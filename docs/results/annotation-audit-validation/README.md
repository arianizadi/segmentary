# Annotation audit validation

The audit reproduces the current RTIS conversion exactly and detects the injected integrity faults tested here. Its original overlap rules are noisy as an annotation-review queue: the new focus review finds broad mud labels that those rules missed. Review candidates require human interpretation; these results do not estimate annotation-error precision or recall.

## RTIS audit results

The local run audited all **307 images**, comprising **723,524,420 pixels**, with **zero audit errors** and **zero native-render/training-mask pixel mismatches**. The report records 307 matching source annotation hashes against the available sample manifest. The RTIS audit reuses the dataset converter, so agreement is not independent proof that every rasterization rule is correct. This confirms agreement with that manifest; historical provenance is only as strong as the manifest's hash history.

The original rules flag **218/307 images (71.01%)**. The improved queue retains those observations and separates them by use:

| Queue | Images | Meaning |
|---|---:|---|
| Integrity | 0 | Broken files, class IDs, provenance mismatches, or conversion mismatches |
| Focus class | 38 | Mud coverage or object-loss candidates |
| Other object loss | 128 | Non-background object-loss or empty-object candidates |
| Background / coverage context | 78 | Background loss or dominance observations |
| Provenance notices only | 0 | Missing historical hashes without a detected integrity failure |
| No current flags | 63 | No current heuristic selected the image |

These queue categories are exclusive and sum to 307. Focus priority supersedes lower-priority context, so these counts cannot be added to the old flagged-image count. **26 of the 38 focus candidates had no original flags.**

### What the old queue missed

**17 images have original mud coverage equal to 100% of the image. All are in the training split's `trackside-maintenance` scene.** Of these, **14/17 (82.35%) had no original flags**. Their source mud regions lost less than half their area, and their final mud coverage did not trigger the original 85% dominance rule.

The improved review selects source focus coverage of at least 98%, final focus coverage of at least 50%, and focus objects losing at least half their original class coverage. There are **17 source full-frame candidates** and **37 broad final-coverage candidates**; these sets overlap. These are transparent triage thresholds, not learned error probabilities.

The 14 previously unflagged full-frame cases are `trackside-maintenance/39`, `/40`, `/43`, `/45`, `/51`, `/55`, `/57`, `/59`, `/64`, `/67`, `/71`, `/79`, `/84`, and `/85`.

### Why overlaps are not automatically errors

There are **580 source objects** losing at least half their class coverage. **311/580 (53.62%)** belong to sky, terrain, or trackbed. **87 of the 218 originally flagged images** contain only those background-loss flags or dominance flags. Broad background polygons are often intentionally covered by later foreground geometry. These counts identify likely sources of review noise, not confirmed false positives.

Only **23/580 (3.97%)** of the loss-flagged objects have source area at most 256 pixels, so tiny-object filtering alone would not solve the queue's main problem. Same-class overlap is already excluded from the class-loss flags.

Cross-class overlap occurs at **297,193,365 distinct image pixels** across the audit, or **41.08%** of all audited pixels. This is a painting-history measurement, not an annotation-error rate. Per-event pixel counts can count a pixel more than once when successive layers repaint it.

## Verifiable examples and calculations

For image pixel count `N`, source class regions `R₁ … Rₖ`, and final class mask `F`:

```text
source coverage = |R₁ ∪ … ∪ Rₖ| / N
final coverage  = |F| / N
object class-loss fraction = |Rᵢ intersect (final class != object class)| / |Rᵢ|
```

The source union avoids counting overlapping same-class objects repeatedly.

| Sample | Source mud union / image pixels | Final mud pixels / image pixels | Review use |
|---|---|---|---|
| `trackside-maintenance/57` | 2,088,960 / 2,088,960 = 100% | 1,197,675 / 2,088,960 = 57.33% | Broad source coverage missed by the original queue |
| `trackside-maintenance/82` | 1,355,643 / 2,088,960 = 64.90% | 826,279 / 2,088,960 = 39.55% | Compare broad corridor labeling with class definition |
| `trackside-maintenance/9` | 806,717 / 2,088,960 = 38.62% | 784,187 / 2,088,960 = 37.54% | Inspect localized loss separately from whole-image coverage |
| `rural-overcast-cab-view/100` | 38,354 / 2,073,600 = 1.85% | 37,048 / 2,073,600 = 1.79% | Validation example with localized mud patches |

