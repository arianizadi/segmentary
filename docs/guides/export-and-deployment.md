# Export and deployment

Segmentary can export the verified dense architectures `segformer_b2` and
`deeplabv3plus_r101` at a fixed shape, compare ONNX Runtime with PyTorch, build
TensorRT FP16/INT8 engines, and record latency plus accuracy degradation.

Mask-classification EoMT/Mask2Former arms are reported as unsupported rather than
silently skipped.

Native one-logit binary models are also unsupported by the current exporter.
Training/evaluation support does not establish an ONNX sigmoid/threshold parity
contract; do not export a binary checkpoint through the multiclass argmax path.

This is deliberately a narrower surface than generic training/evaluation. The
current deployment acceptance command benchmarks resized Cityscapes samples via
`--cityscapes-root`; it is a validated reference profile, not a claim that every
custom loader or `hf_auto` model is export-ready. For another deployment dataset,
extend the export data adapter and add real parity/accuracy tests before making a
reported claim.

## Install the pinned export stack

Use the project extra only in a compatible NVIDIA/CUDA environment:

```bash
python -m pip install -e '.[export]'
python -m pip check
```

Important pins:

- Do not let the extra replace the platform PyTorch installation.
- ONNX Runtime GPU 1.26 is the CUDA 12 line used by the validated profile.
- Use `tensorrt-cu12`, never the bare package that can resolve to CUDA 13.

## Export a checkpoint

```bash
segmentary-export \
  configs/base.yaml \
  configs/models/segformer_b2.yaml \
  configs/curricula/cs_rs.yaml \
  --ckpt runs/cs_rs_seed0/railsem19/last.ckpt \
  --ema \
  --shape 1024 1024 \
  --cityscapes-root data/cityscapes \
  --out exports/cs_rs_seed0
```

The default backends are ONNX, TensorRT FP16, and calibrated TensorRT INT8.
Select a subset while debugging:

```bash
segmentary-export \
  configs/base.yaml \
  configs/models/segformer_b2.yaml \
  configs/curricula/cs_rs.yaml \
  --ckpt runs/cs_rs_seed0/railsem19/last.ckpt \
  --ema \
  --shape 1024 1024 \
  --cityscapes-root data/cityscapes \
  --out exports/cs_rs_seed0-onnx \
  --backends onnx

segmentary-export \
  configs/base.yaml \
  configs/models/segformer_b2.yaml \
  configs/curricula/cs_rs.yaml \
  --ckpt runs/cs_rs_seed0/railsem19/last.ckpt \
  --ema \
  --shape 1024 1024 \
  --cityscapes-root data/cityscapes \
  --out exports/cs_rs_seed0-fp16 \
  --backends onnx fp16
```

## Settings and tradeoffs

| option | meaning | tradeoff |
|---|---|---|
| `--shape H W` | fixed engine input | must match deployment resizing/tiling; fixed shapes optimize better |
| `--ema` | export shadow weights | usually matches reported evaluation; requires saved EMA state |
| `--calibration-samples` | images for INT8 ranges | more representative data can improve INT8, but calibration takes time |
| `--eval-samples` | accuracy comparison subset | larger is more trustworthy and slower |
| `--warmup` | untimed executions | removes startup effects; too few gives noisy latency |
| `--iterations` | timed executions | more stabilizes percentiles |
| `--workspace-gib` | TensorRT builder workspace | more may unlock faster tactics; consumes build memory |
| `--opset` | ONNX operator set | change only for a known runtime compatibility need |
| `--onnx-rtol/atol` | numerical parity tolerance | loosening can hide a broken export; pair with argmax agreement |
| `--untrained-test-only` | label every artifact and result as a functional test from untrained task weights | mandatory when the decoder/head is not trained; absolute mIoU is then not model-quality evidence |
| `--int8-exclude-node NAME` | leave one named ONNX node in floating point; repeatable | advanced escape hatch for a proved TensorRT tactic gap; produces mixed precision and must be reported |

## Read the output

The export directory includes artifacts plus `export_summary.json` and a Markdown
table. For every backend, look at:

- status and artifact path;
- mIoU on the identical resized samples;
- degradation relative to PyTorch FP32;
- p50 and p95 batch-1 latency, CUDA-event timed after warmup;
- ONNX numerical/argmax parity;
- INT8 calibration count and engine precision composition.

In the retained [trained SegFormer-B2 deployment
acceptance](../benchmarks/segformer-b2-export/README.md), TensorRT FP16 was both
fastest and effectively accuracy-neutral on the fixed 20-image resized slice.
Its INT8 engine was slower than FP16 and lost 0.169075 on the 0-to-1 mIoU scale,
or 16.9075 percentage points. This is useful deployment evidence, but the small
legacy slice and dirty source provenance make it unsuitable as a publication
benchmark until rerun cleanly.

The separate [DeepLabV3+-R101 deployment
acceptance](../benchmarks/deeplabv3plus-r101-untrained-export/README.md) proves
ONNX, TensorRT FP16, and mixed-INT8 construction and execution. Its task decoder
and classifier were untrained, so its absolute mIoU is deliberately excluded
from model-quality claims. Lower precision is not automatically faster or
acceptable; measure both against the same PyTorch baseline.

## ONNX Runtime versus TensorRT

**ONNX Runtime**

- Pros: portable ONNX artifact, simpler integration, useful correctness oracle.
- Cons: was slower than PyTorch in the measured configuration; provider/version
  compatibility must be checked explicitly.

**TensorRT FP16**

- Pros: best measured latency, negligible accuracy change on verified samples.
- Cons: NVIDIA-specific engine, fixed hardware/software compatibility, build time.

**TensorRT INT8**

- Pros: can reduce arithmetic/memory cost when calibration and kernels are good.
- Cons: accuracy depends strongly on representative calibration; faster is not
  guaranteed; requires an explicit degradation threshold.

## Deployment checklist

1. Export the exact reported EMA or raw checkpoint policy.
2. Choose a shape and preprocessing identical to production.
3. Confirm the requested ONNX Runtime provider is actually active.
4. Assert numerical parity and pixel argmax agreement.
5. Evaluate enough real target images, including rare/task-critical classes.
6. Time with warmup, CUDA events, batch 1, and both p50/p95.
7. Record GPU, driver, CUDA, library versions, and engine hash.
8. Reject a precision mode if either latency or accuracy is worse for your goal.
9. Rebuild engines after GPU/TensorRT changes; do not treat them as universal.
10. Keep unsupported architectures as explicit table rows, not omissions.
