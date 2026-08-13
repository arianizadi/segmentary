# DeepLabV3+-R101 untrained deployment acceptance

> **UNTRAINED TEST ONLY.** The ResNet-101 encoder is ImageNet-pretrained, but
> the decoder and segmentation classifier are random. Absolute mIoU below is
> not evidence of model quality.

This acceptance isolates whether the second supported dense architecture can be
exported, calibrated, built, and executed by all deployment backends.

## Protocol

- input/output: `1×3×256×512` to `1×19×256×512`;
- calibration: 8 deterministic Cityscapes training samples;
- evaluation: 20 deterministic Cityscapes validation samples;
- latency: batch 1, 20 warmups, 100 CUDA-event-timed iterations;
- environment: NVIDIA L40S, CUDA 12.8, PyTorch 2.11.0+cu128,
  ONNX Runtime 1.26.0, TensorRT 11.2.1.2.

| backend | functional mIoU* | delta vs PyTorch | p50 ms | p95 ms |
|---|---:|---:|---:|---:|
| PyTorch FP32 | 0.001699627 | 0.000000000 | 5.582 | 6.247 |
| ONNX Runtime FP32 | 0.001698807 | +0.000000820 | 6.669 | 6.809 |
| TensorRT FP16 | 0.001701592 | -0.000001966 | 0.982 | 1.009 |
| TensorRT mixed INT8 | 0.001626781 | +0.000072846 | 0.773 | 0.792 |

\*The metric only checks backend consistency for this exact untrained model.

Every backend returned finite `1×19×256×512` logits on a real validation image.
Argmax agreement with PyTorch was 0.999557 for ONNX, 0.997536 for FP16, and
0.954170 for INT8. The FP16 engine had 146 inspected FP16 layers. The mixed INT8
engine had 164 INT8 layers and 16 FP32 layers.

TensorRT had no INT8 tactic for the quantized ResNet stem fused with ReLU and
max-pool. The accepted engine therefore leaves exactly
`/model/encoder/conv1/Conv` in floating point. This fallback is explicit in the
CLI/config and machine evidence; it is not silently called a fully INT8 engine.

See [`summary.json`](summary.json) for the compact machine record and artifact
hashes. A trained DeepLab benchmark is still required before making an accuracy
claim.
