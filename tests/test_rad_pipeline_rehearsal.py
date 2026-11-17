"""Rehearse real inference through training images while the held-out files stay closed."""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from scripts import evaluate_rad_test as evaluate
from scripts.rad_test_contract import evaluation_mode


def test_rehearsal_requires_explicit_train_only_authorization():
    request = {
        "schema_version": 1,
        "rehearsal": True,
        "rehearsal_authorized": True,
        "test_evaluation_authorized": False,
        "evaluation_split": "train",
        "image_keys": ["training/image"],
    }
    assert evaluation_mode(request) == ("train", False)
    for field, value in (
        ("schema_version", 2),
        ("rehearsal_authorized", False),
        ("test_evaluation_authorized", True),
        ("evaluation_split", "test"),
        ("image_keys", ["../image"]),
    ):
        with pytest.raises(ValueError, match="train-only rehearsal"):
            evaluation_mode({**request, field: value})


def test_real_train_loading_never_opens_held_out_files(tmp_path, monkeypatch):
    names = [f"c{index}" for index in range(21)]
    names[13] = "mud-pumping"
    target = np.arange(21, dtype=np.uint8).reshape(3, 7)
    rgb_path = tmp_path / "images/train/training/a.png"
    mask_path = tmp_path / "masks/train/training/a.png"
    rgb_path.parent.mkdir(parents=True)
    mask_path.parent.mkdir(parents=True)
    Image.new("RGB", (7, 3)).save(rgb_path)
    Image.fromarray(target).save(mask_path)
    sample = {
        "key": "training/a",
        "split": "train",
        "group": "training",
        "width": 7,
        "height": 3,
        "image_extension": ".png",
        "image_sha256": evaluate.digest(rgb_path),
        "mask_sha256": hashlib.sha256(target.tobytes()).hexdigest(),
        "class_pixels": {str(index): 1 for index in range(21)},
    }
    held_out = {
        **sample,
        "key": "heldout/a",
        "split": "test",
        "group": "heldout",
        "image_sha256": "different",
    }
    (tmp_path / "audit").mkdir()
    split_path, samples_path = tmp_path / "splits.json", tmp_path / "audit/samples.json"
    split_path.write_text(
        json.dumps({"train": [sample["key"]], "val": [], "test": [held_out["key"]]})
    )
    samples_path.write_text(json.dumps([sample, held_out]))
    request = {
        "dataset_root": str(tmp_path),
        "split_sha256": evaluate.digest(split_path),
        "samples_sha256": evaluate.digest(samples_path),
        "class_names": names,
        "rehearsal": True,
        "image_keys": [sample["key"]],
    }
    original = Image.open

    def open_training_only(path, *args, **kwargs):
        assert "test" not in Path(path).relative_to(tmp_path).parts
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Image, "open", open_training_only)
    selected = evaluate.validate_dataset(request, names)
    assert [row["key"] for row in selected] == ["training/a"]
    rgb, decoded = evaluate.load_test_image(tmp_path, selected[0], 21)
    assert rgb.shape == (3, 7, 3)
    np.testing.assert_array_equal(decoded, target)
    with pytest.raises(evaluate.TestEvaluationError, match="belong to training"):
        evaluate.validate_dataset({**request, "image_keys": [held_out["key"]]}, names)


def test_test_runner_cli_loads_its_contract_from_an_unrelated_working_directory(tmp_path):
    script = Path(__file__).resolve().parents[1] / "scripts/run_rad_test.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"], cwd=tmp_path, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert "--request" in result.stdout
