"""The LightningModule. Iteration-based, dataset-aware, EMA-evaluated.

Deliberately thin: every non-trivial decision lives in a tested module (losses,
metrics, optim, ema, inference) and this file only wires them together in the
right order. If you are debugging a number, the bug is more likely in one of
those than here.

Two things worth knowing before editing:

  * Training is driven by ``max_steps``, never epochs. Datasets can contain very
    different numbers of samples, so epoch budgets would make stages incomparable.
  * Validation runs at native resolution through sliding-window inference, using
    EMA weights when EMA is enabled. Native validation images may be larger than
    training crops; scoring only on crops would report a different task.
"""

from __future__ import annotations

import warnings
from time import monotonic
from typing import Any

import lightning as L
import torch
from torch import Tensor

from ..config import EvalConfig, OptimConfig, TrainConfig
from ..models.outputs import SegmentationOutput
from ..tasks import active_for_loss, validate_canonical_active, validate_task_space
from ..taxonomy import LabelSpace
from .boundary import BoundaryConfig, BoundaryF1
from .ema import EMA_CHECKPOINT_KEY, EmaConfig, ModelEma
from .inference import InferenceConfig, inference, prediction_from_inference
from .losses import SegmentationLoss
from .metrics import ConfusionMatrix
from .optim import build_optimizer, build_scheduler, describe_param_groups
from .query_loss import QuerySegmentationLoss, query_training_objective


def dense_training_objective(
    model: torch.nn.Module,
    loss_fn: SegmentationLoss,
    pixel_values: Tensor,
    target: Tensor,
    active: Tensor | None = None,
) -> tuple[Tensor, dict[str, Tensor]]:
    """Evaluate the primary dense prediction and every named auxiliary head.

    ``SegmentationModel`` supplies ``forward_output`` for every supported model.
    The tensor fallback keeps small third-party/test modules source-compatible,
    but any non-tensor/non-``SegmentationOutput`` value is rejected rather than
    guessed. Query predictions require a query objective and therefore fail
    explicitly in this dense-objective engine. A mask-classification wrapper's
    public dense collapse is the one deliberate exception, preserving the
    separately warned legacy ablation.
    """
    declared_task = getattr(model, "task", None)
    if declared_task is not None and declared_task != loss_fn.cfg.task:
        raise ValueError(
            f"model task {declared_task!r} does not match dense objective task {loss_fn.cfg.task!r}"
        )
    # Mask-classification wrappers deliberately expose two representations:
    # public ``forward`` is the legacy dense-collapse ablation, while
    # ``forward_output`` retains raw queries for Hungarian training. The
    # selected objective decides which one is evaluated; all other models use
    # their rich output so an accidental QueryOutput still fails below.
    if getattr(model, "supports_query_objective", False):
        raw_output = model(pixel_values)
    else:
        forward_output = getattr(model, "forward_output", None)
        raw_output = (
            forward_output(pixel_values) if callable(forward_output) else model(pixel_values)
        )
    if isinstance(raw_output, Tensor):
        output = SegmentationOutput(dense_logits=raw_output)
    elif isinstance(raw_output, SegmentationOutput):
        output = raw_output
    else:
        raise TypeError(
            f"{type(model).__name__} training forward returned "
            f"{type(raw_output).__name__}; expected a Tensor or SegmentationOutput"
        )
    if output.dense_logits is None:
        raise ValueError(
            f"{type(model).__name__} returned query predictions, but the configured "
            "SegmentationLoss is a dense objective. Configure a query-matching objective "
            "before training this model."
        )

    loss_active = active_for_loss(
        active,
        loss_fn.cfg.task,
        batch_size=int(output.dense_logits.shape[0]),
    )
    total, primary_parts = loss_fn(output.dense_logits, target, active=loss_active)
    parts = dict(primary_parts)
    for auxiliary in output.auxiliary_dense:
        auxiliary_loss, auxiliary_parts = loss_fn(
            auxiliary.logits,
            target,
            active=loss_active,
        )
        weighted = auxiliary.loss_weight * auxiliary_loss
        total = total + weighted
        for term_name, value in auxiliary_parts.items():
            if term_name != "total":
                parts[f"aux/{auxiliary.name}/{term_name}"] = value
        parts[f"aux/{auxiliary.name}/loss"] = auxiliary_loss.detach()
        parts[f"aux/{auxiliary.name}/weighted_loss"] = weighted.detach()
    parts["total"] = total.detach()
    return total, parts


