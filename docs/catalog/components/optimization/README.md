# Optimization choices

Segmentary uses AdamW parameter groups plus a per-optimizer-step linear-warmup and
polynomial-decay schedule. Head and backbone learning rates remain separate.

## Beginner choice

Use the base settings with the model YAML's learning-rate overrides:

```yaml
optim:
  backbone_lr: 6.0e-5
  head_lr_mult: 10.0
  weight_decay: 0.05
  llrd: 1.0
  warmup_iters: 1500
  warmup_ratio: 1.0e-6
  poly_power: 0.9
  min_lr_ratio: 0.0
  betas: [0.9, 0.999]
  grad_clip: 1.0
```

## Exact behavior

- Backbone layer rate is `backbone_lr * llrd ** (max_depth - depth)`.
- Decoder/head parameters use `backbone_lr * head_lr_mult` without layer decay.
- Biases, normalization parameters, position/class/register/mask tokens, gamma,
  and layer-scale parameters automatically receive zero weight decay.
- The scheduler warms from `warmup_ratio` to 1, then follows polynomial decay
  toward `min_lr_ratio` with exponent `poly_power`.
- Every stage multiplies all rates by `stage.lr_scale`. An experimental stage
  may instead set `stage.head_group_lr_scale` to scale model-declared head groups
  independently. Those groups often include a complete decoder, not only a
  final classifier.
- A stage caps requested warmup to roughly its first 10 percent
  (`min(warmup_iters, max(1, iters // 10))`).

## Pros and cons

| switch | benefit | risk |
|---|---|---|
| lower `backbone_lr` | protects pretrained features | target adaptation may stall |
| higher `head_lr_mult` | fresh decoder/classifier learns quickly | unstable head or overshoot |
| larger `weight_decay` | regularizes weight matrices | underfit if excessive |
| `llrd < 1` | protects early transformer layers | adds architecture-specific tuning; invalid when depth cannot be discovered |
| longer warmup | reduces early spikes | wastes a short run if it never reaches peak |
| positive `min_lr_ratio` | avoids a near-zero late rate | may prevent final settling |
| gradient clipping | contains large updates | can mask a fundamentally bad LR or corrupt data |

## Validation and limits

`backbone_lr` must be positive and `llrd` lies in `(0, 1]`. Scheduler
construction additionally requires nonnegative warmup shorter than total steps,
and warmup/min-LR ratios in `[0, 1]`. `grad_clip: null` disables clipping.

LLRD requires discoverable transformer block depth. On a conventional CNN it
fails when set below `1.0` rather than turning into an undocumented blanket LR
multiplier. Only parameters with `requires_grad=True` enter optimizer state, so
frozen weights and LoRA base weights do not consume Adam moments.

`stage.init_from: /path/to.ckpt` is a weight warm start, not optimizer/scheduler
resume. The new stage constructs a fresh optimizer and its own step schedule.
`head_group_lr_scale` multiplies the configured head-group rate
(`backbone_lr * head_lr_mult`); it does not replace `head_lr_mult`.

## Evidence and benchmark boundary

Tests cover layer IDs for hierarchical and flat transformers, head multiplier,
no-decay rules, LLRD failure on CNNs, scheduler endpoints, and trainable-only
groups. No completed optimizer/LLRD ablation benchmark is committed. Values in
the model YAMLs are recipes to test, not proof of universal superiority.

## Related documentation

- [Tuning modes](../tuning/README.md)
- [Training runtime](../training-runtime/README.md)
- [Configuration guide](../../../guides/configuration.md)
