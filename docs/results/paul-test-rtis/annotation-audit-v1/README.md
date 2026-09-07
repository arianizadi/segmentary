# RTIS native annotation audit

All 307 packaged training/validation/test images were audited against their original native annotations. **Every final training-mask pixel matches the native render.** This establishes conversion consistency; it does not establish that the annotations themselves are correct.

| Split | Images | Flagged for review | Native/training mismatch pixels | Cross-class overlap pixels |
| --- | ---: | ---: | ---: | ---: |
| train | 220 | 154 | 0 | 199,717,664 |
| val | 37 | 28 | 0 | 35,129,546 |
| test | 50 | 36 | 0 | 62,346,155 |

218 images have one or more heuristic review flags: 580 objects lose at least half their original pixels to different final classes, and 14 images have a class covering at least 85% of the image. All 307 images contain cross-class overlap. These conditions can be intentional background/foreground annotation layering; they are not 218 proven annotation errors. The audit had zero processing errors. A separate file-hash check verified that all 307 original images match their packaged training images and recorded source hashes.

All retained packaged samples use Supervisely annotations. CVAT mixed polygon/RLE and z-order support is tested separately with pixel fixtures; this real audit does not claim that retained CVAT primary samples were inspected. Excluded source duplicates are outside this packaged-image audit.

## Class coverage and overwritten objects

| Class | Source objects | Objects losing at least half | Train pixels | Val pixels | Test pixels |
| --- | ---: | ---: | ---: | ---: | ---: |
| person | 61 | 0 | 636,679 | 0 | 3,937 |
| truck | 55 | 1 | 1,031,666 | 0 | 451,019 |
| rail-track | 430 | 96 | 25,162,999 | 6,323,197 | 3,974,249 |
| vegetation-overgrowth | 1426 | 21 | 4,544,214 | 5,901,821 | 632,785 |
| car | 111 | 6 | 164,279 | 29,664 | 192,532 |
| on-rails | 56 | 0 | 6,246,688 | 0 | 324,597 |
| traffic-sign | 229 | 3 | 240,565 | 13,285 | 218,995 |
| road | 251 | 32 | 6,369,785 | 1,048,831 | 4,610,899 |
| sidewalk | 252 | 19 | 8,013,607 | 1,297,367 | 1,861,703 |
| construction | 999 | 42 | 27,996,895 | 311,585 | 6,871,035 |
| tram-track | 66 | 3 | 963,407 | 56,179 | 554,352 |
| pole | 2413 | 15 | 7,355,053 | 628,038 | 2,534,310 |
| traffic-light | 100 | 1 | 227,240 | 19,510 | 70,024 |
| mud-pumping | 333 | 1 | 63,625,696 | 1,226,250 | 346,535 |
| fence | 325 | 4 | 8,105,416 | 265,137 | 4,247,202 |
| terrain | 848 | 110 | 139,253,931 | 39,239,306 | 81,487,727 |
| sky | 297 | 65 | 82,738,307 | 19,121,606 | 40,520,742 |
| rail-embedded | 120 | 3 | 201,621 | 16,799 | 175,359 |
| rail-raised | 1200 | 20 | 22,285,496 | 2,969,797 | 2,166,233 |
| trackbed | 376 | 136 | 51,924,344 | 10,643,081 | 11,767,671 |
| standing-water | 148 | 1 | 8,653,646 | 95,802 | 2,284,109 |

Ignore/void pixels: train 2,576,486; validation 111,145; test 591,985 (reported separately from trainable classes).

## Reproduced sky example

`rural-overcast-cab-view/92` contains an original sky polygon with 25,132 pixels. Later source geometry overwrites 16,421 of those pixels, leaving 8,711 sky pixels.

`16,421 / 25,132 = 0.6533901003`, or **65.339% sky class loss**. The 1,920 × 1,088 image contains 2,088,960 pixels, so retained sky coverage is `8,711 / 2,088,960 = 0.417002%`. Terrain occupies 1,899,271 pixels, or `90.919453%` of the image.

This confirms the earlier overlap finding in the actual masks. The unusually small original sky polygon also needs human review against the photograph. Changing display overlay order cannot repair the flattened training labels. No labels or split assignments were changed.

## Definitions and reproducibility

- Object class-loss fraction: `count(original_object_mask AND final_native_class != object_class) / count(original_object_mask)`.
- Image cross-class overlap count: number of distinct pixels painted over by a different class at any source-rendering step.
- Overwrite event totals in JSON count successive operations; the same pixel may contribute more than once. Source-object pixel totals also count overlaps repeatedly.
- Class pixel counts in the table are disjoint final semantic-mask pixels, accumulated by split.
- Native/training mismatch count: `count(rendered_native_mask != actual_training_mask)` at the original resolution.

The [machine-readable summary](summary.json) contains exact counts, all per-image flags, flagged object measurements, class-pair overwrite totals, original image/annotation/mask file hashes and dataset metadata hashes. The [review list](review.csv) contains all flagged image keys. Original workstation/server paths are omitted. Full per-object traces and four-panel previews remain reproducible from the preserved native exports; they are not embedded in Git.

Run the [annotation audit workflow](../../../guides/annotation-audit.md) from the repository root:

```bash
python -m scripts.audit_annotations audit \
  --dataset data/paul-test-rtis \
  --out artifacts/rtis-annotation-review
```

The original native paths in `audit/samples.json` must be accessible, or supply `--source-root`. Correct labels only after human review using the documented immutable version operation. Existing RTIS training continues to use its original labels.
