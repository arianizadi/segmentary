"""STAR-C geometry, full-volume ray targets, patch targets, rendering and fusion.

Pure NumPy/SciPy/Torch: no nnU-Net or dynamic-network-architectures needed.
Synthetic shapes use the Task07 plan spacing (2.5 x 0.8125 x 0.8125 mm).
"""

from __future__ import annotations

import copy
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
import torch

from segmentary.medical import recipe_plan
from segmentary.medical import star_completion as sc

SPACING = (2.5, 0.8125, 0.8125)
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def bounded_threads():
    previous = torch.get_num_threads()
    torch.set_num_threads(4)
    yield
    torch.set_num_threads(previous)


@pytest.fixture(scope="module")
def geometry() -> sc.StarGeometry:
    return sc.star_geometry(96)


def _coordinates(shape, spacing=SPACING):
    return np.meshgrid(
        *[np.arange(n) * s for n, s in zip(shape, spacing, strict=True)], indexing="ij"
    )


def _ellipsoid(shape, centre_vox, semi_axes_mm, spacing=SPACING):
    z, y, x = _coordinates(shape, spacing)
    c = np.asarray(centre_vox) * np.asarray(spacing)
    a = np.asarray(semi_axes_mm)
    return ((z - c[0]) / a[0]) ** 2 + ((y - c[1]) / a[1]) ** 2 + ((x - c[2]) / a[2]) ** 2 <= 1


def _ellipsoid_radius(directions, semi_axes_mm):
    return 1.0 / np.sqrt(((directions / np.asarray(semi_axes_mm)) ** 2).sum(1))


def _dice(a, b):
    return 2 * float((a & b).sum()) / float(a.sum() + b.sum())


# ---------------------------------------------------------------------------
# Options and plans
# ---------------------------------------------------------------------------


def test_options_resolve_every_default_and_fail_closed():
    resolved = sc.validate_starc_options(None)
    assert resolved == sc.STARC_DEFAULTS
    assert resolved["rays"] == 96 and resolved["gate_bias"] == -2.0
    assert (resolved["tau_min_mm"], resolved["tau_max_mm"]) == (0.5, 5.0)
    with pytest.raises(ValueError, match="Unknown"):
        sc.validate_starc_options({"rayz": 64})
    for bad in (
        {"rays": 4},
        {"fusion": "add"},
        {"lesion_labels": [0]},
        {"centre_prior": 1.0},
        {"teacher_probability": 1.5},
        {"fusion_channels": [1, 1]},
        {"freeze_backbone": 1},
        {"ray_weight": -1.0},
    ):
        with pytest.raises(ValueError, match="Invalid"):
            sc.validate_starc_options(bad)
    with pytest.raises(ValueError, match="tau"):
        sc.validate_starc_options({"tau_init_mm": 6.0})
    assert set(sc.network_options(resolved)) | set(sc.training_options(resolved)) == set(resolved)


def test_plan_transfer_keeps_resenc_keywords_and_binds_spacing():
    plan = {
        "configurations": {
            "3d_fullres": {
                "spacing": [2.5, 0.8125, 0.8125],
                "architecture": {
                    "network_class_name": "dynamic_network_architectures.architectures.unet."
                    "ResidualEncoderUNet",
                    "arch_kwargs": {"n_stages": 7, "features_per_stage": [32] * 7},
                },
            }
        }
    }
    transferred, record = sc.transfer_starc_plan(plan, {"max_instances": 4})
    after = transferred["configurations"]["3d_fullres"]["architecture"]
    assert after["network_class_name"] == sc.STARC_CLASS
    assert after["arch_kwargs"]["features_per_stage"] == [32] * 7
    assert after["arch_kwargs"]["starc_spacing"] == [2.5, 0.8125, 0.8125]
    assert after["arch_kwargs"]["starc_max_instances"] == 4
    assert "starc_ray_weight" not in after["arch_kwargs"]  # training options stay out
    assert record["starc_options"]["max_instances"] == 4
    assert plan["configurations"]["3d_fullres"]["architecture"]["arch_kwargs"].keys() == {
        "n_stages",
        "features_per_stage",
    }
    dirty = copy.deepcopy(plan)
    dirty["configurations"]["3d_fullres"]["architecture"]["arch_kwargs"]["starc_rays"] = 96
    with pytest.raises(ValueError, match="already"):
        sc.transfer_starc_plan(dirty, None)


def test_dataset_check_names_lesion_labels_and_fusion_channels():
    task07 = {"labels": {"background": 0, "pancreas": 1, "mass": 2}}
    options = sc.validate_starc_options(None)
    assert sc.check_starc_dataset(options, task07) == {
        "lesion_labels": ["mass"],
        "fusion_channels": ["pancreas", "mass"],
    }
    kits = {
        "labels": {"background": 0, "kidney": [1, 2, 3], "masses": [2, 3], "tumor": 2},
        "regions_class_order": [1, 3, 2],
    }
    kits_options = sc.validate_starc_options({"lesion_labels": [2], "fusion_channels": [1, 2]})
    assert sc.check_starc_dataset(kits_options, kits)["fusion_channels"] == ["masses", "tumor"]
    with pytest.raises(ValueError, match="background"):
        sc.check_starc_dataset(sc.validate_starc_options({"fusion_channels": [0, 2]}), task07)
    with pytest.raises(ValueError, match="lesion_labels"):
        sc.check_starc_dataset(sc.validate_starc_options({"lesion_labels": [3]}), task07)


# ---------------------------------------------------------------------------
# Ray geometry
# ---------------------------------------------------------------------------


def test_fibonacci_rays_and_hull(geometry):
    assert geometry.directions.shape == (96, 3)
    assert np.allclose(np.linalg.norm(geometry.directions, axis=1), 1)
    assert geometry.facets.shape == (2 * 96 - 4, 3)  # a closed triangulated sphere
    assert np.allclose(geometry.directions, sc.fibonacci_directions(96))
    assert len(geometry.digest()) == 64


