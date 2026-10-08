"""Region-based nnU-Net labels decode to the native label map, and reuse the reference arrays."""

from __future__ import annotations

import itertools
import json
import pickle
import shutil
from pathlib import Path

import numpy as np
import pytest

from segmentary.medical import nnunet_regions as r

ONTOLOGY = {"background": 0, "pancreas": 1, "mass": 2}
KITS = {"background": 0, "kidney": 1, "tumor": 2, "cyst": 3}


def test_task07_regions_are_the_default_and_decode_losslessly():
    regions, order = r.validate_regions(ONTOLOGY, None, None)
    assert regions == [["pancreas", [1, 2]], ["mass", [2]]] and order == [1, 2]
    # A mapping is accepted in its (insertion) order and returned as ordered pairs.
    assert r.validate_regions(ONTOLOGY, {"pancreas": [2, 1], "mass": [2]}, [1, 2])[0] == regions
    labels = np.random.default_rng(0).integers(0, 3, size=(6, 7, 8))
    assert np.array_equal(r.decode_regions(r.encode_regions(labels, regions), order), labels)


def test_general_regions_follow_the_nnunet_decode_rule():
    regions, order = r.validate_regions(
        KITS, {"kidney_and_masses": [1, 2, 3], "masses": [2, 3], "tumor": [2]}, [1, 3, 2]
    )
    labels = np.arange(4).repeat(5).reshape(4, 5)
    assert np.array_equal(r.decode_regions(r.encode_regions(labels, regions), order), labels)


@pytest.mark.parametrize(
    "regions, order, message",
    [
        ({"pancreas": [1, 2], "mass": [2]}, [2, 1], "reproduce label 1"),
        ({"pancreas": [1], "mass": [2]}, [1, 2], None),  # disjoint regions are lossless too
        ({"pancreas": [1, 2]}, [1], "reproduce label 2"),
        ({"pancreas": [1, 2], "mass": [2]}, [1], "one foreground label value"),
        ({"pancreas": [1, 2], "mass": [3]}, [1, 2], "outside the ontology"),
        ({"pancreas": [1, 2], "other": [1, 2]}, [1, 2], "distinct"),
        ({"background": [1], "mass": [2]}, [1, 2], "reserved"),
        ({"pancreas": [], "mass": [2]}, [1, 2], "nonempty"),
        ({"pancreas": [1, True], "mass": [2]}, [1, 2], "distinct foreground"),
        ({}, [], "nonempty ordered list"),
        ([["pancreas", [1, 2]], ["pancreas", [2]]], [1, 2], "names must be distinct"),
        ([["pancreas", [1, 2]], ["mass"]], [1, 2], "pairs"),
        ([["pancreas", 1], ["mass", [2]]], [1, 2], "list of labels"),
        # Head order matters: mass first with order [1, 2] would label mass as pancreas.
        ([["mass", [2]], ["pancreas", [1, 2]]], [1, 2], "reproduce label 1"),
    ],
)
def test_lossy_or_malformed_region_recipes_are_refused(regions, order, message):
    if message is None:
        r.validate_regions(ONTOLOGY, regions, order)
        return
    with pytest.raises(ValueError, match=message):
        r.validate_regions(ONTOLOGY, regions, order)


def test_decode_rule_matches_an_exhaustive_voxel_enumeration():
    _, order = r.validate_regions(ONTOLOGY, None, None)
    for membership in itertools.product([False, True], repeat=2):
        probabilities = np.asarray(membership, dtype=float).reshape(2, 1) * 0.9
        expected = r.decode_label(membership, order)
        assert r.decode_regions(probabilities, order)[0] == expected


def test_region_order_survives_sorted_json_records_and_is_checked():
    regions, order = r.validate_regions(ONTOLOGY, None, None)
    reloaded = json.loads(json.dumps({"label_regions": regions}, sort_keys=True))
    assert reloaded["label_regions"] == regions
    dataset = r.region_dataset_json(ONTOLOGY, regions, order, {"labels": ONTOLOGY})
    assert list(dataset["labels"]) == ["background", "pancreas", "mass"]
    resorted = json.loads(json.dumps(dataset, sort_keys=True))
    assert resorted == dataset  # dict equality ignores the order nnU-Net depends on
    assert r.same_dataset_json(dataset, dataset)
    assert not r.same_dataset_json(resorted, dataset)
    # Label-mode heads are sorted label values: key order does not matter there.
    labels = {"labels": {"background": 0, "pancreas": 1, "mass": 2}}
    assert r.same_dataset_json(json.loads(json.dumps(labels, sort_keys=True)), labels)


