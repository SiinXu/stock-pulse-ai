# Layer-Direction Ratchet

- Status: `Living`
- Last verified: 2026-08-29
- Related: [import-cycle ratchet](import-cycle-ratchet.md),
  [architecture overview](architecture-overview.md),
  [hot-path module size ratchet](hot-path-module-size-ratchet.md),
  `scripts/check_layer_direction.py`,
  `scripts/layer_direction_baseline.json`,
  issues [#1082](https://github.com/SiinXu/stock-pulse-ai/issues/1082),
  [#1555](https://github.com/SiinXu/stock-pulse-ai/issues/1555)

## Purpose

The bidirectional import-cycle ratchet (ADR-010) blocks new **pairs** but still
allows a one-way reverse edge that has not yet become a cycle, and it allowlists
known cycles without encoding the intended **direction**.

This ratchet enforces the directed layer shape:

```text
src.api → services → pipeline/stages → src.data_provider
```

Lower layers must not import higher ones. In particular:

| Forbidden reverse edge | Why |
| --- | --- |
| `src.data_provider` → `src.services` / `src.core` / `src.agent` / `src.api` | Providers are the leaf data adapters |
| `src.services` → `src.api` | HTTP transport is one-way |
| `src.core` / `src.agent` / `src.market` / `src.analyzer` → `src.api` | Domain and orchestration must not depend on transport |
| `src.core` pipeline/stages → `src.services` | Intended direction is services → pipeline |

The `src.core` → `src.services` rule is scoped to `src/core/pipeline.py` and
`src/core/stages/**` so package-level coarseness does not sweep unrelated core
modules.

## Measured scope

**Import-time** imports count: every import statement that runs while the module
object is being built. That is the module body plus every nested body that
executes eagerly:

| Placement | Counted? | Why |
| --- | --- | --- |
| Module body | Yes | Runs at import |
| `try` / `except` / `else` / `finally` | Yes | Runs at import |
| `if` / `else` (non-`TYPE_CHECKING`) | Yes | Runs at import |
| `with` / `async with` | Yes | Runs at import |
| `for` / `while` bodies and their `else` | Yes | Runs at import |
| `match` case bodies | Yes | Runs at import |
| Class bodies (at any eager nesting depth) | Yes | Runs at import |
| `if TYPE_CHECKING:` body | **No** | Never executes at runtime |
| `def` / `async def` bodies (any depth, methods included) | **No** | Deferred load; tracked separately, see below |

Before issue [#1555](https://github.com/SiinXu/stock-pulse-ai/issues/1555) the
guard iterated the module body's direct children only, so a reverse import
nested in `try` / `if` / `with` / a class body was silently dropped even though
it binds the name at import time. Those placements are now counted.

### `if TYPE_CHECKING:` exclusion

Imports guarded by `if TYPE_CHECKING:` never execute, so they are not package
edges and stay excluded. The exclusion is **binding-aware**: only names actually
bound to `TYPE_CHECKING` from `typing` or `typing_extensions` in that file are
honoured, in any of these forms:

```python
from typing import TYPE_CHECKING          # if TYPE_CHECKING:
from typing import TYPE_CHECKING as TC    # if TC:
import typing                             # if typing.TYPE_CHECKING:
import typing as t                        # if t.TYPE_CHECKING:
from typing_extensions import TYPE_CHECKING
```

A name that is rebound (`TYPE_CHECKING = True`), imported from somewhere else,
or never bound at all does **not** suppress an edge, and `if not TYPE_CHECKING:`
bodies are counted because they do execute at runtime.

### Function-body imports: advisory `lazy_exceptions` inventory

Lazy imports inside functions or methods stay **outside enforcement** so
intentional deferred loads remain available. They are no longer invisible: any
function-local reverse import whose `(path, from_package, to_package)` triple is
not also a **currently scanned import-time reverse edge** is recorded in the
baseline's `lazy_exceptions` section, and the guard prints the count plus any
drift:

```text
[layer-direction] NOTE: 5 function-local reverse import(s) tracked as advisory lazy_exceptions (not enforced)
[layer-direction] NOTE: lazy-inventory-growth: src/data_provider/foo.py: src.data_provider -> src.services: ...
[layer-direction] NOTE: lazy-inventory-shrink: src/data_provider/bar.py: src.data_provider -> src.services: ...
```

The dedupe is against what the scan just measured, not against the baseline
`exceptions` array. The two coincide only while the enforced ratchet is green,
and the scanned set is the more accurate answer to "does this deferred load tell
us anything the ratchet does not already count?".

#### What "advisory" means, exactly

| Situation | Guard exit code | CI |
| --- | --- | --- |
| A new function-local reverse import appears (`lazy-inventory-growth`) | `0` | green |
| A recorded function-local reverse import disappears (`lazy-inventory-shrink`) | `0` | green |
| The seed is stale in either direction | `0` | green |
| `lazy_exceptions` is present but malformed (bad shape, wrong `lazy_exception_count`, unsorted, duplicated, not a configured rule) | `1` | red, with `ERROR: invalid-baseline: …` |

Drift is advisory and **never** fails CI: it is not counted against
`hard_ceiling`, it does not change the exit code, and **no test pins the live
tree to the checked-in seed**. Adding or removing a deferred reverse import
cannot turn a PR red here, and cannot turn `main` red after that PR merges. The
one thing that is still fail-closed is a `lazy_exceptions` section the guard
cannot parse — that is a broken baseline, not drift, and it is rejected through
the same `ERROR: invalid-baseline:` line as the enforced section
(`tests/scripts/test_check_layer_direction.py` pins every malformed shape
through the CLI).

Refresh the seed with `--write-baseline` when you want the recorded list to
match the tree again. That is a tidiness step you may take at any time, never a
prerequisite for green CI. `--write-baseline` rewrites the advisory section from
the scan, so it also *repairs* a malformed one instead of refusing — the
fail-closed row above is the checking run, which is what CI executes. Its purpose is that moving a reverse import into a
function body no longer removes it from every inventory without a trace.

## Existing debt (introduction inventory)

Historical reverse edges are frozen in
`scripts/layer_direction_baseline.json` (hard ceiling = exception count at
introduction). Current categories:

1. **src.data_provider → src.services** (symbol/market helpers used by providers).
2. **pipeline/stages → src.services** (orchestration importing application
   services instead of receiving injected ports).

Separately, `lazy_exceptions` records the function-local reverse imports that
are not also scanned as import-time edges. It is advisory, has no ceiling, and
never changes the guard's exit code; see
[Function-body imports](#function-body-imports-advisory-lazy_exceptions-inventory).

### Cleanup plan

1. Move pure market/symbol helpers consumed by providers into a leaf module
   (`src.utils` or a `src.data_provider`-local helper) so providers stop importing
   `src.services`.
2. Inject service ports into pipeline/stages from the services layer (or share
   leaf adapters) so stages stop importing application services at module level.
3. Keep any `* → src.api` edge at zero forever; share DTOs via `src.schemas` or
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
   and not part of the package graph (prefer extraction). Note that this does
   **not** erase the coupling: it moves the edge into the advisory
   `lazy_exceptions` inventory, where it stays visible as a
   `lazy-inventory-growth` note. That note is informational — the guard still
   exits `0` and no test fails, so this remediation needs no baseline refresh to
   land. Run `--write-baseline` afterwards only if you want the recorded seed to
   match the tree.

Indenting a reverse import into a `try`, `if`, `with`, or class body is **not**
a fix. Those still execute at import time and are still counted.

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

Both guards share one import-placement traversal
(`scripts/check_import_layers.py::classify_import_modules`), so the import-time
scope described above applies identically to the cycle ratchet. Only the
layer-direction guard keeps the advisory `lazy_exceptions` inventory; the cycle
ratchet has no equivalent section because a lazy import cannot create a runtime
cycle.
