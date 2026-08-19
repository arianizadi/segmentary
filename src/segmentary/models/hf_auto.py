"""Conservative ``AutoModelForSemanticSegmentation`` integration.

The Hugging Face auto class is intentionally used as a loader, not as a promise
that every model registered under it satisfies Segmentary's training contract.
This module proves the pieces Segmentary relies on before returning a model:

* pretrained loading changed only the final classifier when label counts differ,
  apart from a completely audited auxiliary head that Segmentary deliberately drops;
* processor normalization and RGB/BGR channel order are reproduced by the data pipeline;
* backbone, trainable head, and final classifier paths are unambiguous;
* every parameter belongs to exactly one of backbone or head; and
* forward output is dense ``.logits`` which can be resized to input resolution.

An upstream layout that cannot be proven automatically fails with instructions
to provide the three explicit layout fields.  Repository-defined Python remains
disabled; supporting a new architecture must not imply executing remote code.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from torch import Tensor, nn

from ..config import ModelConfig
from ..data.transforms import IMAGENET_MEAN, IMAGENET_STD
from .wrappers import SegmentationModel, reinit_, resize_logits, resolve

_MISSING_PROCESSOR_FIELD = object()


@dataclass(frozen=True)
class HFLayout:
    """Validated module boundaries for one loaded HF segmentation model."""

    backbone_path: str
    head_paths: tuple[str, ...]
    classifier_path: str


@dataclass(frozen=True)
class ShapeMismatch:
    """One shape mismatch reported by ``from_pretrained``."""

    key: str
    checkpoint_shape: tuple[int, ...]
    model_shape: tuple[int, ...]


class HFAutoDenseWrapper(SegmentationModel):
    """A validated HF semantic-segmentation model with Segmentary's dense contract."""

    def __init__(
        self,
        model: nn.Module,
        num_classes: int,
        layout: HFLayout,
        *,
        source_num_labels: int,
        input_mean: tuple[float, float, float] = IMAGENET_MEAN,
        input_std: tuple[float, float, float] = IMAGENET_STD,
        input_channel_order: str = "rgb",
        inactive_parameter_paths: tuple[str, ...] = (),
    ) -> None:
        super().__init__(num_classes)
        self.model = model
        self.layout = layout
        self.source_num_labels = source_num_labels
        self.input_mean = input_mean
        self.input_std = input_std
        self.input_channel_order = input_channel_order
        self.input_normalization_source = "hf_image_processor"
        self.inactive_parameter_paths = inactive_parameter_paths
        for path in inactive_parameter_paths:
            if not path.startswith(layout.backbone_path + "."):
                raise ValueError(
                    f"hf_auto inactive parameter path {path!r} must be a strict descendant "
                    f"of backbone {layout.backbone_path!r}"
                )
        self.enforce_inactive_parameters()

    def forward(self, pixel_values: Tensor) -> Tensor:
        # No labels=: upstream losses do not implement Segmentary's per-sample
        # inactive-class masking or its configured auxiliary loss.
        output = self.model(pixel_values=pixel_values)
        logits = getattr(output, "logits", None)
        if not isinstance(logits, Tensor):
            raise ValueError(
                f"{type(self.model).__name__} did not return a tensor at output.logits; "
                "this AutoModelForSemanticSegmentation implementation is unsupported"
            )
        if logits.ndim != 4 or logits.shape[0] != pixel_values.shape[0]:
            raise ValueError(
                f"{type(self.model).__name__} returned logits with shape "
                f"{tuple(logits.shape)}; expected (N, C, H, W) with batch "
                f"{pixel_values.shape[0]}"
            )
        logits = resize_logits(logits, tuple(pixel_values.shape[-2:]))
        return self._check_output(logits, pixel_values)

    def head_patterns(self) -> tuple[str, ...]:
        return self.layout.head_paths

    def backbone_modules(self) -> list[nn.Module]:
        return [resolve(self.model, self.layout.backbone_path)]

    def reset_head(self) -> None:
        classifier = resolve(self.model, self.layout.classifier_path)
        hits = reinit_(classifier)
        if hits != 1:
            raise ValueError(
                f"hf_auto classifier {self.layout.classifier_path!r} reinitialised {hits} "
                "Conv2d/Linear modules, expected exactly one final classifier"
            )

    def enforce_inactive_parameters(self) -> set[str]:
        """Freeze only explicitly audited upstream modules absent from dense logits."""
        frozen: set[str] = set()
        for path in self.inactive_parameter_paths:
            try:
                module = resolve(self.model, path)
            except ValueError as exc:
                raise ValueError(
                    f"hf_auto inactive parameter path {path!r} does not exist on "
                    f"{type(self.model).__name__}"
                ) from exc
            parameters = list(module.named_parameters())
            if not parameters:
                raise ValueError(f"hf_auto inactive parameter path {path!r} has no parameters")
            for name, parameter in parameters:
                parameter.requires_grad_(False)
                frozen.add(f"model.{path}.{name}" if name else f"model.{path}")
        return frozen


