# `cityscapes19` taxonomy

This is the standard Cityscapes 19-class train-ID protocol. Use it for
Cityscapes reference/literature comparison, not for rail-transfer training.

## Canonical classes

IDs 0–18 are, in order: road, sidewalk, building, wall, fence, pole,
traffic-light, traffic-sign, vegetation, terrain, sky, person, rider, car,
truck, bus, train, motorcycle, and bicycle. Ignore is 255. Pole,
traffic-light, and traffic-sign are marked thin for separate reporting.

## `cityscapes.yaml`: official mapping

[`cityscapes.yaml`](cityscapes.yaml) maps raw `gtFine *_labelIds.png` IDs 0–33
onto standard train IDs. Official `ignoreInEval` labels—including native rail
track and guard rail—map to 255. All 19 canonical classes are active and there
are no many-to-one merges in train-ID space.

Beginner/reference config:

```yaml
space: cityscapes19
data:
  - name: cityscapes
    root: data/cityscapes
```

Pros: exact standard semantics; direct reference scale; all classes evaluable.
Cons: deliberately discards rail infrastructure ignored by the official
protocol; unsuitable as the training space for the staged rail experiment.

## `railsem19.yaml`: lossy cross-evaluation mapping

[`railsem19.yaml`](railsem19.yaml) exists only to ask how a
Cityscapes-19-space model behaves on rail imagery. It activates 14 of 19
classes. RailSem19 rail-track, trackbed, rail-raised, rail-embedded, and
tram-track map to ignore because this space has no evaluated counterpart.

Additional unavoidable losses are:

- RailSem19 `construction` maps to building; wall cannot be recovered;
- `human` maps to person; rider cannot be recovered;
- `truck` maps to truck; bus/caravan/trailer cannot be recovered;
- wall, rider, bus, motorcycle, and bicycle are inactive in this cross-map.

Pros: enables a clearly labeled zero-shot domain-gap measurement in the same
output space. Cons: asymmetric and unsuitable for RailSem19 training; several
per-class values are intrinsically unreliable.

## Advanced rule

Never compare a `cityscapes19` mIoU with a `rail_union` mIoU. Even if the image
files match, class meanings, active sets, and ignored pixels differ. Likewise,
do not train a RailSem stage through the lossy cross-map and call it transfer.

## Verified evidence

The corrected SegFormer-B2 reference curriculum recorded `0.805073` mIoU on
all 500 Cityscapes validation images at the true 40k endpoint. It validates this
exact space and does not establish performance on RailSem19. Exact tracked
context and the absent raw-machine-record caveat are in
[benchmark evidence](https://github.com/arianizadi/segmentary/blob/main/docs/benchmarks/README.md).

Taxonomy and real-data tests verify the official raw-ID mapping, all active
classes, ignore behavior, and Cityscapes mask coverage.

## Related documentation

- [Taxonomy catalog](../README.md)
- [Cityscapes dataset](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/datasets/cityscapes/README.md)
- [RailSem19 cross-evaluation](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/datasets/railsem19/README.md)
- [Reference curriculum](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/reference_cityscapes19/README.md)
