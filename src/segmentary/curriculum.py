"""Curriculum staging: run stages in order and thread checkpoints between them.

Staging rules are explicit here rather than implied by config:

  init_from: pretrained   start from the architecture's pretrained backbone
  init_from: previous     start from the previous stage's final weights
  init_from: <path>       start from a specific checkpoint

  reset_head: true        re-initialise the unified classifier for this stage;
                          the backbone still carries over
  freeze: <spec>          freeze matching parameters for this stage
  lr_scale                multiplies the stage's learning rates; later stages
                          conventionally use 0.1
  iters                   per-stage schedule length; later stages are shorter

Each stage writes its own results.json under runs/<experiment>/<stage>/, so a
three-stage curriculum produces three comparable records rather than one summary
that hides where the gain came from.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from pathlib import Path

import lightning as L
import torch
from lightning.pytorch.callbacks import ModelCheckpoint
from lightning.pytorch.loggers import TensorBoardLogger

from .checkpoints import (
    TRAINING_RESUME_KEY,
    TRAINING_RESUME_SCHEMA_VERSION,
    checkpoint_uses_lora,
    read_checkpoint,
)
from .config import ExperimentConfig, StageConfig, TrainConfig, config_hash, to_dict
from .data.base import SegDataset
from .data.loaders import (
    build_train_loader,
    build_val_loader,
    input_normalization,
    load_data_mapping,
    validation_active_mask,
)
from .data.mixed import MixedDataset
from .engine.ema import EMA_CHECKPOINT_KEY, EmaConfig, ModelEma
from .engine.losses import LossConfig, SegmentationLoss
from .engine.module import SegLitModule
from .engine.query_loss import QuerySegmentationLoss
from .models.factory import build_model
from .models.tuning import apply_tuning, count_trainable
from .tasks import (
    validate_canonical_active,
    validate_task_configuration,
    validate_task_space,
)
from .taxonomy import LabelSpace, load_space
from .utils.provenance import collect_env, git_sha
from .utils.results import RunRecord, RunTimer, write_results


@dataclass
class StageResult:
    name: str
    checkpoint: Path
    metrics: dict
    results_path: Path
    wall_clock_s: float


def validate_training_contract(cfg: ExperimentConfig) -> None:
    """Reject model/objective task mismatches before loading data or a model."""
    validate_task_configuration(cfg)
    if cfg.loss.query is None and any(
        term.kind == "kl_distillation" for term in cfg.loss.resolved_terms()
    ):
        raise ValueError(
            "loss.terms includes kl_distillation, but the standard curriculum has no "
            "configured teacher-logit provider. Use SegmentationLoss directly with "
            "teacher_logits, or add a typed teacher runtime before launching this run."
        )


def validate_data_task_contract(
    cfg: ExperimentConfig,
    space: LabelSpace,
) -> None:
    """Validate taxonomy and every configured dataset mapping before training."""
    validate_task_space(cfg.loss.task, space)
    if cfg.loss.task != "binary":
        return
    for stage in cfg.stages:
        for data in stage.data:
            mapping = load_data_mapping(data, space, cfg.taxonomy_root)
            active = torch.from_numpy(mapping.active_mask())
            validate_canonical_active(
                active,
                cfg.loss.task,
                where=f"stage {stage.name!r} dataset {data.name!r} active mask",
            )


def _save_final_checkpoint(trainer: L.Trainer, out_dir: Path) -> Path:
    """Persist the fixed-step state and return its unambiguous hand-off path."""
    final_checkpoint = out_dir / "last.ckpt"
    # Lightning 2.6's ModelCheckpoint(save_last=True, save_top_k=1) can leave
    # `last.ckpt` at the last top-k improvement instead of the final optimizer
    # step. Trainer.save_checkpoint must be called on every rank: distributed
    # strategies may participate in saving, and Lightning supplies the barrier.
    trainer.save_checkpoint(final_checkpoint, weights_only=False)
    return final_checkpoint


def validate_resume_checkpoint(
    checkpoint: Path,
    *,
    stage: StageConfig,
    train_cfg: TrainConfig,
) -> int:
    """Require a complete, compatible Lightning training state before resuming."""
    if not checkpoint.is_file():
        raise FileNotFoundError(f"resume checkpoint not found: {checkpoint}")
    state = read_checkpoint(checkpoint)
    step = state.get("global_step")
    if isinstance(step, bool) or not isinstance(step, int) or not 0 < step <= train_cfg.iters:
        raise RuntimeError(
            f"resume checkpoint {checkpoint} has global_step={step!r}; expected an integer "
            f"in [1, {train_cfg.iters}]"
        )
    metadata = state.get(TRAINING_RESUME_KEY)
    if not isinstance(metadata, dict):
        raise RuntimeError(
            f"resume checkpoint {checkpoint} has no Segmentary full-state resume metadata"
        )
    if metadata.get("schema_version") != TRAINING_RESUME_SCHEMA_VERSION:
        raise RuntimeError(
            f"resume checkpoint {checkpoint} uses unsupported resume schema "
            f"{metadata.get('schema_version')!r}"
        )
    if metadata.get("stage_name") != stage.name:
        raise RuntimeError(
            f"resume checkpoint stage {metadata.get('stage_name')!r} does not match "
            f"configured stage {stage.name!r}"
        )
    optimizer_states = state.get("optimizer_states")
    if not isinstance(optimizer_states, list) or not optimizer_states:
        raise RuntimeError(f"resume checkpoint {checkpoint} has no optimizer state")
    schedulers = state.get("lr_schedulers")
    if not isinstance(schedulers, list) or not schedulers:
        raise RuntimeError(f"resume checkpoint {checkpoint} has no scheduler state")
    if not isinstance(state.get("callbacks"), dict):
        raise RuntimeError(f"resume checkpoint {checkpoint} has no callback state")
    if train_cfg.ema_decay is not None:
        ema = state.get(EMA_CHECKPOINT_KEY)
        if not isinstance(ema, dict):
            raise RuntimeError(f"resume checkpoint {checkpoint} has no EMA state")
        if ema.get("num_updates") != step:
            raise RuntimeError(
                f"resume checkpoint {checkpoint} EMA updates={ema.get('num_updates')!r}, "
                f"but global_step={step}"
            )
    return step


def _checkpoint_callbacks(out_dir: Path, train_cfg: TrainConfig) -> list[ModelCheckpoint]:
    """Keep the best validation model and explicit periodic recovery snapshots."""
    best = ModelCheckpoint(
        dirpath=out_dir,
        filename="best",
        monitor="val/miou",
        mode="max",
        save_last=True,
        save_top_k=1,
    )
    periodic = ModelCheckpoint(
        dirpath=out_dir,
        filename="step-{step:08d}",
        auto_insert_metric_name=False,
        every_n_train_steps=train_cfg.ckpt_every,
        save_on_train_epoch_end=False,
        save_last=False,
        save_top_k=-1,
    )
    return [best, periodic]


def _tensorboard_logger(out_dir: Path) -> TensorBoardLogger:
    """Return the stable, explicit TensorBoard destination for one stage.

    Lightning's implicit logger chooses ``lightning_logs/version_N``. That is
    awkward for unattended campaigns because a retry silently moves to a new
    directory. A fixed stage-local directory lets TensorBoard merge event-file
    rollovers and lets the read-only progress dashboard find the current run
    without guessing a version number.
    """
    return TensorBoardLogger(
        save_dir=out_dir,
        name="tensorboard",
        version="",
        default_hp_metric=False,
    )


def resolve_init(stage: StageConfig, previous: Path | None) -> Path | None:
    """Turn a stage's ``init_from`` into a concrete checkpoint path, or None."""
    if stage.init_from == "pretrained":
        return None
    if stage.init_from == "previous":
        if previous is None:
            raise ValueError(
                f"stage {stage.name!r} says init_from: previous but no earlier stage "
                f"produced a checkpoint"
            )
        path = Path(previous)
    else:
        path = Path(stage.init_from)
    if not path.is_file():
        raise FileNotFoundError(f"stage {stage.name!r}: init_from checkpoint not found: {path}")
    return path


