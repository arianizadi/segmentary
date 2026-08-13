# BEiT-Base + pyramid decode head

Use [`hf_auto_beit_base_ade.yaml`](../../../../configs/models/hf_auto_beit_base_ade.yaml)
when a larger, self-supervised transformer backbone and pyramid-style semantic
head are worth substantially more compute than a lightweight baseline.

## What it is

BEiT is a patch transformer pretrained by predicting visual tokens. This
checkpoint adds feature-pyramid and UPerNet-style decode modules and was
fine-tuned on ADE20K. Segmentary trains the primary dense head and deliberately
drops the checkpoint's separate auxiliary training branch. Only keys below the
exact `auxiliary_head.` prefix may be discarded; any other load gap is fatal.

| item | value |
|---|---|
| checkpoint | [`microsoft/beit-base-finetuned-ade-640-640`](https://huggingface.co/microsoft/beit-base-finetuned-ade-640-640) |
| pinned revision | `a8b6f5ef4acb2ea55d882989deaa02d39401e2b2` |
| source task | ADE20K, 150 classes, 640×640 fine-tuning |
| source preprocessing | RGB, mean/std `(0.5, 0.5, 0.5)`, `1/255` rescale |
| Segmentary parameters with 19 classes | 161,498,707 |

## Why choose it

Pros:

- high-capacity transformer representation;
- multi-level pyramid/decode path is appropriate for dense prediction;
- source checkpoint includes segmentation training rather than encoder-only
  pretraining;
- supports full, frozen, and compatible attention-LoRA tuning.

Cons:

- by far the largest shipped `hf_auto` example;
- slower and more memory-hungry than SegFormer-B0 or the mobile recipes;
- Segmentary does not reproduce the upstream auxiliary-loss objective;
- a new classifier and domain transfer still require careful optimization.

## Verified Segmentary evidence

The pinned real checkpoint passed the full strict load audit and five FP32 AdamW
steps on one L40S with batch 2 and 128×128 synthetic inputs. It used 2.827 GiB
peak allocated CUDA memory; all losses and trainable gradients were finite.
The later BF16 strict audit froze only the two declared unreachable blocks,
verified a finite gradient on every remaining trainable tensor, and updated the
classifier.

That small-crop memory number is only a compatibility reference. It excludes a
production crop, distributed buffers, and a realistic dataset, and it is not an
accuracy or latency benchmark. No comparable Segmentary mIoU exists yet.

## Advanced settings

- Begin with a smaller crop/batch and use accumulation to reach the intended
  effective batch.
- `llrd: 0.8` gives lower learning rates to earlier backbone layers.
- Frozen tuning is useful to establish how much of the gain comes from the
  pretrained representation; full tuning is the main adaptation path.
- Treat changing/removing the auxiliary-head policy as a new objective, not a
  harmless loader option.
- This pinned implementation's final two BEiT blocks are not consumed by its
  selected feature outputs. The recipe explicitly freezes only
  `beit.layers.10` and `beit.layers.11`; deleting that declaration will make a
  strict multi-GPU full-tuning run fail on unused gradients.

See the [Hugging Face component contract](../../components/hf-auto/README.md).
