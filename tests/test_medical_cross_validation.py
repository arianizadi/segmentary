"""Development CV keeps fold 0 identical to the frozen split and never touches test."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from segmentary.medical import backend as b
from segmentary.medical.cv_splits import (
    fold_splits,
    make_cv_splits,
    nnunet_splits,
    validate_cv_splits,
)
from segmentary.medical.data import atomic_write_json, fingerprint, load_manifest, make_splits
from segmentary.medical.geometry import MedicalDataError, sha256_file

SPACING = [0.75, 1.25, 3.0]


def _manifest(tmp_path: Path, labeled: int = 30, *, volumes: bool = True) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    cases = []
    for index in range(labeled + 2):
        case_id = f"case_{index:03d}"
        image = source / f"{case_id}.nii.gz"
        image.write_bytes(f"image {index}".encode())
        case = {
            "case_id": case_id,
            # Cases 0/1 and 2/3 are one patient each and must stay together.
            "patient_id": f"patient_{index // 2 if index < 4 else index}",
            "source": "fixture",
            "annotation_status": "labeled" if index < labeled else "unlabeled",
            "image": str(image),
            "image_sha256": sha256_file(image),
            "label": None,
            "label_sha256": None,
            "shape": [4, 5, 6],
            "spacing_mm": SPACING,
            "affine": np.diag([*SPACING, 1.0]).tolist(),
        }
        if index < labeled:
            label = source / f"{case_id}_label.nii.gz"
            label.write_bytes(f"label {index}".encode())
            case.update(label=str(label), label_sha256=sha256_file(label))
            if volumes:
                case["label_counts"] = {"0": 100, "1": 20, "2": 3 * index}
        cases.append(case)
    manifest = {
        "schema_version": 1,
        "dataset": "fixture",
        "ontology": {"background": 0, "pancreas": 1, "mass": 2},
        "audit": {"passed": True},
        "source_root": str(source),
        "grouping_status": "fixture",
        "cases": cases,
    }
    manifest["fingerprint"] = fingerprint(manifest)
    path = tmp_path / "manifest.json"
    atomic_write_json(path, manifest)
    return path


@pytest.fixture
def frozen(tmp_path):
    manifest = _manifest(tmp_path)
    splits = tmp_path / "frozen-splits.json"
    make_splits(manifest, splits, seed=3)
    return manifest, splits


def test_fold_zero_is_the_frozen_split_and_test_never_enters_a_fold(tmp_path, frozen):
    manifest, splits = frozen
    split = json.loads(splits.read_text())
    before = splits.read_bytes()
    cv = make_cv_splits(manifest, splits, tmp_path / "cv.json", seed=0)
    assert splits.read_bytes() == before
    assert cv["fold_count"] == 5 and len(cv["folds"]) == 5
    assert cv["folds"][0]["train"] == split["train"]
    assert cv["folds"][0]["val"] == split["val"]
    assert cv["base_splits_sha256"] == sha256_file(splits)
    assert cv["assignment"]["method"] == "mass_volume_stratified_blocks"
    development = split["train"] + split["val"]
    assert cv["development_cases"] == len(development)
    assert cv["held_out_test_cases"] == len(split["test"])
    seen: list[str] = []
    for item in cv["folds"]:
        assert not set(item["val"]) & set(split["test"])
        assert not set(item["train"]) & set(split["test"])
        assert item["train"] == [case for case in development if case not in item["val"]]
        seen += item["val"]
    assert sorted(seen) == sorted(development)
    for patient in (["case_000", "case_001"], ["case_002", "case_003"]):
        owners = {i for i, item in enumerate(cv["folds"]) if set(patient) & set(item["val"])}
        assert len(owners) == 1
        assert set(patient) <= set(cv["folds"][owners.pop()]["val"])
    sizes = [len(item["val"]) for item in cv["folds"][1:]]
    assert max(sizes) - min(sizes) <= 2
    assert nnunet_splits(cv)[0] == {"train": split["train"], "val": split["val"]}
    assert load_manifest(manifest)["fingerprint"] == cv["manifest_fingerprint"]
    repeated = make_cv_splits(manifest, splits, tmp_path / "repeat.json", seed=0)
    assert repeated == cv


def test_never_overwrites_the_frozen_split_or_an_existing_manifest(tmp_path, frozen):
    manifest, splits = frozen
    before = splits.read_bytes()
    with pytest.raises(FileExistsError):
        make_cv_splits(manifest, splits, splits)
    make_cv_splits(manifest, splits, tmp_path / "cv.json")
    with pytest.raises(FileExistsError):
        make_cv_splits(manifest, splits, tmp_path / "cv.json")
    assert splits.read_bytes() == before


def test_missing_volume_metadata_falls_back_to_a_seeded_shuffle(tmp_path):
    manifest = _manifest(tmp_path, volumes=False)
    splits = tmp_path / "splits.json"
    make_splits(manifest, splits, seed=3)
    cv = make_cv_splits(manifest, splits, tmp_path / "cv.json", seed=5)
    assert cv["assignment"]["method"] == "seeded_shuffle_blocks"
    assert cv["assignment"]["stratification_variable"] is None


@pytest.mark.parametrize("fault", ["fold0", "test", "overlap", "fingerprint", "split"])
def test_validator_rejects_tampered_folds(tmp_path, frozen, fault):
    manifest_path, splits = frozen
    manifest = load_manifest(manifest_path)
    split = json.loads(splits.read_text())
    cv = make_cv_splits(manifest_path, splits, tmp_path / "cv.json")
    if fault == "fold0":
        moved = cv["folds"][1]["val"][0]
        cv["folds"][0]["val"] = [*cv["folds"][0]["val"], moved]
        cv["folds"][1]["val"].remove(moved)
    elif fault == "test":
        cv["folds"][2]["val"].append(split["test"][0])
    elif fault == "overlap":
        cv["folds"][3]["val"].append(cv["folds"][4]["val"][0])
    elif fault == "split":
        split = {**split, "fingerprint": "different"}
    if fault != "fingerprint":
        cv["fingerprint"] = fingerprint(cv)
    else:
        cv["seed"] = 99
    with pytest.raises(MedicalDataError):
        validate_cv_splits(manifest, split, cv)


def test_fold_document_is_a_valid_standard_split(tmp_path, frozen):
    manifest_path, splits = frozen
    split = json.loads(splits.read_text())
    cv = make_cv_splits(manifest_path, splits, tmp_path / "cv.json")
    derived = fold_splits(split, cv, 3)
    assert derived["val"] == cv["folds"][3]["val"]
    assert derived["test"] == split["test"]
    assert derived["fingerprint"] == fingerprint(derived)
    with pytest.raises(MedicalDataError):
        fold_splits(split, cv, 5)


def _cv_config(tmp_path, cv_path, fold, name):
    return b.NNUNetConfig(
        str(tmp_path / name),
        gpu="2",
        fold=fold,
        cv_splits=str(cv_path),
        cv_splits_sha256=sha256_file(cv_path),
    )


def test_nnunet_fold_zero_under_cv_matches_the_frozen_split(tmp_path, frozen):
    manifest, splits = frozen
    split = json.loads(splits.read_text())
    cv_path = tmp_path / "cv.json"
    cv = make_cv_splits(manifest, splits, cv_path)
    plain = b.NNUNetConfig(str(tmp_path / "plain"), gpu="2")
    b.prepare_dataset(manifest, splits, plain)
    config = _cv_config(tmp_path, cv_path, 0, "cv-fold0")
    result = b.prepare_dataset(manifest, splits, config)
    folds = b._json(config.preprocessed / "splits_final.json")
    assert len(folds) == 5
    assert folds[0] == b._json(plain.preprocessed / "splits_final.json")[0]
    assert folds[0] == {"train": split["train"], "val": split["val"]}
    assert (result["train_cases"], result["val_cases"]) == (len(split["train"]), len(split["val"]))
    binding = b._binding(config)
    assert binding["cross_validation"]["fold"] == 0
    assert binding["development_cases"] == b._binding(plain)["development_cases"]
    assert b._fold_cases(config, binding, "train") == split["train"]
    assert b._fold_cases(config, binding, "val") == split["val"]
    assert b._fold_cases(config, binding, "test") == split["test"]
    assert config.fold_folder.name == "fold_0"
    assert cv["folds"][0]["val"] == b._fold_cases(plain, b._binding(plain), "val")


def test_nnunet_other_folds_use_the_cv_partition_and_bind_its_hash(tmp_path, frozen):
    manifest, splits = frozen
    split = json.loads(splits.read_text())
    cv_path = tmp_path / "cv.json"
    cv = make_cv_splits(manifest, splits, cv_path)
    config = _cv_config(tmp_path, cv_path, 2, "cv-fold2")
    b.prepare_dataset(manifest, splits, config)
    binding = b._binding(config)
    assert config.fold_folder.name == "fold_2"
    assert b._fold_cases(config, binding, "val") == cv["folds"][2]["val"]
    assert b._fold_cases(config, binding, "test") == split["test"]
    assert not set(b._fold_cases(config, binding, "train")) & set(split["test"])
    raw = config.root / "nnUNet_raw" / config.dataset / "imagesTr"
    assert len(list(raw.iterdir())) == len(split["train"]) + len(split["val"])
    cv_path.write_text(cv_path.read_text().replace('"seed": 0', '"seed": 1'))
    with pytest.raises(ValueError, match="Content hash changed"):
        b._binding(config)


@pytest.mark.parametrize(
    "kwargs, message",
    [
        ({"fold": 1}, "cv_splits for other folds"),
        ({"cv_splits": "/cv.json"}, "frozen SHA256"),
        ({"cv_splits_sha256": "0" * 64}, "requires cv_splits"),
        ({"cv_splits": "/cv.json", "cv_splits_sha256": "0" * 64, "fold": 20}, "folds are 0 to 19"),
        ({"cv_splits": "/cv.json", "cv_splits_sha256": "0" * 64, "fold": -1}, "folds are 0 to 19"),
    ],
)
def test_fold_configuration_is_explicit(tmp_path, kwargs, message):
    with pytest.raises(ValueError, match=message):
        b.NNUNetConfig(str(tmp_path), **kwargs)


def test_cli_evaluates_the_requested_fold_only(tmp_path, frozen, monkeypatch):
    from segmentary.medical import cli, evaluation

    manifest, splits = frozen
    cv_path = tmp_path / "cv.json"
    cv = make_cv_splits(manifest, splits, cv_path)
    seen = {}
    monkeypatch.setattr(
        evaluation, "evaluate_predictions", lambda *a, **k: seen.update(k) or {"ok": True}
    )
    common = ["evaluate", "--manifest", str(manifest), "--splits", str(splits)]
    common += ["--predictions", str(tmp_path), "--output", str(tmp_path / "out")]
    bound = [*common, "--cv-splits", str(cv_path), "--cv-splits-sha256", sha256_file(cv_path)]
    args = cli._parser().parse_args([*bound, "--fold", "4"])
    cli.dispatch(args)
    assert seen["case_ids"] == cv["folds"][4]["val"]
    assert seen["cohort"] == {
        "source": "development_cross_validation",
        "cv_splits_sha256": sha256_file(cv_path),
        "cv_fingerprint": cv["fingerprint"],
        "fold": 4,
        "partition": "val",
    }
    args = cli._parser().parse_args([*bound, "--fold", "1", "--partition", "test", "--final-test"])
    with pytest.raises(ValueError, match="never include the held-out test"):
        cli.dispatch(args)
    with pytest.raises(ValueError, match="together"):
        cli.dispatch(cli._parser().parse_args([*common, "--fold", "1"]))
    unhashed = [*common, "--cv-splits", str(cv_path), "--fold", "1"]
    with pytest.raises(ValueError, match="together"):
        cli.dispatch(cli._parser().parse_args(unhashed))
    wrong = [*common, "--cv-splits", str(cv_path), "--cv-splits-sha256", "0" * 64, "--fold", "1"]
    with pytest.raises(ValueError, match="SHA256 differs"):
        cli.dispatch(cli._parser().parse_args(wrong))
    seen.clear()
    cli.dispatch(cli._parser().parse_args(common))
    assert seen["cohort"] is None


def test_cv_output_is_identical_across_processes_and_hash_seeds(tmp_path, frozen):
    import os
    import subprocess
    import sys

    manifest, splits = frozen
    source = str(Path(b.__file__).resolve().parents[2])
    digests = set()
    for hash_seed in ("0", "777", "random"):
        output = tmp_path / f"cv-{hash_seed}.json"
        code = (
            "import sys; from segmentary.medical.cv_splits import make_cv_splits; "
            "make_cv_splits(sys.argv[1], sys.argv[2], sys.argv[3])"
        )
        env = os.environ | {"PYTHONHASHSEED": hash_seed, "PYTHONPATH": source}
        subprocess.run(
            [sys.executable, "-c", code, str(manifest), str(splits), str(output)],
            env=env,
            check=True,
        )
        digests.add(sha256_file(output))
    assert len(digests) == 1


def test_fold_bound_comes_from_the_manifest_and_is_checked_before_any_write(tmp_path, frozen):
    manifest, splits = frozen
    three = tmp_path / "cv3.json"
    make_cv_splits(manifest, splits, three, folds=3)
    config = _cv_config(tmp_path, three, 3, "cv3-fold3")
    with pytest.raises(ValueError, match="outside the 3-fold manifest"):
        b.prepare_dataset(manifest, splits, config)
    assert not config.root.exists() or not any(config.root.iterdir())
    ten = tmp_path / "cv10.json"
    make_cv_splits(manifest, splits, ten, folds=10)
    config = _cv_config(tmp_path, ten, 7, "cv10-fold7")
    b.prepare_dataset(manifest, splits, config)
    assert len(b._json(config.preprocessed / "splits_final.json")) == 10
    assert config.fold_folder.name == "fold_7"


def test_trainer_split_guard_rejects_any_split_but_the_bound_fold():
    class Trainer:
        def __init__(self, split):
            self.split = split

        def do_split(self):
            return self.split

    expected = (["a", "b"], ["c"])
    good = Trainer((["a", "b"], ["c"]))
    b._guard_trainer_split(good, 2, expected)
    assert good.do_split() == (["a", "b"], ["c"])
    for wrong in ((["a", "c"], ["b"]), (["b", "a"], ["c"]), (["a", "b"], ["c", "d"])):
        trainer = Trainer(wrong)
        b._guard_trainer_split(trainer, 2, expected)
        with pytest.raises(ValueError, match="differs from bound fold 2"):
            trainer.do_split()
