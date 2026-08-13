# Switchable component catalog

This is the map of every public choice in Segmentary. A model, dataset,
curriculum, loss, or runtime setting is not just a string: its README explains
what it changes, when a beginner should use it, advanced controls, tradeoffs,
known incompatibilities, and exactly what evidence exists.

For capabilities that are not yet admitted catalog choices, see the
[full-suite capability roadmap](../roadmap/full-suite.md).

## Start here

For a first project, use one choice from each row:

| layer | beginner starting point | catalog |
|---|---|---|
| model | SegFormer-B0 or SMP U-Net/ResNet-34 | [model recipes](../../configs/models/README.md) and [compatibility probe](../guides/model-catalog-and-probe.md) |
| task | multiclass; native binary for exactly two mutually exclusive classes | [semantic task modes](components/tasks/README.md) |
| dataset | paired folders | [datasets](datasets/README.md) and [loaders](components/loaders/README.md) |
| taxonomy | copy `example` and define your own classes | [taxonomy spaces](../../taxonomy/README.md) |
| curriculum | one stage / one dataset | [curricula](curricula/README.md) and [ready YAMLs](../../configs/curricula/README.md) |
| tuning | full fine-tuning | [tuning](components/tuning/README.md) |
| loss | cross-entropy | [losses](components/losses/README.md) |
| augmentation | shipped base defaults | [augmentation](components/augmentation/README.md) |
| optimizer/runtime | AdamW + poly schedule; one GPU first | [optimization](components/optimization/README.md) and [runtime](components/training-runtime/README.md) |
| evaluation | native validation, EMA, no TTA first | [evaluation](components/evaluation/README.md) |
| deployment | ONNX parity before TensorRT | [export](components/export/README.md) |

The normal composition is:

```bash
segmentary-train \
  configs/base.yaml \
  configs/models/smp_unet_resnet34.yaml \
  path/to/your_experiment.yaml
```

The files merge left to right. The model layer does not choose your dataset,
and the curriculum does not silently rewrite your optimizer. This separation is
inspired by the useful part of MMSegmentation's model/dataset/schedule design,
while Segmentary keeps a smaller typed schema and rejects unknown keys instead of
using a dynamic registry.

## Model building blocks

- [All ready model YAMLs and factory statuses](../../configs/models/README.md)
- [Hand-integrated built-ins](components/builtin-models/README.md)
- [Hugging Face `hf_auto`](components/hf-auto/README.md)
- [Composable SMP decoders and encoders](components/smp/README.md)
- [Segmentary-native backbones](components/native-backbones/README.md)
- [Segmentary-native necks](components/native-necks/README.md)
- [Segmentary-native dense and auxiliary heads](components/native-heads/README.md)
- [Segmentary-native normalization, activation, and dropout blocks](components/native-blocks/README.md)
- [Backbones](components/backbones/README.md)
- [Heads and output strategy](components/heads/README.md)

The model recipe index covers the shipped native compositions, SegFormer,
UPerNet, HRNet/OCR, DeepLab, EoMT, revision-pinned Hugging Face semantic
checkpoints, and SMP decoder/encoder recipes. `mask2former_dinov3` has a page
but remains deliberately blocked until its required feature-pyramid adapter
exists.

## Data and experiment design

- [Multiclass and native binary task contracts](components/tasks/README.md)
- [Built-in datasets and extension paths](datasets/README.md)
- [Loader mechanics](components/loaders/README.md)
- [Canonical taxonomy spaces and mappings](../../taxonomy/README.md)
- [Curriculum patterns and all ten recipes](curricula/README.md)
- [Full/frozen/LoRA tuning](components/tuning/README.md)
- [Losses](components/losses/README.md)
- [Hungarian query/mask objective](components/query-objectives/README.md)
- [Augmentation](components/augmentation/README.md)

## Training, measurement, and deployment

- [Optimization and scheduling](components/optimization/README.md)
- [Training runtime, EMA, checkpoints, DDP, and precision](components/training-runtime/README.md)
- [Evaluation choices and metric contracts](components/evaluation/README.md)
- [Export and deployment](components/export/README.md)
- [Benchmark and evidence ledger](../benchmarks/README.md)
- [Interpreting results and debugging](../tutorials/interpreting-results.md)

## How evidence labels work

A page may report one or more of these, and should never blur them together:

1. **Contract test:** config, construction, shape, parameter partition, or
   gradient behavior.
2. **Training smoke:** a few optimizer steps completed. This finds wiring bugs;
   it does not rank accuracy.
3. **Deployment acceptance:** backend parity, precision composition, accuracy
   degradation, and latency under one exact protocol.
4. **Model-quality benchmark:** trained result with data split, taxonomy,
   schedule, checkpoint/EMA/TTA policy, code revision, and seeds recorded.

When no comparable benchmark exists, the page says so. Upstream paper scores,
tiny synthetic smokes, untrained deployment checks, and Segmentary dataset results
are never combined into one ranking table.

## Adding a choice

A new option belongs here only after it has:

1. a typed config field or reviewed allowlist entry;
2. a fail-closed construction/load contract;
3. preprocessing, output, tuning, and checkpoint compatibility checks;
4. a small real forward/backward or optimizer smoke where practical;
5. a point-of-choice README with pros, cons, limits, and truthful evidence;
6. an inbound link from the relevant index.

Start with [Contributing](../../CONTRIBUTING.md), then add the smallest tested
extension rather than a generic arbitrary-kwargs escape hatch.
