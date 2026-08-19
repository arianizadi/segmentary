<h1 align="center">Segmentary</h1>

<p align="center">
  <b>Train, evaluate, and compare semantic-segmentation models — reproducibly.</b><br>
  Config-driven. No hidden defaults. Fails loudly instead of quietly.
</p>

<p align="center">
  <a href="https://github.com/arianizadi/segmentary/actions/workflows/checks.yml"><img alt="checks" src="https://github.com/arianizadi/segmentary/actions/workflows/checks.yml/badge.svg"></a>
  <img alt="python" src="https://img.shields.io/badge/python-3.11-blue">
  <a href="LICENSE"><img alt="license" src="https://img.shields.io/badge/license-MIT-green"></a>
</p>

---

Point it at a folder of images and masks, describe your experiment in YAML, and
get back metrics you can defend six months later — with the exact config, Git
commit, and environment recorded alongside every number.

```bash
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install -e '.[dev]'

segmentary-init my-project && cd my-project
segmentary-train base.yaml model.yaml experiment.yaml --seed 0
```

That's the whole loop. Everything below is detail you can reach for when you
need it.

## Quick start

**1. Install.** Requires Python 3.11 and a matching PyTorch build. Pick the
[CUDA wheel](docs/tutorials/installation.md) for your GPU, or the CPU line above.

**2. Scaffold a project.** `segmentary-init my-project` writes three composable
YAML files and a tiny example taxonomy.

**3. Drop in your data.** Masks are single-channel integer class IDs; `255` is ignored.

```text
data/
  images/train/frame_001.jpg    masks/train/frame_001.png
  images/val/frame_101.jpg      masks/val/frame_101.png
```

**4. Check before you commit GPU hours.**

```bash
segmentary-train base.yaml model.yaml experiment.yaml --print-config   # resolve config, open nothing
segmentary-verify --dataset my_dataset --loader folder --root data \
  --mapping my_dataset --space example --taxonomy taxonomy            # audit real mask IDs
segmentary-overfit base.yaml model.yaml experiment.yaml --images 8     # can it memorize 8 images?
```

If the model can't overfit eight images, the bug is in your data or your model —
not your learning rate. Finding that out takes a minute instead of a weekend.

**5. Train and evaluate.**

```bash
segmentary-train base.yaml model.yaml experiment.yaml --seed 0

segmentary-eval base.yaml model.yaml experiment.yaml \
  --ckpt runs/first_run_seed0/train_my_data/last.ckpt --ema \
  --out runs/first_run_seed0/eval_val/results.json
```

## How a run flows

<p align="center">
  <strong>YAML configuration</strong><br>
  <sub>Base → model → experiment, merged left to right</sub><br><br>
  ↓<br><br>
  <strong>Taxonomy mapping</strong><br>
  <sub>Native dataset IDs → canonical classes</sub><br><br>
  ↓<br><br>
  <strong>Training stage 1</strong><br>
  <sub>Writes a checkpoint and stage result</sub><br><br>
  ↓ <em>checkpoint</em><br><br>
  <strong>Additional training stages</strong> <em>(optional)</em><br>
  <sub>Continues from the verified checkpoint</sub><br><br>
  ↓<br><br>
  <strong>Evaluation</strong><br>
  <sub>Native resolution or sliding window</sub><br><br>
  ↓<br><br>
  <strong><code>results.json</code></strong><br>
  <sub>Metrics + resolved config + Git SHA</sub><br><br>
  ↓<br><br>
  <strong><code>segmentary-table</code></strong><br>
  <sub>Comparable results across models and seeds</sub>
</p>

Each stage writes its own `results.json`, so a three-stage curriculum produces
three comparable records instead of one summary that hides where the gain came
from.

## What you get

| | |
|---|---|
| **Models** | SegFormer, DeepLabV3+, UPerNet, HRNet-OCR, DINOv3, plus 10 SMP decoder families and any standard Hugging Face `AutoModelForSemanticSegmentation` |
| **Data** | Any paired image/mask folder, or your own `SegDataset` subclass via `package.module:Class` |
| **Training** | One-stage, sequential, or mixed-dataset curricula · full / frozen / LoRA tuning · EMA · iteration-based schedules |
| **Metrics** | mIoU, per-class IoU/accuracy/support, pixel accuracy, frequency-weighted IoU, confusion matrices, boundary precision/recall/F1 |
| **Evaluation** | Native resolution, sliding window, optional multi-scale + flip TTA reported as a separate variant — never as the headline |
| **Provenance** | Config hash, Git SHA and dirty flag, environment, wall time, peak VRAM in every result |
| **Export** | Static-shape ONNX / ONNX Runtime / TensorRT for the supported dense architectures |

