# Instance and panoptic comparison reports

Generate a model page with native-resolution metrics, per-class results, separately measured model and pipeline speed, process VRAM peaks, and checkpoint/data provenance. These reports are independent of the running semantic RTIS campaign and its publisher.

```bash
python -m segmentary.objects.reports configs/examples/instance.yaml \
  --checkpoint runs/my-instance-run/best.pt \
  --out docs/results/my-instance-comparison/eomt-large \
  --name 'EoMT Large — instance' \
  --warmup 3 --reference
```

Use a panoptic config for PQ/SQ/RQ. The validation split in the config defines the exact evaluation image set; unrelated files in the image directory are excluded. The checkpoint must match the task and model configuration. Its category mapping is carried into validation splits, including splits that declare only a subset of categories. Output directories must be new and outside evaluation image/mask trees.

`--reference` compares the exported predictions on the same native pixels against official COCO mask evaluation or the COCO panoptic API. Install the pinned benchmark requirements from `requirements/object-benchmark.txt` for both reference evaluators. Reference disagreement yields a nonzero exit while preserving the report and difference details. Without this option, the page explicitly says reference equivalence was not checked.

Create a linked comparison index:

```bash
python -m segmentary.objects.reports \
  --compare docs/results/my-instance-comparison/eomt-large/report.json \
            docs/results/my-instance-comparison/mask2former/report.json \
  --out docs/results/my-instance-comparison/README.md
```

The index groups rows by task and exact dataset fingerprint, so different datasets or label revisions do not share an undifferentiated results table. Every model name links to its full Markdown page. Scores use percentages and missing measurements use an em dash. No seed averages or uncertainty terms are invented.

## Metrics and exported artifacts

- Instance: all-area mask AP across IoU 0.50 through 0.95, AP50, AP75 and AR100; per-class scores and non-crowd ground-truth object counts.
- Panoptic: PQ, SQ and RQ; thing/stuff groups; per-class scores, true positives, false positives and false negatives.
- `report.json`: machine-readable metrics, all timings, input hashes and provenance.
- `README.md`: reviewer-facing model page, per-class tables, timing/memory protocol and reference status.
- `predictions/predictions.json`: exact evaluation image IDs, categories and native predictions. Instance masks use COCO RLE; panoptic masks use RGB segment-ID PNGs. Instance reports also write `instances.json`.

Undefined classes are left missing rather than silently reported as zero. Panoptic classes with evaluation support but no match correctly have zero SQ. Metrics accumulate over the complete dataset, not averages of per-image AP/PQ.

## Measurement protocol

Evaluation is batch size one in float32, even if training used another precision. Model warmup defaults to three forwards on the first image. CUDA and MPS are synchronized at timing boundaries.

**Model-only** measures the query-model forward after resize and host-to-device transfer. **End-to-end** includes image and target decoding, image normalization/resize, transfer, forward, native-resolution postprocessing and moving predictions to CPU. It excludes metric accumulation, prediction-file export and hashing. Because target decoding is included, it is an evaluation-pipeline throughput measurement, not a deployment service benchmark. File caches are not flushed. Mean, median and p95 latency and individual image timings are retained, alongside throughput over the full pass.

CUDA allocated and reserved peaks are recorded after warmup and include loaded model weights. These are this process's PyTorch allocator counters, not total GPU usage and not training VRAM. CPU/MPS reports leave CUDA memory fields empty. GPU model, compute capability, memory available at the end, CUDA runtime, host platform and thread count are recorded when available. GPU exclusivity is not enforced; shared-GPU contention can affect measurements. Use an idle GPU for publishable speed comparisons and keep input sizes, precision, hardware and thresholds explicit.

## Provenance and comparability

The report records SHA256 of the full checkpoint, its embedded architecture/config/step, the resolved evaluation config, evaluation Git state, relevant package versions and category mapping. The dataset fingerprint includes annotation JSON, every evaluated image and every panoptic label PNG. Editing label pixels changes the fingerprint and separates comparison groups.

Initializer configuration is included, but historical checkpoints may lack a hash of the external initializer used before training. A path or Hub model name alone does not prove the external initializer's exact bytes. Full checkpoint bytes are always hashed. The command verifies the captured checkpoint hash after loading, after inference, and before report publication; if a live `best.pt` changes, it aborts instead of attributing old predictions to new weights. Prefer an immutable checkpoint copy. Evaluation thresholds and input sizes are recorded rather than silently standardized across reports; inspect them before claiming a fair comparison. These pages measure the supplied checkpoint on the selected data and do not establish generalization beyond that split.

## Tests

```bash
python -m pytest tests/test_object_reports.py tests/test_object_reference.py -q
```

Report tests run real tiny EoMT checkpoints on native masks, compare against both official evaluators when installed, preserve nonsequential ground-truth image IDs, exclude unlisted image files, verify provenance and timing fields, and check linked comparison grouping. Real dataset/GPU results require the separately documented benchmark recipe.
