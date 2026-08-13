# Curriculum configuration files

Each file in this directory chooses a label space and an ordered data/stage
plan. It is designed to merge after `configs/base.yaml` and one model file:

```bash
segmentary-train \
  configs/base.yaml \
  configs/models/segformer_b2.yaml \
  configs/curricula/rs_only.yaml \
  --seed 0 --devices 1 --print-config
```

Configs merge left to right. Nested mappings merge, but lists—especially
`stages` and each stage's `data`—are replaced as a whole. Always inspect
`--print-config` after adding a site override.

## Beginner choice

Start with a one-stage control that matches the data you actually have:
`cs_only`, `rs_only`, or a copied generic folder experiment. Run the verifier
and overfit check before a staged or mixed curriculum. Use the linked detailed
README whenever choosing a file; it includes prerequisites, exact stage
behavior, pros/cons, and benchmark limits.

## Choose a curriculum

| config | status | stages | detailed README |
|---|---|---|---|
| [`cs_only.yaml`](cs_only.yaml) | runnable with Cityscapes | Cityscapes | [`cs_only`](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/cs_only/README.md) |
| [`rs_only.yaml`](rs_only.yaml) | runnable with RailSem19 | RailSem19 | [`rs_only`](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/rs_only/README.md) |
| [`cs_rs.yaml`](cs_rs.yaml) | runnable with both | Cityscapes -> RailSem19 | [`cs_rs`](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/cs_rs/README.md) |
| [`cs_rs_railbridge.yaml`](cs_rs_railbridge.yaml) | runnable named ablation | rail-bridge Cityscapes -> RailSem19 | [`cs_rs_railbridge`](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/cs_rs_railbridge/README.md) |
| [`joint_cs_rs.yaml`](joint_cs_rs.yaml) | runnable with both | Cityscapes + RailSem19 | [`joint_cs_rs`](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/joint_cs_rs/README.md) |
| [`reference_cityscapes19.yaml`](reference_cityscapes19.yaml) | runnable with Cityscapes | standard Cityscapes-19 | [`reference_cityscapes19`](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/reference_cityscapes19/README.md) |
| [`direct.yaml`](direct.yaml) | blocked on custom data | custom | [`direct`](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/direct/README.md) |
| [`rs_custom.yaml`](rs_custom.yaml) | blocked on custom data | RailSem19 -> custom | [`rs_custom`](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/rs_custom/README.md) |
| [`cs_rs_custom.yaml`](cs_rs_custom.yaml) | blocked on custom data | Cityscapes -> RailSem19 -> custom | [`cs_rs_custom`](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/cs_rs_custom/README.md) |
| [`joint.yaml`](joint.yaml) | blocked on custom data | Cityscapes + RailSem19 -> custom | [`joint`](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/joint/README.md) |

## Site paths without editing research configs

Keep machine-specific roots in an uncommitted/site-specific YAML merged last:

```yaml
# site.yaml -- lists replace, so copy the selected curriculum's complete stages
stages:
  - name: railsem19
    data:
      - name: railsem19
        root: /your/datasets/railsem19
        split_file: splits/railsem19_seed0.json
    init_from: pretrained
```

For a one-off scalar, `--set` is safer than copying a full curriculum. Because
stages are lists, dotted CLI overrides do not address an individual list item;
use a complete small YAML layer when stage structure or paths change.

## Rules that keep comparisons valid

- Keep `splits/railsem19_seed0.json` fixed across training seeds. `train.seed`
  controls the training replicate, not the data partition filename.
- `rail_union` is the transfer space; `cityscapes19` is the standard reference
  space. Their mIoU values are not interchangeable.
- Mixed stages require `unified_head`, positive weights for every listed
  dataset, and explicit common-target evaluation because native validation uses
  the first data entry.
- `init_from: previous` loads the preceding stage's evaluated EMA weights when
  present, then creates a fresh optimizer/scheduler.
- The four custom-data curricula are templates, not runnable claims, until real
  indexed masks and group-safe splits exist.
- Change one variable at a time and keep a separate experiment name/output
  directory for every ablation.

## Evidence and unsupported limits

Config parsing and stage mechanics are tested, but a YAML file is not a quality
benchmark. The four runnable public-data controls now have one completed
[three-seed common-target case study](https://github.com/arianizadi/segmentary/blob/main/docs/findings.md);
its conclusions are limited to that exact model, split, schedules, and evaluator.
All custom-final curricula remain blocked. `per_stage_head` is not implemented;
mixed curricula require the existing unified head. See the linked pages before
turning a template into a scheduled job.

## Related documentation

- [Complete curriculum catalog](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/README.md)
- [Configuration guide](https://github.com/arianizadi/segmentary/blob/main/docs/guides/configuration.md)
- [Evaluation guide](https://github.com/arianizadi/segmentary/blob/main/docs/guides/evaluation-and-results.md)
- [Benchmark evidence](https://github.com/arianizadi/segmentary/blob/main/docs/benchmarks/README.md)
