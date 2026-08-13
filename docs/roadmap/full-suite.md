# Building Segmentary into a full segmentation suite

Segmentary's goal is a broad, composable semantic-segmentation library with a
small beginner path and strict advanced controls. “Full” does not mean that an
arbitrary Python config or every model name from another package is silently
accepted. It means the common pieces are independently selectable, their
contracts compose, unsupported combinations fail early, and every advertised
recipe has evidence.

Segmentary uses mature libraries and papers as references, but owns its config,
component interfaces, training loop, objectives, taxonomy mapping, evaluation,
checkpoints, and provenance. It does not import or execute MMSegmentation
configs, registries, runners, or model implementations.

## Status words

Every catalog choice uses one of four evidence levels:

| status | meaning |
|---|---|
| **available** | implemented, documented, and covered by its required contract tests |
| **admitted recipe** | the exact composition and requested weights passed the recipe admission protocol |
| **experimental** | usable for a named ablation, but an important scientific or deployment contract differs from the reference method |
| **blocked** | deliberately rejected because construction alone would give a misleading or invalid model |

A tiny optimizer smoke proves wiring, not accuracy. A model-quality claim still
requires a complete dataset split, fixed taxonomy and evaluator, exact
checkpoint/EMA/TTA policy, code revision, and the planned seed set.

## Current capability map

### Tasks and outputs

| capability | current status | exact boundary |
|---|---|---|
| multiclass semantic segmentation | **available end to end** | integer masks, canonical classes, ignore `255`, dense or query-model evaluation |
| dense logits | **available** | raw `(N,C,H,W)` logits; activation belongs to the objective or postprocessor |
| auxiliary dense heads | **available** | named full-resolution outputs with independent positive loss weights |
| semantic query/mask training | **available** | Hungarian class, mask-BCE, and Dice objective over one mask per present semantic class |
| binary semantic segmentation | **available end to end** | one foreground logit, canonical IDs `0`/`1`, sigmoid/threshold inference, binary-aware TTA, 2x2 metrics, checkpoints, results, and overfit checks |
| multilabel objectives | **objective available; data/evaluator pending** | independent-channel targets are tested at the loss layer, not yet a public dataset/result protocol |
| instance, panoptic, video, depth, or multimodal tasks | **not yet public** | these need different targets, postprocessing, metrics, and result schemas; they are not aliases for semantic segmentation |

The query objective is semantic set prediction: disconnected regions with the
same class form one target mask. It is not an instance-segmentation objective.

### Model sources

| source | current status | safety boundary |
|---|---|---|
| Segmentary-native composition | **available** | typed timm backbone, identity/FPN/ChannelMapper neck, typed dense head, optional auxiliary heads |
| Segmentation Models PyTorch | **available** | eleven curated decoder/encoder recipes plus explicit dynamic choices with audited preprocessing |
| Hugging Face semantic checkpoints | **available** | complete standard `AutoModelForSemanticSegmentation` models, remote code disabled, strict load/layout/processor audit |
| hand-integrated built-ins | **available or explicitly experimental** | SegFormer, UPerNet, HRNet/OCR, DeepLabV3+, EoMT, and local DINOv3 loading utilities |
| arbitrary upstream code | **blocked by design** | no `trust_remote_code`, arbitrary constructor kwargs, Python config execution, or silent partial checkpoints |

The repository currently ships 37 model YAMLs: twelve native compositions,
eleven SMP recipes, six revision-pinned Hugging Face recipes, and eight
built-in recipes. The model index is the authority for each recipe's exact
status.

### Native components

| layer | available choices | important limit |
|---|---|---|
| backbone | typed timm `features_only` adapter with exact name/tag, requested weights, and output indices | a timm listing is not automatically an admitted recipe |
| neck | identity, FPN, ChannelMapper | token-to-pyramid adapters for flat transformer features remain planned |
| main or auxiliary dense head | FCN, SegFormer-MLP, PSP, ASPP, DeepLabV3+, LR-ASPP, UPer, DPT, OCR | all return input-resolution raw logits; OCR also returns an explicitly weighted named coarse output |
| normalization | BatchNorm, GroupNorm, InstanceNorm, per-pixel LayerNorm2d, none | batch-one global-context branches omit only their invalid `1x1` BatchNorm |
| block activation | ReLU, ReLU6, LeakyReLU, GELU, SiLU, ELU, Mish, Hardswish | prediction heads still return raw logits |
| tuning | full, frozen backbone, LoRA where an audited linear target layout exists | convolution-only native backbones reject LoRA rather than training nothing |

Every component validates feature count, channel count, spatial reduction,
selected indices, parameter ownership, output size, and classifier reset. A
recipe must additionally prove the exact assembled graph and pretrained source.

### Objectives

Dense objectives are weighted, typed terms:

- cross-entropy and binary cross-entropy;
- Dice, Jaccard, Lovasz, focal, and Tversky;
- online hard-example-mined cross-entropy;
- boundary and truncated differentiable Hausdorff surrogates;
- KL distillation when a caller supplies an aligned teacher.

