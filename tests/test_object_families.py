"""Real alternative architectures: gradients, tuning and offline reconstruction."""

import pytest
import torch
from transformers import (
    DetrConfig,
    Mask2FormerConfig,
    Mask2FormerForUniversalSegmentation,
    MaskFormerConfig,
    MaskFormerForInstanceSegmentation,
    SwinConfig,
)

from segmentary.config import ModelConfig
from segmentary.models.tuning import apply_tuning
from segmentary.objects.checkpoint_model import model_spec, restore_model
from segmentary.objects.data import ObjectTarget
from segmentary.objects.loss import ObjectQueryLoss
from segmentary.objects.model_factory import build_object_model, wrap_object_model


def tiny_family(arch, classes=2):
    backbone = SwinConfig(
        embed_dim=32,
        depths=[1, 1, 1, 1],
        num_heads=[1, 2, 4, 8],
        window_size=2,
        out_indices=[1, 2, 3, 4],
    )
    if arch == "mask2former_swin_tiny":
        config = Mask2FormerConfig(
            backbone_config=backbone,
            feature_size=32,
            mask_feature_size=32,
            hidden_dim=32,
            encoder_feedforward_dim=64,
            encoder_layers=1,
            decoder_layers=2,
            num_attention_heads=4,
            dim_feedforward=64,
            num_queries=4,
            num_labels=classes,
        )
        model = Mask2FormerForUniversalSegmentation(config)
    else:
        config = MaskFormerConfig(
            backbone_config=backbone,
            decoder_config=DetrConfig(
                d_model=32,
                decoder_layers=2,
                decoder_attention_heads=4,
                decoder_ffn_dim=64,
                num_queries=4,
            ),
            fpn_feature_size=32,
            mask_feature_size=32,
            num_labels=classes,
            use_auxiliary_loss=True,
        )
        model = MaskFormerForInstanceSegmentation(config)
    return wrap_object_model(model, arch, classes)


@pytest.mark.parametrize("arch", ["maskformer_swin_tiny", "mask2former_swin_tiny"])
@pytest.mark.parametrize("tuning", ["full", "frozen", "lora"])
def test_family_training_and_offline_roundtrip(arch, tuning):
    torch.set_num_threads(1)
    cfg = ModelConfig(arch=arch, tuning=tuning, lora_r=2, lora_dropout=0)
    model = apply_tuning(tiny_family(arch), cfg)
    masks = torch.zeros(2, 64, 64, dtype=torch.bool)
    masks[0, 4:24, 4:24] = True
    masks[1, 32:56, 32:56] = True
    target = ObjectTarget(
        torch.tensor([0, 0]),
        masks,
        torch.ones(64, 64, dtype=torch.bool),
        torch.zeros(2, dtype=torch.bool),
        1,
        (64, 64),
    )
    images = torch.randn(1, 3, 64, 64)
    output = model.forward_output(images).query
    assert output.auxiliary
    loss = ObjectQueryLoss(2, num_points=32)(output, [target])
    loss.backward()
    assert torch.isfinite(loss)
    assert any(p.grad is not None and p.grad.abs().sum() > 0 for p in model.parameters())
    rebuilt = restore_model(model_spec(model), cfg, 2)
    rebuilt.load_state_dict(model.state_dict(), strict=True)
    model.eval()
    rebuilt.eval()
    with torch.no_grad():
        expected = model.forward_output(images).query.primary
        actual = rebuilt.forward_output(images).query.primary
    torch.testing.assert_close(actual.class_logits, expected.class_logits, rtol=0, atol=0)
    torch.testing.assert_close(actual.mask_logits, expected.mask_logits, rtol=0, atol=0)


@pytest.mark.parametrize("arch", ["maskformer_swin_tiny", "mask2former_swin_tiny"])
def test_local_initializer_and_one_category(tmp_path, arch):
    model = tiny_family(arch, classes=1)
    model.model.save_pretrained(tmp_path)
    loaded = build_object_model(
        ModelConfig(arch=arch, checkpoint=str(tmp_path), local_files_only=True), 1
    )
    assert (
        loaded.forward_output(torch.randn(1, 3, 64, 64)).query.primary.class_logits.shape[-1] == 2
    )


def test_unused_swin_final_norm_does_not_affect_predictions():
    arch = "mask2former_swin_tiny"
    model = tiny_family(arch).eval()
    image = torch.rand(1, 3, 64, 64)
    norm = model.model.model.pixel_level_module.encoder.swin.layernorm
    expected = model.forward_output(image).query.primary.mask_logits.detach().clone()
    with torch.no_grad():
        norm.weight.fill_(1000)
        norm.bias.fill_(-1000)
    actual = model.forward_output(image).query.primary.mask_logits
    torch.testing.assert_close(actual, expected, rtol=0, atol=0)
    actual.sum().backward()
    assert norm.weight.grad is None and norm.bias.grad is None


def test_non_unified_head_rejected_before_loading():
    with pytest.raises(ValueError, match="unified_head"):
        build_object_model(ModelConfig(arch="mask2former_swin_tiny", head="per_stage_head"), 2)
