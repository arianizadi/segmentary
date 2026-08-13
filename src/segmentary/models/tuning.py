"""Freeze / LoRA / full-finetune, applied in place to a built SegmentationModel.

This module is the label-efficiency chapter's experimental variable, so its
failure modes are all loud. In particular a LoRA config whose target names do not
exist matches nothing, trains only the head, and still produces a plausible
learning curve -- that is the one bug that could invalidate a whole table, so it
raises instead.
"""

from __future__ import annotations

import re

import torch.nn as nn
from torch.nn.modules.batchnorm import _NormBase

from ..config import ModelConfig
from .wrappers import SegmentationModel

# Ordered by specificity; the first candidate whose every name exists among the
# backbone's Linear leaves wins.
_LORA_CANDIDATES: tuple[tuple[str, ...], ...] = (
    ("q_proj", "k_proj", "v_proj", "o_proj"),  # SegFormer 5.x, DINOv3 ViT
    ("q_proj", "k_proj", "v_proj", "out_proj"),  # EoMT
    ("query", "key", "value"),  # legacy transformers ViT/Swin naming
    ("qkv", "proj"),  # timm ViT
)


def count_trainable(model: nn.Module) -> tuple[int, int]:
    """Return ``(trainable_parameters, total_parameters)``."""
    total = sum(p.numel() for p in model.parameters())
    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    return trainable, total


def backbone_prefixes(model: SegmentationModel) -> list[str]:
    """Qualified names of the backbone submodules inside ``model``."""
    wanted = {id(m) for m in model.backbone_modules()}
    prefixes = [name for name, mod in model.named_modules() if id(mod) in wanted and name]
    if not prefixes:
        raise ValueError(
            f"{type(model).__name__}.backbone_modules() returned modules that are not part of "
            f"the model tree; LoRA could not be scoped to the backbone"
        )
    return prefixes


def _backbone_linear_leaves(model: SegmentationModel) -> set[str]:
    leaves: set[str] = set()
    for backbone in model.backbone_modules():
        for name, mod in backbone.named_modules():
            if isinstance(mod, nn.Linear):
                leaves.add(name.split(".")[-1])
    return leaves


def infer_lora_targets(model: SegmentationModel) -> tuple[str, ...]:
    """Pick attention projection names by introspecting the backbone.

    Guessing from the architecture string would rot the moment transformers
    renames something, which it did between 4.x and 5.x (``o_proj`` used to be
    ``attention.output.dense``).
    """
    leaves = _backbone_linear_leaves(model)
    for candidate in _LORA_CANDIDATES:
        if all(name in leaves for name in candidate):
            return candidate
    raise ValueError(
        f"could not infer LoRA targets for {type(model).__name__}: its backbone has Linear "
        f"layers named {sorted(leaves) or ['<none>']}, none of which match a known attention "
        f"layout {_LORA_CANDIDATES}. Set model.lora_targets explicitly in the config. "
        f"(A purely convolutional backbone such as ConvNeXt or ResNet has no attention "
        f"projections at all and cannot be tuned with LoRA as configured here.)"
    )


def _head_module_names(model: SegmentationModel) -> list[str]:
    """Head patterns reduced to suffixes PEFT's ``modules_to_save`` can match.

    PEFT matches with ``key.endswith(target_key)``, so the dotted prefix is kept
    rather than reduced to a leaf name. Mask2Former is the reason: it has both
    ``pixel_level_module.decoder`` and ``transformer_module.decoder``, and a bare
    ``"decoder"`` would wrap one inside the other and freeze the inner copy.
    """
    existing = [name for name, _ in model.named_modules()]
    names: list[str] = []
    matched: list[str] = []
    for pattern in model.head_patterns():
        name = pattern.strip(".")
        hits = [key for key in existing if key.endswith(name)]
        if not hits:
            raise ValueError(
                f"head pattern {pattern!r} does not name a module of "
                f"{type(model).__name__}; LoRA would leave the head frozen"
            )
        names.append(name)
        matched.extend(hits)
    if not names:
        raise ValueError(f"{type(model).__name__}.head_patterns() is empty")

    # endswith() also matches descendants: "head" matches "head.aux_head" too, and
    # PEFT then nests one wrapper inside the other and freezes the inner module.
    for outer in matched:
        for inner in matched:
            if inner.startswith(outer + "."):
                raise ValueError(
                    f"head patterns {tuple(model.head_patterns())} match both {outer!r} and its "
                    f"descendant {inner!r}. PEFT matches modules_to_save with key.endswith(), so "
                    f"it would wrap {inner!r} inside the wrapper it put on {outer!r} and leave the "
                    f"inner copy frozen. Rename the submodule so it does not end in its parent's "
                    f"name, or make head_patterns specific enough to name only one of the two."
                )
    return names


