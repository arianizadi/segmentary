"""Load the released Meta DINOv3 S/B/L checkpoints into Transformers locally.

The licensed downloads are plain Meta state dicts.  Transformers uses different
module names and splits Meta's fused QKV projection into three Linear layers, so
passing the ``.pth`` file to ``from_pretrained`` cannot work.  This converter is
strict in both directions: every model tensor must be initialised and every
checkpoint tensor must be consumed. Meta's persistent RoPE periods become
Transformers' non-persistent inverse-frequency buffer, and its fused masked QKV
bias becomes separate effective Q/V biases.

Only the LVD-1689M S/B/L checkpoints use the architecture implemented here: a
GELU MLP, fused QKV with a masked key bias, and one shared output LayerNorm.
S+/H+/7B use SwiGLU, 7B omits QKV bias, and the SAT checkpoints add a local-crop
normalisation that Transformers' DINOv3 backbone does not represent.  Those
schemas are rejected explicitly instead of being approximately loaded.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

import torch
from torch import Tensor, nn

# These are the three released FC-MLP shapes whose semantics were checked against
# Meta's implementation. Architecture is inferred from tensors, never filenames.
_ATTENTION_HEADS = {
    (384, 12): 6,
    (768, 12): 12,
    (1024, 24): 16,
}
_BLOCK_RE = re.compile(r"^blocks\.(\d+)\.")


def _reject_unsupported_schema(raw: Mapping[str, Tensor], path: Path) -> None:
    if "blocks.0.mlp.w1.weight" in raw:
        details = "SwiGLU MLP"
        if "blocks.0.attn.qkv.bias" not in raw:
            details += " and biasless QKV"
        raise ValueError(
            f"{path}: unsupported DINOv3 checkpoint schema ({details}). This converter "
            "supports only the released LVD-1689M ViT-S/B/L FC-MLP checkpoints; use "
            "Meta's native DINOv3 implementation for S+/H+/7B weights."
        )
    local_norms = sorted(key for key in raw if key.startswith("local_cls_norm."))
    if local_norms:
        raise ValueError(
            f"{path}: unsupported DINOv3 checkpoint schema (local-crop CLS norm). "
            "Transformers DINOv3ViTModel has no local_cls_norm module; use Meta's native "
            "DINOv3 implementation for SAT-493M or other local-norm weights."
        )


def _checkpoint_shape(raw: Mapping[str, Tensor], path: Path) -> tuple[int, int, int, int, int]:
    _reject_unsupported_schema(raw, path)
    required = {
        "cls_token",
        "storage_tokens",
        "mask_token",
        "patch_embed.proj.weight",
        "blocks.0.mlp.fc1.weight",
        "norm.weight",
    }
    missing = sorted(required - raw.keys())
    if missing:
        raise ValueError(f"{path}: not a DINOv3 ViT backbone checkpoint; missing {missing}")

    hidden = int(raw["cls_token"].shape[-1])
    intermediate = int(raw["blocks.0.mlp.fc1.weight"].shape[0])
    patch_weight = raw["patch_embed.proj.weight"]
    if patch_weight.ndim != 4 or patch_weight.shape[-1] != patch_weight.shape[-2]:
        raise ValueError(f"{path}: malformed patch projection {tuple(patch_weight.shape)}")
    patch_size = int(patch_weight.shape[-1])
    blocks = {int(match.group(1)) for key in raw if (match := _BLOCK_RE.match(key))}
    if not blocks or blocks != set(range(max(blocks) + 1)):
        raise ValueError(f"{path}: transformer block indices are not contiguous: {sorted(blocks)}")
    depth = len(blocks)
    try:
        heads = _ATTENTION_HEADS[(hidden, depth)]
    except KeyError as exc:
        raise ValueError(
            f"{path}: unsupported DINOv3 FC-MLP shape hidden={hidden}, depth={depth}; "
            f"supported LVD-1689M S/B/L shapes are {sorted(_ATTENTION_HEADS)}"
        ) from exc
    return hidden, intermediate, patch_size, depth, heads


def _convert_state_dict(raw: Mapping[str, Tensor], depth: int, path: Path) -> dict[str, Tensor]:
    converted: dict[str, Tensor] = {
        "embeddings.cls_token": raw["cls_token"],
        "embeddings.mask_token": raw["mask_token"].reshape(1, 1, -1),
        "embeddings.register_tokens": raw["storage_tokens"],
        "embeddings.patch_embeddings.weight": raw["patch_embed.proj.weight"],
        "embeddings.patch_embeddings.bias": raw["patch_embed.proj.bias"],
        "norm.weight": raw["norm.weight"],
        "norm.bias": raw["norm.bias"],
    }
    consumed = {
        "cls_token",
        "mask_token",
        "storage_tokens",
        "patch_embed.proj.weight",
        "patch_embed.proj.bias",
        "norm.weight",
        "norm.bias",
    }

    for index in range(depth):
        source = f"blocks.{index}."
        target = f"model.layer.{index}."
        for suffix in ("norm1.weight", "norm1.bias", "norm2.weight", "norm2.bias"):
            converted[target + suffix] = raw[source + suffix]
            consumed.add(source + suffix)

        q_weight, k_weight, v_weight = raw[source + "attn.qkv.weight"].chunk(3, dim=0)
        fused_bias = raw[source + "attn.qkv.bias"]
        bias_mask = raw[source + "attn.qkv.bias_mask"]
        if fused_bias.shape != bias_mask.shape:
            raise ValueError(
                f"{path}: {source} QKV bias shape {tuple(fused_bias.shape)} does not match "
                f"its mask {tuple(bias_mask.shape)}"
            )
        effective_bias = fused_bias * bias_mask.to(fused_bias.dtype)
        if not bool(torch.isfinite(effective_bias).all()):
            raise ValueError(f"{path}: {source} masked QKV bias contains non-finite values")
        q_bias, k_bias, v_bias = effective_bias.chunk(3, dim=0)
        if bool(torch.count_nonzero(k_bias)):
            raise ValueError(
                f"{path}: {source}attn.qkv.bias has a non-zero key-bias segment, but the "
                "Transformers DINOv3 architecture has key_bias=False"
            )
        converted.update(
            {
                target + "attention.q_proj.weight": q_weight,
                target + "attention.k_proj.weight": k_weight,
                target + "attention.v_proj.weight": v_weight,
                target + "attention.q_proj.bias": q_bias,
                target + "attention.v_proj.bias": v_bias,
                target + "attention.o_proj.weight": raw[source + "attn.proj.weight"],
                target + "attention.o_proj.bias": raw[source + "attn.proj.bias"],
                target + "layer_scale1.lambda1": raw[source + "ls1.gamma"],
                target + "layer_scale2.lambda1": raw[source + "ls2.gamma"],
                target + "mlp.up_proj.weight": raw[source + "mlp.fc1.weight"],
                target + "mlp.up_proj.bias": raw[source + "mlp.fc1.bias"],
                target + "mlp.down_proj.weight": raw[source + "mlp.fc2.weight"],
                target + "mlp.down_proj.bias": raw[source + "mlp.fc2.bias"],
            }
        )
        consumed.update(
            {
                source + "attn.qkv.weight",
                source + "attn.qkv.bias",
                source + "attn.qkv.bias_mask",
                source + "attn.proj.weight",
                source + "attn.proj.bias",
                source + "ls1.gamma",
                source + "ls2.gamma",
                source + "mlp.fc1.weight",
                source + "mlp.fc1.bias",
                source + "mlp.fc2.weight",
                source + "mlp.fc2.bias",
            }
        )

    # ``periods`` is installed into Transformers' non-persistent ``inv_freq``
    # buffer after strict parameter loading. QKV bias masks were applied above.
    consumed.add("rope_embed.periods")
    unexpected = sorted(set(raw) - consumed)
    if unexpected:
        raise ValueError(
            f"{path}: refusing to ignore {len(unexpected)} unknown checkpoint tensors; "
            f"first is {unexpected[0]!r}"
        )
    return converted


def _load_local(path: Path, *, backbone: bool) -> nn.Module:
    from transformers import DINOv3ViTBackbone, DINOv3ViTConfig, DINOv3ViTModel

    if not path.is_file():
        raise FileNotFoundError(f"DINOv3 checkpoint not found: {path}")
    raw = torch.load(path, map_location="cpu", weights_only=True, mmap=True)
    if not isinstance(raw, Mapping) or not all(isinstance(value, Tensor) for value in raw.values()):
        raise ValueError(f"{path}: expected a weights-only tensor mapping")
    hidden, intermediate, patch_size, depth, heads = _checkpoint_shape(raw, path)
    config = DINOv3ViTConfig(
        hidden_size=hidden,
        intermediate_size=intermediate,
        num_hidden_layers=depth,
        num_attention_heads=heads,
        patch_size=patch_size,
        num_register_tokens=int(raw["storage_tokens"].shape[1]),
        rope_theta=100.0,
        layerscale_value=1.0,
        query_bias=True,
        key_bias=False,
        value_bias=True,
        proj_bias=True,
        mlp_bias=True,
    )
    if backbone:
        config.out_indices = [round(depth * fraction / 4) for fraction in (1, 2, 3, 4)]
        model: nn.Module = DINOv3ViTBackbone(config)
    else:
        model = DINOv3ViTModel(config)
    converted = _convert_state_dict(raw, depth, path)
    model.load_state_dict(converted, strict=True)
    periods = raw["rope_embed.periods"]
    inv_freq = cast(Any, model.rope_embeddings).inv_freq
    if periods.ndim != 1 or periods.shape != inv_freq.shape:
        raise ValueError(
            f"{path}: RoPE periods shape {tuple(periods.shape)} does not match Transformers "
            f"inverse frequency shape {tuple(inv_freq.shape)}"
        )
    periods = periods.to(device=inv_freq.device, dtype=inv_freq.dtype)
    if not bool(torch.isfinite(periods).all()) or bool((periods <= 0).any()):
        raise ValueError(f"{path}: RoPE periods must be finite and positive")
    inv_freq.copy_(periods.reciprocal())
    return model


def load_local_dinov3_backbone(path: Path | str) -> nn.Module:
    """Load a licensed Meta ``.pth`` as a four-tap Transformers backbone."""
    return _load_local(Path(path), backbone=True)


def load_local_dinov3_model(path: Path | str) -> nn.Module:
    """Load the same checkpoint as a plain ``DINOv3ViTModel`` for verification."""
    return _load_local(Path(path), backbone=False)
