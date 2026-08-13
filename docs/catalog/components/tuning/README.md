# Tuning modes

Tuning decides which model weights learn. It is independent of the dataset and
curriculum, although a later stage may additionally freeze a named parameter
subtree.

## Beginner choice

Use full fine-tuning first:

```yaml
model:
  tuning: full
```

It is the clearest baseline. Consider frozen or LoRA only after the same model,
data, and evaluation protocol work end to end.

## Exact switches

| `model.tuning` | what trains | pros | cons |
|---|---|---|---|
| `full` | backbone and full decoder/head | maximum adaptation; simplest interpretation | largest optimizer memory; more forgetting/overfit risk |
| `frozen` | decoder/head; backbone weights and running-stat norms stay frozen | cheap feature probe; useful for very small data | domain shift cannot reshape backbone features |
| `lora` | low-rank attention adapters plus the full head | lower trainable parameter count; base weights preserved | transformer/module-name dependent; full Lightning checkpoint is still not adapter-only |

LoRA fields are:

```yaml
model:
  tuning: lora
  lora_r: 16
  lora_alpha: 32
  lora_dropout: 0.05
  lora_targets: []  # infer one complete known attention layout
```

`lora_r` must be positive in LoRA mode, `lora_alpha` positive, and dropout in
`[0, 1)`. With an empty target list, Segmentary inspects backbone `Linear` leaves
for a known complete projection layout. Explicit targets are leaf names such as
`q_proj`, not broad unreviewed regexes. Zero matches are fatal.

## Stage-specific freezing

This is separate from tuning mode:

```yaml
stages:
  - name: target
    freeze: backbone.stages.0
```

`freeze` is a substring match over qualified parameter names after model tuning
is applied. A value that matches zero parameters raises. This is useful for a
named partial-freeze ablation, but it is easier to misinterpret than the three
global tuning modes; record the exact matched parameter count from the run log.

## Compatibility limits

- Automatic LoRA requires recognized attention projection names. Ordinary
  ResNet, ConvNeXt, MobileNet, EfficientNet, and HRNet backbones are
  convolutional and fail rather than silently becoming head-only training.
- The full decoder/head remains trainable under LoRA. Segmentary checks that PEFT
  did not freeze nested head copies.
- Sequential LoRA curricula inject the same adapter layout before loading the
  prior stage's full checkpoint. The hand-off therefore includes adapter,
  pretrained base, and wrapped head state exactly; a changed target/rank/layout
  fails rather than partially loading.
- Frozen and LoRA backbone BatchNorm running statistics stay in evaluation mode;
  otherwise those modes would still adapt hidden state.
- `model.head: per_stage_head` is not implemented. Use `unified_head` and a
  deliberate stage `reset_head` ablation.

## Evidence and benchmark boundary

Tests prove trainable counts, backbone/head gradients, target inference,
zero-match failure, normalization freezing, and reset behavior. No completed
same-protocol full-versus-frozen-versus-LoRA accuracy table is committed, so the
mode descriptions are mechanisms and tradeoffs, not ranking claims.

## Related documentation

- [Models and tuning guide](../../../guides/models-and-tuning.md)
- [Heads](../heads/README.md)
- [Optimization](../optimization/README.md)
- [Training runtime](../training-runtime/README.md)
