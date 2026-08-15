# Export a scene for inference-checker

Use `segmentary-scene` when a metric difference needs a pixel-level explanation.
It exports one real validation frame, its canonical ground truth, and one model
prediction without introducing a second preprocessing or inference path.

The key safety rule is that the viewer must color **canonical** IDs. RailSem19's
native class 3 is `tram-track`, while canonical `rail_union` class 3 is `fence`.
Copying the dataset's native `rs19-config.json` beside canonical predictions
therefore produces plausible-looking but false colors. This command generates
`config.json` from Segmentary's loaded `LabelSpace`, including every canonical
ID, name, RGB color, active/evaluate flag, thin-class list, and ignore index.

## Export two checkpoints onto one frame

Run once per checkpoint with the same output root and frame key. Choose distinct,
filesystem-safe names; each becomes both the display identity and PNG filename.

```bash
segmentary-scene \
  PATH/TO/RAIL_ONLY_RESOLVED.yaml \
  --ckpt PATH/TO/RAIL_ONLY/best.ckpt --ema \
  --name eomt-dinov3-rail-only \
  --dataset railsem19 --root /datasets/railsem19 \
  --mapping railsem19 --split val \
  --split-file /workspace/segmentary/splits/railsem19_seed0.json \
  --frame-key rs04890 --device cuda:0 \
  --out /artifacts/empty-canonical-comparison

segmentary-scene \
  PATH/TO/CITY_TO_RAIL_RESOLVED.yaml \
  --ckpt PATH/TO/CITY_TO_RAIL/best.ckpt --ema \
  --name eomt-dinov3-city-to-rail \
  --dataset railsem19 --root /datasets/railsem19 \
  --mapping railsem19 --split val \
  --split-file /workspace/segmentary/splits/railsem19_seed0.json \
  --frame-key rs04890 --device cuda:0 \
  --out /artifacts/empty-canonical-comparison
```

Prefer a run's recorded/resolved YAML when available, as above. Otherwise pass
the same base, model, and curriculum layers used for training, in the same order.
The config must build the checkpoint's exact architecture and canonical class count.
`--ema` fails if the checkpoint has no EMA state; omitting it loads raw weights.

## Artifact contract

The example above creates:

```text
empty-canonical-comparison/
├── config.json
└── rs04890/
    ├── input.png
    ├── gt.png
    ├── eomt-dinov3-rail-only.png
    ├── eomt-dinov3-city-to-rail.png
    └── scene.json
```

- `input.png` is native-resolution RGB.
- `gt.png` is an 8-bit grayscale canonical index mask and may contain ignore ID
  255.
- Every named prediction is an 8-bit grayscale canonical index mask. Predictions
  may contain only IDs `0..num_classes-1`.
- A scene contains exactly one `input.jpg`, `input.jpeg`, `input.png`, or
  `input.webp`; a second input is rejected instead of being silently preferred.
- `config.json` is the dataset-level canonical display contract.
- `scene.json` records frame/dataset/split identity plus, per prediction,
  checkpoint SHA-256, merged and source-config hashes, raw/EMA selection,
  Segmentary Git provenance, input normalization, native resolution, window,
  stride, task, threshold, and artifact hashes.

Predictions placed in one scene must use the same task, whole/sliding policy,
window, stride, TTA state, threshold, native resolution, and autocast mode.
Model-specific normalization and raw/EMA selection remain recorded per prediction
but are not mistaken for shared settings. Put protocol variants in separate
canonical output roots.

PNG masks are written as index images and round-trip exactly; no palette,
gamma, sRGB, or ICC color-management chunks reinterpret their bytes. Do not
convert them to RGB before giving them to the viewer.

## Repository hygiene

Generated scenes can contain licensed datasets and large binary predictions.
The repository's `scene_exports/` staging directory is ignored, and
inference-checker should import this bundle into a new canonical artifact root.
Never point this command at an older viewer root containing `rs19-config.json` or
scenes without Segmentary `scene.json`: those artifacts use RailSem native IDs,
whose ordering differs from canonical `rail_union`. The exporter rejects that
mixture. Commit only an explicitly approved small example whose redistribution
terms are known. Check `git status --short` before every push.
