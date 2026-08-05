# Config-Access Ratchet

- Status: `Living`
- Last verified: 2026-08-05
- Related: [ADR-011](adr/ADR-011-config-access-ratchet.md),
  [ADR-003](adr/ADR-003-application-services-composition-root.md),
  [architecture overview](architecture-overview.md),
  `scripts/check_config_access.py`,
  `scripts/config_access_baseline.json`

## Purpose

Production code still reaches process-wide `Config` through the service-locator
`get_config()` accessor in many modules. That pattern works for a single-process
app but hides dependencies, forces tests to mutate globals, and slows extraction
of services with clear owners.

This ratchet does **not** rewrite every call site. It:

1. Measures bare `get_config()` call counts per production module (AST `Name`
   callees only).
2. Allows only counts listed in the checked-in baseline.
3. Fails CI when a **new** module introduces `get_config()` or an existing
   module's count **grows**.
4. Treats shrink as free: after you convert call sites, re-run
   `--write-baseline`.

## Preferred access path

For **new** modules and **files already under edit**, prefer:

1. **Constructor / parameter injection** of `Config` (or a narrow view) when the
   caller already owns a config instance.
2. **Composition-root access** via `get_application_services().config` when the
   process root is the correct owner (see ADR-003).

Do **not** add new bare `get_config()` call sites without PR justification.

### Out of scope for the scanner

| Pattern | Why |
| --- | --- |
| `system_config_service.get_config(...)` (attribute call) | Different API (persisted settings payload), not the process `Config` locator |
| `src/config.py` | Defines `get_config()` |
| `src/application_services.py` | Composition-root lazy fallback may call `get_config()` |
| `tests/**` | Test fixtures may still patch or call the locator |

## How to read a failure

```text
[config-access] ERROR: src/services/foo.py: new-module-get-config: ...
[config-access] ERROR: src/services/bar.py: get-config-count-growth: ...
[config-access] HINT: convert callers to injection / get_application_services().config ...
```

Meaning: the current tree has more bare `get_config()` sites than
`scripts/config_access_baseline.json` allows for that path (or the path is new).

Typical fixes:

1. Accept `config: Config | None = None` on the constructor or function and use
   the injected value when present.
2. Resolve defaults through `get_application_services().config` instead of
   `get_config()`.
3. Thread an existing config instance from a caller that already holds one.

## Commands

```bash
python scripts/check_config_access.py --self-test
python scripts/check_config_access.py
python scripts/check_config_access.py --write-baseline
```

The guard is wired into `./scripts/ci_gate.sh` deterministic checks (self-test
then live check), next to the other AST ratchets.

## Legitimate change path

| Change | Action |
| --- | --- |
| **Shrink** (convert existing sites) | Merge the code conversion, then run `--write-baseline` so the JSON drops counts/modules. Always allowed. |
| **Growth** (new intentional direct access) | **Not** allowed via `--write-baseline` (it refuses). Manually edit the baseline in the same PR, justify why injection/composition-root is not viable, and preferably file follow-up work to remove it. Prefer not to grow. |
| Accidental new site | Fix the code; do not edit the baseline. |

## Pilot conversions (V0)

The first shrink pilot converted three services that already had or could take
an injection seam:

| Module | Pattern |
| --- | --- |
| `src/services/history_service.py` | Optional `config` constructor arg; default via `get_application_services().config` |
| `src/services/portfolio_risk_service.py` | Existing optional `config` arg; default via composition root |
| `src/services/alert_worker.py` | Existing `config_provider` callable; default provider uses composition root |

Further conversions are incremental follow-ups under issue #625; each PR should
shrink the baseline without changing config semantics.
