"""Fail-closed contracts at the boundaries between native model components."""

from __future__ import annotations

import math

import pytest
import torch
import torch.nn.functional as F
from torch import Tensor, nn

from segmentary.models.features import (
    FeatureBackbone,
    FeatureMaps,
    FeatureNeck,
    FeatureSpec,
    checked_feature_specs,
    checked_indices,
    validate_feature_maps,
    validate_image,
)
from segmentary.models.native import AuxiliaryHeadBinding, NativeDenseSegmenter
from segmentary.models.native_heads.base import DenseHead
from segmentary.models.outputs import (
    AuxiliaryDenseOutput,
    QueryOutput,
    QueryPrediction,
    SegmentationOutput,
)

SPECS = (
    FeatureSpec("s2", 4, 2),
    FeatureSpec("s4", 6, 4),
)
OTHER_SPECS = (
    FeatureSpec("other_s2", 4, 2),
    FeatureSpec("other_s4", 6, 4),
)
NUM_CLASSES = 3


def _valid_features() -> list[Tensor]:
    # For a 9x13 input, independently exercise floor and ceiling rounding.
    return [torch.randn(2, 4, 4, 7), torch.randn(2, 6, 3, 3)]


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("name", " s2", "name must be a non-empty, trimmed string"),
        ("name", "", "name must be a non-empty, trimmed string"),
        ("channels", True, "channels must be a positive integer"),
        ("channels", 0, "channels must be a positive integer"),
        ("reduction", 1.5, "reduction must be a positive integer"),
        ("reduction", 0, "reduction must be a positive integer"),
    ],
)
def test_feature_specs_cannot_encode_ambiguous_layout_facts(
    field: str, value: object, message: str
) -> None:
    values: dict[str, object] = {"name": "s2", "channels": 4, "reduction": 2}
    values[field] = value

    with pytest.raises(ValueError, match=message):
        FeatureSpec(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("specs", "error", "message"),
    [
        ((), ValueError, "must declare at least one feature"),
        ([SPECS[0]], ValueError, "must declare at least one feature"),
        ((SPECS[0], object()), TypeError, "tuple of FeatureSpec"),
        ((SPECS[0], SPECS[0]), ValueError, "duplicate feature names"),
    ],
)
def test_feature_pyramids_require_a_nonempty_typed_unique_tuple(
    specs: object, error: type[Exception], message: str
) -> None:
    with pytest.raises(error, match=message):
        checked_feature_specs(specs, where="decoder input")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("indices", "minimum", "error", "message"),
    [
        ([], 1, ValueError, "needs at least 1"),
        ((0,), 2, ValueError, "needs at least 2"),
        ((True,), 1, TypeError, "indices must be integers"),
        ((1, 0), 1, ValueError, "unique and strictly increasing"),
        ((0, 0), 1, ValueError, "unique and strictly increasing"),
        ((-1,), 1, ValueError, "outside the available range"),
        ((2,), 1, ValueError, "outside the available range"),
    ],
)
def test_feature_selection_cannot_silently_reorder_repeat_or_escape_the_pyramid(
    indices: object,
    minimum: int,
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        checked_indices(
            indices,  # type: ignore[arg-type]
            SPECS,
            where="decoder",
            minimum=minimum,
        )


def test_runtime_feature_contract_accepts_independent_floor_and_ceiling_rounding() -> None:
    features = _valid_features()

    checked = validate_feature_maps(
        features,
        SPECS,
        where="backbone",
        batch_size=2,
        input_size=(9, 13),
    )

    assert isinstance(checked, tuple)
    assert all(left is right for left, right in zip(checked, features, strict=True))


@pytest.mark.parametrize(
    ("defect", "error", "message"),
    [
        ("container", TypeError, "tuple/list of feature tensors"),
        ("count", ValueError, "returned 1 features, expected 2"),
        ("rank", ValueError, "must be NCHW"),
        ("batch", ValueError, "batch 1 != 2"),
        ("channels", ValueError, "declared 6"),
        ("empty", ValueError, "empty spatial dimension"),
        ("reduction", ValueError, "inconsistent with input 13"),
    ],
)
def test_runtime_feature_contract_stops_miswired_tensors_before_the_decoder(
    defect: str, error: type[Exception], message: str
) -> None:
    features: object = _valid_features()
    if defect == "container":
        features = torch.randn(2, 4, 4, 7)
    elif defect == "count":
        features = _valid_features()[:1]
    elif defect == "rank":
        features[0] = torch.randn(2, 4, 7)  # type: ignore[index]
    elif defect == "batch":
        features[1] = torch.randn(1, 6, 3, 3)  # type: ignore[index]
    elif defect == "channels":
        features[1] = torch.randn(2, 5, 3, 3)  # type: ignore[index]
    elif defect == "empty":
        features[1] = torch.randn(2, 6, 0, 3)  # type: ignore[index]
    elif defect == "reduction":
        features[1] = torch.randn(2, 6, 3, 5)  # type: ignore[index]

    with pytest.raises(error, match=message):
        validate_feature_maps(
            features,  # type: ignore[arg-type]
            SPECS,
            where="backbone",
            batch_size=2,
            input_size=(9, 13),
        )


@pytest.mark.parametrize(
    ("image", "message"),
    [
        ("not a tensor", "expects an NCHW Tensor"),
        (torch.randn(3, 9, 13), "expects an NCHW Tensor"),
        (torch.randn(0, 3, 9, 13), "empty image dimension"),
        (torch.randn(2, 3, 0, 13), "empty image dimension"),
        (torch.randn(2, 1, 9, 13), "expects 3 input channels"),
    ],
)
def test_native_image_contract_rejects_inputs_that_cannot_preserve_batch_geometry(
    image: object, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_image(image, channels=3, where="native backbone")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("name", "logits", "weight", "message"),
    [
        (" coarse", torch.randn(2, 3, 9, 13), 0.4, "name must be a non-empty, trimmed"),
        ("coarse", torch.randn(2, 3, 9), 0.4, "logits must be NCHW"),
        ("coarse", torch.randn(2, 3, 9, 13), 0.0, "finite and positive"),
        ("coarse", torch.randn(2, 3, 9, 13), math.inf, "finite and positive"),
    ],
)
def test_auxiliary_dense_outputs_are_safe_to_name_weight_and_sum(
    name: str, logits: Tensor, weight: float, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        AuxiliaryDenseOutput(name, logits, weight)


@pytest.mark.parametrize(
    ("class_logits", "mask_logits", "message"),
    [
        (torch.randn(2, 4), torch.randn(2, 4, 5, 7), "class_logits must have shape"),
        (torch.randn(2, 4, 4), torch.randn(2, 4, 5), "mask_logits must have shape"),
        (torch.randn(2, 3, 4), torch.randn(2, 4, 5, 7), "disagree on batch or query"),
        (torch.randn(0, 4, 4), torch.randn(0, 4, 5, 7), "at least one batch item"),
        (torch.randn(2, 0, 4), torch.randn(2, 0, 5, 7), "at least one batch item"),
        (torch.randn(2, 4, 1), torch.randn(2, 4, 5, 7), "one class plus no-object"),
        (torch.randn(2, 4, 4), torch.randn(2, 4, 0, 7), "empty spatial dimension"),
    ],
)
def test_query_predictions_reject_shapes_that_change_set_semantics(
    class_logits: Tensor, mask_logits: Tensor, message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        QueryPrediction(class_logits, mask_logits)


def test_query_output_preserves_multiscale_layers_but_rejects_semantic_shape_drift() -> None:
    primary = QueryPrediction(torch.randn(2, 4, 4), torch.randn(2, 4, 5, 7))
    lower_resolution = QueryPrediction(torch.randn(2, 4, 4), torch.randn(2, 4, 3, 4))

    output = QueryOutput(primary, (lower_resolution,))

    assert output.auxiliary == (lower_resolution,)
    with pytest.raises(TypeError, match="primary must be a QueryPrediction"):
        QueryOutput(object())  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="auxiliary must be a tuple"):
        QueryOutput(primary, [lower_resolution])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="tuple of QueryPrediction"):
        QueryOutput(primary, (object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="class shape"):
        QueryOutput(
            primary,
            (QueryPrediction(torch.randn(2, 4, 5), torch.randn(2, 4, 3, 4)),),
        )
    with pytest.raises(ValueError, match="class shape"):
        QueryOutput(
            primary,
            (QueryPrediction(torch.randn(1, 4, 4), torch.randn(1, 4, 3, 4)),),
        )


def _query_output() -> QueryOutput:
    return QueryOutput(QueryPrediction(torch.randn(2, 4, 4), torch.randn(2, 4, 5, 7)))


def test_segmentation_output_rejects_any_representation_the_engine_would_ignore() -> None:
    dense = torch.randn(2, NUM_CLASSES, 9, 13)
    auxiliary = AuxiliaryDenseOutput("coarse", dense.clone(), 0.4)
    query = _query_output()

    with pytest.raises(ValueError, match="exactly one"):
        SegmentationOutput()
    with pytest.raises(ValueError, match="exactly one"):
        SegmentationOutput(dense_logits=dense, query=query)
    with pytest.raises(TypeError, match="query must be a QueryOutput"):
        SegmentationOutput(query=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="query output cannot carry dense auxiliary"):
        SegmentationOutput(query=query, auxiliary_dense=(auxiliary,))


def test_dense_segmentation_output_rejects_auxiliary_predictions_it_cannot_supervise() -> None:
    dense = torch.randn(2, NUM_CLASSES, 9, 13)
    auxiliary = AuxiliaryDenseOutput("coarse", dense.clone(), 0.4)

    with pytest.raises(ValueError, match="dense_logits must have shape"):
        SegmentationOutput(dense_logits=torch.randn(2, NUM_CLASSES, 9))
    with pytest.raises(TypeError, match="auxiliary_dense must be a tuple"):
        SegmentationOutput(dense_logits=dense, auxiliary_dense=[auxiliary])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="tuple of AuxiliaryDenseOutput"):
        SegmentationOutput(dense_logits=dense, auxiliary_dense=(object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="duplicate auxiliary output names"):
        SegmentationOutput(dense_logits=dense, auxiliary_dense=(auxiliary, auxiliary))
    with pytest.raises(ValueError, match="!= primary dense shape"):
        SegmentationOutput(
            dense_logits=dense,
            auxiliary_dense=(
                AuxiliaryDenseOutput("coarse", torch.randn(2, NUM_CLASSES, 5, 7), 0.4),
            ),
        )


class _ContractBackbone(FeatureBackbone):
    input_channels = 3

    def __init__(
        self,
        *,
        specs: tuple[FeatureSpec, ...] = SPECS,
        defect: str | None = None,
        shared: nn.Parameter | None = None,
    ) -> None:
        super().__init__()
        self._specs = specs
        self.defect = defect
        self.stage_0 = nn.Conv2d(3, 4, 1, stride=2)
        self.stage_1 = nn.Conv2d(4, 6, 1, stride=2)
        if shared is not None:
            self.shared = shared

    @property
    def output_specs(self) -> tuple[FeatureSpec, ...]:
        return self._specs

    def forward_features(self, image: Tensor) -> FeatureMaps:
        first = self.stage_0(image)
        second = self.stage_1(first)
        if self.defect == "channels":
            second = second[:, :-1]
        return first, second


class _ContractNeck(FeatureNeck):
    def __init__(
        self,
        *,
        input_specs: tuple[FeatureSpec, ...] = SPECS,
        output_specs: tuple[FeatureSpec, ...] | None = None,
        defect: str | None = None,
    ) -> None:
        super().__init__()
        self._input_specs = input_specs
        self._output_specs = output_specs or input_specs
        self.defect = defect
        self.scale = nn.Parameter(torch.ones(()))

    @property
    def input_specs(self) -> tuple[FeatureSpec, ...]:
        return self._input_specs

    @property
    def output_specs(self) -> tuple[FeatureSpec, ...]:
        return self._output_specs

    def forward(self, features: FeatureMaps) -> FeatureMaps:
        output = tuple(feature * self.scale for feature in features)
        if self.defect == "batch":
            output = (output[0], output[1][:-1])
        return output


class _ContractHead(DenseHead):
    def __init__(
        self,
        input_specs: tuple[FeatureSpec, ...] = SPECS,
        num_classes: int = NUM_CLASSES,
        *,
        declared_auxiliary: tuple[str, ...] = (),
        emitted_auxiliary: tuple[str, ...] = (),
        forward_kind: str = "dense",
        shared: nn.Parameter | None = None,
    ) -> None:
        super().__init__(input_specs, num_classes, (0,))
        self.classifier = nn.Conv2d(input_specs[0].channels, num_classes, 1)
        self._declared_auxiliary = declared_auxiliary
        self.emitted_auxiliary = emitted_auxiliary
        self.forward_kind = forward_kind
        self.reset_calls = 0
        self.forward_calls = 0
        if shared is not None:
            self.shared = shared

    @property
    def auxiliary_output_names(self) -> tuple[str, ...]:
        return self._declared_auxiliary

    def forward(self, features: FeatureMaps, output_size: tuple[int, int]) -> Tensor:
        self.forward_calls += 1
        logits = self.classifier(features[0])
        return F.interpolate(logits, size=output_size, mode="bilinear", align_corners=False)

    def forward_output(
        self, features: FeatureMaps, output_size: tuple[int, int]
    ) -> SegmentationOutput:
        logits = self(features, output_size)
        if self.forward_kind == "tensor":
            return logits  # type: ignore[return-value]
        if self.forward_kind == "query":
            batch = int(logits.shape[0])
            prediction = QueryPrediction(
                torch.randn(batch, 2, self.num_classes + 1),
                torch.randn(batch, 2, *output_size),
            )
            return SegmentationOutput(query=QueryOutput(prediction))
        auxiliary = tuple(
            AuxiliaryDenseOutput(name, logits.clone(), 0.25) for name in self.emitted_auxiliary
        )
        return SegmentationOutput(dense_logits=logits, auxiliary_dense=auxiliary)

    def reset_classifier(self) -> None:
        self.reset_calls += 1
        with torch.no_grad():
            self.classifier.weight.fill_(42.0)
            if self.classifier.bias is not None:
                self.classifier.bias.fill_(-42.0)


def _model(
    *,
    backbone: FeatureBackbone | None = None,
    neck: FeatureNeck | None = None,
    head: DenseHead | None = None,
    auxiliary_heads: tuple[AuxiliaryHeadBinding, ...] = (),
) -> NativeDenseSegmenter:
    return NativeDenseSegmenter(
        backbone or _ContractBackbone(),
        neck or _ContractNeck(),
        head or _ContractHead(),
        NUM_CLASSES,
        auxiliary_heads=auxiliary_heads,
    )


@pytest.mark.parametrize(
    ("component", "message"),
    [
        ("backbone", "backbone must implement FeatureBackbone"),
        ("neck", "neck must implement FeatureNeck"),
        ("head", "head must implement DenseHead"),
    ],
)
def test_native_composition_requires_explicit_component_protocols(
    component: str, message: str
) -> None:
    parts: dict[str, object] = {
        "backbone": _ContractBackbone(),
        "neck": _ContractNeck(),
        "head": _ContractHead(),
    }
    parts[component] = nn.Identity()

    with pytest.raises(TypeError, match=message):
        _model(**parts)  # type: ignore[arg-type]


def test_native_composition_rejects_static_feature_and_task_mismatches_before_a_batch() -> None:
    with pytest.raises(ValueError, match="neck input contract does not exactly match"):
        _model(neck=_ContractNeck(input_specs=OTHER_SPECS, output_specs=OTHER_SPECS))
    with pytest.raises(ValueError, match="primary head input contract does not exactly match"):
        _model(head=_ContractHead(OTHER_SPECS))
    with pytest.raises(ValueError, match="primary head has 2 output channels"):
        _model(head=_ContractHead(num_classes=2))


@pytest.mark.parametrize(
    ("name", "head", "weight", "error", "message"),
    [
        (" aux", _ContractHead(), 0.4, ValueError, "name must be a non-empty, trimmed"),
        ("aux", nn.Identity(), 0.4, TypeError, "must implement DenseHead"),
        ("aux", _ContractHead(), 0.0, ValueError, "finite and positive"),
        ("aux", _ContractHead(), math.nan, ValueError, "finite and positive"),
    ],
)
def test_auxiliary_head_bindings_cannot_hide_or_misweight_supervised_classifiers(
    name: str,
    head: nn.Module,
    weight: float,
    error: type[Exception],
    message: str,
) -> None:
    with pytest.raises(error, match=message):
        AuxiliaryHeadBinding(name, head, weight)  # type: ignore[arg-type]


def test_native_composition_rejects_ambiguous_auxiliary_head_ownership() -> None:
    valid = AuxiliaryHeadBinding("aux", _ContractHead(), 0.4)
    duplicate = AuxiliaryHeadBinding("aux", _ContractHead(), 0.2)

    with pytest.raises(TypeError, match="auxiliary_heads must be a tuple"):
        _model(auxiliary_heads=[valid])  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="must contain AuxiliaryHeadBinding"):
        _model(auxiliary_heads=(object(),))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="duplicate auxiliary head names"):
        _model(auxiliary_heads=(valid, duplicate))
    with pytest.raises(ValueError, match="input contract does not match"):
        _model(auxiliary_heads=(AuxiliaryHeadBinding("aux", _ContractHead(OTHER_SPECS), 0.4),))
    with pytest.raises(ValueError, match="has 2 output channels"):
        _model(auxiliary_heads=(AuxiliaryHeadBinding("aux", _ContractHead(num_classes=2), 0.4),))


