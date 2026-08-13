"""Map a parameter name to its depth in the backbone, for layer-wise LR decay.

A pretrained encoder is only worth fine-tuning if its early layers move slowly:
generic edge/texture filters transfer, task-specific top blocks do not. LLRD
encodes that as ``lr = backbone_lr * llrd ** (max_depth - depth)``, which is only
as good as ``depth``. Getting it wrong is silent -- the run still converges, just
to a worse optimum -- so depths come from the model's real parameter names rather
than from a hardcoded per-architecture table.

Names, not attributes: the encoder is wrapped several deep (SegmentationModel ->
HF model -> backbone -> stages) and PEFT re-parents the whole tree under
``base_model.model``, so attribute walking finds nothing. Names survive all of it.

Two naming families have to be handled. Plain ViTs (EoMT, DINOv3) number their
blocks flat, so the index is the depth. Hierarchical encoders (SegFormer/MiT,
ConvNeXt, Swin) nest ``(stage, block)`` and must be flattened against the real
per-stage block counts before the LLRD exponent means anything.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from torch import nn

DEFAULT_HEAD_PATTERNS: tuple[str, ...] = ("decode_head", "classifier")

# The stage container is "stages" for SegFormer/MiT and both HF and timm
# ConvNeXt, "layers" for Swin; the inner block list is "blocks" everywhere except
# HF ConvNeXt, which calls it "layers".
_HIER_BLOCK = re.compile(r"(?:^|\.)(?:stages|layers)\.(\d+)\.(?:blocks|layers)\.(\d+)\.")
_HIER_STAGE = re.compile(r"(?:^|\.)(?:stages|layers)\.(\d+)\.")
# Only this spelling may *demand* stage counts: a bare "layers.N." is how a plain
# ViT names its flat block list, and treating that as a stage would be wrong.
_STAGES_ONLY = re.compile(r"(?:^|\.)stages\.(\d+)\.")
_VIT_BLOCK = re.compile(r"(?:^|\.)(?:blocks|layers|encoder\.layer|layer)\.(\d+)\.")
_STEM = re.compile(
    r"patch_embed|cls_token|class_token|pos_embed|position_embed|(?:^|\.)embeddings\."
)
_TRAILING_NORM = re.compile(r"(?:^|\.)(?:norm|layernorm|layer_norm|ln)\d*\.(?:weight|bias)$")
# Stage-level tensors that run *before* the stage's blocks rather than after.
_STAGE_ENTRY = ("patch_embed", "downsampl", "reduction")


@dataclass(frozen=True)
class LayerLayout:
    """Depth layout discovered from a live module.

    ``num_layers`` is the total number of blocks in the backbone; depth 0 is the
    stem, blocks occupy 1..num_layers and the head sits at num_layers + 1.
    ``stage_blocks`` is non-empty only for hierarchical encoders, where it holds
    the per-stage block counts needed to flatten (stage, block) into a global
    index. ``num_layers == 0`` means no numbered block list was found at all,
    which is the normal answer for a ResNet/HRNet trunk.
    """

    num_layers: int
    stage_blocks: tuple[int, ...] | None

    @property
    def max_depth(self) -> int:
        return self.num_layers + 1


def is_head(name: str, head_patterns: Sequence[str]) -> bool:
    """True if ``name`` belongs to the task head rather than the pretrained trunk."""
    return any(pattern in name for pattern in head_patterns)


def _stage_blocks(model: nn.Module, head_patterns: Sequence[str]) -> tuple[int, ...] | None:
    # Head parameters are excluded because a Mask2Former-style decoder also
    # contains numbered layer stacks, and counting those would shift every
    # backbone depth.
    counts: dict[int, int] = {}
    for name, _ in model.named_parameters():
        if is_head(name, head_patterns):
            continue
        match = _HIER_BLOCK.search(name)
        if match is not None:
            stage, block = int(match.group(1)), int(match.group(2))
            counts[stage] = max(counts.get(stage, -1), block)
    if not counts:
        return None
    stages = sorted(counts)
    if stages != list(range(len(stages))):
        raise ValueError(
            f"hierarchical encoder has non-contiguous stage indices {stages}; layer-wise "
            f"decay cannot order it, set llrd=1.0"
        )
    return tuple(counts[s] + 1 for s in stages)


def discover_layout(model: nn.Module, head_patterns: Sequence[str]) -> LayerLayout:
    """Measure ``model``'s block layout from its parameter names."""
    stage_blocks = _stage_blocks(model, head_patterns)
    if stage_blocks is not None:
        return LayerLayout(num_layers=sum(stage_blocks), stage_blocks=stage_blocks)

    highest = -1
    for name, _ in model.named_parameters():
        if is_head(name, head_patterns):
            continue
        match = _VIT_BLOCK.search(name)
        if match is not None:
            highest = max(highest, int(match.group(1)))
    return LayerLayout(num_layers=highest + 1, stage_blocks=None)


