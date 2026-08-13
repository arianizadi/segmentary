# Portable developer shortcuts. Override variables on the command line, e.g.
#   make train CONFIGS="base.yaml model.yaml experiment.yaml" DEVICES=1

PY       ?= python
RUFF     ?= ruff
REPO     := $(shell pwd)
CONFIGS  ?= configs/base.yaml configs/models/segformer_b2.yaml configs/curricula/cs_only.yaml
SEED     ?= 0
DEVICES  ?= auto
CKPT     ?=
DATASET  ?= cityscapes
ROOT     ?=
SPACE    ?= rail_union
MAPPING  ?= $(DATASET)
LOADER   ?= $(DATASET)

export PYTHONPATH := $(REPO)/src

.PHONY: help install install-export init test test-fast lint gpus verify overfit \
        train eval export table clean sweep-rail-examples

help:
	@echo "Segmentary targets:"
	@echo "  make install             install editable library + dev tools (PyTorch first)"
	@echo "  make install-export      install the platform-specific export extra"
	@echo "  make init DEST=project   create a portable starter project"
	@echo "  make test                full suite (hardware/data tests may skip)"
	@echo "  make test-fast           skip slow and GPU tests"
	@echo "  make lint                Ruff check + format check"
	@echo "  make verify ROOT=...     verify DATASET/LOADER/MAPPING/SPACE"
	@echo "  make overfit             tiny memorization check for CONFIGS"
	@echo "  make train               train CONFIGS"
	@echo "  make eval CKPT=...       evaluate one exact checkpoint"
	@echo "  make export CKPT=...     run the validated export CLI"
	@echo "  make table               build checked tables from RUNS (optional STAGE/EXPERIMENT)"
	@echo ""
	@echo "Current CONFIGS: $(CONFIGS)"

install:
	$(PY) -m pip install -e ".[dev]"
	$(PY) -m pip check

install-export:
	$(PY) -m pip install -e ".[export]"
	$(PY) -m pip check

init:
	@test -n "$(DEST)" || (echo "usage: make init DEST=my-project"; exit 1)
	$(PY) -m segmentary.init_project "$(DEST)"

test:
	$(PY) -m pytest

test-fast:
	$(PY) -m pytest -m "not slow and not gpu"

lint:
	$(RUFF) check src tests scripts
	$(RUFF) format --check src tests scripts

gpus:
	@nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu --format=csv

verify:
	@test -n "$(ROOT)" || (echo "usage: make verify ROOT=/path/to/data [DATASET=... LOADER=folder MAPPING=... SPACE=...]"; exit 1)
	$(PY) -m segmentary.verify --dataset "$(DATASET)" --loader "$(LOADER)" \
		--mapping "$(MAPPING)" --root "$(ROOT)" --space "$(SPACE)"

overfit:
	$(PY) -m segmentary.overfit $(CONFIGS) --seed $(SEED)

train:
	$(PY) -m segmentary.train $(CONFIGS) --seed $(SEED) --devices $(DEVICES)

eval:
	@test -n "$(CKPT)" || (echo "usage: make eval CKPT=runs/<run>/<stage>/last.ckpt"; exit 1)
	$(PY) -m segmentary.eval $(CONFIGS) --ckpt "$(CKPT)"

export:
	@test -n "$(CKPT)" || (echo "usage: make export CKPT=runs/<run>/<stage>/last.ckpt"; exit 1)
	$(PY) -m segmentary.export $(CONFIGS) --ckpt "$(CKPT)"

RUNS ?= runs
REPORT ?= reports/results
CLASSES ?=
STAGE ?=
EXPERIMENT ?=
table:
	$(PY) -m segmentary.results_table --runs "$(RUNS)" --out "$(REPORT)" \
		$(if $(STAGE),--stage "$(STAGE)",) \
		$(if $(EXPERIMENT),--experiment "$(EXPERIMENT)",) \
		$(if $(CLASSES),--classes $(CLASSES),)

# Reproduction helper, deliberately named as such instead of being the generic
# default. Long campaigns should use a scheduler/runner with provenance checks.
sweep-rail-examples:
	@for curriculum in cs_only rs_only cs_rs joint_cs_rs; do \
		for seed in 0 1 2; do \
			$(MAKE) train CONFIGS="configs/base.yaml configs/models/segformer_b2.yaml configs/curricula/$$curriculum.yaml" SEED=$$seed || exit 1; \
		done; \
	done

clean:
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
	rm -rf .pytest_cache .ruff_cache
