"""Runtime integration tests for Segmentary-native dense segmentation models."""

from __future__ import annotations

import pytest
import torch
from torch import Tensor, nn

import segmentary.curriculum as curriculum
from segmentary.config import (
    AuxiliaryHeadSpec,
    BinaryCrossEntropyTerm,
    DataConfig,
    EvalConfig,
    ExperimentConfig,
    FCNHeadSpec,
    FPNNeckSpec,
    KLDistillationTerm,
    LossSpec,
    ModelConfig,
    NativeModelSpec,
    OCRHeadSpec,
    OptimConfig,
    StageConfig,
    TimmBackboneSpec,
    TrainConfig,
)
from segmentary.engine.losses import LossConfig, SegmentationLoss
from segmentary.engine.module import SegLitModule, dense_training_objective
from segmentary.models.factory import VALID_ARCHS, build_model
from segmentary.models.outputs import (
    AuxiliaryDenseOutput,
    QueryOutput,
    QueryPrediction,
    SegmentationOutput,
)
from segmentary.models.tuning import apply_tuning
from segmentary.models.wrappers import SegmentationModel
from segmentary.taxonomy import CanonicalClass, LabelSpace

NUM_CLASSES = 3


class _LegacyDenseModel(SegmentationModel):
    """Small pre-native wrapper proving the old Tensor contract is unchanged."""

    def __init__(self) -> None:
        super().__init__(NUM_CLASSES)
        self.backbone = nn.Conv2d(3, 4, 1)
        self.classifier = nn.Conv2d(4, NUM_CLASSES, 1)
        self.forward_calls = 0

    def forward(self, pixel_values: Tensor) -> Tensor:
        self.forward_calls += 1
        return self._check_output(self.classifier(self.backbone(pixel_values)), pixel_values)

    def head_patterns(self) -> tuple[str, ...]:
        return ("classifier.",)

    def backbone_modules(self) -> list[nn.Module]:
        return [self.backbone]

    def reset_head(self) -> None:
        self.classifier.reset_parameters()


class _AuxiliaryDenseModel(_LegacyDenseModel):
    def __init__(self, loss_weight: float = 0.35) -> None:
        super().__init__()
        self.auxiliary = nn.Conv2d(4, NUM_CLASSES, 1)
        self.loss_weight = loss_weight

    def forward_output(self, pixel_values: Tensor) -> SegmentationOutput:
        self.forward_calls += 1
        features = self.backbone(pixel_values)
        return SegmentationOutput(
            dense_logits=self.classifier(features),
            auxiliary_dense=(
                AuxiliaryDenseOutput(
                    "early",
                    self.auxiliary(features),
                    self.loss_weight,
                ),
            ),
        )

    def head_patterns(self) -> tuple[str, ...]:
        return ("classifier.", "auxiliary.")


def _space() -> LabelSpace:
    return LabelSpace(
        name="runtime-test",
        description="native runtime tests",
        ignore_index=255,
        classes=tuple(
            CanonicalClass(class_id, f"c{class_id}", (class_id, class_id, class_id))
            for class_id in range(NUM_CLASSES)
        ),
        thin_classes=(),
    )


def _batch() -> dict[str, Tensor]:
    mask = torch.randint(NUM_CLASSES, (2, 12, 16))
    mask[1].remainder_(2)
    return {
        "image": torch.randn(2, 3, 12, 16),
        "mask": mask,
        "active": torch.tensor([[True, True, True], [True, True, False]]),
    }


def _experiment(*, model: ModelConfig, loss: LossSpec) -> ExperimentConfig:
    return ExperimentConfig(
        name="runtime-test",
        model=model,
        space="unused",
        loss=loss,
        stages=[
            StageConfig(
                name="train",
                data=[DataConfig(name="cityscapes", root="/must-not-be-opened")],
            )
        ],
    )


def _native_spec(*, auxiliary: bool = True) -> NativeModelSpec:
    auxiliary_heads = []
    if auxiliary:
        auxiliary_heads.append(
            AuxiliaryHeadSpec(
                name="s16",
                loss_weight=0.4,
                head=FCNHeadSpec(in_indices=(2,), channels=8, num_convs=1, dropout=0.0),
            )
        )
    return NativeModelSpec(
        backbone=TimmBackboneSpec(name="resnet18", weights="scratch", out_indices=(1, 2, 3, 4)),
        neck=FPNNeckSpec(out_channels=16, num_outputs=4),
        head=FCNHeadSpec(in_indices=(0, 1, 2, 3), channels=16, num_convs=1, dropout=0.0),
        auxiliary_heads=auxiliary_heads,
    )


