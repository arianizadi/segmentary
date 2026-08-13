# Installation

Segmentary deliberately does not declare PyTorch as an ordinary dependency. A CPU
laptop, CUDA workstation, and managed cluster need different PyTorch wheels, and
silently replacing the platform build is a common way to break an otherwise
healthy environment.

## Requirements

- Python 3.11 (the package currently declares `==3.11.*`);
- a PyTorch/torchvision pair compatible with your CPU, accelerator, driver, and
  operating system;
- enough storage for model weights, datasets, checkpoints, and caches;
- a GPU for practical training (config inspection, taxonomy checks, packaging,
  and many unit tests work on CPU).

Use the [official PyTorch installation selector](https://pytorch.org/get-started/locally/)
for your machine. Do not copy another host's CUDA index blindly.

## 1. Create an isolated environment

With `venv`:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
```

Conda/mamba environments are also fine. The important properties are Python
3.11, an explicit environment, and a recorded package set.

## 2. Install and verify PyTorch first

Run the command produced by the official selector, then check the actual runtime:

```bash
python - <<'PY'
import torch

print("torch:", torch.__version__)
print("compiled CUDA:", torch.version.cuda)
print("CUDA available:", torch.cuda.is_available())
print("visible GPUs:", torch.cuda.device_count())
if torch.cuda.is_available():
    print("GPU 0:", torch.cuda.get_device_name(0))
PY
```

An install command succeeding does not prove CUDA can initialize. If
`torch.cuda.is_available()` is false on a GPU machine, resolve the PyTorch wheel,
driver, container, or visibility issue before installing more packages.

## 3. Install Segmentary

From a source checkout:

```bash
git clone https://github.com/arianizadi/segmentary.git
cd segmentary
python -m pip install -e '.[dev]'
python -m pip check
```

The editable install exposes:

```text
segmentary-init
segmentary-verify
segmentary-overfit
segmentary-train
segmentary-eval
segmentary-export
segmentary-make-split
segmentary-table
segmentary-models
segmentary-progress
```

Check the entry points without downloading a model:

```bash
segmentary-init --help
segmentary-verify --help
segmentary-overfit --help
segmentary-train --help
segmentary-eval --help
segmentary-export --help
segmentary-make-split --help
segmentary-table --help
segmentary-models --help
segmentary-progress --help
```

For deployment/export support, install the optional extra only in a compatible
environment:

```bash
python -m pip install -e '.[export]'
python -m pip check
```

The repository pins the export stack used for its validated NVIDIA/CUDA profile.
TensorRT and GPU ONNX Runtime are platform-sensitive; install success is not a
backend parity test. Follow the [export guide](../guides/export-and-deployment.md)
before reporting a deployment result.

## 4. Run CPU-safe checks

```bash
python -m pytest -m 'not slow and not gpu'
ruff check src tests scripts
ruff format --check src tests scripts
```

Some tests are intentionally real-data, CUDA, ONNX Runtime, or TensorRT tests.
They skip or require the named fixture/extra. A skipped hardware test is not
evidence that the hardware path works; it is only evidence that the portable
suite handled the missing capability correctly.

## 5. Create a project outside the source tree

```bash
segmentary-init ~/segmentation-project --name baseline
cd ~/segmentation-project
git init
git add .
git commit -m "Initialize Segmentary project"
segmentary-train base.yaml model.yaml experiment.yaml --print-config
```

The generated configuration uses relative `data`, `taxonomy`, and `runs` paths,
so the project can move as one directory. Large datasets and model caches may
live elsewhere; set absolute paths in a private site override rather than
committing another user's mount layout.

Keep this project outside the cloned Segmentary source tree. Commit the intended
config, taxonomy, and split metadata again after editing them and before
training, so result provenance points to a clean project repository rather than
an untracked nested directory.

## Storage and caches

Hugging Face uses its standard cache unless `HF_HOME` is set:

```bash
export HF_HOME=/fast-storage/$USER/huggingface
```

Choose a location with enough space and appropriate backup/retention. Keep these
out of Git:

- raw or licensed datasets;
- Hub credentials and service tokens;
- checkpoints and TensorRT engines;
- run directories and generated caches.

For offline execution, download/approve weights first, set
`model.local_files_only: true`, and test the exact model ID/revision from the
offline environment.

## Cluster and multi-GPU notes

- Use your scheduler when one exists; otherwise use a persistent session.
- Select GPUs through the scheduler or `CUDA_VISIBLE_DEVICES`.
- Record `train.devices`, per-device batch, gradient accumulation, precision,
  and visible device information in the resolved config/environment record.
- Run a short distributed smoke before a multi-day campaign.
- Never change a shared environment or active source tree underneath running
  jobs.

## Installation choices

| Choice | Advantage | Cost | Use it when |
|---|---|---|---|
| Editable source install | examples, scripts, tests, and code stay together | source tree is required | development and research |
| Installed wheel | clean consumer boundary and packaged starter | repository-only reproduction files are elsewhere | library use and packaging QA |
| CPU PyTorch | easy config/taxonomy/unit checks | impractical training and no CUDA verification | laptops and CI |
| CUDA PyTorch | practical training and GPU evaluation | driver/wheel compatibility matters | workstation or cluster |
| Export extra | ONNX/ORT/TRT tools in one profile | large and accelerator-specific | deployment validation only |

## Common installation mistakes

- Installing an arbitrary `torch` wheel after a working platform build.
- Assuming a successful import proves the GPU kernel path works.
- Mixing Python 3.12/3.13 into a project that currently requires 3.11.
- Installing Segmentary into the system interpreter rather than an environment.
- Treating a hardware-dependent skipped test as a passed integration test.
- Committing dataset credentials, signed URLs, cache files, or checkpoints.
- Using an old config with a newer source tree without printing and validating
  the resolved config first.

Next: [Getting started](getting-started.md).
