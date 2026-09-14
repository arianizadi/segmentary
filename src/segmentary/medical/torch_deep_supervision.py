"""Training-only decoder supervision for the unchanged scratch DynUNet trunk."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, cast

import torch
import torch.nn.functional as F
from torch import nn

OBJECTIVE = "dense_ce_dice_with_two_native_decoder_auxiliary_losses"
WEIGHTS = (4 / 7, 2 / 7, 1 / 7)


def supervision_metadata() -> dict[str, Any]:
    return {
        "objective": OBJECTIVE,
        "deep_supervision": {
            "auxiliary_scales": [2, 4],
            "loss_weights_finest_to_coarsest": list(WEIGHTS),
            "target_resampling": "nearest, on aligned native decoder grids",
            "inference": "primary full-resolution logits only; auxiliary heads not executed",
            "initialization": "unchanged primary construction; auxiliary initialization preserves RNG",
            "paper_training_reproduction": False,
        },
    }


class DeepSupervisedDynUNet(nn.Module):
    """Keep primary inference identical and supervise two intermediate decoders.

    Hooks exist only for the duration of ``training_loss`` and are always removed.
    They capture decoder features, not detached tensors. Auxiliary labels are
    nearest-neighbor downsampled categorical targets. Restrict training to aligned
    patches so implicit padding never contributes fabricated background targets.
    The ordinary inference adapter continues to accept arbitrary volume tiles.
    """

    def __init__(self, primary: nn.Module, filters: list[int], num_classes: int) -> None:
        super().__init__()
        if len(filters) < 4:
            raise ValueError("Deep supervision requires at least four DynUNet levels")
        self.primary: Any = primary
        # Match the control's primary parameters AND post-construction RNG. These
        # are new random auxiliary heads, never copied learned/checkpoint weights.
        with torch.random.fork_rng(devices=[]):
            self.auxiliary_heads = nn.ModuleList(
                nn.Conv3d(channels, num_classes, 1) for channels in filters[1:3]
            )
            for head in self.auxiliary_heads:
                assert isinstance(head, nn.Conv3d)
                nn.init.kaiming_normal_(head.weight, a=0.01)
                assert head.bias is not None
                nn.init.zeros_(head.bias)
        self.architecture_metadata: dict[str, Any] = deepcopy(
            cast(dict[str, Any], primary.architecture_metadata)
        )
        self.architecture_metadata.update(supervision_metadata())

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.primary(image)

    def training_loss(self, images: torch.Tensor, labels: torch.Tensor) -> torch.Tensor:
        from .torch_data import dice_ce

        if not self.training:
            raise ValueError("Deep supervision loss requires training mode")
        if images.ndim != 5 or labels.shape != (images.shape[0], *images.shape[2:]):
            raise ValueError(
                "Deep supervision requires aligned N,C,D,H,W images and N,D,H,W labels"
            )
        if any(
            size < self.primary.minimum or size % self.primary.multiple for size in images.shape[2:]
        ):
            raise ValueError("Deep supervision training patches must align to the DynUNet grid")
        captured: dict[int, torch.Tensor] = {}

        def capture(index: int):
            def hook(_module: nn.Module, _inputs: Any, output: torch.Tensor) -> None:
                if index in captured:
                    raise RuntimeError("Decoder feature was produced more than once")
                captured[index] = output

            return hook

        handles = []
        try:
            for index in range(2):
                decoder = self.primary.network.upsamples[-2 - index]
                handles.append(decoder.register_forward_hook(capture(index)))
            logits = self.primary(images)
        finally:
            for handle in handles:
                handle.remove()
        if set(captured) != {0, 1}:
            raise RuntimeError("DynUNet did not produce both supervised decoder features")
        loss = WEIGHTS[0] * dice_ce(logits, labels)
        for index, head in enumerate(self.auxiliary_heads):
            auxiliary = head(captured[index])
            expected = tuple(size // (2 ** (index + 1)) for size in images.shape[2:])
            if tuple(auxiliary.shape[2:]) != expected:
                raise RuntimeError("Unexpected native DynUNet auxiliary grid")
            target = F.interpolate(labels[:, None].float(), size=expected, mode="nearest")
            loss = loss + WEIGHTS[index + 1] * dice_ce(auxiliary, target[:, 0].long())
        return loss