def test_parameter_partition_rejects_shared_and_unowned_trainable_tensors() -> None:
    shared = nn.Parameter(torch.ones(()))
    with pytest.raises(ValueError, match=r"backbone.*head.*share 1 parameter"):
        _model(
            backbone=_ContractBackbone(shared=shared),
            head=_ContractHead(shared=shared),
        )

    model = _model()
    model.register_parameter("unowned_parameter", nn.Parameter(torch.ones(())))
    with pytest.raises(ValueError, match="parameter partition missed 1 tensors"):
        model.validate_parameter_partition()


def test_native_forward_stops_invalid_backbone_and_neck_outputs_before_the_head() -> None:
    bad_backbone_head = _ContractHead()
    bad_backbone = _model(
        backbone=_ContractBackbone(defect="channels"),
        head=bad_backbone_head,
    )
    with pytest.raises(ValueError, match=r"native backbone output.*declared 6"):
        bad_backbone(torch.randn(2, 3, 9, 13))
    assert bad_backbone_head.forward_calls == 0

    bad_neck_head = _ContractHead()
    bad_neck = _model(neck=_ContractNeck(defect="batch"), head=bad_neck_head)
    with pytest.raises(ValueError, match=r"native neck output.*batch 1 != 2"):
        bad_neck(torch.randn(2, 3, 9, 13))
    assert bad_neck_head.forward_calls == 0