def test_lookup_radius_matches_exact_polyhedron(geometry):
    rng = np.random.default_rng(0)
    unit = rng.normal(size=(20000, 3))
    unit /= np.linalg.norm(unit, axis=1, keepdims=True)
    smooth = 10 + 3 * geometry.directions[:, 0] + 2 * geometry.directions[:, 2] ** 2
    exact = sc.exact_star_radius(geometry, smooth, unit)
    error = np.abs(geometry.radius(smooth, unit) - exact)
    assert (error > 1e-9).mean() < 1e-3 and error.max() < 0.02
    rough = rng.uniform(5, 15, 96)
    error = np.abs(geometry.radius(rough, unit) - sc.exact_star_radius(geometry, rough, unit))
    assert np.median(error) < 1e-9 and error.max() < 0.1
    # At a ray direction the radius is that ray's length.
    assert np.allclose(geometry.radius(rough, geometry.directions), rough, atol=1e-6)
    # A constant star is the inscribed polyhedron of the sphere.
    constant = geometry.radius(np.full(96, 10.0), unit)
    assert constant.max() <= 10 + 1e-9 and constant.min() > 9.3


def test_torch_renderer_radius_equals_numpy(geometry):
    renderer = sc.StarRenderer(96, SPACING, (256, 512))
    rng = np.random.default_rng(1)
    unit = rng.normal(size=(5000, 3))
    unit /= np.linalg.norm(unit, axis=1, keepdims=True)
    radii = rng.uniform(4, 20, 96)
    got = renderer.radius(torch.tensor(radii), torch.tensor(unit)).numpy()
    assert np.allclose(got, geometry.radius(radii, unit), atol=1e-9)
    assert not any(name.startswith(("directions", "lut")) for name in renderer.state_dict())


# ---------------------------------------------------------------------------
# Full-volume ray targets on synthetic shapes
# ---------------------------------------------------------------------------


def test_sphere_rays_are_its_radius_at_anisotropic_spacing(geometry):
    shape = (40, 120, 120)
    sphere = _ellipsoid(shape, (20, 60, 60), (15, 15, 15))
    targets = sc.compute_case_targets(sphere.astype(np.uint8) * 2, SPACING, [2], geometry)
    assert targets.count == 1
    assert np.allclose(targets.centres[0], (20, 60, 60))
    assert targets.max_edt_mm[0] == pytest.approx(15, abs=1.3)
    error = targets.rays_mm[0] - 15
    # The voxel boundary is a staircase: within half a voxel along each axis.
    assert np.abs(np.median(error)) < 0.5 and np.abs(error).max() < 1.3
    star = sc.render_star_mask(shape, SPACING, targets.centres[0], targets.rays_mm[0], geometry)
    assert _dice(star, sphere) > 0.95


def test_ellipsoid_rays_match_the_analytic_surface(geometry):
    shape = (36, 100, 100)
    axes = (20.0, 12.0, 8.0)
    ellipsoid = _ellipsoid(shape, (18, 50, 50), axes)
    targets = sc.compute_case_targets(ellipsoid.astype(np.uint8) * 2, SPACING, [2], geometry)
    expected = _ellipsoid_radius(geometry.directions, axes)
    error = targets.rays_mm[0] - expected
    assert np.abs(np.median(error)) < 0.5 and np.abs(error).max() < 1.5
    star = sc.render_star_mask(shape, SPACING, targets.centres[0], targets.rays_mm[0], geometry)
    assert _dice(star, ellipsoid) > 0.93


def test_non_convex_rays_stop_at_the_first_exit(geometry):
    # A horseshoe: a half torus plus a block; not star-convex from any point.
    shape = (24, 120, 120)
    z, y, x = _coordinates(shape)
    cz, cy, cx = 12 * 2.5, 60 * 0.8125, 60 * 0.8125
    ring = (np.hypot(y - cy, x - cx) - 25) ** 2 + (z - cz) ** 2 <= 8**2
    shape_mask = ring & (x >= cx - 4)
    targets = sc.compute_case_targets(shape_mask.astype(np.uint8) * 2, SPACING, [2], geometry)
    assert targets.count == 1
    centre = targets.centres[0]
    assert shape_mask[tuple(np.rint(centre).astype(int))]
    # Each ray is inside just before its exit and (up to voxel-corner grazes) outside after it.
    origin = centre * np.asarray(SPACING)
    regrazed = 0
    for direction, distance in zip(geometry.directions, targets.rays_mm[0], strict=True):
        before = np.rint((origin + max(distance - 0.02, 0) * direction) / SPACING).astype(int)
        after = np.rint((origin + (distance + 0.3) * direction) / SPACING).astype(int)
        assert shape_mask[tuple(before)]
        regrazed += bool(np.all((after >= 0) & (after < shape)) and shape_mask[tuple(after)])
    assert regrazed <= 2
    # The star covers the visible part only: well below the full horseshoe.
    star = sc.render_star_mask(shape, SPACING, centre, targets.rays_mm[0], geometry)
    assert (star & shape_mask).sum() < 0.6 * shape_mask.sum()
    # A march that is too short reports no exit.
    _, exited = sc.march_exit_mm(
        (shape_mask * 1).astype(np.uint16),
        1,
        centre[None],
        geometry.directions,
        SPACING,
        step_mm=0.2,
        max_mm=1.0,
    )
    assert not exited.all()


