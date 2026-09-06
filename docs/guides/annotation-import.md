# Importing mixed Supervisely and CVAT annotations

## Downloads

Keep the native exports as the source of truth. Export original-size images and
all intended datasets/tasks, preserving their names and any sequence identifiers.

| Platform | Export | Local intake directory |
| --- | --- | --- |
| Supervisely | **Export to Supervisely format** (images and JSON annotations) | `~/Downloads/segmentary-exports/supervisely/` |
| CVAT | **CVAT for images 1.1**, with **Save images** enabled | `~/Downloads/segmentary-exports/cvat/` |

Leave downloaded archives intact. Give separate exports distinct filenames.
Supervisely exports should contain project metadata, image annotations, and images;
CVAT exports should contain `annotations.xml` and images. Retain the native
archives even after conversion. Native exports are annotation sources, not a
complete backup of platform users, jobs, or review history.

COCO is a viable interchange alternative: **Export to COCO mask** on Supervisely
preserves holes as RLE; CVAT's **COCO 1.0** supports polygons and masks. However,
native exports are preferred here so conversion can inspect source geometry,
attributes, and available ordering metadata. COCO category numbers from different
exports must never be assumed to mean the same thing. Explicit CVAT `is_crowd`
attributes can change polygon/mask conversion; do not change them just to export.

## Target for this repository

Segmentary's `folder` loader reads images paired with single-channel integer
class-ID PNG masks. It does not directly read either native annotation format.
Use the existing folder loader, taxonomy mapping, split helper, and verifier
after conversion; see [custom data](custom-data.md).

```text
data/annotation-import/
  raw/       # preserved source exports and provenance
  work/      # extracted annotations and intermediate conversion outputs
  qa/        # inventories, conflict reports, and overlays

data/merged_annotations/    # created after annotation policy is resolved
  images/train/<source>/<sample>.jpg
  images/val/<source>/<sample>.jpg
  masks/train/<source>/<sample>.png
  masks/val/<source>/<sample>.png
  splits.json
```

The image extension can vary; matching relative paths and stems pair masks with
images. Dataset contents under `data/` are already ignored by Git.

## Conversion decisions after the exports arrive

1. Inventory archives, image counts, dimensions, class definitions, geometry
   types, annotation coverage, source dataset/task IDs, and sequence metadata.
   Check that intended images and both CVAT geometry types actually survived
   export before switching away from the annotation-server VPN.
2. Define a shared class vocabulary with explicit per-source mappings. Match
   meanings rather than numeric IDs or display colors; flag ambiguous names.
3. Rasterize polygons at original image resolution, respecting interior holes;
   decode bitmap/RLE annotations with their offsets and image dimensions.
   Do not turn existing bitmap masks into approximate polygons.
4. Produce one semantic class per pixel. Same-class regions can be unioned.
   Different-class overlaps require a documented visibility/priority policy,
   using reliable source ordering when available. Report ambiguous overlaps;
   annotation list order is not an implicit policy. Uncovered pixels default to
   ignore ID 255 until annotation coverage establishes whether they are a real
   background class. Instance identities remain in the raw exports.
5. Detect duplicate images across exports by content, not just filenames. Keep
   provenance and reconcile duplicate-image annotations before splitting;
   conflicting revisions must not silently overwrite one another.
6. Split related video frames, recordings, routes, or sites as groups. Preserve
   legitimate existing splits when compatible with this constraint. Never infer
   that separate annotation tasks necessarily mean independent recordings.
7. Validate image/mask pairs, class IDs, holes, offsets, class frequencies,
   ignored-pixel coverage, and cross-split duplicates. Inspect overlays of mixed
   polygon/mask images and every problematic geometry category.
8. Generate the actual taxonomy and training configuration from the audited
   classes. Run `segmentary-verify` and a tiny overfit check in a compatible
   training environment before a full run.

## Current preparation status

The supplied exports have now been prepared as
[paul-test-rtis](../datasets/paul-test-rtis/README.md). That dataset guide records
the actual counts, mappings, exclusions, provisional scene splits, and model
diagnostics. This page retains the general export/conversion workflow.

## Format references

- [Supervisely native annotation objects](https://developer.supervisely.com/getting-started/supervisely-annotation-format/objects)
- [Supervisely COCO mask exporter](https://ecosystem.supervisely.com/apps/export-to-coco-mask)
- [CVAT native image format](https://docs.cvat.ai/docs/dataset_management/formats/format-cvat/)
- [CVAT COCO format](https://docs.cvat.ai/docs/dataset_management/formats/format-coco/)
- [CVAT export instructions](https://docs.cvat.ai/docs/dataset_management/export-datasets/)