## Watch it train

`segmentary-progress runs/my_campaign` gives every lane one row, so a ten-GPU
campaign fits in one window:

```text
SEGMENTARY ⠹  all-model-city-rail        12/120 jobs   10/10 lanes running        finish Fri 08:14 PM · 09:31:05 PM
─────────────────────────────────────────────────────────────────────────────────────────────────────────────────
LANE   CURRENT JOB                QUEUE        PROGRESS         ITERATIONS   LOSS    VAL mIoU        it/s   LEFT  AGE
GPU0 ● train  segformer_b5 / railsem19   ▶·········  ━━━━━━━━━━━━━━━     12,000/40,000 30%  0.4021  68.10% @8,000  0.79  9h51  14s
GPU1 ● train  upernet_convnext / cs      ✓▶········  ━━━━━━━━━━━━━━━     31,450/40,000 79%  0.2887  71.44% @28,000 0.60  3h58  41s
GPU2 ✗ failed native_resnet50_psp / cs   ✓✓✗·······  —                            —    —          —        —     —    —
```

**AGE** is the column to read when you're asking *is this thing alive?* It ticks
every second, while the metric columns only change when training logs — so a
still frame is never mistaken for a stall. The view is read-only; Ctrl-C closes
the display, not your training.

## Configuration

YAML files merge left to right. Lists replace rather than append. Unknown keys
and wrong types are fatal. The resolved config is embedded in every result.

```yaml
name: animals_transfer
space: animals

stages:
  - name: source
    data: [{name: source_photos, root: data/source, loader: folder, mapping: source_photos}]
    init_from: pretrained
    iters: 20000

  - name: target
    data: [{name: target_photos, root: data/target, loader: folder, mapping: target_photos}]
    init_from: previous     # inherit the previous stage's weights
    iters: 5000
    lr_scale: 0.1
```

## Why things fail loudly

Segmentary refuses to run when a config key is unknown, a taxonomy merge is
undeclared, pretrained weights load only partly, a checkpoint doesn't match the
model, or result records are unsafe to aggregate.

That is a deliberate trade. Each of those failures is one that would otherwise
surface months later as a number you can't explain — a mask padded with class
`0` instead of *ignore*, or two native labels silently collapsed into one.
Errors protect the meaning of your experiment rather than hiding it.

## Documentation

**Start here** — [Installation](docs/tutorials/installation.md) ·
[Getting started](docs/tutorials/getting-started.md) ·
[Core concepts](docs/tutorials/core-concepts.md) ·
[Interpreting results](docs/tutorials/interpreting-results.md)

**Guides** — [Configuration](docs/guides/configuration.md) ·
[Custom datasets](docs/guides/custom-data.md) ·
[Models and tuning](docs/guides/models-and-tuning.md) ·
[Evaluation](docs/guides/evaluation-and-results.md) ·
[Export and deployment](docs/guides/export-and-deployment.md) ·
[Troubleshooting](docs/guides/troubleshooting.md)

**Reference** — [CLI](docs/reference/cli.md) ·
[Python API](docs/reference/python-api.md) ·
[Project layout](docs/reference/project-layout.md) ·
[Model catalog](configs/models/README.md) ·
[Component catalog](docs/catalog/README.md) ·
[Glossary](docs/glossary.md)

The repository also ships Cityscapes, RailSem19, and staged rail-transfer
configs. They are worked examples of multi-dataset taxonomy and curriculum
handoff — not defaults imposed on you. No rail data is required to use anything
here.

## Development

```bash
python -m pytest          # full suite; hardware/data tests skip cleanly
ruff check src tests scripts && ruff format --check src tests scripts
mypy
```

All of the above run in CI on every pull request. See
[CONTRIBUTING.md](CONTRIBUTING.md) before changing a public config, loader,
model, metric, checkpoint, or result-record contract.

## License

[MIT](LICENSE). Dataset and pretrained-model licenses remain separate — check
each catalog page before redistributing data or derived weights.
