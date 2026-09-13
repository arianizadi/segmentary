# mednext architecture provenance

Source: https://github.com/MIC-DKFZ/MedNeXt/tree/0b78ed869fbd1cc2fd38754d2f8519f1b72d43ba/nnunet_mednext/network_architecture/mednextv1

Commit: `0b78ed869fbd1cc2fd38754d2f8519f1b72d43ba`. License: Apache-2.0 (full text in `LICENSE`).

Imports made package-relative; removed executable profiling example; no architectural changes. Ruff formatting was applied; retained upstream source and adapters pass the project type check; compatibility annotations were corrected. No model weights or runtime network downloads are included.

The obsolete checkpoint dummy is retained as a nontrainable buffer; calls explicitly use modern non-reentrant checkpointing. This removes unused trainable state while preserving the network computations.
