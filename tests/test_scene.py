"""One-scene comparison export uses the real taxonomy and inference contracts."""

from __future__ import annotations

import hashlib
import json
import shutil
import stat
import struct
from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image
from torch import nn

from segmentary import scene

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIGS = [
    REPO_ROOT / "configs/base.yaml",
    REPO_ROOT / "configs/models/native_resnet18_fpn_fcn.yaml",
    REPO_ROOT / "configs/curricula/rs_only.yaml",
]


class _ConstantCanonicalModel(nn.Module):
    def __init__(self, class_id: int = 16) -> None:
        super().__init__()
        self.class_id = class_id

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        logits = torch.zeros(
            image.shape[0], 21, image.shape[2], image.shape[3], device=image.device
        )
        logits[:, self.class_id] = 5.0
        return logits


class _WrongSizeModel(_ConstantCanonicalModel):
    def forward(self, image: torch.Tensor) -> torch.Tensor:
        logits = super().forward(image)
        return logits[:, :, :-1, :]


class _NonFiniteModel(_ConstantCanonicalModel):
    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return torch.full(
            (image.shape[0], 21, image.shape[2], image.shape[3]),
            float("nan"),
            device=image.device,
        )


def _fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / "railsem19"
    image_dir = root / "jpgs" / "rs19_val"
    label_dir = root / "uint8" / "rs19_val"
    image_dir.mkdir(parents=True)
    label_dir.mkdir(parents=True)
    rgb = np.arange(6 * 8 * 3, dtype=np.uint8).reshape(6, 8, 3)
    native = np.full((6, 8), 3, dtype=np.uint8)  # native tram-track -> canonical id 19
    native[0, 0] = 255
    Image.fromarray(rgb).save(image_dir / "rs04890.jpg")
    Image.fromarray(native).save(label_dir / "rs04890.png")
    split = tmp_path / "split.json"
    split.write_text(json.dumps({"train": [], "val": ["rs04890"]}), encoding="utf-8")
    checkpoint = tmp_path / "best.ckpt"
    checkpoint.write_bytes(b"checkpoint fixture")
    return root, split, checkpoint


def _argv(root: Path, split: Path, checkpoint: Path, output: Path) -> list[str]:
    return [
        *(str(path) for path in CONFIGS),
        "--ckpt",
        str(checkpoint),
        "--name",
        "eomt-rail-only",
        "--out",
        str(output),
        "--device",
        "cpu",
        "--dataset",
        "railsem19",
        "--root",
        str(root),
        "--split",
        "val",
        "--split-file",
        str(split),
        "--mapping",
        "railsem19",
        "--frame-key",
        "rs04890",
        "--set",
        f"taxonomy_root={REPO_ROOT / 'taxonomy'}",
    ]


def _rename_prediction(args: list[str], name: str) -> None:
    args[args.index("eomt-rail-only")] = name


def _png_chunks(path: Path) -> list[str]:
    raw = path.read_bytes()
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    chunks: list[str] = []
    offset = 8
    while offset < len(raw):
        length = struct.unpack(">I", raw[offset : offset + 4])[0]
        kind = raw[offset + 4 : offset + 8].decode("ascii")
        chunks.append(kind)
        offset += 12 + length
    return chunks


def test_export_uses_canonical_ids_and_writes_lossless_index_pngs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "comparison"
    monkeypatch.setattr(scene, "build_model", lambda *_: _ConstantCanonicalModel())
    monkeypatch.setattr(scene, "load_configured_checkpoint", lambda model, *_args: model)

    assert scene.main(_argv(root, split, checkpoint, output)) == 0

    scene_dir = output / "rs04890"
    with Image.open(scene_dir / "gt.png") as image:
        assert image.mode == "L"
        gt = np.asarray(image)
    with Image.open(scene_dir / "eomt-rail-only.png") as image:
        assert image.mode == "L"
        prediction = np.asarray(image)
    assert gt[0, 0] == 255
    assert set(np.unique(gt[1:])) == {19}
    assert np.all(prediction == 16)
    for filename in ("gt.png", "eomt-rail-only.png"):
        chunks = _png_chunks(scene_dir / filename)
        assert "gAMA" not in chunks
        assert "sRGB" not in chunks
        assert "iCCP" not in chunks

    config = json.loads((output / "config.json").read_text(encoding="utf-8"))
    classes = config["taxonomy"]["classes"]
    assert len(classes) == 21
    assert classes[3]["name"] == "fence"
    assert classes[16]["name"] == "rail-track"
    assert classes[19]["name"] == "tram-track"
    assert classes[13]["evaluate"] is False
    assert classes[14]["evaluate"] is False
    assert config["taxonomy"]["ignore_index"] == 255

    manifest = json.loads((scene_dir / "scene.json").read_text(encoding="utf-8"))
    record = manifest["predictions"]["eomt-rail-only"]
    assert manifest["frame_key"] == "rs04890"
    assert manifest["dataset"] == "railsem19"
    assert record["checkpoint"]["sha256"] == hashlib.sha256(checkpoint.read_bytes()).hexdigest()
    assert record["protocol"]["native_resolution"] == [6, 8]
    assert record["protocol"]["configured_inference"] == "sliding_window"
    assert record["protocol"]["execution"] == "whole_image_fallback"
    for filename in ("config.json", "rs04890/input.png", "rs04890/gt.png"):
        mode = stat.S_IMODE((output / filename).stat().st_mode)
        assert mode == 0o644


