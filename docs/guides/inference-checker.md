# Inspect images, ground truth, and predictions

Segmentary includes [Inference Checker](../../tools/inference-checker/README.md),
Arian's existing local viewer. You do not need a second repository or a GPU to
inspect saved predictions. The original sibling project is unchanged.

## One command to open a bundle

Install [Bun](https://bun.sh/) once. From the Segmentary checkout:

```bash
./scripts/inspect.sh /path/to/bundle
```

This installs the viewer's locked dependencies and opens a local server at
<http://127.0.0.1:3000>. Open that address in your browser; Ctrl-C stops it.
The first dependency installation needs network access. Image inspection uses
local files, with no analytics or remote fonts. The launcher disables Next.js
telemetry and binds to loopback. Use `PORT=3001 ./scripts/inspect.sh /path/to/bundle`
if port 3000 is occupied. Paths containing spaces are supported when quoted.

The viewer supports ground-truth-only bundles, one or many models, single-model
overlays, side-by-side comparisons, disagreement views, pixel hover labels,
and per-scene metrics. Use **Focus class** to isolate a defect such as mud-pumping,
**Overlay** to reveal the original image, and **Zoom** to magnify it. Scroll within
a zoomed image to pan. Display filters and zoom do not alter metrics.
Scene navigation shows original frame names, including nested dataset groups.

## Prepare a bundle from existing masks

If you already have a bundle from [segmentary-scene](scene-comparison.md), open
it directly. Otherwise package paired files with this helper. Only Pillow and
PyYAML are needed (`python -m pip install pillow pyyaml`); Segmentary's normal
environment already provides both.

```bash
python scripts/prepare_viewer_bundle.py \
  --images /datasets/my-data/images/val \
  --masks /datasets/my-data/masks/val \
  --taxonomy taxonomy/example/canonical.yaml \
  --prediction model-a=/results/model-a/predictions \
  --prediction model-b=/results/model-b/predictions \
  --out artifacts/my-review \
  --title "My validation comparison"

./scripts/inspect.sh artifacts/my-review
```

Omit both `--prediction` arguments to inspect annotations alone. Each prediction
argument is a unique `NAME=DIRECTORY`. Inputs can be nested: `group/frame.jpg`
requires `group/frame.png` in the ground-truth and every prediction directory.
Every supplied model must cover every image in this bundle; missing pairs fail
instead of quietly comparing different samples. Subset the inputs first if you
want a smaller comparison.

The taxonomy is a Segmentary `canonical.yaml` with contiguous IDs beginning at
zero. It must describe the IDs actually stored in the masks. For RTIS, use
`taxonomy/paul-test-rtis/canonical.yaml`; do not substitute RailSem19 labels.
Images retain native resolution. Palette PNGs are read as indices and rewritten
as plain 8-bit grayscale PNGs; RGB color masks are rejected. Unknown IDs, dimension
mismatches, and predictions that ignore labeled pixels fail validation. No model
is loaded, no inference runs, and no image is resized.

The output directory must be new. A successful bundle contains `config.json`,
scene folders, and `bundle-manifest.json` with source paths and hashes. Original
files stay unchanged; failed preparation removes its temporary output. Bundles
under `artifacts/` are ignored by Git. They may include sensitive or licensed
imagery and absolute source paths; review contents before sharing a bundle.

## Compatibility with the original tool

The bundled viewer retains the original commands:

```bash
cd tools/inference-checker
bun install --frozen-lockfile
bun run inspect -- /path/to/bundle
# Or use the original default public/inference_comparison directory:
bun run dev
```

`INFERENCE_CHECKER_BUNDLE_ROOT=/path/to/bundle bun run dev` still works.
`config.json` is preferred; legacy `rs19-config.json` remains supported. Existing
bundle files do not need conversion. External bundles are read in place and
must be immutable while the server runs; restart after changing their contents.
The viewer ships as source in this Git repository, not inside the Python wheel.

The bundled copy removes external analytics/fonts, fixes asynchronous mask races
and custom ignore-index handling, normalizes display masks to prevent PNG color
metadata from changing hover IDs, and supports keyboard class filtering. Canvas
components avoid redraws on unrelated hover state updates. Display-mask caching
is bounded to 16 entries / 16 MiB and invalidates when file metadata changes;
the original bounded bundle/statistics caches remain in place.

## Checks

```bash
cd tools/inference-checker
bun run test
bun run lint
bun run build
```

Python preparation tests: `python -m pytest tests/test_viewer_bundle.py`.
The viewer has its own CI workflow; normal Python checks still cover the exporter.

The viewer fits one viewport: image zoom, class lists, and the compact toolbar
scroll internally. On narrow screens, **Classes** opens a panel over the images.
Search the compact legend, or use **Isolate a class** to focus on mud-pumping.
**Reset view** restores all classes, 1× zoom, and the default overlay opacity.
In Compare and Diff modes, legend metrics and the footer describe the **right**
model. Help explains the metric denominators and displays supplied provenance.
