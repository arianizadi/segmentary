# Export and deployment choices

Segmentary's deployment path benchmarks one fixed batch-1 shape across PyTorch,
ONNX Runtime, TensorRT FP16, and calibrated TensorRT INT8. It is deliberately
narrower than model training.

## Beginner choice

First export ONNX and prove parity. Then try TensorRT FP16. Treat INT8 as a
measured experiment, not an automatic optimization.

```bash
segmentary-export base.yaml model.yaml experiment.yaml \
  --ckpt runs/experiment_seed0/target/last.ckpt \
  --ema \
  --shape 1024 1024 \
  --cityscapes-root data/cityscapes \
  --backends onnx fp16 \
  --out exports/experiment_seed0
```

## Supported architectures

| `model.arch` | status |
|---|---|
| `segformer_b2` | verified fixed-shape ONNX/ORT/TensorRT path |
| `deeplabv3plus_r101` | supported fixed-shape path; any untrained acceptance proves deployment plumbing only, not model quality |
| native binary models | unsupported; the exporter has no accepted one-channel sigmoid/threshold parity contract |
| EoMT/Mask2Former arms | explicitly unsupported because post-processing is dynamic/control-flow-heavy |
| every other architecture, including generic `hf_auto`/`smp` | not accepted by this exporter until architecture-specific real parity tests exist |

## Exact switches

| option | meaning and tradeoff |
|---|---|
| `--ckpt` | required checkpoint to export; must exactly match the configured architecture/taxonomy |
| `--cityscapes-root` | Cityscapes source for real parity, INT8 calibration, and backend accuracy samples |
| `--shape H W` | fixed NCHW engine shape; optimize for deployment but rebuild for another shape |
| `--ema` | export the saved EMA shadow; omit for raw weights |
| `--backends onnx fp16 int8` | choose any subset; default requests all three |
| `--calibration-samples` | deterministic real Cityscapes-train prefix for INT8; more representative data costs calibration time |
| `--eval-samples` | deterministic resized Cityscapes-val prefix for backend accuracy comparison |
| `--warmup` / `--iterations` | discarded and timed batch-1 executions; more reduces timing noise |
| `--workspace-gib` | TensorRT builder workspace; larger may expose faster tactics and consumes build memory |
| `--opset` | ONNX opset, default 18; change only for a known compatibility need |
| `--onnx-rtol` / `--onnx-atol` | numerical parity thresholds; loosening can hide a bad graph |
| `--device` | must resolve to CUDA for the full acceptance benchmark |
| `--out` | explicit artifact/report directory; default is beside the checkpoint |
| `--untrained-test-only` | labels every report as functional plumbing evidence; absolute mIoU is not model quality |
| `--int8-exclude-node NAME` | repeatable advanced escape hatch for a named node with no TensorRT INT8 tactic; exclusions are recorded and engine precision still audited |

## What is checked

- ONNX structural validity and exact fixed input shape;
- ONNX Runtime CUDA provider is actually active;
- PyTorch/ORT numerical parity and at least 99.9% argmax agreement on a real
  image;
- FP16 graph actually contains FP16 initializers;
- INT8 calibration produces Q/DQ nodes and the engine inspector reports INT8
  layers;
- identical resized samples produce mIoU/boundary metrics for every backend;
- p50/p95 batch-1 latency uses CUDA events after warmup;
- artifacts, engine precision counts, environment, hashes, and degradation from
  PyTorch are recorded.

## Pros and cons

- ONNX is portable and a strong correctness oracle, but its CUDA runtime may not
  be fastest.
- TensorRT FP16 is NVIDIA-specific and requires rebuilds across incompatible
  hardware/software, but was the best measured path in the tracked acceptance.
- INT8 can reduce arithmetic and memory, but poor calibration/kernel selection
  can make it both slower and less accurate.
- Fixed shape improves reproducibility and tactic selection, but production must
  reproduce the same resize/tiling and preprocessing.

## Evidence and benchmark boundary

The retained export acceptance compares deployment backends on a fixed resized
subset. It is implementation evidence, not a native-resolution model-quality
score. See the [benchmark evidence page](../../../benchmarks/README.md).

No trained DeepLabV3+-R101 quality benchmark is committed. An untrained
deployment smoke, if present, must remain labeled untrained/test-only.

## Related documentation

- [Semantic task modes](../tasks/README.md)
- [Export and deployment guide](../../../guides/export-and-deployment.md)
- [Evaluation](../evaluation/README.md)
- [Training runtime](../training-runtime/README.md)