def _freeze_backbone_norms(model: SegmentationModel) -> None:
    """Keep running-stat norms in eval() whenever the model is training.

    A frozen backbone whose BatchNorm layers stay in train mode is not frozen:
    ``running_mean``/``running_var`` keep adapting to the new domain, so the
    features drift even though every weight is fixed. That silently turns the
    'frozen' arm of the label-efficiency comparison into a partial finetune.
    """
    norms = [
        m
        for backbone in model.backbone_modules()
        for m in backbone.modules()
        if isinstance(m, _NormBase)
    ]
    if not norms:
        return

    def _pre_forward(module: nn.Module, _args: tuple) -> None:
        if module.training:
            for norm in norms:
                norm.eval()

    model.register_forward_pre_hook(_pre_forward)


def apply_tuning(model: SegmentationModel, cfg: ModelConfig) -> SegmentationModel:
    """Apply ``cfg.tuning`` to ``model`` in place and return it.

    Args:
        model: a freshly built model; call before wrapping in DDP or EMA.
        cfg: the model config carrying ``tuning`` and the LoRA hyperparameters.
    """
    if cfg.tuning == "full":
        for p in model.parameters():
            p.requires_grad_(True)
        model.enforce_inactive_parameters()
        return model

    if cfg.tuning == "frozen":
        for p in model.parameters():
            p.requires_grad_(True)
        for backbone in model.backbone_modules():
            for p in backbone.parameters():
                p.requires_grad_(False)
        _freeze_backbone_norms(model)
        model.enforce_inactive_parameters()
        trainable, total = count_trainable(model)
        if trainable == 0:
            raise ValueError(
                "freezing the backbone left zero trainable parameters; head_patterns and "
                "backbone_modules overlap"
            )
        if trainable == total:
            raise ValueError("freezing the backbone changed nothing; backbone_modules is empty")
        return model

    if cfg.tuning != "lora":
        raise ValueError(f"unknown tuning mode {cfg.tuning!r}")
    model = _apply_lora(model, cfg)
    model.enforce_inactive_parameters()
    trainable_lora_a = [
        name
        for name, parameter in model.named_parameters()
        if "lora_A" in name and parameter.requires_grad
    ]
    trainable_lora_b = [
        name
        for name, parameter in model.named_parameters()
        if "lora_B" in name and parameter.requires_grad
    ]
    if not trainable_lora_a or not trainable_lora_b:
        raise ValueError(
            "audited inactive_parameter_paths froze every LoRA adapter; this would train "
            "only the head while reporting tuning='lora'. Remove the conflicting inactive "
            "path or target at least one loss-reachable attention projection."
        )
    return model


def _apply_lora(model: SegmentationModel, cfg: ModelConfig) -> SegmentationModel:
    from peft import LoraConfig, inject_adapter_in_model

    targets = tuple(cfg.lora_targets) if cfg.lora_targets else infer_lora_targets(model)
    prefixes = "|".join(re.escape(p) for p in backbone_prefixes(model))
    names = "|".join(re.escape(t) for t in targets)
    # Scoped to the backbone: an unanchored name list would also hit identically
    # named projections in a randomly initialised decoder, which must stay fully
    # trainable rather than being reduced to rank r.
    pattern = rf"(?:{prefixes})\..*\.(?:{names})"

    lora_cfg = LoraConfig(
        r=cfg.lora_r,
        lora_alpha=cfg.lora_alpha,
        lora_dropout=cfg.lora_dropout,
        bias="none",
        target_modules=pattern,
        modules_to_save=_head_module_names(model),
    )
    no_match = (
        f"LoRA matched zero modules with targets {targets} under backbone prefixes "
        f"{backbone_prefixes(model)}. A no-op LoRA trains only the head while reporting "
        f"itself as a parameter-efficient finetune, so this is fatal. Inspect the module "
        f"names with `[n for n, _ in model.named_modules()]` and set model.lora_targets."
    )
    # PEFT raises one of two different messages on an empty match, and neither says
    # which module names it did find. Replace both rather than letting them through.
    peft_empty_match = ("not found in the base model", "No modules were targeted")
    try:
        inject_adapter_in_model(lora_cfg, model)
    except ValueError as exc:
        if not any(msg in str(exc) for msg in peft_empty_match):
            raise
        raise ValueError(no_match) from exc

    # Backstop in case a future PEFT stops raising on an empty match.
    if not any(name.endswith("lora_A") for name, _ in model.named_modules()):
        raise ValueError(no_match)

    # The base weights are frozen but a BatchNorm in the backbone would keep
    # adapting its running stats, i.e. tune more than rank r behind the report.
    _freeze_backbone_norms(model)

    head_frozen = [
        name
        for name, p in model.named_parameters()
        if not p.requires_grad
        and "original_module" not in name
        and any(pat in name for pat in model.head_patterns())
    ]
    if head_frozen:
        raise ValueError(
            f"LoRA left {len(head_frozen)} head parameters frozen (e.g. {head_frozen[0]}); "
            f"the classifier must stay fully trainable"
        )
    return model
