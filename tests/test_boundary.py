"""Contour metrics, asserted on cases where a wrong implementation visibly differs.

Failure modes these catch:
  * contours manufactured along the edge of an ignore region, which every image
    has (ego-vehicle strip, unlabelled sky) and which no model can ever match;
  * absent classes scored 0 instead of NaN, which would let a class the dataset
    never labels dominate the macro mean;
  * a tolerance that is not actually applied, so a one-pixel offset reads as a
    total miss on a three-pixel-wide rail;
  * a trimap band that follows the prediction instead of the ground truth.
"""

from __future__ import annotations

import json

import numpy as np
import pytest
import torch
from PIL import Image
from scipy.ndimage import binary_erosion, distance_transform_cdt

from segmentary.engine.boundary import (
    BoundaryConfig,
    BoundaryF1,
    class_contours,
    dilate,
    erode,
    trimap_iou,
)
from segmentary.engine.metrics import ConfusionMatrix
from segmentary.taxonomy import load_mapping, load_space

IGNORE = 255
C = 4


def _square(size: int = 64, lo: int = 20, hi: int = 40, shift: int = 0) -> torch.Tensor:
    """Field of class 0 with a class-1 square, optionally translated along x."""
    lab = torch.zeros(size, size, dtype=torch.long)
    lab[lo:hi, lo + shift : hi + shift] = 1
    return lab


def _naive_contours(labels: torch.Tensor, valid: torch.Tensor, num_classes: int) -> torch.Tensor:
    """The tempting-but-wrong version: erode the class mask alone."""
    ids = torch.arange(num_classes).view(num_classes, 1, 1)
    onehot = (labels.unsqueeze(0) == ids) & valid
    return onehot & ~erode(onehot, 1)


# --------------------------------------------------------------------------
# morphology helpers
# --------------------------------------------------------------------------


def test_dilate_matches_hand_computed_5x5():
    mask = torch.tensor(
        [
            [1, 0, 0, 0, 0],
            [0, 0, 0, 0, 0],
            [0, 0, 1, 1, 0],
            [0, 0, 1, 1, 0],
            [0, 0, 0, 0, 0],
        ],
        dtype=torch.bool,
    )
    expected = torch.tensor(
        [
            [1, 1, 0, 0, 0],
            [1, 1, 1, 1, 1],
            [0, 1, 1, 1, 1],
            [0, 1, 1, 1, 1],
            [0, 1, 1, 1, 1],
        ],
        dtype=torch.bool,
    )
    assert torch.equal(dilate(mask, 1), expected)


def test_erode_matches_hand_computed_5x5():
    mask = torch.tensor(
        [
            [0, 0, 0, 0, 0],
            [0, 1, 1, 1, 0],
            [0, 1, 1, 1, 0],
            [0, 1, 1, 1, 0],
            [0, 0, 0, 0, 0],
        ],
        dtype=torch.bool,
    )
    expected = torch.zeros(5, 5, dtype=torch.bool)
    expected[2, 2] = True
    assert torch.equal(erode(mask, 1), expected)


def test_erode_treats_outside_the_image_as_foreground():
    """The frame border must not be a contour, or every image gains four fake edges."""
    assert torch.equal(
        erode(torch.ones(5, 5, dtype=torch.bool), 1), torch.ones(5, 5, dtype=torch.bool)
    )
    assert torch.equal(
        erode(torch.ones(5, 5, dtype=torch.bool), 2), torch.ones(5, 5, dtype=torch.bool)
    )


def test_radius_zero_is_identity_and_negative_radius_is_rejected():
    mask = torch.tensor([[1, 0], [0, 1]], dtype=torch.bool)
    assert torch.equal(dilate(mask, 0), mask)
    assert torch.equal(erode(mask, 0), mask)
    with pytest.raises(ValueError, match="radius must be >= 0"):
        dilate(mask, -1)


def test_dilate_radius_two_reaches_exactly_two_pixels():
    mask = torch.zeros(7, 7, dtype=torch.bool)
    mask[3, 3] = True
    out = dilate(mask, 2)
    assert int(out.sum()) == 25
    assert bool(out[1, 1]) and bool(out[5, 5]) and not bool(out[0, 3])


# --------------------------------------------------------------------------
# tolerance
# --------------------------------------------------------------------------


def test_tolerance_scales_with_the_diagonal():
    cfg = BoundaryConfig()
    assert cfg.tolerance_px(1024, 2048) == 17
    assert cfg.tolerance_px(512, 512) == 5
    assert cfg.tolerance_px(8, 8) == 1  # min_tolerance floor
    assert BoundaryConfig(tolerance_frac=0.0, min_tolerance=3).tolerance_px(512, 512) == 3


