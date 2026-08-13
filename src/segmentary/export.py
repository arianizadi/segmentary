"""Export fixed-shape dense segmentation models to ONNX and TensorRT.

The deployment benchmark deliberately uses one fixed ``NCHW`` shape.  TensorRT
engines are therefore reproducible, latency is not mixed across optimisation
profiles, and every backend sees the same resized Cityscapes pixels.  Successful
variants write ordinary :class:`~segmentary.utils.results.RunRecord` files under
``<out>/records/<variant>/results.json`` so the benchmark table generator can ingest
them without a second schema.

Only SegFormer-B2 and DeepLabV3+-R101 are supported.  Mask-classification models
(Mask2Former/EoMT) have dynamic/control-flow-heavy post-processing and are
reported as unsupported in the generated table instead of being skipped.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import statistics
import tempfile
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F
from torch import Tensor, nn

from .config import ExperimentConfig, config_hash, deep_merge, from_dict, load_yaml, to_dict
from .data.loaders import aug_from_spec, build_dataset, input_normalization
from .data.transforms import build_eval_transform
from .engine.boundary import BoundaryConfig, BoundaryF1
from .engine.metrics import ConfusionMatrix
from .eval import load_configured_checkpoint
from .models.factory import build_model
from .taxonomy import LabelSpace, load_mapping, load_space
from .utils.provenance import (
    collect_env,
    discover_git_root,
    git_sha,
    peak_vram,
    reset_peak_vram,
)
from .utils.results import RunRecord, write_results
from .utils.seed import seed_everything

SUPPORTED_ARCHS = frozenset({"segformer_b2", "deeplabv3plus_r101"})
MASK_CLASSIFICATION_ARCHS = frozenset({"mask2former_dinov3", "eomt_large", "eomt_dinov3_large"})


class ExportError(RuntimeError):
    """A deployment artifact failed validation or could not be built."""


@dataclass(frozen=True)
class LatencyStats:
    """Batch-one latency measured by CUDA events after warmup."""

    p50_ms: float
    p95_ms: float
    iterations: int
    warmup_iterations: int
    batch_size: int = 1
    timing: str = "cuda_events"


def unsupported_reason(arch: str) -> str | None:
    """Return an explicit deployment status for architectures outside C1."""
    if arch in SUPPORTED_ARCHS:
        return None
    if arch in MASK_CLASSIFICATION_ARCHS:
        return (
            "unsupported: Mask2Former/EoMT mask-classification post-processing has "
            "dynamic/control-flow-heavy execution and no verified fixed-shape export path"
        )
    return (
        f"unsupported: Part C1 validates only {sorted(SUPPORTED_ARCHS)}, not architecture {arch!r}"
    )


def resize_sample(image: Tensor, mask: Tensor, shape: tuple[int, int]) -> tuple[Tensor, Tensor]:
    """Resize one normalised sample and its integer mask to the export shape."""
    height, width = shape
    if height <= 0 or width <= 0:
        raise ValueError(f"fixed export shape must be positive, got {shape}")
    if image.ndim != 3 or mask.ndim != 2:
        raise ValueError(
            f"expected image CHW and mask HW, got image={tuple(image.shape)} mask={tuple(mask.shape)}"
        )
    fixed_image = F.interpolate(
        image.unsqueeze(0), size=shape, mode="bilinear", align_corners=False
    ).squeeze(0)
    fixed_mask = (
        F.interpolate(mask[None, None].float(), size=shape, mode="nearest")
        .squeeze(0)
        .squeeze(0)
        .long()
    )
    return fixed_image.contiguous(), fixed_mask.contiguous()


def take_fixed_samples(
    dataset: Any, count: int, shape: tuple[int, int]
) -> list[tuple[Tensor, Tensor]]:
    """Materialise a deterministic prefix of real samples at one fixed shape."""
    if count < 1:
        raise ValueError(f"sample count must be at least 1, got {count}")
    if len(dataset) < count:
        raise ValueError(
            f"requested {count} samples but {dataset.describe()} contains {len(dataset)}"
        )
    samples = []
    for index in range(count):
        item = dataset[index]
        samples.append(resize_sample(item["image"], item["mask"], shape))
    return samples


def export_onnx(
    model: nn.Module,
    example: Tensor,
    path: Path,
    *,
    opset: int = 18,
) -> None:
    """Export a fixed-shape ONNX graph and run the ONNX structural checker."""
    try:
        import onnx
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ExportError("ONNX export needs `pip install -e '.[export]'`") from exc

    if example.ndim != 4 or example.shape[0] != 1:
        raise ValueError(f"export input must be batch-one NCHW, got {tuple(example.shape)}")
    path.parent.mkdir(parents=True, exist_ok=True)
    model.eval()
    with torch.inference_mode():
        torch.onnx.export(
            model,
            (example,),
            path,
            input_names=["pixel_values"],
            output_names=["logits"],
            opset_version=opset,
            do_constant_folding=True,
            dynamo=False,
            dynamic_axes=None,
        )
    try:
        graph = onnx.load(path)
        onnx.checker.check_model(graph, full_check=True)
    except Exception as exc:
        raise ExportError(f"ONNX checker rejected {path}: {exc}") from exc

    input_shape = tuple(dim.dim_value for dim in graph.graph.input[0].type.tensor_type.shape.dim)
    if input_shape != tuple(example.shape):
        raise ExportError(
            f"ONNX input is not the requested fixed shape: graph={input_shape}, "
            f"requested={tuple(example.shape)}"
        )


class OnnxRunner:
    """ONNX Runtime runner with CUDA I/O binding (or a CPU test fallback)."""

    def __init__(self, path: Path, shape: tuple[int, int, int, int], device: torch.device):
        try:
            import onnxruntime as ort
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ExportError("ONNX Runtime needs `pip install -e '.[export]'`") from exc

        self.device = device
        self.shape = shape
        self.input_name = "pixel_values"
        self.output_name = "logits"
        self._ort = ort
        self._cuda = device.type == "cuda"
        if self._cuda:
            if "CUDAExecutionProvider" not in ort.get_available_providers():
                raise ExportError(
                    "onnxruntime-gpu has no CUDAExecutionProvider; CPU timing is not the "
                    "requested deployment benchmark"
                )
            index = device.index if device.index is not None else torch.cuda.current_device()
            stream = torch.cuda.current_stream(device)
            providers: list[Any] = [
                (
                    "CUDAExecutionProvider",
                    {
                        "device_id": str(index),
                        "user_compute_stream": str(stream.cuda_stream),
                        "do_copy_in_default_stream": "1",
                        # Match PyTorch's FP32 reference rather than allowing
                        # ONNX Runtime to silently trade mantissa bits for TF32.
                        "use_tf32": "0",
                    },
                )
            ]
        else:
            providers = ["CPUExecutionProvider"]
        self.session = ort.InferenceSession(str(path), providers=providers)
        actual_provider = self.session.get_providers()[0]
        expected_provider = "CUDAExecutionProvider" if self._cuda else "CPUExecutionProvider"
        if actual_provider != expected_provider:
            raise ExportError(
                f"ONNX Runtime requested {expected_provider} but activated {actual_provider}; "
                "refusing an unnoticed CPU fallback in the GPU benchmark"
            )
        if self.session.get_inputs()[0].name != self.input_name:
            raise ExportError(
                f"ONNX graph input is {self.session.get_inputs()[0].name!r}, "
                f"expected {self.input_name!r}"
            )
        if self.session.get_outputs()[0].name != self.output_name:
            raise ExportError(
                f"ONNX graph output is {self.session.get_outputs()[0].name!r}, "
                f"expected {self.output_name!r}"
            )
        output_shape = tuple(int(v) for v in self.session.get_outputs()[0].shape)
        if any(v <= 0 for v in output_shape):
            raise ExportError(f"ONNX output must have a fixed shape, got {output_shape}")
        self.output_shape = output_shape
        self.output = torch.empty(output_shape, dtype=torch.float32, device=device)

    def __call__(self, image: Tensor) -> Tensor:
        if tuple(image.shape) != self.shape:
            raise ValueError(f"ONNX input shape {tuple(image.shape)} != fixed shape {self.shape}")
        image = image.to(device=self.device, dtype=torch.float32).contiguous()
        if not self._cuda:
            output = self.session.run([self.output_name], {self.input_name: image.numpy()})[0]
            return torch.from_numpy(output)

        index = self.device.index if self.device.index is not None else torch.cuda.current_device()
        io = self.session.io_binding()
        io.bind_input(
            self.input_name,
            "cuda",
            index,
            np.float32,
            tuple(image.shape),
            image.data_ptr(),
        )
        io.bind_output(
            self.output_name,
            "cuda",
            index,
            np.float32,
            self.output_shape,
            self.output.data_ptr(),
        )
        self.session.run_with_iobinding(io)
        return self.output


def assert_onnx_parity(
    model: nn.Module,
    runner: Callable[[Tensor], Tensor],
    image: Tensor,
    *,
    rtol: float,
    atol: float,
    min_argmax_agreement: float = 0.999,
) -> dict[str, float]:
    """Assert ONNX Runtime matches PyTorch on a real input and report errors."""
    with torch.inference_mode():
        expected = model(image)
        actual = runner(image)
        if image.device.type == "cuda":
            torch.cuda.synchronize(image.device)
    if expected.shape != actual.shape:
        raise ExportError(
            f"ONNX Runtime output shape {tuple(actual.shape)} != PyTorch {tuple(expected.shape)}"
        )
    if expected.ndim == 4 and expected.shape[1] == 1:
        raise ExportError(
            "one-channel binary export parity is not implemented by Part C1; refusing "
            "meaningless argmax agreement on a single channel"
        )
    diff = (expected.float() - actual.float()).abs()
    max_abs = float(diff.max())
    mean_abs = float(diff.mean())
    argmax_agreement = float((actual.argmax(dim=1) == expected.argmax(dim=1)).float().mean())
    try:
        torch.testing.assert_close(actual.float(), expected.float(), rtol=rtol, atol=atol)
    except AssertionError as exc:
        raise ExportError(
            f"ONNX Runtime parity failed (rtol={rtol}, atol={atol}, "
            f"max_abs={max_abs:.6g}, mean_abs={mean_abs:.6g}): {exc}"
        ) from exc
    if argmax_agreement < min_argmax_agreement:
        raise ExportError(
            f"ONNX Runtime changed too many predicted classes: agreement "
            f"{argmax_agreement:.6f} < {min_argmax_agreement:.6f}"
        )
    return {
        "max_abs": max_abs,
        "mean_abs": mean_abs,
        "argmax_agreement": argmax_agreement,
        "rtol": rtol,
        "atol": atol,
    }


class _CalibrationReader:
    """ONNX Runtime calibration reader over a fixed real-image prefix."""

    def __init__(self, images: Sequence[Tensor]):
        self._images = [image.cpu().numpy().astype(np.float32, copy=False) for image in images]
        self._iterator: Iterable[np.ndarray] | None = None

    def get_next(self) -> dict[str, np.ndarray] | None:
        if self._iterator is None:
            self._iterator = iter(self._images)
        try:
            return {"pixel_values": next(self._iterator)}
        except StopIteration:
            return None

    def rewind(self) -> None:
        self._iterator = iter(self._images)


def quantize_int8_onnx(
    onnx_path: Path,
    output_path: Path,
    calibration_images: Sequence[Tensor],
    *,
    device: torch.device,
    nodes_to_exclude: Sequence[str] = (),
) -> int:
    """Create a symmetric Q/DQ ONNX graph calibrated on Cityscapes images.

    TensorRT 11 removed the legacy Python calibrator interfaces, so INT8 uses
    explicit quantisation: ONNX Runtime collects real-image ranges and inserts
    Q/DQ nodes, then TensorRT consumes that graph.
    """
    try:
        import onnx
        from onnxruntime.quantization import (
            CalibrationMethod,
            QuantFormat,
            QuantType,
            quantize_static,
        )
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ExportError("INT8 quantisation needs `pip install -e '.[export]'`") from exc

    if not calibration_images:
        raise ValueError("INT8 calibration needs at least one image")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    providers: list[Any]
    if device.type == "cuda":
        index = device.index if device.index is not None else torch.cuda.current_device()
        providers = [("CUDAExecutionProvider", {"device_id": str(index), "use_tf32": "0"})]
    else:
        providers = ["CPUExecutionProvider"]
    # Fail before the quantizer if CUDA EP cannot load. ORT otherwise logs a
    # warning and silently calibrates on CPU, hiding an incompatible wheel.
    import onnxruntime as ort

    probe = ort.InferenceSession(str(onnx_path), providers=providers)
    expected_provider = "CUDAExecutionProvider" if device.type == "cuda" else "CPUExecutionProvider"
    if probe.get_providers()[0] != expected_provider:
        raise ExportError(
            f"INT8 calibration requested {expected_provider} but ONNX Runtime activated "
            f"{probe.get_providers()[0]}"
        )
    del probe
    quantize_static(
        onnx_path,
        output_path,
        _CalibrationReader(calibration_images),
        quant_format=QuantFormat.QDQ,
        activation_type=QuantType.QInt8,
        weight_type=QuantType.QInt8,
        calibrate_method=CalibrationMethod.MinMax,
        per_channel=True,
        op_types_to_quantize=["Conv", "Gemm", "MatMul"],
        nodes_to_exclude=list(nodes_to_exclude),
        calibration_providers=providers,
        extra_options={
            "ActivationSymmetric": True,
            "WeightSymmetric": True,
            # TensorRT 11 accepts explicit INT8 Q/DQ but removed support for the
            # INT32 bias-dequantize pattern emitted by ORT. Keep convolution
            # biases floating point; weights and activations remain calibrated.
            "QuantizeBias": False,
        },
    )
    graph = onnx.load(output_path)
    onnx.checker.check_model(graph, full_check=True)
    q_nodes = sum(node.op_type == "QuantizeLinear" for node in graph.graph.node)
    dq_nodes = sum(node.op_type == "DequantizeLinear" for node in graph.graph.node)
    if q_nodes == 0 or dq_nodes == 0:
        raise ExportError(
            f"INT8 calibration produced no Q/DQ graph (Q={q_nodes}, DQ={dq_nodes}); "
            "TensorRT would silently build a floating-point engine"
        )
    return q_nodes


def convert_fp16_onnx(onnx_path: Path, output_path: Path) -> None:
    """Convert an FP32 graph to explicit FP16 types for TensorRT 11.

    TensorRT 11 is always strongly typed and removed ``BuilderFlag.FP16``.
    Precision must therefore be encoded in the graph before it is parsed.
    """
    try:
        import onnx
        from onnxconverter_common import float16
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ExportError(
            "TensorRT 11 FP16 export needs pinned `onnxconverter-common` from "
            "`pip install -e '.[export]'`"
        ) from exc

    graph = onnx.load(onnx_path)
    converted = float16.convert_float_to_float16(graph, keep_io_types=True)
    onnx.checker.check_model(converted, full_check=True)
    fp16_initializers = sum(
        initializer.data_type == onnx.TensorProto.FLOAT16
        for initializer in converted.graph.initializer
    )
    if fp16_initializers == 0:
        raise ExportError("FP16 conversion produced no FLOAT16 initializers")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    onnx.save(converted, output_path)


def build_trt_engine(
    onnx_path: Path,
    engine_path: Path,
    *,
    precision: str,
    workspace_bytes: int,
) -> float:
    """Build one fixed-shape TensorRT engine and return build seconds."""
    try:
        import tensorrt as trt
    except ImportError as exc:  # pragma: no cover - depends on optional extra
        raise ExportError(
            "TensorRT needs the pinned `tensorrt-cu12` package from `pip install -e '.[export]'`"
        ) from exc

    if precision not in {"fp16", "int8"}:
        raise ValueError(f"TensorRT precision must be fp16 or int8, got {precision!r}")
    if workspace_bytes <= 0:
        raise ValueError(f"workspace_bytes must be positive, got {workspace_bytes}")

    logger = trt.Logger(trt.Logger.WARNING)
    builder = trt.Builder(logger)
    # TensorRT 10+ removed the EXPLICIT_BATCH flag because explicit batch is now
    # unconditional.  Passing 0 also remains correct on the older API.
    network = builder.create_network(0)
    parser = trt.OnnxParser(network, logger)
    if not parser.parse(onnx_path.read_bytes()):
        errors = "\n".join(str(parser.get_error(i)) for i in range(parser.num_errors))
        raise ExportError(f"TensorRT could not parse {onnx_path}:\n{errors}")
    if network.num_inputs != 1 or network.num_outputs != 1:
        raise ExportError(
            f"expected one input and one output, got {network.num_inputs}/{network.num_outputs}"
        )
    if any(int(dim) <= 0 for dim in network.get_input(0).shape):
        raise ExportError(f"TensorRT input is not fixed-shape: {tuple(network.get_input(0).shape)}")

    config = builder.create_builder_config()
    config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_bytes)
    config.profiling_verbosity = trt.ProfilingVerbosity.DETAILED
    # TensorRT 11 removed FP16/INT8 builder flags and the legacy calibrator API.
    # The input graph is strongly typed: explicit FLOAT16 types select FP16, and
    # explicit Q/DQ nodes select INT8 with graph-declared floating-point fallback.

    started = time.perf_counter()
    plan = builder.build_serialized_network(network, config)
    elapsed = time.perf_counter() - started
    if plan is None:
        raise ExportError(f"TensorRT returned no {precision} engine for {onnx_path}")
    engine_path.parent.mkdir(parents=True, exist_ok=True)
    engine_path.write_bytes(bytes(plan))
    return elapsed


def _trt_torch_dtype(dtype: Any) -> torch.dtype:
    import tensorrt as trt

    mapping = {
        trt.float32: torch.float32,
        trt.float16: torch.float16,
        trt.int8: torch.int8,
        trt.int32: torch.int32,
        trt.bool: torch.bool,
    }
    if dtype not in mapping:
        raise ExportError(f"unsupported TensorRT tensor dtype {dtype}")
    return mapping[dtype]


class TrtRunner:
    """TensorRT 11 named-tensor runner on PyTorch's current CUDA stream."""

    def __init__(self, path: Path, device: torch.device):
        if device.type != "cuda":
            raise ValueError("TensorRT execution requires a CUDA device")
        try:
            import tensorrt as trt
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise ExportError("TensorRT needs `pip install -e '.[export]'`") from exc

        self._trt = trt
        self.device = device
        self.logger = trt.Logger(trt.Logger.WARNING)
        self.runtime = trt.Runtime(self.logger)
        self.engine = self.runtime.deserialize_cuda_engine(path.read_bytes())
        if self.engine is None:
            raise ExportError(f"TensorRT could not deserialize {path}")
        self.context = self.engine.create_execution_context()
        if self.context is None:
            raise ExportError(f"TensorRT could not create an execution context for {path}")
        inputs = []
        outputs = []
        for index in range(self.engine.num_io_tensors):
            name = self.engine.get_tensor_name(index)
            mode = self.engine.get_tensor_mode(name)
            (inputs if mode == trt.TensorIOMode.INPUT else outputs).append(name)
        if len(inputs) != 1 or len(outputs) != 1:
            raise ExportError(f"TensorRT engine needs one input/output, got {inputs}/{outputs}")
        self.input_name = inputs[0]
        self.output_name = outputs[0]
        self.input_shape = tuple(int(v) for v in self.engine.get_tensor_shape(self.input_name))
        self.output_shape = tuple(int(v) for v in self.engine.get_tensor_shape(self.output_name))
        if any(v <= 0 for v in (*self.input_shape, *self.output_shape)):
            raise ExportError(
                f"TensorRT engine is not fixed-shape: input={self.input_shape}, "
                f"output={self.output_shape}"
            )
        self.input_dtype = _trt_torch_dtype(self.engine.get_tensor_dtype(self.input_name))
        output_dtype = _trt_torch_dtype(self.engine.get_tensor_dtype(self.output_name))
        self.output = torch.empty(self.output_shape, dtype=output_dtype, device=device)
        # TensorRT warns and synchronises internally on CUDA's legacy default
        # stream. Use a dedicated stream for accurate asynchronous timing.
        self.stream = torch.cuda.Stream(device=device)

    def __call__(self, image: Tensor) -> Tensor:
        if tuple(image.shape) != self.input_shape:
            raise ValueError(
                f"TensorRT input shape {tuple(image.shape)} != fixed shape {self.input_shape}"
            )
        image = image.to(device=self.device, dtype=self.input_dtype).contiguous()
        self.context.set_tensor_address(self.input_name, image.data_ptr())
        self.context.set_tensor_address(self.output_name, self.output.data_ptr())
        self.stream.wait_stream(torch.cuda.current_stream(self.device))
        if not self.context.execute_async_v3(self.stream.cuda_stream):
            raise ExportError("TensorRT execute_async_v3 returned false")
        torch.cuda.current_stream(self.device).wait_stream(self.stream)
        return self.output

    def precision_counts(self) -> dict[str, int]:
        """Count layer precision strings from TensorRT's detailed inspector."""
        inspector = self.engine.create_engine_inspector()
        raw = inspector.get_engine_information(self._trt.LayerInformationFormat.JSON)
        try:
            report = json.loads(raw)
        except json.JSONDecodeError:
            return {"unknown": 1}
        layers = report.get("Layers", []) if isinstance(report, dict) else report
        counts: dict[str, int] = {}
        for layer in layers if isinstance(layers, list) else []:
            text = json.dumps(layer).lower()
            precision = next(
                (
                    name
                    for name, tokens in (
                        ("int8", ("int8",)),
                        ("fp16", ("half", "float16", "fp16")),
                        ("fp32", ("float", "float32", "fp32")),
                    )
                    if any(token in text for token in tokens)
                ),
                "unknown",
            )
            counts[precision] = counts.get(precision, 0) + 1
        return counts or {"unknown": 1}


