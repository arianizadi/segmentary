# Hugging Face `hf_auto` component

`hf_auto` safely turns a standard
`AutoModelForSemanticSegmentation` checkpoint into Segmentary's common dense-model
contract. It is a conservative adapter, not a promise that every Hub model is
compatible.

## Switchable pieces

| field | beginner meaning | advanced use |
|---|---|---|
| `checkpoint` | the complete pretrained segmentation model | local model directory or Hub repository ID |
| `revision` | exact version of that model | pin an immutable commit; never rely on moving `main` for reported runs |
| `subfolder` | normally empty | load a model stored below the repository root |
| `local_files_only` | allow/deny downloads | enforce offline and pre-warmed-cache execution |
| `backbone_path` | inferred for simple models | assert the exact backbone module for an unusual standard layout |
| `head_paths` | inferred trainable prediction modules | assert every non-backbone parameter owner |
| `classifier_path` | inferred final class layer | assert the one Conv/Linear whose label axis may change |
| `inactive_parameter_paths` | normally empty | revision-pinned backbone modules proven unreachable from primary logits |
| `tuning` | `full`, `frozen`, or `lora` | compare adaptation capacity under the same model |

The three path fields are all-or-nothing. They do not bypass validation.

## What Segmentary proves

Before training, the adapter requires:

- a complete standard Transformers semantic-segmentation checkpoint;
- no repository-defined Python (`trust_remote_code` is always false);
- loading diagnostics for every pretrained tensor;
- only the final classifier's label axis may change shape;
- every parameter belongs to exactly one backbone or head;
- one unambiguous final classifier inside a selected head;
- finite four-dimensional logits that can be resized to input resolution;
- standard `1/255` rescaling plus auditable three-channel mean/std;
- the processor's RGB or BGR channel order, reproduced by every data path.

BEiT/UPerNet-style models may contain a separate upstream auxiliary head. Since
Segmentary owns one dense loss and does not consume that branch, the adapter may
drop only checkpoint keys beginning with `auxiliary_head.`. Any other missing or
unexpected tensor remains a hard failure.

Some upstream implementations also retain backbone modules that their primary
segmentation output never consumes. A shipped recipe may list those exact
modules in `inactive_parameter_paths` only after a real backward audit. Segmentary
then freezes them before optimizer/DDP construction. This keeps ordinary DDP's
unused-gradient check strict: a new, undeclared disconnected branch still
fails. Runtime auto-detection is deliberately avoided because one synthetic
input cannot prove that a conditional path is unused for all real data.
Any nonempty declaration requires an immutable lowercase 40-hex Hub revision;
a branch name or moving tag is rejected.

For these recipes, `tuning: full` means every parameter reachable from
Segmentary's primary dense loss is trainable; explicitly declared unreachable
upstream parameters remain frozen and are recorded in the config.

## Pros and cons

Pros:

- broad access to current standard Transformers architectures;
- checkpoint revision and processor semantics become run provenance;
- one model interface works with the same data, loss, metrics, and exporter;
- strict failure is safer than accidentally training a partly loaded model.

Cons:

- custom Hub code is intentionally unsupported;
- some official checkpoints have architectures or state dictionaries that do
  not partition cleanly and therefore fail;
- upstream objectives are never invoked automatically; standard dense
  checkpoints use Segmentary dense losses, while reviewed query wrappers use the
  separate Segmentary Hungarian objective;
- Hub popularity/download counts are not evidence of accuracy on your dataset.

## Verification levels

1. **Config proof:** typed YAML merges and records the intended checkpoint.
2. **Load proof:** every expected pretrained tensor is audited.
3. **Processor proof:** normalization and channel order match the model card.
4. **Optimizer smoke:** a short real forward/backward run has finite outputs,
   loss, and every remaining trainable parameter has a finite gradient.
5. **Dataset benchmark:** only a fixed dataset/split/checkpoint/EMA/TTA protocol
   produces comparable mIoU.

The first four establish compatibility, not model quality. A new recipe should
not enter the catalog until they pass. Accuracy tables must state the fifth
protocol and must never mix source-model-card results with Segmentary runs.
The compact machine record for the six shipped recipe smokes is
[`hf-auto.json`](../../../benchmarks/model-catalog-smokes/hf-auto.json).

## Known rejection example

`Intel/dpt-large-ade` was inspected but is not shipped: its available checkpoint
reported an auxiliary branch plus missing fusion-neck BatchNorm state under the
current pinned Transformers loader. Segmentary rejected the partial load instead
of weakening the invariant.

Return to the [model config catalog](../../../../configs/models/README.md).
