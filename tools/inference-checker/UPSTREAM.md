# Bundled origin

Copied from Arian Izadi’s local `inference-checker` repository at commit
`4d1f170a1b39e80685650f4e2702c994b7bca2d7`.
The sibling checkout remains unchanged. Sample dataset binaries were not copied.
This source is maintained inside Segmentary; it is not a submodule.

The original config/scene bundle contract, legacy `rs19-config.json` fallback,
and `bun run inspect -- <bundle>` entry point remain supported. Segmentary adds
root-level launch and preparation commands. Local inspection no longer loads
analytics or remote fonts. The inspection launcher binds to loopback and accepts
`PORT` (default 3000).
