"""The forward contract, and the two dense-prediction wrappers that satisfy it.

Everything downstream -- the train loop, sliding-window inference, TTA, the
confusion matrix -- must hold a model without knowing whether it is a SegFormer,
an smp encoder/decoder pair, or a mask-classification transformer. Every wrapper
returns ``(N, C, H, W)`` logits at *input* resolution and nothing else.
Mask-classification models need a whole inference rule of their own and live in
``models.mask_classification``.

Two deliberate non-features:

* The HuggingFace models are never called with ``labels=``. Their internal loss
  ignores our inactive-class masking and our ignore-index contract, so using it
  would silently bypass ``engine.losses``.
* Module references are resolved by path or by name at call time, never cached as
  attributes. Caching would either duplicate parameters in ``state_dict`` (a
  module registered under two names) or go stale the moment PEFT re-parents the
  tree under ``base_model.model``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import torch.nn.functional as F
from torch import Tensor, nn

from .outputs import SegmentationOutput

_PEFT_PREFIXES = ("", "base_model.model.")


def resize_logits(logits: Tensor, size: tuple[int, ...]) -> Tensor:
    """Resize to a spatial (H, W); callers pass a tensor .shape slice directly."""
    """Bilinearly resize (N, C, h, w) logits to ``size``, or pass through if equal.

    Segmentary fixes ``align_corners=False`` everywhere so train, sliding-window,
    TTA, and export use one interpolation convention. Changing it can shift
    boundaries and therefore defines a different evaluation protocol.
    """
    if tuple(logits.shape[-2:]) == tuple(size):
        return logits
    return F.interpolate(logits, size=size, mode="bilinear", align_corners=False)


def resolve(root: nn.Module, path: str) -> nn.Module:
    """``get_submodule`` that also looks past PEFT's ``base_model.model`` wrapper."""
    for prefix in _PEFT_PREFIXES:
        try:
            return root.get_submodule(prefix + path)
        except AttributeError:
            continue
    raise ValueError(
        f"submodule {path!r} not found on {type(root).__name__}; the wrapper was built "
        f"against a different module layout. Fix the path in models.factory rather than "
        f"training a partly-frozen model by accident."
    )


def find_by_component(root: nn.Module, component: str) -> list[nn.Module]:
    """Every submodule whose qualified name ends with ``component``.

    Matching only the final path component survives PEFT re-parenting
    (``base_model.model.decode_head.modules_to_save.default.classifier``), which
    dotted-path lookup does not. When PEFT keeps a trainable copy under
    ``modules_to_save``, return only that active copy and never its frozen
    ``original_module`` twin.
    """
    matches = [
        (name, module) for name, module in root.named_modules() if name.split(".")[-1] == component
    ]
    active = [module for name, module in matches if ".modules_to_save." in f".{name}."]
    return active or [module for _, module in matches]


def reinit_(module: nn.Module) -> int:
    """Re-initialise every Conv2d/Linear leaf in place; returns how many were hit.

    Segmentary uses std=0.01 normal with zero bias to give a near-uniform
    prediction at step 0, so a reset head does not start out
    confidently asserting some arbitrary class over the whole image.
    """
    hits = 0
    for m in module.modules():
        if isinstance(m, (nn.Conv2d, nn.Linear)):
            nn.init.normal_(m.weight, mean=0.0, std=0.01)
            if m.bias is not None:
                nn.init.zeros_(m.bias)
            hits += 1
    return hits


def reinit_component_(root: nn.Module, component: str) -> None:
    """Re-initialise the Conv2d/Linear leaves under every module named ``component``.

    Raises if that hits nothing. A ``reset_head`` that quietly re-initialises zero
    tensors -- because the component was renamed upstream, or because the module it
    names turned out to be an ``Identity`` -- carries the previous stage's class
    priors into the next one while the log still says the head was reset.
    """
    hits = sum(reinit_(m) for m in find_by_component(root, component))
    if hits == 0:
        raise ValueError(
            f"reset_head re-initialised nothing on {type(root).__name__}: no Conv2d or Linear "
            f"under a submodule named {component!r}. The head would silently keep its old "
            f"weights across a stage boundary; fix the component name in models.factory."
        )


