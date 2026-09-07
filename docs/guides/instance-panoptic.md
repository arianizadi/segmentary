# Instance and panoptic segmentation

Segmentary now has an opt-in object-segmentation workflow alongside its semantic
pipeline. Use `segmentary-objects` for instance and panoptic tasks. Existing
`segmentary-train`, curricula, semantic masks, mIoU reports and running campaigns
keep their existing contracts.

| Task | Training target | Prediction | Quality metric |
| --- | --- | --- | --- |
| Semantic | One class ID per pixel | Dense class map | mIoU |
| Instance | One mask per object; repeated class IDs stay separate | Overlapping masks, categories and scores | Mask AP, AP50, AP75, AR100 |
| Panoptic | Non-overlapping segment IDs plus thing/stuff categories | RGB segment-ID PNG plus `segments_info` | PQ, SQ, RQ; things and stuff separately |

## Install and choose a model

Use Python 3.11 and your existing compatible Torch/torchvision installation:

```bash
python -m pip install -e '.[objects]'
segmentary-objects --help
```

The objects extra installs pinned `pycocotools` for exact COCO polygon decoding
and instance RLE export. Panoptic IDs and RLE inputs are validated locally.

The engine supports **EoMT Large**, **EoMT DINOv3 Large**, **MaskFormer Swin-T**,
and **Mask2Former Swin-T**. Both new Swin families support instance and panoptic
tasks with full, frozen-backbone, or LoRA tuning. Semantic-only architectures are
rejected. It uses explicit architecture constructors and Segmentary's tuning settings;
full tuning is the default. A model pretrained on panoptic data is still adapted
to the categories declared by your dataset. First loading a Hub checkpoint needs
network access; a local pretrained model directory is also supported.

A one-category instance dataset is supported: no-object is an additional query
classification target, not an annotation category. The number of annotated
non-crowd segments in an image must not exceed the model's query count.

## Data contracts

For instance segmentation, supply COCO JSON with `images`, `annotations` and
`categories`, plus the original images. Each annotation has its own object ID,
`image_id`, `category_id`, `segmentation` and optional `iscrowd`. Polygon lists,
compressed RLE and uncompressed RLE are supported. Two objects with the same
category stay as two targets; overlapping objects remain distinct. Background
images with an empty annotation list are valid negative examples.

For panoptic segmentation, supply COCO panoptic JSON and its RGB PNG directory.
Each image has one annotation with `file_name` and `segments_info`. Every category
must explicitly set `isthing` to 0 or 1. A PNG pixel encodes
`segment_id = R + 256*G + 65536*B`; zero is void. Every nonzero segment ID must
match metadata. Different thing instances remain separate; non-crowd stuff of
the same category is merged for query supervision. Crowd regions are retained
for evaluation and excluded from training supervision.

Category IDs can be noncontiguous; the loader maps sorted category IDs to
contiguous internal classes and converts back to original IDs at export. Train
and validation category definitions must agree. Unknown IDs, path traversal,
mismatched image/mask dimensions and invalid segment metadata fail validation.
Semantic class PNGs cannot recover instance identities: export the original
instance or panoptic annotations instead of relabeling semantic masks.

Split your data by recording/sequence before configuring train and validation.
Identical train/validation image files are rejected. Only for a deliberate
memorization check, set `allow_train_val_overlap: true`; that result is not
validation accuracy.
Validation is used for checkpoint selection; use a separate held-out dataset
for final evaluation. Do not use your test split for model selection.

## Validate and train

Copy [instance.yaml](../../configs/examples/instance.yaml) or
[panoptic.yaml](../../configs/examples/panoptic.yaml), then set the dataset paths,
output directory and device. Data/output paths resolve relative to the YAML.
Model Hub IDs retain their normal meaning; use an absolute path for a local model.

```bash
segmentary-objects validate configs/examples/instance.yaml
segmentary-objects train configs/examples/instance.yaml

# Or, with panoptic data:
segmentary-objects validate configs/examples/panoptic.yaml
segmentary-objects train configs/examples/panoptic.yaml
```