def _hub_kwargs(cfg: ModelConfig) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "local_files_only": cfg.local_files_only,
        # Config validation makes True impossible, but spell this out at the
        # trust boundary instead of forwarding an unchecked config value.
        "trust_remote_code": False,
    }
    if cfg.revision is not None:
        kwargs["revision"] = cfg.revision
    if cfg.subfolder is not None:
        kwargs["subfolder"] = cfg.subfolder
    return kwargs


def _processor_normalization(
    processor: Any, checkpoint: str
) -> tuple[tuple[float, float, float], tuple[float, float, float], str]:
    """Audit normalization and channel order Segmentary must reproduce."""
    do_rescale = getattr(processor, "do_rescale", _MISSING_PROCESSOR_FIELD)
    if do_rescale is _MISSING_PROCESSOR_FIELD:
        raise ValueError(
            f"hf_auto image processor for {checkpoint!r} does not expose do_rescale; "
            "Segmentary cannot prove its pixel preprocessing contract"
        )
    if do_rescale is not True:
        raise ValueError(
            f"hf_auto image processor for {checkpoint!r} does not rescale uint8 pixels; "
            "Segmentary currently requires the standard 1/255 preprocessing contract"
        )
    factor = getattr(processor, "rescale_factor", _MISSING_PROCESSOR_FIELD)
    if factor is _MISSING_PROCESSOR_FIELD:
        raise ValueError(
            f"hf_auto image processor for {checkpoint!r} does not expose rescale_factor; "
            "Segmentary cannot prove its pixel preprocessing contract"
        )
    if (
        isinstance(factor, bool)
        or not isinstance(factor, (int, float))
        or not abs(float(factor) - 1.0 / 255.0) < 1e-12
    ):
        raise ValueError(
            f"hf_auto image processor for {checkpoint!r} uses rescale_factor={factor!r}; "
            "only the standard 1/255 factor is supported"
        )
    channel_flags = [
        getattr(processor, name)
        for name in ("do_flip_channel_order", "do_flip_channels")
        if hasattr(processor, name)
    ]
    if any(value not in (True, False, None) for value in channel_flags):
        raise ValueError(
            f"hf_auto image processor for {checkpoint!r} has invalid channel-order "
            f"flags {channel_flags!r}"
        )
    concrete_flags = {value for value in channel_flags if value is not None}
    if len(concrete_flags) > 1:
        raise ValueError(
            f"hf_auto image processor for {checkpoint!r} has conflicting channel-order "
            f"flags {channel_flags!r}"
        )
    channel_order = "bgr" if True in concrete_flags else "rgb"

    do_normalize = getattr(processor, "do_normalize", _MISSING_PROCESSOR_FIELD)
    if do_normalize is _MISSING_PROCESSOR_FIELD:
        raise ValueError(
            f"hf_auto image processor for {checkpoint!r} does not expose do_normalize; "
            "Segmentary cannot prove its normalization contract"
        )
    if do_normalize not in (True, False, None):
        raise ValueError(
            f"hf_auto image processor for {checkpoint!r} has invalid do_normalize={do_normalize!r}"
        )
    if do_normalize is not True:
        return (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), channel_order

    def triplet(name: str) -> tuple[float, float, float]:
        raw = getattr(processor, name, None)
        if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)) or len(raw) != 3:
            raise ValueError(
                f"hf_auto image processor for {checkpoint!r} has invalid {name}={raw!r}; "
                "Segmentary's RGB loader requires three channel statistics"
            )
        values = tuple(float(value) for value in raw)
        if any(not value == value or value in (float("inf"), float("-inf")) for value in values):
            raise ValueError(f"hf_auto image processor has non-finite {name}={raw!r}")
        if name == "image_std" and any(value <= 0.0 for value in values):
            raise ValueError(f"hf_auto image processor has non-positive image_std={raw!r}")
        return values  # type: ignore[return-value]

    return triplet("image_mean"), triplet("image_std"), channel_order


