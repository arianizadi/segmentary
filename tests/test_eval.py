"""End-to-end checkpoint evaluation and CLI failure-mode tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
import torch
import yaml
from torch import nn

from segmentary import eval as eval_module
from segmentary import results_table
from segmentary.config import DataConfig, ExperimentConfig, ModelConfig, StageConfig, config_hash
from segmentary.engine.ema import EMA_CHECKPOINT_KEY, EmaConfig, ModelEma
from segmentary.models.tuning import apply_tuning
from segmentary.models.wrappers import HFDenseWrapper
from segmentary.utils.results import write_results as real_write_results

REPO_ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_CHECKPOINT = Path(
    os.environ.get(
        "SEGMENTARY_CALIBRATION_CHECKPOINT",
        REPO_ROOT / "runs" / "calib_cs19_b2_seed0" / "cityscapes" / "best.ckpt",
    )
)


def _fill(module: torch.nn.Module, value: float) -> None:
    with torch.no_grad():
        for parameter in module.parameters():
            parameter.fill_(value)


class _TinyDenseNet(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.backbone = nn.Module()
        self.backbone.attention = nn.Module()
        self.backbone.attention.q_proj = nn.Linear(3, 3)
        self.decode_head = nn.Module()
        self.decode_head.classifier = nn.Conv2d(3, 2, 1)

    def forward(self, pixel_values: torch.Tensor) -> SimpleNamespace:
        features = pixel_values.movedim(1, -1)
        features = self.backbone.attention.q_proj(features).movedim(-1, 1)
        return SimpleNamespace(logits=self.decode_head.classifier(features))


def _tiny_dense(seed: int) -> HFDenseWrapper:
    torch.manual_seed(seed)
    return HFDenseWrapper(
        _TinyDenseNet(),
        2,
        backbone_path="backbone",
        head_paths=("decode_head",),
    )


def _lora_experiment(*, rank: int = 2) -> ExperimentConfig:
    return ExperimentConfig(
        name="eval-lora-test",
        space="unused",
        model=ModelConfig(
            arch="segformer_b0",
            tuning="lora",
            lora_targets=["q_proj"],
            lora_r=rank,
        ),
        stages=[
            StageConfig(
                name="stage",
                data=[DataConfig(name="cityscapes", root="/unused")],
            )
        ],
    )


def test_checkpoint_loader_selects_raw_or_nested_ema_weights(tmp_path: Path) -> None:
    raw = torch.nn.Linear(2, 2)
    _fill(raw, 1.0)
    shadow_source = torch.nn.Linear(2, 2)
    _fill(shadow_source, 2.0)
    ema = ModelEma(shadow_source, EmaConfig())
    checkpoint = tmp_path / "both.ckpt"
    torch.save(
        {
            "state_dict": {
                f"model.{name}": tensor.detach().clone()
                for name, tensor in raw.state_dict().items()
            },
            EMA_CHECKPOINT_KEY: ema.state_dict(),
        },
        checkpoint,
    )

    raw_target = torch.nn.Linear(2, 2)
    eval_module.load_checkpoint(raw_target, checkpoint, use_ema=False)
    assert all(parameter.eq(1.0).all() for parameter in raw_target.parameters())

    ema_target = torch.nn.Linear(2, 2)
    eval_module.load_checkpoint(ema_target, checkpoint, use_ema=True)
    assert all(parameter.eq(2.0).all() for parameter in ema_target.parameters())


def test_checkpoint_loader_rejects_incomplete_raw_state(tmp_path: Path) -> None:
    checkpoint = tmp_path / "incomplete.ckpt"
    torch.save({"state_dict": {"model.weight": torch.zeros(2, 2)}}, checkpoint)
    with pytest.raises(RuntimeError, match="1 missing"):
        eval_module.load_checkpoint(torch.nn.Linear(2, 2), checkpoint, use_ema=False)


@pytest.mark.parametrize("use_ema", [False, True])
def test_configured_loader_warm_starts_raw_checkpoint_before_lora(
    tmp_path: Path, use_ema: bool
) -> None:
    raw = _tiny_dense(seed=1)
    shadow = _tiny_dense(seed=2)
    _fill(raw, 1.0)
    _fill(shadow, 2.0)
    checkpoint = tmp_path / "raw.ckpt"
    torch.save(
        {
            "state_dict": {
                f"model.{name}": tensor.detach().clone()
                for name, tensor in raw.state_dict().items()
            },
            EMA_CHECKPOINT_KEY: ModelEma(shadow, EmaConfig()).state_dict(),
        },
        checkpoint,
    )

    loaded = eval_module.load_configured_checkpoint(
        _tiny_dense(seed=3), _lora_experiment(), checkpoint, use_ema
    )
    expected = 2.0 if use_ema else 1.0
    state = loaded.state_dict()
    assert state["model.backbone.attention.q_proj.base_layer.weight"].eq(expected).all()
    assert state["model.decode_head.modules_to_save.default.classifier.weight"].eq(expected).all()
    assert any("lora_A" in name for name in state)


@pytest.mark.parametrize("use_ema", [False, True])
def test_configured_loader_injects_lora_before_loading_adapter_checkpoint(
    tmp_path: Path, use_ema: bool
) -> None:
    cfg = _lora_experiment()
    raw_source = apply_tuning(_tiny_dense(seed=4), cfg.model)
    ema_source = apply_tuning(_tiny_dense(seed=5), cfg.model)
    _fill(raw_source, 3.0)
    _fill(ema_source, 4.0)
    checkpoint = tmp_path / "adapted.ckpt"
    torch.save(
        {
            "state_dict": {
                f"model.{name}": tensor.detach().clone()
                for name, tensor in raw_source.state_dict().items()
            },
            EMA_CHECKPOINT_KEY: ModelEma(ema_source, EmaConfig()).state_dict(),
        },
        checkpoint,
    )

    loaded = eval_module.load_configured_checkpoint(_tiny_dense(seed=6), cfg, checkpoint, use_ema)
    expected = ema_source.state_dict() if use_ema else raw_source.state_dict()
    assert set(loaded.state_dict()) == set(expected)
    assert all(torch.equal(tensor, expected[name]) for name, tensor in loaded.state_dict().items())


def test_configured_loader_rejects_lora_rank_mismatch(tmp_path: Path) -> None:
    source_cfg = _lora_experiment(rank=2)
    source = apply_tuning(_tiny_dense(seed=7), source_cfg.model)
    checkpoint = tmp_path / "rank-two.ckpt"
    torch.save(
        {
            "state_dict": {
                f"model.{name}": tensor.detach().clone()
                for name, tensor in source.state_dict().items()
            }
        },
        checkpoint,
    )

    with pytest.raises(RuntimeError, match="size mismatch"):
        eval_module.load_configured_checkpoint(
            _tiny_dense(seed=8), _lora_experiment(rank=3), checkpoint, False
        )


def test_ema_flag_fails_clearly_when_checkpoint_has_no_ema(
    tmp_path: Path, taxonomy_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exercise the flag through ``main``, not just the checkpoint helper."""
    config = tmp_path / "eval.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "name": "ema-error",
                "space": "rail_union",
                "taxonomy_root": str(taxonomy_root),
                "model": {"arch": "segformer_b0"},
                "stages": [
                    {
                        "name": "stage",
                        "data": [
                            {
                                "name": "cityscapes",
                                "root": "/unused",
                                "val_split": "validation",
                            }
                        ],
                    }
                ],
            }
        )
    )
    checkpoint = tmp_path / "raw-only.ckpt"
    torch.save(
        {
            "state_dict": {
                "model.weight": torch.zeros(2, 2),
                "model.bias": torch.zeros(2),
            }
        },
        checkpoint,
    )

    seen_splits: list[str] = []

    def fake_dataset(data, space, taxonomy_root, split, transform):
        seen_splits.append(split)
        return object()

    monkeypatch.setattr(eval_module, "build_dataset", fake_dataset)
    monkeypatch.setattr(eval_module, "build_model", lambda config, classes: torch.nn.Linear(2, 2))

    with pytest.raises(
        ValueError,
        match=r"contains no EMA weights.*--ema.*checkpoint that explicitly saved",
    ):
        eval_module.main(
            [
                str(config),
                "--ckpt",
                str(checkpoint),
                "--ema",
                "--device",
                "cpu",
            ]
        )

    # A malformed checkpoint fails before opening dataset files.
    assert seen_splits == []


