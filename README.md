# Segmentary

Segmentary is a configuration-driven Python library for training, evaluating, and
benchmarking semantic-segmentation models. It is designed for the common path—a
folder of images and integer masks—but keeps the controls needed for serious
experiments: custom label spaces, multiple datasets, staged transfer, mixed
sampling, strict checkpoint handoff, EMA, native-resolution evaluation, per-class
and boundary metrics, provenance, ONNX, and TensorRT.

The name means "composed of segments." It fits both the task and the design:
datasets, taxonomies, backbones, necks, heads, objectives, stages, and deployment
paths are explicit pieces that can be composed without turning the configuration
into arbitrary executable code. No rail data is required.

## What you can use

- Any paired image/mask dataset through the built-in `folder` loader.
- A project-specific `SegDataset` subclass through `package.module:Class`.
- Standard Hugging Face semantic-segmentation checkpoints through the audited
  `hf_auto` path, with remote repository code disabled.
- Ten typed SMP decoder families with an explicit encoder and pretrained-weight
  choice, plus revision-pinned ready recipes.
- Verified built-in SegFormer, DeepLabV3+, UPerNet, HRNet-OCR, and research model
  arms.
- One canonical label space across datasets, with explicit native-ID mappings and
  per-sample active-class masks.
- One-stage, sequential, or mixed-dataset training with full, frozen, or LoRA
  backbone tuning.
- mIoU, per-class IoU/accuracy/support, pixel accuracy, frequency-weighted IoU,
  confusion matrices, boundary precision/recall/F1, wall time, VRAM, config hash,
  Git provenance, and multi-seed tables.
- Static-shape ONNX/ONNX Runtime/TensorRT export for the explicitly supported
  dense architectures.

Segmentary fails closed when a config key is unknown, a taxonomy merge is
undeclared, pretrained weights load only partly, a checkpoint does not match, or
result records are unsafe to aggregate. Those errors protect experimental
meaning rather than hiding it.

## Five-minute start

