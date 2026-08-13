# Python API reference

The command-line tools are the recommended path for reproducible experiments,
but the core pieces are ordinary Python modules and can be embedded in notebooks,
tests, or another training service.

Segmentary 0.1 does not yet promise long-term semantic-version compatibility for
every internal helper. The objects below are the clearest integration points.

## Load and inspect a config

```python
from segmentary.config import config_hash, load_experiment, to_dict

cfg = load_experiment(
    [
        "base.yaml",
        "model.yaml",
        "experiment.yaml",
    ]
)

print(cfg.name, cfg.model.arch)
print([stage.name for stage in cfg.stages])
print(config_hash(cfg))
plain_dict = to_dict(cfg)
```

`load_experiment()` merges left to right and returns a validated
`ExperimentConfig`. `ConfigError` is raised for unknown keys, wrong scalar/list
types, invalid literals, or unsafe combinations.

Programmatic overrides use nested dictionaries:

```python
cfg = load_experiment(
    ["base.yaml", "model.yaml", "experiment.yaml"],
    overrides={"train": {"batch_size": 4, "seed": 2}},
)
```

## Taxonomy and mappings

```python
import numpy as np

from segmentary.taxonomy import colorize, load_mapping, load_space

space = load_space("taxonomy", "my_space")
mapping = load_mapping("taxonomy", space, "my_dataset")

native_mask = np.asarray([[0, 1, 255]], dtype=np.uint8)
canonical_mask = mapping.apply(native_mask)
active_classes = mapping.active_mask()  # bool array, shape (num_classes,)
rgb_preview = colorize(canonical_mask, space)
```

Important properties:

- `LabelSpace.num_classes`, `.names`, `.palette`, `.ignore_index`, `.thin_classes`;
- `DatasetMapping.apply()` for vectorized native→canonical ids;
- `.active_mask()` for classes the dataset can supervise;
- `.assert_covers(observed_ids)` to reject undeclared real mask values.

## Build a model and data loaders

```python
from segmentary.data.loaders import (
    build_dataset,
    build_train_loader,
    build_val_loader,
    load_data_mapping,
    resolve_dataset_loader,
)
from segmentary.models.factory import build_model

stage = cfg.stages[0]
model = build_model(cfg.model, space.num_classes)
train_loader = build_train_loader(stage, space, cfg.taxonomy_root, cfg.aug, cfg.train, model=model)
val_loader, val_dataset = build_val_loader(
    stage,
    space,
    cfg.taxonomy_root,
    cfg.aug,
    cfg.train,
    batch_size=cfg.eval.batch_size,
    model=model,
)

batch = next(iter(train_loader))
print(batch["image"].shape)  # (N, 3, H, W)
print(batch["mask"].shape)  # (N, H, W)
print(batch["active"].shape)  # (N, C)
```

Use the loader builders rather than calling dataset classes directly when you
need production transforms, mixed sampling, active masks, reproducible worker
seeding, and native-resolution validation.

Pass the model into both loader builders. This lets `hf_auto` use the audited
checkpoint processor's mean and standard deviation; omitting it uses the
generic ImageNet normalization fallback.

`resolve_dataset_loader(data)` accepts a built-in ID or the configured
`package.module:SegDatasetSubclass`. `load_data_mapping(data, space, root)` is
important when logical `data.name` and mapping stem differ. `build_dataset()`
combines those pieces with a transform.

## Run the model

```python
import torch

model = model.cuda().eval()
x = torch.randn(1, 3, 512, 768, device="cuda")
with torch.no_grad():
    logits = model(x)
assert logits.shape == (1, space.num_classes, 512, 768)
```

Every returned object is a `SegmentationModel` with:

- `forward(pixel_values)` → input-resolution dense logits;
- `head_patterns()` → parameter-name patterns for head LR/LoRA handling;
- `backbone_modules()` → the pretrained feature extractor modules;
- `reset_head()` → reinitialize only the final classifier;
- `supports_dense_ce` → false when the wrapper is mask-classification based.

`build_model()` either loads the requested pretrained path or raises. It never
silently substitutes random backbone weights.