def test_multiple_lesions_labels_and_empty_cases(geometry):
    shape = (40, 160, 160)
    segmentation = np.zeros(shape, np.uint8)
    segmentation[_ellipsoid(shape, (20, 80, 80), (40, 40, 40))] = 1  # host organ
    lesions = [((12, 50, 50), 6.0, 2), ((28, 110, 70), 9.0, 3), ((20, 60, 120), 4.0, 2)]
    for centre, radius, label in lesions:
        segmentation[_ellipsoid(shape, centre, (radius,) * 3)] = label
    targets = sc.compute_case_targets(segmentation, SPACING, [2, 3], geometry)
    assert targets.count == 3
    assert targets.instances.dtype == np.uint16 and targets.edt_mm.dtype == np.float16
    order = np.argsort(targets.volume_mm3)
    for k, (centre, radius, label) in zip(
        order[::-1], sorted(lesions, key=lambda item: -item[1]), strict=True
    ):
        assert np.linalg.norm((targets.centres[k] - centre) * SPACING) < 1.5
        assert targets.labels[k] == label
        assert targets.volume_mm3[k] == pytest.approx(4 / 3 * np.pi * radius**3, rel=0.25)
        assert np.median(targets.rays_mm[k]) == pytest.approx(radius, abs=1.0)
    # The crop holds every lesion voxel and the instance ids follow the components.
    low = targets.crop_origin
    full = np.zeros(shape, np.uint16)
    window = tuple(slice(a, a + n) for a, n in zip(low, targets.instances.shape, strict=True))
    full[window] = targets.instances
    assert np.array_equal(full > 0, np.isin(segmentation, [2, 3]))
    only_two = sc.compute_case_targets(segmentation, SPACING, [2], geometry)
    assert only_two.count == 2
    empty = sc.compute_case_targets(np.zeros((8, 8, 8), np.uint8), SPACING, [2], geometry)
    assert empty.count == 0 and empty.rays_mm.shape == (0, 96)


def test_case_target_files_round_trip_and_verification(tmp_path, geometry):
    shape = (20, 60, 60)
    segmentation = (_ellipsoid(shape, (10, 30, 30), (8, 8, 8)) * 2).astype(np.uint8)
    seg_file = tmp_path / "case_seg.npy"
    np.save(seg_file, segmentation[None])
    targets = sc.compute_case_targets(segmentation, SPACING, [2], geometry)
    folder = tmp_path / "targets"
    folder.mkdir()
    digest = sc.save_case_targets(folder / "case.npz", targets)
    with pytest.raises(FileExistsError):
        sc.save_case_targets(folder / "case.npz", targets)
    loaded = sc.load_case_targets(folder / "case.npz")
    for name, value in targets.arrays().items():
        assert np.array_equal(getattr(loaded, name), value)
    manifest = {
        "schema": sc.TARGET_SCHEMA,
        **copy.deepcopy(recipe_plan.STARC_TARGET_METHOD),
        "rays": 96,
        "directions_sha256": geometry.digest(),
        "spacing": list(SPACING),
        "lesion_labels": [2],
        "cases": {"case": {"sha256": digest, "segmentation_sha256": sc.sha256_file(seg_file)}},
    }
    (folder / "manifest.json").write_text(json.dumps(manifest))
    good = dict(cases=["case"], spacing=SPACING, rays=96, lesion_labels=[2])
    sc.verify_star_targets(folder, **good, segmentation_files={"case": seg_file})
    sc.verify_star_targets(folder, **good, manifest_sha256=sc.sha256_file(folder / "manifest.json"))
    with pytest.raises(ValueError, match="bound sha256"):
        sc.verify_star_targets(folder, **good, manifest_sha256="0" * 64)
    with pytest.raises(ValueError, match="spacing"):
        sc.verify_star_targets(folder, **(good | {"spacing": (2.0, 0.8, 0.8)}))
    with pytest.raises(ValueError, match="lesion labels"):
        sc.verify_star_targets(folder, **(good | {"lesion_labels": [2, 3]}))
    with pytest.raises(ValueError, match="missing"):
        sc.verify_star_targets(folder, **(good | {"cases": ["case", "other"]}))
    np.save(seg_file, np.zeros_like(segmentation)[None])
    with pytest.raises(ValueError, match="different segmentation"):
        sc.verify_star_targets(folder, **good, segmentation_files={"case": seg_file})


# ---------------------------------------------------------------------------
# Augmentation frames and patch targets
# ---------------------------------------------------------------------------


def test_frame_composition_inverts_crop_spatial_and_mirror():
    angle = 0.3
    rotation = np.array([[math.cos(angle), -math.sin(angle)], [math.sin(angle), math.cos(angle)]])
    spatial = sc.frame_record((1, 2), rotation * 1.2, np.array([40.0, 35.0]))
    mirror = sc.mirror_record((0, 2), (16, 64, 48))
    frame = sc.compose_patch_frame([5, -3, 7], [spatial, mirror])
    p = np.array([[2.0, 10.0, 20.0], [15.0, 0.0, 47.0]])
    unmirrored = p.copy()
    unmirrored[:, 0] = 15 - p[:, 0]
    unmirrored[:, 2] = 47 - p[:, 2]
    expected = unmirrored.copy()
    expected[:, 1:] = unmirrored[:, 1:] @ (rotation * 1.2).T + [40.0, 35.0]
    expected += [5, -3, 7]
    assert np.allclose(frame.to_volume(p), expected)
    assert np.allclose(frame.to_patch(frame.to_volume(p)), p)
    physical = frame.physical(SPACING)
    assert np.allclose(physical, np.diag(SPACING) @ frame.jacobian @ np.diag(1 / np.array(SPACING)))


def _write_case(folder: Path, name: str, segmentation: np.ndarray, geometry) -> sc.CaseTargets:
    targets = sc.compute_case_targets(segmentation, SPACING, [2], geometry)
    sc.save_case_targets(folder / f"{name}.npz", targets)
    return targets


def _builder(folder, patch=(32, 128, 128), **changes):
    settings = dict(
        spacing=SPACING,
        rays=96,
        patch_size=patch,
        cell_stride=(2, 4, 4),
        ray_samples=32,
        max_gt_instances=4,
        core_fraction=0.3,
        sigma_min_mm=3.0,
        sigma_fraction=0.25,
        min_ray_mm=0.5,
        max_ray_mm=90.0,
    )
    settings.update(changes)
    return sc.StarTargetBuilder(folder, **settings)