In `/9`, mud object `1723293987` loses **9,220 / 9,547 = 96.57%** to rail-raised object `1723293989`, leaving 327 pixels of its class. A large fraction alone cannot distinguish a geometry mistake from an intentionally visible rail. The sum of all source mud-object areas in this image is 812,314 pixels, while the correct union is 806,717: summation would double-count 5,597 pixels.

The difference between broad maintenance-view labels and localized cab-view labels warrants a class-definition review. The audit cannot infer from coverage alone whether the intended target is visible expelled mud, affected ballast, or a broader affected track region.

## Controlled integrity-fault validation

The validation harness modified disposable copies of `trackside-maintenance/57`. Current training images, masks, and source annotations were preserved.

| Case | Expected detection | Native/training mismatched pixels | Result |
|---|---|---:|---|
| Clean control | No integrity flags | 0 | Pass |
| Unknown class ID | Unknown ID 250 and render mismatch | 400 | Pass |
| Shifted labels | Render mismatch | 168,179 | Pass |
| All-void labels | Render mismatch and dominant void | 2,088,960 | Pass |
| Wrong mask dimensions | Audit error | Not computed | Pass |
| Changed packaged image | Packaged/source image mismatch | 0 | Pass |
| Reversed source order | Annotation hash change and render mismatch | 891,285 | Pass |

All **six injected fault cases** and the **one clean control** behaved as expected. This establishes detection for these specific faults on this sample. It does not establish sensitivity to all conversion bugs or semantic annotation mistakes. Reversing source order also produces ordinary object-loss flags; the integrity flags distinguish the detected source change.

## Reproduce and review

Follow the [annotation review guide](../../guides/annotation-review.md). The generated `index.html` provides a searchable queue, labeled comparisons, original flags, review notes, and a portable decisions export. Decisions do not edit labels. Approved corrections must create a separate dataset version.

Published machine-readable evidence: [RTIS review examples](rtis-review-evidence.json), [shared mask checks](rtis-mask-summary.json), and [controlled fault results](fault-validation.json).

The review page was checked in a real browser at 1440×1000 and 390×844: image loading, search/filter counts, saved verdict persistence after reload, JSON decision download, and no outer-page overflow. Inner panels scroll.

Local evidence files used for this report:

- `artifacts/rtis-audit-review-v3/report.json`
- `artifacts/rtis-audit-review-v3/review-summary.json`
- `artifacts/rtis-annotation-review-v2/report.json` for original flags
- `artifacts/annotation-audit-fault-validation/results.json`

No raw dataset images are committed with this report. Evidence file SHA-256 values:

```text
RTIS report: 704ef9a3aafe22f21aa78361389c842950a791a5c2875ea568525a702af2fa67
Fault validation: 201b3d971abeb319a66f112dc7c601abfa7bf11f436cca26c890574e7ef25ce2
```

## Cityscapes and RailSem19 comparison

The final CPU runs inspected **3,475 Cityscapes images** (2,975 train, 500 validation) and **8,500 RailSem19 images**. RailSem19 split lists select 4,000 images; another 4,500 downloaded images are reported separately as unassigned. Hidden Cityscapes test labels are excluded. All masks were measured at native resolution. No training jobs or dataset labels were changed.

The same `mask_stats` function supplies the shared measurements below. Dominance means a non-ignore class occupies at least 85% of **all** image pixels. Ignore coverage is pixel-weighted within each split.

| Dataset / split | Images | Dominance candidates | Ignore pixels (%) |
|---|---:|---:|---:|
| RTIS / train | 220 | 13 | 0.550 |
| RTIS / val | 37 | 1 | 0.124 |
| RTIS / test | 50 | 0 | 0.357 |
| Cityscapes / train | 2,975 | 0 | 11.472 |
| Cityscapes / val | 500 | 0 | 12.546 |
| RailSem19 / train | 3,000 | 7 | 3.352 |
| RailSem19 / val | 500 | 3 | 3.743 |
| RailSem19 / test | 500 | 1 | 3.433 |
| RailSem19 / unassigned | 4,500 | 7 | 3.577 |

