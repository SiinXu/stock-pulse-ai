# ADR-011: Shrink-Only Direct Config-Access Ratchet

- Status: `Proposed`
- Decision date: 2026-08-05
- Decision owners: maintainers reviewing composition-boundary and DI hygiene PRs
- References: [Issue #625](https://github.com/SiinXu/stock-pulse-ai/issues/625),
  `scripts/check_config_access.py`,
  [config-access ratchet](../config-access-ratchet.md),
  [ADR-003](ADR-003-application-services-composition-root.md)

## Context

ADR-003 introduced `ApplicationServices` as a lightweight composition root, but
production code still calls `get_config()` widely. That preserves single-process
compatibility while hiding dependencies from signatures and pushing tests toward
global mutation.

A full rewrite of every call site is out of scope. The repository already uses
AST-based shrink-only ratchets for broad exceptions, legacy facade imports, and
bidirectional package pairs. The same enforcement shape fits direct config
access: inventory the debt, block unexplained growth, and convert modules
incrementally.

## Decision

1. Maintain a checked-in per-module count of **bare** `get_config()` call sites
   in production paths (`src/`, `data_provider/`, `api/`, `bot/`, and top-level
   entrypoints), measured via AST `Name` callees only.
2. CI fails when a module's count grows or a new production module introduces
   `get_config()`.
3. `--write-baseline` may **shrink** the inventory to the current measurement
   and **refuses growth**. Intentional new sites require a manual baseline edit
   plus PR justification.
4. Prefer constructor/param injection of `Config`, or
   `get_application_services().config`, over new `get_config()` sites for new
   and touched code.
5. Exclude `src/config.py` (definition) and `src/application_services.py`
   (composition-root lazy fallback). Attribute-style
   `*.get_config(...)` APIs (for example system-config payloads) are out of
   scope.

This ADR authorizes the enforcement mechanism and the incremental conversion
pattern. It does not mandate a third-party DI framework, a big-bang migration,
or changes to config semantics / env loading.

## Consequences

- New unexplained direct `get_config()` usage is blocked by the deterministic CI
  gate.
- Contributors get an explicit failure message and a documented shrink path.
- Residual sites remain until dedicated follow-up work; the baseline is honest
  inventory, not an endorsement of every locator call.
- Composition-root adoption stays incremental and behavior-preserving when
  defaults still resolve to the same process singleton.