def test_patch_targets_identity_frame(tmp_path, geometry):
    shape = (48, 200, 200)
    segmentation = (_ellipsoid(shape, (24, 100, 100), (10, 10, 10)) * 2).astype(np.uint8)
    table = _write_case(tmp_path, "a", segmentation, geometry)
    builder = _builder(tmp_path)
    # Crop at (8, 36, 36): the lesion centre lands at patch voxel (16, 64, 64).
    frame = sc.compose_patch_frame([8, 36, 36], [])
    out = builder.build("a", frame, np.random.default_rng(0))
    centre = table.centres[0] - [8, 36, 36]
    assert out["centre_valid"].tolist() == [True, False, False, False]
    assert np.allclose(out["centres"][0], centre)
    peak = np.floor((centre + 0.5) / (2, 4, 4)).astype(int)
    assert out["heatmap"][0][tuple(peak)] == 1.0
    assert (out["heatmap"] == 1.0).sum() == 1 and out["heatmap"].max() == 1.0
    # The first sample is the centre: its targets are the precomputed centre rays.
    assert np.allclose(sc.voxel_to_cell(centre[None], (2, 4, 4)), out["ray_positions"][0])
    assert np.allclose(np.exp(out["ray_targets"][0]), table.rays_mm[0], atol=0.05)
    assert out["ray_mask"][0].all()
    used = out["ray_mask"].any(1).sum()
    assert 2 <= used <= 1 + 32
    # Every core sample lies inside the lesion and has positive, finite targets.
    positions = out["ray_positions"][1:used]
    voxels = positions * (2, 4, 4) + (np.array([2, 4, 4]) - 1) / 2 + [8, 36, 36]
    assert segmentation[tuple(np.rint(voxels).astype(int).T)].all()


def test_patch_targets_are_full_volume_not_patch_truncated(tmp_path, geometry):
    shape = (48, 200, 200)
    segmentation = (_ellipsoid(shape, (24, 100, 100), (15, 15, 15)) * 2).astype(np.uint8)
    table = _write_case(tmp_path, "b", segmentation, geometry)
    builder = _builder(tmp_path)
    # The patch ends 8 voxels (6.5 mm) past the centre along x.
    frame = sc.compose_patch_frame([8, 36, 108 - 128], [])
    out = builder.build("b", frame, np.random.default_rng(0))
    assert out["centre_valid"][0]
    targets = np.exp(out["ray_targets"][0])
    plus_x = geometry.directions[:, 2] > 0.9
    assert plus_x.any()
    # Rays toward the cut keep their full-volume length (about 15 mm, not 6.5 mm).
    assert (targets[plus_x] > 13).all()
    assert np.allclose(targets, table.rays_mm[0], atol=0.05)
    # A lesion whose centre is outside the patch: Gaussian tail only, no positive.
    frame = sc.compose_patch_frame([8, 36, 104], [])
    out = builder.build("b", frame, np.random.default_rng(0))
    assert not out["centre_valid"].any()
    assert 0 < out["heatmap"].max() < 1
    assert out["ray_mask"].any()  # core cells inside the patch are still supervised


@pytest.mark.parametrize("kind", ["scale", "rotate", "mirror"])
def test_patch_targets_follow_the_augmentation_frame(tmp_path, geometry, kind):
    shape = (48, 220, 220)
    axes = (12.0, 16.0, 8.0)
    segmentation = (_ellipsoid(shape, (24, 110, 110), axes) * 2).astype(np.uint8)
    table = _write_case(tmp_path, "c", segmentation, geometry)
    builder = _builder(tmp_path)
    patch_centre = np.array([16.0, 64.0, 64.0])
    if kind == "scale":
        matrix = np.diag([1.0, 1.25, 1.25])  # in-plane zoom out (nnU-Net scaling 1.25)
        expected_axes = (12.0, 16.0 / 1.25, 8.0 / 1.25)
    elif kind == "rotate":
        matrix = np.array([[1.0, 0, 0], [0, 0, -1.0], [0, 1.0, 0]])  # 90 degrees in-plane
        expected_axes = (12.0, 8.0, 16.0)
    else:
        matrix = np.diag([-1.0, 1.0, -1.0])
        expected_axes = axes
    offset = table.centres[0] - matrix @ patch_centre
    frame = sc.PatchFrame(matrix, offset)
    out = builder.build("c", frame, np.random.default_rng(0))
    assert np.allclose(out["centres"][0], patch_centre)
    got = np.exp(out["ray_targets"][0])
    expected = _ellipsoid_radius(geometry.directions, expected_axes)
    assert np.median(np.abs(got - expected)) < 0.6
    assert np.abs(got - expected).max() < 2.0


def test_patch_targets_for_several_lesions(tmp_path, geometry):
    shape = (48, 200, 200)
    segmentation = np.zeros(shape, np.uint8)
    for centre, radius in (((20, 80, 80), 7.0), ((28, 120, 110), 10.0), ((24, 60, 130), 5.0)):
        segmentation[_ellipsoid(shape, centre, (radius,) * 3)] = 2
    table = _write_case(tmp_path, "d", segmentation, geometry)
    builder = _builder(tmp_path, ray_samples=30)
    out = builder.build("d", sc.compose_patch_frame([8, 36, 36], []), np.random.default_rng(3))
    assert out["centre_valid"].sum() == 3
    assert (out["heatmap"] == 1.0).sum() == 3
    # Largest first; core samples come from every component.
    volumes = sorted(table.volume_mm3, reverse=True)
    assert volumes[0] > volumes[1] > volumes[2]
    positions = out["ray_positions"][3 : out["ray_mask"].any(1).sum()]
    voxels = positions * (2, 4, 4) + (np.array([2, 4, 4]) - 1) / 2 + [8, 36, 36]
    full = np.zeros(shape, np.uint16)
    window = tuple(
        slice(a, a + n) for a, n in zip(table.crop_origin, table.instances.shape, strict=True)
    )
    full[window] = table.instances
    assert set(full[tuple(np.rint(voxels).astype(int).T)].tolist()) == {1, 2, 3}
    batch = sc.collate_star_targets([out, out])
    assert batch["heatmap"].shape == (2, 1, 16, 32, 32)
    assert batch["ray_targets"].shape == (2, 30 + 4, 96)
    empty = np.zeros(shape, np.uint8)
    _write_case(tmp_path, "e", empty, geometry)
    nothing = builder.build("e", sc.compose_patch_frame([0, 0, 0], []), np.random.default_rng(0))
    assert not nothing["ray_mask"].any() and nothing["heatmap"].max() == 0


# ---------------------------------------------------------------------------
# Rendering, proposals and losses
# ---------------------------------------------------------------------------


