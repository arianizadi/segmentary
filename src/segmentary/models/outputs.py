"""Typed model outputs for dense and query-based segmentation.

Training needs richer information than deployment.  A dense auxiliary head must
not disappear just because the public ``forward`` method returns one ONNX-friendly
tensor, and a query model must not be collapsed before Hungarian matching.  These
dataclasses preserve those distinctions without allowing architecture-specific
dictionaries to leak into the engine.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from torch import Tensor


@dataclass(frozen=True)
class AuxiliaryDenseOutput:
    """Named full-resolution auxiliary logits and their configured loss weight."""

    name: str
    logits: Tensor
    loss_weight: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
            or self.name != self.name.strip()
        ):
            raise ValueError("auxiliary output name must be a non-empty, trimmed string")
        if not isinstance(self.logits, Tensor) or self.logits.ndim != 4:
            raise ValueError(f"auxiliary output {self.name!r} logits must be NCHW")
        if not math.isfinite(self.loss_weight) or self.loss_weight <= 0.0:
            raise ValueError(
                f"auxiliary output {self.name!r} loss_weight must be finite and positive"
            )


@dataclass(frozen=True)
class QueryPrediction:
    """One decoder layer's raw query-class and query-mask predictions."""

    class_logits: Tensor  # (N, Q, C + 1), including the no-object column
    mask_logits: Tensor  # (N, Q, h, w), before sigmoid

    def __post_init__(self) -> None:
        if not isinstance(self.class_logits, Tensor) or self.class_logits.ndim != 3:
            raise ValueError("query class_logits must have shape (N, Q, C+1)")
        if not isinstance(self.mask_logits, Tensor) or self.mask_logits.ndim != 4:
            raise ValueError("query mask_logits must have shape (N, Q, h, w)")
        if self.class_logits.shape[:2] != self.mask_logits.shape[:2]:
            raise ValueError(
                "query class/mask predictions disagree on batch or query count: "
                f"{tuple(self.class_logits.shape)} vs {tuple(self.mask_logits.shape)}"
            )
        if self.class_logits.shape[0] < 1 or self.class_logits.shape[1] < 1:
            raise ValueError("query prediction needs at least one batch item and one query")
        if self.class_logits.shape[2] < 2:
            raise ValueError("query class_logits needs at least one class plus no-object")
        if self.mask_logits.shape[2] < 1 or self.mask_logits.shape[3] < 1:
            raise ValueError("query mask_logits has an empty spatial dimension")


@dataclass(frozen=True)
class QueryOutput:
    """Primary query prediction plus optional intermediate decoder predictions."""

    primary: QueryPrediction
    auxiliary: tuple[QueryPrediction, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.primary, QueryPrediction):
            raise TypeError("query output primary must be a QueryPrediction")
        if not isinstance(self.auxiliary, tuple) or not all(
            isinstance(item, QueryPrediction) for item in self.auxiliary
        ):
            raise TypeError("query output auxiliary must be a tuple of QueryPrediction values")
        for index, item in enumerate(self.auxiliary):
            if item.class_logits.shape != self.primary.class_logits.shape:
                raise ValueError(
                    f"query auxiliary layer {index} class shape {tuple(item.class_logits.shape)} "
                    f"!= primary {tuple(self.primary.class_logits.shape)}"
                )
            if item.mask_logits.shape[:2] != self.primary.mask_logits.shape[:2]:
                raise ValueError(f"query auxiliary layer {index} changed batch/query count")


@dataclass(frozen=True)
class SegmentationOutput:
    """Architecture-independent training output.

    Exactly one primary representation is present: dense logits *or* raw query
    predictions.  This prevents an engine from accidentally choosing whichever
    key happens to exist first.
    """

    dense_logits: Tensor | None = None
    auxiliary_dense: tuple[AuxiliaryDenseOutput, ...] = field(default_factory=tuple)
    query: QueryOutput | None = None

    def __post_init__(self) -> None:
        if (self.dense_logits is None) == (self.query is None):
            raise ValueError("segmentation output needs exactly one of dense_logits or query")
        if self.query is not None and not isinstance(self.query, QueryOutput):
            raise TypeError("segmentation output query must be a QueryOutput")
        if self.dense_logits is not None and (
            not isinstance(self.dense_logits, Tensor) or self.dense_logits.ndim != 4
        ):
            raise ValueError("dense_logits must have shape (N, C, H, W)")
        if not isinstance(self.auxiliary_dense, tuple) or not all(
            isinstance(item, AuxiliaryDenseOutput) for item in self.auxiliary_dense
        ):
            raise TypeError("auxiliary_dense must be a tuple of AuxiliaryDenseOutput values")
        names = [item.name for item in self.auxiliary_dense]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate auxiliary output names: {names}")
        if self.query is not None and self.auxiliary_dense:
            raise ValueError(
                "query output cannot carry dense auxiliary predictions; put intermediate "
                "query predictions in QueryOutput.auxiliary"
            )
        if self.dense_logits is not None:
            for item in self.auxiliary_dense:
                if item.logits.shape != self.dense_logits.shape:
                    raise ValueError(
                        f"auxiliary output {item.name!r} shape {tuple(item.logits.shape)} "
                        f"!= primary dense shape {tuple(self.dense_logits.shape)}"
                    )
