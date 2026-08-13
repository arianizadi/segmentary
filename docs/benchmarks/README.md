# Benchmark and evidence ledger

This folder separates implementation evidence from model-quality results.
Segmentary currently bundles no model-quality leaderboard or prior training-result
table. Start new quality comparisons from a clean campaign with fixed datasets,
taxonomies, seeds, optimizer-step budgets, checkpoints, and evaluation settings.

## Evidence levels

1. **Model-quality benchmark:** complete training and evaluation under one fixed,
   reproducible protocol.
2. **Deployment acceptance:** checkpoint parity and runtime behavior for a named
   export backend.
3. **Overfit proof:** optimization on a tiny fixed sample; useful for wiring only.
4. **Compatibility smoke:** construction, forward/backward, gradients, and an
   optimizer update; never a quality claim.
5. **Documented or blocked:** a design exists but a required dependency or
   scientifically correct objective is unavailable.

## Retained compatibility evidence

- [Model-catalog smokes](model-catalog-smokes/README.md)
- [Native-component smokes](native-component-smokes/README.md)
- [SegFormer-B2 export acceptance](segformer-b2-export/README.md)
- [DeepLabV3+ R101 untrained export acceptance](deeplabv3plus-r101-untrained-export/README.md)

These records prove only what their individual pages state. Compatibility,
gradient, export, latency, or tiny-set evidence must not be promoted into a
generalization or model-quality result.

## Rules for future quality results

- publish the exact config, source revision, seed, dataset split, taxonomy, and
  checkpoint policy;
- compare models under the same optimizer-step and effective-batch budget;
- use the same EMA/raw, sliding-window, TTA, and evaluator settings;
- report task-critical class support and boundary behavior beside aggregate
  metrics in machine-readable artifacts;
- keep user-facing Markdown concise and place raw seed-level data in JSON or CSV.