def _render(renderer, radii, centres, scores=None, tau=1.5, transforms=None, shape=(24, 96, 96)):
    radii = torch.as_tensor(radii)
    if radii.ndim == 1:
        radii = radii[None]
    centres = torch.as_tensor(centres, dtype=radii.dtype).reshape(-1, 3)
    scores = torch.ones(len(centres), dtype=radii.dtype) if scores is None else scores
    return renderer.render(
        shape,
        centres,
        radii,
        torch.as_tensor(scores, dtype=radii.dtype),
        torch.as_tensor(tau, dtype=radii.dtype),
        margin_mm=5.0,
        prior_scale=6.0,
        transforms=transforms,
    )


def test_soft_star_matches_hard_star_and_is_zero_outside_boxes(geometry):
    renderer = sc.StarRenderer(96, SPACING, (256, 512))
    rng = np.random.default_rng(0)
    radii = 8 + rng.uniform(-1.5, 1.5, 96)
    centre = np.array([12.0, 48.0, 48.0])
    prior, mask = _render(renderer, torch.tensor(radii), centre)
    hard = sc.render_star_mask((24, 96, 96), SPACING, centre, radii, geometry)
    soft = prior[0].numpy() > 0
    assert (soft != hard).mean() < 1e-3
    box = mask[0].numpy() > 0
    assert (prior[0].numpy()[~box] == 0).all()
    assert (prior[0].numpy()[box & ~hard] <= 0).all() and (prior[0].numpy()[hard] >= 0).all()
    assert prior.abs().max() <= 6.0
    # The box spans the longest ray plus the 5 mm margin along every axis.
    extent = np.argwhere(box)
    reach = (radii.max() + 5) / np.asarray(SPACING)
    assert np.all(extent.min(0) >= np.floor(centre - reach) - 1)
    assert np.all(extent.max(0) <= np.ceil(centre + reach) + 1)
    # Score scales the magnitude only; score 0 renders nothing inside the box either.
    half, _ = _render(renderer, torch.tensor(radii), centre, scores=[0.5])
    assert torch.allclose(half, prior * 0.5)
    none, box_none = _render(renderer, torch.tensor(radii), centre, scores=[0.0])
    assert none.abs().max() == 0 and box_none.sum() == box.sum()
    empty, empty_box = _render(renderer, torch.zeros((0, 96)), np.zeros((0, 3)))
    assert empty.abs().max() == 0 and empty_box.max() == 0


def test_union_of_several_instances_is_their_maximum():
    renderer = sc.StarRenderer(96, SPACING, (256, 512))
    radii = torch.full((2, 96), 6.0)
    centres = np.array([[8.0, 30.0, 30.0], [16.0, 60.0, 64.0]])
    both, both_box = _render(renderer, radii, centres, scores=[1.0, 0.7])
    first, first_box = _render(renderer, radii[:1], centres[:1], scores=[1.0])
    second, second_box = _render(renderer, radii[1:], centres[1:], scores=[0.7])
    expected = torch.where(
        (first_box > 0) & (second_box > 0),
        torch.maximum(first, second),
        first + second,
    )
    assert torch.allclose(both, expected)
    assert torch.equal(both_box, torch.maximum(first_box, second_box))


def test_mirrored_instance_renders_the_mirrored_star():
    renderer = sc.StarRenderer(96, SPACING, (256, 512))
    rng = np.random.default_rng(2)
    radii = torch.tensor(7 + rng.uniform(-2, 2, 96))
    shape = (24, 96, 96)
    centre = np.array([10.3, 40.6, 55.2])
    prior, _ = _render(renderer, radii, centre, shape=shape)
    flipped_centre = centre.copy()
    flipped_centre[2] = shape[2] - 1 - centre[2]
    transform = torch.diag(torch.tensor([1.0, 1.0, -1.0], dtype=torch.float64))[None]
    mirrored, _ = _render(renderer, radii, flipped_centre, transforms=transform, shape=shape)
    assert torch.allclose(mirrored, torch.flip(prior, (3,)), atol=1e-9)


def test_rendering_gradients_are_correct():
    renderer = sc.StarRenderer(96, SPACING, (256, 512))
    rng = np.random.default_rng(4)
    radii = torch.tensor(4 + rng.uniform(-0.5, 0.5, 96), requires_grad=True)
    tau = torch.tensor(1.5, dtype=torch.float64, requires_grad=True)
    centre = torch.tensor([[4.2, 12.7, 13.1]], dtype=torch.float64)
    weight = torch.tensor(rng.normal(size=(1, 10, 32, 32)))

    def objective(r, t):
        prior, _ = renderer.render(
            (10, 32, 32),
            centre,
            r[None],
            torch.ones(1, dtype=torch.float64),
            t,
            margin_mm=5.0,
            prior_scale=6.0,
        )
        return (prior * weight).sum()

    # The box depends on max(r) only through a detached integer, so fix it.
    assert torch.autograd.gradcheck(objective, (radii, tau), eps=1e-6, atol=1e-5)
    objective(radii, tau).backward()
    assert radii.grad is not None and (radii.grad != 0).sum() > 80
    assert tau.grad is not None and tau.grad != 0


def test_sample_cells_and_peak_detection():
    maps = torch.arange(4 * 5 * 6, dtype=torch.float32).reshape(1, 1, 4, 5, 6)
    positions = torch.tensor([[[0.0, 0.0, 0.0], [3.0, 4.0, 5.0], [1.5, 2.0, 2.5]]])
    sampled = sc.sample_cells(maps, positions)[0, :, 0]
    assert torch.allclose(sampled, torch.tensor([0.0, 119.0, 1.5 * 30 + 2 * 6 + 2.5]))
    heat = torch.full((1, 1, 8, 16, 16), -6.0)
    heat[0, 0, 2, 4, 4] = 3.0
    heat[0, 0, 2, 4, 5] = 3.0 - 1e-3  # a plateau neighbour shifts the sub-cell centre
    heat[0, 0, 6, 12, 10] = 1.0
    heat[0, 0, 6, 12, 11] = -1.0  # below threshold but not a peak
    cells, scores, valid = sc.detect_peaks(heat, 0.15, 4)
    assert valid.tolist() == [[True, True, False, False]]
    assert torch.allclose(cells[0, 0], torch.tensor([2.0, 4.0, 4.5]), atol=0.03)
    assert torch.allclose(cells[0, 1, :2], torch.tensor([6.0, 12.0]))
    assert 10.0 < float(cells[0, 1, 2]) < 10.3
    assert scores[0, 0] == pytest.approx(torch.sigmoid(torch.tensor(3.0)).item())
    many, _, valid_many = sc.detect_peaks(torch.zeros(1, 1, 1, 1, 2) + 5, 0.15, 6)
    assert many.shape == (1, 6, 3) and valid_many.sum() == 2


