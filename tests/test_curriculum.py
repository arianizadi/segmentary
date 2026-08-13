"""Tests for the curriculum chain, especially checkpoint hand-off between stages.

The fast tests use an actual serialized Lightning-shaped checkpoint around a
small dense model.  The marked integration test exercises the same path with
SegFormer-B0, real Cityscapes/RailSem19 samples, and one GPU.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import torch
import yaml
from torch import nn
from torch.utils.data import DataLoader, Dataset

import segmentary.curriculum as curriculum
from segmentary import eval as eval_module
from segmentary.checkpoints import TRAINING_RESUME_KEY, TRAINING_RESUME_SCHEMA_VERSION
from segmentary.config import (
    AugConfigSpec,
    DataConfig,
    EvalConfig,
    ExperimentConfig,
    LossSpec,
    ModelConfig,
    OptimConfig,
    StageConfig,
    TrainConfig,
    config_hash,
    to_dict,
)
from segmentary.curriculum import (
    _checkpoint_callbacks,
    _strategy,
    apply_freeze,
    load_backbone_weights,
    prepare_stage_model,
    resolve_init,
)
from segmentary.engine.ema import EMA_CHECKPOINT_KEY, EmaConfig, ModelEma
from segmentary.engine.losses import LossConfig, SegmentationLoss
from segmentary.engine.module import SegLitModule
from segmentary.models.tuning import apply_tuning
from segmentary.models.wrappers import HFDenseWrapper


def _stage(name: str = "stage", *, init_from: str = "pretrained") -> StageConfig:
    return StageConfig(
        name=name,
        data=[DataConfig(name="cityscapes", root="/unused")],
        init_from=init_from,
    )


# ---------------------------------------------------------------- resolve_init


def test_resolve_init_pretrained_needs_no_checkpoint():
    assert resolve_init(_stage(init_from="pretrained"), previous=None) is None


def test_resolve_init_previous_returns_the_existing_prior_checkpoint(tmp_path: Path):
    prior = tmp_path / "stage-one.ckpt"
    prior.write_bytes(b"checkpoint")

    assert resolve_init(_stage(name="stage-two", init_from="previous"), prior) == prior


def test_resolve_init_literal_returns_the_existing_path(tmp_path: Path):
    checkpoint = tmp_path / "explicit.ckpt"
    checkpoint.write_bytes(b"checkpoint")

    assert resolve_init(_stage(init_from=str(checkpoint)), previous=None) == checkpoint


def test_resolve_init_previous_on_stage_zero_fails_loudly():
    with pytest.raises(ValueError, match="no earlier stage produced a checkpoint"):
        resolve_init(_stage(name="first", init_from="previous"), previous=None)


@pytest.mark.parametrize("use_previous", [False, True])
def test_resolve_init_rejects_a_missing_checkpoint(tmp_path: Path, use_previous: bool):
    missing = tmp_path / "missing.ckpt"
    stage = _stage(init_from="previous" if use_previous else str(missing))
    previous = missing if use_previous else None

    with pytest.raises(FileNotFoundError, match="checkpoint not found"):
        resolve_init(stage, previous)


# ---------------------------------------------------------------- apply_freeze


class _FreezeModel(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.backbone = nn.Sequential(nn.Linear(3, 4), nn.Linear(4, 4))
        self.classifier = nn.Linear(4, 2)


def test_apply_freeze_freezes_exactly_the_matching_parameter_tensors():
    model = _FreezeModel()
    expected = {"backbone.0.weight", "backbone.0.bias"}

    count = apply_freeze(model, "backbone.0")
    frozen = {name for name, param in model.named_parameters() if not param.requires_grad}

    assert count == len(expected)
    assert frozen == expected
    assert all(
        param.requires_grad for name, param in model.named_parameters() if name not in expected
    )


def test_apply_freeze_none_is_an_exact_noop():
    model = _FreezeModel()

    assert apply_freeze(model, None) == 0
    assert all(param.requires_grad for param in model.parameters())


def test_apply_freeze_rejects_a_spec_that_matches_nothing():
    with pytest.raises(ValueError, match="matched no parameters"):
        apply_freeze(_FreezeModel(), "not_a_real_submodule")


# ----------------------------------------------------- load_backbone_weights


class _TinyDenseNet(nn.Module):
    """HF-shaped module used through the production HFDenseWrapper."""

    def __init__(self, num_classes: int = 3) -> None:
        super().__init__()
        self.backbone = nn.Module()
        self.backbone.stem = nn.Conv2d(3, 4, 3, padding=1)
        self.backbone.attention = nn.Module()
        self.backbone.attention.q_proj = nn.Linear(4, 4)
        # This realistic name deliberately contains the substring "ema".  A
        # prior implementation accidentally exempted every such missing key
        # while intending to exempt external EMA state.
        self.semantic_scale = nn.Parameter(torch.ones(()))
        self.decode_head = nn.Module()
        self.decode_head.classifier = nn.Conv2d(4, num_classes, 1)

    def forward(self, pixel_values: torch.Tensor) -> SimpleNamespace:
        features = self.backbone.stem(pixel_values).movedim(1, -1)
        features = self.backbone.attention.q_proj(features).movedim(-1, 1).relu()
        logits = self.decode_head.classifier(features) * self.semantic_scale
        return SimpleNamespace(logits=logits)


def _tiny_model(seed: int, num_classes: int = 3) -> HFDenseWrapper:
    torch.manual_seed(seed)
    return HFDenseWrapper(
        _TinyDenseNet(num_classes),
        num_classes=num_classes,
        backbone_path="backbone",
        head_paths=("decode_head",),
    )


def _fill_distinct(model: nn.Module) -> None:
    with torch.no_grad():
        for index, parameter in enumerate(model.parameters(), start=1):
            parameter.fill_(float(index))


def _save_lightning_checkpoint(path: Path, model: nn.Module, *, omit: str | None = None) -> None:
    state_dict = {
        f"model.{name}": tensor.detach().clone()
        for name, tensor in model.state_dict().items()
        if name != omit
    }
    torch.save({"state_dict": state_dict, "global_step": 17}, path)


def test_load_backbone_weights_round_trips_a_lightning_checkpoint(tmp_path: Path):
    source = _tiny_model(seed=1)
    _fill_distinct(source)
    checkpoint = tmp_path / "stage-one.ckpt"
    _save_lightning_checkpoint(checkpoint, source)
    target = _tiny_model(seed=2)

    load_backbone_weights(target, checkpoint, reset_head=False)

    source_state = source.state_dict()
    assert set(target.state_dict()) == set(source_state)
    assert all(
        torch.equal(tensor, source_state[name]) for name, tensor in target.state_dict().items()
    )


def test_load_backbone_weights_prefers_the_reported_ema_shadow(tmp_path: Path):
    raw = _tiny_model(seed=1)
    _fill_distinct(raw)
    shadow_source = _tiny_model(seed=2)
    with torch.no_grad():
        for parameter in shadow_source.parameters():
            parameter.fill_(9.0)
    ema = ModelEma(shadow_source, EmaConfig())
    checkpoint = tmp_path / "stage-one.ckpt"
    state = {f"model.{name}": tensor.detach().clone() for name, tensor in raw.state_dict().items()}
    torch.save(
        {"state_dict": state, EMA_CHECKPOINT_KEY: ema.state_dict()},
        checkpoint,
    )

    target = _tiny_model(seed=3)
    load_backbone_weights(target, checkpoint, reset_head=False)

    assert all(parameter.eq(9.0).all() for parameter in target.parameters())


def test_load_backbone_weights_rejects_any_uninitialised_parameter(tmp_path: Path):
    source = _tiny_model(seed=3)
    checkpoint = tmp_path / "incomplete.ckpt"
    # "semantic" contains "ema" and guards against a dangerously broad EMA
    # exception: it is an ordinary model parameter and must not be ignored.
    _save_lightning_checkpoint(checkpoint, source, omit="model.semantic_scale")

    with pytest.raises(RuntimeError, match=r"semantic_scale.*partially-loaded checkpoint"):
        load_backbone_weights(_tiny_model(seed=4), checkpoint, reset_head=False)


def test_lora_checkpoint_round_trips_when_adapter_is_injected_before_loading(
    tmp_path: Path,
) -> None:
    cfg = ModelConfig(
        arch="segformer_b0",
        tuning="lora",
        lora_targets=["q_proj"],
        lora_r=2,
    )
    source = apply_tuning(_tiny_model(seed=10), cfg)
    _fill_distinct(source)
    checkpoint = tmp_path / "lora-stage-one.ckpt"
    ema = ModelEma(source, EmaConfig())
    torch.save(
        {
            "state_dict": {
                f"model.{name}": tensor.detach().clone()
                for name, tensor in source.state_dict().items()
            },
            EMA_CHECKPOINT_KEY: ema.state_dict(),
        },
        checkpoint,
    )

    experiment = ExperimentConfig(name="test", model=cfg, space="unused", stages=[_stage()])
    target = prepare_stage_model(_tiny_model(seed=11), experiment, checkpoint, False)

    source_state = source.state_dict()
    assert set(target.state_dict()) == set(source_state)
    assert all(
        torch.equal(tensor, source_state[name]) for name, tensor in target.state_dict().items()
    )
    assert any("lora_A" in name for name, _ in target.named_parameters())


def test_lora_checkpoint_reset_changes_only_active_classifier(tmp_path: Path) -> None:
    cfg = ModelConfig(
        arch="segformer_b0",
        tuning="lora",
        lora_targets=["q_proj"],
        lora_r=2,
    )
    source = apply_tuning(_tiny_model(seed=12), cfg)
    _fill_distinct(source)
    checkpoint = tmp_path / "lora-reset.ckpt"
    ema = ModelEma(source, EmaConfig())
    torch.save({EMA_CHECKPOINT_KEY: ema.state_dict()}, checkpoint)

    experiment = ExperimentConfig(name="test", model=cfg, space="unused", stages=[_stage()])
    torch.manual_seed(14)
    target = prepare_stage_model(_tiny_model(seed=13), experiment, checkpoint, True)

    source_state = source.state_dict()
    changed = {
        name
        for name, tensor in target.state_dict().items()
        if not torch.equal(tensor, source_state[name])
    }
    assert changed == {
        name
        for name in source_state
        if ".modules_to_save.default.classifier.weight" in name
        or ".modules_to_save.default.classifier.bias" in name
    }


def test_raw_checkpoint_warm_starts_before_lora_injection(tmp_path: Path) -> None:
    source = _tiny_model(seed=15)
    _fill_distinct(source)
    checkpoint = tmp_path / "raw-warm-start.ckpt"
    _save_lightning_checkpoint(checkpoint, source)
    cfg = ModelConfig(
        arch="segformer_b0",
        tuning="lora",
        lora_targets=["q_proj"],
        lora_r=2,
    )
    experiment = ExperimentConfig(name="test", model=cfg, space="unused", stages=[_stage()])

    target = prepare_stage_model(_tiny_model(seed=16), experiment, checkpoint, False)
    target_state = target.state_dict()
    source_state = source.state_dict()
    assert torch.equal(
        target_state["model.backbone.attention.q_proj.base_layer.weight"],
        source_state["model.backbone.attention.q_proj.weight"],
    )
    assert torch.equal(
        target_state["model.decode_head.modules_to_save.default.classifier.weight"],
        source_state["model.decode_head.classifier.weight"],
    )
    assert any("lora_A" in name for name in target_state)


def test_reset_head_changes_only_classifier_after_loading(tmp_path: Path):
    source = _tiny_model(seed=5)
    _fill_distinct(source)
    source_state = {name: tensor.detach().clone() for name, tensor in source.state_dict().items()}
    checkpoint = tmp_path / "stage-one.ckpt"
    _save_lightning_checkpoint(checkpoint, source)
    target = _tiny_model(seed=6)

    torch.manual_seed(7)
    load_backbone_weights(target, checkpoint, reset_head=True)

    target_state = target.state_dict()
    changed = {
        name for name, tensor in target_state.items() if not torch.equal(tensor, source_state[name])
    }
    classifier = {
        name for name in source_state if ".classifier.weight" in name or ".classifier.bias" in name
    }
    backbone = {name for name in source_state if ".backbone." in name}

    assert changed == classifier
    assert classifier
    assert backbone
    assert all(torch.equal(target_state[name], source_state[name]) for name in backbone)


def test_reset_head_allows_only_classifier_shape_change_from_ema_checkpoint(
    tmp_path: Path,
) -> None:
    source = _tiny_model(seed=20, num_classes=3)
    _fill_distinct(source)
    checkpoint = tmp_path / "city-19-class.ckpt"
    ema = ModelEma(source, EmaConfig())
    torch.save({EMA_CHECKPOINT_KEY: ema.state_dict()}, checkpoint)
    target = _tiny_model(seed=21, num_classes=5)

    load_backbone_weights(target, checkpoint, reset_head=True)

    source_state = source.state_dict()
    target_state = target.state_dict()
    assert torch.equal(
        target_state["model.backbone.stem.weight"],
        source_state["model.backbone.stem.weight"],
    )
    assert torch.equal(
        target_state["model.backbone.attention.q_proj.weight"],
        source_state["model.backbone.attention.q_proj.weight"],
    )
    assert target_state["model.decode_head.classifier.weight"].shape[0] == 5
    assert not target_state["model.decode_head.classifier.weight"].eq(6.0).all()


def test_reset_head_includes_unchanged_zero_bias_owned_by_reset_classifier(
    tmp_path: Path,
) -> None:
    class _ZeroBiasClassifier(nn.Module):
        def __init__(self, classes: int) -> None:
            super().__init__()
            self.backbone = nn.Linear(4, 4)
            self.classifier = nn.Linear(4, classes)
            nn.init.zeros_(self.classifier.bias)

        def reset_head(self) -> None:
            nn.init.normal_(self.classifier.weight)
            nn.init.zeros_(self.classifier.bias)

    source = _ZeroBiasClassifier(3)
    checkpoint = tmp_path / "zero-bias-city.ckpt"
    torch.save(
        {"state_dict": {f"model.{name}": value for name, value in source.state_dict().items()}},
        checkpoint,
    )
    target = _ZeroBiasClassifier(5)

    load_backbone_weights(target, checkpoint, reset_head=True)

    assert torch.equal(target.backbone.weight, source.backbone.weight)
    assert target.classifier.weight.shape[0] == 5
    assert target.classifier.bias.shape[0] == 5
    assert torch.count_nonzero(target.classifier.bias) == 0


def test_reset_head_still_rejects_non_classifier_shape_change(tmp_path: Path) -> None:
    source = _tiny_model(seed=22)
    checkpoint = tmp_path / "bad-backbone.ckpt"
    state = {name: tensor.detach().clone() for name, tensor in source.state_dict().items()}
    state["model.backbone.stem.weight"] = torch.zeros(5, 3, 3, 3)
    torch.save(
        {"state_dict": {f"model.{name}": value for name, value in state.items()}},
        checkpoint,
    )

    with pytest.raises(RuntimeError, match="shape mismatches"):
        load_backbone_weights(_tiny_model(seed=23), checkpoint, reset_head=True)


# ---------------------------------------------------------------- strategy


@pytest.mark.parametrize(
    ("tuning", "expected"),
    [
        ("full", "ddp"),
        ("frozen", "ddp_find_unused_parameters_true"),
        ("lora", "ddp_find_unused_parameters_true"),
    ],
)
def test_strategy_for_multi_gpu_runs_depends_on_tuning(tuning: str, expected: str):
    assert _strategy(devices=[0, 1], tuning=tuning) == expected


@pytest.mark.parametrize("tuning", ["full", "frozen", "lora"])
def test_strategy_for_one_gpu_is_automatic(tuning: str):
    assert _strategy(devices=1, tuning=tuning) == "auto"


@pytest.mark.parametrize(
    ("devices", "expected"),
    [(1, False), ([0], False), (2, True), ([0, 1], True), ("auto", torch.cuda.device_count() > 1)],
)
def test_multi_device_detection_controls_sync_batchnorm(devices, expected: bool):
    assert curriculum._multi(devices) is expected


@pytest.mark.parametrize("is_global_zero", [True, False])
def test_save_final_checkpoint_uses_the_explicit_last_path_on_every_rank(
    tmp_path: Path, is_global_zero: bool
):
    class _FakeTrainer:
        def __init__(self) -> None:
            self.is_global_zero = is_global_zero
            self.calls: list[tuple[Path, bool]] = []

        def save_checkpoint(self, path: Path, *, weights_only: bool) -> None:
            self.calls.append((path, weights_only))

    trainer = _FakeTrainer()
    out_dir = tmp_path / "stage"

    checkpoint = curriculum._save_final_checkpoint(trainer, out_dir)

    expected = out_dir / "last.ckpt"
    assert checkpoint == expected
    assert trainer.calls == [(expected, False)]


def test_checkpoint_callbacks_honor_periodic_checkpoint_cadence(tmp_path: Path):
    best, periodic = _checkpoint_callbacks(tmp_path, TrainConfig(ckpt_every=37))

    assert best.monitor == "val/miou"
    assert best.mode == "max"
    assert best.save_top_k == 1
    assert periodic.monitor is None
    assert periodic._every_n_train_steps == 37
    assert periodic._save_on_train_epoch_end is False
    assert periodic.save_top_k == -1
    assert periodic.filename == "step-{step:08d}"
    assert periodic.state_key != best.state_key


def test_resume_checkpoint_requires_full_optimizer_scheduler_ema_and_stage_state(
    tmp_path: Path,
) -> None:
    train = TrainConfig(iters=100, ema_decay=0.9)
    checkpoint = tmp_path / "step-00000040.ckpt"
    state = {
        "global_step": 40,
        "optimizer_states": [{}],
        "lr_schedulers": [{}],
        "callbacks": {},
        EMA_CHECKPOINT_KEY: {"num_updates": 40},
        TRAINING_RESUME_KEY: {
            "schema_version": TRAINING_RESUME_SCHEMA_VERSION,
            "stage_name": "cityscapes",
        },
    }
    torch.save(state, checkpoint)

    assert (
        curriculum.validate_resume_checkpoint(
            checkpoint,
            stage=_stage(name="cityscapes"),
            train_cfg=train,
        )
        == 40
    )

    for missing, message in (
        ("optimizer_states", "optimizer state"),
        ("lr_schedulers", "scheduler state"),
        ("callbacks", "callback state"),
        (EMA_CHECKPOINT_KEY, "EMA state"),
    ):
        broken = tmp_path / f"missing-{missing}.ckpt"
        payload = dict(state)
        payload.pop(missing)
        torch.save(payload, broken)
        with pytest.raises(RuntimeError, match=message):
            curriculum.validate_resume_checkpoint(
                broken,
                stage=_stage(name="cityscapes"),
                train_cfg=train,
            )


def test_resume_checkpoint_rejects_cross_stage_and_misaligned_ema(tmp_path: Path) -> None:
    checkpoint = tmp_path / "step.ckpt"
    state = {
        "global_step": 20,
        "optimizer_states": [{}],
        "lr_schedulers": [{}],
        "callbacks": {},
        EMA_CHECKPOINT_KEY: {"num_updates": 19},
        TRAINING_RESUME_KEY: {
            "schema_version": TRAINING_RESUME_SCHEMA_VERSION,
            "stage_name": "railsem19",
        },
    }
    torch.save(state, checkpoint)
    with pytest.raises(RuntimeError, match="does not match configured stage"):
        curriculum.validate_resume_checkpoint(
            checkpoint,
            stage=_stage(name="cityscapes"),
            train_cfg=TrainConfig(iters=100),
        )
    state[TRAINING_RESUME_KEY]["stage_name"] = "cityscapes"
    torch.save(state, checkpoint)
    with pytest.raises(RuntimeError, match="EMA updates=19"):
        curriculum.validate_resume_checkpoint(
            checkpoint,
            stage=_stage(name="cityscapes"),
            train_cfg=TrainConfig(iters=100),
        )


def test_lightning_full_state_resume_continues_optimizer_scheduler_ema_and_step(
    tmp_path: Path,
) -> None:
    class _Dataset(Dataset):
        def __len__(self) -> int:
            return 8

        def __getitem__(self, index: int) -> dict[str, torch.Tensor]:
            generator = torch.Generator().manual_seed(index)
            return {
                "image": torch.rand(3, 8, 8, generator=generator),
                "mask": torch.randint(0, 3, (8, 8), generator=generator),
            }

    space = SimpleNamespace(
        name="resume-test",
        num_classes=3,
        ignore_index=255,
        names=("a", "b", "c"),
        thin_classes=(),
    )
    train_cfg = TrainConfig(
        iters=4,
        batch_size=1,
        accum=1,
        num_workers=0,
        precision="32-true",
        ema_decay=0.9,
        val_every=4,
        ckpt_every=1,
    )
    optim_cfg = OptimConfig(warmup_iters=0)

    def module(seed: int) -> SegLitModule:
        return SegLitModule(
            model=_tiny_model(seed, num_classes=3),
            loss_fn=SegmentationLoss(LossConfig(), 3, 255),
            space=space,
            optim_cfg=optim_cfg,
            train_cfg=train_cfg,
            eval_cfg=EvalConfig(sliding_window=False),
            stage_name="cityscapes",
        )

    loader = DataLoader(_Dataset(), batch_size=1)
    first_dir = tmp_path / "first"
    first_callback = curriculum.ModelCheckpoint(
        dirpath=first_dir,
        filename="step-{step:08d}",
        auto_insert_metric_name=False,
        every_n_train_steps=1,
        save_on_train_epoch_end=False,
        save_top_k=-1,
    )
    first = curriculum.L.Trainer(
        accelerator="cpu",
        devices=1,
        max_steps=2,
        callbacks=[first_callback],
        logger=False,
        enable_progress_bar=False,
        num_sanity_val_steps=0,
    )
    first.fit(module(1), train_dataloaders=loader)
    checkpoint = first_dir / "step-00000002.ckpt"
    assert checkpoint.is_file()
    saved = torch.load(checkpoint, map_location="cpu", weights_only=False)
    assert saved["global_step"] == 2
    assert saved[EMA_CHECKPOINT_KEY]["num_updates"] == 2

    resumed_module = module(99)
    resumed = curriculum.L.Trainer(
        accelerator="cpu",
        devices=1,
        max_steps=4,
        logger=False,
        enable_checkpointing=False,
        enable_progress_bar=False,
        num_sanity_val_steps=0,
    )
    resumed.fit(
        resumed_module,
        train_dataloaders=loader,
        ckpt_path=str(checkpoint),
        weights_only=False,
    )

    assert resumed.global_step == 4
    assert resumed_module.ema is not None
    assert resumed_module.ema.num_updates == 4
    optimizer_steps = {
        int(value["step"].item())
        for value in resumed.optimizers[0].state.values()
        if "step" in value
    }
    assert optimizer_steps == {4}
    assert resumed.lr_scheduler_configs[0].scheduler.last_epoch == 4


# -------------------------------------------------------------- integration


@pytest.mark.gpu
@pytest.mark.slow
def test_real_two_stage_curriculum_threads_the_trained_backbone(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    cityscapes_root: Path,
    railsem19_root: Path,
    taxonomy_root: Path,
):
    """Train Cityscapes -> RailSem19 and inspect the stage boundary exactly.

    The wrapper around ``load_backbone_weights`` delegates to the production
    implementation.  It records the fresh stage-two tensor, the tensor stored
    by stage one, and the tensor immediately after loading.  Thus the assertions
    fail if the checkpoint path is not threaded, if loading is a no-op, or if the
    second stage silently starts from the original pretrained backbone.
    """
    if not torch.cuda.is_available():
        pytest.skip("the real curriculum integration test needs one CUDA GPU")

    split_file = Path(__file__).resolve().parents[1] / "splits" / "railsem19_seed0.json"
    cfg = ExperimentConfig(
        name="test_real_two_stage_transfer",
        model=ModelConfig(
            arch="segformer_b0",
            checkpoint="nvidia/mit-b0",
            tuning="full",
        ),
        space="rail_union",
        taxonomy_root=str(taxonomy_root),
        output_root=str(tmp_path / "runs"),
        optim=OptimConfig(
            backbone_lr=1e-4,
            head_lr_mult=1.0,
            weight_decay=0.0,
            warmup_iters=2,
            grad_clip=None,
        ),
        train=TrainConfig(
            iters=20,
            batch_size=1,
            accum=1,
            num_workers=0,
            precision="bf16-mixed",
            ema_decay=0.9,
            val_every=20,
            ckpt_every=20,
            seed=123,
            devices=1,
        ),
        eval=EvalConfig(
            sliding_window=False,
            window=(256, 256),
            stride=(256, 256),
            batch_size=1,
            save_confusion=False,
        ),
        loss=LossSpec(),
        aug=AugConfigSpec(
            crop=(256, 256),
            scale_min=1.0,
            scale_max=1.0,
            hflip_p=0.0,
            color_jitter_p=0.0,
        ),
        stages=[
            StageConfig(
                name="cityscapes",
                data=[DataConfig(name="cityscapes", root=str(cityscapes_root), limit=2)],
                init_from="pretrained",
                iters=20,
            ),
            StageConfig(
                name="railsem19",
                data=[
                    DataConfig(
                        name="railsem19",
                        root=str(railsem19_root),
                        split_file=str(split_file),
                        limit=2,
                    )
                ],
                init_from="previous",
                iters=20,
                lr_scale=0.1,
            ),
        ],
    )

    real_load = curriculum.load_backbone_weights
    transfer: dict[str, object] = {}
    tensor_suffix = "segformer.stages.0.patch_embeddings.proj.weight"

    def capture_transfer(
        model: nn.Module,
        checkpoint: Path,
        reset_head: bool,
        *,
        checkpoint_state: dict[str, object] | None = None,
    ) -> None:
        matches = [
            (name, parameter)
            for name, parameter in model.named_parameters()
            if name.endswith(tensor_suffix)
        ]
        assert len(matches) == 1
        name, parameter = matches[0]
        transfer["fresh_stage_two"] = parameter.detach().cpu().clone()

        saved = torch.load(checkpoint, map_location="cpu", weights_only=False)
        transfer["stage_one_raw"] = saved["state_dict"][f"model.{name}"].detach().clone()
        transfer["stage_one_checkpoint"] = (
            saved[EMA_CHECKPOINT_KEY]["params"][name].detach().clone()
        )
        transfer["stage_one_has_ema"] = EMA_CHECKPOINT_KEY in saved
        transfer["checkpoint_path"] = Path(checkpoint)

        real_load(
            model,
            checkpoint,
            reset_head,
            checkpoint_state=checkpoint_state,
        )
        loaded = dict(model.named_parameters())[name]
        transfer["loaded_stage_two"] = loaded.detach().cpu().clone()
        transfer["parameter_name"] = name

    monkeypatch.setattr(curriculum, "load_backbone_weights", capture_transfer)
    results = curriculum.run_curriculum(cfg, devices=1)

    assert len(results) == 2
    assert all(result.checkpoint.is_file() for result in results)
    assert all(result.checkpoint.name == "last.ckpt" for result in results)
    assert all(result.results_path.is_file() for result in results)
    for result in results:
        record = json.loads(result.results_path.read_text())
        assert record["config_hash"] == config_hash(to_dict(cfg))
        assert record["config"] == to_dict(cfg)
        assert record["env"]["input_normalization"]["source"]
    for stage, result in zip(cfg.stages, results, strict=True):
        assert (result.checkpoint.parent / f"step-{stage.iters:08d}.ckpt").is_file()
        checkpoint = torch.load(result.checkpoint, map_location="cpu", weights_only=False)
        assert checkpoint["global_step"] == stage.iters
        assert checkpoint[EMA_CHECKPOINT_KEY]["num_updates"] == stage.iters
    assert transfer["checkpoint_path"] == results[0].checkpoint
    assert transfer["stage_one_has_ema"]
    assert torch.equal(transfer["loaded_stage_two"], transfer["stage_one_checkpoint"])
    assert not torch.equal(transfer["loaded_stage_two"], transfer["stage_one_raw"])
    assert not torch.equal(transfer["fresh_stage_two"], transfer["loaded_stage_two"])

    stage_two_state = torch.load(results[1].checkpoint, map_location="cpu", weights_only=False)[
        "state_dict"
    ]
    stage_two_final = stage_two_state[f"model.{transfer['parameter_name']}"]
    assert not torch.equal(stage_two_final, transfer["loaded_stage_two"])

    # Re-run the exact stage-one validation externally from the persisted EMA.
    # This closes the loop between Lightning validation, checkpoint save, and
    # the standalone evaluator instead of comparing unrelated sample sizes.
    config_path = tmp_path / "resolved.yaml"
    config_path.write_text(yaml.safe_dump(to_dict(cfg)))
    eval_path = tmp_path / "ema-eval.json"
    assert (
        eval_module.main(
            [
                str(config_path),
                "--ckpt",
                str(results[0].checkpoint),
                "--stage",
                "cityscapes",
                "--ema",
                "--out",
                str(eval_path),
                "--device",
                "cuda:0",
            ]
        )
        == 0
    )
    eval_record = json.loads(eval_path.read_text())
    assert eval_record["metrics"]["miou"] == pytest.approx(results[0].metrics["miou"], abs=1e-7)
