# Real-image object GPU execution checks

This recipe checks GPU forward/backward execution of all four supported object
families using **real Cityscapes images and native annotations**. Models use small,
randomly initialized configurations so this is affordable integration validation,
not a pretrained-model accuracy benchmark. The exact architecture configurations
are embedded in each checkpoint and in `results.json`.

Prepare the Cityscapes object subset using the benchmark conversion recipe, then
run from the repository root in an environment installed with `.[objects]`:

```bash
python scripts/validate_object_gpu.py \
  --task instance \
  --train-images /data/izadia1/datasets/cityscapes/leftImg8bit/train \
  --train-annotations /data/izadia1/datasets/cityscapes-object-validation-v1/train/instance.json \
  --val-images /data/izadia1/datasets/cityscapes/leftImg8bit/val \
  --val-annotations /data/izadia1/datasets/cityscapes-object-validation-v1/val/instance.json \
  --device cuda:0 --memory-fraction 0.15 --steps 2 --limit 2 \
  --height 256 --width 512 --accumulation 2 --precision float32 \
  --output artifacts/cityscapes-object-gpu-instance
```

For panoptic execution, use `--task panoptic`, change both annotation filenames to
`panoptic.json`, and add:

```bash
--train-panoptic-masks /data/izadia1/datasets/cityscapes-object-validation-v1/train/panoptic \
--val-panoptic-masks /data/izadia1/datasets/cityscapes-object-validation-v1/val/panoptic
```

Choose a new output directory for every invocation. Paths are examples and can be
replaced with a local licensed Cityscapes installation. By default the harness
runs EoMT, EoMT DINOv3, MaskFormer and Mask2Former; `--models FAMILY [FAMILY ...]`
selects a subset. Use `--precision float16` or `bfloat16` for separate AMP checks.
EoMT's fixed native grid is a square of the smaller input dimension; the recorded
wrapper explicitly resizes to that grid. Swin families use the supplied rectangle.

Only RGB images are resized. Native target masks retain even one-pixel objects;
no objects are silently filtered. The query count is at least 16 and exceeds the
largest training target count by eight. The training loss operates on original
masks, so GPU memory still depends on image size and object count. The memory
fraction limits PyTorch's allocator, does not reserve currently free memory, and
can intentionally produce an OOM if insufficient memory is available. Select an
available device; this script never changes other processes or campaign settings.

The output records native image IDs, image/mask/annotation SHA-256 hashes, class
mapping, architecture, seed, precision, accumulation, successful optimizer steps,
finite loss and gradient norms, elapsed training time, peak allocated/reserved
VRAM, held-out forward finiteness, and checkpoint digests. The tiny checkpoints
include optimizer, scaler and random state as execution evidence. Their smoke
schema intentionally differs from production training checkpoints; continue real
training with `segmentary-objects train --resume .../last.pt` instead.

A successful smoke does **not** establish dataset accuracy, transfer performance,
or reference-evaluator agreement. Use the separate benchmark evaluation recipes
for mask AP/PQ. The held-out forward check makes no threshold or model-selection
decisions from ground truth.

GPU continuation regression tests exercise the production trainer with FP16 and
BF16, comparing an uninterrupted run against an interrupted/resumed run:

```bash
CUDA_VISIBLE_DEVICES=0 python -m pytest -q tests/test_object_continuation.py -m gpu
```

The default CPU continuation tests also check atomic write failure, epoch-tail
accumulation, changed-data rejection, and signal handler restoration. The harness
architecture tests run without downloads via `tests/test_object_gpu_harness.py`.