def _shape(value: Any, *, key: str, side: str) -> tuple[int, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ValueError(
            f"hf_auto could not audit shape mismatch {key!r}: {side} shape "
            f"{value!r} is not a dimension sequence"
        )
    dims = tuple(value)
    if not dims or any(isinstance(dim, bool) or not isinstance(dim, int) for dim in dims):
        raise ValueError(
            f"hf_auto could not audit shape mismatch {key!r}: invalid {side} shape {value!r}"
        )
    return dims


def _mapping_value(item: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in item:
            return item[name]
    return None


def _parse_mismatch(item: Any) -> ShapeMismatch:
    """Normalise loading-info formats used across Transformers releases."""
    if isinstance(item, Mapping):
        key = _mapping_value(item, "key", "name")
        checkpoint_shape = _mapping_value(
            item, "checkpoint_shape", "shape_checkpoint", "loaded_shape"
        )
        model_shape = _mapping_value(item, "model_shape", "shape_model", "expected_shape")
    elif isinstance(item, (tuple, list)) and len(item) == 3:
        key, checkpoint_shape, model_shape = item
    else:
        raise ValueError(
            "hf_auto received a shape mismatch without auditable key/shape data from "
            f"Transformers: {item!r}"
        )
    if not isinstance(key, str) or not key:
        raise ValueError(f"hf_auto received an invalid mismatched parameter key: {key!r}")
    return ShapeMismatch(
        key=key,
        checkpoint_shape=_shape(checkpoint_shape, key=key, side="checkpoint"),
        model_shape=_shape(model_shape, key=key, side="model"),
    )


def _loading_info(info: Any) -> tuple[list[str], list[str], list[ShapeMismatch]]:
    if not isinstance(info, Mapping):
        raise ValueError(
            "AutoModelForSemanticSegmentation did not return loading diagnostics; "
            "hf_auto cannot prove that pretrained weights loaded completely"
        )
    required = {"missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs"}
    absent = sorted(required - set(info))
    if absent:
        raise ValueError(
            f"Transformers loading diagnostics omit {absent}; hf_auto cannot audit the load"
        )

    collection_types = (tuple, list, set, frozenset)
    errors = info["error_msgs"]
    if not isinstance(errors, collection_types):
        raise ValueError("Transformers loading diagnostics error_msgs is not a collection")
    if errors:
        raise ValueError(f"hf_auto checkpoint loading reported errors: {errors}")

    def keys(name: str) -> list[str]:
        values = info[name]
        if not isinstance(values, collection_types) or any(
            not isinstance(value, str) or not value for value in values
        ):
            raise ValueError(f"Transformers loading diagnostics {name} is not a key collection")
        return list(values)

    mismatched = info["mismatched_keys"]
    if not isinstance(mismatched, collection_types):
        raise ValueError("Transformers loading diagnostics mismatched_keys is not a collection")
    return (
        keys("missing_keys"),
        keys("unexpected_keys"),
        [_parse_mismatch(item) for item in mismatched],
    )


def _has_parameters(module: nn.Module) -> bool:
    return next(module.parameters(), None) is not None


def _path_contains(parent: str, child: str) -> bool:
    return child == parent or child.startswith(parent + ".")


def _classifier_output(module: nn.Module) -> int | None:
    if isinstance(module, nn.Conv2d):
        return module.out_channels
    if isinstance(module, nn.Linear):
        return module.out_features
    return None


def _infer_classifier(
    model: nn.Module,
    head_paths: tuple[str, ...],
    mismatches: list[ShapeMismatch],
    num_classes: int,
) -> str:
    if mismatches:
        paths: set[str] = set()
        for mismatch in mismatches:
            try:
                model.get_parameter(mismatch.key)
            except AttributeError as exc:
                raise ValueError(
                    f"Transformers reported mismatch {mismatch.key!r}, which is not a "
                    "parameter of the constructed model"
                ) from exc
            if "." not in mismatch.key:
                raise ValueError(
                    f"cannot derive a classifier module from parameter {mismatch.key!r}"
                )
            paths.add(mismatch.key.rsplit(".", 1)[0])
        if len(paths) != 1:
            raise ValueError(
                f"pretrained shape mismatches span modules {sorted(paths)}; only one final "
                "classifier may change shape"
            )
        return paths.pop()

    candidates = [
        name
        for name, module in model.named_modules()
        if name
        and any(_path_contains(head, name) for head in head_paths)
        and _classifier_output(module) == num_classes
    ]
    if len(candidates) != 1:
        raise ValueError(
            f"could not infer one final {num_classes}-class Conv2d/Linear under heads "
            f"{head_paths}; candidates={candidates}. Set model.backbone_path, "
            "model.head_paths, and model.classifier_path explicitly."
        )
    return candidates[0]


def _infer_layout(model: nn.Module, mismatches: list[ShapeMismatch], num_classes: int) -> HFLayout:
    backbone_path = getattr(model, "base_model_prefix", None)
    if not isinstance(backbone_path, str) or not backbone_path or "." in backbone_path:
        raise ValueError(
            f"{type(model).__name__} has no unambiguous top-level base_model_prefix; set "
            "the complete advanced hf_auto layout explicitly"
        )
    children = dict(model.named_children())
    if backbone_path not in children:
        raise ValueError(
            f"{type(model).__name__}.base_model_prefix={backbone_path!r} is not a top-level "
            "submodule; set the complete advanced hf_auto layout explicitly"
        )
    head_paths = tuple(
        name
        for name, module in model.named_children()
        if name != backbone_path and _has_parameters(module)
    )
    if not head_paths:
        raise ValueError(
            f"{type(model).__name__} exposes no parameterised head outside "
            f"base_model_prefix={backbone_path!r}; this layout is unsupported"
        )
    return HFLayout(
        backbone_path=backbone_path,
        head_paths=head_paths,
        classifier_path=_infer_classifier(model, head_paths, mismatches, num_classes),
    )


def _explicit_or_inferred_layout(
    cfg: ModelConfig,
    model: nn.Module,
    mismatches: list[ShapeMismatch],
    num_classes: int,
) -> HFLayout:
    if cfg.backbone_path is None:
        return _infer_layout(model, mismatches, num_classes)
    assert cfg.classifier_path is not None and cfg.head_paths
    return HFLayout(cfg.backbone_path, tuple(cfg.head_paths), cfg.classifier_path)


def _validate_layout(model: nn.Module, layout: HFLayout, num_classes: int) -> nn.Module:
    paths = (layout.backbone_path, *layout.head_paths, layout.classifier_path)
    modules: dict[str, nn.Module] = {}
    for path in paths:
        try:
            modules[path] = model.get_submodule(path)
        except AttributeError as exc:
            raise ValueError(
                f"hf_auto module path {path!r} does not exist on {type(model).__name__}"
            ) from exc

    if not _has_parameters(modules[layout.backbone_path]):
        raise ValueError(f"hf_auto backbone {layout.backbone_path!r} has no parameters")
    for head in layout.head_paths:
        if not _has_parameters(modules[head]):
            raise ValueError(f"hf_auto head {head!r} has no parameters")
        suffix_matches = [name for name, _ in model.named_modules() if name.endswith(head)]
        if suffix_matches != [head]:
            raise ValueError(
                f"hf_auto head path {head!r} is ambiguous for LoRA modules_to_save; "
                f"suffix matches are {suffix_matches}"
            )

    classifier = modules[layout.classifier_path]
    output_classes = _classifier_output(classifier)
    if output_classes != num_classes:
        raise ValueError(
            f"hf_auto classifier {layout.classifier_path!r} is "
            f"{type(classifier).__name__} with output size {output_classes}; expected one "
            f"Conv2d/Linear producing {num_classes} classes"
        )
    if not any(_path_contains(head, layout.classifier_path) for head in layout.head_paths):
        raise ValueError(
            f"hf_auto classifier {layout.classifier_path!r} is not inside selected heads "
            f"{layout.head_paths}"
        )

    partition_paths = (layout.backbone_path, *layout.head_paths)
    uncategorised: list[str] = []
    overlapping: list[str] = []
    for name, _ in model.named_parameters():
        owners = [path for path in partition_paths if _path_contains(path, name)]
        if not owners:
            uncategorised.append(name)
        elif len(owners) > 1:
            overlapping.append(name)
    if uncategorised or overlapping:
        raise ValueError(
            "hf_auto layout does not partition model parameters exactly; "
            f"uncategorised={uncategorised[:5]}, overlapping={overlapping[:5]}. Set the "
            "complete advanced layout explicitly."
        )
    return classifier


def _classifier_parameter_keys(model: nn.Module, layout: HFLayout) -> set[str]:
    classifier = model.get_submodule(layout.classifier_path)
    return {
        f"{layout.classifier_path}.{name}" for name, _ in classifier.named_parameters(recurse=False)
    }


def _validate_pretrained_load(
    model: nn.Module,
    layout: HFLayout,
    *,
    source_num_labels: int,
    num_classes: int,
    missing: list[str],
    unexpected: list[str],
    mismatches: list[ShapeMismatch],
    dropped_checkpoint_prefixes: tuple[str, ...] = (),
) -> None:
    mismatch_by_key = {item.key: item for item in mismatches}
    if len(mismatch_by_key) != len(mismatches):
        raise ValueError("Transformers reported the same mismatched parameter more than once")
    mismatch_keys = set(mismatch_by_key)

    allowed_dropped = {
        key
        for key in unexpected
        if any(key.startswith(prefix) for prefix in dropped_checkpoint_prefixes)
    }
    extra_problems = (set(missing) | (set(unexpected) - allowed_dropped)) - mismatch_keys
    if extra_problems:
        raise ValueError(
            "hf_auto refuses a partial pretrained load: missing/unexpected parameters "
            f"outside the reported classifier shape mismatch: {sorted(extra_problems)[:8]}"
        )

    classifier_keys = _classifier_parameter_keys(model, layout)
    if source_num_labels == num_classes:
        if mismatches or missing or set(unexpected) - allowed_dropped:
            raise ValueError(
                "checkpoint and requested model have the same label count, but pretrained "
                "loading was not exact"
            )
        return

    if mismatch_keys != classifier_keys:
        raise ValueError(
            f"label count changed {source_num_labels}->{num_classes}, but shape mismatches "
            f"{sorted(mismatch_keys)} are not exactly final classifier parameters "
            f"{sorted(classifier_keys)}"
        )

    state = dict(model.named_parameters())
    for key, mismatch in mismatch_by_key.items():
        actual = tuple(state[key].shape)
        if mismatch.model_shape != actual:
            raise ValueError(
                f"Transformers reported model shape {mismatch.model_shape} for {key!r}, "
                f"but the constructed parameter has shape {actual}"
            )
        if (
            mismatch.checkpoint_shape[0] != source_num_labels
            or mismatch.model_shape[0] != num_classes
            or mismatch.checkpoint_shape[1:] != mismatch.model_shape[1:]
        ):
            raise ValueError(
                f"{key!r} mismatch {mismatch.checkpoint_shape}->{mismatch.model_shape} is "
                f"not a classifier-only label-axis change {source_num_labels}->{num_classes}"
            )


def _transformers_auto_classes() -> tuple[Any, Any, Any]:
    """Import the three lazy Transformers auto classes at the call boundary."""
    from transformers import AutoConfig, AutoImageProcessor, AutoModelForSemanticSegmentation

    return AutoConfig, AutoImageProcessor, AutoModelForSemanticSegmentation


def _apply_batch_norm_momentum(model: nn.Module, momentum: float | None) -> int:
    """Apply one explicit PyTorch BatchNorm update coefficient, if requested."""
    if momentum is None:
        return 0
    batch_norm_types = (nn.BatchNorm1d, nn.BatchNorm2d, nn.BatchNorm3d, nn.SyncBatchNorm)
    modules = [module for module in model.modules() if isinstance(module, batch_norm_types)]
    if not modules:
        raise ValueError(
            "model.batch_norm_momentum was set, but the loaded hf_auto model has no "
            "PyTorch BatchNorm modules"
        )
    for module in modules:
        module.momentum = float(momentum)
    return len(modules)


def build_hf_auto(cfg: ModelConfig, num_classes: int) -> HFAutoDenseWrapper:
    """Load and validate one standard HF semantic-segmentation checkpoint."""
    AutoConfig, AutoImageProcessor, AutoModelForSemanticSegmentation = _transformers_auto_classes()

    assert cfg.checkpoint is not None  # ModelConfig validates hf_auto eagerly.
    hub_kwargs = _hub_kwargs(cfg)
    try:
        source_config = AutoConfig.from_pretrained(cfg.checkpoint, **hub_kwargs)
    except OSError as exc:
        raise ValueError(f"could not load Hugging Face config {cfg.checkpoint!r}: {exc}") from exc
    try:
        processor = AutoImageProcessor.from_pretrained(cfg.checkpoint, **hub_kwargs)
    except OSError as exc:
        raise ValueError(
            f"could not load Hugging Face image processor {cfg.checkpoint!r}: {exc}"
        ) from exc
    input_mean, input_std, input_channel_order = _processor_normalization(processor, cfg.checkpoint)

    source_num_labels = getattr(source_config, "num_labels", None)
    if (
        isinstance(source_num_labels, bool)
        or not isinstance(source_num_labels, int)
        or source_num_labels < 2
    ):
        raise ValueError(
            f"Hugging Face config {cfg.checkpoint!r} has invalid num_labels="
            f"{source_num_labels!r}; hf_auto needs a pretrained semantic classifier"
        )
    source_config.num_labels = num_classes
    # Segmentary has one explicit loss over dense logits.  Leaving an upstream
    # auxiliary head enabled either wastes parameters or triggers DDP unused-
    # parameter failures because the auto model returns only primary logits.
    dropped_checkpoint_prefixes: tuple[str, ...] = ()
    if getattr(source_config, "use_auxiliary_head", False) is True:
        source_config.use_auxiliary_head = False
        # BEiT and UPerNet checkpoints include a separately supervised auxiliary
        # branch. Segmentary owns one dense loss and cannot consume that branch, so
        # it is removed before construction. The load audit may ignore only this
        # exact prefix; any other missing/unexpected tensor remains fatal.
        dropped_checkpoint_prefixes = ("auxiliary_head.",)

    try:
        loaded = AutoModelForSemanticSegmentation.from_pretrained(
            cfg.checkpoint,
            config=source_config,
            ignore_mismatched_sizes=True,
            output_loading_info=True,
            **hub_kwargs,
        )
    except OSError as exc:
        raise ValueError(f"could not load Hugging Face model {cfg.checkpoint!r}: {exc}") from exc
    if not isinstance(loaded, tuple) or len(loaded) != 2 or not isinstance(loaded[0], nn.Module):
        raise ValueError(
            "AutoModelForSemanticSegmentation did not return (model, loading_info); "
            "hf_auto cannot audit the pretrained load"
        )
    model, raw_info = loaded
    _apply_batch_norm_momentum(model, cfg.batch_norm_momentum)
    missing, unexpected, mismatches = _loading_info(raw_info)
    layout = _explicit_or_inferred_layout(cfg, model, mismatches, num_classes)
    _validate_layout(model, layout, num_classes)
    _validate_pretrained_load(
        model,
        layout,
        source_num_labels=source_num_labels,
        num_classes=num_classes,
        missing=missing,
        unexpected=unexpected,
        mismatches=mismatches,
        dropped_checkpoint_prefixes=dropped_checkpoint_prefixes,
    )
    return HFAutoDenseWrapper(
        model,
        num_classes,
        layout,
        source_num_labels=source_num_labels,
        input_mean=input_mean,
        input_std=input_std,
        input_channel_order=input_channel_order,
        inactive_parameter_paths=tuple(cfg.inactive_parameter_paths),
    )
