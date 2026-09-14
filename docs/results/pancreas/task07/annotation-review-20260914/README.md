# Task07 and PanTS annotation review

The visual concern is reasonable: in several reviewed scans, the mass contour lies within or directly against pancreatic tissue and its exact boundary is difficult to distinguish on the displayed CT. That is different from proving that an annotation is incorrect or the task impossible. We preserved the original labels and made a review set for the radiology mentor.

## What was actually reviewed

On 2026-09-14 we loaded native CT and reference masks for six Task07 **training** cases spanning mass-volume quantiles (minimum, 10th, 25th, median, 75th, maximum) and the first six available positive PanTS training cases outside the known artifact exclusions. This is a deliberately small exploratory sample, not a random estimate of dataset quality. The reserved test payloads were not opened.

All 12 selected image/mask pairs had matching shapes and affines within an absolute tolerance of 0.0001. We rendered and visually inspected axial, coronal and sagittal views, with raw CT on the left and cyan pancreas/magenta mass contours on the right. Display used canonical RAS orientation, physical aspect ratio and the same -100 to 240 HU window. These are selected planes, not a complete diagnostic review of every slice or contrast phase.

[Measured properties](measurements.md) and [sanitized evidence](summary.json) are retained here. Full CT panels, native file paths, file hashes, and the audit script are on HDRFS, outside Git:

```text
/data/izadia1/projects/segmentary-annotation-review-20260914/
  report.json
  task07-train-01.png ... task07-train-06.png
  pants-train-01.png ... pants-train-06.png
/data/izadia1/projects/annotation_review_20260914.py
```

## Findings and interpretation

**Label format explains some apparent inconsistency.** Task07 is a single categorical volume: 0 background, 1 pancreas, 2 mass. A voxel cannot simultaneously equal 1 and 2. Thus the intersection of these two masks is necessarily zero, even when the mass is anatomically inside the gland. Our whole-pancreas metric uses labels 1 OR 2. PanTS instead supplies independent binary pancreas and pancreatic-lesion masks. In the six reviewed PanTS cases, 29.26% to 100% of the lesion voxels overlap the pancreas mask. Our PanTS adapter assigns lesion precedence when making a single categorical training target, while retaining the originals. Neither format alone establishes a bad boundary.

**Appearance and scale vary substantially.** Task07 review cases 01-03 have boundaries that are less conspicuous on these views than cases 04-05. Case 01 contains only about 0.413 mL of annotated mass. Case 06 is an extreme 732.388 mL annotation whose scale and relationship to the organ deserve a separate radiologist check. A large extent is a review trigger, not proof of an error or a diagnosis. PanTS case 02 has a subtle boundary on the displayed window; case 04 has two disconnected lesion components, with only 29.26% of the lesion mask inside the separately drawn pancreas mask. Prioritize both for assessment of lesion extent and annotation convention.

**Thick slices make boundaries less precise in the side views.** Selected Task07 scans have 2.5 or 5 mm native slice spacing, and one PanTS example has 7.5 mm. The blocky coronal/sagittal appearance is visible in the original voxel sampling. Interpolation to finer spacing cannot recover anatomy that was never sampled. This is relevant to the finer-resolution experiment: it improves in-plane sampling relative to our existing preprocessing, while retaining 2.5 mm through-plane spacing.

**PanTS has documented annotation issues, and our intake already quarantines nine cases.** In [issue 12](https://github.com/MrGiovanni/PanTS/issues/12), the maintainer's [radiologist-reviewed response](https://github.com/MrGiovanni/PanTS/issues/12#issuecomment-4538401573) identifies accidental tiny marks in normal cases. We checked our release and intake report: all nine named cases are already excluded from training/evaluation manifests. All nine still have nonempty raw lesion files in this pinned download. One local mask has 166 nonzero voxels although the issue originally listed seven, so the exact raw files cannot be assumed identical to the reporter's version. We retain the exclusion and hashes rather than silently rewriting the downloaded labels.

[Issue 4](https://github.com/MrGiovanni/PanTS/issues/4) also reports disagreements between metadata and masks and other geometric/annotation inconsistencies. Those reports warrant intake checks; they are not evidence that every questioned label is clinically wrong. PanTS covers broader lesion and anatomy targets than a single confirmed-PDAC task; consult its [paper](https://arxiv.org/abs/2507.01291) before aligning disease labels.

## Questions for the radiology mentor

1. For review cases Task07-01/02/03 and PanTS-02/04, is the contour supported by the available scan, or does it depend on another phase, MRI, pathology, or clinical knowledge unavailable to our model?
2. Should the target include cystic components, necrosis, ductal change or extension beyond the gland? Which structures should be excluded? Confirm this separately for each dataset.
3. Is the extreme Task07-06 label appropriate, and do the two PanTS-04 components represent separate lesions or an annotation convention?
4. Can a second reader independently annotate a small training-only subset before seeing the reference contour? Measure reader-to-reader Dice and disagreement locations, then adjudicate; do not treat one reader's disagreement as automatic ground truth.
5. Which uncertainties should be retained as difficult cases, flagged for sensitivity analysis, or corrected with documented evidence?

Do not delete low-Dice or visually subtle cases because the model struggles with them. If a correction is warranted, preserve original labels, record reviewer and reason, version the revised dataset, and rerun the affected protocol under a new dataset identity. Blinded review should precede model-error-based exclusions.

The current evidence supports **a focused annotation audit plus controlled training diagnostics**. It does not show that annotation quality explains our performance gap to the [official benchmark](../official-benchmark-20260914/README.md).
