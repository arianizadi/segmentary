# U-Mamba, SegMamba and Mamba source attribution

The adjacent `models_mamba.py` and `mamba_scan.py` are typed adaptations by
Segmentary, not verbatim upstream snapshots. They contain no learned weights.

* **U-Mamba**, Jun Ma, Feifei Li and Bo Wang, Apache-2.0.
  Upstream: <https://github.com/bowang-lab/U-Mamba>
  Commit: `28459e33ca03769800dd35e23c6e62491d1925b5`.
  Source files: `umamba/nnunetv2/nets/UMambaBot_3d.py` and `UMambaEnc_3d.py`.
  Full upstream license: [LICENSE-UMAMBA](LICENSE-UMAMBA).
* **SegMamba**, Guotai Wang's team / Zhaohu Xing and collaborators.
  Upstream: <https://github.com/ge-xing/SegMamba>
  Commit: `cff35970e0c542ad940b5701267f1ac888298b06`.
  `model_segmamba/segmamba.py` declares Copyright (c) MONAI Consortium,
  Apache-2.0. The same Apache-2.0 text is retained in LICENSE-UMAMBA.
  MONAI UNETR decoder blocks are imported from the installed MONAI dependency.
* **Mamba**, Copyright (c) 2023, Tri Dao, Albert Gu, Apache-2.0.
  SegMamba's pinned `mamba/mamba_ssm/modules/mamba_simple.py` and
  `mamba/mamba_ssm/ops/selective_scan_interface.py` define the v3 extension
  and the real selective recurrence. Full license: [LICENSE-MAMBA](LICENSE-MAMBA).
  Original Mamba project: <https://github.com/state-spaces/mamba>.

## Declared modifications

The portable backend computes the real input-dependent Mamba recurrence through
an associative affine prefix scan in checkpointed chunks. This changes execution
and floating-point reassociation, not the recurrence. It preserves Mamba's causal
depthwise convolution, input-dependent B/C and delta, negative exponential A,
skip D, SiLU gate and output projection. SegMamba retains separately parameterized
forward, reverse and slice-interleaved branches, including the upstream asymmetric
delta-projection initialization. Native `mamba-ssm` selective-scan dispatch is an
explicit option; missing or incompatible native kernels never trigger fallback.

U-Mamba retains the residual convolutional stem, resolution stages, nearest-neighbor
upsampling plus 1x1 projection, and residual decoder. Encoder Mamba switches to
channel tokens when spatial token count is no larger than the channel count.
Same-channel BasicBlockD blocks are expressed directly in PyTorch rather than
requiring the entire dynamic-network-architectures package. The upstream depth
reductions are retained. Instead of invoking nnU-Net's dataset planner, callers
declare fixed isotropic stage widths and a patch size. These are architecture
experiments in Segmentary's shared training protocol, not claims of reproducing
the original paper's automatic plans or training recipe. Deep supervision is off.

SegMamba retains four downsampling stages, GSC blocks, residual tri-direction
Mamba mixers, normalized channel MLP outputs, and MONAI UNETR convolutional skips
and upsampling decoder. The upstream head hard-codes 48 input features; the
adaptation uses the declared first-stage width so reduced-width ablations work.
Unused layer-scale/drop-path/projection methods are omitted. Mixer autocast is
disabled to accumulate recurrence parameters in FP32. Double precision is retained
for independent numerical and gradient checks.

The wrapper end-pads to a declared patch compatible with the architecture and
crops logits back to the input tensor size. Input larger than the declared patch
fails and must use sliding windows. Patch plans ensure at least two spatial
positions per axis in the deepest normalized stage; no normalization layer is
silently swapped. SegMamba slice counts must divide stage token counts.

Scratch-only model options reject checkpoints, pretrained flags and unknown
keys. Architecture widths/depths, patch padding and scan backend are available in
the constructed model's `resolved_model_options`; reduced smoke configurations
are explicitly labeled in metadata and are not claimed as paper-size models.
