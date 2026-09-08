# Annotation audit and reviewed dataset versions

Audit the **native exports and the exact semantic masks used for training** before correcting labels. This workflow supports the packaged RTIS directory layout produced by `prepare_rtis.py` and `package_rtis.py`; it is not a general COCO object audit. It does not modify a dataset or start training.

From the repository root, using the installed Segmentary Python environment:

```bash
python -m scripts.audit_annotations audit \
  --dataset /data/datasets/paul-test-rtis \
  --source-root /data/exports/rtis \
  --out artifacts/rtis-annotation-review \
  --focus-class mud-pumping
```

`--source-root` is optional when `audit/samples.json` still points to accessible native files. When supplied, it relocates paths under `supervisely/` and `cvat/` into that directory. Keep original exports: packaged semantic labels alone cannot recover overwritten polygons or separate overlapping objects.

Required packaged inputs are `classes.json`, `audit/samples.json`, `masks/<split>/<key>.png`, and matching `images/<split>/<key>.<extension>`. Missing packaged images are audit errors. Legacy source annotations without a recorded packaging hash have provenance status `unavailable`; the current hash cannot establish that they were unchanged since packaging. Original Supervisely project annotations/images or CVAT image XML/images must be available. Supervisely polygon holes and alpha bitmaps, CVAT polygons and row-major RLE masks, mixed geometry, and explicit void regions follow the existing RTIS converter. Supervisely list order and ascending CVAT `z_order` determine overlap precedence. There is no automatic assumption that sky is behind vegetation.

## Review outputs

- `report.json`: every image, source and training-mask file hashes, class pixel counts, per-object source area and remaining class coverage, overwrite events, and flags.
- `review.csv`: only flagged images, with split, key, reason, and preview path.
- `index.html`, `review-ranked.csv`, `review-summary.json`: [focused human review](annotation-review.md), with saved verdicts and exported decisions.
- `previews/<split>/<key>.jpg`: labeled 2×2 panels. With `--focus-class`, these show the original, source class union, final training class, and lost/added class pixels (magenta/cyan). Without a focus class, the panels are: original image, native rendered labels, actual training labels, and overlap/mismatch diagnostics. Yellow marks any overlap, orange cross-class overwrites, and magenta native/training disagreements. Exact counts are computed at original resolution; contact sheets may be resized.

An audit exits nonzero if any image could not be inspected. Errors are recorded in the review list so inaccessible or malformed sources cannot silently count as clean images.

Default heuristic flags identify a class occupying at least 85% of an image, an object losing at least 50% of its pixels to different final classes, empty objects, unknown training class IDs, source annotation or image hash changes, source/packaged image disagreements, unavailable legacy annotation hashes, and differences between the native render and training mask. Adjust thresholds with `--dominant-coverage 0.9 --overwrite-fraction 0.6`. These are review prompts, not automatic annotation verdicts. Legitimate broad terrain masks can trigger coverage warnings. Small original sky polygons still require human inspection; geometric auditing cannot infer their correct boundary from the photograph.

For object region A and final native label map L, class-loss fraction is `count(A & (L != object_class)) / count(A)`. Same-class overpainting counts as object overwrite but not class loss. An explicit void shape is retained as a shape and can overwrite another class. Uncovered source pixels are reported separately from annotated void. Event counts refer to successive overwrite operations, so one pixel can participate in multiple events; the image overlap counts are unique pixel counts.

## Correct through a new version

Make replacement **single-channel integer class-ID PNGs**, using the same dimensions and taxonomy as the original masks. Review them manually. Do not use colored visualization PNGs as training masks.

Create a corrections JSON file such as:

```json
{
  "version": "paul-test-rtis-v2",
  "reviewer": "your-name",
  "corrections": [
    {
      "split": "val",
      "key": "rural-overcast-cab-view/92",
      "expected_mask_sha256": "COPY mask_file_sha256 FROM report.json",
      "replacement_mask": "reviewed-masks/92.png",
      "reason": "Manually reviewed sky boundary against the original image"
    }
  ]
}
```

`expected_mask_sha256` hashes the PNG file bytes, not the decoded array. Relative replacement paths resolve against the corrections JSON directory.

```bash
python -m scripts.audit_annotations version \
  --dataset /data/datasets/paul-test-rtis \
  --corrections reviewed-corrections.json \
  --out /data/datasets/paul-test-rtis-v2
```

The version operation validates every correction before making a new independent copy. It refuses an existing output, nested parent/output paths, symlinks, duplicate or unknown samples, stale mask hashes, invalid classes, and shape changes. It preserves the parent dataset and split assignments, updates per-image mask hashes/counts, and records the reviewer, reasons, changed file hashes, and every parent file hash in `dataset-version.json`. Creation uses a temporary sibling directory followed by rename, so failed creation does not expose a partial output dataset.

Old previews and aggregate CSV/summary files are archived under `audit/parent-version-artifacts/` because they no longer describe the new masks. Regenerate statistics and previews before using the new version for a new experiment. Original annotations remain available as provenance; auditing the corrected dataset against unchanged native exports will intentionally flag the reviewed differences. No source annotations are silently rewritten, no inferred corrections are applied, and current training paths stay unchanged.

Keep the original held-out test version for existing comparisons. If you correct validation or test labels, record the dataset version in every subsequent evaluation and re-evaluate compared models consistently; scores across different label versions are not directly comparable.

## Verification

```bash
python -m pytest tests/test_annotation_audit.py tests/test_prepare_rtis.py -q
```

Tests use independently specified pixels to check cross-class overlap, same-class overwrite, explicit void, CVAT z-order and RLE, native/training agreement, changed source provenance, immutable version creation, split preservation, stale derived-artifact handling, and refusal of unsafe corrections. They do not establish that a human-reviewed label is semantically correct.

## Audit validation and reference datasets

See the [Cityscapes/RailSem19 recipes](reference-dataset-audit.md). Run controlled integrity faults against disposable copies of a real RTIS sample:

```bash
python -m scripts.validate_annotation_audit --dataset data/paul-test-rtis \
  --out artifacts/annotation-audit-fault-validation
```

The unchanged control must pass, and each injected fault must produce its expected flag. This verifies integrity checks, not semantic label correctness or the precision of review heuristics.
