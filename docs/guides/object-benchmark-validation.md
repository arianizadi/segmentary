# Real-data object benchmark validation

This workflow checks real Cityscapes images, native instance/panoptic targets,
CUDA execution, pretrained inference, and numerical agreement with independent
reference evaluators. A three-image subset is an integration check, not a
leaderboard score or evidence of generalization to RTIS.

## Prepare licensed local data

Use the original Cityscapes `leftImg8bit` and `gtFine` directories, including
`*_gtFine_instanceIds.png`. Images remain in their original location; conversion
writes COCO JSON, panoptic RGB ID PNGs, and a source-hash manifest to a new directory.

```bash
pip install -e '.[objects]'
pip install -r requirements/object-benchmark.txt
python -m segmentary.objects.benchmark_data \
  --root /data/cityscapes --out /data/cityscapes-objects-v1 --limit 3
```

Selection is the first N sorted annotation filenames within each official split.
The manifest records every selected filename and image/mask SHA-256. Omit
`--limit` for all official train and validation images. Conversion retains the
standard 19 evaluated classes, eight thing categories, group/crowd regions,
separate same-class instances, and void. It refuses an existing output.

The class IDs and instance/group convention follow the
[official Cityscapes labels](https://github.com/mcordts/cityscapesScripts/blob/master/cityscapesscripts/helpers/labels.py).
This conversion does not infer objects from semantic class masks.

## Evaluate published pretrained weights

From the repository root:

```bash
CUDA_VISIBLE_DEVICES=0 python scripts/benchmark_cityscapes_objects.py \
  --prepared /data/cityscapes-objects-v1 \
  --out artifacts/cityscapes-object-check --device cuda:0
```

The recipe resolves and records exact Hub revisions for the task-specific
[instance](https://huggingface.co/facebook/mask2former-swin-tiny-cityscapes-instance)
and [panoptic](https://huggingface.co/facebook/mask2former-swin-tiny-cityscapes-panoptic)
Mask2Former Swin-T initializers. Category names/order must match. It saves a
self-contained checkpoint, exact configuration, dataset manifest, predictions,
and a [full report](object-reports.md) for each task. No model is trained and no
threshold is selected using validation scores.

Inputs use fixed 512×1024 bilinear resize and ImageNet normalization. Predictions
are evaluated at original image resolution. The protocol has no TTA and uses
explicit score/mask/overlap thresholds. It differs from upstream full benchmark
recipes; do not compare its subset scores directly to published leaderboard scores.

`--memory-fraction` defaults to 0.15 and caps this process's CUDA allocator.
It does not reserve a GPU or guarantee spare compute. On shared servers these
short checks can contend for compute, so reports explicitly label timings as
shared-device measurements. For dedicated throughput measurements use an idle
GPU and repeat the full protocol.

## Independent numerical validation

`requirements/object-benchmark.txt` pins the official panoptic evaluator commit.
Instance comparison uses pinned `pycocotools` COCO mask AP at IoU 0.50:0.05:0.95,
101 recall points, all areas, and maxDets=100. Panoptic comparison uses the
[official panoptic API](https://github.com/cocodataset/panopticapi/blob/7bb4655548f98f3fedc07bf37e9040a992b054b0/panopticapi/evaluation.py).
Both sides receive the same exported native-resolution predictions, image set,
category mapping, crowd regions, and void convention. Absolute differences and
tolerance are retained in the report. Unsupported class metrics are null locally;
official panoptic zero placeholders for unsupported classes are excluded.

**COCO mask AP on Cityscapes annotations is not official Cityscapes instance AP.**
The latter has its own distance and area protocol. Panoptic PQ follows the COCO
panoptic definition. Report task/protocol and dataset version alongside every score.

Run evaluator parity regression tests with:

```bash
python -m pytest tests/test_object_reference.py tests/test_object_reports.py
```

## GPU forward/backward and complete continuation

The [GPU execution recipe](object-gpu-validation.md) runs all four implemented
families on real images and native targets with deliberately small, random
architectures. It exercises gradients, optimizer updates, mixed precision and
accumulation without launching a campaign. Those outputs are execution evidence,
not pretrained accuracy results. CUDA continuation tests independently compare
uninterrupted training with interrupted-and-resumed training, including model,
optimizer, GradScaler, sampler, and random state.

Published local evidence is in the
[object validation report](../results/object-validation/README.md).