class SegmentationModel(nn.Module, ABC):
    """The single contract every architecture in this project satisfies.

    Attributes:
        num_classes: canonical class count, matching the label space.
        output_channels: raw dense-logit channels. This equals ``num_classes``
            for multiclass models and is exactly one for binary models.
        task: semantic interpretation of the output channels.
        supports_dense_ce: False for mask-classification models, whose outputs are
            converted probabilities rather than true logits.
    """

    supports_dense_ce: bool = True
    supports_query_objective: bool = False

    def __init__(
        self,
        num_classes: int,
        *,
        output_channels: int | None = None,
        task: str = "multiclass",
    ) -> None:
        super().__init__()
        if num_classes < 2:
            raise ValueError(f"num_classes must be at least 2, got {num_classes}")
        if task not in ("multiclass", "binary"):
            raise ValueError(f"unsupported segmentation task {task!r}")
        resolved_channels = num_classes if output_channels is None else output_channels
        if task == "multiclass" and resolved_channels != num_classes:
            raise ValueError(
                "multiclass models need one output channel per canonical class, got "
                f"{resolved_channels} channels for {num_classes} classes"
            )
        if task == "binary" and (num_classes != 2 or resolved_channels != 1):
            raise ValueError(
                "binary models require two canonical classes and exactly one raw "
                "class-1 positive logit"
            )
        self.num_classes = num_classes
        self.output_channels = resolved_channels
        self.task = task

    @abstractmethod
    def forward(self, pixel_values: Tensor) -> Tensor:
        """Return (N, output_channels, H, W) logits at input resolution."""

    def forward_output(self, pixel_values: Tensor) -> SegmentationOutput:
        """Return the richer training contract while preserving legacy models.

        Existing wrappers expose one dense tensor and inherit this adapter. Native
        models override it when they have auxiliary or query predictions that the
        training engine must not silently discard.
        """
        return SegmentationOutput(dense_logits=self(pixel_values))

    @abstractmethod
    def head_patterns(self) -> tuple[str, ...]:
        """Substrings that identify head parameters in ``named_parameters()``.

        Used by the optimiser to give the head its higher learning rate and by
        PEFT to keep the head fully trainable under LoRA.
        """

    @abstractmethod
    def backbone_modules(self) -> list[nn.Module]:
        """The pretrained feature extractor(s), i.e. everything that is not head."""

    @abstractmethod
    def reset_head(self) -> None:
        """Re-initialise the final classifier only, leaving the rest untouched."""

    def reset_head_state_keys(self) -> tuple[str, ...]:
        """Non-parameter state that belongs to the task classifier.

        Most models keep all class-count-dependent state in Conv2d/Linear
        classifier parameters, which :meth:`reset_head` discovers by mutation.
        A wrapper may return exact additional ``state_dict`` keys here when an
        upstream architecture stores class-count-dependent buffers outside that
        classifier module.  Curriculum hand-off preserves the freshly built
        target values for only these declared keys and still requires every
        other checkpoint tensor to match exactly.
        """

        return ()

    def _check_output(self, logits: Tensor, pixel_values: Tensor) -> Tensor:
        if logits.shape[1] != self.output_channels:
            raise ValueError(
                f"{type(self).__name__} produced {logits.shape[1]} channels but was built "
                f"for {self.output_channels} {self.task} output channel(s)"
            )
        if logits.shape[-2:] != pixel_values.shape[-2:]:
            raise ValueError(
                f"{type(self).__name__} produced {tuple(logits.shape[-2:])} but the input was "
                f"{tuple(pixel_values.shape[-2:])}; the contract is input-resolution logits"
            )
        return logits

    def enforce_inactive_parameters(self) -> set[str]:
        """Freeze audited loss-unreachable parameters; ordinary models have none."""
        return set()