@pytest.mark.parametrize(
    ("head", "error", "message"),
    [
        (_ContractHead(forward_kind="tensor"), TypeError, "expected SegmentationOutput"),
        (_ContractHead(forward_kind="query"), ValueError, "returned query predictions"),
        (
            _ContractHead(declared_auxiliary=("coarse",)),
            ValueError,
            "declared auxiliary outputs.*but emitted",
        ),
    ],
)
def test_native_forward_rejects_head_outputs_the_dense_objective_would_discard(
    head: _ContractHead, error: type[Exception], message: str
) -> None:
    model = _model(head=head)

    with pytest.raises(error, match=message):
        model.forward_output(torch.randn(2, 3, 9, 13))


def test_native_reset_reinitializes_every_classifier_without_touching_feature_extractors() -> None:
    primary = _ContractHead()
    auxiliary = _ContractHead()
    model = _model(
        head=primary,
        auxiliary_heads=(AuxiliaryHeadBinding("aux", auxiliary, 0.4),),
    )
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.fill_(3.0)
    before = {name: parameter.detach().clone() for name, parameter in model.named_parameters()}

    model.reset_head()

    changed = {
        name
        for name, parameter in model.named_parameters()
        if not torch.equal(parameter.detach(), before[name])
    }
    assert changed == {
        "head.classifier.weight",
        "head.classifier.bias",
        "auxiliary_heads.aux.classifier.weight",
        "auxiliary_heads.aux.classifier.bias",
    }
    assert primary.reset_calls == 1
    assert auxiliary.reset_calls == 1


def test_native_optimizer_patterns_assign_only_train_from_scratch_components_to_the_head_lr() -> (
    None
):
    model = _model(
        auxiliary_heads=(AuxiliaryHeadBinding("aux", _ContractHead(), 0.4),),
    )
    patterns = model.head_patterns()
    names = [name for name, _ in model.named_parameters()]

    selected = {name for name in names if any(pattern in name for pattern in patterns)}

    assert selected
    assert all(name.startswith(("neck.", "head.", "auxiliary_heads.")) for name in selected)
    assert all(name in selected for name in names if not name.startswith("backbone."))
    assert all(name not in selected for name in names if name.startswith("backbone."))