def assign_layer_id(
    param_name: str,
    num_layers: int,
    head_patterns: Sequence[str],
    *,
    stage_blocks: Sequence[int] | None = None,
) -> int:
    """Depth of ``param_name``: 0 for the stem, 1..num_layers per block, num_layers + 1 for the head.

    Args:
        param_name: fully qualified name as produced by ``model.named_parameters()``.
        num_layers: total blocks in the backbone.
        head_patterns: substrings marking a parameter as belonging to the head.
        stage_blocks: per-stage block counts, required for hierarchical
            (SegFormer/MiT, ConvNeXt, Swin) names so that (stage, block) can be
            flattened into a global block index.

    Unrecognised names fall back to depth 0, the most conservative choice: an
    unknown parameter is treated as stem-like and gets the smallest LR.
    """
    if num_layers < 0:
        raise ValueError(f"num_layers must be >= 0, got {num_layers}")
    if is_head(param_name, head_patterns):
        return num_layers + 1

    if stage_blocks is None:
        if _STAGES_ONLY.search(param_name):
            raise ValueError(
                f"{param_name!r} uses hierarchical stage naming but stage_blocks was not "
                f"given; pass the model's actual per-stage block counts so (stage, block) "
                f"can be flattened into a global depth"
            )
    else:
        counts = tuple(stage_blocks)
        block = _HIER_BLOCK.search(param_name)
        stage = block or _HIER_STAGE.search(param_name)
        if stage is not None:
            index = int(stage.group(1))
            if index >= len(counts):
                raise ValueError(
                    f"{param_name!r} refers to stage {index} but the model reports only "
                    f"{len(counts)} stages; the discovered layout does not match the model"
                )
            offset = sum(counts[:index])
            if block is not None:
                depth = offset + int(block.group(2)) + 1
            elif any(token in param_name for token in _STAGE_ENTRY):
                # Patch embeddings and downsampling layers feed the stage's first
                # block, so they sit at its entry depth; stage 0's is the stem.
                depth = offset
            else:
                # Everything else at stage level (the trailing layer_norm) follows
                # the stage's last block. Clamping stage-level tensors into the
                # surrounding block depths keeps depth monotone in parameter order
                # without inventing extra levels.
                depth = offset + counts[index]
            return _checked(depth, num_layers, param_name)

    vit = _VIT_BLOCK.search(param_name)
    if vit is not None:
        return _checked(int(vit.group(1)) + 1, num_layers, param_name)
    if _STEM.search(param_name):
        return 0
    if _TRAILING_NORM.search(param_name):
        return num_layers  # final encoder norm sits after the last block
    return 0


def _checked(depth: int, num_layers: int, param_name: str) -> int:
    if depth > num_layers:
        raise ValueError(
            f"{param_name!r} maps to depth {depth} but the backbone was measured at "
            f"{num_layers} blocks; layer-wise decay would use a wrong exponent"
        )
    return depth
