"""Numerical, routing, and immutable-recipe checks for a patch Dice ablation."""

import dataclasses
import json

import pytest
import torch
from torch import nn

from segmentary.medical import model_registry, torch_backend
from segmentary.medical.cli import _config
from segmentary.medical.recipe_ablation import recipe_fingerprint
from segmentary.medical.torch_config import TorchConfig
from segmentary.medical.torch_data import dice_ce, training_loss


def historical_loss(logits, targets):
    probabilities = logits.float().softmax(1)
    truth = torch.nn.functional.one_hot(targets, 3).movedim(-1, 1).float()
    axes = (0, *range(2, logits.ndim))
    intersection = (probabilities * truth).sum(axes)
    denominator = (probabilities + truth).sum(axes)
    dice = (2 * intersection[1:] + 1e-5) / (denominator[1:] + 1e-5)
    return torch.nn.functional.cross_entropy(logits.float(), targets) + 1 - dice.mean()


@pytest.mark.parametrize("spatial", [(4, 7), (3, 4, 5)])
def test_default_batch_loss_and_gradients_are_bitwise_historical(spatial):
    torch.manual_seed(817)
    labels = torch.randint(0, 3, (3, *spatial))
    historical_logits = torch.randn(3, 3, *spatial, requires_grad=True)
    default_logits = historical_logits.detach().clone().requires_grad_()
    explicit_logits = historical_logits.detach().clone().requires_grad_()
    expected = historical_loss(historical_logits, labels)
    default = dice_ce(default_logits, labels)
    explicit = dice_ce(explicit_logits, labels, dice_reduction="batch")
    assert torch.equal(expected, default) and torch.equal(expected, explicit)
    expected.backward()
    default.backward()
    explicit.backward()
    assert torch.equal(historical_logits.grad, default_logits.grad)
    assert torch.equal(historical_logits.grad, explicit_logits.grad)


def test_per_sample_equally_weights_patches_with_unequal_mass_sizes():
    # A large correctly recognized mass and a small missed mass in equal-size
    # patches. The baseline pools class volumes; per_sample weights patches.
    labels = torch.zeros(2, 2, 10, dtype=torch.long)
    labels[0, :, :8] = 2
    labels[1, 0, 0] = 2
    labels[:, :, 9] = 1
    probabilities = torch.nn.functional.one_hot(labels, 3).movedim(-1, 1).float()
    probabilities = probabilities * 0.9 + 0.1 / 3
    probabilities[1, :, 0, 0] = torch.tensor([0.90, 0.09, 0.01])
    logits = probabilities.log().requires_grad_()
    separate = torch.stack([dice_ce(logits[i : i + 1], labels[i : i + 1]) for i in range(2)])
    per_sample = dice_ce(logits, labels, dice_reduction="per_sample")
    torch.testing.assert_close(per_sample, separate.mean(), rtol=1e-6, atol=1e-7)
    assert per_sample > dice_ce(logits, labels) + 0.1
    torch.testing.assert_close(
        torch.autograd.grad(per_sample, logits, retain_graph=True)[0],
        torch.autograd.grad(separate.mean(), logits)[0],
        rtol=1e-6,
        atol=1e-7,
    )


@pytest.mark.parametrize("all_background", [False, True])
@pytest.mark.parametrize("scale", [1, 1000])
def test_per_sample_gradients_remain_finite_with_reference_empty_classes(all_background, scale):
    torch.manual_seed(28)
    labels = torch.zeros(2, 3, 4, 5, dtype=torch.long)
    if not all_background:
        labels[1, 1, :2, :2] = 2  # Pancreas absent everywhere; mass absent in sample 0.
    logits = (torch.randn(2, 3, 3, 4, 5) * scale).requires_grad_()
    loss = dice_ce(logits, labels, dice_reduction="per_sample")
    assert torch.isfinite(loss)
    loss.backward()
    assert logits.grad is not None and torch.isfinite(logits.grad).all()
    assert logits.grad.abs().sum() > 0


def test_training_router_uses_configured_reduction(tmp_path):
    torch.manual_seed(51)
    model = nn.Conv3d(1, 3, kernel_size=1)
    images = torch.randn(2, 1, 3, 4, 5)
    labels = torch.zeros(2, 3, 4, 5, dtype=torch.long)
    labels[0, :2] = 2
    labels[1, 0, 0, 0] = 2
    config = TorchConfig(str(tmp_path), dice_reduction="per_sample")
    actual = training_loss(model, images, labels, config)
    expected = dice_ce(model(images), labels, dice_reduction="per_sample")
    assert torch.equal(actual, expected)
    assert not torch.equal(actual, training_loss(model, images, labels))


