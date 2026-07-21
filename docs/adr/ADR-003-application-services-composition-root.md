# ADR-003: Use A Lightweight ApplicationServices Composition Root

- Status: `Accepted (retrospective)`
- Decision date: 2026-07-20
- Recorded: 2026-07-21
- Decision owners: StockPulse maintainers
- References: [PR #83](https://github.com/SiinXu/stock-pulse-ai/pull/83), merge `cc944703f6ab5f839a17e5eea9ef1c46ef583a01`, [`src/application_services.py`](../../src/application_services.py)

## Context

Configuration, database, search, and analysis-task services were reached through
separate module-level singleton accessors. Startup had no single place to hold
those process-wide dependencies, and isolated tests had to patch each accessor.

A replacement still had to preserve startup order, lazy imports, and existing
singleton reset behavior. The repository did not have process-wide cache,
rate-limiter, or shared-pool services to add, while `SystemConfigService` already
had an app-scoped FastAPI lifespan.

## Decision

Use `ApplicationServices` as a lightweight process composition root for the four
existing process-wide service accessors:

- `Config`
- `DatabaseManager`
- `SearchService`
- `AnalysisTaskQueue`

Explicitly supplied values are retained for startup or test isolation. An unset
value resolves lazily through its existing accessor and is not cached by the
root, preserving current singleton and reset semantics. Property imports remain
lazy to avoid module import cycles. `main.py` and `server.py` install the root.

Adoption is incremental. `src.storage.get_db()` currently delegates through the
root; most config, search, and queue callers still use their existing accessors.
This ADR does not authorize a big-bang caller migration, invent new global
services, or move app-scoped lifespan services into the process root.

## Consequences

- Startup and tests have a stable dependency-injection seam without changing
  default runtime behavior.
- Existing singleton accessors remain compatibility boundaries during gradual
  migration.
- Lazy resolution avoids stale values after a singleton reset and reduces import
  cycle risk.
- The root adds one global indirection and is only partially adopted; documents
  and tests must not claim that every runtime dependency is composed through it.
- Reverting the implementation requires no configuration or data migration.