def test_legacy_forward_and_default_forward_output_are_backward_compatible():
    model = _LegacyDenseModel()
    image = torch.randn(2, 3, 12, 16)

    tensor_output = model(image)
    rich_output = model.forward_output(image)

    assert isinstance(tensor_output, Tensor)
    assert tensor_output.shape == (2, NUM_CLASSES, 12, 16)
    assert rich_output.dense_logits is not None
    assert rich_output.dense_logits.shape == tensor_output.shape
    assert rich_output.auxiliary_dense == ()
    assert model.forward_calls == 2


def test_dense_training_objective_weights_auxiliary_loss_and_backpropagates_every_output():
    torch.manual_seed(3)
    model = _AuxiliaryDenseModel(loss_weight=0.35)
    loss_fn = SegmentationLoss(LossConfig(), NUM_CLASSES, 255)
    batch = _batch()

    output = model.forward_output(batch["image"])
    assert output.dense_logits is not None
    expected_primary, _ = loss_fn(output.dense_logits, batch["mask"], active=batch["active"])
    expected_auxiliary, _ = loss_fn(
        output.auxiliary_dense[0].logits,
        batch["mask"],
        active=batch["active"],
    )
    model.zero_grad(set_to_none=True)
    model.forward_calls = 0

    total, parts = dense_training_objective(
        model,
        loss_fn,
        batch["image"],
        batch["mask"],
        active=batch["active"],
    )

    torch.testing.assert_close(total, expected_primary + 0.35 * expected_auxiliary)
    torch.testing.assert_close(parts["aux/early/loss"], expected_auxiliary.detach())
    torch.testing.assert_close(parts["aux/early/weighted_loss"], 0.35 * expected_auxiliary.detach())
    torch.testing.assert_close(parts["total"], total.detach())
    assert model.forward_calls == 1

    total.backward()
    assert model.backbone.weight.grad is not None
    assert model.classifier.weight.grad is not None
    assert model.auxiliary.weight.grad is not None
    assert bool(model.auxiliary.weight.grad.abs().sum() > 0)


def test_ocr_coarse_output_is_weighted_by_the_production_dense_objective():
    native = NativeModelSpec(
        backbone=TimmBackboneSpec(name="resnet18", weights="scratch", out_indices=(1, 2, 3, 4)),
        neck=FPNNeckSpec(out_channels=16, num_outputs=4),
        head=OCRHeadSpec(
            in_indices=(0, 1, 2, 3),
            channels=24,
            key_channels=12,
            dropout=0.0,
            coarse_loss_weight=0.4,
        ),
    )
    model = build_model(ModelConfig(arch="native", native=native), NUM_CLASSES).eval()
    loss_fn = SegmentationLoss(LossConfig(), NUM_CLASSES, 255)
    batch = _batch()

    with torch.no_grad():
        output = model.forward_output(batch["image"])
        assert output.dense_logits is not None
        primary_loss, _ = loss_fn(output.dense_logits, batch["mask"], active=batch["active"])
        coarse = output.auxiliary_dense[0]
        assert coarse.name == "ocr_coarse"
        assert coarse.loss_weight == pytest.approx(0.4)
        coarse_loss, _ = loss_fn(coarse.logits, batch["mask"], active=batch["active"])

    total, parts = dense_training_objective(
        model,
        loss_fn,
        batch["image"],
        batch["mask"],
        active=batch["active"],
    )
    torch.testing.assert_close(total, primary_loss + 0.4 * coarse_loss)
    torch.testing.assert_close(parts["aux/ocr_coarse/loss"], coarse_loss)
    torch.testing.assert_close(parts["aux/ocr_coarse/weighted_loss"], 0.4 * coarse_loss)

    total.backward()
    assert model.head.coarse_classifier.weight.grad is not None
    assert bool(model.head.coarse_classifier.weight.grad.abs().sum() > 0)
    assert model.head.classifier.weight.grad is not None
    assert bool(model.head.classifier.weight.grad.abs().sum() > 0)


def test_lightning_training_step_consumes_auxiliary_output(monkeypatch):
    model = _AuxiliaryDenseModel(loss_weight=0.5)
    lit = SegLitModule(
        model=model,
        loss_fn=SegmentationLoss(LossConfig(), NUM_CLASSES, 255),
        space=_space(),
        optim_cfg=OptimConfig(),
        train_cfg=TrainConfig(ema_decay=None),
        eval_cfg=EvalConfig(sliding_window=False),
    )
    logged: dict[str, Tensor | float] = {}
    monkeypatch.setattr(lit, "log", lambda name, value, **kwargs: logged.__setitem__(name, value))
    monkeypatch.setattr(lit, "_current_lr", lambda: 1e-3)

    loss = lit.training_step(_batch(), 0)
    loss.backward()

    assert "train/aux/early/loss" in logged
    assert "train/aux/early/weighted_loss" in logged
    assert model.auxiliary.weight.grad is not None
    assert model.forward_calls == 1


