# Augmentation choices

Augmentation changes training images and masks together so a model sees more
variation. Evaluation uses a separate deterministic transform and is never
randomly cropped.

## Beginner choice

Keep the base recipe until the data verifier and eight-image overfit check pass:

```yaml
aug:
  crop: [1024, 1024]
  scale_min: 0.5
  scale_max: 2.0
  hflip_p: 0.5
  color_jitter_p: 0.5
  brightness: 0.25
  contrast: 0.25
  saturation: 0.25
  hue: 0.05
```

## Exact training pipeline

The operations run in this order:

1. random scale using bilinear image interpolation and nearest-neighbor masks;
2. random crop, padding small images with neutral image fill and mask ID `255`;
3. horizontal flip with `hflip_p`;
4. color jitter with `color_jitter_p` and the four configured strengths;
5. audited RGB/BGR channel order and model normalization;
6. tensor conversion.

`crop` is `[height, width]`. Scale bounds must satisfy
`0 < scale_min <= scale_max`. Flip and jitter probabilities are in `[0, 1]`.

## Pros, cons, and tradeoffs

| choice | benefit | cost/risk |
|---|---|---|
| larger crop | more scene context and fewer crop-edge effects | memory grows quickly; often lowers feasible batch size |
| wider scale range | more scale robustness | thin objects can disappear when downscaled; padding grows after strong downscale |
| horizontal flip | cheap left/right variation | wrong for direction-dependent labels or asymmetric text/sign meaning |
| stronger color jitter | lighting/camera robustness | can destroy color cues central to the task |
| no augmentation | easiest memorization/debug path | not a robust full-training recipe |

## Model preprocessing

Normalization is not a manual experiment knob in `AugConfigSpec`. Standard
models use ImageNet mean/std and RGB. `hf_auto` reads the matching
`AutoImageProcessor`, verifies its rescale semantics, and records the effective
mean, std, and channel order in `results.json`. The same preprocessing is used
for training, overfit checks, evaluation, and export.

## Evaluation and overfit differences

Evaluation only applies channel order, normalization, and tensor conversion at
native resolution. Sliding-window inference handles large images. The overfit
transform keeps only crop/pad plus normalization, with random scale/flip/color
changes disabled so failure points at wiring rather than regularization. Seed
the run when the exact crop sequence itself must be reproduced.

## Unsupported/advanced limits

The typed YAML surface does not currently expose rotation, blur, cutout,
copy-paste, mixup, or custom transform lists. Adding one requires mask-safe
geometry, deterministic seeding, config validation, and tests. Do not pass old
Albumentations `mask_value=` examples: version 2 renamed it to `fill_mask`, and
silently ignoring the old argument can turn padding into class 0. Segmentary
promotes that warning to an error.

## Evidence and benchmark boundary

Tests prove nearest-neighbor label geometry, ignore padding, deterministic
seeding with zero workers, channel order, and normalization propagation. No
same-protocol augmentation ablation benchmark is committed; the defaults are a
reviewed baseline, not a universal optimum.

## Related documentation

- [Configuration guide](../../../guides/configuration.md)
- [Dataset loader choices](../loaders/README.md)
- [Evaluation](../evaluation/README.md)
- [Getting started](../../../tutorials/getting-started.md)