## Loss and metrics

```python
from segmentary.engine.boundary import BoundaryConfig, BoundaryF1
from segmentary.engine.losses import LossConfig, SegmentationLoss
from segmentary.engine.metrics import ConfusionMatrix

loss_fn = SegmentationLoss(
    LossConfig(aux="lovasz", aux_weight=0.5),
    num_classes=space.num_classes,
    ignore_index=space.ignore_index,
)

# Use the batch produced by Segmentary's loader so image, target, and per-sample
# active masks agree in shape and meaning.
images = batch["image"].cuda()
targets = batch["mask"].cuda()
active = batch["active"].cuda()
model.train()
logits = model(images)
total_loss, components = loss_fn(logits, targets, active)
total_loss.backward()

# For evaluation, select the dataset-wide active mask from the mapping being
# scored. This is one (C,) mask, unlike the training batch's (N, C) masks.
import torch
from segmentary.data.loaders import load_data_mapping

eval_data = stage.data[0]
eval_mapping = load_data_mapping(eval_data, space, cfg.taxonomy_root)
dataset_active = torch.as_tensor(eval_mapping.active_mask(), device="cuda")
cm = ConfusionMatrix(
    space.num_classes,
    space.ignore_index,
    active=dataset_active,
    device="cuda",
)
bf1 = BoundaryF1(
    space.num_classes,
    space.ignore_index,
    cfg=BoundaryConfig(tolerance_frac=cfg.eval.boundary_tolerance_frac),
    active=dataset_active,
    device="cuda",
)
prediction = logits.argmax(dim=1)
cm.update(prediction, targets)
bf1.update(prediction, targets)

semantic = cm.compute()
boundary = bf1.compute()
print(total_loss.detach().item(), components["ce"], semantic.miou, boundary.macro_f1)
```

For dataset-specific evaluation, pass its active mask so impossible classes are
reported absent instead of zero. In distributed code, the metric classes reduce
their accumulated state as implemented by the training module.

## Sliding-window inference

```python
from segmentary.engine.inference import InferenceConfig, inference

infer_cfg = InferenceConfig(
    sliding_window=True,
    window=(1024, 1024),
    stride=(768, 768),
    scales=(1.0,),
    flip=False,
)

with torch.no_grad():
    logits = inference(model, x, space.num_classes, infer_cfg)
```

Multiple scales and flipping change logits into averaged-view scores and cost one
forward path per view/window. Keep them off for the baseline protocol.

## Run a curriculum programmatically

```python
from segmentary.curriculum import run_curriculum
from segmentary.utils.seed import seed_everything

seed_everything(cfg.train.seed)
stage_results = run_curriculum(cfg, devices=1)
for result in stage_results:
    print(result.name, result.checkpoint, result.results_path)
```

This performs real training and writes under
`<output_root>/<experiment>_seed<seed>/<stage>/`. Prefer the CLI for shell logs,
device parsing, dotted overrides, deterministic mode, and config printing.

## Read and write result records

```python
from segmentary.utils.results import load_results

record = load_results("runs/example_seed0/stage/results.json")
print(record.git_sha, record.seed, record.metrics["miou"])
```

Use `RunRecord` + `write_results()` for a custom evaluation backend so output
remains consumable by `segmentary-table`. The table validator expects
the embedded config, matching hash/seed, clean provenance for replicate groups,
headline metrics, boundary metrics, timing, and VRAM mappings.
It discovers only `**/results.json` below the selected runs directory, so write
each intended table record to a separate directory with that exact filename.

## Exceptions worth handling

| exception | meaning |
|---|---|
| `ConfigError` | invalid or unknown experiment setting |
| `TaxonomyError` | inconsistent label space/mapping or undeclared native ids |
| `FileNotFoundError` | dataset, split, mapping, or checkpoint is absent |
| `ValueError` | unsafe semantic combination such as unmatched freeze/LoRA target |
| `RuntimeError` | model/checkpoint mismatch or failed execution contract |

Catch these at an application boundary to add context, but preserve their exact
message. Do not turn them into fallbacks that make a different experiment run.