def apply_freeze(model: torch.nn.Module, spec: str | None) -> int:
    """Freeze parameters whose qualified name contains ``spec``. Returns the count."""
    if not spec:
        return 0
    frozen = 0
    for name, param in model.named_parameters():
        if spec in name:
            param.requires_grad_(False)
            frozen += 1
    if frozen == 0:
        raise ValueError(
            f"freeze spec {spec!r} matched no parameters. A freeze that silently does "
            f"nothing would make this arm identical to its unfrozen baseline."
        )
    return frozen


def load_backbone_weights(
    model: torch.nn.Module,
    ckpt: Path,
    reset_head: bool,
    *,
    checkpoint_state: dict | None = None,
) -> None:
    """Load the weights a previous stage evaluated, then optionally reset its head.

    New checkpoints carry a separate EMA shadow because it is not an nn.Module.
    That shadow is the model training validates and reports, so it is also the
    correct state to hand to the next stage.  Raw loading remains as an explicit
    compatibility path for legacy checkpoints produced before EMA persistence.
    """
    state = read_checkpoint(ckpt) if checkpoint_state is None else checkpoint_state
    if reset_head:
        # A standard source taxonomy and a unified target taxonomy legitimately
        # have different classifier shapes. Identify exactly the tensors owned
        # by reset_head from its real mutation, retain the freshly reset target
        # values for those tensors, and require every other tensor to load with
        # an exact name and shape. This is a strict feature/decoder warm start,
        # never a broad partial-load escape hatch.
        before_reset = {
            name: tensor.detach().clone() for name, tensor in model.state_dict().items()
        }
        model.reset_head()
        target_state = model.state_dict()
        changed_reset_keys = {
            name
            for name, tensor in target_state.items()
            if name in before_reset and not torch.equal(tensor, before_reset[name])
        }
        if not changed_reset_keys:
            raise RuntimeError(f"reset_head changed no checkpoint tensors while loading {ckpt}")
        # A classifier reset can legitimately leave one tensor numerically
        # unchanged (for example a zero-initialised bias). Once any tensor in a
        # leaf module proves that reset_head touched that classifier, treat all
        # state owned directly by that same leaf module as reset state. This
        # keeps the exception exact without depending on random initial values.
        reset_modules = {name.rpartition(".")[0] for name in changed_reset_keys}
        reset_keys = {name for name in target_state if name.rpartition(".")[0] in reset_modules}

        if EMA_CHECKPOINT_KEY in state:
            ema_state = state[EMA_CHECKPOINT_KEY]
            if not isinstance(ema_state, dict):
                raise RuntimeError(f"invalid EMA state in {ckpt}: expected a mapping")
            params = ema_state.get("params")
            buffers = ema_state.get("buffers")
            if not isinstance(params, dict) or not isinstance(buffers, dict):
                raise RuntimeError(
                    f"invalid EMA state in {ckpt}: params and buffers must be mappings"
                )
            source_state = {**params, **buffers}
        else:
            raw = state.get("state_dict", state)
            if not isinstance(raw, dict):
                raise RuntimeError(f"invalid checkpoint state in {ckpt}: expected a mapping")
            source_state = {
                key[len("model.") :] if key.startswith("model.") else key: value
                for key, value in raw.items()
            }

        unexpected = sorted(set(source_state) - set(target_state))
        missing_non_head = sorted(set(target_state) - set(source_state) - reset_keys)
        bad_shapes = sorted(
            name
            for name in set(source_state) & set(target_state) - reset_keys
            if getattr(source_state[name], "shape", None) != target_state[name].shape
        )
        if unexpected or missing_non_head or bad_shapes:
            raise RuntimeError(
                f"loading {ckpt} with reset_head did not exactly match non-classifier "
                f"weights: {len(missing_non_head)} missing (first {missing_non_head[:5]}), "
                f"{len(unexpected)} unexpected (first {unexpected[:5]}), "
                f"{len(bad_shapes)} shape mismatches (first {bad_shapes[:5]})."
            )
        filtered = {name: value for name, value in source_state.items() if name not in reset_keys}
        missing, unexpected_after = model.load_state_dict(filtered, strict=False)
        if set(missing) != reset_keys or unexpected_after:
            raise RuntimeError(
                f"loading {ckpt} with reset_head produced an unexpected partial load: "
                f"missing={missing[:5]}, unexpected={unexpected_after[:5]}"
            )
        return

    if EMA_CHECKPOINT_KEY in state:
        ema = ModelEma(model, EmaConfig())
        try:
            ema.load_state_dict(state[EMA_CHECKPOINT_KEY])
            ema.copy_to(model)
        except (TypeError, ValueError) as exc:
            raise RuntimeError(f"invalid EMA state in {ckpt}: {exc}") from exc
    else:
        sd = state.get("state_dict", state)
        # Lightning prefixes everything with "model."; strip it so the raw wrapper loads.
        sd = {k[len("model.") :] if k.startswith("model.") else k: v for k, v in sd.items()}
        missing, unexpected = model.load_state_dict(sd, strict=False)
        if missing or unexpected:
            raise RuntimeError(
                f"loading {ckpt} did not exactly match the model: {len(missing)} "
                f"uninitialised (first {missing[:5]}), {len(unexpected)} unexpected "
                f"(first {unexpected[:5]}). Refusing a partially-loaded checkpoint."
            )


