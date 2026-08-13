"""Focused proofs for fixed-shape ONNX/TensorRT deployment export."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import torch
import yaml
from PIL import Image
from torch import nn
from torch.nn import functional as F

from segmentary import export as export_module
from segmentary.config import ExperimentConfig, ModelConfig, from_dict, to_dict
from segmentary.models.factory import build_model
from segmentary.utils.results import load_results


class TinyDenseModel(nn.Module):
    """Small fixed-shape graph that exercises Conv quantisation and four-D output."""

    def __init__(self, classes: int = 3) -> None:
        super().__init__()
        self.conv = nn.Conv2d(3, classes, kernel_size=3, padding=1)

    def forward(self, image: torch.Tensor) -> torch.Tensor:
        return self.conv(image).relu()


def _cfg() -> ExperimentConfig:
    return from_dict(
        ExperimentConfig,
        {
            "name": "export-test",
            "space": "rail_union",
            "model": {"arch": "segformer_b2"},
            "train": {"seed": 7},
            "stages": [
                {
                    "name": "cityscapes",
                    "data": [{"name": "cityscapes", "root": "/unused"}],
                }
            ],
        },
    )


def _metrics() -> dict:
    return {
        "miou": 0.5,
        "macc": 0.6,
        "pixel_accuracy": 0.7,
        "freqw_iou": 0.4,
        "per_class_iou": {"a": 0.4, "b": 0.6},
        "per_class_acc": {"a": 0.5, "b": 0.7},
        "support": {"a": 10, "b": 20},
        "boundary": {"macro_f1": 0.45},
    }


@pytest.mark.parametrize("arch", sorted(export_module.SUPPORTED_ARCHS))
def test_supported_dense_architectures_have_no_block_reason(arch: str) -> None:
    assert export_module.unsupported_reason(arch) is None


@pytest.mark.parametrize("arch", ["mask2former_dinov3", "eomt_large", "eomt_dinov3_large"])
def test_mask_classification_export_is_explicitly_unsupported(arch: str) -> None:
    reason = export_module.unsupported_reason(arch)
    assert reason is not None
    assert "unsupported" in reason
    assert "dynamic/control-flow" in reason


def test_resize_sample_preserves_integer_mask_ids_and_fixed_shape() -> None:
    image = torch.arange(3 * 4 * 8, dtype=torch.float32).reshape(3, 4, 8)
    mask = torch.tensor(
        [[0, 0, 1, 1, 2, 2, 255, 255]] * 2 + [[3, 3, 4, 4, 5, 5, 255, 255]] * 2,
        dtype=torch.long,
    )
    fixed_image, fixed_mask = export_module.resize_sample(image, mask, (8, 16))
    assert fixed_image.shape == (3, 8, 16)
    assert fixed_mask.shape == (8, 16)
    assert fixed_mask.dtype == torch.long
    assert set(fixed_mask.unique().tolist()) <= set(mask.unique().tolist())


def test_summary_reports_unsupported_rows_instead_of_silently_skipping(tmp_path: Path) -> None:
    config = tmp_path / "eomt.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "name": "unsupported-export",
                "space": "rail_union",
                "model": {"arch": "eomt_large"},
                "stages": [
                    {
                        "name": "cityscapes",
                        "data": [{"name": "cityscapes", "root": "/unused"}],
                    }
                ],
            }
        )
    )
    out = tmp_path / "export"
    assert (
        export_module.main(
            [str(config), "--ckpt", str(tmp_path / "absent.ckpt"), "--out", str(out)]
        )
        == 0
    )
    report = json.loads((out / "export_summary.json").read_text())
    assert [row["variant"] for row in report["variants"]] == [
        "onnx_fp32",
        "tensorrt_fp16",
        "tensorrt_int8",
    ]
    assert all("unsupported" in row["status"] for row in report["variants"])
    table = (out / "export_table.md").read_text()
    assert "Mask2Former/EoMT" in table


def test_untrained_summary_and_record_are_unmistakably_labeled(tmp_path: Path) -> None:
    metadata = {"untrained_test_only": True}
    export_module.write_summary(tmp_path, metadata, [{"variant": "pytorch_fp32", "status": "ok"}])
    summary = json.loads((tmp_path / "export_summary.json").read_text())
    assert summary["metadata"]["untrained_test_only"] is True
    assert "not model-quality evidence" in (tmp_path / "export_table.md").read_text()

    cfg = _cfg()
    path = tmp_path / "records" / "pytorch_fp32" / "results.json"
    export_module.write_variant_result(
        path,
        cfg=cfg,
        export_config={"export": {"untrained_test_only": True}},
        variant="pytorch_fp32",
        metrics=_metrics(),
        deployment={
            "backend": "pytorch",
            "precision": "fp32",
            "untrained_test_only": True,
        },
        elapsed_s=1.0,
        eval_samples=1,
        calibration_samples=1,
        checkpoint=tmp_path / "untrained.ckpt",
        use_ema=False,
    )
    record = load_results(path)
    assert record.metrics["deployment"]["untrained_test_only"] is True
    assert "UNTRAINED TEST ONLY" in record.notes


def test_variant_record_uses_standard_results_schema(tmp_path: Path) -> None:
    cfg = _cfg()
    export_config = to_dict(cfg)
    export_config["export"] = {"shape_nchw": [1, 3, 8, 12]}
    path = tmp_path / "records" / "onnx_fp32" / "results.json"
    export_module.write_variant_result(
        path,
        cfg=cfg,
        export_config=export_config,
        variant="onnx_fp32",
        metrics=_metrics(),
        deployment={
            "backend": "onnxruntime_cuda",
            "precision": "fp32",
            "latency": {"p50_ms": 1.0, "p95_ms": 1.2},
            "miou_degradation": 0.0,
        },
        elapsed_s=2.0,
        eval_samples=2,
        calibration_samples=1,
        checkpoint=tmp_path / "model.ckpt",
        use_ema=False,
    )
    record = load_results(path)
    assert record.stage == "export:onnx_fp32"
    assert record.config == export_config
    assert record.metrics["miou"] == 0.5
    assert record.metrics["deployment"]["latency"]["p95_ms"] == 1.2


def test_fixed_onnx_export_matches_onnxruntime_on_cpu(tmp_path: Path) -> None:
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    torch.manual_seed(3)
    model = TinyDenseModel().eval()
    image = torch.randn(1, 3, 8, 12)
    path = tmp_path / "tiny.onnx"
    export_module.export_onnx(model, image, path)
    runner = export_module.OnnxRunner(path, tuple(image.shape), torch.device("cpu"))
    parity = export_module.assert_onnx_parity(model, runner, image, rtol=1e-5, atol=1e-6)
    assert parity["max_abs"] < 1e-5
    with pytest.raises(ValueError, match="fixed shape"):
        runner(torch.randn(1, 3, 9, 12))


@pytest.mark.gpu
def test_onnxruntime_cuda_provider_is_actually_active(tmp_path: Path) -> None:
    pytest.importorskip("onnx")
    ort = pytest.importorskip("onnxruntime")
    if not torch.cuda.is_available():
        pytest.skip("CUDA is unavailable")
    if "CUDAExecutionProvider" not in ort.get_available_providers():
        pytest.fail("pinned onnxruntime-gpu wheel exposes no CUDAExecutionProvider")
    model = TinyDenseModel().cuda().eval()
    image = torch.randn(1, 3, 8, 12, device="cuda")
    path = tmp_path / "tiny.onnx"
    export_module.export_onnx(model, image, path)
    runner = export_module.OnnxRunner(path, tuple(image.shape), torch.device("cuda"))
    assert runner.session.get_providers()[0] == "CUDAExecutionProvider"
    parity = export_module.assert_onnx_parity(model, runner, image, rtol=1e-4, atol=1e-5)
    assert parity["max_abs"] < 1e-4


@pytest.mark.slow
@pytest.mark.gpu
@pytest.mark.parametrize("arch", ["segformer_b2", "deeplabv3plus_r101"])
def test_real_dense_architecture_matches_onnxruntime_cuda_on_real_image(
    arch: str, cityscapes_root: Path, tmp_path: Path
) -> None:
    """Prove each promised export arm, not only a toy graph, on real pixels."""
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime")
    if not torch.cuda.is_available():
        pytest.skip("CUDA is unavailable")

    source = next(
        iter(sorted((cityscapes_root / "leftImg8bit" / "val").rglob("*_leftImg8bit.png")))
    )
    rgb = np.asarray(Image.open(source).convert("RGB")).copy()
    image = torch.from_numpy(rgb).permute(2, 0, 1).float().div_(255.0).unsqueeze(0)
    image = F.interpolate(image, size=(256, 512), mode="bilinear", align_corners=False)
    mean = image.new_tensor((0.485, 0.456, 0.406)).view(1, 3, 1, 1)
    std = image.new_tensor((0.229, 0.224, 0.225)).view(1, 3, 1, 1)
    image = ((image - mean) / std).cuda()

    model = build_model(ModelConfig(arch=arch), num_classes=3).cuda().eval()
    with torch.inference_mode():
        logits = model(image)
    assert logits.shape == (1, 3, 256, 512)
    assert torch.isfinite(logits).all()

    path = tmp_path / f"{arch}.onnx"
    export_module.export_onnx(model, image, path)
    runner = export_module.OnnxRunner(path, tuple(image.shape), torch.device("cuda"))
    parity = export_module.assert_onnx_parity(
        model,
        runner,
        image,
        rtol=1e-3,
        atol=5e-3,
        min_argmax_agreement=0.999,
    )
    assert parity["argmax_agreement"] >= 0.999


def test_int8_quantizer_emits_explicit_qdq_nodes(tmp_path: Path) -> None:
    pytest.importorskip("onnx")
    pytest.importorskip("onnxruntime.quantization")
    torch.manual_seed(4)
    model = TinyDenseModel().eval()
    images = [torch.randn(1, 3, 8, 12) for _ in range(3)]
    fp32 = tmp_path / "tiny.onnx"
    int8 = tmp_path / "tiny_int8.onnx"
    export_module.export_onnx(model, images[0], fp32)
    q_nodes = export_module.quantize_int8_onnx(fp32, int8, images, device=torch.device("cpu"))
    assert q_nodes > 0
    assert int8.is_file()


@pytest.mark.gpu
def test_cuda_event_latency_is_batch_one_and_warmed() -> None:
    if not torch.cuda.is_available():
        pytest.skip("CUDA is unavailable")
    image = torch.randn(1, 3, 8, 12, device="cuda")
    model = TinyDenseModel().cuda().eval()
    stats = export_module.cuda_event_latency(model, image, warmup=2, iterations=4)
    assert stats.iterations == 4
    assert stats.warmup_iterations == 2
    assert stats.batch_size == 1
    assert stats.p50_ms > 0
    assert stats.p95_ms >= stats.p50_ms


@pytest.mark.slow
@pytest.mark.gpu
def test_tensorrt_builds_fp16_and_real_calibrated_int8_toy_engines(tmp_path: Path) -> None:
    pytest.importorskip("tensorrt")
    pytest.importorskip("onnxruntime.quantization")
    if not torch.cuda.is_available():
        pytest.skip("CUDA is unavailable")
    torch.manual_seed(5)
    device = torch.device("cuda")
    model = TinyDenseModel().to(device).eval()
    images = [torch.randn(1, 3, 8, 12) for _ in range(3)]
    fp32 = tmp_path / "tiny.onnx"
    fp16 = tmp_path / "tiny_fp16.onnx"
    int8 = tmp_path / "tiny_int8.onnx"
    export_module.export_onnx(model, images[0].to(device), fp32)
    export_module.convert_fp16_onnx(fp32, fp16)
    q_nodes = export_module.quantize_int8_onnx(fp32, int8, images, device=device)
    assert q_nodes > 0

    for precision, graph in (("fp16", fp16), ("int8", int8)):
        engine = tmp_path / f"tiny_{precision}.engine"
        elapsed = export_module.build_trt_engine(
            graph, engine, precision=precision, workspace_bytes=1 << 28
        )
        assert elapsed >= 0 and engine.stat().st_size > 0
        runner = export_module.TrtRunner(engine, device)
        output = runner(images[0].to(device))
        torch.cuda.synchronize()
        assert output.shape == (1, 3, 8, 12)
        assert torch.isfinite(output).all()
        if precision == "fp16":
            assert runner.precision_counts().get("fp16", 0) > 0
        else:
            assert runner.precision_counts().get("int8", 0) > 0
