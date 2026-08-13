"""Exponential moving average of model weights, with a ramped decay.

The EMA weights are what we actually evaluate and ship: on segmentation they are
worth roughly half a point of mIoU for free, and they make val curves readable
instead of noisy. Two details decide whether that happens:

* The decay is ramped from ~0 at step 0 (see :func:`effective_decay`). A constant
  0.9998 has a ~5000-step horizon, so for the first few thousand iterations the
  "EMA model" is mostly the random init and any early validation is meaningless.
* The shadow weights are kept in float32 even when training runs bf16. bf16 has
  8 mantissa bits, so an update of relative size 2e-4 is below the rounding
  threshold of the accumulator and the average silently stops moving.

Why not ``torch.optim.swa_utils.AveragedModel`` with ``get_ema_multi_avg_fn``:
that helper closes over a *fixed* decay at construction time, and AveragedModel
stores the callable once, so a per-step ramp would mean rebuilding and reassigning
the closure every iteration. AveragedModel also deep-copies the whole module
(including autograd plumbing and the bf16 parameter dtypes we explicitly do not
want) and keys the average positionally rather than by name, which is fragile
across a DDP wrap. We use the same primitive it does -- ``torch._foreach_lerp_``,
one fused kernel per dtype bucket instead of a Python loop over ~400 tensors --
and keep the name-keyed bookkeeping ourselves.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from typing import cast

import torch
from torch import Tensor, nn

# Stored outside Lightning's ordinary ``state_dict`` because ModelEma is
# intentionally a plain object rather than an nn.Module.  Keep one canonical
# key so training, stage hand-off, and the standalone evaluator cannot drift.
EMA_CHECKPOINT_KEY = "ema_state_dict"


@dataclass
class EmaConfig:
    """Shadow-weight averaging schedule.

    ``update_every`` > 1 trades fidelity for speed and stretches the EMA horizon
    by the same factor in optimizer steps; raise ``decay`` deliberately if you
    change it, nothing here compensates automatically.
    """

    decay: float = 0.9998
    warmup_iters: int = 2000
    update_every: int = 1

    def __post_init__(self) -> None:
        if not 0.0 <= self.decay < 1.0:
            raise ValueError(
                f"ema decay must be in [0, 1), got {self.decay}; 1.0 would freeze the "
                "shadow weights at initialization forever"
            )
        if self.warmup_iters < 0:
            raise ValueError(f"ema warmup_iters must be >= 0, got {self.warmup_iters}")
        if self.update_every < 1:
            raise ValueError(f"ema update_every must be >= 1, got {self.update_every}")


def effective_decay(cfg: EmaConfig, step: int) -> float:
    """Decay actually used at ``step``, ramped up from 0.1 over the warmup.

    ``min(decay, (1 + step) / (10 + step))`` gives the shadow a short horizon
    while the weights are still moving fast, so it tracks the model instead of
    staying anchored to the random init. After ``warmup_iters`` the configured
    decay applies unconditionally; with the defaults the ramp has reached 0.9955
    by then, so the transition is small.
    """
    if step < 0:
        raise ValueError(f"ema step must be >= 0, got {step}")
    if step >= cfg.warmup_iters:
        return cfg.decay
    return min(cfg.decay, (1.0 + step) / (10.0 + step))


# Averaging a wrapper directly would prefix every key with "module.", so a
# checkpoint written under DDP could not be loaded by a single-GPU eval run.
def _unwrap(model: nn.Module) -> nn.Module:
    inner = model
    while True:
        if isinstance(inner, (nn.parallel.DistributedDataParallel, nn.DataParallel)):
            inner = inner.module
        elif hasattr(inner, "_orig_mod"):  # torch.compile's OptimizedModule
            # nn.Module.__getattr__ is typed Tensor | Module; this one is a Module.
            inner = cast(nn.Module, inner._orig_mod)
        else:
            return inner


_HALF_WRITTEN = "writing anyway would leave the model half-EMA, half-live"
_DROPPED = "loading would silently drop weights"


def _require_same(
    label: str, shadow: Mapping[str, Tensor], other: Mapping[str, Tensor], consequence: str
) -> None:
    # Mapping, not dict: callers pass named_parameters() (dict[str, Parameter]),
    # and dict is invariant in its value type even though Parameter is a Tensor.
    if set(shadow) != set(other):
        extra = sorted(set(other) - set(shadow))[:3]
        lost = sorted(set(shadow) - set(other))[:3]
        raise ValueError(
            f"EMA {label} keys do not match this model (unexpected: {extra}, "
            f"missing: {lost}); {consequence}"
        )
    for name, tensor in other.items():
        # Not pedantry: Tensor.copy_ broadcasts, so an unchecked mismatch fans one
        # value over a whole row instead of failing.
        if tensor.shape != shadow[name].shape:
            raise ValueError(
                f"EMA {label} entry {name!r} has shape {tuple(tensor.shape)} but the shadow "
                f"holds {tuple(shadow[name].shape)}; {consequence}"
            )


@dataclass
class _Pairing:
    # Rebuilt from named_parameters() on every update rather than cached against
    # the module: `.to(device)`, `load_state_dict(assign=True)` and adapter
    # injection all swap Parameter objects under an unchanged module identity, and
    # a cache would then keep averaging tensors the model no longer uses -- a
    # silently frozen EMA. The traversal costs ~0.1 ms per few hundred tensors,
    # under 0.1% of a training step.
    fp32: list[tuple[Tensor, nn.Parameter]]
    other: list[tuple[Tensor, nn.Parameter]]
    buffers: list[tuple[Tensor, Tensor]]


class ModelEma:
    """Name-keyed EMA shadow of ``model``'s parameters, in float32.

    Buffers are copied, never averaged (see :meth:`update`).
    """

    def __init__(self, model: nn.Module, cfg: EmaConfig) -> None:
        self.cfg = cfg
        self.num_updates = 0
        inner = _unwrap(model)
        self.params: dict[str, Tensor] = {
            name: p.detach().to(torch.float32).clone() for name, p in inner.named_parameters()
        }
        self.buffers: dict[str, Tensor] = {
            name: b.detach().clone() for name, b in inner.named_buffers()
        }

    @torch.no_grad()
    def update(self, model: nn.Module, step: int) -> None:
        """Blend ``model``'s parameters into the shadow using the ramped decay.

        Buffers are *copied* rather than averaged: BatchNorm running stats are
        already an exponential average over batches, so averaging them again
        double-smooths them into a lag the activations were never normalized by,
        and ``num_batches_tracked`` is an int64 counter that a lerp would corrupt
        outright. Copying keeps the shadow's statistics consistent with its most
        recent weights. This is Segmentary's explicit checkpoint/evaluation
        contract rather than an implicit library default.
        """
        if step % self.cfg.update_every != 0:
            return
        decay = effective_decay(self.cfg, step)
        pairs = self._resolve(_unwrap(model))

        if pairs.fp32:
            torch._foreach_lerp_(
                [s for s, _ in pairs.fp32], [p.data for _, p in pairs.fp32], 1.0 - decay
            )
        if pairs.other:
            # _foreach_lerp_ rejects a bf16/fp16 `end` against an fp32 `self`, so
            # the up-cast is mandatory rather than merely tidy.
            torch._foreach_lerp_(
                [s for s, _ in pairs.other],
                [p.data.to(torch.float32) for _, p in pairs.other],
                1.0 - decay,
            )
        for shadow_buf, buf in pairs.buffers:
            shadow_buf.copy_(buf)
        self.num_updates += 1

    def _resolve(self, inner: nn.Module) -> _Pairing:
        fp32_pairs: list[tuple[Tensor, nn.Parameter]] = []
        other_pairs: list[tuple[Tensor, nn.Parameter]] = []
        seen = set()
        for name, param in inner.named_parameters():
            shadow = self.params.get(name)
            if shadow is None:
                raise ValueError(
                    f"parameter {name!r} is absent from the EMA shadow; the model gained "
                    "parameters after ModelEma was constructed, so the average is stale"
                )
            if shadow.shape != param.shape:
                raise ValueError(
                    f"parameter {name!r} has shape {tuple(param.shape)} but the EMA shadow "
                    f"holds {tuple(shadow.shape)}; construct a fresh ModelEma after reshaping"
                )
            if shadow.device != param.device:
                self.params[name] = shadow = shadow.to(param.device)
            seen.add(name)
            pair = (shadow, param)
            (fp32_pairs if param.dtype == torch.float32 else other_pairs).append(pair)
        missing = set(self.params) - seen
        if missing:
            raise ValueError(
                f"model is missing {len(missing)} parameter(s) held by the EMA shadow "
                f"(e.g. {sorted(missing)[0]!r}); the shadow does not match this model"
            )
        buf_pairs: list[tuple[Tensor, Tensor]] = []
        for name, buf in inner.named_buffers():
            shadow_buf = self.buffers.get(name)
            if shadow_buf is None:
                raise ValueError(
                    f"buffer {name!r} is absent from the EMA shadow; the model gained buffers "
                    "after ModelEma was constructed"
                )
            if shadow_buf.shape != buf.shape:
                raise ValueError(
                    f"buffer {name!r} has shape {tuple(buf.shape)} but the EMA shadow holds "
                    f"{tuple(shadow_buf.shape)}; copy_ would broadcast one over the other"
                )
            if shadow_buf.device != buf.device:
                self.buffers[name] = shadow_buf = shadow_buf.to(buf.device)
            buf_pairs.append((shadow_buf, buf))
        return _Pairing(fp32_pairs, other_pairs, buf_pairs)

    @torch.no_grad()
    def copy_to(self, model: nn.Module) -> None:
        """Write the shadow weights (and buffers) into ``model``, in place."""
        inner = _unwrap(model)
        live_params = dict(inner.named_parameters())
        live_buffers = dict(inner.named_buffers())
        # Everything is validated before the first write: a mismatch discovered
        # halfway through the loop would leave exactly the half-EMA, half-live
        # model this is supposed to refuse to produce.
        _require_same("params", self.params, live_params, _HALF_WRITTEN)
        _require_same("buffers", self.buffers, live_buffers, _HALF_WRITTEN)
        for name, param in live_params.items():
            param.data.copy_(self.params[name])
        for name, buf in live_buffers.items():
            buf.copy_(self.buffers[name])

    @contextmanager
    def swapped(self, model: nn.Module) -> Iterator[nn.Module]:
        """Run a block with EMA weights installed in ``model``, then restore.

        Validation runs inside this; the restore is in a ``finally`` so that an
        OOM or a bad batch mid-eval cannot leave training to continue from the
        averaged weights.
        """
        inner = _unwrap(model)
        backup_params = {name: p.detach().clone() for name, p in inner.named_parameters()}
        backup_buffers = {name: b.detach().clone() for name, b in inner.named_buffers()}
        try:
            # Inside the try: an OOM or a mismatch raised while installing the
            # shadow must still hand the live weights back.
            self.copy_to(inner)
            yield model
        finally:
            with torch.no_grad():
                for name, param in inner.named_parameters():
                    param.data.copy_(backup_params[name])
                for name, buf in inner.named_buffers():
                    buf.copy_(backup_buffers[name])

    def state_dict(self) -> dict[str, object]:
        """Checkpointable state: shadow tensors on CPU plus the update counter."""
        return {
            "params": {name: t.detach().cpu().clone() for name, t in self.params.items()},
            "buffers": {name: t.detach().cpu().clone() for name, t in self.buffers.items()},
            "num_updates": self.num_updates,
        }

    def load_state_dict(self, sd: dict[str, object]) -> None:
        """Restore from :meth:`state_dict`, requiring an exact key match."""
        for key in ("params", "buffers", "num_updates"):
            if key not in sd:
                raise ValueError(
                    f"EMA state_dict is missing {key!r}; it was not written by ModelEma"
                )
        params = sd["params"]
        buffers = sd["buffers"]
        if not isinstance(params, dict) or not isinstance(buffers, dict):
            raise ValueError("EMA state_dict 'params'/'buffers' must be dicts of named tensors")
        for label, target, source in (
            ("params", self.params, params),
            ("buffers", self.buffers, buffers),
        ):
            _require_same(label, target, source, _DROPPED)
            for name, tensor in source.items():
                target[name].copy_(tensor)
        num_updates = sd["num_updates"]
        if not isinstance(num_updates, int):
            raise ValueError(f"EMA num_updates must be an int, got {type(num_updates).__name__}")
        self.num_updates = num_updates
