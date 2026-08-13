# SegFormer-B2 trained export benchmark

This is a fixed-shape deployment benchmark for the trained
`segformer_b2` Cityscapes calibration checkpoint. It compares four runtimes on
the same 20-image deterministic Cityscapes validation prefix.

## Protocol

- model/checkpoint: `segformer_b2`, `calib_cs19_b2_seed0/cityscapes/best.ckpt`;
- checkpoint state: raw weights (`ema: false`);
- input/output shape: batch 1, 1024×1024;
- calibration: first 8 deterministic Cityscapes training samples;
- metric evaluation: first 20 deterministic Cityscapes validation samples;
- latency: 20 warmups and 100 CUDA-event-timed iterations;
- hardware: NVIDIA L40S, CUDA 12.8;
- software: PyTorch 2.11.0+cu128, ONNX Runtime CUDA, TensorRT 11.2.1.2.

## Results

| backend | p50 ms | p95 ms |
|---|---:|---:|
| PyTorch FP32 | 29.817 | 30.078 |
| ONNX Runtime FP32 | 44.472 | 45.084 |
| TensorRT FP16 | 10.008 | 10.075 |
| TensorRT INT8 | 14.938 | 15.025 |

This page intentionally omits the prior accuracy measurements. The retained
latency values describe only this deployment acceptance protocol.

## Evidence boundary

This is real trained-model deployment evidence, but it is not a full-validation
model-quality result: resizing, a 20-image prefix, and raw weights define a
different endpoint from native-resolution EMA evaluation. The source run was
recorded from Git commit `fac6cea6bd9d406ad8518886cd91c1136438d534`
with `git_dirty=true`; rerun after the final release commit before using the
numbers in a publication. Artifact hashes and the exact compact protocol live
in [`summary.json`](summary.json).

Return to the [export guide](../../guides/export-and-deployment.md).