def test_bad_config_fails_loudly():
    with pytest.raises(ValueError, match="tolerance_frac"):
        BoundaryConfig(tolerance_frac=1.5)
    with pytest.raises(ValueError, match="min_tolerance"):
        BoundaryConfig(min_tolerance=-1)


# --------------------------------------------------------------------------
# boundary F1
# --------------------------------------------------------------------------


def test_perfect_prediction_scores_one():
    target = _square()
    m = BoundaryF1(C, IGNORE, BoundaryConfig(tolerance_frac=0.0, min_tolerance=1))
    m.update(target.clone(), target.clone())
    res = m.compute()

    assert float(res.f1[0]) == pytest.approx(1.0)
    assert float(res.f1[1]) == pytest.approx(1.0)
    assert res.macro_f1 == pytest.approx(1.0)
    assert res.macro_precision == pytest.approx(1.0)
    assert res.macro_recall == pytest.approx(1.0)


def test_absent_classes_are_nan_not_zero():
    target = _square()
    m = BoundaryF1(C, IGNORE)
    m.update(target.clone(), target.clone())
    res = m.compute()

    assert bool(torch.isnan(res.f1[2:]).all()), "classes 2 and 3 never occur; they must be NaN"
    assert bool(torch.isnan(res.precision[2:]).all())
    assert res.macro_f1 == pytest.approx(1.0), "NaN classes must stay out of the macro mean"


def test_class_filling_the_frame_has_no_contour_and_is_nan():
    """A single-class image has no contour at all -- not a contour of score zero."""
    target = torch.zeros(16, 16, dtype=torch.long)
    m = BoundaryF1(C, IGNORE)
    m.update(target.clone(), target.clone())
    res = m.compute()
    assert int(res.gt_contour_pixels.sum()) == 0
    assert bool(torch.isnan(res.f1).all())
    assert res.macro_f1 != res.macro_f1, "no scored class -> NaN macro"


def test_inactive_classes_report_nan():
    target = _square()
    active = torch.ones(C, dtype=torch.bool)
    active[1] = False
    m = BoundaryF1(C, IGNORE, active=active)
    m.update(target.clone(), target.clone())
    res = m.compute()
    assert bool(torch.isnan(res.f1[1]))
    assert float(res.f1[0]) == pytest.approx(1.0)


def test_one_pixel_shift_is_forgiven_by_the_tolerance():
    target = _square()
    pred = _square(shift=1)
    m = BoundaryF1(C, IGNORE, BoundaryConfig(tolerance_frac=0.0, min_tolerance=2))
    m.update(pred, target)
    res = m.compute()

    assert res.macro_f1 == pytest.approx(1.0)
    assert float(res.f1[1]) == pytest.approx(1.0)


def test_one_pixel_shift_is_not_forgiven_without_tolerance():
    """Sanity: with theta=0 the same shift must be penalised, or the test above is vacuous."""
    m = BoundaryF1(C, IGNORE, BoundaryConfig(tolerance_frac=0.0, min_tolerance=0))
    m.update(_square(shift=1), _square())
    assert m.compute().macro_f1 < 0.6


def test_far_shift_scores_near_zero():
    # Moved diagonally, not along one axis: a square translated in x alone keeps
    # its top and bottom edges collinear with the ground truth, and those pixels
    # legitimately match.
    target = _square(lo=5, hi=20)
    pred = _square(lo=40, hi=55)
    m = BoundaryF1(C, IGNORE, BoundaryConfig(tolerance_frac=0.0, min_tolerance=2))
    m.update(pred, target)
    res = m.compute()

    assert res.macro_f1 < 0.02, f"got {res.macro_f1}"
    assert float(res.f1[1]) == pytest.approx(0.0)


