# `rail_union` taxonomy

This 21-class canonical space lets Cityscapes, RailSem19, and a custom rail
dataset share one classifier. It is the transfer case study, not a standard
Cityscapes benchmark space.

## Canonical classes

| ids | classes |
|---|---|
| 0–1 | road, sidewalk |
| 2–3 | construction, fence |
| 4–6 | pole, traffic-light, traffic-sign |
| 7–9 | vegetation, terrain, sky |
| 10–15 | human, car, truck, motorcycle, bicycle, on-rails |
| 16–20 | rail-track, rail-raised, rail-embedded, tram-track, trackbed |

Ignore is 255. Thin classes are pole, traffic-light, traffic-sign,
rail-raised, rail-embedded, and tram-track (canonical IDs 4, 5, 6, 17, 18, 19).

The space adopts RailSem19's coarser meanings where the sources disagree:
building+wall become construction, person+rider become human, and several large
vehicle types become truck. It retains Cityscapes-only motorcycle/bicycle and
all RailSem19 rail classes. This avoids pretending a coarse native pixel can be
split back into a finer label.

## Beginner choice

Use the default `cityscapes.yaml` mapping for Cityscapes stages and
`railsem19.yaml` for RailSem19 stages. Keep one `rail_union` head across both.
Do not enable the rail-bridge variant until the ordinary staged baseline works,
and use `custom.yaml` only when custom masks truly use these canonical IDs.

## Mapping choices

| mapping | active | behavior | intended use |
|---|---:|---|---|
| [`cityscapes.yaml`](cityscapes.yaml) | 16/21 | official ignored native rail/guard labels stay ignored; declared urban merges | default urban source stage |
| [`cityscapes_railbridge.yaml`](cityscapes_railbridge.yaml) | 18/21 | additionally maps native rail track -> rail-track and guard rail -> rail-raised | named supervision ablation only |
| [`railsem19.yaml`](railsem19.yaml) | 19/21 | one-to-one on RailSem19 evaluated classes; motorcycle/bicycle inactive | rail training/evaluation |
| [`custom.yaml`](custom.yaml) | 21/21 | identity mapping for masks authored in canonical IDs | legacy custom target template |

### Cityscapes default

Native building+wall merge into construction; person+rider into human; and
truck+bus+caravan+trailer into truck. Each merge is declared with a written
reason. Rail infrastructure IDs 16–20 are inactive.

Pros: conservative, reproducible default; avoids inventing rail supervision;
keeps all output meanings stable. Cons: coarsens standard Cityscapes urban
classes and cannot be compared with Cityscapes-19 literature mIoU.

### Cityscapes rail-bridge variant

This keeps the same declared urban merges and turns on two additional native
labels. Rail track is semantically close to canonical rail-track. Guard rail is
noisier: ordinary road barriers are included even though RailSem19's
rail-raised meaning covers rails/guard rails.

Pros: tests whether weak early rail labels help. Cons: nonstandard Cityscapes
protocol, rare supervision, and an explicitly lossy guard-rail proxy. Always set
`variant: railbridge`; never replace the default mapping silently.

### RailSem19

All 19 native classes map injectively into the union. Motorcycle and bicycle are
inactive because RailSem19 cannot label them. Pros: direct rail semantics and no
merges. Cons: those two Cityscapes-only classes receive no RailSem loss.

### Custom identity template

All 21 classes plus ignore map to themselves. Pros: simplest target mapping and
full active space. Cons: it is only correct when annotation masks truly use
these exact IDs/meanings; edit the mapping if the annotation tool uses another
schema.

## Advanced active-mask behavior

In a mixed Cityscapes/RailSem batch, Cityscapes samples exclude rail logits from
their softmax while RailSem samples exclude motorcycle/bicycle. The model still
has all 21 outputs. In-training validation uses the first dataset's mapping; a
common RailSem evaluation uses the RailSem active set.

## Evidence and benchmark boundary

Taxonomy tests verify every native target, active set, merge declaration,
variant difference, and real observed IDs where datasets are available. No
completed multi-seed `rail_union` curriculum table is committed, so this page
does not claim that staged, joint, or rail-bridge training wins. The
Cityscapes-19 `0.805073` reference belongs to a different taxonomy and cannot be
borrowed.

## Related documentation

- [Taxonomy catalog](../README.md)
- [Cityscapes dataset](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/datasets/cityscapes/README.md)
- [RailSem19 dataset](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/datasets/railsem19/README.md)
- [Legacy custom dataset](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/datasets/custom-legacy/README.md)
- [Curriculum catalog](https://github.com/arianizadi/segmentary/blob/main/docs/catalog/curricula/README.md)
