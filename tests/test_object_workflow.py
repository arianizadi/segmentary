"""CPU end-to-end checks using a real tiny EoMT, without Hub or training servers."""

import json
import shutil
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml
from PIL import Image
from transformers import EomtConfig, EomtForUniversalSegmentation

from segmentary.config import ModelConfig
from segmentary.models.mask_classification import MaskClassWrapper
from segmentary.objects import runner
from segmentary.objects.cli import main
from segmentary.objects.config import ObjectConfig, ObjectDataConfig, load_config


def tiny_model(config, num_classes):
    upstream = EomtForUniversalSegmentation(
        EomtConfig(
            hidden_size=32,
            num_hidden_layers=2,
            num_attention_heads=4,
            image_size=32,
            patch_size=8,
            num_blocks=1,
            num_upscale_blocks=1,
            num_queries=4,
            num_register_tokens=0,
            num_labels=num_classes,
        )
    )
    return MaskClassWrapper(
        upstream,
        num_classes,
        backbone_paths=("embeddings", "layers"),
        head_paths=("class_predictor", "mask_head", "query"),
    )


def fixture_config(tmp_path, task):
    images = tmp_path / "images"
    images.mkdir()
    Image.fromarray(np.full((32, 32, 3), 127, dtype=np.uint8)).save(images / "one.png")
    categories = [{"id": 7, "name": "object", "isthing": 1}]
    if task == "panoptic":
        categories.append({"id": 9, "name": "ground", "isthing": 0})
    annotation = {
        "images": [{"id": 1, "file_name": "one.png", "height": 32, "width": 32}],
        "categories": categories,
    }
    masks = None
    if task == "instance":
        annotation["annotations"] = [
            {
                "id": i,
                "image_id": 1,
                "category_id": 7,
                "segmentation": [[x, 4, x + 8, 4, x + 8, 12, x, 12]],
                "iscrowd": 0,
            }
            for i, x in enumerate((2, 20), 1)
        ]
    else:
        masks = tmp_path / "masks"
        masks.mkdir()
        ids = np.full((32, 32), 3, np.uint8)
        ids[4:12, 2:10] = 1
        ids[4:12, 20:28] = 2
        rgb = np.zeros((32, 32, 3), np.uint8)
        rgb[:, :, 0] = ids
        Image.fromarray(rgb).save(masks / "one.png")
        annotation["annotations"] = [
            {
                "image_id": 1,
                "file_name": "one.png",
                "segments_info": [
                    {
                        "id": i,
                        "category_id": 7 if i < 3 else 9,
                        "iscrowd": 0,
                        "area": int((ids == i).sum()),
                    }
                    for i in (1, 2, 3)
                ],
            }
        ]
    path = tmp_path / "labels.json"
    path.write_text(json.dumps(annotation))
    data = ObjectDataConfig(str(images), str(path), str(masks) if masks else None)
    return ObjectConfig(
        task=task,
        model=ModelConfig(arch="eomt_large"),
        train=data,
        val=data,
        output=str(tmp_path / "run"),
        allow_train_val_overlap=True,
        image_size=[32, 32],
        max_steps=2,
        val_every=1,
        num_points=32,
        score_threshold=0.01,
    )


@pytest.mark.parametrize("task", ["instance", "panoptic"])
def test_real_query_model_train_evaluate_checkpoint_and_export(tmp_path, monkeypatch, task):
    config = fixture_config(tmp_path, task)
    # Exercise the normal pretrained-model factory, but use a tiny local model
    # so this scientific smoke test needs neither a GPU nor the network.
    local = tmp_path / "tiny-eomt"
    tiny_model(config, 1 if task == "instance" else 2).model.save_pretrained(local)
    config.model.checkpoint = str(local)
    result = runner.train(config)
    assert result["steps"] == 2
    assert all(np.isfinite(row["loss"]) for row in result["history"])
    checkpoint = Path(config.output) / "last.pt"
    shutil.rmtree(local)  # Reload must not depend on the original initializer.
    saved = torch.load(checkpoint, weights_only=True)
    assert saved["step"] == 2 and saved["task"] == task
    data = runner.dataset(config, config.val)
    model = runner.load_checkpoint(config, checkpoint, data.categories)
    metrics = runner.evaluate(model, config, data)
    assert 0 <= metrics["map" if task == "instance" else "pq"] <= 1
    exported = runner.predict(config, checkpoint, Path(config.val.images), tmp_path / "predictions")
    assert exported["images"][0]["file_name"] == "one.png"
    assert exported["checkpoint_sha256"]
    if task == "instance":
        for item in exported["annotations"]:
            assert item["category_id"] == 7 and "counts" in item["segmentation"]
    else:
        assert (tmp_path / "predictions" / "00000001.png").exists()
    with pytest.raises(FileExistsError):
        runner.train(config)
    with pytest.raises(ValueError, match="category"):
        runner.load_checkpoint(config, checkpoint, [{"id": 99, "name": "bad"}])


def test_object_config_strict_and_cli_help(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0 and "panoptic" in capsys.readouterr().out
    path = tmp_path / "config.yaml"
    path.write_text("task: semantic\n")
    with pytest.raises((ValueError, TypeError)):
        load_config(path)


def test_eval_keeps_training_categories_when_validation_declares_subset(tmp_path, capsys):
    config = fixture_config(tmp_path, "instance")
    config.max_steps = 1
    validation_path = tmp_path / "val.json"
    original = json.loads(Path(config.train.annotations).read_text())
    validation_path.write_text(json.dumps(original))
    original["categories"].append({"id": 20, "name": "unused", "isthing": 1})
    Path(config.train.annotations).write_text(json.dumps(original))
    config.val = ObjectDataConfig(config.train.images, str(validation_path))
    local = tmp_path / "tiny-eomt"
    tiny_model(config, 2).model.save_pretrained(local)
    config.model.checkpoint = str(local)
    runner.train(config)
    shutil.rmtree(local)
    path = tmp_path / "run.yaml"
    path.write_text(yaml.safe_dump(asdict(config)))
    output = tmp_path / "eval.json"
    main(
        [
            "eval",
            str(path),
            "--checkpoint",
            str(Path(config.output) / "last.pt"),
            "--out",
            str(output),
        ]
    )
    results = json.loads(output.read_text())
    assert len(results["checkpoint_sha256"]) == 64
    assert results["config"]["task"] == "instance"
    assert "map" in results


def test_training_rejects_leaked_validation_before_model_build(tmp_path, monkeypatch):
    config = fixture_config(tmp_path, "instance")
    config.allow_train_val_overlap = False
    monkeypatch.setattr(runner, "make_model", lambda *args: pytest.fail("must fail before loading"))
    with pytest.raises(ValueError, match="identical image"):
        runner.train(config)
    assert not Path(config.output).exists()
