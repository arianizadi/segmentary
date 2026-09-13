"""Explicit CT architecture catalog and a fail-closed scratch construction boundary."""

from __future__ import annotations

import contextlib
import importlib
import socket
import sys
from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import torch
from torch import nn

_MODULES = ("models_2d", "models_3d", "models_mamba")


def _providers() -> Iterator[Any]:
    for name in _MODULES:
        yield importlib.import_module(f"segmentary.medical.{name}")


def catalog() -> list[dict[str, Any]]:
    return [
        dict(module.model_metadata(name), name=name)
        for module in _providers()
        for name in module.MODEL_NAMES
    ]


def model_metadata(name: str) -> dict[str, Any]:
    for module in _providers():
        if name in module.MODEL_NAMES:
            return dict(module.model_metadata(name), name=name)
    raise ValueError(f"Unknown medical model: {name}")


@contextlib.contextmanager
def scratch_only() -> Iterator[None]:
    """Block weight deserialization and network access during construction.

    This supplements audited random-init constructors, including cached weights;
    it is an accidental-loading tripwire, not a sandbox for arbitrary model code.
    It is a process-global guard; construct models in the isolated stage worker,
    not concurrently in another Python thread. Same-run resume happens outside it.
    """

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise RuntimeError("Scratch-only construction forbids weight loading and network access")

    import safetensors.torch

    with contextlib.ExitStack() as stack:
        for owner, name in (
            (torch, "load"),
            (torch.hub, "load_state_dict_from_url"),
            (torch.hub, "download_url_to_file"),
            (nn.Module, "load_state_dict"),
            (safetensors.torch, "load_file"),
            (safetensors.torch, "load_model"),
            (safetensors.torch, "load"),
            (safetensors, "safe_open"),
            (safetensors.torch, "safe_open"),
            (socket.socket, "connect"),
            (socket.socket, "connect_ex"),
        ):
            stack.enter_context(patch.object(owner, name, forbidden))
        for module_name, module in list(sys.modules.items()):
            if (
                module is not None
                and module_name.startswith(
                    ("transformers.", "timm.", "segmentation_models_pytorch.")
                )
                and "safe_open" in vars(module)
            ):
                stack.enter_context(patch.object(module, "safe_open", forbidden))
        yield


def build_model(
    name: str,
    *,
    in_channels: int = 1,
    num_classes: int = 3,
    patch_size: tuple[int, ...] = (128, 128),
    model_options: dict[str, Any] | None = None,
) -> nn.Module:
    if type(in_channels) is not int or in_channels < 1 or num_classes != 3:
        raise ValueError("Use positive CT channels and the three-class medical ontology")
    with scratch_only():
        for module in _providers():
            if name in module.MODEL_NAMES:
                result = module.build_model(
                    name,
                    in_channels=in_channels,
                    num_classes=num_classes,
                    patch_size=patch_size,
                    model_options=model_options,
                )
                if not isinstance(result, nn.Module):
                    raise TypeError("Model provider must return torch.nn.Module")
                return result
    raise ValueError(f"Unknown medical model: {name}")
