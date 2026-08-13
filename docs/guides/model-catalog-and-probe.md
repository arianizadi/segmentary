# Model catalog and compatibility probe

`segmentary-models` answers two different questions without opening a dataset:

1. **What model recipes are available?** `segmentary-models list` type-checks and
   lists the installed YAML catalog. It does not construct a model or download
   weights.
2. **Can this exact composed model enter training?** `segmentary-models probe`
   constructs the first-stage model, checks preprocessing and variable shapes,
   and runs Segmentary's real loss/backward/AdamW path on synthetic data.

The probe dispatch is explicit: ordinary `loss.terms` use the production dense
objective, while `loss.query` uses the production Hungarian class/mask
objective over raw queries. A query-capable model with a dense objective keeps
Segmentary's deliberately supported legacy dense-collapse ablation and labels it
`experimental_dense_query_collapse` in JSON and human output. A dense model
with `loss.query` fails instead of silently switching objectives.

A passing probe is a compatibility check. It is not mIoU, convergence, speed,
memory-at-production-crop, or evidence that one architecture is better than
another.

## Beginner workflow

List the recipes shipped by the checkout or installed wheel:

```bash
segmentary-models list
```

Choose one YAML, compose it exactly as you would for training, and probe it:

```bash
segmentary-models probe \
  configs/base.yaml \
  configs/models/native_resnet18_fpn_fcn.yaml \
  path/to/your_experiment.yaml
```

The files merge left to right and pass through the same strict
`ExperimentConfig` parser as training. The experiment supplies the taxonomy,
so the probe builds the real class count rather than an invented three-class
head. It reads `taxonomy_root/<space>/canonical.yaml`, but it does **not** open
the configured image roots or masks.

The default protocol uses batch one, FP32 CPU, two deliberately different
non-square inputs (`64x96` and odd `65x97`), and two optimizer steps. Requested
pretrained weights still load normally, so a first run may download them. A
missing or gated weight request is an error; there is no retry from scratch.

Save a machine-readable record when the check matters:

```bash
segmentary-models probe \
  configs/base.yaml configs/models/native_resnet18_fpn_fcn.yaml experiment.yaml \
  --output reports/resnet18-fpn-fcn-probe.json
```

`--json` prints the same single JSON document to standard output. `--output`
writes it atomically and can be combined with either human or JSON terminal
output. A failed probe returns nonzero and retains a small failure JSON when an
output path was requested.

## What a probe proves

The command applies the first stage's real configuration in this order:

1. merge and type-check every YAML and `--set` override;
2. reject an incompatible model/objective task or unsupported teacher loss;
3. load the canonical label space and build the requested model and weights;
4. apply configured tuning, first-stage classifier reset, and explicit freeze;
5. validate three-channel mean/std, channel order, and normalization source;
6. forward both non-square shapes and require finite input-resolution NCHW
   evaluation logits with the canonical class count; a query configuration also
   validates and records every raw primary/auxiliary class and mask tensor;
7. construct `SegmentationLoss` or `QuerySegmentationLoss` from the configured
   objective and the same stage-scaled AdamW parameter groups training uses;
8. call `dense_training_objective` (including every named native auxiliary
   head) or `query_training_objective` (including configured decoder-layer
   supervision), then backward, optional gradient clipping, and
   `optimizer.step()`;
9. require a present, finite gradient for every trainable tensor and require at
   least one tracked classifier (or, for older wrappers, head) tensor to change;
10. record config hash, source state, environment, preprocessing, parameters,
    optimizer groups, shapes, loss components, gradients, and peak reserved
    CUDA memory when applicable.

For a Segmentary-native model, the record additionally describes the exact
backbone, pretrained source metadata exposed by timm, chosen feature indices,
backbone and neck feature channel/reduction contracts, main and auxiliary head
types, selected features, and disjoint parameter-tensor ownership.

An inactive upstream branch is not silently excused. It must already be listed
as a revision-pinned `inactive_parameter_paths` exception, which makes its
parameters non-trainable before the audit. Every remaining trainable parameter
must receive a finite gradient.

## Failures are useful

The command intentionally stops instead of weakening the protocol:

| failure | what it means | next check |
|---|---|---|
| unknown YAML key or wrong type | the experiment is not the config you think it is | fix the named field; do not add arbitrary kwargs |
| pretrained load error | the exact requested weights were unavailable or incompatible | check access, revision/tag, cache, and library version |
| incomplete or invalid normalization | Segmentary cannot reproduce the model's input distribution | use a supported processor/weight contract |
| first stage initializes from a checkpoint | a constructor-only probe would not be the exact first-stage state | use checkpoint-aware train/eval, or probe a `pretrained` first stage |
| one shape fails | the model may be fixed-size or the crop is below a pyramid minimum | document and test the true supported shape; do not claim arbitrary resolution |
| model advertises neither dense nor raw-query training | there is no reviewed production objective path | implement and test one explicit contract; the probe will not guess |
| `loss.query` with dense output | the selected model exposes no raw query contract | choose a query model or a dense loss; the probe will not invent queries |
| task/objective mismatch | target encoding and output semantics disagree | align multiclass/binary/multilabel model, loss, and taxonomy |
| missing gradient | a supposedly trainable branch is disconnected from the production loss | fix the graph or freeze one exact audited inactive path |
| non-finite logit, loss, or gradient | the configuration is numerically unsafe even on a tiny input | inspect normalization, precision, objective, and learning rate |
| no classifier or head update | the optimizer did not affect the prediction path | inspect tuning, head patterns, learning rates, and frozen parameters |

