# paul-test-rtis

A rail-scene semantic-segmentation dataset prepared from the supplied Supervisely
project and CVAT task 61. **307 unique annotated images; 21 classes; ignore ID 255.**

Local dataset: `data/paul-test-rtis/`. HDRFS dataset: `/data/izadia1/datasets/paul-test-rtis/`. Paths below are relative to that dataset root.

## Start here

- `images/`: original images, arranged by split and readable scene group.
- `masks/`: matching grayscale PNG labels. Pixel values are class IDs, not colors.
- `previews/`: image/annotation overlays for people to inspect; never training labels.
- `source-annotations/`: original retained Supervisely JSONs and the CVAT XML for traceability.
- `classes.json`: class IDs, names, and display colors.
- `splits.json`: exact membership and scene groups used by Segmentary.
- `audit/samples.csv`: one row per retained image, with provenance and checksums.
- `audit/excluded-images.csv`: every removed empty image and consolidated duplicate.
- `audit/class-distribution.csv`: class support in each split, by images and pixels.
- `audit/scene-groups.yaml`: the manually reviewed split decisions.

Example pair:

```text
images/train/trackside-maintenance/0.png
masks/train/trackside-maintenance/0.png
previews/train/trackside-maintenance/0.jpg
```

## Splits

| Split | Images | Scene groups | Purpose |
| --- | ---: | ---: | --- |
| train | 220 | 14 | Fit model weights; tiny overfit diagnostics use this split only |
| val | 37 | 3 | Development checks and source-checkpoint inference |
| test | 50 | 4 | Reserved final evaluation; no model inference in this preparation |

Assignments were chosen by examining all retained image thumbnails and grouping
related-looking scenes, including groups spanning multiple annotation folders.
They are deterministic, explicit assignments, not a random frame split.
Original recording IDs are absent. **The split is provisional until recording
provenance is confirmed; visual grouping cannot prove route/video independence.**
Validation has no person, truck, or on-rails ground-truth pixels. All 21 classes
are present in training and test. Report per-class support with every evaluation.

## What was removed

The exports contained 1,206 image entries: 1,191 in Supervisely and 15 in CVAT.
884 Supervisely images had empty annotation lists and are excluded from this
working dataset. All 15 CVAT images are exact decoded-image duplicates of images
in Supervisely. They are represented once, using the main Supervisely project's
annotation. Native archives remain intact in Downloads; no original was erased.

The duplicate annotations are not identical: 0.195–1.717% of pixels differ after
rasterization. Differences include polygon clipping/coordinates and changed
object counts, so they are logged rather than described as identical labels.
The extracted exports and alternative masks remain in
`artifacts/paul-test-rtis/preparation/` locally, outside the training dataset.

## Annotation rules

Polygons are filled at original resolution; bitmap masks retain their offsets
and holes. Supervisely objects paint in saved order; CVAT objects paint in
ascending z-order. This follows their annotation rendering conventions. Overlap
counts are retained for QA. The source annotations have not been manually
relabelled or certified for semantic correctness.

`road_1`, `terrain_1`, `pole_1`, and `standing-water_1` are imported variants of the
corresponding base classes and map to those base IDs. The shared images and label
geometries establish their correspondence. Source colors and numeric platform
IDs are not used as cross-platform training IDs.

`void` and unpainted pixels map to 255 (ignored by loss and metrics). An image
with no objects is excluded, rather than converted into a background example.
There is no invented background class.

## Classes

| Pixel ID | Class |
| ---: | --- |
| 0 | person |
| 1 | truck |
| 2 | rail-track |
| 3 | vegetation-overgrowth |
| 4 | car |
| 5 | on-rails |
| 6 | traffic-sign |
| 7 | road |
| 8 | sidewalk |
| 9 | construction |
| 10 | tram-track |
| 11 | pole |
| 12 | traffic-light |
| 13 | mud-pumping |
| 14 | fence |
| 15 | terrain |
| 16 | sky |
| 17 | rail-embedded |
| 18 | rail-raised |
| 19 | trackbed |
| 20 | standing-water |
| 255 | ignore / void / unpainted |

Source-specific meanings matter: truck includes buses and other large vehicles;
void includes train-cab/video overlays, bicycles, motorcycles and their riders.
Most other source classes have no written definition in project metadata.
`terrain` is used broadly in the supplied labels, including many vegetated
surroundings; `vegetation-overgrowth` is a distinct class. Keep these RTIS labels
separate from the Cityscapes/RailSem19 taxonomy. Mud-pumping and standing-water
are also additional task concepts, not interchangeable existing rail classes.

## Use in Segmentary

The repository contains `taxonomy/paul-test-rtis/` and
`configs/datasets/paul-test-rtis.yaml`. The dataset uses the existing `folder`
loader, with group checking enabled. From the repository root:

```bash
python -m segmentary.verify \
  --dataset paul-test-rtis --loader folder \
  --root data/paul-test-rtis --space paul-test-rtis \
  --loader-options '{"require_groups":true}' --n-scan 1000
```

Full training has not been started. Tiny overfit checks and source-only inference
are diagnostics stored separately under `segmentary-runs/paul-test-rtis/diagnostics`
on HDRFS. They are not trained RTIS model releases or a final benchmark.
