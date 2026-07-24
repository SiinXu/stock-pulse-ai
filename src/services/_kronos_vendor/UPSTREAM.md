# Vendored Kronos Inference

- Upstream repository: `shiyu-coder/Kronos`
- Upstream commit: `67b630e67f6a18c9e9be918d9b4337c960db1e9a`
- Source files: `model/kronos.py`, `model/module.py`
- License: MIT; see `LICENSE`

The vendored source retains the official model and predictor implementation.
StockPulse adds provenance/SPDX headers and changes the upstream
`from model.module import *` statement to the package-relative
`from .module import *` form. Trailing whitespace and excess blank lines are
normalized. No model architecture or inference algorithm is changed.

When updating, compare both source files against an immutable upstream commit,
re-apply only the package-relative import, verify the upstream license, run the
mocked contract suite, and run the opt-in real-inference test with reviewed
local weights.
