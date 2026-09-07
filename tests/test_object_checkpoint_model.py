"""Portable object checkpoints reconstruct real tiny models without pretrained IO."""

from __future__ import annotations

import copy
import shutil

import pytest
import torch
from transformers import (
    EomtConfig,
    EomtDinov3Config,
    EomtDinov3ForUniversalSegmentation,
    EomtForUniversalSegmentation,
    PreTrainedModel,
)

from segmentary.config import ModelConfig
from segmentary.models.mask_classification import MaskClassWrapper
from segmentary.models.tuning import apply_tuning
from segmentary.objects.checkpoint_model import model_spec, restore_model


def _model(arch: str) -> MaskClassWrapper:
    dino = arch == "eomt_dinov3_large"
    config_type = EomtDinov3Config if dino else EomtConfig
    model_type = EomtDinov3ForUniversalSegmentation if dino else EomtForUniversalSegmentation
    config = config_type(
        hidden_size=32,
        intermediate_size=64,
        num_hidden_layers=2,
        num_attention_heads=4,
        image_size=32,
        patch_size=8,
        num_blocks=1,
        num_upscale_blocks=1,
        num_queries=4,
        num_register_tokens=0,
        num_labels=1,
    )
    return MaskClassWrapper(
        model_type(config),
        1,
        backbone_paths=("embeddings", "layers", "layernorm")
        + (("rope_embeddings",) if dino else ()),
        head_paths=("query", "upscale_block", "mask_head", "class_predictor"),
        native_size=(32, 32),
    )


@pytest.mark.parametrize("arch", ["eomt_large", "eomt_dinov3_large"])
@pytest.mark.parametrize("tuning", ["full", "frozen", "lora"])
def test_offline_checkpoint_restores_exact_predictions_and_tuning(
    tmp_path, monkeypatch, arch, tuning
):
    initialization = tmp_path / "initialization"
    original = _model(arch)
    original.model.save_pretrained(initialization)
    config = ModelConfig(
        arch=arch,
        checkpoint=str(initialization),
        tuning=tuning,
        lora_r=2,
        lora_alpha=4,
        lora_dropout=0,
    )
    apply_tuning(original, config)
    original.eval()
    images = torch.randn(1, 3, 32, 32)
    with torch.no_grad():
        expected = original.forward_output(images).query.primary
    checkpoint = tmp_path / "trained.pt"
    torch.save({"model_spec": model_spec(original), "model": original.state_dict()}, checkpoint)
    shutil.rmtree(initialization)

    def forbidden(*args, **kwargs):
        raise AssertionError(
            "Restoring a complete object checkpoint must not load pretrained weights"
        )

    monkeypatch.setattr(PreTrainedModel, "from_pretrained", forbidden)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", forbidden)
    saved = torch.load(checkpoint, weights_only=True)
    restored = restore_model(saved["model_spec"], config, num_classes=1)
    restored.load_state_dict(saved["model"], strict=True)
    restored.eval()
    with torch.no_grad():
        actual = restored.forward_output(images).query.primary
    torch.testing.assert_close(actual.class_logits, expected.class_logits, rtol=0, atol=0)
    torch.testing.assert_close(actual.mask_logits, expected.mask_logits, rtol=0, atol=0)
    assert {name: p.requires_grad for name, p in restored.named_parameters()} == {
        name: p.requires_grad for name, p in original.named_parameters()
    }
    if tuning == "lora":
        assert any("lora_A" in name for name in restored.state_dict())


def test_checkpoint_model_rejects_unrecognized_architecture_and_mismatched_classes():
    spec = model_spec(_model("eomt_large"))
    wrong_model = copy.deepcopy(spec)
    wrong_model["model_class"] = "AutoModel.from_pretrained"
    with pytest.raises(ValueError, match="model type"):
        restore_model(wrong_model, ModelConfig(arch="eomt_large"), 1)
    with pytest.raises(ValueError, match="class count"):
        restore_model(spec, ModelConfig(arch="eomt_large"), 2)
    with pytest.raises(ValueError, match="architecture"):
        restore_model(spec, ModelConfig(arch="segformer_b0"), 1)
    with pytest.raises(ValueError, match="schema"):
        restore_model({}, ModelConfig(arch="eomt_large"), 1)
    with pytest.raises(ValueError, match="model type"):
        restore_model(spec, ModelConfig(arch="eomt_dinov3_large"), 1)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("native_size", [64, 64], "fixed token grid"),
        ("native_size", [0, 32], "native_size"),
        ("request_auxiliary_logits", "yes", "boolean"),
        ("backbone_paths", [], "module paths"),
        ("head_paths", [""], "module paths"),
        ("classifier_component", "", "nonempty"),
    ],
)
def test_invalid_wrapper_metadata_is_rejected(key, value, message):
    spec = model_spec(_model("eomt_large"))
    spec["wrapper"][key] = value
    with pytest.raises(ValueError, match=message):
        restore_model(spec, ModelConfig(arch="eomt_large"), 1)
