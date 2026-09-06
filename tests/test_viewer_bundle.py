"""Portable bundle creation must preserve IDs and fail without partial output."""

import json

import pytest
import yaml
from PIL import Image
from scripts.prepare_viewer_bundle import prepare


def setup_data(tmp_path):
    images, masks, preds = [tmp_path / n for n in ("images", "masks", "preds")]
    for p in (images, masks, preds):
        (p / "scene folder").mkdir(parents=True)
    Image.new("RGB", (2, 2), "white").save(images / "scene folder/frame.png")
    for p in (masks, preds):
        Image.frombytes("L", (2, 2), bytes([0, 1, 1, 255])).save(p / "scene folder/frame.png")
    taxonomy = tmp_path / "canonical.yaml"
    taxonomy.write_text(
        yaml.safe_dump(
            {
                "classes": [
                    {"id": 0, "name": "ground", "color": [0, 0, 0]},
                    {"id": 1, "name": "mud", "color": [255, 0, 0]},
                ]
            }
        )
    )
    return images, masks, taxonomy, {"model": preds}, tmp_path / "bundle", "Review"


def test_bundle_preserves_ids_and_source_names(tmp_path):
    args = setup_data(tmp_path)
    assert prepare(*args) == 1
    manifest = json.loads((args[4] / "bundle-manifest.json").read_text())
    scene = args[4] / manifest[0]["scene"]
    assert Image.open(scene / "model.png").tobytes() == bytes([0, 1, 1, 255])
    assert json.loads((scene / "scene.json").read_text())["title"] == "scene folder/frame"
    with pytest.raises(ValueError, match="already exists"):
        prepare(*args)


@pytest.mark.parametrize("values", [[0, 2, 1, 255], [0, 255, 1, 255]])
def test_bad_prediction_leaves_no_partial_bundle(tmp_path, values):
    args = setup_data(tmp_path)
    Image.frombytes("L", (2, 2), bytes(values)).save(args[3]["model"] / "scene folder/frame.png")
    with pytest.raises(ValueError):
        prepare(*args)
    assert not args[4].exists()
    assert not list(tmp_path.glob(".viewer-bundle-*"))


def test_ground_truth_only_supported(tmp_path):
    args = list(setup_data(tmp_path))
    args[3] = {}
    assert prepare(*args) == 1
