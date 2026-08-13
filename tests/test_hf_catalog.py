"""Catalog integrity plus opt-in real-checkpoint tests for shipped HF recipes."""

from __future__ import annotations

import gc
import os
import re
from pathlib import Path

import numpy as np
import pytest
import torch
import torch.nn.functional as F
from transformers import AutoImageProcessor

from segmentary.config import load_experiment
from segmentary.data.loaders import aug_from_spec
from segmentary.data.transforms import build_eval_transform
from segmentary.engine.optim import build_optimizer
from segmentary.models.factory import build_model
from segmentary.models.tuning import apply_tuning

ROOT = Path(__file__).resolve().parents[1]
RECIPES = {
    "hf_auto_beit_base_ade.yaml": "hf-auto-beit-base-ade",
    "hf_auto_mobilenetv2_deeplabv3.yaml": "hf-auto-mobilenetv2-deeplabv3",
    "hf_auto_mobilevit_xxs_deeplabv3.yaml": "hf-auto-mobilevit-xxs-deeplabv3",
    "hf_auto_mobilevitv2_deeplabv3.yaml": "hf-auto-mobilevitv2-deeplabv3",
    "hf_auto_segformer_b0.yaml": "hf-auto-segformer-b0",
    "hf_auto_upernet_swin_tiny.yaml": "hf-auto-upernet-swin-tiny",
}


def _load(recipe: str):
    return load_experiment(
        [
            ROOT / "configs/base.yaml",
            ROOT / "configs/models" / recipe,
            ROOT / "configs/curricula/reference_cityscapes19.yaml",
        ]
    )


def test_hf_catalog_is_revision_pinned_documented_and_complete() -> None:
    found = {path.name for path in (ROOT / "configs/models").glob("hf_auto_*.yaml")}
    assert found == set(RECIPES)

    checkpoints: set[str] = set()
    for recipe, slug in RECIPES.items():
        cfg = _load(recipe)
        assert cfg.model.arch == "hf_auto"
        assert cfg.model.checkpoint is not None
        assert cfg.model.checkpoint not in checkpoints
        checkpoints.add(cfg.model.checkpoint)
        assert cfg.model.revision is not None
        assert re.fullmatch(r"[0-9a-f]{40}", cfg.model.revision)
        readme = ROOT / "docs/catalog/models" / slug / "README.md"
        text = readme.read_text(encoding="utf-8")
        assert recipe in text
        assert cfg.model.checkpoint in text
        assert cfg.model.revision in text
        assert "Pros" in text and "Cons" in text
        assert "benchmark" in text.lower()


@pytest.mark.slow
@pytest.mark.gpu
@pytest.mark.parametrize("recipe", sorted(RECIPES))
def test_real_hf_catalog_checkpoint_forward_backward(recipe: str) -> None:
    if os.environ.get("SEGMENTARY_RUN_HF_CATALOG") != "1":
        pytest.skip("set SEGMENTARY_RUN_HF_CATALOG=1 for the real Hub catalog acceptance")
    if not torch.cuda.is_available():
        pytest.skip("CUDA is required for the real Hub catalog acceptance")

    cfg = _load(recipe)
    torch.manual_seed(20260812)
    model = apply_tuning(build_model(cfg.model, num_classes=19), cfg.model).train().cuda()
    transform = build_eval_transform(aug_from_spec(cfg.aug, model))
    try:
        uint8_images = torch.randint(0, 256, (2, 128, 128, 3), dtype=torch.uint8).numpy()
        empty_mask = torch.zeros((128, 128), dtype=torch.uint8).numpy()
        transformed = torch.stack(
            [transform(image=image, mask=empty_mask)["image"] for image in uint8_images]
        )
        hub_kwargs = {
            "revision": cfg.model.revision,
            "local_files_only": cfg.model.local_files_only,
            "trust_remote_code": False,
        }
        if cfg.model.subfolder is not None:
            hub_kwargs["subfolder"] = cfg.model.subfolder
        processor = AutoImageProcessor.from_pretrained(cfg.model.checkpoint, **hub_kwargs)
        reference = processor(
            images=[np.asarray(image) for image in uint8_images],
            return_tensors="pt",
            do_resize=False,
            do_center_crop=False,
        ).pixel_values
        assert torch.allclose(transformed, reference, rtol=0.0, atol=1e-6)

        images = transformed.cuda()
        labels = torch.randint(0, 19, (2, 128, 128), device="cuda")
        optimizer = build_optimizer(model, cfg.optim, model.head_patterns())
        classifier = model.model.get_submodule(model.layout.classifier_path)
        classifier_before = [parameter.detach().clone() for parameter in classifier.parameters()]
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast("cuda", dtype=torch.bfloat16):
            logits = model(images)
            loss = F.cross_entropy(logits, labels)
        loss.backward()
        assert logits.shape == (2, 19, 128, 128)
        assert torch.isfinite(logits).all()
        assert torch.isfinite(loss)
        trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
        assert trainable
        frozen = {
            name for name, parameter in model.named_parameters() if not parameter.requires_grad
        }
        for path in cfg.model.inactive_parameter_paths:
            assert any(name.startswith(f"model.{path}.") for name in frozen)
        assert all(
            any(name.startswith(f"model.{path}.") for path in cfg.model.inactive_parameter_paths)
            for name in frozen
        )
        assert all(
            parameter.grad is not None and torch.isfinite(parameter.grad).all()
            for parameter in trainable
        )
        optimizer.step()
        assert any(
            not torch.equal(before, after)
            for before, after in zip(classifier_before, classifier.parameters(), strict=True)
        )
    finally:
        del model
        gc.collect()
        torch.cuda.empty_cache()