**Every dataset had zero invalid-ID and all-ignore masks.** RTIS had zero audit errors; the reference runs also found zero image/mask or source/mask dimension mismatches and zero read/schema errors. These are integrity results, not a certification of semantic labels. Cityscapes marks several valid semantic classes as evaluation-ignored, while RTIS and RailSem19 use their void ID; ignore percentages are therefore not directly comparable quality scores.

### Overlap flags are strongly nonspecific

The object-loss rule flags **3,449 / 3,475 Cityscapes images = 99.25%**: 2,958 train and 491 validation. There are 37,247 individual objects losing at least half their class coverage. Ordinary painter-order occlusion is a plausible contributor. This near-universal flag rate demonstrates why an overlap flag cannot by itself be interpreted as an annotation error. It does not establish that every flagged object is correct.

### Exact rasterization differences need context

Cityscapes has **31,298,612 / 7,287,603,200 mismatching pixels = 0.4295%** between the current Pillow polygon reconstruction and released label PNGs. Every image has some mismatch, but **all mismatches lie within two pixels of a boundary in either map; zero occur farther inside regions**. This supports a rasterization-boundary explanation, without proving every boundary difference harmless. Thin objects or small errors can also fit inside this tolerance band. Raw exact mismatch counts remain available.

Independent verification also caught a bug in the new audit: translating polygon coordinates before drawing into a cropped canvas changed Pillow edge rounding. The fix draws original coordinates before cropping. A regression fixture reproduces the old discrepancy at pixel `(23, 41)`, and the corrected implementation matches an independent full-canvas renderer pixel-for-pixel on **20 real Cityscapes images**. The complete Cityscapes audit was rerun after this fix. See [renderer verification](cityscapes-renderer-verification.json).

RailSem19 has sparse source polygons, boxes and polylines, whereas its dense masks include additional label generation. Full source-to-dense equality and overlap-loss checks are **unavailable**, represented by `null`; they are not reported as zero failures. Its 18 dominance candidates across 8,500 images are coverage observations, not an annotation-error count: nine construction, eight vegetation, and one sky. [Reference review samples](reference-review-samples.json) provide all 18 cases and three Cityscapes controls with measurements and hashes. In Cityscapes `aachen_000000_000019`, the sky polygon loses 296,463 / 334,922 = 88.52% of its class coverage, illustrating why a large sky-overwrite fraction alone cannot certify a sky annotation problem.

### What this validation establishes

The audit is useful for detecting the tested integrity faults, tracing class coverage back to source geometry, and selecting images for review. The original overlap/dominance flags alone make a poor error detector: they select nearly all Cityscapes images and miss broad source mud regions. The improved focus queue addresses the demonstrated RTIS blind spot and preserves raw evidence. Estimating semantic-error precision or recall still requires independently reviewed labels, including randomly selected unflagged images; no such performance estimate is claimed here.

Published full class-coverage distributions, split totals, code hashes and source references: [Cityscapes](cityscapes-summary.json), [RailSem19](railsem19-summary.json), [RTIS common checks](rtis-mask-summary.json). Reproduce using the [reference audit recipes](../../guides/reference-dataset-audit.md). Local per-image evidence is in `artifacts/reference-audit/cityscapes-v4/images.jsonl` and `artifacts/reference-audit/railsem19-v4/images.jsonl`; it includes source/mask hashes without publishing raw photographs.

## Code validation

The repository test suite excluding `slow` and `gpu` passed. The targeted audit suite passed 33 tests, including independent pixel fixtures, source union counting, immutable corrections, review exports, boundary classification, and the Cityscapes coordinate-rounding regression. Ruff lint/format and the repository mypy gate passed; the four new standalone modules also passed an explicit mypy check. These checks and CPU audits did not change the running campaign or its dataset.