All dense terms share exact ignore and per-sample active-class semantics. Query
models can instead select the separate Hungarian class/mask objective. Dense
and query objectives cannot be mixed accidentally.

The standard CLI does not yet instantiate a distillation teacher. Selecting KL
therefore fails before training instead of producing a student-only run.

### Data, training, evaluation, and deployment

Available today:

- paired-folder datasets, Cityscapes, RailSem19, the legacy custom loader, and
  a reviewed `SegDataset` subclass import path;
- explicit native-ID to canonical mappings, active classes, ignore handling,
  group-safe manifests, and mixed-dataset sampling;
- one-stage, sequential-transfer, and joint curricula;
- AdamW, layer-wise decay, warmup plus polynomial scheduling, gradient
  clipping, mixed precision, DDP, EMA, retained/final checkpoints, and strict
  stage handoff;
- native-resolution whole/sliding inference, multi-scale/flip TTA, confusion
  metrics, per-class support/IoU/accuracy, and boundary metrics;
- provenance-rich result records and fail-closed multi-seed aggregation;
- explicitly admitted ONNX, ONNX Runtime, TensorRT FP16, and calibrated INT8
  export paths.

Deployment support remains architecture-specific. A training recipe is not
automatically exportable, and an exported graph is not accepted until numerical
parity and precision composition are measured.

## What comes next

The implementation order follows dependencies rather than the number of names
we can place in a menu.

### Priority 0: finish cross-cutting contracts

1. Define a real multilabel mask storage/loader contract, task-aware metrics,
   thresholds, and result schema before exposing multilabel training in the CLI.
2. Make the catalog/probe command the common admission front door for every
   model family.
3. Add a public teacher-provider contract before exposing the implemented KL
   objective through the standard training CLI.

### Priority 1: broaden composable semantic architectures

1. Add token-to-pyramid necks for flat transformer features with declared
   reductions.
2. Add PointRend/cascade refinement and a native query decoder one at a time.
3. Add curated real-time families such as BiSeNet, DDRNet, and PIDNet through
   the same output, optimizer, checkpoint, and evaluation contracts.
4. Add conventional Mask2Former with a valid hierarchical backbone before any
   DINOv3 variant. DINOv3 requires an explicit spatial-prior/pyramid adapter;
   a flat stride-16 ViT is not a valid shortcut.
5. Expand pretrained native recipes only after exact source, normalization,
   variable-shape, optimizer, and DDP admission passes.

### Priority 2: additional tasks and deployment

1. Add instance and panoptic target adapters, matching criteria,
   postprocessors, and metrics as separate task protocols.
2. Add temporal/video and multimodal inputs only with explicit batch and
   evaluator contracts.
3. Broaden ONNX/TensorRT support per architecture, retaining explicit
   unsupported reasons where a graph cannot be exported safely.
4. Build same-protocol, multi-seed quality tables after functionality—not from
   upstream paper numbers measured on incompatible data.

## Admission gate for every new recipe

A recipe is not “supported” until the applicable checks pass:

1. typed config with no arbitrary kwargs and an immutable pretrained source;
2. exact weight-load diagnostics and preprocessing audit;
3. two distinct non-square shape checks, including an odd shape where the
   architecture claims variable resolution;
4. finite production loss and several optimizer steps;
5. a present finite gradient for every trainable tensor, or an exact documented
   inactive path frozen before optimizer construction;
6. verified classifier/head update and disjoint parameter ownership;
7. full/frozen/LoRA behavior or an explicit, tested rejection;
8. checkpoint, EMA, reset, and resume/handoff behavior;
9. single-rank and multi-rank DDP checks where the recipe is intended for DDP;
10. point-of-choice README with beginner use, advanced settings, pros, cons,
    limits, and exact evidence;
11. real dataset overfit and full benchmark as separate, higher evidence levels;
12. export parity or a precise unsupported reason.

This gate intentionally prevents “popular on the Hub” from becoming “works in
Segmentary” without proof.

## Why the suite does not promise every possible combination

Backbone, neck, head, objective, task, crop, precision, and tuning choices form
a huge Cartesian product. Many combinations are structurally invalid: a head
may need four feature scales, a transformer may require a token-to-pyramid
adapter, a binary model needs one output channel, and a query model needs a
matching objective. Testing every string against every other string would
create a large but misleading API.

Segmentary instead provides:

- strict reusable component contracts;
- curated admitted recipes;
- an explicit model probe for new compositions;
- loud compatibility errors;
- recipe-specific evidence and documentation.

That is the path to a dependable full suite: broad enough to compose serious
experiments, but precise enough that a successful command still means
something.

## Related documentation

- [Switchable component catalog](../catalog/README.md)
- [Model recipe index](../../configs/models/README.md)
- [Model and tuning guide](../guides/models-and-tuning.md)
- [Objective library](../catalog/components/losses/README.md)
- [Benchmark and evidence ledger](../benchmarks/README.md)
- [Contributing and admission requirements](../../CONTRIBUTING.md)