def cuda_event_latency(
    runner: Callable[[Tensor], Tensor], image: Tensor, *, warmup: int, iterations: int
) -> LatencyStats:
    """Measure synchronous batch-one inference with CUDA events."""
    if image.device.type != "cuda":
        raise ValueError("deployment latency must be CUDA-event timed on a CUDA tensor")
    if image.shape[0] != 1:
        raise ValueError(f"latency benchmark requires batch 1, got {image.shape[0]}")
    if warmup < 1 or iterations < 1:
        raise ValueError(f"warmup and iterations must be positive, got {warmup}/{iterations}")
    with torch.inference_mode():
        for _ in range(warmup):
            runner(image)
        torch.cuda.synchronize(image.device)
        timings = []
        for _ in range(iterations):
            start = torch.cuda.Event(enable_timing=True)
            end = torch.cuda.Event(enable_timing=True)
            start.record()
            runner(image)
            end.record()
            end.synchronize()
            timings.append(float(start.elapsed_time(end)))
    return LatencyStats(
        p50_ms=float(statistics.median(timings)),
        p95_ms=float(np.percentile(np.asarray(timings), 95)),
        iterations=iterations,
        warmup_iterations=warmup,
    )


def evaluate_runner(
    runner: Callable[[Tensor], Tensor],
    samples: Sequence[tuple[Tensor, Tensor]],
    *,
    device: torch.device,
    space: LabelSpace,
    active: Tensor,
    boundary_tolerance_frac: float,
    save_confusion: bool,
) -> dict[str, Any]:
    """Evaluate one backend over the identical fixed-shape sample list."""
    cm = ConfusionMatrix(
        space.num_classes, space.ignore_index, active=active.to(device), device=device
    )
    boundary = BoundaryF1(
        space.num_classes,
        space.ignore_index,
        cfg=BoundaryConfig(tolerance_frac=boundary_tolerance_frac),
        active=active.to(device),
        device=device,
    )
    with torch.inference_mode():
        for image, target in samples:
            image_batch = image.unsqueeze(0).to(device, non_blocking=True)
            target_batch = target.unsqueeze(0).to(device, non_blocking=True)
            logits = runner(image_batch)
            if tuple(logits.shape) != (
                1,
                space.num_classes,
                *tuple(image_batch.shape[-2:]),
            ):
                raise ExportError(
                    f"backend output {tuple(logits.shape)} violates the segmentation contract"
                )
            if not bool(torch.isfinite(logits).all()):
                raise ExportError("backend produced non-finite logits")
            pred = logits.float().argmax(dim=1)
            cm.update(pred, target_batch)
            boundary.update(pred, target_batch)
    result = cm.compute()
    metrics = result.as_dict(list(space.names))
    metrics["boundary"] = boundary.compute().as_dict(list(space.names))
    if save_confusion:
        metrics["confusion"] = result.confusion.tolist()
    return metrics


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def write_variant_result(
    path: Path,
    *,
    cfg: ExperimentConfig,
    export_config: dict[str, Any],
    variant: str,
    metrics: dict[str, Any],
    deployment: dict[str, Any],
    elapsed_s: float,
    eval_samples: int,
    calibration_samples: int,
    checkpoint: Path,
    use_ema: bool,
    provenance_root: Path | None = None,
) -> None:
    """Write a table-consumable deployment result record."""
    sha, dirty = git_sha(provenance_root or Path.cwd())
    payload = dict(metrics)
    payload["deployment"] = deployment
    now = _utc_now()
    write_results(
        path,
        RunRecord(
            name=cfg.name,
            stage=f"export:{variant}",
            config_hash=config_hash(export_config),
            git_sha=sha,
            git_dirty=dirty,
            seed=cfg.train.seed,
            started_at=now,
            finished_at=now,
            wall_clock_s=elapsed_s,
            peak_vram_bytes=peak_vram(),
            metrics=payload,
            config=export_config,
            env=collect_env(),
            dataset_sizes={"eval": eval_samples, "calibration": calibration_samples},
            notes=(
                f"checkpoint={checkpoint} ema={use_ema}; deployment mIoU uses deterministic "
                "fixed-shape resizing and is comparable only within this export table"
                + (
                    "; UNTRAINED TEST ONLY: functional deployment evidence, not model-quality "
                    "evidence"
                    if deployment.get("untrained_test_only") is True
                    else ""
                )
            ),
        ),
    )


