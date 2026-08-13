"""End-to-end contracts for one-logit binary semantic segmentation."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml
from PIL import Image
from torch import Tensor, nn

from segmentary import eval as eval_module
from segmentary import overfit as overfit_module
from segmentary import train as train_module
from segmentary.config import (
    BinaryCrossEntropyTerm,
    ConfigError,
    DataConfig,
    EvalConfig,
    ExperimentConfig,
    FCNHeadSpec,
    FPNNeckSpec,
    LossSpec,
    ModelConfig,
    NativeModelSpec,
    OCRHeadSpec,
    OptimConfig,
    StageConfig,
    TimmBackboneSpec,
    TrainConfig,
    config_hash,
    load_experiment,
    to_dict,
)
from segmentary.curriculum import validate_data_task_contract
from segmentary.engine.inference import (
    InferenceConfig,
    inference,
    prediction_from_inference,
    slide_inference,
    whole_inference,
)
from segmentary.engine.losses import LossConfig, SegmentationLoss
from segmentary.engine.module import SegLitModule, dense_training_objective
from segmentary.models.factory import build_model
from segmentary.models.wrappers import SegmentationModel
from segmentary.tasks import (
    active_for_loss,
    output_channels,
    validate_canonical_active,
    validate_task_configuration,
    validate_task_space,
)
from segmentary.taxonomy import CanonicalClass, LabelSpace, load_space
from segmentary.utils.provenance import git_sha

IGNORE = 255


def _space(*, names: tuple[str, ...] = ("background", "foreground")) -> LabelSpace:
    return LabelSpace(
        name="binary",
        description="binary test space",
        ignore_index=IGNORE,
        classes=tuple(
            CanonicalClass(index, name, (index * 255, 0, 0)) for index, name in enumerate(names)
        ),
        thin_classes=(),
    )


def _native(task: str = "binary") -> NativeModelSpec:
    return NativeModelSpec(
        task=task,
        backbone=TimmBackboneSpec(
            name="resnet18",
            weights="scratch",
            out_indices=(1, 2, 3, 4),
        ),
        head=FCNHeadSpec(
            in_indices=(3,),
            channels=8,
            num_convs=1,
            dropout=0.0,
        ),
    )


def _experiment(*, task: str = "binary", arch: str = "native") -> ExperimentConfig:
    model = (
        ModelConfig(arch="native", native=_native(task))
        if arch == "native"
        else ModelConfig(arch=arch)
    )
    return ExperimentConfig(
        name="binary-test",
        model=model,
        space="binary",
        loss=LossSpec(
            task="binary",
            terms=[BinaryCrossEntropyTerm(kind="binary_cross_entropy")],
        ),
        stages=[StageConfig(name="train", data=[DataConfig(name="toy", root="/unused")])],
    )


class _OneLogitModel(SegmentationModel):
    def __init__(self) -> None:
        super().__init__(2, output_channels=1, task="binary")
        self.encoder = nn.Conv2d(3, 4, 1)
        self.classifier = nn.Conv2d(4, 1, 1)

    def forward(self, pixel_values: Tensor) -> Tensor:
        return self._check_output(self.classifier(self.encoder(pixel_values)), pixel_values)

    def head_patterns(self) -> tuple[str, ...]:
        return ("classifier.",)

    def backbone_modules(self) -> list[nn.Module]:
        return [self.encoder]

    def reset_head(self) -> None:
        self.classifier.reset_parameters()


class _TwoLogitModel(SegmentationModel):
    def __init__(self) -> None:
        super().__init__(2, output_channels=2, task="multiclass")
        self.encoder = nn.Conv2d(3, 4, 1)
        self.classifier = nn.Conv2d(4, 2, 1)

    def forward(self, pixel_values: Tensor) -> Tensor:
        return self._check_output(self.classifier(self.encoder(pixel_values)), pixel_values)

    def head_patterns(self) -> tuple[str, ...]:
        return ("classifier.",)

    def backbone_modules(self) -> list[nn.Module]:
        return [self.encoder]

    def reset_head(self) -> None:
        self.classifier.reset_parameters()


def test_binary_task_configuration_rejects_every_ambiguous_combination() -> None:
    assert validate_task_configuration(_experiment()) == "binary"

    with pytest.raises(ValueError, match=r"currently requires model\.arch='native'"):
        validate_task_configuration(_experiment(arch="segformer_b0"))

    mismatch = _experiment(task="multiclass")
    with pytest.raises(ValueError, match=r"model.native.task='multiclass'.*loss.task='binary'"):
        validate_task_configuration(mismatch)

    multilabel = _experiment()
    multilabel.loss = LossSpec(
        task="multilabel",
        terms=[BinaryCrossEntropyTerm(kind="binary_cross_entropy")],
    )
    with pytest.raises(ValueError, match="no standard dataset, inference, or evaluation"):
        validate_task_configuration(multilabel)


def test_binary_taxonomy_uses_ids_zero_and_one_with_arbitrary_names() -> None:
    validate_task_space("binary", _space())
    validate_task_space("binary", _space(names=("dry", "wet")))
    validate_task_space("binary", _space(names=("background", "tumor")))
    assert output_channels("binary", 2) == 1

    reversed_ids = LabelSpace(
        name="binary",
        description="invalid reversed ids",
        ignore_index=IGNORE,
        classes=(
            CanonicalClass(1, "negative", (0, 0, 0)),
            CanonicalClass(0, "positive", (255, 0, 0)),
        ),
        thin_classes=(),
    )
    with pytest.raises(ValueError, match=r"canonical ids \(0, 1\).*id 1.*positive"):
        validate_task_space("binary", reversed_ids)
    with pytest.raises(ValueError, match="exactly two canonical classes"):
        output_channels("binary", 3)


@pytest.mark.parametrize("value", [0.0, 1.0, -0.1, 1.1, float("nan"), True])
def test_binary_threshold_is_a_strict_probability(value: float) -> None:
    with pytest.raises((ConfigError, ValueError), match="threshold"):
        EvalConfig(threshold=value)
    with pytest.raises(ValueError, match="threshold"):
        InferenceConfig(threshold=value)


def test_binary_active_masks_require_both_canonical_classes_per_sample() -> None:
    one = torch.tensor([True, True])
    many = torch.tensor([[True, True], [True, True]])
    assert active_for_loss(one, "binary", batch_size=4).tolist() == [True]
    assert active_for_loss(many, "binary", batch_size=2).tolist() == [[True], [True]]

    original = torch.tensor([[True, False, True]])
    assert active_for_loss(original, "multiclass", batch_size=1) is original

    with pytest.raises(ValueError, match=r"both canonical classes.*sample rows=\[1\]"):
        active_for_loss(
            torch.tensor([[True, True], [True, False]]),
            "binary",
            batch_size=2,
        )
    with pytest.raises(ValueError, match="requires the dataset's canonical active mask"):
        active_for_loss(None, "binary", batch_size=1)
    with pytest.raises(ValueError, match="boolean"):
        validate_canonical_active(torch.ones(2), "binary")


def test_binary_dense_objective_converts_active_mask_and_ignores_void_pixels() -> None:
    torch.manual_seed(4)
    model = _OneLogitModel().double()
    objective = SegmentationLoss(
        LossConfig(
            task="binary",
            terms=[BinaryCrossEntropyTerm(kind="binary_cross_entropy")],
        ),
        1,
        IGNORE,
    ).double()
    image = torch.randn(2, 3, 5, 7, dtype=torch.float64)
    target = torch.randint(0, 2, (2, 5, 7))
    target[:, 0, :3] = IGNORE
    active = torch.tensor([[True, True], [True, True]])

    loss, parts = dense_training_objective(model, objective, image, target, active)
    loss.backward()

    assert torch.isfinite(loss)
    assert set(parts) >= {"binary_cross_entropy", "total"}
    assert model.classifier.weight.grad is not None
    with pytest.raises(ValueError, match="both canonical classes"):
        dense_training_objective(
            model,
            objective,
            image,
            target,
            torch.tensor([[True, True], [False, True]]),
        )

    logits = model(image).detach().requires_grad_()
    before, _ = objective(logits, target, active=torch.ones(2, 1, dtype=torch.bool))
    perturbed = logits.detach().clone()
    ignored = (target == IGNORE).unsqueeze(1)
    perturbed[ignored] += 1e4
    after, _ = objective(perturbed, target, active=torch.ones(2, 1, dtype=torch.bool))
    assert torch.equal(before, after)
    before.backward()
    assert torch.count_nonzero(logits.grad[ignored]) == 0


def test_binary_ocr_production_objective_supervises_one_logit_primary_and_coarse() -> None:
    torch.manual_seed(24)
    model = build_model(
        ModelConfig(
            arch="native",
            native=NativeModelSpec(
                task="binary",
                backbone=TimmBackboneSpec(
                    name="resnet18",
                    weights="scratch",
                    out_indices=(1, 2, 3, 4),
                ),
                neck=FPNNeckSpec(out_channels=8, num_outputs=4),
                head=OCRHeadSpec(
                    in_indices=(0, 1, 2, 3),
                    channels=12,
                    key_channels=6,
                    dropout=0.0,
                    coarse_loss_weight=0.4,
                ),
            ),
        ),
        2,
    )
    objective = SegmentationLoss(
        LossConfig(
            task="binary",
            terms=[BinaryCrossEntropyTerm(kind="binary_cross_entropy")],
        ),
        1,
        IGNORE,
    )
    image = torch.randn(2, 3, 32, 48)
    target = torch.randint(0, 2, (2, 32, 48))
    target[:, :2, :3] = IGNORE
    active = torch.tensor([[True, True], [True, True]])
    tracked_names = (
        "head.coarse_classifier.weight",
        "head.coarse_classifier.bias",
        "head.classifier.weight",
        "head.classifier.bias",
    )
    before = {name: dict(model.named_parameters())[name].detach().clone() for name in tracked_names}
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3)

    output = model.forward_output(image)
    assert output.dense_logits is not None
    assert output.dense_logits.shape == (2, 1, 32, 48)
    assert len(output.auxiliary_dense) == 1
    assert output.auxiliary_dense[0].name == "ocr_coarse"
    assert output.auxiliary_dense[0].logits.shape == (2, 1, 32, 48)

    loss, parts = dense_training_objective(model, objective, image, target, active)
    loss.backward()
    assert torch.isfinite(loss)
    assert set(parts) >= {
        "binary_cross_entropy",
        "aux/ocr_coarse/binary_cross_entropy",
        "aux/ocr_coarse/loss",
        "aux/ocr_coarse/weighted_loss",
        "total",
    }
    torch.testing.assert_close(
        parts["aux/ocr_coarse/weighted_loss"],
        0.4 * parts["aux/ocr_coarse/loss"],
    )
    torch.testing.assert_close(
        loss.detach(),
        parts["binary_cross_entropy"] + parts["aux/ocr_coarse/weighted_loss"],
    )
    assert all(parameter.grad is not None for parameter in model.parameters())
    assert bool(model.head.coarse_classifier.weight.grad.abs().sum() > 0)
    assert bool(model.head.classifier.weight.grad.abs().sum() > 0)
    optimizer.step()
    parameters = dict(model.named_parameters())
    assert all(not torch.equal(before[name], parameters[name].detach()) for name in tracked_names)

    model.zero_grad(set_to_none=True)
    empty_target = torch.full_like(target, IGNORE)
    empty_loss, empty_parts = dense_training_objective(
        model,
        objective,
        image,
        empty_target,
        active,
    )
    empty_loss.backward()
    assert empty_loss.item() == 0.0
    assert empty_parts["empty_crop"].item() == 1.0
    assert empty_parts["aux/ocr_coarse/empty_crop"].item() == 1.0
    assert all(parameter.grad is not None for parameter in model.parameters())
    assert all(torch.count_nonzero(parameter.grad) == 0 for parameter in model.parameters())


def test_dense_objective_rejects_model_task_mismatch_before_forward() -> None:
    model = _OneLogitModel()
    model.task = "multiclass"
    objective = SegmentationLoss(
        LossConfig(
            task="binary",
            terms=[BinaryCrossEntropyTerm(kind="binary_cross_entropy")],
        ),
        1,
        IGNORE,
    )
    with pytest.raises(ValueError, match=r"model task 'multiclass'.*objective task 'binary'"):
        dense_training_objective(
            model,
            objective,
            torch.randn(1, 3, 4, 4),
            torch.zeros(1, 4, 4, dtype=torch.long),
            torch.tensor([True, True]),
        )


def test_binary_all_ignore_batch_returns_graph_connected_zero() -> None:
    model = _OneLogitModel()
    objective = SegmentationLoss(
        LossConfig(
            task="binary",
            terms=[BinaryCrossEntropyTerm(kind="binary_cross_entropy")],
        ),
        1,
        IGNORE,
    )
    image = torch.randn(2, 3, 4, 6)
    target = torch.full((2, 4, 6), IGNORE)

    loss, parts = dense_training_objective(
        model,
        objective,
        image,
        target,
        torch.tensor([[True, True], [True, True]]),
    )
    loss.backward()

    assert loss.item() == 0.0
    assert parts["empty_crop"].item() == 1.0
    assert all(parameter.grad is not None for parameter in model.parameters())
    assert all(torch.count_nonzero(parameter.grad) == 0 for parameter in model.parameters())


def test_single_view_binary_prediction_uses_sigmoid_and_configured_threshold() -> None:
    logits = torch.tensor([[[[-2.0, 0.0, 2.0]]]])
    default = prediction_from_inference(
        logits, InferenceConfig(sliding_window=False, task="binary")
    )
    high = prediction_from_inference(
        logits,
        InferenceConfig(sliding_window=False, task="binary", threshold=0.8),
    )
    assert default.tolist() == [[[0, 1, 1]]]
    assert high.tolist() == [[[0, 0, 1]]]


def test_binary_tta_averages_sigmoid_probabilities_not_logits() -> None:
    class SequencedModel:
        def __init__(self) -> None:
            self.values = iter((0.0, 2.0))

        def __call__(self, image: Tensor) -> Tensor:
            value = next(self.values)
            return torch.full(
                (image.shape[0], 1, image.shape[2], image.shape[3]),
                value,
                device=image.device,
            )

    image = torch.zeros(1, 3, 3, 4)
    cfg = InferenceConfig(
        sliding_window=False,
        scales=(1.0,),
        flip=True,
        task="binary",
        threshold=0.7,
    )
    scores = inference(SequencedModel(), image, 2, cfg)
    expected = (torch.sigmoid(torch.tensor(0.0)) + torch.sigmoid(torch.tensor(2.0))) / 2
    assert torch.allclose(scores, torch.full_like(scores, expected))
    assert not torch.allclose(scores, torch.full_like(scores, torch.sigmoid(torch.tensor(1.0))))
    assert prediction_from_inference(scores, cfg).eq(0).all()


def test_binary_sliding_window_stitches_one_channel_and_multiclass_is_unchanged() -> None:
    class PixelModel:
        def __call__(self, image: Tensor) -> Tensor:
            return image[:, :1] - 0.25

    image = torch.arange(3 * 9 * 11).reshape(1, 3, 9, 11).float()
    cfg = InferenceConfig(
        window=(5, 6),
        stride=(3, 4),
        task="binary",
    )
    tiled = slide_inference(PixelModel(), image, 2, cfg)
    whole = whole_inference(PixelModel(), image, 2, task="binary")
    assert tiled.shape == (1, 1, 9, 11)
    torch.testing.assert_close(tiled, whole, rtol=0, atol=0)

    multiclass_scores = torch.randn(2, 4, 5, 6)
    pred = prediction_from_inference(multiclass_scores, InferenceConfig())
    assert torch.equal(pred, multiclass_scores.argmax(dim=1))


def test_task_channel_mismatches_fail_before_prediction() -> None:
    image = torch.zeros(1, 3, 4, 4)

    with pytest.raises(ValueError, match="exactly one raw class-1 positive logit"):
        whole_inference(
            lambda value: torch.zeros(1, 2, 4, 4),
            image,
            2,
            task="binary",
        )
    with pytest.raises(ValueError, match="different label space"):
        whole_inference(lambda value: torch.zeros(1, 1, 4, 4), image, 2)
    with pytest.raises(ValueError, match="refusing to argmax"):
        prediction_from_inference(torch.zeros(1, 1, 4, 4), InferenceConfig())


def test_binary_lightning_validation_thresholds_into_two_class_metrics(monkeypatch) -> None:
    model = _OneLogitModel()
    with torch.no_grad():
        model.encoder.weight.zero_()
        model.encoder.bias.zero_()
        model.classifier.weight.zero_()
        model.classifier.bias.fill_(1.0)
    loss = SegmentationLoss(
        LossConfig(
            task="binary",
            terms=[BinaryCrossEntropyTerm(kind="binary_cross_entropy")],
        ),
        1,
        IGNORE,
    )
    lit = SegLitModule(
        model,
        loss,
        _space(),
        optim_cfg=OptimConfig(),
        train_cfg=TrainConfig(ema_decay=None),
        eval_cfg=EvalConfig(sliding_window=False, threshold=0.8),
        eval_active=torch.tensor([True, True]),
    )
    monkeypatch.setattr(lit, "log", lambda *args, **kwargs: None)
    lit.on_validation_epoch_start()
    target = torch.tensor([[[0, 1], [IGNORE, 0]]])
    lit.validation_step({"image": torch.zeros(1, 3, 2, 2), "mask": target}, 0)
    assert torch.equal(lit._cm.mat.cpu(), torch.tensor([[2, 0], [1, 0]]))


def _write_pair(root: Path, split: str, key: str, *, phase: int) -> None:
    height = width = 32
    yy, xx = np.mgrid[:height, :width]
    mask = (((xx + yy + phase) % 11) < 5).astype(np.uint8)
    mask[:2, :3] = IGNORE
    image = np.stack(
        (
            np.where(mask == 1, 230, 20),
            ((xx * 7 + phase) % 255).astype(np.uint8),
            ((yy * 9 + phase) % 255).astype(np.uint8),
        ),
        axis=-1,
    ).astype(np.uint8)
    image_path = root / "images" / split / f"{key}.png"
    mask_path = root / "masks" / split / f"{key}.png"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    mask_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(image, mode="RGB").save(image_path)
    Image.fromarray(mask, mode="L").save(mask_path)


def _write_binary_project(tmp_path: Path) -> tuple[Path, Path, Path]:
    taxonomy = tmp_path / "taxonomy"
    space_root = taxonomy / "binary"
    space_root.mkdir(parents=True)
    (space_root / "canonical.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "binary",
                "description": "synthetic binary smoke",
                "ignore_index": IGNORE,
                "classes": [
                    {"id": 0, "name": "background", "color": [0, 0, 0]},
                    {"id": 1, "name": "foreground", "color": [255, 0, 0]},
                ],
            }
        ),
        encoding="utf-8",
    )
    (space_root / "synthetic.yaml").write_text(
        yaml.safe_dump(
            {
                "space": "binary",
                "dataset": "synthetic",
                "source": "generated test masks",
                "default": IGNORE,
                "map": {0: 0, 1: 1, IGNORE: IGNORE},
            }
        ),
        encoding="utf-8",
    )

    data = tmp_path / "data"
    _write_pair(data, "train", "a", phase=0)
    _write_pair(data, "train", "b", phase=3)
    _write_pair(data, "val", "c", phase=6)

    config = tmp_path / "binary.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "name": "binary-disk-smoke",
                "space": "binary",
                "taxonomy_root": str(taxonomy),
                "output_root": str(tmp_path / "runs"),
                "model": {
                    "arch": "native",
                    "native": {
                        "task": "binary",
                        "backbone": {
                            "kind": "timm",
                            "name": "resnet18",
                            "weights": "scratch",
                            "out_indices": [1, 2, 3, 4],
                        },
                        "head": {
                            "kind": "fcn",
                            "in_indices": [3],
                            "channels": 8,
                            "num_convs": 1,
                            "dropout": 0.0,
                        },
                    },
                },
                "loss": {
                    "task": "binary",
                    "terms": [{"kind": "binary_cross_entropy"}],
                },
                "train": {
                    "iters": 1,
                    "batch_size": 2,
                    "num_workers": 0,
                    "precision": "32-true",
                    "ema_decay": None,
                    "val_every": 1,
                    "ckpt_every": 1,
                },
                "eval": {
                    "sliding_window": False,
                    "batch_size": 1,
                    "num_workers": 0,
                    "threshold": 0.6,
                },
                "aug": {
                    "crop": [32, 32],
                    "scale_min": 1.0,
                    "scale_max": 1.0,
                    "hflip_p": 0.0,
                    "color_jitter_p": 0.0,
                },
                "stages": [
                    {
                        "name": "train",
                        "data": [
                            {
                                "name": "synthetic",
                                "root": str(data),
                                "loader": "folder",
                                "mapping": "synthetic",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return config, taxonomy, data


def test_segmentary_train_runs_binary_folder_curriculum_on_cpu(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    torch.manual_seed(12)
    config_path, taxonomy_root, _ = _write_binary_project(tmp_path)
    repo_root = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)

    expected_sha, expected_dirty = git_sha(repo_root)
    assert expected_sha != "unknown"
    assert train_module.main([str(config_path), "--devices", "1"]) == 0

    cfg = load_experiment([config_path])
    space = load_space(taxonomy_root, "binary")
    run_dir = Path(cfg.output_root) / f"{cfg.name}_seed{cfg.train.seed}" / "train"
    checkpoint_path = run_dir / "last.ckpt"
    results_path = run_dir / "results.json"
    assert checkpoint_path.is_file()
    assert results_path.is_file()

    tensorboard_dir = run_dir / "tensorboard"
    event_files = list(tensorboard_dir.glob("events.out.tfevents*"))
    assert len(event_files) == 1
    assert (tensorboard_dir / "hparams.yaml").is_file()
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    events = EventAccumulator(str(event_files[0]), size_guidance={"scalars": 0})
    events.Reload()
    scalar_tags = set(events.Tags()["scalars"])
    assert {
        "train/loss",
        "train/lr",
        "train/iteration",
        "train/progress",
        "train/optimizer_steps_per_sec",
        "train/examples_per_sec",
        "train/elapsed_seconds",
        "train/eta_seconds",
        "val/miou",
        "val/macc",
        "val/pixel_acc",
        "val/boundary_f1",
    } <= scalar_tags
    assert events.Scalars("train/iteration")[-1].value == 1
    assert events.Scalars("train/progress")[-1].value == pytest.approx(1.0)
    assert events.Scalars("train/eta_seconds")[-1].value == pytest.approx(0.0)

    checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    assert checkpoint["global_step"] == cfg.train.iters == 1
    assert len(checkpoint["optimizer_states"]) == 1
    optimizer_state = checkpoint["optimizer_states"][0]["state"]
    assert optimizer_state
    assert {int(state["step"]) for state in optimizer_state.values()} == {1}
    assert checkpoint["state_dict"]["model.head.classifier.weight"].shape[0] == 1

    model = build_model(cfg.model, space.num_classes)
    eval_module.load_checkpoint(model, checkpoint_path, use_ema=False)
    model.eval()
    with torch.inference_mode():
        logits = model(torch.zeros(1, 3, 32, 32))
    assert model.task == "binary"
    assert model.num_classes == 2
    assert model.output_channels == 1
    assert logits.shape == (1, 1, 32, 32)

    curriculum_record = json.loads(results_path.read_text(encoding="utf-8"))
    assert curriculum_record["config"] == to_dict(cfg)
    assert curriculum_record["config_hash"] == config_hash(cfg)
    assert curriculum_record["git_sha"] == expected_sha
    assert curriculum_record["git_dirty"] is expected_dirty
    assert curriculum_record["config"]["loss"]["task"] == "binary"
    assert curriculum_record["config"]["model"]["native"]["task"] == "binary"
    assert curriculum_record["config"]["eval"]["threshold"] == 0.6
    assert curriculum_record["env"]["cuda_available"] is False
    assert curriculum_record["env"]["gpu_count"] == 0
    assert curriculum_record["peak_vram_bytes"] == {}
    assert curriculum_record["dataset_sizes"] == {
        "train": 2,
        "train:synthetic": 2,
        "val": 1,
    }
    assert len(curriculum_record["metrics"]["confusion"]) == 2
    assert all(len(row) == 2 for row in curriculum_record["metrics"]["confusion"])
    assert curriculum_record["metrics"]["support"]["foreground"] > 0

    eval_results = tmp_path / "eval" / "results.json"
    assert (
        eval_module.main(
            [
                str(config_path),
                "--ckpt",
                str(checkpoint_path),
                "--device",
                "cpu",
                "--num-workers",
                "0",
                "--out",
                str(eval_results),
            ]
        )
        == 0
    )
    eval_record = json.loads(eval_results.read_text(encoding="utf-8"))
    assert eval_record["config"]["evaluation"]["prediction"] == {
        "activation": "sigmoid",
        "task": "binary",
        "threshold": 0.6,
    }
    assert eval_record["git_sha"] == expected_sha
    assert eval_record["git_dirty"] is expected_dirty


def test_binary_checkpoint_cannot_load_into_two_logit_multiclass_model(tmp_path: Path) -> None:
    binary = _OneLogitModel()
    checkpoint = tmp_path / "binary.ckpt"
    torch.save(
        {
            "state_dict": {
                f"model.{name}": value.detach().clone()
                for name, value in binary.state_dict().items()
            }
        },
        checkpoint,
    )

    with pytest.raises(RuntimeError, match=r"size mismatch for classifier\.(weight|bias)"):
        eval_module.load_checkpoint(
            _TwoLogitModel(),
            checkpoint,
            use_ema=False,
        )


def test_real_on_disk_binary_overfit_cli_smoke(tmp_path: Path) -> None:
    config_path, _, _ = _write_binary_project(tmp_path)

    assert (
        overfit_module.main(
            [
                str(config_path),
                "--images",
                "2",
                "--iters",
                "1",
                "--target",
                "0.000001",
                "--crop",
                "32",
                "32",
                "--device",
                "cpu",
                "--seed",
                "3",
            ]
        )
        == 0
    )


def test_binary_dataset_mapping_without_both_classes_fails_before_training(tmp_path: Path) -> None:
    config_path, taxonomy_root, _ = _write_binary_project(tmp_path)
    mapping_path = taxonomy_root / "binary" / "synthetic.yaml"
    mapping = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    mapping["map"][1] = IGNORE
    mapping_path.write_text(yaml.safe_dump(mapping), encoding="utf-8")

    cfg = load_experiment([config_path])
    space = load_space(taxonomy_root, "binary")
    with pytest.raises(ValueError, match=r"both canonical classes.*sample rows=\[0\]"):
        validate_data_task_contract(cfg, space)