def test_focal_and_ray_losses():
    target = torch.zeros(1, 1, 4, 4, 4)
    target[0, 0, 1, 1, 1] = 1.0
    target[0, 0, 1, 1, 2] = 0.6
    good = torch.where(target >= 1, torch.tensor(8.0), torch.tensor(-8.0))
    bad = -good
    assert sc.centre_focal_loss(good, target) < 1e-3 < sc.centre_focal_loss(bad, target)
    flat = torch.full((1, 1, 28, 80, 64), math.log(0.01 / 0.99))
    empty = sc.centre_focal_loss(flat, torch.zeros_like(flat))
    assert empty < 0.2  # the 0.01 prior keeps an empty Task07 patch cheap (about 0.14)
    log_map = torch.zeros(1, 3, 4, 4, 4)
    log_map[:, 1] = 1.0
    positions = torch.tensor([[[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]]])
    targets = torch.tensor([[[0.0, 1.0, 0.5], [9.0, 9.0, 9.0]]])
    mask = torch.tensor([[[True, True, True], [False, False, False]]])
    assert sc.ray_l1_loss(log_map, positions, targets, mask) == pytest.approx(0.5 / 3)


def _completion(**changes):
    settings = dict(
        spacing=SPACING,
        stride=(2, 4, 4),
        rays=96,
        fusion_channels=[1, 2],
        fusion="gated",
        max_instances=4,
        centre_threshold=0.15,
        box_margin_mm=5.0,
        min_ray_mm=0.5,
        max_ray_mm=90.0,
        tau_init_mm=1.5,
        tau_min_mm=0.5,
        tau_max_mm=5.0,
        gate_bias=-2.0,
        prior_scale=6.0,
        centre_hidden=8,
        ray_hidden=8,
        gate_hidden=4,
        ray_init_mm=10.0,
        centre_prior=0.01,
        lut_shape=(256, 512),
    )
    settings.update(changes)
    torch.manual_seed(0)
    return sc.StarCompletion(16, 8, 3, **settings)


def test_completion_is_identity_at_initialisation_and_has_the_planned_state():
    module = _completion()
    level = torch.randn(2, 16, 8, 16, 16)
    full = torch.randn(2, 8, 16, 64, 64)
    logits = torch.randn(2, 3, 16, 64, 64)
    instances = sc.StarInstances(
        centres=torch.tensor([[[8.0, 30.0, 30.0]], [[4.0, 10.0, 50.0]]]),
        valid=torch.tensor([[True], [False]]),
    )
    fused, aux = module(level, full, logits, instances)
    assert torch.equal(fused, logits)
    assert aux["heat_logits"].shape == (2, 1, 8, 16, 16)
    assert aux["log_radii"].shape == (2, 96, 8, 16, 16)
    assert torch.allclose(aux["gate"], torch.sigmoid(torch.tensor(-2.0)))
    assert module.tau().item() == pytest.approx(1.5)
    assert torch.allclose(torch.sigmoid(aux["heat_logits"]), torch.tensor(0.01))
    assert torch.isfinite(aux["log_radii"]).all()
    assert aux["prior"][1].abs().max() == 0 and aux["prior"][0].abs().max() > 0
    # No proposals from the flat initial heatmap.
    _, proposed = module(level, full, logits)
    assert not proposed["instances"].valid.any()


def test_fusion_gradients_and_aux_only_mode():
    module = _completion()
    with torch.no_grad():
        module.fusion_weight.fill_(0.5)
    level = torch.randn(1, 16, 8, 16, 16)
    full = torch.randn(1, 8, 16, 64, 64)
    logits = torch.randn(1, 3, 16, 64, 64, requires_grad=True)
    instances = sc.StarInstances(
        centres=torch.tensor([[[8.0, 30.0, 30.0], [8.0, 40.0, 50.0]]]),
        valid=torch.tensor([[True, True]]),
    )
    fused, aux = module(level, full, logits, instances)
    assert torch.equal(fused[:, 0], logits[:, 0])  # background is not fused
    changed = (fused - logits).abs().sum((0, 2, 3, 4))
    assert changed[1] > 0 and changed[2] > 0
    outside = aux["prior"] == 0
    assert torch.equal(
        fused[:, 1:][outside.expand(-1, 2, -1, -1, -1)],
        logits[:, 1:][outside.expand(-1, 2, -1, -1, -1)],
    )
    loss = fused[:, 2].mean() + sc.centre_focal_loss(
        aux["heat_logits"], torch.zeros(1, 1, 8, 16, 16)
    )
    loss.backward()
    for name in ("fusion_weight", "tau_logit"):
        assert getattr(module, name).grad is not None and getattr(module, name).grad.abs().sum() > 0
    for head in (module.ray_head, module.gate, module.centre_head):
        assert head[-1].weight.grad is not None and head[-1].weight.grad.abs().sum() > 0
    aux_only = _completion(fusion="aux_only")
    with torch.no_grad():
        aux_only.fusion_weight.fill_(1.0)
    unchanged, extras = aux_only(level, full, logits.detach(), instances)
    assert torch.equal(unchanged, logits.detach()) and "prior" not in extras


# ---------------------------------------------------------------------------
# Case-level NMS
# ---------------------------------------------------------------------------