def _atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def write_summary(out_dir: Path, metadata: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    """Write the machine-readable report and human-readable latency/mIoU table."""
    _atomic_json(out_dir / "export_summary.json", {"metadata": metadata, "variants": rows})
    headers = (
        "variant",
        "status",
        "mIoU",
        "degradation",
        "p50_ms",
        "p95_ms",
        "artifact",
    )

    def shown(row: dict[str, Any], key: str) -> str:
        value = row.get(key)
        if value is None:
            return "--"
        if isinstance(value, float):
            return f"{value:.6f}" if key in {"mIoU", "degradation"} else f"{value:.3f}"
        return str(value).replace("|", "\\|")

    lines = [
        "# Fixed-shape deployment benchmark",
        "",
    ]
    if metadata.get("untrained_test_only") is True:
        lines.extend(
            [
                "> **UNTRAINED TEST ONLY.** This proves export, execution, parity, calibration, "
                "and relative runtime degradation. Absolute mIoU is not model-quality evidence.",
                "",
            ]
        )
    lines.extend(
        [
            "Latency is batch 1, CUDA-event timed after warmup. mIoU degradation is relative "
            "to the PyTorch FP32 row on the identical deterministically resized validation samples.",
            "",
            "| " + " | ".join(headers) + " |",
            "|" + "|".join("---" for _ in headers) + "|",
        ]
    )
    for row in rows:
        lines.append("| " + " | ".join(shown(row, key) for key in headers) + " |")
    (out_dir / "export_table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_config(paths: Sequence[Path]) -> ExperimentConfig:
    merged: dict[str, Any] = {}
    for path in paths:
        merged = deep_merge(merged, load_yaml(path))
    return from_dict(ExperimentConfig, merged)


def _cityscapes_data(cfg: ExperimentConfig, root: Path | None) -> Any:
    configured = [data for stage in cfg.stages for data in stage.data if data.name == "cityscapes"]
    if not configured:
        raise ExportError(
            "FP16/INT8 export needs a Cityscapes stage for real-input parity, calibration, "
            "and the deployment mIoU comparison"
        )
    data = configured[0]
    return replace(data, root=str(root) if root is not None else data.root, limit=None)


def _row(
    variant: str,
    status: str,
    *,
    artifact: Path | None = None,
    metrics: dict[str, Any] | None = None,
    degradation: float | None = None,
    latency: LatencyStats | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "variant": variant,
        "status": status,
        "mIoU": None if metrics is None else metrics.get("miou"),
        "degradation": degradation,
        "p50_ms": None if latency is None else latency.p50_ms,
        "p95_ms": None if latency is None else latency.p95_ms,
        "artifact": None if artifact is None else str(artifact),
        **extra,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("configs", nargs="+", type=Path)
    ap.add_argument("--ckpt", required=True, type=Path)
    ap.add_argument("--ema", action="store_true", help="export saved EMA weights")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--device", default="cuda:0")
    ap.add_argument("--shape", nargs=2, type=int, metavar=("HEIGHT", "WIDTH"), default=None)
    ap.add_argument("--cityscapes-root", type=Path, default=None)
    ap.add_argument("--calibration-samples", type=int, default=8)
    ap.add_argument("--eval-samples", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=20)
    ap.add_argument("--iterations", type=int, default=100)
    ap.add_argument("--workspace-gib", type=float, default=8.0)
    ap.add_argument("--opset", type=int, default=18)
    ap.add_argument("--onnx-rtol", type=float, default=1e-3)
    ap.add_argument("--onnx-atol", type=float, default=5e-3)
    ap.add_argument(
        "--untrained-test-only",
        action="store_true",
        help=(
            "mark every report and result as functional deployment evidence from an "
            "untrained model; absolute mIoU must not be interpreted as model quality"
        ),
    )
    ap.add_argument(
        "--int8-exclude-node",
        action="append",
        default=[],
        metavar="ONNX_NODE_NAME",
        help=(
            "leave one named ONNX node in floating point when TensorRT has no INT8 tactic; "
            "repeat for multiple nodes and inspect engine_layer_precision_counts"
        ),
    )
    ap.add_argument(
        "--backends",
        nargs="+",
        choices=("onnx", "fp16", "int8"),
        default=("onnx", "fp16", "int8"),
    )
    args = ap.parse_args(argv)

    for label, value in (
        ("--calibration-samples", args.calibration_samples),
        ("--eval-samples", args.eval_samples),
        ("--warmup", args.warmup),
        ("--iterations", args.iterations),
    ):
        if value < 1:
            ap.error(f"{label} must be at least 1")
    if args.workspace_gib <= 0 or not math.isfinite(args.workspace_gib):
        ap.error("--workspace-gib must be a positive finite number")

    cfg = _load_config(args.configs)
    provenance_root = discover_git_root([*args.configs, Path.cwd()]) or Path.cwd()
    shape = tuple(args.shape or cfg.aug.crop)
    out_dir = args.out or args.ckpt.parent / f"export_{shape[0]}x{shape[1]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    metadata = {
        "architecture": cfg.model.arch,
        "checkpoint": str(args.ckpt),
        "ema": args.ema,
        "shape_nchw": [1, 3, *shape],
        "batch_size": 1,
        "timing": "CUDA events after warmup",
        "calibration": "Cityscapes train, deterministic prefix, fixed-shape resize",
        "evaluation": "Cityscapes val, deterministic prefix, fixed-shape resize",
        "torch": torch.__version__,
        "cuda": torch.version.cuda,
        "untrained_test_only": args.untrained_test_only,
        "int8_excluded_nodes": list(args.int8_exclude_node),
    }
    if args.untrained_test_only:
        metadata["model_quality_warning"] = (
            "UNTRAINED TEST ONLY: absolute mIoU is not model-quality evidence; compare only "
            "runtime parity and degradation against this exact PyTorch baseline"
        )
    reason = unsupported_reason(cfg.model.arch)
    if reason is not None:
        rows = [
            _row(variant, reason) for variant in ("onnx_fp32", "tensorrt_fp16", "tensorrt_int8")
        ]
        write_summary(out_dir, metadata, rows)
        print(f"{reason}\nwrote {out_dir / 'export_table.md'}")
        return 0

    if not args.ckpt.is_file():
        raise FileNotFoundError(f"checkpoint not found: {args.ckpt}")
    if not torch.cuda.is_available():
        raise ExportError("Part C1 requires CUDA for TensorRT and CUDA-event latency")
    device = torch.device(args.device)
    if device.type != "cuda":
        raise ExportError("Part C1 latency must run on CUDA; choose --device cuda:N")
    torch.cuda.set_device(device)
    seed_everything(cfg.train.seed)

    taxonomy_root = Path(cfg.taxonomy_root)
    if not taxonomy_root.is_absolute():
        taxonomy_root = Path.cwd() / taxonomy_root
    space = load_space(taxonomy_root, cfg.space)
    cityscapes = _cityscapes_data(cfg, args.cityscapes_root)
    model = build_model(cfg.model, space.num_classes)
    model = load_configured_checkpoint(model, cfg, args.ckpt, args.ema)
    model = model.to(device).eval()
    transform = build_eval_transform(aug_from_spec(cfg.aug, model))
    train_dataset = build_dataset(
        cityscapes, space, taxonomy_root, cityscapes.train_split, transform
    )
    val_dataset = build_dataset(cityscapes, space, taxonomy_root, cityscapes.val_split, transform)
    calibration = take_fixed_samples(train_dataset, args.calibration_samples, shape)
    evaluation = take_fixed_samples(val_dataset, args.eval_samples, shape)
    active = torch.from_numpy(
        load_mapping(taxonomy_root, space, "cityscapes", cityscapes.variant).active_mask()
    )

    example = evaluation[0][0].unsqueeze(0).to(device)
    fixed_shape = tuple(int(v) for v in example.shape)
    export_cfg = to_dict(cfg)
    export_cfg["input_normalization"] = input_normalization(model)
    export_cfg["export"] = {
        "shape_nchw": list(fixed_shape),
        "calibration_samples": args.calibration_samples,
        "eval_samples": args.eval_samples,
        "warmup": args.warmup,
        "iterations": args.iterations,
        "workspace_gib": args.workspace_gib,
        "opset": args.opset,
        "onnx_rtol": args.onnx_rtol,
        "onnx_atol": args.onnx_atol,
        "untrained_test_only": args.untrained_test_only,
        "int8_excluded_nodes": list(args.int8_exclude_node),
    }
    rows: list[dict[str, Any]] = []

    def torch_runner(image: Tensor) -> Tensor:
        with torch.inference_mode():
            return model(image)

    reset_peak_vram()
    started = time.perf_counter()
    torch_metrics = evaluate_runner(
        torch_runner,
        evaluation,
        device=device,
        space=space,
        active=active,
        boundary_tolerance_frac=cfg.eval.boundary_tolerance_frac,
        save_confusion=cfg.eval.save_confusion,
    )
    torch_latency = cuda_event_latency(
        torch_runner, example, warmup=args.warmup, iterations=args.iterations
    )
    torch_elapsed = time.perf_counter() - started
    baseline_miou = float(torch_metrics["miou"])
    baseline_deployment = {
        "backend": "pytorch",
        "precision": "fp32",
        "latency": to_dict(torch_latency),
        "miou_degradation": 0.0,
        "fixed_shape": list(fixed_shape),
        "untrained_test_only": args.untrained_test_only,
    }
    write_variant_result(
        out_dir / "records" / "pytorch_fp32" / "results.json",
        cfg=cfg,
        export_config=export_cfg,
        variant="pytorch_fp32",
        metrics=torch_metrics,
        deployment=baseline_deployment,
        elapsed_s=torch_elapsed,
        eval_samples=args.eval_samples,
        calibration_samples=args.calibration_samples,
        checkpoint=args.ckpt,
        use_ema=args.ema,
        provenance_root=provenance_root,
    )
    rows.append(
        _row(
            "pytorch_fp32",
            "ok",
            metrics=torch_metrics,
            degradation=0.0,
            latency=torch_latency,
        )
    )

    onnx_path = out_dir / f"{cfg.model.arch}_{shape[0]}x{shape[1]}.onnx"
    try:
        export_onnx(model, example, onnx_path, opset=args.opset)
        onnx_runner = OnnxRunner(onnx_path, fixed_shape, device)
        parity = assert_onnx_parity(
            model,
            onnx_runner,
            example,
            rtol=args.onnx_rtol,
            atol=args.onnx_atol,
        )
    except Exception as exc:
        rows.append(_row("onnx_fp32", f"failed: {type(exc).__name__}: {exc}"))
        rows.extend(
            _row(variant, "blocked: ONNX export/parity failed")
            for variant in ("tensorrt_fp16", "tensorrt_int8")
        )
        write_summary(out_dir, metadata, rows)
        print(f"ONNX export failed: {exc}\nwrote {out_dir / 'export_table.md'}")
        return 1

    if "onnx" in args.backends:
        reset_peak_vram()
        started = time.perf_counter()
        onnx_metrics = evaluate_runner(
            onnx_runner,
            evaluation,
            device=device,
            space=space,
            active=active,
            boundary_tolerance_frac=cfg.eval.boundary_tolerance_frac,
            save_confusion=cfg.eval.save_confusion,
        )
        onnx_latency = cuda_event_latency(
            onnx_runner, example, warmup=args.warmup, iterations=args.iterations
        )
        elapsed = time.perf_counter() - started
        degradation = baseline_miou - float(onnx_metrics["miou"])
        deployment = {
            "backend": "onnxruntime_cuda",
            "precision": "fp32",
            "latency": to_dict(onnx_latency),
            "miou_degradation": degradation,
            "parity": parity,
            "fixed_shape": list(fixed_shape),
            "untrained_test_only": args.untrained_test_only,
        }
        write_variant_result(
            out_dir / "records" / "onnx_fp32" / "results.json",
            cfg=cfg,
            export_config=export_cfg,
            variant="onnx_fp32",
            metrics=onnx_metrics,
            deployment=deployment,
            elapsed_s=elapsed,
            eval_samples=args.eval_samples,
            calibration_samples=args.calibration_samples,
            checkpoint=args.ckpt,
            use_ema=args.ema,
            provenance_root=provenance_root,
        )
        rows.append(
            _row(
                "onnx_fp32",
                "ok",
                artifact=onnx_path,
                metrics=onnx_metrics,
                degradation=degradation,
                latency=onnx_latency,
                parity=parity,
            )
        )
    else:
        rows.append(_row("onnx_fp32", "not requested", artifact=onnx_path, parity=parity))

    workspace_bytes = int(args.workspace_gib * 2**30)
    failures = False
    if "fp16" in args.backends:
        fp16_onnx = out_dir / f"{cfg.model.arch}_{shape[0]}x{shape[1]}_fp16.onnx"
        fp16_engine = out_dir / f"{cfg.model.arch}_{shape[0]}x{shape[1]}_fp16.engine"
        try:
            convert_fp16_onnx(onnx_path, fp16_onnx)
            build_seconds = build_trt_engine(
                fp16_onnx,
                fp16_engine,
                precision="fp16",
                workspace_bytes=workspace_bytes,
            )
            fp16_runner = TrtRunner(fp16_engine, device)
            reset_peak_vram()
            started = time.perf_counter()
            fp16_metrics = evaluate_runner(
                fp16_runner,
                evaluation,
                device=device,
                space=space,
                active=active,
                boundary_tolerance_frac=cfg.eval.boundary_tolerance_frac,
                save_confusion=cfg.eval.save_confusion,
            )
            fp16_latency = cuda_event_latency(
                fp16_runner, example, warmup=args.warmup, iterations=args.iterations
            )
            elapsed = time.perf_counter() - started
            degradation = baseline_miou - float(fp16_metrics["miou"])
            precision_counts = fp16_runner.precision_counts()
            if precision_counts.get("fp16", 0) == 0:
                raise ExportError(
                    "explicit FP16 graph built an engine with no inspected FP16 layers: "
                    f"{precision_counts}"
                )
            deployment = {
                "backend": "tensorrt",
                "precision": "fp16",
                "latency": to_dict(fp16_latency),
                "miou_degradation": degradation,
                "fixed_shape": list(fixed_shape),
                "build_seconds": build_seconds,
                "engine_layer_precision_counts": precision_counts,
                "untrained_test_only": args.untrained_test_only,
            }
            write_variant_result(
                out_dir / "records" / "tensorrt_fp16" / "results.json",
                cfg=cfg,
                export_config=export_cfg,
                variant="tensorrt_fp16",
                metrics=fp16_metrics,
                deployment=deployment,
                elapsed_s=elapsed,
                eval_samples=args.eval_samples,
                calibration_samples=args.calibration_samples,
                checkpoint=args.ckpt,
                use_ema=args.ema,
                provenance_root=provenance_root,
            )
            rows.append(
                _row(
                    "tensorrt_fp16",
                    "ok",
                    artifact=fp16_engine,
                    metrics=fp16_metrics,
                    degradation=degradation,
                    latency=fp16_latency,
                    build_seconds=build_seconds,
                    engine_layer_precision_counts=precision_counts,
                )
            )
        except Exception as exc:
            failures = True
            rows.append(_row("tensorrt_fp16", f"failed: {type(exc).__name__}: {exc}"))
    else:
        rows.append(_row("tensorrt_fp16", "not requested"))

    if "int8" in args.backends:
        int8_onnx = out_dir / f"{cfg.model.arch}_{shape[0]}x{shape[1]}_int8_qdq.onnx"
        int8_engine = out_dir / f"{cfg.model.arch}_{shape[0]}x{shape[1]}_int8.engine"
        try:
            calibration_images = [image.unsqueeze(0) for image, _ in calibration]
            q_nodes = quantize_int8_onnx(
                onnx_path,
                int8_onnx,
                calibration_images,
                device=device,
                nodes_to_exclude=args.int8_exclude_node,
            )
            build_seconds = build_trt_engine(
                int8_onnx,
                int8_engine,
                precision="int8",
                workspace_bytes=workspace_bytes,
            )
            int8_runner = TrtRunner(int8_engine, device)
            reset_peak_vram()
            started = time.perf_counter()
            int8_metrics = evaluate_runner(
                int8_runner,
                evaluation,
                device=device,
                space=space,
                active=active,
                boundary_tolerance_frac=cfg.eval.boundary_tolerance_frac,
                save_confusion=cfg.eval.save_confusion,
            )
            int8_latency = cuda_event_latency(
                int8_runner, example, warmup=args.warmup, iterations=args.iterations
            )
            elapsed = time.perf_counter() - started
            degradation = baseline_miou - float(int8_metrics["miou"])
            precision_counts = int8_runner.precision_counts()
            if precision_counts.get("int8", 0) == 0:
                raise ExportError(
                    f"Q/DQ graph had {q_nodes} quantizers but engine inspector found no INT8 layers: "
                    f"{precision_counts}"
                )
            deployment = {
                "backend": "tensorrt",
                "precision": "int8_qdq",
                "latency": to_dict(int8_latency),
                "miou_degradation": degradation,
                "fixed_shape": list(fixed_shape),
                "build_seconds": build_seconds,
                "calibration_samples": args.calibration_samples,
                "qdq_quantize_nodes": q_nodes,
                "engine_layer_precision_counts": precision_counts,
                "untrained_test_only": args.untrained_test_only,
                "excluded_nodes": list(args.int8_exclude_node),
            }
            write_variant_result(
                out_dir / "records" / "tensorrt_int8" / "results.json",
                cfg=cfg,
                export_config=export_cfg,
                variant="tensorrt_int8",
                metrics=int8_metrics,
                deployment=deployment,
                elapsed_s=elapsed,
                eval_samples=args.eval_samples,
                calibration_samples=args.calibration_samples,
                checkpoint=args.ckpt,
                use_ema=args.ema,
                provenance_root=provenance_root,
            )
            rows.append(
                _row(
                    "tensorrt_int8",
                    "ok",
                    artifact=int8_engine,
                    metrics=int8_metrics,
                    degradation=degradation,
                    latency=int8_latency,
                    calibration_samples=args.calibration_samples,
                    qdq_quantize_nodes=q_nodes,
                    build_seconds=build_seconds,
                    engine_layer_precision_counts=precision_counts,
                )
            )
        except Exception as exc:
            failures = True
            rows.append(_row("tensorrt_int8", f"failed: {type(exc).__name__}: {exc}"))
    else:
        rows.append(_row("tensorrt_int8", "not requested"))

    metadata["onnx_sha256"] = hashlib.sha256(onnx_path.read_bytes()).hexdigest()
    write_summary(out_dir, metadata, rows)
    print((out_dir / "export_table.md").read_text(encoding="utf-8"))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
