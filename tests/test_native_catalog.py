"""Parser and documentation admission for shipped native model recipes."""

from __future__ import annotations

from pathlib import Path

import pytest

from segmentary.config import ExperimentConfig, load_experiment

ROOT = Path(__file__).resolve().parents[1]
RECIPES = {
    "native_convnext_tiny_channelmapper_dpt.yaml": (
        "convnext_tiny.fb_in22k_ft_in1k",
        "channel_mapper",
        "dpt",
        0,
    ),
    "native_resnet18_fpn_fcn.yaml": ("resnet18.a1_in1k", "fpn", "fcn", 0),
    "native_resnet18_fpn_segformer_aux.yaml": (
        "resnet18.a1_in1k",
        "fpn",
        "segformer",
        1,
    ),
    "native_resnet50_psp.yaml": ("resnet50.a1_in1k", "identity", "psp", 0),
    "native_resnet50_aspp.yaml": ("resnet50.a1_in1k", "identity", "aspp", 0),
    "native_resnet50_deeplabv3plus.yaml": (
        "resnet50.a1_in1k",
        "identity",
        "deeplabv3plus",
        0,
    ),
    "native_resnet50_fpn_ocr.yaml": ("resnet50.a1_in1k", "fpn", "ocr", 0),
    "native_resnet101_uper.yaml": ("resnet101.a1_in1k", "identity", "uper", 0),
    "native_convnext_tiny_uper.yaml": (
        "convnext_tiny.fb_in22k_ft_in1k",
        "identity",
        "uper",
        0,
    ),
    "native_efficientnet_b0_deeplabv3plus.yaml": (
        "efficientnet_b0.ra_in1k",
        "identity",
        "deeplabv3plus",
        0,
    ),
    "native_mobilenetv3_large_deeplabv3plus.yaml": (
        "mobilenetv3_large_100.ra_in1k",
        "identity",
        "deeplabv3plus",
        0,
    ),
    "native_mobilenetv3_large_lraspp.yaml": (
        "mobilenetv3_large_100.ra_in1k",
        "identity",
        "lraspp",
        0,
    ),
}
MODEL_PAGES = {
    "native-convnext-tiny-channelmapper-dpt",
    "native-convnext-tiny-uper",
    "native-efficientnet-b0-deeplabv3plus",
    "native-mobilenetv3-large-deeplabv3plus",
    "native-mobilenetv3-large-lraspp",
    "native-resnet101-uper",
    "native-resnet18-fpn-fcn",
    "native-resnet18-fpn-segformer-aux",
    "native-resnet50-aspp",
    "native-resnet50-deeplabv3plus",
    "native-resnet50-fpn-ocr",
    "native-resnet50-psp",
}


def _parse(path: Path) -> ExperimentConfig:
    return load_experiment(
        [ROOT / "configs/base.yaml", path],
        {
            "name": "native-catalog-parse",
            "space": "example",
            "train": {"num_workers": 0},
            "eval": {"num_workers": 0},
            "stages": [
                {
                    "name": "smoke",
                    "data": [{"name": "example", "root": "data/example"}],
                }
            ],
        },
    )


def test_native_catalog_inventory_is_intentional() -> None:
    actual = {path.name for path in (ROOT / "configs/models").glob("native_*.yaml")}
    assert actual == set(RECIPES)


@pytest.mark.parametrize("filename", sorted(RECIPES))
def test_every_native_recipe_loads_through_the_real_parser(filename: str) -> None:
    expected_backbone, expected_neck, expected_head, expected_aux = RECIPES[filename]
    cfg = _parse(ROOT / "configs/models" / filename)

    assert cfg.model.arch == "native"
    assert cfg.model.native is not None
    assert cfg.model.native.task == "multiclass"
    assert cfg.model.native.backbone.name == expected_backbone
    assert cfg.model.native.backbone.weights == "pretrained"
    assert cfg.model.native.neck.kind == expected_neck
    assert cfg.model.native.head.kind == expected_head
    assert len(cfg.model.native.auxiliary_heads) == expected_aux
    assert cfg.optim.llrd == 1.0


def test_native_recipe_indices_match_admitted_feature_layouts() -> None:
    for filename in RECIPES:
        cfg = _parse(ROOT / "configs/models" / filename)
        assert cfg.model.native is not None
        backbone = cfg.model.native.backbone
        expected = (0, 1, 2, 3) if backbone.name.startswith("convnext_tiny.") else (1, 2, 3, 4)
        assert backbone.out_indices == expected


def test_every_native_recipe_has_complete_point_of_choice_guidance() -> None:
    pages_root = ROOT / "docs/catalog/models"
    actual = {page.parent.name for page in pages_root.glob("native-*/README.md")}
    assert actual == MODEL_PAGES
    for slug in sorted(MODEL_PAGES):
        text = (pages_root / slug / "README.md").read_text(encoding="utf-8").lower()
        for required in ("pros:", "cons:", "advanced", "compatibility", "evidence", "benchmark"):
            assert required in text, f"{slug} omits {required!r}"


def test_every_native_component_family_explains_choices_and_limits() -> None:
    components = ROOT / "docs/catalog/components"
    expected = {
        "native-backbones",
        "native-blocks",
        "native-heads",
        "native-necks",
    }
    actual = {page.parent.name for page in components.glob("native-*/README.md")}
    assert actual == expected
    for slug in sorted(expected):
        text = (components / slug / "README.md").read_text(encoding="utf-8").lower()
        for required in ("pros", "cons", "advanced", "compatibility", "evidence", "benchmark"):
            assert required in text, f"{slug} omits {required!r}"


def test_native_block_page_documents_every_typed_choice() -> None:
    text = (ROOT / "docs/catalog/components/native-blocks/README.md").read_text(encoding="utf-8")
    for choice in (
        "`batch`",
        "`group`",
        "`instance`",
        "`layer`",
        "`none`",
        "`relu`",
        "`relu6`",
        "`leaky_relu`",
        "`gelu`",
        "`silu`",
        "`elu`",
        "`mish`",
        "`hardswish`",
    ):
        assert choice in text
