# transunet architecture provenance

Source: https://github.com/Beckschen/3D-TransUNet/tree/9f18182f5f7b26fc81e2f2d70fb5c40ee8a58908/nn_transunet/networks

Commit: `9f18182f5f7b26fc81e2f2d70fb5c40ee8a58908`. License: Apache-2.0 (full text in `LICENSE`).

The published encoder-transformer variant is selected. Replaced legacy prediction base with nn.Module (external native-volume harness handles prediction), removed unused decoder construction and matching helpers, disabled pretrained loading, removed ViT weight-import methods and paths, deep-copied mutable ViT config per construction. Encoder/CNN decoder forward computations are upstream. Dense raw final logits are selected by adapter; auxiliary heads are excluded from the objective. This is an architecture comparison, not a reproduction of the paper training protocol. Ruff formatting was applied; retained upstream source and adapters pass the project type check; compatibility annotations were corrected. No model weights or runtime network downloads are included.

The adapter replaces unused auxiliary classification heads with Identity when deep supervision is disabled; the final classifier and its native forward output are retained.
