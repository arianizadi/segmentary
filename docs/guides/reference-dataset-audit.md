# Compare annotation audits across datasets

Run these read-only audits against the original downloaded datasets. Outputs must be outside the dataset; the command refuses to overwrite an existing output directory.

```bash
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python scripts/audit_reference_datasets.py \
  --dataset cityscapes --root /path/to/cityscapes --out artifacts/audit-cityscapes
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 python scripts/audit_reference_datasets.py \
  --dataset railsem19 --root /path/to/railsem19 --out artifacts/audit-railsem19
```

The commands need NumPy and Pillow, run on CPU, and do not load models or touch training jobs. Add `--limit 10` for a smoke check; this is marked as limited in the summary and is not a representative sample. Cityscapes scans `gtFine/train` and `gtFine/val`; hidden test annotations are excluded. RailSem19 scans available `uint8` masks and takes membership from this checkout's `splits/train.txt`, `val.txt`, and `test.txt`. The download directory `rs19_val` is the release name, **not** our validation split.

Outputs:

- `summary.json`: split denominators, flag counts, class prevalence and coverage distributions, boundary density and geometry totals.
- `images.jsonl`: every image's measurements, relative source paths, mask/source SHA-256 hashes, and flags.
- `review.json`: image keys and reasons to inspect. A flag is a review suggestion, not a confirmed annotation defect.

No raw images are exported. Keep source images within the access terms of each dataset.

## Shared measurements

Class coverage is `class pixels / all image pixels`. Ignored pixels stay in this denominator, but ignored classes cannot trigger the dominant-class flag. A class covering at least 85% triggers review. The summary gives both all-image quantiles (including absent classes as zero) and present-image quantiles. Do not compare numeric IDs across datasets; each uses its native taxonomy.

Other checks include unknown class IDs, all-ignore masks, readability, mask/image dimensions and source dimensions. Boundary density counts unequal horizontal and vertical neighboring labels divided by the number of such neighbor pairs: `[(H-1)W + H(W-1)]`. It describes label complexity, including ignore boundaries; it does not establish contour correctness.

## Geometry comparisons have different scopes

Cityscapes uses the [official label ID taxonomy](https://github.com/mcordts/cityscapesScripts/blob/master/cityscapesscripts/helpers/labels.py) and [official polygon rendering rules](https://github.com/mcordts/cityscapesScripts/blob/master/cityscapesscripts/preparation/json2labelImg.py): source order, Pillow polygon filling, skipped deleted objects and negative-ID license plates, and group-name fallback. The audit compares that reconstruction against `labelIds` at native resolution. Polygon coordinates stay in the original canvas until after rasterization: translating vertices into a crop can change Pillow edge rounding. Cross-class overlap counts unique image pixels touched by a later different-class polygon. Per-object class loss compares a source polygon against the final reconstructed class, not object ownership; same-class overlap is not class loss.

Cityscapes ignore IDs are all official classes with `ignoreInEval=True`; RTIS uses its configured ignore ID and RailSem19 uses 255. This difference prevents raw ignore coverage from serving as a dataset quality ranking.

RailSem19 includes sparse boxes, polygons and polylines in `jsons`. Its supplied `readme.txt` explicitly describes dense masks as a mixture of geometry rasterization and weakly supervised labels. Those sparse annotations do **not** reconstruct the full dense training mask. The audit records source geometry types and dimensions; a full-render equality test is reported as unavailable, never as zero errors. The provided `example-vis.py` is a visualization of sparse geometry, not a complete dense-label converter.

## Interpreting a comparison

Compare the shared mask checks separately from source geometry checks. Overlapping polygons and more than 50% object class loss can be intentional painter-order occlusion, including sky behind vegetation. These cannot be used as automatic error labels. A Cityscapes render mismatch is a reproducible source-to-mask discrepancy; even an exact match does not prove that an annotator chose the correct region or class. The audit separates differences within two pixels of either mask's semantic boundary (Chebyshev distance) from interior differences beyond that band. Boundary-only differences can be consistent with rasterization conventions and are not automatically annotation errors. The two pixel tolerance is an explicit diagnostic choice, not proof that every edge is correct. Counts from unavailable geometry checks are `null`, with a separate checked-image denominator, rather than artificial zeros.

Review images with domain context before changing labels. Reference audits never edit datasets. Apply approved RTIS corrections through the immutable dataset-version workflow in [Annotation audit](annotation-audit.md), retaining the original data and reviewer decisions.

The Cityscapes report separates exact mismatches within a two-pixel Chebyshev neighborhood of either mask's boundary from mismatches farther inside regions. Boundary-only differences can reflect rasterization conventions; they are retained as discrepancies, not certified harmless. Thin or small semantic errors can also fall entirely inside this band. The independent native-canvas rendering check and regression fixture preserve original polygon coordinates before cropping.

Use the same mask measurements on packaged RTIS:

```bash
python -m scripts.summarize_rtis_masks --dataset data/paul-test-rtis \
  --out artifacts/rtis-mask-summary.json \
  --audit-report artifacts/rtis-audit-review-v3/report.json
```

See the [measured comparison and validation findings](../results/annotation-audit-validation/README.md).
