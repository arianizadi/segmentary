# Task07 checkpoint retention audit

**There were no unreferenced intermediate Torch checkpoints to delete.** The medical backend already removes older generations after committing the replacement index. No remote files were changed or deleted by this audit.

Observed on HDRFS at **2026-09-14 04:45:46 UTC** (September 13 evening Pacific). This is a point-in-time inventory; the continuation campaign can change after it starts.

| Location / purpose | Physical files | File bytes | GiB |
| --- | ---: | ---: | ---: |
| Original campaign: indexed Torch checkpoints, 27 models | 53 | 21,545,739,900 | 20.066 |
| New continuation: indexed Torch checkpoints, 27 models | 53 | 21,545,091,132 | 20.065 |
| New continuation: preserved original checkpoint evidence | 53 | 21,545,739,900 | 20.066 |
| Original campaign: active nnU-Net best/latest and their RNG companions | 4 | 2,256,806,568 | 2.102 |
| Unindexed Torch generations, either campaign | **0** | **0** | **0** |
| In-progress continuation staging checkpoint files | **0** | **0** | **0** |

Bytes are regular-file lengths, not filesystem allocated blocks. The audit enumerated checkpoint files and matched names against every published `checkpoint-index.json`; it did not deserialize or rehash checkpoint payloads. All 27 original Torch campaign states were completed. All 27 continuation workspaces were published and queued. nnU-Net was still training and was left alone.

## Why an earlier best checkpoint stays

- **Latest** contains the newest recoverable training state. Training continuation must restore this state, including optimizer, scheduler, scaler, and RNG state.
- **Best** contains the checkpoint selected by the existing validation rule. It can be from an earlier epoch and remains necessary for the reported evaluation. Its lower epoch number does not make it disposable.
- **Final** identifies the completed training state. Here it points to the same physical generation as latest.
- **Continuation-parent** files preserve the exact original bytes that were migrated to the reviewed implementation. The new active generations have a different binding identity; these original audit copies are intentional.

For each of the 26 ordinary completed Torch runs, two physical files support three aliases: an earlier best and one shared latest/final. Mask2Former has one physical file shared by all three aliases. Thus 81 logical aliases use 53 files per campaign. The original campaign's 26 best-only files total 10,488,076,934 bytes; its 26 latest/final files total 10,488,076,870 bytes; the shared Mask2Former file is 569,586,096 bytes.

## Existing protection and verification

[`_save_checkpoint`](../../../../../src/segmentary/medical/torch_backend.py) writes and synchronizes a fresh generation, atomically publishes the alias index, and then removes generation files absent from that index. A failed index publication retains the previous resumable checkpoint. An orphan left by that interruption is removed after the next successful save.

[`test_medical_checkpoint_retention.py`](../../../../../tests/test_medical_checkpoint_retention.py) adds two focused passing regressions: latest rollover preserves an earlier best and continuation-parent evidence, while the aliases share files; failed publication preserves the prior bytes and the next save removes its orphan. No training source change was needed.

Any future manual recovery cleanup must first establish a quiescent workspace with the existing stage lock, verify all indexed files and continuation references, and target only unindexed generation files. An active import, training/evaluation stage, or unfinished checkpoint publication is not a cleanup target.

This inventory covers the original `task07-scratch-screen-20260913` and new `task07-performance-continuation-20260914` campaigns under `/data/izadia1/projects/segmentary-runs/pancreas`. It does not claim that other projects have no checkpoint accumulation. The separate generic RTIS callback in [`curriculum.py`](../../../../../src/segmentary/curriculum.py) currently retains all periodic snapshots (`save_top_k=-1`); changing that policy is outside this Task07 cleanup.
