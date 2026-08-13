# Segmentary-native block settings

Native FPN and dense heads share a small, explicit convolution-block vocabulary.
This page explains the settings that can be switched across several components.

## Normalization

| value | what it does | pros | cons |
|---|---|---|---|
| `group` | normalizes channels in groups within each sample | stable with small per-device batches; shipped default | group count is chosen internally; may differ from a published BatchNorm recipe |
| `batch` | uses batch/spatial statistics | familiar and effective with large representative batches | unstable with tiny batches; global 1x1 pooled branches can lack enough values while training |
| `instance` | normalizes every channel independently within each sample | independent of other samples; useful for appearance/style variation | removes per-channel contrast that may carry semantic information |
| `layer` | normalizes all channels independently at each pixel | batch-size independent; accepts arbitrary NCHW map sizes | extra tensor permutation; different inductive bias from convolutional BatchNorm/GroupNorm |
| `none` | adds no normalization layer | simplest graph; avoids statistic mismatch | optimization may be harder and learning-rate sensitive |

`layer` is a real per-pixel channel LayerNorm, not the superficially similar
`GroupNorm(1, C)`: one spatial position never changes another position's
statistics. `instance` uses learnable scale and bias without running statistics.

## Activation

| value | plain meaning | pros | cons |
|---|---|---|---|
| `relu` | zeroes negative activations | cheap, familiar, conservative default | hard zero region can discard signal |
| `relu6` | clips ReLU output at six | bounded and historically mobile-friendly | clipping may constrain useful high activations |
| `leaky_relu` | keeps a small negative slope | avoids a completely dead negative region | fixed slope is another architecture choice to tune |
| `gelu` | smooth probability-shaped gate | common in transformer-style blocks | more compute; no native quality evidence here |
| `silu` | smooth input-weighted sigmoid gate | popular in efficient CNNs | more compute; changing it confounds architecture comparisons |
| `elu` | exponential negative branch and linear positive branch | smooth negative signal with zero-centered tendency | exponential branch costs more than ReLU |
| `mish` | smooth self-gated activation | retains negative signal and is fully smooth | more compute and memory; no native quality evidence here |
| `hardswish` | piecewise-linear approximation of swish | mobile-oriented and cheaper than a sigmoid gate | approximation and clipping can differ from a backbone's original recipe |

## Dropout

`dropout` is a probability in `[0, 1)`. Native heads use spatial dropout before
the classifier. Start at `0.1`; use `0.0` for an overfit diagnostic. Higher is
not automatically better and can obscure a wiring failure in a tiny smoke run.

## Advanced compatibility and evidence

Settings are typed and invalid names/probabilities fail before training. Tests
exercise every listed factory choice and gradient path, including an exact
per-pixel LayerNorm statistic check. There is no same-protocol Segmentary benchmark
comparing these switches, so they are documented as optimization choices rather
than ranked features. Change one block setting at a time for a defensible
ablation.

See [native necks](../native-necks/README.md) and
[native heads](../native-heads/README.md).