def test_export_refuses_accidental_named_prediction_overwrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "comparison"
    monkeypatch.setattr(scene, "build_model", lambda *_: _ConstantCanonicalModel())
    monkeypatch.setattr(scene, "load_configured_checkpoint", lambda model, *_args: model)
    args = _argv(root, split, checkpoint, output)

    assert scene.main(args) == 0
    capsys.readouterr()
    with pytest.raises(SystemExit) as raised:
        scene.main(args)
    assert raised.value.code == 1
    assert "--replace" in capsys.readouterr().err


def test_export_fails_when_frame_key_is_not_in_requested_split(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "comparison"
    monkeypatch.setattr(scene, "build_model", lambda *_: _ConstantCanonicalModel())
    monkeypatch.setattr(scene, "load_configured_checkpoint", lambda model, *_args: model)
    args = _argv(root, split, checkpoint, output)
    args[args.index("rs04890")] = "missing-frame"

    with pytest.raises(SystemExit) as raised:
        scene.main(args)
    assert raised.value.code == 1
    assert "not present" in capsys.readouterr().err


def test_export_fails_before_writing_when_model_output_dimensions_are_wrong(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "comparison"
    monkeypatch.setattr(scene, "build_model", lambda *_: _WrongSizeModel())
    monkeypatch.setattr(scene, "load_configured_checkpoint", lambda model, *_args: model)

    with pytest.raises(SystemExit) as raised:
        scene.main(_argv(root, split, checkpoint, output))
    assert raised.value.code == 1
    assert "expected" in capsys.readouterr().err
    assert not output.exists()


def test_export_reports_nonfinite_prediction_as_friendly_cli_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "comparison"
    monkeypatch.setattr(scene, "build_model", lambda *_: _NonFiniteModel())
    monkeypatch.setattr(scene, "load_configured_checkpoint", lambda model, *_args: model)

    with pytest.raises(SystemExit) as raised:
        scene.main(_argv(root, split, checkpoint, output))
    assert raised.value.code == 1
    assert "non-finite" in capsys.readouterr().err
    assert not output.exists()


def test_export_refuses_legacy_native_config_before_building_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "legacy-comparison"
    output.mkdir()
    (output / "rs19-config.json").write_text('{"labels": []}\n', encoding="utf-8")
    monkeypatch.setattr(
        scene, "build_model", lambda *_: pytest.fail("legacy root must fail before model build")
    )

    with pytest.raises(SystemExit) as raised:
        scene.main(_argv(root, split, checkpoint, output))
    assert raised.value.code == 1
    error = capsys.readouterr().err
    assert "legacy RailSem native-ID" in error
    assert not (output / "config.json").exists()


def test_export_refuses_manifest_free_legacy_scene_before_building_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "legacy-comparison"
    legacy = output / "rs00001"
    legacy.mkdir(parents=True)
    (legacy / "input.jpg").write_bytes(b"legacy input")
    (legacy / "gt.png").write_bytes(b"legacy ground truth")
    monkeypatch.setattr(
        scene, "build_model", lambda *_: pytest.fail("legacy scene must fail before model build")
    )

    with pytest.raises(SystemExit) as raised:
        scene.main(_argv(root, split, checkpoint, output))
    assert raised.value.code == 1
    assert "has no compatible Segmentary scene.json" in capsys.readouterr().err
    assert not (output / "config.json").exists()


def test_export_identifies_interrupted_canonical_scene_and_requires_clean_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "comparison"
    monkeypatch.setattr(scene, "build_model", lambda *_: _ConstantCanonicalModel())
    monkeypatch.setattr(scene, "load_configured_checkpoint", lambda model, *_args: model)
    real_atomic_bytes = scene._atomic_bytes

    def interrupt_manifest(path: Path, payload: bytes) -> None:
        if path.name == "scene.json":
            raise OSError("simulated interruption")
        real_atomic_bytes(path, payload)

    monkeypatch.setattr(scene, "_atomic_bytes", interrupt_manifest)
    with pytest.raises(SystemExit) as interrupted:
        scene.main(_argv(root, split, checkpoint, output))
    assert interrupted.value.code == 1
    assert "simulated interruption" in capsys.readouterr().err
    monkeypatch.setattr(scene, "_atomic_bytes", real_atomic_bytes)

    with pytest.raises(SystemExit) as retry:
        scene.main(_argv(root, split, checkpoint, output))
    assert retry.value.code == 1
    error = capsys.readouterr().err
    assert "incomplete Segmentary scene" in error
    assert "Remove this scene directory and retry" in error
    assert "legacy comparison scene" not in error


def test_export_refuses_a_second_input_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "comparison"
    monkeypatch.setattr(scene, "build_model", lambda *_: _ConstantCanonicalModel())
    monkeypatch.setattr(scene, "load_configured_checkpoint", lambda model, *_args: model)
    assert scene.main(_argv(root, split, checkpoint, output)) == 0
    capsys.readouterr()
    shutil.copyfile(root / "jpgs" / "rs19_val" / "rs04890.jpg", output / "rs04890" / "input.jpg")
    args = _argv(root, split, checkpoint, output)
    _rename_prediction(args, "eomt-city-to-rail")

    with pytest.raises(SystemExit) as raised:
        scene.main(args)
    assert raised.value.code == 1
    assert "exactly one input image" in capsys.readouterr().err
    assert not (output / "rs04890" / "eomt-city-to-rail.png").exists()


def test_export_verifies_and_reuses_one_existing_input_jpeg(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "comparison"
    monkeypatch.setattr(scene, "build_model", lambda *_: _ConstantCanonicalModel())
    monkeypatch.setattr(scene, "load_configured_checkpoint", lambda model, *_args: model)
    assert scene.main(_argv(root, split, checkpoint, output)) == 0
    scene_dir = output / "rs04890"
    (scene_dir / "input.png").unlink()
    input_jpeg = scene_dir / "input.jpg"
    shutil.copyfile(root / "jpgs" / "rs19_val" / "rs04890.jpg", input_jpeg)
    manifest_path = scene_dir / "scene.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["artifacts"]["input"] = {
        "file": "input.jpg",
        "sha256": hashlib.sha256(input_jpeg.read_bytes()).hexdigest(),
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args = _argv(root, split, checkpoint, output)
    _rename_prediction(args, "eomt-city-to-rail")

    assert scene.main(args) == 0
    assert input_jpeg.is_file()
    assert not (scene_dir / "input.png").exists()
    updated = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert set(updated["predictions"]) == {"eomt-rail-only", "eomt-city-to-rail"}


def test_export_refuses_mismatched_prediction_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "comparison"
    monkeypatch.setattr(scene, "build_model", lambda *_: _ConstantCanonicalModel())
    monkeypatch.setattr(scene, "load_configured_checkpoint", lambda model, *_args: model)
    assert scene.main(_argv(root, split, checkpoint, output)) == 0
    capsys.readouterr()
    args = _argv(root, split, checkpoint, output)
    _rename_prediction(args, "eomt-city-to-rail")
    args.extend(["--set", "eval.window=[5,5]", "--set", "eval.stride=[5,5]"])

    with pytest.raises(SystemExit) as raised:
        scene.main(args)
    assert raised.value.code == 1
    error = capsys.readouterr().err
    assert "different comparison protocol" in error
    assert "window" in error
    assert not (output / "rs04890" / "eomt-city-to-rail.png").exists()


def test_export_refuses_mismatched_autocast_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root, split, checkpoint = _fixture(tmp_path)
    output = tmp_path / "comparison"
    monkeypatch.setattr(scene, "build_model", lambda *_: _ConstantCanonicalModel())
    monkeypatch.setattr(scene, "load_configured_checkpoint", lambda model, *_args: model)
    assert scene.main(_argv(root, split, checkpoint, output)) == 0
    capsys.readouterr()
    manifest_path = output / "rs04890" / "scene.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["predictions"]["eomt-rail-only"]["protocol"]["autocast"] = "bfloat16"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args = _argv(root, split, checkpoint, output)
    _rename_prediction(args, "eomt-city-to-rail")

    with pytest.raises(SystemExit) as raised:
        scene.main(args)
    assert raised.value.code == 1
    error = capsys.readouterr().err
    assert "different comparison protocol" in error
    assert "autocast" in error
    assert not (output / "rs04890" / "eomt-city-to-rail.png").exists()