class HFDenseWrapper(SegmentationModel):
    """SegformerForSemanticSegmentation / UperNetForSemanticSegmentation.

    Args:
        model: the HuggingFace model, already built with the right ``num_labels``.
        num_classes: canonical class count.
        backbone_path: dotted path to the encoder submodule.
        head_paths: parameter-name substrings identifying the decode head(s).
        classifier_component: final path component of the modules ``reset_head``
            re-initialises.
    """

    def __init__(
        self,
        model: nn.Module,
        num_classes: int,
        backbone_path: str,
        head_paths: tuple[str, ...],
        classifier_component: str = "classifier",
    ) -> None:
        super().__init__(num_classes)
        self.model = model
        self.backbone_path = backbone_path
        self.head_paths = head_paths
        self.classifier_component = classifier_component

    def forward(self, pixel_values: Tensor) -> Tensor:
        # No labels=: the internal loss knows nothing about inactive classes.
        out = self.model(pixel_values=pixel_values)
        logits = resize_logits(out.logits, tuple(pixel_values.shape[-2:]))
        return self._check_output(logits, pixel_values)

    def head_patterns(self) -> tuple[str, ...]:
        return self.head_paths

    def backbone_modules(self) -> list[nn.Module]:
        return [resolve(self.model, self.backbone_path)]

    def reset_head(self) -> None:
        reinit_component_(self, self.classifier_component)


class SMPWrapper(SegmentationModel):
    """segmentation_models_pytorch model: already full resolution, nothing to resize.

    Args:
        model: an smp model with ``.encoder``, ``.decoder`` and ``.segmentation_head``.
        num_classes: canonical class count.
    """

    def __init__(
        self,
        model: nn.Module,
        num_classes: int,
        *,
        input_mean: tuple[float, float, float],
        input_std: tuple[float, float, float],
        input_channel_order: str,
        input_normalization_source: str,
        inactive_parameter_paths: tuple[str, ...] = (),
    ) -> None:
        super().__init__(num_classes)
        missing = [a for a in ("encoder", "decoder", "segmentation_head") if not hasattr(model, a)]
        if missing:
            raise ValueError(
                f"SMPWrapper expects an smp model with {missing}; got {type(model).__name__}"
            )
        self.model = model
        self.input_mean = input_mean
        self.input_std = input_std
        self.input_channel_order = input_channel_order
        self.input_normalization_source = input_normalization_source
        self.inactive_parameter_paths = inactive_parameter_paths
        self.enforce_inactive_parameters()

    def forward(self, pixel_values: Tensor) -> Tensor:
        return self._check_output(self.model(pixel_values), pixel_values)

    def head_patterns(self) -> tuple[str, ...]:
        # The smp decoder is randomly initialised, so it belongs on the head
        # learning rate alongside the classifier, not on the backbone's.
        return ("decoder.", "segmentation_head.")

    def backbone_modules(self) -> list[nn.Module]:
        return [resolve(self.model, "encoder")]

    def reset_head(self) -> None:
        reinit_component_(self, "segmentation_head")

    def enforce_inactive_parameters(self) -> set[str]:
        """Freeze exact, audited modules retained but bypassed by this SMP recipe."""
        frozen: set[str] = set()
        for path in self.inactive_parameter_paths:
            if not path.startswith("encoder."):
                raise ValueError(
                    f"SMP inactive parameter path {path!r} must be a strict descendant "
                    "of encoder; decoder and segmentation head paths cannot be disabled"
                )
            try:
                module = self.model.get_submodule(path)
            except AttributeError as exc:
                raise ValueError(
                    f"SMP inactive parameter path {path!r} does not exist on "
                    f"{type(self.model).__name__}"
                ) from exc
            parameters = list(module.named_parameters())
            if not parameters:
                raise ValueError(f"SMP inactive parameter path {path!r} has no parameters")
            for name, parameter in parameters:
                parameter.requires_grad_(False)
                frozen.add(f"model.{path}.{name}" if name else f"model.{path}")
        return frozen