def test_region_dataset_json_keeps_everything_but_labels():
    base = {"channel_names": {"0": "CT"}, "labels": ONTOLOGY, "numTraining": 3}
    result = r.region_dataset_json(ONTOLOGY, {"pancreas": [1, 2], "mass": [2]}, [1, 2], base)
    assert result == {
        "channel_names": {"0": "CT"},
        "labels": {"background": 0, "pancreas": [1, 2], "mass": [2]},
        "numTraining": 3,
        "regions_class_order": [1, 2],
    }
    assert base["labels"] == ONTOLOGY


def test_nnunet_label_manager_decodes_exactly_like_the_declared_rule():
    label_handling = pytest.importorskip("nnunetv2.utilities.label_handling.label_handling")
    dataset = r.region_dataset_json(ONTOLOGY, r.TASK07_REGIONS, [1, 2], {"labels": ONTOLOGY})
    manager = label_handling.LabelManager(dataset["labels"], dataset["regions_class_order"])
    assert manager.has_regions
    assert [tuple(region) for region in manager.foreground_regions] == [(1, 2), (2,)]
    assert manager.num_segmentation_heads == 2
    probabilities = np.random.default_rng(1).random((2, 9, 10, 11)).astype(np.float32)
    assert np.array_equal(
        manager.convert_probabilities_to_segmentation(probabilities),
        r.decode_regions(probabilities, [1, 2]),
    )


def _plans() -> dict:
    resample = "resample_data_or_seg_to_shape"
    return {
        "dataset_name": "Dataset999_Regions",
        "plans_name": "nnUNetResEncUNetLPlans",
        "original_median_spacing_after_transp": [2.5, 0.8, 0.8],
        "original_median_shape_after_transp": [12, 24, 20],
        "image_reader_writer": "NibabelIO",
        "transpose_forward": [0, 1, 2],
        "transpose_backward": [0, 1, 2],
        "label_manager": "LabelManager",
        "experiment_planner_used": "nnUNetPlannerResEncL",
        "foreground_intensity_properties_per_channel": {
            "0": {
                "max": 300.0,
                "mean": 80.0,
                "median": 80.0,
                "min": -100.0,
                "percentile_00_5": -90.0,
                "percentile_99_5": 210.0,
                "std": 70.0,
            }
        },
        "configurations": {
            "3d_fullres": {
                "data_identifier": "nnUNetPlans_3d_fullres",
                "preprocessor_name": "DefaultPreprocessor",
                "batch_size": 2,
                "patch_size": [8, 16, 16],
                "median_image_size_in_voxels": [12, 24, 20],
                # Not the image spacing: preprocessing really resamples, as for Task07.
                "spacing": [2.0, 0.9, 0.9],
                "normalization_schemes": ["CTNormalization"],
                "use_mask_for_norm": [False],
                "resampling_fn_data": resample,
                "resampling_fn_seg": resample,
                "resampling_fn_probabilities": resample,
                "resampling_fn_data_kwargs": {
                    "is_seg": False,
                    "order": 3,
                    "order_z": 0,
                    "force_separate_z": None,
                },
                "resampling_fn_seg_kwargs": {
                    "is_seg": True,
                    "order": 1,
                    "order_z": 0,
                    "force_separate_z": None,
                },
                "resampling_fn_probabilities_kwargs": {
                    "is_seg": False,
                    "order": 1,
                    "order_z": 0,
                    "force_separate_z": None,
                },
                "batch_dice": False,
                "architecture": {
                    "network_class_name": "dynamic_network_architectures.architectures.unet.ResidualEncoderUNet",
                    "arch_kwargs": {},
                    "_kw_requires_import": [],
                },
            }
        },
    }


def _case(folder: Path) -> tuple[Path, Path]:
    import nibabel as nib

    rng = np.random.default_rng(7)
    shape = (20, 24, 12)  # x, y, z as NIfTI stores it
    image = np.zeros(shape, dtype=np.float32)
    image[2:-2, 3:-3, 1:-1] = rng.normal(60, 40, size=(16, 18, 10))
    label = np.zeros(shape, dtype=np.uint8)
    label[6:14, 8:16, 3:9] = 1
    label[8:12, 10:13, 4:7] = 2
    label[15, 18, 9] = 2  # an isolated mass voxel outside the gland
    affine = np.diag([0.8, 0.8, 2.5, 1.0])
    folder.mkdir(parents=True, exist_ok=True)
    paths = folder / "case_0000.nii.gz", folder / "case.nii.gz"
    for path, values in zip(paths, (image, label), strict=True):
        volume = nib.Nifti1Image(values, affine)
        volume.header.set_xyzt_units("mm")
        nib.save(volume, path)
    return paths


