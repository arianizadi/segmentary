# Research stack notes

> Historical design note, not installation instructions.
>
> Use [Installation](tutorials/installation.md) for setup and
> [`pyproject.toml`](../pyproject.toml) for the supported dependency contract.
> Those files are authoritative when this note and the current package differ.

This page records the durable conclusions that shaped Segmentary's dependency and
model boundaries. It intentionally omits the original raw research-agent dump:
that dump mixed proposals, contradictory environment observations, and commands
for package versions that were never adopted. Running those commands against a
working environment would be unsafe.

## Why the stack is deliberately constrained

Semantic-segmentation projects combine a platform-specific PyTorch build with
fast-moving model libraries, image augmentation, distributed training, and
optional deployment runtimes. A version that imports successfully can still be
wrong for the host GPU, checkpoint layout, image processor, or TensorRT runtime.

Segmentary therefore follows four rules:

1. Install and verify the platform's PyTorch and torchvision pair first.
2. Pin ordinary Python dependencies together in `pyproject.toml`.
3. Keep accelerator-specific export tooling in the optional `export` extra.
4. Admit model recipes through exact load, preprocessing, gradient, and output
   checks rather than assuming a library or Hub identifier is compatible.

The project does **not** install PyTorch as a normal package dependency. This
prevents an editable install or wheel upgrade from silently replacing a working
CPU, CUDA, ROCm, or other accelerator build.

## Current authority map

| Question | Authoritative source |
|---|---|
| How do I install Segmentary? | [Installation tutorial](tutorials/installation.md) |
| Which versions does the package declare? | [`pyproject.toml`](../pyproject.toml) |
| Which models are supported or blocked? | [Model recipe index](../configs/models/README.md) |
| How are Hub checkpoints admitted? | [Hugging Face Auto component](catalog/components/hf-auto/README.md) |
| How do native backbones, necks, and heads compose? | [Native component guides](catalog/README.md) |
| Which export paths are verified? | [Export and deployment](guides/export-and-deployment.md) |
| What evidence is compatibility-only versus a quality benchmark? | [Benchmark ledger](benchmarks/README.md) |

## Durable compatibility findings

### PyTorch and accelerators

- A wheel's CUDA runtime must be compatible with the installed driver. A
  successful `pip install` is not evidence that CUDA can initialize.
- Verify `torch.__version__`, `torch.version.cuda`, device visibility, and a real
  tensor operation before starting a campaign.
- Never change a shared environment or source checkout beneath active jobs.
- Segmentary records the reference host's tested pair under
  `[tool.segmentary.install]`; it is reproduction metadata, not a universal
  install command.

### Image processing

- Albumentations and OpenCV are pinned because unconstrained image-library
  upgrades can change transforms or mask behavior without changing a model
  config.
- Masks use nearest-neighbor interpolation and ignore value `255` through resize
  and padding operations.
- A Hugging Face model is accepted only when its image-processor rescaling,
  normalization, and channel order can be reproduced exactly by Segmentary.

### Hugging Face checkpoints

- `hf_auto` is for complete dense semantic-segmentation checkpoints handled by
  `AutoModelForSemanticSegmentation`. It is not a generic adapter for query,
  panoptic, instance, video, or task-conditioned models.
- Model IDs alone are mutable. Catalog recipes pin immutable revisions and audit
  checkpoint layout, classifier mismatch, processor behavior, inactive
  parameters, and gradient reachability.
- `trust_remote_code` remains disabled. Supporting arbitrary repository code
  would turn a data/config input into executable code and weaken reproducibility.
- Query-based models need their native output and matching objective. Collapsing
  query masks into dense logits for cross-entropy is an explicit experimental
  ablation, not equivalent training.

### Native and third-party model components

- Native Segmentary models use typed backbone, neck, primary-head, and auxiliary-
  head specs with compatibility checks. Unknown or irrelevant options fail
  instead of being forwarded as arbitrary keyword arguments.
- The SMP family is useful for audited encoder/decoder recipes, but an installed
  encoder name is not automatically a supported Segmentary recipe. Preprocessing,
  feature geometry, gradient reachability, and minimum input size still matter.
- A compatibility smoke proves construction and optimization wiring. It does not
  establish accuracy, convergence, robustness, or deployment performance.

### Export runtimes

- ONNX export is accepted only after comparison with the PyTorch output on real
  inputs.
- TensorRT packages and engines are CUDA/driver-specific. Segmentary keeps them in
  a separate optional extra and records backend versions and precision evidence.
- FP16 or INT8 latency without parity and accuracy-degradation measurements is
  incomplete evidence. An untrained-model export can prove mechanics and
  backend parity, but never model quality.

## Research records versus library guidance

The bundled Cityscapes/RailSem19 configs, benchmark records, and reviewed
[project history](project-history.md) preserve one demanding rail-transfer case
study. They helped expose label-space, thin-boundary, curriculum-handoff, and
common-evaluation problems. They are examples, not required defaults and not
evidence that a result generalizes to another dataset.

For a new project, start with the portable tutorials, create your own taxonomy
and dataset config, run verification and a tiny overfit check, and only then
select or admit a larger model recipe.

## When changing the stack

Treat a dependency or model-library update as a compatibility change:

1. make the change in an isolated environment;
2. run `python -m pip check`;
3. run the CPU-safe regression suite;
4. run the applicable real-data, GPU, distributed, and export tests;
5. repeat processor/output parity and model-catalog admission checks;
6. record exact versions and evidence before updating the declared pins.

Do not preserve an old pin merely because it once worked, and do not replace it
merely because a newer release exists. The relevant question is whether the
current supported contracts remain proven.
