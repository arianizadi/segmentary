"""A native, independently composable dense segmentation model."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, cast

from torch import Tensor, nn

from .features import FeatureBackbone, FeatureNeck, validate_feature_maps, validate_image
from .native_heads.base import DenseHead
from .outputs import AuxiliaryDenseOutput, SegmentationOutput
from .wrappers import SegmentationModel


@dataclass(frozen=True)
class AuxiliaryHeadBinding:
    """Attach a unique training name and weight to a dense head module."""

    name: str
    head: DenseHead
    loss_weight: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.name, str)
            or not self.name.strip()
            or self.name != self.name.strip()
        ):
            raise ValueError("auxiliary head name must be a non-empty, trimmed string")
        if not isinstance(self.head, DenseHead):
            raise TypeError("auxiliary head must implement DenseHead")
        if self.head.auxiliary_output_names:
            raise ValueError(
                "an auxiliary head cannot itself emit auxiliary outputs; use that head as "
                "the primary head so none of its supervised classifiers are discarded"
            )
        if not math.isfinite(self.loss_weight) or self.loss_weight <= 0.0:
            raise ValueError("auxiliary head loss_weight must be finite and positive")


class NativeDenseSegmenter(SegmentationModel):
    """Compose one feature backbone, neck, primary head, and auxiliary heads.

    Public ``forward`` remains the repository's deployment-friendly dense tensor
    contract.  Training calls ``forward_output`` to retain auxiliary logits.
    """

    def __init__(
        self,
        backbone: FeatureBackbone,
        neck: FeatureNeck,
        head: DenseHead,
        num_classes: int,
        *,
        task: str = "multiclass",
        auxiliary_heads: tuple[AuxiliaryHeadBinding, ...] = (),
    ) -> None:
        expected_channels = num_classes if task == "multiclass" else 1
        super().__init__(num_classes, output_channels=expected_channels, task=task)
        if not isinstance(backbone, FeatureBackbone):
            raise TypeError("native backbone must implement FeatureBackbone")
        if not isinstance(neck, FeatureNeck):
            raise TypeError("native neck must implement FeatureNeck")
        if not isinstance(head, DenseHead):
            raise TypeError("native head must implement DenseHead")
        if neck.input_specs != backbone.output_specs:
            raise ValueError(
                "neck input contract does not exactly match backbone output contract: "
                f"{neck.input_specs} != {backbone.output_specs}"
            )
        if head.input_specs != neck.output_specs:
            raise ValueError(
                "primary head input contract does not exactly match neck output contract"
            )
        if head.num_classes != self.output_channels:
            raise ValueError(
                f"primary head has {head.num_classes} output channels, model requests "
                f"{self.output_channels} for task={self.task!r}"
            )
        if not isinstance(auxiliary_heads, tuple):
            raise TypeError("auxiliary_heads must be a tuple")
        if not all(isinstance(binding, AuxiliaryHeadBinding) for binding in auxiliary_heads):
            raise TypeError("auxiliary_heads must contain AuxiliaryHeadBinding values")
        names = [binding.name for binding in auxiliary_heads]
        if len(names) != len(set(names)):
            raise ValueError(f"duplicate auxiliary head names: {names}")
        collisions = sorted(set(names) & set(head.auxiliary_output_names))
        if collisions:
            raise ValueError(
                f"external auxiliary head names collide with primary-head outputs: {collisions}"
            )
        for binding in auxiliary_heads:
            if binding.head.input_specs != neck.output_specs:
                raise ValueError(
                    f"auxiliary head {binding.name!r} input contract does not match neck output"
                )
            if binding.head.num_classes != self.output_channels:
                raise ValueError(
                    f"auxiliary head {binding.name!r} has {binding.head.num_classes} output "
                    f"channels, model requests {self.output_channels}"
                )

        self.backbone = backbone
        self.neck = neck
        self.head = head
        self.auxiliary_heads = nn.ModuleDict(
            {binding.name: binding.head for binding in auxiliary_heads}
        )
        self._auxiliary_weights = {
            binding.name: float(binding.loss_weight) for binding in auxiliary_heads
        }
        self._copy_preprocessing_contract(backbone)
        self.validate_parameter_partition()

    def _copy_preprocessing_contract(self, backbone: FeatureBackbone) -> None:
        for attribute in (
            "input_mean",
            "input_std",
            "input_channel_order",
            "input_normalization_source",
        ):
            if hasattr(backbone, attribute):
                setattr(self, attribute, getattr(backbone, attribute))

    def validate_parameter_partition(self) -> dict[str, int]:
        """Prove that backbone and train-from-scratch components share no tensors."""

        groups = {
            "backbone": {id(parameter) for parameter in self.backbone.parameters()},
            "neck": {id(parameter) for parameter in self.neck.parameters()},
            "head": {id(parameter) for parameter in self.head.parameters()},
            "auxiliary": {id(parameter) for parameter in self.auxiliary_heads.parameters()},
        }
        labels = tuple(groups)
        for left_index, left in enumerate(labels):
            for right in labels[left_index + 1 :]:
                shared = groups[left] & groups[right]
                if shared:
                    raise ValueError(
                        f"native components {left!r} and {right!r} share {len(shared)} "
                        "parameter tensors; optimizer ownership would be ambiguous"
                    )
        all_parameters = {id(parameter) for parameter in self.parameters()}
        owned = set().union(*groups.values())
        if owned != all_parameters:
            raise ValueError(
                f"native parameter partition missed {len(all_parameters - owned)} tensors"
            )
        return {name: len(parameters) for name, parameters in groups.items()}

    def forward_output(self, pixel_values: Tensor) -> SegmentationOutput:
        validate_image(
            pixel_values,
            channels=self.backbone.input_channels,
            where="NativeDenseSegmenter",
        )
        input_size = (int(pixel_values.shape[2]), int(pixel_values.shape[3]))
        batch_size = int(pixel_values.shape[0])
        backbone_features = self.backbone.forward_features(pixel_values)
        validate_feature_maps(
            backbone_features,
            self.backbone.output_specs,
            where="native backbone output",
            batch_size=batch_size,
            input_size=input_size,
        )
        neck_features = self.neck(backbone_features)
        validate_feature_maps(
            neck_features,
            self.neck.output_specs,
            where="native neck output",
            batch_size=batch_size,
            input_size=input_size,
        )
        head_output = self.head.forward_output(neck_features, input_size)
        if not isinstance(head_output, SegmentationOutput):
            raise TypeError(
                f"native dense head returned {type(head_output).__name__}, expected "
                "SegmentationOutput"
            )
        if head_output.dense_logits is None:
            raise ValueError("native dense head returned query predictions")
        emitted_names = tuple(item.name for item in head_output.auxiliary_dense)
        if emitted_names != self.head.auxiliary_output_names:
            raise ValueError(
                f"native dense head declared auxiliary outputs "
                f"{self.head.auxiliary_output_names} but emitted {emitted_names}"
            )
        primary = self._check_output(head_output.dense_logits, pixel_values)
        intrinsic_auxiliary = tuple(
            AuxiliaryDenseOutput(
                item.name,
                self._check_output(item.logits, pixel_values),
                item.loss_weight,
            )
            for item in head_output.auxiliary_dense
        )
        external_auxiliary = tuple(
            AuxiliaryDenseOutput(
                name,
                self._check_output(auxiliary_head(neck_features, input_size), pixel_values),
                self._auxiliary_weights[name],
            )
            for name, auxiliary_head in self.auxiliary_heads.items()
        )
        return SegmentationOutput(
            dense_logits=primary,
            auxiliary_dense=intrinsic_auxiliary + external_auxiliary,
        )

    def forward(self, pixel_values: Tensor) -> Tensor:
        output = self.forward_output(pixel_values)
        assert output.dense_logits is not None
        return output.dense_logits

    def head_patterns(self) -> tuple[str, ...]:
        # The neck and every dense head are initialized for this task and belong
        # at the head learning rate rather than the pretrained-backbone rate.
        return ("neck.", "head.", "auxiliary_heads.")

    def backbone_modules(self) -> list[nn.Module]:
        return [self.backbone]

    def reset_head(self) -> None:
        self.head.reset_classifier()
        for auxiliary_head in self.auxiliary_heads.values():
            cast(Any, auxiliary_head).reset_classifier()
