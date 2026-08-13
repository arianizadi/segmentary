# Architecture and project layout

Segmentary keeps scientific contracts in small explicit modules. Built-in models
use one audited factory. Datasets use built-in IDs or an explicit
`package.module:SegDatasetSubclass` path, which keeps the extension source
visible in config and provenance without introducing a global plugin registry.

```text
configs/                  composable experiment YAML
  base.yaml
  models/                 architecture/tuning defaults
  curricula/              ordered data/stage plans
taxonomy/                 canonical label spaces and native-id mappings
splits/                   versioned dataset partitions
src/segmentary/
  config.py               typed merge, validation, stable hashing
  taxonomy.py             canonical classes and uint8 LUT mappings
  data/                    datasets, transforms, mixed sampling, loaders
  models/                  wrappers, factory, tuning, local DINO conversion
  engine/                  loss, metrics, boundary, EMA, inference, optimizer
  curriculum.py           stage execution and checkpoint threading
  train.py / eval.py      reproducible CLIs
  init_project.py         packaged portable starter
  verify.py / overfit.py  data audit and tiny memorization CLIs
  export.py               ONNX/TensorRT pipeline
  utils/                   results, environment provenance, seeding
scripts/                   verification, custom splitting, tables, orchestration
tests/                     numeric contracts plus real data/GPU integrations
docs/                      tutorials, guides, and reproduction notes
```

## Data flow

```text
native mask
  -> DatasetMapping LUT
  -> canonical uint8 mask + per-sample active-class vector
  -> geometric/color transform (mask uses nearest neighbor, 255 padding)
  -> model input-resolution logits
  -> task-aware active masking + multiclass or binary dense loss
  -> EMA shadow
  -> native-resolution sliding-window metrics
  -> checkpoint + provenance-rich results.json
```

## Curriculum flow

```text
validated merged config
  -> stage 1 model + loaders + optimizer
  -> true-final checkpoint (EMA persisted)
  -> stage 2 fresh model construction
  -> exact EMA checkpoint load, optional classifier reset/freeze/tuning
  -> stage 2 training
  -> one result record per stage
```

Fresh construction at every stage prevents optimizer/module state from leaking
implicitly. The checkpoint load validates complete parameter coverage.

## Key invariants

1. **Canonical ids are contiguous and uint8-safe.** Ignore is always 255.
2. **Unknown native ids do not become supervision.** Default mapping is ignore.
3. **Many-to-one label merges need written reasons.** Stale declarations fail.
4. **Each sample carries its active classes.** Mixed datasets are safe within one
   batch; impossible classes receive no gradient.
5. **Every model returns input-resolution dense outputs.** Backends cannot change
   the downstream contract.
6. **Published validation stays native-resolution.** Training crops never leak
   into the evaluator protocol.
7. **Stage handoff uses evaluated EMA weights when the checkpoint has them.**
   Malformed EMA and partial model loads fail loudly; a legacy checkpoint with
   no EMA follows the documented raw-weight compatibility path.
8. **The final checkpoint is the actual final optimizer step.** A dedicated save
   occurs after fit rather than trusting callback naming behavior.
9. **Every result records config, seed, code, environment, and dataset size.**
10. **Aggregation proves replicate equivalence before calculating a mean.**

## Extending a dataset

1. Prefer the generic `folder` loader and its documented `loader_options`.
2. For a genuinely different source, add a `SegDataset` subclass with strict,
   deterministic indexing and configure `package.module:Class`. Add a built-in
   dispatch only when the format belongs in Segmentary itself.
3. Add mapping YAML for every label space it should support.
4. Add real/synthetic tests for id coverage, split behavior, transforms, active
   classes, and native validation resolution.
5. Exercise it through `segmentary-verify` and inspect overlays.

Imported loader code executes locally, so it must be reviewed and versioned.
The resolver rejects non-classes and classes outside the `SegDataset` contract.

## Extending a model

1. Wrap it as `SegmentationModel` with input-resolution outputs.
2. Identify exact backbone modules and head parameter patterns.
3. Implement head reset without touching the backbone.
4. Add one explicit factory branch and model default.
5. Test non-square output shape, parameter partition, pretrained tensor identity,
   tuning gradients, and a real construction/forward when feasible.
6. Decide whether dense CE is scientifically valid. If not, expose
   `supports_dense_ce=False` and implement the native objective before claiming
   paper parity.
7. Add explicit export support or an explicit unsupported reason.

## Extending metrics or results

Streaming metric state must define ignore behavior, active/absent classes,
distributed reduction, reset, JSON-safe output, and a hand-computed independent
test. New headline metrics require result-schema/table validation so a missing
seed cannot silently produce a plausible aggregate.