def _official_2_8_1() -> None:
    """Skip unless nnunetv2 is the released 2.8.1 layout (class_locations in each .pkl)."""
    import importlib.util

    pytest.importorskip("nnunetv2")
    if importlib.util.find_spec("nnunetv2.preprocessing.sampling_locations") is not None:
        pytest.skip("nnU-Net master keeps sampling locations in a store; regions bind 2.8.1")


def _equal(first, second) -> bool:
    if isinstance(first, dict):
        return (
            isinstance(second, dict)
            and first.keys() == second.keys()
            and all(_equal(first[key], second[key]) for key in first)
        )
    if isinstance(first, (list, tuple)):
        return (
            isinstance(second, (list, tuple))
            and len(first) == len(second)
            and all(_equal(a, b) for a, b in zip(first, second, strict=True))
        )
    return bool(np.array_equal(np.asarray(first), np.asarray(second)))


def _decoded(path: Path) -> np.ndarray:
    import blosc2

    return np.asarray(blosc2.open(urlpath=str(path), mode="r")[:])


def test_copied_arrays_plus_regenerated_locations_equal_a_full_region_preprocess(tmp_path):
    """Region preprocessing changes only class_locations; the copy path reproduces it exactly."""
    _official_2_8_1()
    from nnunetv2.preprocessing.preprocessors.default_preprocessor import DefaultPreprocessor
    from nnunetv2.utilities.plans_handling.plans_handler import PlansManager

    image, label = _case(tmp_path / "raw")
    manager = PlansManager(_plans())
    configuration = manager.get_configuration("3d_fullres")
    base = {"channel_names": {"0": "CT"}, "labels": ONTOLOGY, "file_ending": ".nii.gz"}
    region = r.region_dataset_json(ONTOLOGY, r.TASK07_REGIONS, [1, 2], base)
    outputs = {}
    for name, dataset in (("labels", base), ("regions", region)):
        folder = tmp_path / name
        folder.mkdir()
        DefaultPreprocessor().run_case_save(
            str(folder / "case"), [str(image)], str(label), manager, configuration, dataset
        )
        outputs[name] = folder
    for suffix in (".b2nd", "_seg.b2nd"):
        assert np.array_equal(
            _decoded(outputs["labels"] / f"case{suffix}"),
            _decoded(outputs["regions"] / f"case{suffix}"),
        )
    labels_props = pickle.loads((outputs["labels"] / "case.pkl").read_bytes())
    region_props = pickle.loads((outputs["regions"] / "case.pkl").read_bytes())
    assert set(labels_props["class_locations"]) == {1, 2}
    assert set(region_props["class_locations"]) == {(1, 2), (2,)}
    # The label-mode pickle is not a valid region-mode pickle.
    assert not r._same_locations(labels_props["class_locations"], region_props["class_locations"])

    copy = tmp_path / "copy"
    shutil.copytree(outputs["labels"], copy)
    report = r._regenerate_case((str(copy), "case", [1, 2], [(1, 2), (2,)]))
    assert report["region_keys"] == [[1, 2], [2]]
    regenerated = pickle.loads((copy / "case.pkl").read_bytes())
    assert r._same_locations(regenerated["class_locations"], region_props["class_locations"])
    rest = {k: v for k, v in regenerated.items() if k != "class_locations"}
    assert _equal(rest, {k: v for k, v in region_props.items() if k != "class_locations"})
    for suffix in (".b2nd", "_seg.b2nd"):
        assert (copy / f"case{suffix}").read_bytes() == (
            outputs["labels"] / f"case{suffix}"
        ).read_bytes()


def test_regeneration_refuses_a_copy_that_does_not_reproduce_the_reference(tmp_path):
    _official_2_8_1()
    from nnunetv2.preprocessing.preprocessors.default_preprocessor import DefaultPreprocessor
    from nnunetv2.utilities.plans_handling.plans_handler import PlansManager

    image, label = _case(tmp_path / "raw")
    manager = PlansManager(_plans())
    folder = tmp_path / "labels"
    folder.mkdir()
    dataset = {"channel_names": {"0": "CT"}, "labels": ONTOLOGY, "file_ending": ".nii.gz"}
    DefaultPreprocessor().run_case_save(
        str(folder / "case"),
        [str(image)],
        str(label),
        manager,
        manager.get_configuration("3d_fullres"),
        dataset,
    )
    properties = pickle.loads((folder / "case.pkl").read_bytes())
    properties["class_locations"][2] = properties["class_locations"][2][:-1]
    (folder / "case.pkl").write_bytes(pickle.dumps(properties))
    with pytest.raises(ValueError, match="does not reproduce"):
        r._regenerate_case((str(folder), "case", [1, 2], [(1, 2), (2,)]))