@pytest.mark.slow
def test_real_railsem19_pair_matches_independent_scipy_reference(railsem19_root, taxonomy_root):
    """Recompute every contour match without the production morphology code.

    The prediction is a translated copy of a real RailSem19 crop, so tolerance
    changes a large, heterogeneous set of boundaries rather than a toy square.
    SciPy's binary erosion and chessboard distance transform are independent of
    the max-pool implementation used by :class:`BoundaryF1`.
    """
    space = load_space(taxonomy_root, "rail_union")
    mapping = load_mapping(taxonomy_root, space, "railsem19")
    label_path = sorted((railsem19_root / "uint8" / "rs19_val").glob("*.png"))[0]
    with Image.open(label_path) as image:
        native = np.asarray(image).copy()
    target_np = mapping.apply(native)[256:768, 704:1216]
    target = torch.from_numpy(target_np.astype(np.int64, copy=False))
    pred = torch.roll(target, shifts=2, dims=1)
    pred[pred == space.ignore_index] = 0

    cfg = BoundaryConfig(tolerance_frac=0.0, min_tolerance=2)
    metric = BoundaryF1(space.num_classes, space.ignore_index, cfg)
    metric.update(pred, target)
    got = metric.compute()

    target_np = target.numpy()
    pred_np = pred.numpy()
    valid = target_np != space.ignore_index
    structure = np.ones((3, 3), dtype=bool)
    reference_counts = np.zeros((4, space.num_classes), dtype=np.int64)
    for class_id in range(space.num_classes):
        gt_mask = (target_np == class_id) & valid
        pred_mask = (pred_np == class_id) & valid
        gt_contour = gt_mask & ~binary_erosion(
            gt_mask | ~valid, structure=structure, border_value=1
        )
        pred_contour = pred_mask & ~binary_erosion(
            pred_mask | ~valid, structure=structure, border_value=1
        )
        reference_counts[1, class_id] = pred_contour.sum()
        reference_counts[3, class_id] = gt_contour.sum()
        if gt_contour.any():
            distance_to_gt = distance_transform_cdt(~gt_contour, metric="chessboard")
            reference_counts[0, class_id] = (
                pred_contour & (distance_to_gt <= cfg.min_tolerance)
            ).sum()
        if pred_contour.any():
            distance_to_pred = distance_transform_cdt(~pred_contour, metric="chessboard")
            reference_counts[2, class_id] = (
                gt_contour & (distance_to_pred <= cfg.min_tolerance)
            ).sum()

    assert np.array_equal(metric.counts.numpy(), reference_counts)
    matched_pred, total_pred, matched_gt, total_gt = reference_counts
    precision = np.divide(
        matched_pred,
        total_pred,
        out=np.zeros_like(matched_pred, dtype=np.float64),
        where=total_pred > 0,
    )
    recall = np.divide(
        matched_gt,
        total_gt,
        out=np.zeros_like(matched_gt, dtype=np.float64),
        where=total_gt > 0,
    )
    expected_f1 = np.divide(
        2 * precision * recall,
        precision + recall,
        out=np.zeros_like(precision),
        where=(precision + recall) > 0,
    )
    seen = (total_pred + total_gt) > 0
    assert torch.allclose(
        got.f1[torch.from_numpy(seen)],
        torch.from_numpy(expected_f1[seen]),
        atol=0.0,
        rtol=0.0,
    )


def test_class_predicted_but_absent_from_gt_scores_zero_not_nan():
    target = torch.zeros(32, 32, dtype=torch.long)
    target[:, 16:] = 2  # classes 0 and 2 present, class 1 never
    pred = target.clone()
    pred[4:12, 4:12] = 1  # a hallucinated class-1 blob with a real contour

    m = BoundaryF1(C, IGNORE, BoundaryConfig(tolerance_frac=0.0, min_tolerance=1))
    m.update(pred, target)
    res = m.compute()

    assert float(res.f1[1]) == pytest.approx(0.0)
    assert bool(torch.isnan(res.f1[3])), "class 3 is in neither map and stays NaN"


# --------------------------------------------------------------------------
# ignore semantics -- the reason this module is not three lines long
# --------------------------------------------------------------------------


def test_ignore_hole_manufactures_no_contour():
    """One class everywhere plus an unlabelled hole: there is no contour to score."""
    target = torch.ones(32, 32, dtype=torch.long)
    target[10:20, 10:20] = IGNORE
    pred = torch.ones(32, 32, dtype=torch.long)

    valid = target != IGNORE
    naive = _naive_contours(target, valid, C)
    assert int(naive.sum()) > 0, "sanity: a naive implementation does report a contour here"

    got = class_contours(target, valid, C)
    assert int(got.sum()) == 0

    m = BoundaryF1(C, IGNORE)
    m.update(pred, target)
    res = m.compute()
    assert int(res.gt_contour_pixels.sum()) == 0
    assert int(res.pred_contour_pixels.sum()) == 0


def test_real_contour_survives_while_ignore_edge_does_not():
    """Exactly the true class boundary is counted; the hole's rim contributes nothing."""
    target = torch.zeros(32, 32, dtype=torch.long)
    target[:, 16:] = 1
    target[4:9, 4:9] = IGNORE  # a hole well away from the class boundary
    valid = target != IGNORE

    got = class_contours(target, valid, C)
    assert int(got[0].sum()) == 32, "class 0 contour is column 15, one pixel per row"
    assert int(got[1].sum()) == 32, "class 1 contour is column 16"
    assert bool(got[0][:, 15].all()) and bool(got[1][:, 16].all())
    assert int(got[2:].sum()) == 0

    naive = _naive_contours(target, valid, C)
    assert int(naive[0].sum()) > 32, "sanity: the naive version adds the rim of the hole"


