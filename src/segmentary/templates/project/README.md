# My Segmentary project

This starter uses a generic paired-folder dataset:

```text
data/
  images/train/example.jpg
  images/val/example.jpg
  masks/train/example.png
  masks/val/example.png
```

Masks must be single-channel integer images. Edit the canonical class list and
native-id mapping under `taxonomy/example/`, then edit `experiment.yaml`.

Initialize and commit this project before training so each result records clean,
portable Git provenance. The starter `.gitignore` excludes data, runs,
checkpoints, debug overlays, and `resolved.json`:

```bash
git init
git add .
git commit -m "Configure first Segmentary experiment"
```

Validate the merged configuration without opening a model or dataset:

```bash
segmentary-train base.yaml model.yaml experiment.yaml --print-config
```

Verify real masks and overlays, then run the tiny memorization check:

```bash
segmentary-verify --dataset my_dataset --loader folder --mapping my_dataset \
  --root data --space example --taxonomy taxonomy --crop 512 512
segmentary-overfit base.yaml model.yaml experiment.yaml --images 8 --device cuda:0
```

See the main Segmentary documentation for training, evaluation, model choices,
metric interpretation, and advanced settings.
