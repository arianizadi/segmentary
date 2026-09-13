"""Explicit CT architecture catalog and a fail-closed scratch construction boundary."""

from __future__ import annotations

import contextlib
import importlib
import socket
import sys
from collections.abc import Iterator
from types import ModuleType
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

    import safetensors.torch

    targets = (
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
    )
    # Each distinct original needs its own wrapper so aliases imported during
    # lazy construction can later recover the correct callable by identity.
    # Reusing one forbidden function loses that information for new modules.
    originals: dict[int, tuple[Any, Any]] = {}
    wrappers: dict[int, tuple[Any, Any]] = {}

    def blocker() -> Any:
        def forbidden(*args: Any, **kwargs: Any) -> Any:
            raise RuntimeError(
                "Scratch-only construction forbids weight loading and network access"
            )

        return forbidden

    for owner, name in targets:
        original = getattr(owner, name)
        if id(original) not in originals:
            replacement = blocker()
            originals[id(original)] = (original, replacement)
            wrappers[id(replacement)] = (replacement, original)

    def module_attributes() -> Iterator[tuple[ModuleType, str, Any]]:
        for module in list(sys.modules.values()):
            if isinstance(module, ModuleType):
                for name, value in list(vars(module).items()):
                    yield module, name, value

    with contextlib.ExitStack() as stack:
        try:
            for owner, name in targets:
                original = getattr(owner, name)
                # Shared targets (the two safe_open exports) have independent
                # owners but share the same replacement and original callable.
                replacement = originals[id(original)][1]
                stack.enter_context(patch.object(owner, name, replacement))
            for module, name, value in module_attributes():
                pair = originals.get(id(value))
                if pair is not None and value is pair[0]:
                    stack.enter_context(patch.object(module, name, pair[1]))
            yield
        finally:
            # Imports performed inside the guard can retain replacements in
            # module globals even after patch.object restores the source export.
            # Restore only our exact wrapper objects, including new aliases and
            # exception paths, before ExitStack restores pre-existing attributes.
            for module, name, value in module_attributes():
                pair = wrappers.get(id(value))
                if pair is not None and value is pair[0]:
                    setattr(module, name, pair[1])


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
