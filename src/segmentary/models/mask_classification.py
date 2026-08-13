"""EoMT / Mask2Former collapsed to the dense semantic map the rest of the project expects.

The inference rule is the one in ``MaskFormerImageProcessor.post_process_semantic_segmentation``
and its EoMT copy: upsample the mask *logits* to the target size, then sigmoid,
then contract over queries with the class posteriors. The order matters --
sigmoid is not linear, so sigmoid-then-upsample blurs the mask boundary that the
logit field encodes sharply, and the two differ by several percent of the score
range on a real checkpoint.
"""

from __future__ import annotations

import torch
import torch.nn.functional as F
from torch import Tensor, nn

from .outputs import QueryOutput, QueryPrediction, SegmentationOutput
from .wrappers import SegmentationModel, reinit_component_, resize_logits, resolve

# The query-contracted score is a sum of Q non-negative terms, so it is bounded by
# the number of queries rather than by 1, and log() of it is not sign-constrained.
# The floor only exists to keep log() finite where every query rejected the pixel.
# It is raised to the dtype's smallest normal at call time: under fp16 autocast
# 1e-8 rounds to zero and log() returns -inf, which reaches the loss as NaN a few
# steps later with nothing in the traceback pointing back here.
_SCORE_FLOOR = 1e-8


class MaskClassWrapper(SegmentationModel):
    """EoMT / Mask2Former: mask classification collapsed to a dense semantic map.

    The model predicts ``class_queries_logits`` (N, Q, C+1) and
    ``masks_queries_logits`` (N, Q, h, w). Dropping the no-object column and
    contracting the class posteriors against the sigmoid masks gives a per-pixel
    *score* in [0, Q] -- a sum over queries, not a probability and not a logit. It
    is log()'d so that the cross-entropy downstream re-normalises it into exactly
    the posterior the reference post-processor argmaxes over, and so that argmax
    over the log is the argmax over the score.

    Training calls :meth:`forward_output` to retain the raw class and mask
    predictions for Segmentary's native Hungarian objective.  ``forward`` remains
    the stable dense-tensor contract used by evaluation, sliding windows, and
    export.  ``supports_dense_ce`` remains False so choosing a dense objective
    for this wrapper is still explicit and warned about.

    ``native_size`` exists because EoMT bakes its token grid into the checkpoint
    (``config.image_size // patch_size``) and reshapes the patch tokens with it in
    ``predict()``; any other resolution is a raw view-shape error, not a graceful
    degradation. Inputs are resized to the native grid and the result mapped back.
    Note this is *not* what ``EomtImageProcessor`` does -- it rescales the shortest
    edge and then tiles the long axis into square patches, reassembling them in
    post-processing. We resize instead because this project owns its own
    sliding-window protocol in ``engine.inference``, and running EoMT's tiling
    inside the wrapper would tile each window a second time. The consequence is
    that a non-square window is squashed, so keep ``eval.window`` square for these
    architectures.

    Args:
        model: the HuggingFace universal-segmentation model.
        num_classes: canonical class count (the model itself holds C+1 columns).
        backbone_paths: dotted paths to the pretrained encoder submodules.
        head_paths: parameter-name substrings identifying the query/mask/class head.
        native_size: fixed (H, W) the checkpoint requires, or None if any size works.
        classifier_component: final path component reset by ``reset_head``.
        request_auxiliary_logits: ask compatible models (currently Mask2Former)
            to return intermediate decoder predictions for auxiliary supervision.
    """

    supports_dense_ce = False
    supports_query_objective = True

    def __init__(
        self,
        model: nn.Module,
        num_classes: int,
        backbone_paths: tuple[str, ...],
        head_paths: tuple[str, ...],
        native_size: tuple[int, int] | None = None,
        classifier_component: str = "class_predictor",
        request_auxiliary_logits: bool = False,
    ) -> None:
        super().__init__(num_classes)
        self.model = model
        self.backbone_paths = backbone_paths
        self.head_paths = head_paths
        self.native_size = native_size
        self.classifier_component = classifier_component
        self.request_auxiliary_logits = request_auxiliary_logits

    def _raw_output(self, pixel_values: Tensor, *, with_auxiliary: bool):
        size = (int(pixel_values.shape[-2]), int(pixel_values.shape[-1]))
        model_input = pixel_values
        if self.native_size is not None and size != self.native_size:
            model_input = F.interpolate(
                pixel_values, size=self.native_size, mode="bilinear", align_corners=False
            )

        extra = (
            {"output_auxiliary_logits": True}
            if with_auxiliary and self.request_auxiliary_logits
            else {}
        )
        return self.model(pixel_values=model_input, **extra)

    @staticmethod
    def _prediction_from_values(class_logits: Tensor, mask_logits: Tensor) -> QueryPrediction:
        return QueryPrediction(class_logits=class_logits, mask_logits=mask_logits)

    def forward_output(self, pixel_values: Tensor) -> SegmentationOutput:
        """Preserve raw query tensors and any explicitly returned decoder layers."""
        out = self._raw_output(pixel_values, with_auxiliary=True)
        primary = self._prediction_from_values(out.class_queries_logits, out.masks_queries_logits)
        auxiliary_values = getattr(out, "auxiliary_logits", None)
        auxiliary: list[QueryPrediction] = []
        if auxiliary_values is not None:
            if not isinstance(auxiliary_values, (list, tuple)):
                raise TypeError("model auxiliary_logits must be a list or tuple of mappings")
            for layer_index, values in enumerate(auxiliary_values):
                if not isinstance(values, dict):
                    raise TypeError(
                        f"model auxiliary_logits[{layer_index}] must be a mapping, "
                        f"got {type(values).__name__}"
                    )
                try:
                    class_logits = values["class_queries_logits"]
                    mask_logits = values["masks_queries_logits"]
                except KeyError as exc:
                    raise ValueError(
                        f"model auxiliary_logits[{layer_index}] lacks {exc.args[0]!r}"
                    ) from exc
                auxiliary.append(self._prediction_from_values(class_logits, mask_logits))
        return SegmentationOutput(query=QueryOutput(primary, tuple(auxiliary)))

    def forward(self, pixel_values: Tensor) -> Tensor:
        size = (int(pixel_values.shape[-2]), int(pixel_values.shape[-1]))
        out = self._raw_output(pixel_values, with_auxiliary=False)
        class_logits = out.class_queries_logits
        if class_logits.shape[-1] != self.num_classes + 1:
            raise ValueError(
                f"expected {self.num_classes + 1} class columns (classes + no-object), got "
                f"{class_logits.shape[-1]}"
            )

        # Drop the no-object column, then contract queries against their masks.
        cls_probs = class_logits.softmax(dim=-1)[..., :-1]
        masks = resize_logits(out.masks_queries_logits, size).sigmoid()
        semseg = torch.einsum("bqc,bqhw->bchw", cls_probs, masks)
        floor = max(_SCORE_FLOOR, torch.finfo(semseg.dtype).tiny)
        return self._check_output(semseg.clamp(min=floor).log(), pixel_values)

    def head_patterns(self) -> tuple[str, ...]:
        return self.head_paths

    def backbone_modules(self) -> list[nn.Module]:
        return [resolve(self.model, p) for p in self.backbone_paths]

    def reset_head(self) -> None:
        reinit_component_(self, self.classifier_component)