def prepare_stage_model(
    model: torch.nn.Module,
    cfg: ExperimentConfig,
    init_ckpt: Path | None,
    reset_head: bool,
) -> torch.nn.Module:
    """Apply tuning and a raw/adapted warm-start in the only compatible order."""
    checkpoint_state = read_checkpoint(init_ckpt) if init_ckpt is not None else None
    adapted_checkpoint = (
        checkpoint_uses_lora(checkpoint_state) if checkpoint_state is not None else False
    )
    if cfg.model.tuning == "lora" and (init_ckpt is None or adapted_checkpoint):
        model = apply_tuning(model, cfg.model)
    if init_ckpt is not None:
        load_backbone_weights(
            model,
            init_ckpt,
            reset_head,
            checkpoint_state=checkpoint_state,
        )
    elif reset_head:
        model.reset_head()
    if cfg.model.tuning != "lora" or (init_ckpt is not None and not adapted_checkpoint):
        model = apply_tuning(model, cfg.model)
    return model


def run_stage(
    cfg: ExperimentConfig,
    stage: StageConfig,
    space: LabelSpace,
    previous: Path | None,
    out_root: Path,
    devices,
    provenance_root: Path,
    resume_checkpoint: Path | None = None,
) -> StageResult:
    """Train one stage and return its checkpoint plus metrics."""
    validate_training_contract(cfg)
    validate_task_space(cfg.loss.task, space)
    out_dir = out_root / stage.name
    out_dir.mkdir(parents=True, exist_ok=True)

    train_cfg = replace(cfg.train, iters=stage.iters or cfg.train.iters)
    # The scheduler requires warmup < total; a literal one-step smoke therefore uses zero.
    optim_cfg = replace(
        cfg.optim,
        backbone_lr=cfg.optim.backbone_lr * stage.lr_scale,
        warmup_iters=min(
            cfg.optim.warmup_iters,
            max(1, train_cfg.iters // 10),
            train_cfg.iters - 1,
        ),
    )

    model = build_model(cfg.model, space.num_classes)
    if cfg.loss.query is not None and not getattr(model, "supports_query_objective", False):
        raise ValueError(
            f"loss.query requires raw QueryOutput, but {type(model).__name__} is a dense model"
        )
    # Hugging Face from_pretrained() returns eval-mode modules. Lightning 2.6
    # intentionally preserves those per-module modes at fit start, which would
    # otherwise disable dropout/stochastic depth for the whole experiment.
    model.train()
    init_ckpt = resolve_init(stage, previous)
    model = prepare_stage_model(model, cfg, init_ckpt, stage.reset_head)
    n_frozen = apply_freeze(model, stage.freeze)
    trainable, total = count_trainable(model)

    train_loader = build_train_loader(
        stage, space, cfg.taxonomy_root, cfg.aug, train_cfg, model=model
    )
    val_loader, val_ds = build_val_loader(
        stage,
        space,
        cfg.taxonomy_root,
        cfg.aug,
        train_cfg,
        batch_size=cfg.eval.batch_size,
        model=model,
    )

    loss_fn = (
        QuerySegmentationLoss(cfg.loss.query, space.num_classes, space.ignore_index)
        if cfg.loss.query is not None
        else SegmentationLoss(
            LossConfig.from_spec(cfg.loss),
            int(getattr(model, "output_channels", space.num_classes)),
            space.ignore_index,
        )
    )

    lit = SegLitModule(
        model=model,
        loss_fn=loss_fn,
        space=space,
        optim_cfg=optim_cfg,
        train_cfg=train_cfg,
        eval_cfg=cfg.eval,
        eval_active=validation_active_mask(stage, space, cfg.taxonomy_root),
        stage_name=stage.name,
    )

    resume_step: int | None = None
    if resume_checkpoint is not None:
        resume_checkpoint = resume_checkpoint.expanduser().resolve()
        resume_step = validate_resume_checkpoint(
            resume_checkpoint,
            stage=stage,
            train_cfg=train_cfg,
        )

    checkpoint_callbacks = _checkpoint_callbacks(out_dir, train_cfg)
    tensorboard_logger = _tensorboard_logger(out_dir)
    trainer = L.Trainer(
        default_root_dir=out_dir,
        max_steps=train_cfg.iters,
        devices=devices,
        accelerator="gpu" if torch.cuda.is_available() else "cpu",
        # find_unused_parameters costs an extra autograd-graph traversal every
        # step, so only pay for it when a tuning mode actually leaves parameters
        # out of the backward pass (frozen backbone, or LoRA's inert base weights).
        strategy=_strategy(devices, cfg.model.tuning),
        # The published SegFormer decoder uses SyncBN. Rank-local BatchNorm would
        # let each validation rank score a slightly different model and only
        # rank 0's running statistics would survive in the EMA checkpoint.
        sync_batchnorm=_multi(devices),
        precision=train_cfg.precision,
        accumulate_grad_batches=train_cfg.accum,
        gradient_clip_val=optim_cfg.grad_clip,
        val_check_interval=train_cfg.val_every,
        check_val_every_n_epoch=None,  # iteration-based validation
        callbacks=checkpoint_callbacks,
        logger=tensorboard_logger,
        log_every_n_steps=min(50, train_cfg.iters),
        num_sanity_val_steps=1,
        enable_progress_bar=True,
    )

    print(
        f"\n=== stage {stage.name}: {train_cfg.iters} iters, "
        f"init={stage.init_from}, reset_head={stage.reset_head}, "
        f"lr={optim_cfg.backbone_lr:.2e}, trainable={trainable / 1e6:.1f}M/{total / 1e6:.1f}M"
        f"{f', frozen {n_frozen} tensors' if n_frozen else ''} ==="
    )
    print(f"TensorBoard: tensorboard --logdir {out_root}")
    if resume_checkpoint is not None:
        print(f"Resuming stage {stage.name} from step {resume_step}: {resume_checkpoint}")

    with RunTimer() as timer:
        trainer.fit(
            lit,
            train_dataloaders=train_loader,
            val_dataloaders=val_loader,
            ckpt_path=str(resume_checkpoint) if resume_checkpoint is not None else None,
            weights_only=False if resume_checkpoint is not None else None,
        )
        final_checkpoint = _save_final_checkpoint(trainer, out_dir)

    metrics = lit.latest_metrics() if trainer.is_global_zero else {}
    sha, dirty = git_sha(provenance_root)
    record_config = to_dict(cfg)
    record_env = collect_env()
    record_env["input_normalization"] = input_normalization(model)
    record = RunRecord(
        name=cfg.name,
        stage=stage.name,
        config_hash=config_hash(record_config),
        git_sha=sha,
        git_dirty=dirty,
        seed=train_cfg.seed,
        started_at=timer.started_at,
        finished_at=timer.finished_at,
        wall_clock_s=timer.wall_clock_s,
        peak_vram_bytes=timer.peak_vram_bytes(),
        metrics=metrics,
        config=record_config,
        env=record_env,
        dataset_sizes={
            "train": len(train_loader.dataset),
            "val": len(val_ds),
            # Flat "train:<name>" keys rather than a nested dict: RunRecord types
            # this field dict[str, int] and the table generator reads it as one.
            **{f"train:{d.name}": len(d) for d in _members(train_loader.dataset)},
        },
        notes=f"stage {stage.name} of curriculum {cfg.name}",
    )
    results_path = out_dir / "results.json"
    if trainer.is_global_zero:
        write_results(results_path, record)

    return StageResult(stage.name, final_checkpoint, metrics, results_path, timer.wall_clock_s)


def run_curriculum(
    cfg: ExperimentConfig,
    devices="auto",
    provenance_root: str | Path | None = None,
    resume_checkpoint: str | Path | None = None,
) -> list[StageResult]:
    """Run every stage in order, threading each stage's checkpoint into the next."""
    validate_training_contract(cfg)
    space = load_space(cfg.taxonomy_root, cfg.space)
    validate_data_task_contract(cfg, space)
    out_root = Path(cfg.output_root) / f"{cfg.name}_seed{cfg.train.seed}"
    out_root.mkdir(parents=True, exist_ok=True)
    source_root = Path(provenance_root) if provenance_root is not None else Path.cwd()

    results: list[StageResult] = []
    previous: Path | None = None
    start_index = 0
    resume_path: Path | None = None
    if resume_checkpoint is not None:
        resume_path = Path(resume_checkpoint).expanduser().resolve()
        state = read_checkpoint(resume_path)
        metadata = state.get(TRAINING_RESUME_KEY)
        stage_name = metadata.get("stage_name") if isinstance(metadata, dict) else None
        matches = [index for index, stage in enumerate(cfg.stages) if stage.name == stage_name]
        if len(matches) != 1:
            raise RuntimeError(
                f"resume checkpoint names stage {stage_name!r}, which matches "
                f"{len(matches)} configured stages"
            )
        start_index = matches[0]
        expected_parent = (out_root / cfg.stages[start_index].name).resolve()
        if resume_path.parent != expected_parent:
            raise RuntimeError(
                f"resume checkpoint must belong to this run's stage directory "
                f"{expected_parent}, got {resume_path.parent}"
            )
        if start_index:
            previous = out_root / cfg.stages[start_index - 1].name / "last.ckpt"
            if not previous.is_file():
                raise FileNotFoundError(
                    f"cannot resume stage {stage_name!r}: previous stage checkpoint "
                    f"is missing: {previous}"
                )

    for index, stage in enumerate(cfg.stages[start_index:], start=start_index):
        result = run_stage(
            cfg,
            stage,
            space,
            previous,
            out_root,
            devices,
            source_root,
            resume_checkpoint=resume_path if index == start_index else None,
        )
        results.append(result)
        previous = result.checkpoint
        # Only rank 0 holds real metrics (the others return {}), so only rank 0
        # prints -- otherwise every stage reports itself once per GPU, half of
        # them as NaN.
        if _is_rank_zero():
            miou = result.metrics.get("miou")
            shown = "n/a" if miou is None else f"{miou:.4f}"
            print(
                f"=== stage {stage.name} done in {result.wall_clock_s / 60:.1f} min, "
                f"mIoU={shown} -> {result.checkpoint}"
            )
    return results


def _members(dataset: SegDataset | MixedDataset) -> list[SegDataset]:
    """The datasets a train loader actually draws from (a mix has several)."""
    return list(getattr(dataset, "datasets", [dataset]))


def _is_rank_zero() -> bool:
    return int(os.environ.get("LOCAL_RANK", 0)) == 0 and int(os.environ.get("NODE_RANK", 0)) == 0


def _multi(devices) -> bool:
    if devices == "auto":
        return torch.cuda.device_count() > 1
    if isinstance(devices, int):
        return devices > 1
    return len(devices) > 1 if hasattr(devices, "__len__") else False


def _strategy(devices, tuning: str) -> str:
    if not _multi(devices):
        return "auto"
    return "ddp_find_unused_parameters_true" if tuning in ("frozen", "lora") else "ddp"
