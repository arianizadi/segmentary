# Segmentary documentation

Segmentary is a semantic-segmentation library with a simple folder-dataset path
and explicit controls for advanced training and benchmarking. Choose the path
that matches your goal; you do not need to read every page first.

## New user: get one complete run

1. [Install Segmentary](tutorials/installation.md).
2. Follow [Getting started](tutorials/getting-started.md) to run
   `segmentary-init`, add paired images/masks, author a label space, verify the
   data, run a tiny memorization test, train, and evaluate.
3. Read [Core concepts](tutorials/core-concepts.md) when terms such as canonical
   labels, active masks, stages, EMA, or common evaluation appear.
4. Use [Interpreting results and debugging
   metrics](tutorials/interpreting-results.md) to understand the `0–1` scale,
   `null` versus zero, per-class support, confusion matrices, boundary scores,
   seed variance, and failure patterns.

The safe beginner sequence is:

```text
initialize project
      ↓
edit classes and native-ID mapping
      ↓
print/validate merged config
      ↓
verify real masks and inspect overlays
      ↓
memorize 8 images
      ↓
run full training
      ↓
evaluate an exact checkpoint
```

## Bring your own data or model

- [Custom datasets and loaders](guides/custom-data.md) covers the default
  `images/<split>` + `masks/<split>` layout, advanced directory options,
  native-ID mappings, group-safe video manifests, and Python loader extensions.
- [Models and tuning](guides/models-and-tuning.md) covers the generic Hugging
  Face `hf_auto` path, verified built-in architectures, pretrained-load safety,
  full/frozen/LoRA tuning, classifier reset, and architecture limitations.
- [Model catalog and compatibility probe](guides/model-catalog-and-probe.md)
  shows how to list typed recipes and run exact two-shape forward,
  loss/backward, gradient, and optimizer checks before opening a dataset.
- [Switchable component catalog](catalog/README.md) links the README beside
  every model, loader, curriculum, taxonomy, loss, tuning, runtime, evaluation,
  and export choice, including pros/cons and evidence boundaries.
- [Full-suite capability roadmap](roadmap/full-suite.md) records what is usable,
  partial, blocked, or planned without turning roadmap items into support claims.
- [Configuration](guides/configuration.md) explains every major field, why
  top-level `space` is required, merge semantics, mixed stages, and advanced
  runtime/evaluation controls.

## Design and report a fair experiment

- [Evaluation and results](guides/evaluation-and-results.md) explains native and
  common endpoints, EMA versus raw weights, final versus best checkpoints, TTA,
  multi-seed aggregation, and reproducible result records.
- [Export a scene for inference-checker](guides/scene-comparison.md) creates one
  canonical ground-truth/prediction bundle with checkpoint and protocol provenance.
- [Interpreting results](tutorials/interpreting-results.md) gives the detailed
  metric and debugging tutorial.
- [All-model Cityscapes and RailSem19 campaign](guides/all-model-city-rail-campaign.md)
  documents reuse-first scheduling, named tmux lanes, frozen training provenance,
  and incremental model README publication.
- [Export and deployment](guides/export-and-deployment.md) covers the explicitly
  supported ONNX, ONNX Runtime, TensorRT FP16, and TensorRT INT8 path, including
  parity and truthful accuracy/latency reporting.
- [Troubleshooting](guides/troubleshooting.md) starts with cheap checks and
  preserves evidence before expensive reruns.
For model comparisons, keep the label space, dataset split, checkpoint policy,
EMA/TTA settings, inference window, seed set, training budget, and source version
fixed. Change one named variable at a time.

## Use Segmentary as a library

- [CLI reference](reference/cli.md) lists `segmentary-init`, `segmentary-models`,
  `segmentary-progress`, `segmentary-verify`, `segmentary-overfit`,
  `segmentary-train`, `segmentary-eval`, `segmentary-export`, `segmentary-scene`,
  `segmentary-make-split`, and `segmentary-table`.
- [Python API](reference/python-api.md) shows config, taxonomy, loader, model,
  loss, metrics, inference, curricula, and result-record APIs.
- [Architecture and project layout](reference/project-layout.md) explains data
  flow, invariants, and extension points.
- [Glossary](glossary.md) translates config and metric terms into plain
  language.
- [Contributing](../CONTRIBUTING.md) defines compatibility and verification
  requirements.

The CLI is the easiest path to provenance-rich experiments. The Python API is
appropriate for a notebook, test, service, or custom orchestration layer that
still wants the same validated components.

## Beginner and advanced choices

| Goal | Start with | Advance when |
|---|---|---|
| Check data/model wiring | folder loader, small model, 8-image overfit | the tiny set reaches its target |
| Establish a baseline | one dataset, one stage, full tuning | the one-stage result is valid and reproducible |
| Use a Hub model | complete standard `hf_auto` segmentation checkpoint | you need an explicit built-in recipe or custom module layout |
| Save memory | frozen backbone, then LoRA | the accuracy ceiling or target-module coverage is understood |
| Transfer across domains | sequential stages with `init_from: previous` | source and target controls exist |
| Train datasets together | mixed stage with explicit `sample_weights` | mappings share one canonical space |
| Compare models | exact common evaluation target, at least three seeds | every protocol and provenance field matches |
| Deploy | ONNX/ORT parity, then TensorRT FP16 | representative INT8 calibration proves an actual benefit |

## Bundled rail-transfer case study

Cityscapes, RailSem19, and rail-transfer YAMLs remain as executable research
examples. They demonstrate cross-dataset taxonomy, inactive classes, sequential
versus mixed training, thin-structure boundary metrics, and common-target
evaluation. They are not required for your own project.

The [benchmark ledger](benchmarks/README.md) explains evidence levels and keeps
compatibility checks separate from model-quality claims. No prior quality table
is bundled; start new comparisons from a clean, fully specified campaign.