Segmentary requires Python 3.11 and a compatible PyTorch/torchvision pair. For a
CPU-only first run, the following is directly copyable. GPU users should choose
the matching CUDA wheel in the [installation guide](https://github.com/arianizadi/segmentary/blob/main/docs/tutorials/installation.md).

```bash
git clone https://github.com/arianizadi/segmentary.git
cd segmentary
python -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e '.[dev]'

cd ..
segmentary-init my-segmentation-project --name first_run
cd my-segmentation-project
```

The generated project has three composable YAML files and a tiny example
taxonomy. Put paired files in this default layout:

```text
data/
  images/train/frame_001.jpg
  images/val/frame_101.jpg
  masks/train/frame_001.png
  masks/val/frame_101.png
```

Masks are single-channel integer class IDs; `255` is ignored. Edit
`taxonomy/example/canonical.yaml`,
`taxonomy/example/my_dataset.yaml`, and `experiment.yaml`, then validate the
fully merged configuration without opening a model or dataset:

```bash
git init
git add .
git commit -m "Configure first Segmentary experiment"

segmentary-train base.yaml model.yaml experiment.yaml --print-config
```

Keep the generated project as a sibling of, or otherwise outside, the Segmentary
source checkout. Its starter `.gitignore` excludes data, runs, checkpoints,
debug overlays, and `resolved.json`; the committed configuration and taxonomy
are therefore the clean Git provenance recorded with training results.

Before a long run, inspect real overlays and prove that the model can memorize a
few images:

```bash
segmentary-models list
segmentary-models probe base.yaml model.yaml experiment.yaml \
  --output reports/model-probe.json

segmentary-verify \
  --dataset my_dataset --loader folder --mapping my_dataset \
  --root data --space example --taxonomy taxonomy --crop 512 512

segmentary-overfit \
  base.yaml model.yaml experiment.yaml --images 8 --device cuda:0
```

Then train and evaluate:

```bash
segmentary-train base.yaml model.yaml experiment.yaml --seed 0 \
  --set train.devices=1

segmentary-eval base.yaml model.yaml experiment.yaml \
  --ckpt runs/first_run_seed0/train_my_data/last.ckpt \
  --seed 0 --ema --device cuda:0 \
  --out runs/first_run_seed0/eval_my_dataset_val/results.json
```

`segmentary-table` discovers only files matching `**/results.json` below its
`--runs` directory. Put every full evaluation intended for aggregation in its
own named directory as shown above.

Long jobs should use your cluster scheduler or a persistent session appropriate
to your environment. Segmentary does not assume Slurm, a particular host, or a
particular data mount.

For a queued campaign that writes `lane_*_status.json`, open the read-only live
dashboard in another terminal. Every lane is one row, so a whole multi-GPU
campaign fits in one window: live optimizer iterations, training and validation
metrics, throughput, ETA, queue state, and GPU health. Ctrl-C closes only the
display and does not stop training:

```bash
segmentary-progress runs/my_campaign --timezone America/Los_Angeles
```

Use `--once` when you want one clean, printable snapshot rather than a live
screen. See the [CLI reference](https://github.com/arianizadi/segmentary/blob/main/docs/reference/cli.md#watch-live-training) for
the update cadence and ETA limitations.

## The configuration model

YAML files merge left to right. A typical command layers:

1. shared optimization, augmentation, and evaluation defaults;
2. one model choice;
3. one experiment with a label space and ordered stages;
4. optional site- or run-specific overrides.

Lists replace rather than append. Unknown keys and wrong types are fatal. The
resolved config is embedded in every result and contributes to `config_hash`.

```yaml
name: animals_transfer
space: animals
taxonomy_root: taxonomy
output_root: runs

stages:
  - name: source
    data:
      - name: source_photos
        root: data/source
        loader: folder
        mapping: source_photos
    init_from: pretrained
    iters: 20000

  - name: target
    data:
      - name: target_photos
        root: data/target
        loader: folder
        mapping: target_photos
    init_from: previous
    iters: 5000
    lr_scale: 0.1
```

The same schema supports one stage, many stages, or a mixed stage. A mixed stage
lists multiple datasets and declares `sample_weights` by logical dataset name.

## Models

The portable Hugging Face path consumes a complete standard
`AutoModelForSemanticSegmentation` checkpoint:

```yaml
model:
  arch: hf_auto
  checkpoint: nvidia/segformer-b0-finetuned-ade-512-512
  revision: null       # pin a Hub commit for a reported experiment
  local_files_only: false
  trust_remote_code: false
  tuning: full
  head: unified_head
```

Segmentary audits loading diagnostics. A label-count change may replace exactly the
final classifier; missing or unexpected pretrained backbone/head weights are an
error. Auto-discovery works for standard layouts such as SegFormer. Advanced
users can provide a complete `backbone_path`, `head_paths`, and `classifier_path`
triplet when the upstream module layout is safe but not automatically provable.

Built-in arms remain useful when you need a verified recipe or an encoder-only
pretraining checkpoint. Every wrapper accepts `(N, 3, H, W)` and returns dense
`(N, C, H, W)` logits. See
[Models and tuning](https://github.com/arianizadi/segmentary/blob/main/docs/guides/models-and-tuning.md) for the advantages,
limitations, memory tradeoffs, and currently blocked architectures. The
[model catalog](https://github.com/arianizadi/segmentary/blob/main/configs/models/README.md) links a dedicated README for every
shipped recipe and every factory-only or blocked choice.
Use [`segmentary-models list` and `probe`](https://github.com/arianizadi/segmentary/blob/main/docs/guides/model-catalog-and-probe.md)
to inspect the typed catalog and run an exact synthetic
forward/backward/optimizer compatibility check before opening a dataset. A
passing probe is not a quality or speed benchmark.

## Labels and multiple datasets

A canonical space defines the meaning of every output channel. Each dataset has
a native-ID-to-canonical-ID YAML mapping. This lets datasets with different
annotation systems share one model while keeping differences explicit.

The mapping layer enforces:

- class IDs are contiguous and `ignore_index` is 255;
- unknown native IDs map only to ignore;
- many native IDs cannot collapse into one canonical class unless the mapping
  declares the merge and explains why;
- every real mask ID can be audited with `segmentary-verify`;
- every sample carries an active-class mask, so a dataset does not teach the
  model that classes it cannot annotate are negatives.

For video or burst data, use a `splits.json` manifest with group IDs and set
`require_groups: true`. The folder loader rejects a group shared across splits.

## Results and debugging

Accuracy-like metrics are stored on the `0.0–1.0` scale and may be rendered as
percentages. Loss is not bounded to this range. A per-class result of `null`
means unscored/absent; `0.0` means the class was scored and had no correct
overlap.

Start with [Interpreting results and debugging
metrics](https://github.com/arianizadi/segmentary/blob/main/docs/tutorials/interpreting-results.md). It explains every metric,
support, confusion matrices, boundary scores, EMA/raw checkpoints, best/final
artifacts, seed variation, diagnostic bands, and a cheapest-first debugging
flow. The table builder refuses duplicate seeds, mixed configs, dirty multi-seed
runs, incompatible Git provenance, and partial metric groups.

## Documentation paths

- [Documentation home](https://github.com/arianizadi/segmentary/blob/main/docs/README.md)
- [Installation](https://github.com/arianizadi/segmentary/blob/main/docs/tutorials/installation.md)
- [Getting started](https://github.com/arianizadi/segmentary/blob/main/docs/tutorials/getting-started.md)
- [Core concepts](https://github.com/arianizadi/segmentary/blob/main/docs/tutorials/core-concepts.md)
- [Interpreting results and debugging](https://github.com/arianizadi/segmentary/blob/main/docs/tutorials/interpreting-results.md)
- [Configuration](https://github.com/arianizadi/segmentary/blob/main/docs/guides/configuration.md)
- [Custom datasets and loaders](https://github.com/arianizadi/segmentary/blob/main/docs/guides/custom-data.md)
- [Models and tuning](https://github.com/arianizadi/segmentary/blob/main/docs/guides/models-and-tuning.md)
- [Model catalog and compatibility probe](https://github.com/arianizadi/segmentary/blob/main/docs/guides/model-catalog-and-probe.md)
- [Switchable component catalog](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/README.md)
- [Full-suite capability roadmap](https://github.com/arianizadi/segmentary/blob/main/docs/roadmap/full-suite.md)
- [Model recipe catalog](https://github.com/arianizadi/segmentary/blob/main/configs/models/README.md)
- [Evaluation and fair comparisons](https://github.com/arianizadi/segmentary/blob/main/docs/guides/evaluation-and-results.md)
- [Export and deployment](https://github.com/arianizadi/segmentary/blob/main/docs/guides/export-and-deployment.md)
- [Troubleshooting](https://github.com/arianizadi/segmentary/blob/main/docs/guides/troubleshooting.md)
- [CLI](https://github.com/arianizadi/segmentary/blob/main/docs/reference/cli.md), [Python API](https://github.com/arianizadi/segmentary/blob/main/docs/reference/python-api.md), and
  [architecture](https://github.com/arianizadi/segmentary/blob/main/docs/reference/project-layout.md)
- [Glossary](https://github.com/arianizadi/segmentary/blob/main/docs/glossary.md)
- [Contributing](https://github.com/arianizadi/segmentary/blob/main/CONTRIBUTING.md)

## Bundled research examples

The repository includes Cityscapes, RailSem19, and staged rail-transfer configs
because they are a demanding real-world case study for multi-dataset taxonomy,
thin-class boundary metrics, curriculum handoff, and reproducible benchmarking.
They are examples, not defaults imposed on library users.

Use the [benchmark ledger](docs/benchmarks/README.md) to distinguish compatibility
checks from model-quality evidence. New quality results should be generated from
a clean, fully specified campaign rather than copied from earlier runs.

## Development

```bash
python -m pytest
ruff check src tests scripts
ruff format --check src tests scripts
python -m pip check
```

Real-data/GPU/export tests skip or require their documented extras and fixtures.
See [CONTRIBUTING.md](https://github.com/arianizadi/segmentary/blob/main/CONTRIBUTING.md) before changing a public config, loader,
model, metric, checkpoint, or result-record contract.

## License

Segmentary is available under the [MIT License](https://github.com/arianizadi/segmentary/blob/main/LICENSE). Dataset and pretrained
model licenses remain separate; review each dataset/model catalog page before
redistributing data or derived weights.