These examples default to CPU deliberately. Set `device: cuda:0` explicitly for
a GPU. Starting one of these commands starts a new independent run; adding the
feature does not start or change an existing training campaign.

The object workflow uses single-device AdamW (float32 by default), a constant learning
rate, gradient clipping at 1.0, fixed-size image resizing and no augmentation.
Masks use nearest-neighbor resizing; a resize that erases a segment is rejected.
Query matching uses class/BCE/Dice costs with configurable sampled matching
points and per-object positive anchors; matched mask losses use full resolution.
Auxiliary query outputs are supervised. Void/crowd pixels are excluded from loss.
Input normalization is RGB ImageNet mean/std. EoMT may internally resize to the
native grid stored by its pretrained checkpoint; that size is recorded.

Validation resizes model inputs but evaluates reconstructed predictions against
**native-resolution** targets. The best checkpoint maximizes mask AP for instance
or PQ for panoptic. The output directory must be new; no existing run is silently
overwritten. Only `best.pt` and `last.pt` are kept. Config, annotation hashes,
category mapping, architecture config, Git provenance, step/loss/validation history, wall time and
CUDA peak allocated memory (when applicable) are written alongside checkpoints.

This object workflow does not yet implement distributed training,
EMA, curricula, sliding-window/TTA merging, or ONNX/TensorRT object export. These remain separate
from the mature semantic engine; no support is inferred from a model's name.

## Interruption, resume and mixed precision

```bash
segmentary-objects train configs/examples/instance.yaml \
  --resume runs/my-instance-run/last.pt
```

Use the same configuration and output directory. `max_steps` counts successful
optimizer updates and may be increased; other training settings must match.
Resume verifies image, annotation and panoptic mask content hashes, model/category
configuration and PyTorch version. It restores model and AdamW state, FP16
GradScaler, Python/NumPy/PyTorch/CUDA random states, exact shuffled sample order,
epoch/cursor, best metric, history and elapsed training time. Older weights-only
checkpoints remain usable for prediction but cannot resume training. Continuation
uses the original run's `last.pt`; `best.pt` is for evaluation.

SIGINT/Ctrl-C and SIGTERM finish the current optimizer update and save before
returning `status: interrupted`. Atomic `last.pt` is replaced after every update;
a hard kill or unexpected failure can replay the unfinished update on resume.
Snapshots are only made at accumulation boundaries, so partial gradients are
never mistaken for a finished optimizer update. A signal cannot finish until
an in-progress device operation returns. This single-process runner uses zero
loader workers. Reproducibility assumes the same hardware/runtime and deterministic
kernels. CPU float32/bfloat16 and CUDA float16/bfloat16 continuation are tested
for exact equality; cross-hardware bitwise identity is not promised. See the
[recorded CUDA checks](../results/object-validation/README.md).

Optional YAML settings:

```yaml
precision: bfloat16       # float32 (default), bfloat16, or CUDA-only float16
batch_size: 2
gradient_accumulation: 4  # default 1; up to 8 images per optimizer update here
```