def test_seed_and_set_overrides_are_recorded_without_hash_collision(
    tmp_path: Path, taxonomy_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Common RailSem19 evals must retain the training seed in provenance."""
    config = tmp_path / "eval.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "name": "common-railsem19",
                "space": "rail_union",
                "taxonomy_root": str(taxonomy_root),
                "model": {"arch": "segformer_b0"},
                "train": {"seed": 99},
                "stages": [
                    {
                        "name": "railsem19",
                        "data": [
                            {
                                "name": "railsem19",
                                "root": "/unused",
                                "split_file": "splits/railsem19_seed0.json",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    checkpoint = tmp_path / "best.ckpt"
    checkpoint.touch()

    space = SimpleNamespace(num_classes=2, ignore_index=255, names=("background", "rail"))

    class Mapping:
        @staticmethod
        def active_mask() -> np.ndarray:
            return np.ones(2, dtype=np.bool_)

    class Dataset:
        @staticmethod
        def describe() -> str:
            return "SyntheticEval(1)"

        @staticmethod
        def __len__() -> int:
            return 1

    target = torch.tensor([[[0, 1], [1, 0]]])
    image = torch.zeros(1, 3, 2, 2)
    logits = torch.nn.functional.one_hot(target, num_classes=2).permute(0, 3, 1, 2).float()

    monkeypatch.setattr(eval_module, "load_space", lambda *args: space)
    monkeypatch.setattr(eval_module, "load_data_mapping", lambda *args: Mapping())
    monkeypatch.setattr(eval_module, "build_eval_transform", lambda *args: object())
    monkeypatch.setattr(eval_module, "build_dataset", lambda *args: Dataset())
    monkeypatch.setattr(eval_module, "build_model", lambda *args: torch.nn.Identity())
    monkeypatch.setattr(
        eval_module,
        "load_configured_checkpoint",
        lambda model, *_args: model,
    )
    monkeypatch.setattr(eval_module, "inference", lambda *args: logits)
    loader_kwargs: list[dict] = []

    def fake_loader(*args, **kwargs):
        loader_kwargs.append(kwargs)
        return [{"image": image, "mask": target}]

    monkeypatch.setattr(eval_module, "DataLoader", fake_loader)
    monkeypatch.setattr(eval_module, "tqdm", lambda iterable, **kwargs: iterable)
    monkeypatch.setattr(eval_module, "git_sha", lambda *args: ("a" * 40, False))
    monkeypatch.setattr(eval_module, "collect_env", lambda: {})
    monkeypatch.setattr(eval_module, "peak_vram", lambda: {})

    seeded: list[int] = []
    monkeypatch.setattr(eval_module, "seed_everything", seeded.append)
    records = []

    def capture_record(path, record) -> None:
        records.append(record)
        real_write_results(path, record)

    monkeypatch.setattr(eval_module, "write_results", capture_record)

    outputs = [tmp_path / "common_seed1.json", tmp_path / "common_seed2.json"]
    for seed, output in zip((1, 2), outputs, strict=True):
        assert (
            eval_module.main(
                [
                    str(config),
                    "--ckpt",
                    str(checkpoint),
                    "--set",
                    "train.seed=88",
                    "--set",
                    "eval.boundary_tolerance_frac=0.125",
                    "--set",
                    "eval.save_confusion=false",
                    "--seed",
                    str(seed),
                    "--out",
                    str(output),
                    "--device",
                    "cpu",
                ]
            )
            == 0
        )

    assert seeded == [1, 2]
    assert len(loader_kwargs) == 2
    assert all(kwargs["multiprocessing_context"] == "spawn" for kwargs in loader_kwargs)
    assert all(kwargs["num_workers"] == 4 for kwargs in loader_kwargs)
    assert [record.seed for record in records] == [1, 2]
    assert [record.config["train"]["seed"] for record in records] == [1, 2]
    assert all(record.config["eval"]["boundary_tolerance_frac"] == 0.125 for record in records)
    assert all(record.config["eval"]["save_confusion"] is False for record in records)
    assert all(record.config["evaluation"]["data"]["name"] == "railsem19" for record in records)
    assert all(record.config["evaluation"]["weights"] == "raw" for record in records)
    assert all(record.config["evaluation"]["tta"]["scales"] == [1.0] for record in records)
    assert all(record.metrics["boundary"]["tolerance_frac"] == 0.125 for record in records)
    assert all(record.env["input_normalization"]["source"] == "imagenet" for record in records)
    assert all("confusion" not in record.metrics for record in records)
    assert all(record.config_hash == config_hash(record.config) for record in records)
    assert records[0].config_hash != records[1].config_hash
    assert outputs[0] != outputs[1] and all(output.is_file() for output in outputs)
    assert [json.loads(output.read_text())["seed"] for output in outputs] == [1, 2]

    # Dataset/loader protocol overrides are part of provenance, not hidden in
    # the stage label or notes.  Two otherwise-identical evals must not collide.
    overridden = []
    for image_dir in ("images_a/{split}", "images_b/{split}"):
        output = tmp_path / f"override_{len(overridden)}.json"
        assert (
            eval_module.main(
                [
                    str(config),
                    "--ckpt",
                    str(checkpoint),
                    "--seed",
                    "1",
                    "--dataset",
                    "external",
                    "--root",
                    str(tmp_path),
                    "--loader",
                    "folder",
                    "--mapping",
                    "external_schema",
                    "--loader-options",
                    json.dumps({"image_dir": image_dir}),
                    "--out",
                    str(output),
                    "--device",
                    "cpu",
                ]
            )
            == 0
        )
        overridden.append(records[-1])

    assert overridden[0].config_hash != overridden[1].config_hash
    assert overridden[0].config["evaluation"]["data"]["loader"] == "folder"
    assert overridden[0].config["evaluation"]["data"]["mapping"] == "external_schema"
    assert (
        overridden[0].config["evaluation"]["data"]["loader_options"]
        != overridden[1].config["evaluation"]["data"]["loader_options"]
    )

    # Non-picklable custom loaders can opt into in-process evaluation. The
    # multiprocessing context must be absent entirely when workers are zero.
    assert (
        eval_module.main(
            [
                str(config),
                "--ckpt",
                str(checkpoint),
                "--seed",
                "1",
                "--num-workers",
                "0",
                "--out",
                str(tmp_path / "workers_zero.json"),
                "--device",
                "cpu",
            ]
        )
        == 0
    )
    assert loader_kwargs[-1]["num_workers"] == 0
    assert "multiprocessing_context" not in loader_kwargs[-1]
    assert records[-1].config["evaluation"]["num_workers"] == 0

    # The default is a results.json inside a descriptive directory so the
    # fail-closed table builder discovers standalone evaluations automatically.
    default_output = tmp_path / "eval_railsem19_val" / "results.json"
    assert (
        eval_module.main(
            [
                str(config),
                "--ckpt",
                str(checkpoint),
                "--seed",
                "1",
                "--num-workers",
                "0",
                "--device",
                "cpu",
            ]
        )
        == 0
    )
    assert default_output.is_file()
    table_dir = tmp_path / "table"
    assert results_table.main(["--runs", str(tmp_path), "--out", str(table_dir)]) == 0
    assert "eval:railsem19:val" in (table_dir / "results.md").read_text(encoding="utf-8")


@pytest.mark.slow
@pytest.mark.gpu
def test_real_checkpoint_limit_four_matches_recorded_golden(
    tmp_path: Path, cityscapes_root: Path
) -> None:
    """Run the actual SegFormer-B2 checkpoint through native sliding-window eval.

    The golden is for the first four Cityscapes validation images specifically;
    it was captured from this training checkpoint.  It is intentionally not the
    500-image training-run mIoU, because ``--limit 4`` changes class support and
    the sample distribution substantially.
    """
    if not torch.cuda.is_available():
        pytest.skip("real checkpoint evaluation requires CUDA")
    if not CALIBRATION_CHECKPOINT.is_file():
        pytest.skip(f"calibration checkpoint not found at {CALIBRATION_CHECKPOINT}")

    out = tmp_path / "results.json"
    rc = eval_module.main(
        [
            str(REPO_ROOT / "configs" / "base.yaml"),
            str(REPO_ROOT / "configs" / "models" / "segformer_b2.yaml"),
            str(REPO_ROOT / "configs" / "curricula" / "reference_cityscapes19.yaml"),
            "--ckpt",
            str(CALIBRATION_CHECKPOINT),
            "--dataset",
            "cityscapes",
            "--root",
            str(cityscapes_root),
            "--limit",
            "4",
            "--out",
            str(out),
            "--device",
            "cuda:0",
        ]
    )

    assert rc == 0 and out.is_file()
    result = json.loads(out.read_text())
    assert result["dataset_sizes"] == {"eval": 4}
    assert result["stage"] == "eval:cityscapes:val"
    assert result["metrics"]["miou"] == pytest.approx(0.6350306086, abs=0.002)
    assert sum(result["metrics"]["support"].values()) > 0
    assert f"checkpoint={CALIBRATION_CHECKPOINT}" in result["notes"]
