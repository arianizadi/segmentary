# RailSem19 dataset

`loader: railsem19` reads RailSem19 v1 RGB images and indexed masks.

## Required layout

```text
<root>/jpgs/rs19_val/rsNNNNN.jpg
<root>/uint8/rs19_val/rsNNNNN.png
<root>/jsons/rs19_val/rsNNNNN.json  # present upstream; unused by this loader
<root>/rs19-config.json
```

The verified archive has 8,500 matched 1920x1080 image/mask pairs. Masks contain
native IDs 0 through 18 plus void 255.

## Beginner choice

Use `space: rail_union`, the bundled `railsem19_seed0.json` split, and the
default `railsem19` mapping. Run the verifier on real masks before training, and
keep the same split file for every training seed.

## Mandatory split

RailSem19 does not provide the train/validation split used by the main
curricula. Every data entry must name a committed JSON file:

```yaml
data:
  - name: railsem19
    root: data/railsem19
    split_file: splits/railsem19_seed0.json
```

The bundled seed-0 split contains 6,800 train, 850 validation, and 850 test
frames. The v1 naming identifies one frame per sequence, so this split does not
mix adjacent video frames. That fact is specific to RailSem19 and must not be
copied to ordinary recorded-video data.

The alternate `railsem19_official4000.json` lists 3,000/500/500 frames. These
split files are different protocols; never mix them in one aggregate.

## Taxonomy choices

| space | active classes | intended use | limitation |
|---|---:|---|---|
| `rail_union` | 19 of 21 | training and rail-target evaluation | motorcycle and bicycle are inactive because RailSem19 cannot label them |
| `cityscapes19` | 14 of 19 | cross-evaluation of a Cityscapes-space model on rail imagery | lossy/asymmetric; rail classes are ignored and several urban distinctions are unrecoverable |

The verifier also compares the dataset's own `rs19-config.json` IDs with the
mapping file, so a stale transcription is caught.

## Pros and cons

Pros:

- direct railway-domain semantic labels, including five rail infrastructure
  classes in `rail_union`;
- 8,500 full-HD images;
- one-to-one mapping into the union space;
- explicit versioned split makes experiments reproducible.

Cons:

- no universal official split for the main experiment, so papers using other
  partitions are not directly comparable;
- motorcycle/bicycle are unavailable;
- 1080x1920 native evaluation is computationally expensive;
- the `cityscapes19` cross-map deliberately destroys rail semantics.

## Evidence and benchmark boundary

Real-data tests verify matched files, split counts, native sizes/modes/IDs,
mapping coverage, and native-resolution loading. The completed
[three-seed case study](../../../findings.md) uses this same 850-image split for
all 12 common evaluations and independently verifies the full 8,500-key dataset
inventory. Its curriculum findings are protocol-specific; any new comparison
must keep the split, taxonomy, EMA/raw policy, checkpoint rule, and evaluator
settings fixed.

## Related documentation

- [Dataset catalog](../README.md)
- [`rail_union` taxonomy](../../../../taxonomy/rail_union/README.md)
- [`cityscapes19` cross-evaluation mapping](../../../../taxonomy/cityscapes19/README.md)
- [RailSem-only curriculum](../../curricula/rs_only/README.md)
- [Evaluation choices](../../components/evaluation/README.md)