@pytest.mark.parametrize("value", [None, True, [], 0, "global", "patient"])
def test_invalid_reductions_are_rejected(value, tmp_path):
    with pytest.raises(ValueError, match="dice_reduction"):
        TorchConfig(str(tmp_path), dice_reduction=value)


@pytest.mark.parametrize(
    "options",
    [{"loss": "dice_focal"}, {"model_options": {"deep_supervision": True}}],
)
def test_reduction_does_not_silently_override_other_objectives(options, tmp_path):
    with pytest.raises(ValueError, match="only dense dice_ce"):
        TorchConfig(str(tmp_path), model="dynunet", dice_reduction="per_sample", **options)


def test_model_native_loss_is_preserved_or_rejected_explicitly(tmp_path):
    class Native(nn.Module):
        def training_loss(self, images, labels):
            return images.sum()

    image, labels = torch.ones(1, 1, 2, 2), torch.zeros(1, 2, 2, dtype=torch.long)
    config = TorchConfig(str(tmp_path))
    assert training_loss(Native(), image, labels, config) == 4
    with pytest.raises(ValueError, match="model-native"):
        training_loss(
            Native(), image, labels, dataclasses.replace(config, dice_reduction="per_sample")
        )


@pytest.mark.parametrize(
    "name",
    [
        "maskformer",
        "mask2former",
        "bisenetv2",
        "pidnet",
        "ddrnet",
        "convnext_upernet",
        "swin_upernet",
        "dpt",
        "hrnet_ocr",
    ],
)
def test_prepare_rejects_native_objective_before_reading_data(tmp_path, monkeypatch, name):
    config = TorchConfig(
        str(tmp_path),
        model=name,
        mode="2d",
        patch_size=(32, 32),
        dice_reduction="per_sample",
    )

    def forbidden(*args):
        raise AssertionError("Unsupported objective reached dataset access")

    monkeypatch.setattr(torch_backend, "_documents", forbidden)
    with pytest.raises(ValueError, match="model-native"):
        torch_backend.prepare_dataset("missing-manifest", "missing-splits", config, dry_run=True)
    assert model_registry.model_metadata(name)["training_loss"]["custom_training_loss"]


def test_prepare_records_actual_dense_loss_semantics(tmp_path, monkeypatch):
    config = TorchConfig(str(tmp_path / "run"), model="dynunet", dice_reduction="per_sample")
    monkeypatch.setattr(
        torch_backend,
        "_documents",
        lambda *args: (
            {"cases": [], "fingerprint": "manifest"},
            {"train": [], "val": [], "test": [], "fingerprint": "split"},
        ),
    )
    monkeypatch.setattr(torch_backend, "_sha", lambda path: "fixture-sha")
    monkeypatch.setattr(torch_backend, "_code", lambda: {})
    monkeypatch.setattr(torch_backend, "_runtime", lambda config: {})
    torch_backend.prepare_dataset("manifest", "splits", config)
    binding = json.loads((config.root / "binding.json").read_text())
    assert binding["config"]["dice_reduction"] == "per_sample"
    metadata = binding["architecture"]
    assert metadata["objective"] == "dense_ce_plus_per_sample_foreground_dice"
    assert metadata["dice_reduction"]["unit"] == "sampled patch, not necessarily a distinct patient"
    assert metadata["dice_reduction"]["classes"] == [1, 2]


def test_json_serialization_and_binding_reject_loss_change(tmp_path, monkeypatch):
    config = TorchConfig(str(tmp_path), dice_reduction="per_sample", gpu="cpu")
    record = torch_backend._config_record(config)
    assert record["dice_reduction"] == "per_sample"
    recipe = tmp_path / "recipe.json"
    recipe.write_text(json.dumps(record))
    assert _config(recipe) == config
    batch = dataclasses.replace(config, dice_reduction="batch")
    assert recipe_fingerprint(record) != recipe_fingerprint(torch_backend._config_record(batch))
    assert TorchConfig(**{k: v for k, v in record.items() if k != "dice_reduction"}) == batch
    binding = {
        "config": record,
        "code": {"fixture.py": "source"},
        "runtime": {},
        "manifest_path": "manifest",
        "manifest_sha256": "m",
        "splits_path": "splits",
        "splits_sha256": "s",
    }
    (tmp_path / "binding.json").write_text(json.dumps(binding))
    monkeypatch.setattr(torch_backend, "_code", lambda: {"fixture.py": "source"})
    monkeypatch.setattr(torch_backend, "_runtime", lambda config: {})
    monkeypatch.setattr(torch_backend, "_check_hash", lambda *args: None)
    assert torch_backend._binding(config) == binding
    with pytest.raises(ValueError, match="Configuration or source changed"):
        torch_backend._binding(batch)
