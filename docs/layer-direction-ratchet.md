# Layer-Direction Ratchet

- Status: `Living`
- Last verified: 2026-08-12
- Related: [import-cycle ratchet](import-cycle-ratchet.md),
  [architecture overview](architecture-overview.md),
  [hot-path module size ratchet](hot-path-module-size-ratchet.md),
  `scripts/check_layer_direction.py`,
  `scripts/layer_direction_baseline.json`,
  issues [#1082](https://github.com/SiinXu/stock-pulse-ai/issues/1082)

## Purpose

The bidirectional import-cycle ratchet (ADR-010) blocks new **pairs** but still
allows a one-way reverse edge that has not yet become a cycle, and it allowlists
known cycles without encoding the intended **direction**.

This ratchet enforces the directed layer shape:

```text
api → services → pipeline/stages → src.data_provider
```

Lower layers must not import higher ones. In particular:

| Forbidden reverse edge | Why |
| --- | --- |
| `src.data_provider` → `src.services` / `src.core` / `src.agent` / `api` | Providers are the leaf data adapters |
| `src.services` → `api` | HTTP transport is one-way |
| `src.core` / `src.agent` / `src.market` / `src.analyzer` → `api` | Domain and orchestration must not depend on transport |
| `src.core` pipeline/stages → `src.services` | Intended direction is services → pipeline |

Only **module body** imports count. Lazy imports inside functions or methods are
ignored so intentional deferred loads remain available.

The `src.core` → `src.services` rule is scoped to `src/core/pipeline.py` and
`src/core/stages/**` so package-level coarseness does not sweep unrelated core
modules.

## Existing debt (introduction inventory)

Historical reverse edges are frozen in
`scripts/layer_direction_baseline.json` (hard ceiling = exception count at
introduction). Current categories:

1. **src.data_provider → src.services** (symbol/market helpers used by providers).
2. **pipeline/stages → src.services** (orchestration importing application
   services instead of receiving injected ports).

### Cleanup plan

1. Move pure market/symbol helpers consumed by providers into a leaf module
   (`src.utils` or a `data_provider`-local helper) so providers stop importing
   `src.services`.
2. Inject service ports into pipeline/stages from the services layer (or share
   leaf adapters) so stages stop importing application services at module level.
3. Keep any `* → api` edge at zero forever; share DTOs via `src.schemas` or
   dedicated contracts.
4. After each fix, run `--write-baseline` to shrink the allowlist. **Never raise
   `hard_ceiling` or expand exceptions to green CI.**

## How to read a failure

```text
[layer-direction] ERROR: new-reverse-edge: src/data_provider/foo.py: src.data_provider -> src.services: ...
[layer-direction] HINT: break the reverse import or see docs/layer-direction-ratchet.md ...
```

Typical fixes:

1. Extract a stdlib-leaning leaf helper both sides may import one-way.
2. Invert ownership so only the higher layer depends on the lower one.
3. Use a function-body lazy import only when the dependency is truly optional
   and not part of the package graph (prefer extraction).

## Commands

```bash
python scripts/check_layer_direction.py --self-test
python scripts/check_layer_direction.py
python scripts/check_layer_direction.py --write-baseline
```

Wired into `./scripts/ci_gate.sh` deterministic checks (self-test then live
check), next to the import-cycle ratchet.

## Legitimate change path

| Change | Action |
| --- | --- |
| **Shrink** (remove a reverse edge) | Merge the code fix, then run `--write-baseline`. Always allowed. |
| **Growth** (new reverse edge) | **Not** allowed via `--write-baseline`. Fix the code. Manual baseline expansion requires explicit PR justification and must not raise `hard_ceiling`. Prefer not to grow. |
| Accidental new reverse edge | Fix the code; do not edit the baseline. |

## Relationship to the import-cycle ratchet

| Guard | Blocks |
| --- | --- |
| `check_import_layers.py` | New bidirectional package pairs |
| `check_layer_direction.py` | New one-way reverse edges against the layer direction |

Both use shrink-only baselines. A reverse edge may appear in both inventories
when it is also half of a bidirectional pair; removing it shrinks both.