The probe never silently changes device, precision, shape, objective, model,
weights, or task to make a failure disappear.

## Advanced controls

```bash
segmentary-models probe base.yaml model.yaml experiment.yaml \
  --shape 257x385 --shape 513x769 \
  --batch-size 2 --steps 4 \
  --device cuda:0 --precision bf16 \
  --seed 42 \
  --set loss.terms='[{"kind":"cross_entropy","weight":1.0},{"kind":"dice","weight":0.5}]' \
  --json --output reports/model-probe.json
```

For a mask-classification recipe, select the query objective explicitly:

```bash
segmentary-models probe base.yaml configs/models/eomt_large.yaml experiment.yaml \
  --set loss.query='{"kind":"hungarian_query"}' \
  --shape 511x639 --shape 513x641 \
  --device cuda:0 --precision bf16 --steps 4 \
  --output reports/eomt-query-probe.json
```

EoMT still runs its checkpoint-native internal grid; the two public input shapes
prove Segmentary's resize-and-restore wrapper, not native arbitrary-grid support.
If `loss.query` is absent, the same model intentionally exercises the older
dense-collapse pixel-loss ablation instead. The record warns and names that
contract explicitly; do not compare it to native-query or published EoMT
results without treating objective choice as a separate experimental arm.

| option | purpose and tradeoff |
|---|---|
| repeated `--shape HxW` | test at least two distinct non-square shapes; larger values better expose memory/minimum-pyramid limits but cost more |
| `--batch-size` | exposes batch-sensitive normalization; larger values consume more memory |
| `--steps` | repeats real backward/AdamW while alternating shapes; four is a useful admission smoke, not convergence |
| `--device` | exact PyTorch device; CUDA and MPS requests never fall back to CPU |
| `--precision` | `auto` means BF16 on CUDA and FP32 otherwise; explicit BF16 requires a CUDA device that reports support |
| repeatable `--set` | dotted JSON-valued override; the resolved typed config and hash reflect it |
| `--json` | automation-friendly stdout; model-library logs may still appear on stderr |
| `--output` | durable evidence or durable failure reason |

Both shapes must remain non-square. A square-only smoke can miss swapped
height/width assumptions, and accepting a single convenient shape would make
“variable input” an untested claim.

## Catalog discovery and installed wheels

`list` looks for `configs/models` in the current or source checkout and then the
wheel's `share/segmentary/configs/models` directory. Use `--config-dir PATH` to
inspect a different typed recipe directory. Every `*.yaml` there must contain a
top-level `model` mapping; one invalid recipe fails the catalog rather than
being omitted from a plausible-looking list.

The catalog is a curated starting set, not a claim that every upstream model
works. `hf_auto`, SMP, and Segmentary-native adapters each preserve their own
load, preprocessing, shape, and objective boundaries. Run the probe on the
exact new composition before scheduling training.

## Full native-catalog GPU acceptance

Maintainers can opt into the real pretrained acceptance test. It dynamically
discovers every recipe whose parsed `model.arch` is `native`, runs them
sequentially to release memory, and requires four BF16 optimizer steps per
recipe:

```bash
CUDA_VISIBLE_DEVICES=0 \
SEGMENTARY_EXPECTED_CUDA_VISIBLE_DEVICES=0 \
SEGMENTARY_RUN_NATIVE_CATALOG_GPU=1 \
SEGMENTARY_NATIVE_CATALOG_EVIDENCE=reports/native-catalog-gpu.json \
python -m pytest -q -s tests/test_native_catalog_gpu.py
```

Expose exactly one GPU and set the expected visibility string to the same
value. This avoids assuming a workstation or cluster numbering scheme while
making accidental device use fatal. The aggregate JSON retains per-recipe
records and labels the entire protocol `synthetic_data: true` and
`quality_benchmark: false`.

## Pros and cons

Pros:

- catches model/config/preprocessing/loss/optimizer incompatibility before data
  loading or a long reservation;
- uses public typed configs and production training components rather than a
  parallel toy registry;
- produces reviewable machine evidence;
- provides deeper native feature/component diagnostics than a plain forward.

Cons:

- synthetic labels cannot test dataset mappings, augmentation, learning, or
  generalization;
- tiny shapes and steps understate production memory and reveal no throughput;
- loading real pretrained weights can still require network access, license
  acceptance, cache space, and time;
- passing today does not replace dependency and version pinning for a reported run.

After a probe passes, run `segmentary-verify` on real masks and
`segmentary-overfit` on a few real samples. Only a complete named split under a
fixed taxonomy, schedule, checkpoint policy, evaluator, and seed set belongs in
a model-quality comparison.
