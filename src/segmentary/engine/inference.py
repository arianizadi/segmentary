"""Sliding-window inference and multi-scale/flip TTA.

Evaluating a crop-trained model on larger frames by resizing each frame down is
not the same experiment as evaluating it at native resolution: thin or small
structures can disappear during downscaling. Eval therefore runs an independently
implemented sliding window at native resolution and averages overlapping logits.
The deterministic edge-aligned grid is recorded as part of Segmentary's evaluation
contract so repeated runs remain comparable.

The model passed in is any callable ``(N, 3, H, W) -> (N, C, H, W)`` whose logits
are *already* upsampled to the input resolution. Keeping the stride-4 -> stride-1
upsample inside the model wrapper is what lets this file stay architecture-blind.

One asymmetry worth knowing before you use the return value: with a single view
(``scales=(1.0,)`` and ``flip=False``) ``inference`` returns raw logits, byte-for-
byte identical to a plain forward pass. With transformed views it returns
averaged probabilities: softmax for multiclass and sigmoid for binary. Always
use :func:`prediction_from_inference` to turn either representation into class
ids; it never applies argmax to a one-channel binary tensor.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal, Protocol

import torch
import torch.nn.functional as F
from torch import Tensor


class SegModel(Protocol):
    """Any callable mapping a normalised image batch to full-resolution logits."""

    def __call__(self, image: Tensor) -> Tensor: ...


@dataclass
class InferenceConfig:
    """How one evaluation forward pass is assembled.

    Args:
        sliding_window: tile the image instead of running it whole. Off only for
            datasets whose frames already match the training crop.
        window: (H, W) of one tile, normally the training crop size.
        stride: (H, W) step between tiles; stride < window gives the overlap that
            averages away tile-boundary artefacts.
        scales: multipliers applied to the input before inference.
        flip: also run the horizontally mirrored image.
        task: multiclass softmax or one-logit binary sigmoid semantics.
        threshold: class-1 positive probability cutoff used only by binary prediction.
    """

    sliding_window: bool = True
    window: tuple[int, int] = (1024, 1024)
    stride: tuple[int, int] = (768, 768)
    scales: tuple[float, ...] = (1.0,)
    flip: bool = False
    task: Literal["multiclass", "binary"] = "multiclass"
    threshold: float = 0.5

    def __post_init__(self) -> None:
        if len(self.window) != 2 or len(self.stride) != 2:
            raise ValueError(
                f"window and stride must be (H, W) pairs, got {self.window} / {self.stride}"
            )
        if any(v <= 0 for v in self.window):
            raise ValueError(f"window must be positive, got {self.window}")
        for s, w in zip(self.stride, self.window, strict=False):
            if not 0 < s <= w:
                raise ValueError(
                    f"stride {tuple(self.stride)} must be positive and <= window {tuple(self.window)}; "
                    f"a larger stride would leave uncovered pixels between tiles"
                )
        if len(self.scales) == 0:
            raise ValueError(
                "scales must list at least one scale; use (1.0,) for single-scale eval"
            )
        if any(s <= 0 for s in self.scales):
            raise ValueError(f"scales must be positive, got {tuple(self.scales)}")
        if self.task not in ("multiclass", "binary"):
            raise ValueError(f"task must be 'multiclass' or 'binary', got {self.task!r}")
        if (
            isinstance(self.threshold, bool)
            or not isinstance(self.threshold, (int, float))
            or not math.isfinite(self.threshold)
            or not 0.0 < self.threshold < 1.0
        ):
            raise ValueError(
                f"threshold must be a finite probability in (0, 1), got {self.threshold!r}"
            )


def _output_channels(num_classes: int, task: str) -> int:
    if task == "multiclass":
        if num_classes < 2:
            raise ValueError(f"multiclass inference needs at least two classes, got {num_classes}")
        return num_classes
    if task == "binary":
        if num_classes != 2:
            raise ValueError(
                "binary inference requires exactly two canonical classes "
                f"(id 0 negative, id 1 positive), got {num_classes}"
            )
        return 1
    raise ValueError(f"unsupported inference task {task!r}")


def _check_logits(
    logits: object,
    image: Tensor,
    num_classes: int,
    where: str,
    *,
    task: str = "multiclass",
) -> Tensor:
    if not isinstance(logits, Tensor):
        raise ValueError(
            f"{where}: model returned {type(logits).__name__}, expected a Tensor of logits. "
            f"Wrap HuggingFace models so they return .logits already upsampled to input size."
        )
    channels = _output_channels(num_classes, task)
    expected = (image.shape[0], channels, image.shape[2], image.shape[3])
    if tuple(logits.shape) == expected:
        return logits
    # Separate diagnoses: a channel mismatch is a head/label-space mismatch (evaluating
    # a 19-class checkpoint in the 21-class space), and telling that user to fix their
    # upsampling sends them to the wrong file.
    if logits.ndim == 4 and logits.shape[1] != channels:
        if task == "binary":
            raise ValueError(
                f"{where}: binary model returned {logits.shape[1]} logit channels; exactly "
                "one raw class-1 positive logit is required for canonical ids 0/1"
            )
        raise ValueError(
            f"{where}: model returned {logits.shape[1]} logit channels but the label space has "
            f"{num_classes} classes. The checkpoint was built for a different label space, or "
            f"num_classes was not threaded through from the taxonomy."
        )
    raise ValueError(
        f"{where}: model returned logits {tuple(logits.shape)}, expected {expected}. "
        f"Inference requires logits at input resolution; upsample inside the model wrapper."
    )


def _check_image(image: Tensor) -> None:
    if image.ndim != 4:
        raise ValueError(f"image must be (N, 3, H, W), got {tuple(image.shape)}")


def _window_grid(
    height: int, width: int, window: tuple[int, int], stride: tuple[int, int]
) -> list[tuple[int, int, int, int]]:
    # Tile origins are (y1, y2, x1, x2). The final row/column is pulled *back* to
    # end on the image edge rather than overrunning it,
    # so the last tile overlaps its neighbour more than `stride` instead of being
    # padded: padding would feed the model a border of zeros it never saw in training.
    win_h, win_w = window
    stride_h, stride_w = stride
    h_grids = max(height - win_h + stride_h - 1, 0) // stride_h + 1
    w_grids = max(width - win_w + stride_w - 1, 0) // stride_w + 1
    cells: list[tuple[int, int, int, int]] = []
    for h_idx in range(h_grids):
        for w_idx in range(w_grids):
            y1 = h_idx * stride_h
            x1 = w_idx * stride_w
            y2 = min(y1 + win_h, height)
            x2 = min(x1 + win_w, width)
            y1 = max(y2 - win_h, 0)
            x1 = max(x2 - win_w, 0)
            cells.append((y1, y2, x1, x2))
    return cells


def whole_inference(
    model: SegModel,
    image: Tensor,
    num_classes: int,
    *,
    task: Literal["multiclass", "binary"] = "multiclass",
) -> Tensor:
    """Run the model on the full image in one pass. Returns (N, C, H, W) logits."""
    _check_image(image)
    return _check_logits(model(image), image, num_classes, "whole_inference", task=task)


def slide_inference(
    model: SegModel, image: Tensor, num_classes: int, cfg: InferenceConfig
) -> Tensor:
    """Tile the image, run the model per tile, average the overlapping logits.

    Falls back to :func:`whole_inference` when the image is smaller than the
    window in either dimension -- padding up to the window would change the
    statistics of the border pixels, and a model that handles a 512 image fine
    does not need help from 512 rows of zeros.

    Args:
        model: callable returning logits at input resolution.
        image: (N, 3, H, W) normalised float batch.
        num_classes: canonical taxonomy class count. Binary still passes two
            canonical classes even though its model emits one channel.
        cfg: window/stride settings; TTA fields are ignored here.

    Returns:
        (N, C, H, W) float32 logits at the original size.
    """
    _check_image(image)
    n, _, height, width = image.shape
    win_h, win_w = cfg.window
    if height < win_h or width < win_w:
        # .float() on the fallback too: otherwise the return dtype of this function
        # silently depends on the image size (bf16 under autocast for a small frame,
        # float32 for a large one), and callers argmax the result without casting.
        return whole_inference(model, image, num_classes, task=cfg.task).float()

    # float32 regardless of autocast: hundreds of bf16 accumulations into the same
    # overlap region lose enough mantissa to move argmax on close calls.
    channels = _output_channels(num_classes, cfg.task)
    logit_sum = torch.zeros((n, channels, height, width), dtype=torch.float32, device=image.device)
    count = torch.zeros((n, 1, height, width), dtype=torch.float32, device=image.device)

    for y1, y2, x1, x2 in _window_grid(height, width, cfg.window, cfg.stride):
        crop = image[:, :, y1:y2, x1:x2]
        logits = _check_logits(
            model(crop),
            crop,
            num_classes,
            f"slide_inference tile ({y1}:{y2}, {x1}:{x2})",
            task=cfg.task,
        )
        logit_sum[:, :, y1:y2, x1:x2] += logits.float()
        count[:, :, y1:y2, x1:x2] += 1.0

    if not bool((count > 0).all()):
        missing = int((count == 0).sum())
        raise ValueError(
            f"sliding window left {missing} pixel slots uncovered for image {height}x{width} "
            f"with window {tuple(cfg.window)} stride {tuple(cfg.stride)}; dividing would yield NaN"
        )
    return logit_sum / count


def _base_pass(model: SegModel, image: Tensor, num_classes: int, cfg: InferenceConfig) -> Tensor:
    if cfg.sliding_window:
        return slide_inference(model, image, num_classes, cfg)
    return whole_inference(model, image, num_classes, task=cfg.task)


def _single_view(cfg: InferenceConfig) -> bool:
    return tuple(cfg.scales) == (1.0,) and not cfg.flip


def inference(model: SegModel, image: Tensor, num_classes: int, cfg: InferenceConfig) -> Tensor:
    """One evaluation prediction: window strategy plus multi-scale/flip TTA.

    Args:
        model: callable returning logits at input resolution.
        image: (N, 3, H, W) normalised float batch.
        num_classes: canonical taxonomy class count. Binary still passes two
            canonical classes even though its model emits one channel.
        cfg: window and TTA settings.

    Returns:
        (N, C, H, W) at the *original* spatial size. Raw logits when the config
        asks for a single view (``scales=(1.0,)``, ``flip=False``), otherwise the
        mean probability over views (softmax for multiclass, sigmoid for binary).
    """
    _check_image(image)
    scales = tuple(cfg.scales)
    if _single_view(cfg):
        # Short-circuit, not an optimisation: single-scale eval must be bit-identical
        # to a plain pass, and log/softmax round-tripping is not.
        return _base_pass(model, image, num_classes, cfg)

    height, width = image.shape[2], image.shape[3]
    prob_sum: Tensor | None = None
    views = 0
    for scale in scales:
        if scale == 1.0:
            scaled = image
        else:
            size = (max(1, round(height * scale)), max(1, round(width * scale)))
            scaled = F.interpolate(image, size=size, mode="bilinear", align_corners=False)
        for flipped in (False, True) if cfg.flip else (False,):
            view = torch.flip(scaled, dims=(3,)) if flipped else scaled
            logits = _base_pass(model, view, num_classes, cfg).float()
            if flipped:
                logits = torch.flip(logits, dims=(3,))
            if logits.shape[2] != height or logits.shape[3] != width:
                logits = F.interpolate(
                    logits, size=(height, width), mode="bilinear", align_corners=False
                )
            # Activate first, then average. Logits from differently transformed
            # passes have no common scale. Binary views use independent class-1
            # sigmoid probability; multiclass views retain the historical softmax.
            probs = logits.sigmoid() if cfg.task == "binary" else logits.softmax(dim=1)
            prob_sum = probs if prob_sum is None else prob_sum + probs
            views += 1

    assert prob_sum is not None  # scales is non-empty by construction
    return prob_sum / views


def prediction_from_inference(scores: Tensor, cfg: InferenceConfig) -> Tensor:
    """Convert inference output to canonical integer class ids.

    Single-view outputs are raw logits. Transformed-view outputs are already
    averaged probabilities. The distinction is explicit so binary prediction
    performs sigmoid exactly once and never uses a one-channel argmax.
    """
    if not isinstance(scores, Tensor) or scores.ndim != 4:
        raise ValueError(
            f"inference scores must have shape (N,C,H,W), got "
            f"{type(scores).__name__} {getattr(scores, 'shape', None)}"
        )
    if not bool(torch.isfinite(scores).all()):
        raise FloatingPointError("inference produced non-finite scores")
    if cfg.task == "multiclass":
        if scores.shape[1] < 2:
            raise ValueError(
                "multiclass prediction requires at least two channels; refusing to argmax "
                f"a {scores.shape[1]}-channel tensor"
            )
        return scores.argmax(dim=1)
    if scores.shape[1] != 1:
        raise ValueError(
            f"binary prediction requires exactly one class-1 positive channel, got "
            f"{scores.shape[1]}"
        )
    probabilities = scores.sigmoid() if _single_view(cfg) else scores
    if not _single_view(cfg) and bool(((probabilities < 0) | (probabilities > 1)).any()):
        raise ValueError("binary transformed-view inference must return probabilities in [0, 1]")
    return (probabilities[:, 0] >= cfg.threshold).to(torch.long)
