"""Small, format-aware helpers shared by training, evaluation, and export."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import torch

from .engine.ema import EMA_CHECKPOINT_KEY


def read_checkpoint(path: Path) -> dict[str, Any]:
    """Load one trusted Segmentary/PyTorch checkpoint and require a mapping root."""
    state = torch.load(path, map_location="cpu", weights_only=False)
    if not isinstance(state, dict):
        raise RuntimeError(f"checkpoint {path} has {type(state).__name__} root, expected a dict")
    return state


def checkpoint_uses_lora(state: Mapping[str, Any]) -> bool:
    """Return whether saved model/EMA parameter names contain PEFT LoRA adapters."""
    candidates: list[object] = [state.get("state_dict")]
    ema = state.get(EMA_CHECKPOINT_KEY)
    if isinstance(ema, Mapping):
        candidates.append(ema.get("params"))
    # Raw state_dict checkpoints have tensors directly at the root.
    candidates.append(state)
    for candidate in candidates:
        if not isinstance(candidate, Mapping):
            continue
        if any(
            isinstance(name, str) and (".lora_A." in name or ".lora_B." in name)
            for name in candidate
        ):
            return True
    return False