def test_prediction_under_ignore_cannot_change_the_score():
    g = torch.Generator().manual_seed(7)
    target = _square()
    target[48:60, 48:60] = IGNORE
    pred = target.clone()
    pred[target == IGNORE] = 0

    m = BoundaryF1(C, IGNORE)
    m.update(pred, target)
    clean = m.compute()

    noisy = pred.clone()
    noisy[target == IGNORE] = torch.randint(0, C, (int((target == IGNORE).sum()),), generator=g)
    m2 = BoundaryF1(C, IGNORE)
    m2.update(noisy, target)
    dirty = m2.compute()

    assert torch.equal(clean.gt_contour_pixels, dirty.gt_contour_pixels)
    assert torch.equal(clean.pred_contour_pixels, dirty.pred_contour_pixels)
    assert clean.macro_f1 == dirty.macro_f1


def test_fully_ignored_image_is_skipped():
    m = BoundaryF1(C, IGNORE)
    m.update(torch.zeros(8, 8, dtype=torch.long), torch.full((8, 8), IGNORE, dtype=torch.long))
    assert int(m.counts.sum()) == 0


# --------------------------------------------------------------------------
# dataset-level accumulation
# --------------------------------------------------------------------------


def test_counts_pool_across_images():
    a_pred, a_target = _square(shift=1), _square()
    b_pred = b_target = torch.zeros(64, 64, dtype=torch.long)

    cfg = BoundaryConfig(tolerance_frac=0.0, min_tolerance=1)
    streamed = BoundaryF1(C, IGNORE, cfg)
    streamed.update(a_pred, a_target)
    streamed.update(b_pred, b_target)

    batched = BoundaryF1(C, IGNORE, cfg)
    batched.update(torch.stack([a_pred, b_pred]), torch.stack([a_target, b_target]))

    assert torch.equal(streamed.counts, batched.counts)
    # The contour-free second image must not move the score, which per-image
    # averaging (0 or 1 for an empty image) could not achieve.
    solo = BoundaryF1(C, IGNORE, cfg)
    solo.update(a_pred, a_target)
    assert streamed.compute().macro_f1 == solo.compute().macro_f1


def test_reset_clears_state():
    m = BoundaryF1(C, IGNORE)
    m.update(_square(), _square())
    m.reset()
    assert int(m.counts.sum()) == 0


def test_shape_and_range_errors_are_loud():
    m = BoundaryF1(C, IGNORE)
    with pytest.raises(ValueError, match="!="):
        m.update(torch.zeros(4, 4, dtype=torch.long), torch.zeros(4, 5, dtype=torch.long))
    with pytest.raises(ValueError, match="predictions outside"):
        m.update(torch.full((4, 4), C, dtype=torch.long), torch.zeros(4, 4, dtype=torch.long))
    with pytest.raises(ValueError, match="taxonomy LUT was probably not applied"):
        m.update(torch.zeros(4, 4, dtype=torch.long), torch.full((4, 4), 33, dtype=torch.long))


# --------------------------------------------------------------------------
# trimap IoU
# --------------------------------------------------------------------------


def test_trimap_iou_is_one_for_a_perfect_prediction():
    target = _square()
    iou = trimap_iou(target.clone(), target.clone(), C, band_px=3)
    assert float(iou[0]) == pytest.approx(1.0)
    assert float(iou[1]) == pytest.approx(1.0)
    assert bool(torch.isnan(iou[2:]).all())


def test_trimap_iou_ignores_errors_far_from_the_boundary():
    """The band follows the ground truth, so an interior blunder is invisible to it."""
    target = torch.zeros(64, 64, dtype=torch.long)
    target[:, 32:] = 1
    pred = target.clone()
    pred[4:9, 4:9] = 2  # 25 wrong pixels, 23px from the only boundary

    band = trimap_iou(pred, target, C, band_px=3)
    assert float(band[0]) == pytest.approx(1.0)
    assert float(band[1]) == pytest.approx(1.0)

    cm = ConfusionMatrix(C, IGNORE)
    cm.update(pred, target)
    assert cm.compute().iou[0] < 1.0, "sanity: plain IoU does see the blunder"