def test_dense_training_objective_rejects_query_output_instead_of_dropping_it():
    class QueryModel(nn.Module):
        def forward_output(self, pixel_values: Tensor) -> SegmentationOutput:
            n, _, h, w = pixel_values.shape
            return SegmentationOutput(
                query=QueryOutput(
                    QueryPrediction(
                        torch.randn(n, 4, NUM_CLASSES + 1),
                        torch.randn(n, 4, h, w),
                    )
                )
            )

    batch = _batch()
    with pytest.raises(ValueError, match=r"query predictions.*dense objective"):
        dense_training_objective(
            QueryModel(),
            SegmentationLoss(LossConfig(), NUM_CLASSES, 255),
            batch["image"],
            batch["mask"],
        )


def test_native_factory_builds_real_timm_stack_and_preserves_tensor_forward():
    assert "native" in VALID_ARCHS
    model = build_model(
        ModelConfig(arch="native", native=_native_spec()),
        NUM_CLASSES,
    )
    image = torch.randn(1, 3, 64, 96)

    model.eval()
    with torch.no_grad():
        output = model.forward_output(image)
        logits = model(image)

    assert output.dense_logits is not None
    assert output.dense_logits.shape == (1, NUM_CLASSES, 64, 96)
    assert len(output.auxiliary_dense) == 1
    assert output.auxiliary_dense[0].name == "s16"
    assert output.auxiliary_dense[0].loss_weight == pytest.approx(0.4)
    assert isinstance(logits, Tensor)
    assert logits.shape == (1, NUM_CLASSES, 64, 96)
    assert model.validate_parameter_partition() == {
        "backbone": len({id(parameter) for parameter in model.backbone.parameters()}),
        "neck": len({id(parameter) for parameter in model.neck.parameters()}),
        "head": len({id(parameter) for parameter in model.head.parameters()}),
        "auxiliary": len({id(parameter) for parameter in model.auxiliary_heads.parameters()}),
    }


def test_native_full_and_frozen_tuning_keep_component_ownership_explicit():
    full_cfg = ModelConfig(arch="native", native=_native_spec())
    full = apply_tuning(build_model(full_cfg, NUM_CLASSES), full_cfg)
    assert all(parameter.requires_grad for parameter in full.parameters())

    frozen_cfg = ModelConfig(arch="native", native=_native_spec(), tuning="frozen")
    frozen = apply_tuning(build_model(frozen_cfg, NUM_CLASSES), frozen_cfg)
    assert all(not parameter.requires_grad for parameter in frozen.backbone.parameters())
    assert all(parameter.requires_grad for parameter in frozen.neck.parameters())
    assert all(parameter.requires_grad for parameter in frozen.head.parameters())
    assert all(parameter.requires_grad for parameter in frozen.auxiliary_heads.parameters())


def test_native_convolutional_backbone_rejects_unavailable_lora_explicitly():
    cfg = ModelConfig(arch="native", native=_native_spec(), tuning="lora")
    model = build_model(cfg, NUM_CLASSES)

    with pytest.raises(
        ValueError, match=r"purely convolutional backbone.*cannot be tuned with LoRA"
    ):
        apply_tuning(model, cfg)


def test_native_task_mismatch_fails_before_taxonomy_or_dataset_access(monkeypatch):
    cfg = _experiment(
        model=ModelConfig(arch="native", native=_native_spec()),
        loss=LossSpec(
            task="binary",
            terms=[BinaryCrossEntropyTerm(kind="binary_cross_entropy")],
        ),
    )
    monkeypatch.setattr(
        curriculum,
        "load_space",
        lambda *args, **kwargs: pytest.fail("taxonomy was opened before validation"),
    )

    with pytest.raises(ValueError, match=r"model.native.task='multiclass'.*loss.task='binary'"):
        curriculum.run_curriculum(cfg, devices=1)


def test_standard_curriculum_rejects_distillation_without_teacher_before_data(monkeypatch):
    cfg = _experiment(
        model=ModelConfig(arch="toy"),
        loss=LossSpec(terms=[KLDistillationTerm(kind="kl_distillation")]),
    )
    monkeypatch.setattr(
        curriculum,
        "load_space",
        lambda *args, **kwargs: pytest.fail("taxonomy was opened before validation"),
    )

    with pytest.raises(ValueError, match=r"kl_distillation.*no configured teacher-logit provider"):
        curriculum.run_curriculum(cfg, devices=1)
