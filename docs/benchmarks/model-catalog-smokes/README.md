# Model catalog compatibility smokes

These records prove that every new Hugging Face and SMP recipe can load its real
requested pretrained weights, preprocess an input, run forward/backward, and
update through a few optimizer steps on one NVIDIA L40S.

They are deliberately **not accuracy or latency benchmarks**:

- inputs and labels are synthetic;
- crops are 64, 128, or 128×128 depending on the family;
- only four or five optimizer steps run;
- wall time includes model loading and is not a timed inference protocol;
- peak memory is allocated CUDA memory for the tiny test, not production
  training memory.

Use the figures to catch incompatibility and choose a conservative first smoke
batch, not to rank models. Machine-readable evidence is in
[`hf-auto.json`](hf-auto.json) and [`smp.json`](smp.json).

## Acceptance summary

- Six revision-pinned complete Hugging Face semantic checkpoints passed five
  steps. A separate pixel-level check matched every pinned upstream image
  processor, including MobileViT's BGR/no-normalization contract.
- A stricter BF16 audit then required every loss-reachable trainable parameter
  to have a finite gradient and the classifier to update. Three pinned upstream
  implementations contained explicitly documented loss-unreachable modules;
  those exact paths are frozen in their recipe configs so ordinary DDP remains
  strict for every undeclared disconnection.
- The original ten SMP recipes retain per-model parameter/VRAM records from
  their first four-step run. A later strict GPU8 audit covers all eleven shipped
  recipes, including UPerNet/ResNet-101, at one common 128×128 shape and requires
  a finite gradient on every loss-reachable trainable tensor plus a changed
  segmentation head. Both protocols are recorded in `smp.json`.
- Every loss was finite, gradients reached trainable parameters, and every SMP
  segmentation head changed.
- PAN required 128×128; at 64×64 its pyramid would pool below one pixel. That
  minimum is now explicit in its recipe documentation.

Dataset-quality comparisons require the same taxonomy, split, schedule,
checkpoint/EMA policy, evaluation mode, code revision, and seed set. See
[interpreting results](../../tutorials/interpreting-results.md).