def test_trimap_iou_penalises_a_shifted_boundary():
    target = torch.zeros(64, 64, dtype=torch.long)
    target[:, 32:] = 1
    pred = torch.zeros(64, 64, dtype=torch.long)
    pred[:, 34:] = 1

    band = trimap_iou(pred, target, C, band_px=3)
    full = ConfusionMatrix(C, IGNORE)
    full.update(pred, target)
    plain = full.compute().iou

    assert float(band[1]) < float(plain[1]), "the band must amplify a boundary error"
    assert float(band[1]) < 0.85


def test_trimap_band_width_controls_the_scored_area():
    target = _square()
    pred = _square(shift=2)
    narrow = float(trimap_iou(pred, target, C, band_px=1)[1])
    wide = float(trimap_iou(pred, target, C, band_px=8)[1])
    assert narrow < wide, "a wider band admits more correctly-labelled interior"


def test_trimap_iou_excludes_ignore_pixels():
    target = torch.zeros(32, 32, dtype=torch.long)
    target[:, 16:] = 1
    pred = target.clone()
    target[0:4, 14:18] = IGNORE  # straddles the boundary, so it is inside the band
    pred[0:4, 14:18] = 2  # would be scored as wrong if ignore leaked through

    iou = trimap_iou(pred, target, C, band_px=2)
    assert float(iou[0]) == pytest.approx(1.0)
    assert float(iou[1]) == pytest.approx(1.0)
    assert bool(torch.isnan(iou[2])), "the class only 'predicted' under ignore must not appear"


def test_trimap_band_zero_scores_the_contour_itself():
    target = torch.zeros(16, 16, dtype=torch.long)
    target[:, 8:] = 1
    iou = trimap_iou(target.clone(), target.clone(), C, band_px=0)
    assert float(iou[0]) == pytest.approx(1.0)
    with pytest.raises(ValueError, match="band_px must be >= 0"):
        trimap_iou(target, target, C, band_px=-1)


# --------------------------------------------------------------------------
# the results.json contract -- compute() is written straight into it
# --------------------------------------------------------------------------


def test_compute_result_is_json_serialisable_with_allow_nan_false():
    """write_results() uses allow_nan=False, so NaN and Tensors must not survive as_dict."""
    target = _square()
    m = BoundaryF1(C, IGNORE)
    m.update(target.clone(), target.clone())
    names = [f"c{i}" for i in range(C)]
    payload = m.compute().as_dict(names)

    json.dumps(payload, allow_nan=False)  # this is exactly what write_results does
    assert payload["per_class_f1"]["c2"] is None, "an absent class must be null, not NaN"
    assert payload["per_class_f1"]["c1"] == pytest.approx(1.0)
    assert payload["gt_contour_pixels"]["c1"] > 0


def test_all_nan_result_still_serialises():
    m = BoundaryF1(C, IGNORE)
    m.update(torch.zeros(8, 8, dtype=torch.long), torch.zeros(8, 8, dtype=torch.long))
    payload = m.compute().as_dict([f"c{i}" for i in range(C)])
    assert payload["macro_f1"] is None
    json.dumps(payload, allow_nan=False)


# --------------------------------------------------------------------------
# loud failure on malformed input
# --------------------------------------------------------------------------


def test_trimap_iou_rejects_out_of_space_target_ids():
    target = torch.zeros(8, 8, dtype=torch.long)
    target[:, 4:] = 33
    with pytest.raises(ValueError, match="taxonomy LUT was probably not applied"):
        trimap_iou(torch.zeros(8, 8, dtype=torch.long), target, C, band_px=1)


def test_class_contours_rejects_mismatched_valid_shape():
    with pytest.raises(ValueError, match="must match"):
        class_contours(torch.zeros(8, 8, dtype=torch.long), torch.ones(8, dtype=torch.bool), C)


def test_empty_batch_is_a_no_op_like_confusion_matrix():
    empty = torch.zeros(0, 8, 8, dtype=torch.long)
    m = BoundaryF1(C, IGNORE)
    m.update(empty, empty.clone())
    assert int(m.counts.sum()) == 0
    assert bool(torch.isnan(trimap_iou(empty, empty.clone(), C, band_px=2)).all())


def test_morphology_thresholds_consistently_at_every_radius():
    """dilate(x, 0) and dilate(x, 1) must agree on what is foreground."""
    x = torch.zeros(5, 5)
    x[2, 2] = 0.3  # below the 0.5 used internally, above the 0 used by .to(bool)
    assert bool(dilate(x, 0)[2, 2])
    assert bool(dilate(x, 1)[2, 2]) and int(dilate(x, 1).sum()) == 9
    assert bool(erode(torch.full((5, 5), 0.3), 1).all())
