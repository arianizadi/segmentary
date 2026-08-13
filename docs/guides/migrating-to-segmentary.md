# Migrating a pre-release project to Segmentary

Segmentary is the public name of the pre-release research harness formerly
called Railyard. This is a coordinated namespace change, not a new training
method: model, data, taxonomy, objective, checkpoint, metric, and result-record
contracts are otherwise unchanged.

## Rename map

| Before the public release | Segmentary |
|---|---|
| `import railyard` | `import segmentary` |
| `python -m railyard.train` | `python -m segmentary.train` |
| `railyard-train` | `segmentary-train` |
| any other `railyard-*` command | the matching `segmentary-*` command |
| `RAILYARD_*` test/site variables | `SEGMENTARY_*` |
| `share/railyard/...` | `share/segmentary/...` |
| `[tool.railyard.install]` | `[tool.segmentary.install]` |
| `github.com/arianizadi/railyard` | `github.com/arianizadi/segmentary` |

The ten public commands retain the same suffixes: `init`, `verify`, `overfit`,
`train`, `eval`, `export`, `make-split`, `table`, `models`, and `progress`.

## Why there is no old import alias

The old distribution name is already owned on public PyPI by an unrelated
project. Segmentary therefore does not install a second top-level package or
console-script namespace under that name. An alias could shadow the unrelated
package and make an environment's behavior depend on installation order.

Update imports and commands explicitly. This also makes provenance honest: new
result records report the `segmentary` distribution rather than appearing to
use the unrelated package.

## Existing records and checkpoints

JSON result records remain ordinary schema-compatible data. Their old package
keys, command strings, and evidence-kind names are historical provenance and
should not be rewritten. `segmentary-table` can consume valid old result records
because aggregation depends on their schema, config, normalization, seed, and
metric fields—not the CLI spelling that created them.

Old Python-pickled Lightning checkpoints may embed the pre-release module path.
Keep the frozen private research environment for replaying those artifacts; do
not install a public namespace shim. New Segmentary checkpoints use the new
module path. Model state dictionaries without pickled Python objects remain
portable when their architecture/config matches.

The live dashboard can inspect a pre-rename campaign because it reads status and
TensorBoard files as text. Pass the actual old session prefix explicitly:

```bash
segmentary-progress runs/my_campaign --tmux-prefix railyard-m5
```

## Recommended migration procedure

1. Commit the existing experiment configs and results before changing names.
2. Install Segmentary in a fresh Python 3.11 environment.
3. Replace imports, commands, environment variables, and installed resource
   paths using the table above.
4. Run `segmentary-train ... --print-config` and compare the resolved experiment
   semantics, not the package-name strings.
5. Run `segmentary-verify` and a tiny `segmentary-overfit` check before resuming
   expensive training.
6. Write new runs to a new output directory so old and new provenance remain
   distinguishable.
