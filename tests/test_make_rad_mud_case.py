"""make_rad_mud_case: the cross-validation false-positive section on small synthetic data."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scripts import make_rad_mud_case as case
from scripts.collect_rtis_statistics import mud_counts

MUD, IGNORE, CAB = case.MUD, case.IGNORE, case.CAB


def counts(tp: int, fp: int, fn: int) -> dict:
    matrix = np.zeros((case.MUD + 1, case.MUD + 1), np.int64)
    matrix[MUD, MUD], matrix[0, MUD], matrix[MUD, 0], matrix[0, 0] = tp, fp, fn, 100
    return mud_counts(matrix, MUD)


def image(key: str, fp: int, gt: int = 0, viewpoint: str = CAB, fold: int = 0) -> case.CvImage:
    group = key.split("/")[0]
    return case.CvImage(key, fold, group, viewpoint, counts(gt // 2, fp, gt - gt // 2))


# ----------------------------------------------------------------------------- ranking


def test_rank_false_positives_orders_by_fp_then_key_and_keeps_train_camera_only():
    images = [
        image("b/0002", 50),
        image("a/0001", 50),
        image("c/0003", 900, viewpoint="track-level"),
        image("d/0004", 0),
        image("e/0005", 70, gt=40),
        image("f/0006", 10),
    ]
    ranked = case.rank_false_positives(images, n=3)
    assert [i.key for i in ranked] == ["e/0005", "a/0001", "b/0002"]
    assert [i.key for i in case.rank_false_positives(images, n=10)][-1] == "f/0006"
    assert all(i.fp > 0 and i.viewpoint == CAB for i in case.rank_false_positives(images, 10))


# ----------------------------------------------------------------------------- zoom box


def test_fp_zoom_box_is_a_16_9_window_on_the_densest_false_positives():
    mask = np.zeros((1080, 1920), bool)
    mask[800:900, 1300:1500] = True  # the bulk
    mask[100, 50] = mask[1000, 1900] = True  # strays
    left, top, right, bottom = case.fp_zoom_box(mask)
    assert (right - left, bottom - top) == (480, 270)  # min_w; the bulk is small
    assert left >= 0 and right <= 1920 and top >= 0 and bottom <= 1080
    assert mask[top:bottom, left:right].sum() == 200 * 100  # holds the whole bulk
    assert case.fp_zoom_box(mask) == (left, top, right, bottom)  # deterministic


def test_fp_zoom_box_caps_wide_spreads_at_a_2x_zoom():
    mask = np.zeros((1080, 1920), bool)
    mask[900:1000, 0:1920] = True  # a band across the frame
    mask[950:1000, 1200:1500] = False
    left, top, right, bottom = case.fp_zoom_box(mask)
    assert (right - left, bottom - top) == (960, 540)
    assert bottom == 1080 or top <= 900
    inside = mask[top:bottom, left:right].sum()
    others = [mask[top:bottom, x : x + 960].sum() for x in range(0, 1920 - 960 + 1, 8) if x != left]
    assert inside >= max(others)


def test_fp_zoom_box_refuses_an_empty_mask():
    with pytest.raises(case.CaseError, match="no false-positive pixel"):
        case.fp_zoom_box(np.zeros((90, 160), bool))


# ----------------------------------------------------------------------------- recount check


def write_png(path: Path, array: np.ndarray) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(array.astype(np.uint8), mode="L").save(path)
    return path


def labels() -> tuple[np.ndarray, np.ndarray]:
    gt = np.zeros((18, 32), np.uint8)
    gt[10:14, 4:10] = MUD  # 24 px
    gt[0, :] = IGNORE
    pred = np.zeros_like(gt)
    pred[10:14, 6:12] = MUD  # 16 TP, 8 FP
    pred[0, 0:5] = MUD  # on ignore: not counted
    pred[2:4, 20:25] = MUD  # 10 FP
    return gt, pred


def test_checked_prediction_accepts_matching_counts_and_refuses_a_mismatch(tmp_path):
    gt, pred = labels()
    path = write_png(tmp_path / "pred.png", pred)
    good = counts(16, 18, 8)
    assert np.array_equal(case.checked_prediction(path, "job key", gt, good), pred)
    with pytest.raises(case.CaseError, match=r"job key: prediction PNG gives mud TP/FP/FN"):
        case.checked_prediction(path, "job key", gt, counts(16, 17, 8))
    with pytest.raises(case.CaseError, match="prediction shape"):
        case.checked_prediction(path, "job key", gt[:-1], good)


# ----------------------------------------------------------------------------- coverage


def spec() -> dict:
    rows = {
        "g1/0001": ("g1", 0, True),
        "g1/0002": ("g1", 0, True),
        "g2/0003": ("g2", 1, True),
        "g2/0004": ("g2", 1, False),  # small image, never scored
        "h/0005": ("h", None, False),
    }
    return {
        "scheme": "stratified-group-kfold",
        "method": {"folds": 2},
        "assignments": {
            key: {
                "group": group,
                "fold": fold,
                "scored": scored,
                "role": "holdout" if fold is None else "cv_fold",
                "image_sha256": f"sha-{key}",
            }
            for key, (group, fold, scored) in rows.items()
        },
    }


def test_check_cv_coverage_requires_every_scored_image_exactly_once():
    s = spec()

    def row(key: str) -> tuple[str, str]:
        return key, f"sha-{key}"

    case.check_cv_coverage(s, {0: [row("g1/0001"), row("g1/0002")], 1: [row("g2/0003")]})
    with pytest.raises(case.CaseError, match=r"fold 0: .*missing \['g1/0002'\]"):
        case.check_cv_coverage(s, {0: [row("g1/0001")], 1: [row("g2/0003")]})
    with pytest.raises(case.CaseError, match=r"fold 1: .*extra \['g1/0001'\]"):
        case.check_cv_coverage(
            s, {0: [row("g1/0001"), row("g1/0002")], 1: [row("g2/0003"), row("g1/0001")]}
        )
    with pytest.raises(case.CaseError, match="1 duplicates"):
        case.check_cv_coverage(
            s, {0: [row("g1/0001"), row("g1/0002"), row("g1/0001")], 1: [row("g2/0003")]}
        )
    with pytest.raises(case.CaseError, match="folds \\[0\\], the spec has 2"):
        case.check_cv_coverage(s, {0: [row("g1/0001"), row("g1/0002")]})
    with pytest.raises(case.CaseError, match="image sha256 differs"):
        case.check_cv_coverage(s, {0: [row("g1/0001"), ("g1/0002", "other")], 1: [row("g2/0003")]})


# ----------------------------------------------------------------------------- figure + text


def fold_dataset(tmp_path: Path) -> tuple[case.CvCase, case.CvImage]:
    """One fold dataset with one val image, its prediction PNG and a CvCase around it."""
    gt, pred = labels()
    root = tmp_path / "fold-0"
    key = "g1/0001"
    rgb = np.random.default_rng(0).integers(0, 255, (*gt.shape, 3), dtype=np.uint8)
    (root / "images/val/g1").mkdir(parents=True)
    Image.fromarray(rgb).save(root / "images/val" / f"{key}.png")
    write_png(root / "masks/val" / f"{key}.png", gt)
    sha = hashlib.sha256((root / "images/val" / f"{key}.png").read_bytes()).hexdigest()
    sample = {
        "key": key,
        "split": "val",
        "group": "g1",
        "stem": "0001",
        "image_extension": ".png",
        "image_sha256": sha,
        "class_pixels": {str(MUD): int((gt == MUD).sum())},
    }
    (root / "audit").mkdir()
    (root / "audit/samples.json").write_text(json.dumps([sample]))
    predictions = tmp_path / "predictions"
    write_png(predictions / f"{key}.png", pred)
    arm = case.Arm(root, {sha: {"viewpoint": CAB}})
    item = case.CvImage(key, 0, "g1", CAB, counts(16, 18, 8))
    cv = case.CvCase(
        "cv-test",
        {0: case.CvFold(0, "job-fold-0", arm, predictions)},
        [item],
        {CAB: {"images": 1, "focus_precision": 16 / 34}},
        1,
        3,
        "f" * 64,
    )
    return cv, item


def test_figure_cv_fp_draws_checked_predictions_and_counts_fp_outside_the_zoom(tmp_path):
    cv, item = fold_dataset(tmp_path)
    out = tmp_path / "fig.jpg"
    notes = case.figure_cv_fp(cv, [item], out)
    assert out.is_file() and Image.open(out).width == 3 * 432 + 8
    left, top, right, bottom = notes[0]["box"]
    gt, pred = labels()
    fp = (gt != MUD) & (gt != IGNORE) & (pred == MUD)
    assert notes[0]["fp_outside"] == 18 - int(fp[top:bottom, left:right].sum())
    first = out.read_bytes()
    case.figure_cv_fp(cv, [item], out)
    assert out.read_bytes() == first  # deterministic
    bad = case.CvImage(item.key, 0, "g1", CAB, counts(16, 18, 9))
    with pytest.raises(case.CaseError, match="job-fold-0 g1/0001: prediction PNG gives"):
        case.figure_cv_fp(cv, [bad], out)


def test_cv_section_renders_summary_figure_and_table(tmp_path, monkeypatch):
    images = [
        image("g1/0010", 300),
        image("g2/0020", 100, gt=50, fold=1),
        image("g3/0030", 0, gt=20),
        image("g4/0040", 999, viewpoint="track-level"),
    ]
    cv = case.CvCase(
        "cv-test", {}, images, {CAB: {"images": 3, "focus_precision": 0.626}}, 1, 20, "f" * 64
    )
    shown = case.rank_false_positives(images)
    text = "\n".join(case.cv_section(cv, shown, 8, 5, "assets/x"))
    assert text.startswith(
        "## 8. Cross-validation: where the best model predicts mud that is not there\n"
    )
    assert "the best of the 20 complete setups" in text
    assert "pooled mud precision is 62.6%, so 37.4% of the pixels predicted as mud" in text
    assert "**400 false-positive mud pixels** on train-camera images, in 2 of 3 images." in text
    assert "300 (75.0%) are on 1 image with no mud in the ground truth" in text
    assert "100 (25.0%) are on 1 image that have mud" in text
    assert "The 2 images with the most (figure 5) hold 100.0%." in text
    assert f"![Train-camera false-positive mud in cross-validation](assets/x/{case.CV_FIGURE})" in (
        text
    )
    assert "| `0010` | `g1` | 0 | no | 0 | 300 | 75.0% | — |" in text
    assert "| `0020` | `g2` | 1 | yes | 50 | 100 | 25.0% | 16.7 |" in text
    assert "0040" not in text and case.CV_OBSERVED not in text  # observation: other images
    monkeypatch.setattr(case, "CV_OBSERVED_KEYS", ("g1/0010", "g2/0020"))
    assert case.CV_OBSERVED in "\n".join(case.cv_section(cv, shown, 8, 5, "assets/x"))
    cv.rank = 2
    assert "## 8. Cross-validation: where the eomt_dinov3_large model predicts" in "\n".join(
        case.cv_section(cv, shown, 8, 5, "a")
    )
    with pytest.raises(case.CaseError, match="no false-positive mud"):
        case.cv_section(cv, [], 8, 5, "a")