Epoch-tail groups use their actual sample count when weighting microbatch losses;
an update never crosses an epoch. Gradients are unscaled before clipping. FP16
overflow skips the optimizer update, updates/persists the scaler, and consumes the
sample group without incrementing `step`. Validation stays float32 at native target
resolution. AMP behavior follows the [PyTorch AMP recipe](https://docs.pytorch.org/tutorials/recipes/recipes/amp_recipe.html);
full continuation follows [PyTorch checkpoint guidance](https://docs.pytorch.org/tutorials/beginner/saving_loading_models.html).

## Evaluate and export predictions

```bash
segmentary-objects eval configs/examples/instance.yaml \
  --checkpoint runs/my-instance-run/best.pt --out artifacts/instance-eval.json

segmentary-objects predict configs/examples/instance.yaml \
  --checkpoint runs/my-instance-run/best.pt \
  --images /path/to/new/images --out artifacts/instance-predictions
```

The same commands work with the panoptic config/checkpoint. `eval` uses the
configured validation dataset; point a copied configuration's `val` section at
the held-out dataset for final testing. Task, categories and model configuration
must match the saved checkpoint. Validation may contain a subset of categories;
the saved full category mapping is preserved. Trained checkpoint reload uses its
saved architecture and weights and does not download the original initializer.
Output paths must be new.

Instance `predictions.json` contains image metadata and scored COCO-style RLE
annotations with original category IDs. `instances.json` also provides the plain
COCO results list accepted by `COCO.loadRes`. Panoptic output contains RGB ID PNGs
and a `predictions.json` with categories, image metadata and `segments_info`.
The export includes the checkpoint SHA-256, inference settings and image dimensions/hashes. These exports contain object masks;
they are not semantic class-index PNGs.

Postprocessing filters no-object/low-confidence queries and retains independent
thing masks for instance output. Panoptic output assigns each pixel to a retained
query using score-weighted mask probabilities, rejects insufficiently supported
segments and merges same-category stuff. The three thresholds are explicit in
config. In particular, threshold changes can change both AP and PQ and must be
reported with comparisons.

## Metric definitions and validation

Definitions follow the official [COCO mask evaluator](https://github.com/cocodataset/cocoapi/blob/master/PythonAPI/pycocotools/cocoeval.py)
and [panoptic evaluator](https://github.com/cocodataset/panopticapi/blob/master/panopticapi/evaluation.py).

Instance AP uses IoU thresholds 0.50 through 0.95 in steps of 0.05, 101-point
interpolated precision and at most 100 predictions per image/category. It
supports crowd matching; empty-GT images still contribute false positives to a
supported class. It reports all-area mask metrics, not box AP or area-stratified
COCO scores. Panoptic PQ uses same-class matches at strict IoU > 0.5, with void
and crowd handling. `PQ = sum(matched IoU)/(TP + 0.5 FP + 0.5 FN)`, `SQ` is mean
matched IoU, and `RQ = TP/(TP + 0.5 FP + 0.5 FN)`. Machine metrics are fractions
from 0 to 1; absent evaluation support is `null`, never a fabricated zero.

Tests cover separate same-class instances, COCO encodings, crowds/void, things
versus stuff, matching gradients, numerical metric cases, and CPU training,
checkpoint reload, evaluation and export through a tiny real EoMT model:

```bash
python -m pytest tests/test_object_data.py tests/test_object_loss.py \
  tests/test_object_predictions.py tests/test_object_metrics.py \
  tests/test_object_checkpoint_model.py tests/test_object_workflow.py
```

These synthetic scientific tests verify implementation behavior. They do not
establish accuracy on a real instance/panoptic benchmark or GPU throughput.

A local 50-step memorization smoke check on two same-class objects used a tiny
randomly initialized EoMT on CPU. Instance loss fell from 8.93738 to 0.04390 with
same-image AP 1.000; panoptic loss fell from 9.54115 to 0.11781 with same-image
PQ 0.97825. These are deliberately overfit synthetic examples, not held-out
benchmark results. The active RTIS campaign was not used for these tests.

## Additional families and tools

| Architecture key | Default initialization | Backbone |
| --- | --- | --- |
| `maskformer_swin_tiny` | `facebook/maskformer-swin-tiny-coco` | Swin Tiny |
| `mask2former_swin_tiny` | `facebook/mask2former-swin-tiny-coco-panoptic` | Swin Tiny |

These are pretrained complete query models; the target classifier is resized when
the category count differs. Loading never silently falls back to random weights.
Set `model.revision` to a Hub commit for reproducible initialization; a local
checkpoint directory works too. See [Mask2Former instance example](../../configs/examples/instance-mask2former.yaml)
and [MaskFormer panoptic example](../../configs/examples/panoptic-maskformer.yaml).
Swin inputs support rectangular shapes; EoMT retains its saved fixed token grid.

Use the [Inference Checker](inference-checker.md) for object review,
[object reports](object-reports.md) for linked AP/PQ comparisons, and
[benchmark validation](object-benchmark-validation.md) for reproducible real-data checks.
