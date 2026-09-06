# paul-test-rtis preparation and diagnostics

Dataset: **307 unique annotated images**, 21 native RTIS classes, ignore 255.
[Dataset structure and definitions](../../datasets/paul-test-rtis/README.md) ·
[Future campaign design](../../guides/paul-test-rtis-campaign.md)

## Dataset checks

- 884 empty-annotation images excluded and logged; 15 duplicate CVAT images consolidated.
- 220 train / 37 validation / 50 test, with readable, manually reviewed scene groups.
- All image/mask pairs and class IDs passed; source annotations and provenance retained.
- All 21 classes occur in training and test. Validation lacks person, truck and on-rails.
- Original recording IDs remain unconfirmed: the split is provisional.
- Reference screening covered 13,500 Cityscapes/RailSem19 files. No exact file matches
  were found. One perceptual-hash candidate was visually checked and was a different
  scene. No cross-split RTIS pairs met the hash-distance threshold of 6. This does
  not prove recording independence or exclude differently cropped/re-encoded overlap.

## Eight-image overfit checks

These are bounded pipeline diagnostics, not full-dataset training. Both used the
same eight train images, deterministic 512×512 crops, no random augmentation,
seed 0, BF16, and a maximum of 400 updates. The eight full images cover all 21
classes; the fixed crops contain 19, excluding truck and on-rails.

| Model | Outcome | mIoU on memorized crops | Step | Loop time |
| --- | --- | ---: | ---: | ---: |
| SegFormer-B2 | PASS | 95.28% | 140 | 27 s |
| FPN-ResNet50 | PASS | 95.39% | 380 | 41 s |

All six source-to-RTIS classifier-reset warm starts also loaded successfully and
produced finite `2 × 21 × 256 × 256` outputs. This includes the 21-channel
RailUnion → 21-channel RTIS case, where resetting the classifier is essential
because the label meanings differ. No optimizer update was used in that check.

## Source-only inference on RTIS validation

Six existing checkpoints were evaluated on all 37 validation images, with **no
RTIS adaptation**: two architectures under Cityscapes-only, RailSem19-only, and
Cityscapes → RailSem19 source protocols. Each exact checkpoint was SHA-256 checked
against its campaign record. Predictions use the repository's loader/transforms
and inference implementation, raw weights, BF16, native-resolution 1024×1024
sliding windows with stride 768, and no TTA. Test images were not inferred on.

**The following is a shared, coarse diagnostic score, not 21-class RTIS mIoU.**
Cityscapes cannot predict the rail-specific classes, and neither source taxonomy
contains mud-pumping or standing-water. Those target pixels are excluded.
Vegetation, terrain and overgrowth are combined into natural-surroundings for
this diagnostic only, because the RTIS source labels use terrain broadly.
Other shared classes are road, sidewalk, construction, fence, pole, traffic-light,
traffic-sign, sky, person, car, truck and on-rails. Source predictions outside the
shared set count as errors on evaluated pixels. mIoU averages only classes with
validation target support. It does not measure anomaly detection.

| Model | Cityscapes only | RailSem19 only | Cityscapes → RailSem19 |
| --- | ---: | ---: | ---: |
| FPN-ResNet50 | 27.30% | 59.78% | 57.99% |
| SegFormer-B2 | 35.11% | 64.41% | 60.84% |

Visual inspection of rural track, dark wet-track, and trackside-vegetation scenes
shows the source Cityscapes models frequently treating railway surfaces as road
or construction. RailSem19-only and staged models recover much more recognizable
rail geometry. Fine rails and close-up vegetation remain imperfect, and none of
these heads can emit the new mud/water anomaly labels. This small, scene-grouped
validation diagnostic is not enough to select a final model or claim significance.

Full predictions, class legends, comparison images and logs are in
`artifacts/paul-test-rtis/diagnostics/` locally, and
`/data/izadia1/projects/segmentary-runs/paul-test-rtis/diagnostics/` on HDRFS.
The machine-readable summary here retains hashes, inference settings, class
support and per-class scores without placing dataset images in Git.

## Prepared, not launched

144 future configurations cover 36 distinct model recipes × four RTIS
initializations: pretrained backbone, Cityscapes, RailSem19, and Cityscapes →
RailSem19. The planner validated all serialized configs and found all 108 source
checkpoint files. Only the two architectures above have completed RTIS runtime
diagnostics. The full campaign and publisher are not running. No results were
pushed. Confirm recording provenance and review the pilot budget before launch.