def test_case_level_nms_merges_tile_duplicates(geometry):
    radii = np.log(np.full(96, 8.0))
    detections = [
        sc.CaseDetection(np.array([20.0, 100.0, 100.0]), radii, 0.9, 0.3),  # tile edge
        sc.CaseDetection(np.array([20.5, 101.0, 99.0]), radii, 0.8, 1.0),  # tile centre
        sc.CaseDetection(np.array([21.0, 104.0, 100.0]), radii, 0.7, 0.9),  # inside the star
        sc.CaseDetection(np.array([20.0, 160.0, 100.0]), radii, 0.6, 1.0),  # another lesion
        sc.CaseDetection(np.array([30.0, 30.0, 30.0]), radii, 0.1, 1.0),  # below threshold
    ]
    kept = sc.merge_tile_detections(
        detections,
        geometry,
        SPACING,
        threshold=0.15,
        nms_radius_mm=5.0,
        max_instances=32,
        min_ray_mm=0.5,
        max_ray_mm=90.0,
    )
    assert [d.score for d in kept] == [0.8, 0.6]
    capped = sc.merge_tile_detections(
        detections,
        geometry,
        SPACING,
        threshold=0.15,
        nms_radius_mm=5.0,
        max_instances=1,
        min_ray_mm=0.5,
        max_ray_mm=90.0,
    )
    assert len(capped) == 1


# ---------------------------------------------------------------------------
# Offline precompute script
# ---------------------------------------------------------------------------


def test_precompute_script_writes_hashed_targets_and_refuses_forbidden_cases(tmp_path, geometry):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import precompute_star_targets as script
    finally:
        sys.path.pop(0)
    data = tmp_path / "nnUNetPlans_3d_fullres"
    data.mkdir()
    shape = (24, 80, 80)
    for name, centres in (("case_a", [(12, 40, 40)]), ("case_b", [(8, 20, 20), (16, 60, 60)])):
        segmentation = np.zeros((1, *shape), np.int8)
        for centre in centres:
            segmentation[0][_ellipsoid(shape, centre, (6, 6, 6))] = 2
        np.save(data / f"{name}_seg.npy", segmentation)
    plans = tmp_path / "plans.json"
    plans.write_text(
        json.dumps(
            {
                "configurations": {
                    "3d_fullres": {"spacing": list(SPACING), "data_identifier": data.name}
                }
            }
        )
    )
    output = tmp_path / "starc_targets__plans__3d_fullres"
    common = ["--preprocessed", str(data), "--plans", str(plans), "--workers", "2"]
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"test": ["case_b"]}))
    with pytest.raises(SystemExit):
        script.main([*common, "--output", str(output), "--forbid-cases-from", str(split)])
    assert not output.exists()
    split.write_text(json.dumps({"test": ["pancreas_028"]}))
    assert script.main([*common, "--output", str(output), "--forbid-cases-from", str(split)]) == 0
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["cases"]["case_b"]["components"] == 2
    assert manifest["directions_sha256"] == geometry.digest()
    sc.verify_star_targets(
        output,
        cases=["case_a", "case_b"],
        spacing=SPACING,
        rays=96,
        lesion_labels=[2],
        segmentation_files={c: data / f"{c}_seg.npy" for c in ("case_a", "case_b")},
    )
    with pytest.raises(SystemExit):
        script.main([*common, "--output", str(output)])
    with pytest.raises(SystemExit):
        script.main([*common, "--output", str(data / "inside")])


def test_dataset_check_reads_voxel_labels_of_region_datasets():
    """Region dataset.json files list label sets; lesion labels stay voxel labels."""
    from segmentary.medical.nnunet_regions import region_dataset_json, validate_regions

    ontology = {"background": 0, "pancreas": 1, "mass": 2}
    regions, order = validate_regions(ontology, None, None)
    task07 = region_dataset_json(ontology, regions, order, {"channel_names": {"0": "CT"}})
    options = sc.validate_starc_options({"fusion_channels": [0, 1]})
    assert sc.check_starc_dataset(options, task07) == {
        "lesion_labels": ["mass"],
        "fusion_channels": ["pancreas", "mass"],
    }
    with pytest.raises(ValueError, match="exceed"):
        sc.check_starc_dataset(sc.validate_starc_options(None), task07)
    kits = {
        "labels": {"background": 0, "kidney": [1, 2, 3], "masses": [2, 3], "tumor": [2]},
        "regions_class_order": [1, 3, 2],
    }
    masses = sc.validate_starc_options({"lesion_labels": [2, 3], "fusion_channels": [1, 2]})
    assert sc.check_starc_dataset(masses, kits) == {
        "lesion_labels": ["tumor", "label 3"],
        "fusion_channels": ["masses", "tumor"],
    }
    with pytest.raises(ValueError, match="lesion_labels"):
        sc.check_starc_dataset(sc.validate_starc_options({"lesion_labels": [4]}), kits)


