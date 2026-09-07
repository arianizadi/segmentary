# Inspect instance and panoptic predictions

The bundled inference checker has a dedicated object mode. It displays independent
instance masks, native panoptic segment IDs, boundaries, category names,
thing/stuff labels, and model-provided segment confidence. Ground-truth confidence
is explicitly unavailable. It never infers confidence from a hard mask.

## Prepare and open a review bundle

First use `segmentary-objects predict` to create predictions, as described in the
[instance/panoptic guide](instance-panoptic.md). Then run:

```bash
python -m segmentary.objects.viewer_bundle \
  --images /data/example/val/images \
  --annotations /data/example/annotations/instances_val.json \
  --predictions /runs/model-a/predictions.json \
  --predictions /runs/model-b/predictions.json \
  --out artifacts/object-review

./scripts/inspect.sh artifacts/object-review
```

For panoptic data, provide the COCO panoptic annotation JSON and add
`--panoptic-masks /data/example/annotations/panoptic_val`. Both prediction files
must be for the same task and ground-truth image set. One prediction is sufficient;
repeat `--predictions` to compare additional checkpoints through the selector.
The command requires Segmentary's normal environment and its `objects` extra
for polygon decoding. The browser itself needs only Bun, not Python or a GPU.

Prediction image IDs assigned during inference often differ from original COCO
IDs. This exporter joins images by their exact relative filenames, validates
category IDs/names/thing-stuff labels, dimensions, and image hashes when prediction
hashes are provided. It rejects missing/extra images rather than silently showing
an unmatched prediction as an empty result. To review a subset, provide a COCO
annotation file containing exactly that subset. Output must be a new directory;
publication uses a temporary sibling directory so an error does not leave a
partially valid bundle. Input data and previous bundles remain unchanged.

The bundle can be zipped and opened with the same viewer command on another
machine. It includes copies of the images and exact row-major foreground intervals
for every object. Overlapping instances remain independent; disconnected regions
belonging to one object retain one ID. COCO polygons and compressed/uncompressed
RLE are decoded with the same mask decoder used by the object data loader.
Panoptic RGB segment IDs are decoded without palette/color reinterpretation.

## Review controls

- **All segments:** GT on the left, selected model on the right. Colors distinguish
  local object IDs; the object list shows the semantic category and thing/stuff type.
- **Boundaries / IDs / Overlay:** control the outlines, captions, and translucent
  mask fills. Click a mask or a list row to isolate its exact foreground. Click
  the selected row again or **Reset view** to clear isolation. Original mask
  ordering affects only how overlapping fills are drawn, never the stored masks.
- **Zoom:** magnifies both views. Scrolling either pane synchronizes horizontal
  and vertical panning in the other. The page stays within one viewport; panes,
  the object list, and expanded help can scroll internally.
- **Search objects:** narrows the object list by category or ID. On narrow screens,
  the **Objects** button opens the compact sidebar.
- **Min confidence:** filters predictions and recomputes review diagnostics.
  Unknown confidence is retained. This is not a change to benchmark evaluation.

IDs are local to each image and layer. A prediction ID equal to a GT ID does not
mean the objects correspond. Panoptic stuff remains visible as segments but is
excluded from object miss/extra/merge/split counts.

## Exact diagnostic definitions

These views are interactive review heuristics, **not COCO AP or panoptic PQ**.

1. For non-crowd **things**, compute same-class mask IoU:
   `intersection_pixels / (GT_pixels + prediction_pixels - intersection_pixels)`.
2. Sort pairs with IoU at least 0.50 by descending IoU; ties use ascending GT then
   prediction ID. Greedily accept pairs whose two objects have not already matched.
3. **Missed things:** unmatched GT objects. **Extra things:** unmatched predictions
   after applying the confidence filter. Wrong-class predictions cannot match.
4. A mask-overlap link exists when intersection divided by the **smaller** mask
   area is at least 0.50. **Merge candidates:** a prediction links to at least two
   same-class GT objects. **Split candidates:** one GT links to at least two
   same-class predictions. The view highlights every participating mask on both
   sides. Flags can coexist with missed/extra counts.

Crowd annotations are visible in the all view and marked in the list, but excluded
from matching. Predictions covering crowd are **not** suppressed using COCO's
crowd rules. Merge/split flags can be caused by legitimate overlaps or ambiguous
labels; they do not establish that a model or annotation is wrong. Use
`segmentary-objects eval` for formal AP/PQ and the full benchmark reports.

Checkpoint SHA-256 from each prediction manifest appears in the expandable matching
rules panel. Confidence reflects the prediction export's segment-level score,
not pixel probabilities. No object tracking across images is implied.

## Bundle schema and limits

`config.json` adds `task: "instance"` or `"panoptic"`; old semantic bundles and the
standalone viewer's original commands remain supported. Each scene has an input
image, `scene.json`, and `objects.json` with native dimensions and layers. Each
object records `id`, contiguous `classId`, original `categoryId`, `isthing`,
`crowd`, nullable `score`, and sorted `[start, length]` foreground runs in row-major
order. Layers contain GT first, then models and their checkpoint hashes.

Compatibility `gt.png` and model PNGs are flattened previews for scene discovery.
The object renderer uses `objects.json`, and the semantic stats API rejects object
bundles so previews cannot accidentally be reported as evaluation labels.

Object masks load lazily per scene through the loopback-only server. Limits are
64 MiB per object JSON, 40 million pixels per scene, 32 layers, 5,000 objects per
layer, and four million foreground intervals across all layers. An additional
100-million interval-work bound rejects excessive pairwise matching before it
reaches the browser. Existing semantic
bundle limits still apply. Dense scenes near these limits can be slow: review
matching considers same-class GT/prediction pairs, and outlines traverse their
foreground pixels. Prepare smaller review subsets for large collections.