class SegLitModule(L.LightningModule):
    """Trains one stage of a curriculum.

    Args:
        model: any wrapper satisfying the SegmentationModel contract, i.e.
            ``forward(pixel_values) -> (N, C, H, W)`` at input resolution.
        loss_fn: configured SegmentationLoss over the canonical space.
        space: the canonical label space, used for class names in logs.
        optim_cfg / train_cfg / eval_cfg: validated dataclass configs.
        eval_active: (C,) bool mask of classes the validation dataset supervises.
            Classes outside it are reported NaN instead of a hard zero.
    """

    def __init__(
        self,
        model: torch.nn.Module,
        loss_fn: SegmentationLoss | QuerySegmentationLoss,
        space: LabelSpace,
        optim_cfg: OptimConfig,
        train_cfg: TrainConfig,
        eval_cfg: EvalConfig,
        eval_active: Tensor | None = None,
    ) -> None:
        super().__init__()
        self.model = model
        self.loss_fn = loss_fn
        self.space = space
        self.optim_cfg = optim_cfg
        self.train_cfg = train_cfg
        self.eval_cfg = eval_cfg
        self.eval_active = eval_active
        if isinstance(loss_fn, QuerySegmentationLoss):
            self.task = "multiclass"
        elif isinstance(loss_fn, SegmentationLoss):
            self.task = loss_fn.cfg.task
        else:
            # A few checkpoint-hook tests intentionally use an inert loss module
            # because no training/evaluation step runs. Preserve that narrow
            # construction surface without guessing binary semantics.
            self.task = getattr(model, "task", "multiclass")
        validate_task_space(self.task, space)
        model_task = getattr(model, "task", "multiclass")
        if model_task != self.task:
            raise ValueError(
                f"model task {model_task!r} does not match objective task {self.task!r}"
            )
        if self.task == "binary":
            if eval_active is None:
                raise ValueError("binary validation requires the dataset's canonical active mask")
            validate_canonical_active(eval_active, self.task, where="validation active mask")
        if isinstance(loss_fn, QuerySegmentationLoss) and not getattr(
            model, "supports_query_objective", False
        ):
            raise ValueError(
                f"{type(model).__name__} is a dense model and cannot use a Hungarian "
                "query objective"
            )

        # Mask-classification models (EoMT, Mask2Former) are trained upstream with
        # Hungarian matching, not pixel CE. We can still train them densely, but
        # the numbers will sit below their published ones and that must be stated
        # rather than discovered later.
        if isinstance(loss_fn, SegmentationLoss) and not getattr(model, "supports_dense_ce", True):
            warnings.warn(
                f"{type(model).__name__} is a mask-classification architecture being trained "
                f"with pixel-wise cross-entropy instead of its native Hungarian-matching loss. "
                f"Expect results below the published numbers, and report this in the write-up.",
                stacklevel=2,
            )

        self.ema: ModelEma | None = None
        if train_cfg.ema_decay is not None:
            self.ema = ModelEma(model, EmaConfig(decay=train_cfg.ema_decay))

        self._cm: ConfusionMatrix | None = None
        self._bf1: BoundaryF1 | None = None
        self._train_started_monotonic: float | None = None
        self._training_samples = 0
        self._telemetry_step = -1
        self.save_hyperparameters(ignore=["model", "loss_fn", "space", "eval_active"])

    # -- training ----------------------------------------------------------

    def forward(self, pixel_values: Tensor) -> Tensor:
        return self.model(pixel_values)

    def training_step(self, batch: dict[str, Any], batch_idx: int) -> Tensor:
        # Per-sample active masks: a `joint` batch mixes datasets that disagree
        # about which canonical classes are supervised.
        objective = (
            query_training_objective
            if isinstance(self.loss_fn, QuerySegmentationLoss)
            else dense_training_objective
        )
        loss, parts = objective(
            self.model, self.loss_fn, batch["image"], batch["mask"], active=batch.get("active")
        )

        bs = batch["image"].shape[0]
        self.log("train/loss", loss, prog_bar=True, on_step=True, batch_size=bs, sync_dist=False)
        for name, value in parts.items():
            if name != "total":
                self.log(f"train/{name}", value, on_step=True, batch_size=bs, sync_dist=False)
        self.log("train/lr", self._current_lr(), prog_bar=True, on_step=True, batch_size=bs)
        return loss

    def on_train_batch_end(self, outputs, batch, batch_idx: int) -> None:
        if self.ema is not None:
            self.ema.update(self.model, self.global_step)
        self._training_samples += int(batch["image"].shape[0]) * int(self.trainer.world_size)
        completed = int(self.global_step)
        if completed <= self._telemetry_step or self._train_started_monotonic is None:
            return
        self._telemetry_step = completed
        elapsed = monotonic() - self._train_started_monotonic
        if elapsed <= 0:
            return
        total = int(self.train_cfg.iters)
        step_rate = completed / elapsed
        remaining = max(0, total - completed)
        telemetry = {
            "train/iteration": float(completed),
            "train/progress": min(1.0, completed / total),
            "train/optimizer_steps_per_sec": step_rate,
            "train/examples_per_sec": self._training_samples / elapsed,
            "train/elapsed_seconds": elapsed,
            "train/eta_seconds": remaining / step_rate if step_rate > 0 else float("nan"),
        }
        if self.device.type == "cuda":
            device = self.device
            telemetry.update(
                {
                    "system/gpu_memory_allocated_gib": torch.cuda.memory_allocated(device) / 2**30,
                    "system/gpu_memory_reserved_gib": torch.cuda.memory_reserved(device) / 2**30,
                    "system/gpu_peak_memory_allocated_gib": torch.cuda.max_memory_allocated(device)
                    / 2**30,
                    "system/gpu_peak_memory_reserved_gib": torch.cuda.max_memory_reserved(device)
                    / 2**30,
                }
            )
        for name, value in telemetry.items():
            self.log(name, value, on_step=True, on_epoch=False, sync_dist=False)

    def on_train_start(self) -> None:
        """Put pretrained modules into training mode before the first batch.

        Hugging Face ``from_pretrained`` returns modules in eval mode, and modern
        Lightning deliberately preserves per-submodule modes instead of calling
        ``train()`` at fit start.  Without this hook all stochastic depth and
        dropout stay disabled for the entire run.  Frozen/LoRA backbone norms
        immediately put themselves back in eval mode through tuning's forward
        pre-hook, so this does not weaken those ablations.
        """
        self.train()
        self._train_started_monotonic = monotonic()
        self._training_samples = 0
        self._telemetry_step = -1

    def on_save_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Persist the EMA shadow Lightning cannot discover on its own.

        ``ModelEma`` deliberately is not an ``nn.Module``, so without this hook
        validation can report EMA metrics while the resulting checkpoint holds
        only raw weights.  That makes the headline result impossible to
        reproduce and also hands raw weights to the next curriculum stage.
        """
        if self.ema is not None:
            checkpoint[EMA_CHECKPOINT_KEY] = self.ema.state_dict()

    def on_load_checkpoint(self, checkpoint: dict[str, Any]) -> None:
        """Restore EMA exactly when resuming an EMA-enabled training run."""
        if self.ema is None:
            return
        if EMA_CHECKPOINT_KEY not in checkpoint:
            raise RuntimeError(
                "this run has EMA enabled, but the checkpoint contains no saved EMA "
                "state. It is a legacy/raw-only checkpoint and cannot safely resume "
                "EMA training; disable EMA deliberately or start a fresh run."
            )
        self.ema.load_state_dict(checkpoint[EMA_CHECKPOINT_KEY])

    # -- validation --------------------------------------------------------

    def on_validation_epoch_start(self) -> None:
        n = self.space.num_classes
        active = self.eval_active.to(self.device) if self.eval_active is not None else None
        self._cm = ConfusionMatrix(n, self.space.ignore_index, active=active, device=self.device)
        self._bf1 = BoundaryF1(
            n,
            self.space.ignore_index,
            cfg=BoundaryConfig(tolerance_frac=self.eval_cfg.boundary_tolerance_frac),
            active=active,
            device=self.device,
        )

    def validation_step(self, batch: dict[str, Any], batch_idx: int) -> None:
        infer_cfg = InferenceConfig(
            sliding_window=self.eval_cfg.sliding_window,
            window=tuple(self.eval_cfg.window),
            stride=tuple(self.eval_cfg.stride),
            scales=tuple(self.eval_cfg.tta_scales) or (1.0,),
            flip=self.eval_cfg.tta_flip,
            task=self.task,
            threshold=self.eval_cfg.threshold,
        )
        # EMA weights are the ones we report; swapped() restores on exit even if
        # inference raises.
        context = self.ema.swapped(self.model) if self.ema is not None else _null_context()
        with context:
            logits = inference(self.model, batch["image"], self.space.num_classes, infer_cfg)

        pred = prediction_from_inference(logits, infer_cfg)
        target = batch["mask"]
        self._cm.update(pred, target)
        self._bf1.update(pred, target)

    def on_validation_epoch_end(self) -> None:
        self._cm.all_reduce()
        self._bf1.all_reduce()
        result = self._cm.compute()
        boundary = self._bf1.compute()

        self.log("val/miou", result.miou, prog_bar=True, sync_dist=False)
        self.log("val/macc", result.macc, sync_dist=False)
        self.log("val/pixel_acc", result.pixel_accuracy, sync_dist=False)
        self.log("val/boundary_f1", boundary.macro_f1, sync_dist=False)

        # Per-class IoU is the point: aggregate mIoU is dominated by road,
        # building, vegetation and sky, which every arm already gets right.
        for cid, name in enumerate(self.space.names):
            iou = result.iou[cid]
            if not torch.isnan(iou):
                self.log(f"val_iou/{name}", float(iou), sync_dist=False)

        thin = [self.space.names[i] for i in self.space.thin_classes]
        thin_ious = [
            float(result.iou[i]) for i in self.space.thin_classes if not torch.isnan(result.iou[i])
        ]
        if thin_ious:
            self.log("val/thin_miou", sum(thin_ious) / len(thin_ious), prog_bar=True)
            if self.trainer.is_global_zero:
                pairs = ", ".join(
                    f"{n}={float(result.iou[i]):.3f}"
                    for n, i in zip(thin, self.space.thin_classes, strict=True)
                    if not torch.isnan(result.iou[i])
                )
                print(f"\n[step {self.global_step}] thin-class IoU: {pairs}")

    def latest_metrics(self) -> dict[str, Any]:
        """Full metric dump for results.json, including the confusion matrix."""
        if self._cm is None:
            raise RuntimeError("latest_metrics() called before any validation ran")
        result = self._cm.compute()
        out = result.as_dict(list(self.space.names))
        out["boundary"] = self._bf1.compute().as_dict(list(self.space.names))
        if self.eval_cfg.save_confusion:
            out["confusion"] = result.confusion.tolist()
        return out

    # -- optimisation ------------------------------------------------------

    def configure_optimizers(self):
        head_patterns = (
            tuple(self.model.head_patterns())
            if hasattr(self.model, "head_patterns")
            else ("classifier", "decode_head", "head")
        )
        optimizer = build_optimizer(self.model, self.optim_cfg, head_patterns)
        if self.trainer.is_global_zero:
            print(describe_param_groups(optimizer.param_groups))

        total = self.train_cfg.iters
        scheduler = build_scheduler(optimizer, self.optim_cfg, total)
        return {
            "optimizer": optimizer,
            # interval="step": the whole schedule is iteration-based.
            "lr_scheduler": {"scheduler": scheduler, "interval": "step", "frequency": 1},
        }

    def _current_lr(self) -> float:
        opts = self.optimizers()
        opt = opts[0] if isinstance(opts, list) else opts
        return float(opt.param_groups[0]["lr"])


class _null_context:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False