def test_options_and_plan_transfer_are_torch_free_and_reexported():
    import ast

    from segmentary.medical import recipe_plan

    source = Path(recipe_plan.__file__).read_text()
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Import | ast.ImportFrom)
        for alias in node.names
    } | {
        node.module.split(".")[0]
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not imported & {"torch", "numpy", "scipy"}
    assert sc.validate_starc_options is recipe_plan.validate_starc_options
    assert sc.TARGET_SCHEMA == recipe_plan.STARC_TARGET_SCHEMA
    plan = {
        "configurations": {
            "3d_fullres": {
                "spacing": [2.5, 0.8125, 0.8125],
                "architecture": {
                    "network_class_name": recipe_plan.RESENC_CLASS,
                    "arch_kwargs": {"n_stages": 7},
                },
            }
        }
    }
    transferred, record = recipe_plan.transfer_plan(plan, "starc", {"max_instances": 4})
    assert transferred == sc.transfer_starc_plan(plan, {"max_instances": 4})[0]
    assert record["starc_options"]["max_instances"] == 4
    with pytest.raises(ValueError, match="only defined for hrc and starc"):
        recipe_plan.transfer_plan(plan, "plainconv", {})


def test_inference_settings_are_bound_complete():
    from segmentary.medical.recipe_plan import validate_starc_inference

    assert validate_starc_inference(None) == {
        "two_pass": True,
        "nms_radius_mm": 5.0,
        "max_case_instances": 32,
    }
    assert validate_starc_inference({"nms_radius_mm": 4})["nms_radius_mm"] == 4.0
    for bad, message in (
        ({"two_pass": 1}, "two_pass"),
        ({"nms_radius_mm": 0}, "nms_radius_mm"),
        ({"max_case_instances": 0}, "max_case_instances"),
        ({"mirroring": True}, "Unknown"),
    ):
        with pytest.raises(ValueError, match=message):
            validate_starc_inference(bad)


# ---------------------------------------------------------------------------
# Review fixes: memory, precision, verified reloads and the target method
# ---------------------------------------------------------------------------


def test_chunked_facet_lookup_equals_one_pass_and_keeps_gradients(monkeypatch):
    renderer = sc.StarRenderer(96, SPACING, (256, 512))
    rng = np.random.default_rng(3)
    radii = torch.tensor(10 + rng.uniform(-2, 2, 96), requires_grad=True)
    centre = np.array([12.0, 48.0, 48.0])
    whole, _ = _render(renderer, radii, centre)
    monkeypatch.setattr(sc, "RADIUS_CHUNK", 997)
    chunked, _ = _render(renderer, radii, centre)
    assert torch.equal(whole, chunked)
    chunked.sum().backward()
    assert radii.grad is not None and torch.isfinite(radii.grad).all()
    facet, weights = renderer.facet_weights(torch.zeros((0, 3)))
    assert facet.shape == (0,) and weights.shape == (0, 3)


def test_rendering_ignores_autocast():
    renderer = sc.StarRenderer(96, SPACING, (256, 512))
    radii = torch.full((96,), 9.3)
    centre = np.array([12.0, 48.0, 48.0])
    plain, _ = _render(renderer, radii, centre)
    with torch.autocast("cpu", dtype=torch.bfloat16):
        mixed, _ = _render(renderer, radii, centre)
    assert mixed.dtype == torch.float32 and torch.equal(plain, mixed)


def test_target_reloads_are_checked_against_the_verified_hash(tmp_path, geometry):
    shape = (32, 128, 128)
    segmentation = (_ellipsoid(shape, (16, 64, 64), (8, 8, 8)) * 2).astype(np.uint8)
    _write_case(tmp_path, "case", segmentation, geometry)
    digest = sc.sha256_file(tmp_path / "case.npz")
    with pytest.raises(ValueError, match="changed"):
        sc.load_case_targets(tmp_path / "case.npz", "0" * 64)
    builder = _builder(tmp_path, file_hashes={"case": digest}, cache_cases=1)
    assert builder.case("case").count == 1
    with pytest.raises(ValueError, match="not verified"):
        builder.case("other")
    # Evicted, then the file changes on disk: the reload is refused.
    builder._cache.clear()
    other = (_ellipsoid(shape, (16, 60, 60), (9, 9, 9)) * 2).astype(np.uint8)
    (tmp_path / "case.npz").unlink()
    _write_case(tmp_path, "case", other, geometry)
    with pytest.raises(ValueError, match="changed"):
        builder.case("case")


def test_targets_computed_with_another_method_are_refused(tmp_path, geometry):
    shape = (20, 60, 60)
    segmentation = (_ellipsoid(shape, (10, 30, 30), (8, 8, 8)) * 2).astype(np.uint8)
    digest = sc.save_case_targets(
        tmp_path / "case.npz", sc.compute_case_targets(segmentation, SPACING, [2], geometry)
    )
    manifest = {
        "schema": sc.TARGET_SCHEMA,
        **copy.deepcopy(recipe_plan.STARC_TARGET_METHOD),
        "rays": 96,
        "directions_sha256": geometry.digest(),
        "spacing": list(SPACING),
        "lesion_labels": [2],
        "cases": {"case": {"sha256": digest}},
    }
    manifest["march"]["bisections"] = 4
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="target method"):
        sc.verify_star_targets(
            tmp_path, cases=["case"], spacing=SPACING, rays=96, lesion_labels=[2]
        )


def _precompute_script():
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import precompute_star_targets as script
    finally:
        sys.path.pop(0)
    return script


@pytest.mark.parametrize("place", ["preprocessed", "workspace", "results"])
def test_precompute_refuses_outputs_inside_workspaces_and_nnunet_folders(tmp_path, place):
    script = _precompute_script()
    root = tmp_path / "reference"
    data = root / "nnUNet_preprocessed" / "Dataset707_Pancreas" / "nnUNetPlans_3d_fullres"
    data.mkdir(parents=True)
    np.save(data / "case_a_seg.npy", np.zeros((1, 8, 16, 16), np.int8))
    plans = tmp_path / "plans.json"
    plans.write_text(
        json.dumps(
            {
                "configurations": {
                    "3d_fullres": {"spacing": list(SPACING), "data_identifier": data.name}
                }
            }
        )
    )
    (root / "binding.json").write_text("{}")
    output = {
        "preprocessed": data.parent / "starc_targets__plans__3d_fullres",
        "workspace": root / "starc-targets",
        "results": tmp_path / "other" / "nnUNet_results" / "targets",
    }[place]
    with pytest.raises(SystemExit):
        script.main(["--preprocessed", str(data), "--plans", str(plans), "--output", str(output)])
    assert not output.exists()
    assert script.workspace_conflict(tmp_path / "outside" / "targets") is None


def test_cpu_smoke_refuses_visible_gpus(tmp_path, monkeypatch):
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import starc_cpu_smoke as smoke
    finally:
        sys.path.pop(0)
    arguments = [
        "--plan",
        "p.json",
        "--workdir",
        str(tmp_path / "w"),
        "--output",
        str(tmp_path / "o"),
    ]
    for value in (None, "2"):
        if value is None:
            monkeypatch.delenv("CUDA_VISIBLE_DEVICES", raising=False)
        else:
            monkeypatch.setenv("CUDA_VISIBLE_DEVICES", value)
        with pytest.raises(SystemExit):
            smoke.main(arguments)
    assert not (tmp_path / "w").exists()
