# ADR-010: Shrink-Only Import-Cycle Ratchet

- Status: `Proposed`
- Decision date: 2026-08-05
- Decision owners: maintainers reviewing package-boundary hygiene PRs
- References: `scripts/check_import_layers.py`,
  [import-cycle ratchet](../import-cycle-ratchet.md),
  [ADR-006](ADR-006-behavior-preserving-module-decomposition.md)

## Context

Module-level bidirectional imports between top-level packages (for example
`src.config` ↔ `src.services`) accumulate as convenient shortcuts. Nothing in
CI previously prevented new pairs from landing, so package-layer debt only grew.
A related concern (ADR-006 legacy facades) already uses a shrink-only AST
baseline; the same enforcement shape fits package-pair cycles.

Verified at introduction: configuration imported
`src.services.stock_list_parser.split_stock_list` from three sites, contributing
to `src.config` ↔ `src.services` and `src.config_parts` ↔ `src.services`. The
helper is pure separator logic and belongs on a leaf path.

## Decision

1. Maintain a checked-in allowlist of **bidirectional package pairs** measured
   from production module-level imports (`src.<subpkg>` and root packages
   `data_provider` / `api` / `bot` / entrypoints).
2. CI fails on any pair not listed in the baseline.
3. `--write-baseline` may **shrink** the allowlist to the current measurement
   and **refuses growth**. Intentional new pairs require a manual baseline edit
   plus PR justification.
4. Lazy (function-body) imports are out of scope for edge construction so
   deferred loads remain available as an escape hatch without inventing pairs.
5. Prefer breaking cycles by extracting stdlib-only leaf utilities or one-way
   ownership rather than expanding the baseline.

This ADR authorizes the enforcement mechanism and the leaf-extraction pattern
used to remove the config→services stock-list edge. It does not mandate a
complete layered architecture rewrite or ban all remaining baseline pairs.

## Consequences

- New bidirectional package cycles are blocked by the deterministic CI gate.
- Contributors get an explicit failure message and a documented shrink path.
- Residual pairs remain until dedicated follow-up work; the baseline is honest
  inventory, not an endorsement of every cycle.
- Package identity is coarse (`src.services` not per-file), so intra-package
  cycles are not covered by this ratchet.
