# Built-in HRNet-W48 with OCR

Use [`hrnet_w48_ocr.yaml`](../../../../configs/models/hrnet_w48_ocr.yaml) for a
legacy high-resolution CNN comparison with an Object-Contextual Representations
head.

## What it is

The backbone is timm's ImageNet-pretrained HRNet-W48. Unlike an ordinary encoder
that repeatedly downsamples one stream, HRNet keeps four resolution branches in
parallel. Segmentary removes timm's classification-only modules, upsamples the four
branches to the finest feature resolution, concatenates them, and feeds them to
the local OCR head.

OCR first predicts soft class regions, pools an object representation for each
region, lets every pixel attend to those representations, and classifies the
refined features.

## OCR supervision

Training applies an explicit `0.4`-weighted auxiliary loss to the full-resolution
coarse OCR logits. Public inference still returns only the refined logits, so the
extra prediction is used for deep supervision without changing deployment or
evaluation output.

Pros:

- preserves high-resolution features for thin structures and boundaries;
- useful convolutional legacy comparison against transformer models;
- local OCR implementation is readable and covered without adding another
  segmentation framework as a runtime dependency.

Cons:

- large W48 backbone and high-resolution activations;
- the auxiliary OCR objective increases training memory and computation;
- export has not been validated;
- no same-protocol Segmentary dataset-quality benchmark is recorded.

## Settings and checkpoints

Full and frozen tuning are supported. Automatic LoRA target discovery is not a
default for HRNet; an explicit convolution target is an advanced experiment and
needs its own gradient proof. `drop_path` is rejected because timm HRNet does
not implement the option even though it can silently accept an unused keyword.

The factory rejects `model.checkpoint` for this arm because timm owns the
ImageNet weight selection. To load a Segmentary-trained model, use the curriculum
stage's `init_from` field. `reset_head` resets the final classifier and the
coarse class predictor while keeping class-agnostic OCR attention.

Use RGB ImageNet normalization and crop sizes divisible by 32. Begin with a
smaller crop/batch smoke, then measure intended-crop memory.

## Verified evidence

Unit and gradient regressions exercise the local OCR arithmetic, multi-scale
concatenation, reset behavior, and a smaller HRNet variant through the same code
path. This is implementation evidence, not W48 accuracy evidence. No benchmark
number is claimed until a complete result record exists.

See the [built-in model component](../../components/builtin-models/README.md)
and [`hrnet_ocr.py`](../../../../src/segmentary/models/hrnet_ocr.py).
