# Dense Dice reduction experiment

The scratch Torch backend accepts one optional scientific recipe field:

```yaml
loss: dice_ce
dice_reduction: per_sample
```

`batch` is the default and preserves the existing CE plus foreground Dice value
and gradients. It sums intersections and denominators across the entire batch
before calculating each foreground class's Dice.

`per_sample` sums only over spatial axes, computes Dice separately for each
sample and foreground class, then averages equally. A sample is a **training
patch**, not necessarily a distinct patient: a batch can contain multiple patches
from one CT. This is not an equal-patient training objective.

Both variants retain labels 1 and 2 as separate foreground classes, the existing
`1e-5` smoothing, and mean cross-entropy over all voxels including background.
Reference-empty classes remain included; their predicted probability contributes
to the denominator. This option changes only the Dice reduction, not class
weights, sampling, optimization, inference, or native evaluation.

This first ablation supports models using the common dense `dice_ce` objective.
Focal loss, DynUNet deep supervision, auxiliary model-native objectives, and
query matching losses reject `per_sample` explicitly. Their existing default
behavior remains unchanged.

## Experiment and checkpoint identity

Use a **fresh scratch workspace and frozen source checkout** for each arm. Compare
`batch` and `per_sample` with matched seeds, patches, sampling, and update budgets.
The resolved recipe and immutable binding contain `dice_reduction`; changing it
after preparation invalidates resume. Scientific recipe fingerprints also include
the setting.

Recipes that omit the option resolve to `batch`. Existing experiments retain their
original frozen source and serialized bindings. This source version adds a recipe
field and changes source hashes, so it does not migrate or rebind old workspaces;
resume historical runs using the source that created them. The new option is a
testable hypothesis inspired by the official reference recipe, not a confirmed
explanation of the performance gap.
