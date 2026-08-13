# Contributing to Segmentary

Thanks for improving the project. Segmentary is research software: a change is not
finished merely because it runs; it must preserve the meaning and provenance of
the reported experiment.

Read these first:

1. [`docs/tutorials/core-concepts.md`](docs/tutorials/core-concepts.md) for the
   scientific contracts;
2. [`docs/reference/project-layout.md`](docs/reference/project-layout.md) for
   extension points.

## Development setup

From a Python 3.11 environment with the appropriate platform PyTorch installed:

```bash
git clone https://github.com/arianizadi/segmentary.git
cd segmentary
export PYTHONPATH="$PWD/src"
python -m pip install -e '.[dev]'
```

Do not replace a working PyTorch build casually. Select it for the actual
CPU/GPU, driver, and operating system; the bundled reproduction profile has its
own tested pin.

## Before opening a change

```bash
python -m pytest -q
ruff check src tests scripts
ruff format --check src tests scripts
python -m pip check
git diff --check
```

Run real-data/GPU tests when the change touches data, model, curriculum,
evaluation, EMA, distributed training, or export. State explicitly when hardware
or Docker daemon access prevents a check.

## Test philosophy

Write a case where the wrong implementation produces a different checkable
answer. Good examples:

- an ignored pixel whose logit changes but loss/gradient/metric must not;
- a stage-two tensor compared exactly with the stage-one EMA checkpoint;
- a mixed batch whose samples have different active masks;
- a boundary result compared with independent SciPy morphology;
- a table input with a duplicate seed or changed learning rate that must fail.

Do not weaken an assertion to make a failure green. Determine whether the code or
expectation is wrong, fix that, and preserve the reason in the test/comment.

## Scientific safety rules

- Never silently fall back to random weights, a different dataset/split, raw
  instead of EMA, crops instead of native validation, or TTA instead of baseline.
- Unknown config keys, mapping ids, checkpoint keys, freeze patterns, and LoRA
  targets must fail loudly.
- Keep experiment lists explicit. A configured dataset import path must resolve
  to a `SegDataset` subclass, stay versioned with the run, and have contract
  tests; it is an extension point, not a remote-code fallback.
- Do not hand-copy table values. Generate from validated `results.json` records.
- A multi-seed group must differ only by seed and share clean git provenance.
- Disclose changed compute budgets, effective batch, label space, objective, and
  checkpoint selection.
- Split video-derived custom data by run/sequence, never by frame.

## Files and credentials

Never commit datasets, licensed frames, checkpoints, exported engines, Hugging
Face tokens, Cityscapes credentials, cookies, `.env`, or other secrets. Large
artifacts belong in an appropriate data/artifact store, not Git.

## Documentation standard

When adding a setting or public workflow:

- update the relevant tutorial/guide/reference;
- explain the default, when to use it, benefits, costs, and unsafe combinations;
- include a copyable command or YAML snippet;
- distinguish verified behavior from planned/blocked behavior;
- keep public paths portable and label reproduction-profile paths explicitly.

## Scope of public compatibility

The command-line tools, typed config objects, taxonomy loaders, model contract,
result schema, and documented functions in `docs/reference/python-api.md` are the
intended integration surface for version 0.1. Other helpers may change while the
library evolves. If an internal helper becomes useful externally, add a
test and documentation before treating it as stable.
