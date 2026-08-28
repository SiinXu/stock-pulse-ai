# Structured readiness / self-check

Issue: [#1071](https://github.com/SiinXu/stock-pulse-ai/issues/1071)

## Purpose

Operators and first-run surfaces need a **single, fail-closed** readiness projection for:

- market data providers
- LLM / generation backend
- task queue capacity
- selected setup dependencies (storage, stock list, notification, agent)

Missing providers, models, or queue capacity should surface as **explicit** `failed` / `degraded` results with a reason and suggestion—not as silent mid-run partial success.

## Module

```text
src/core/readiness.py
```

Stable report schema version: `readiness_v1`.

Each check returns `status` (`ok` | `degraded` | `failed`), `reason_code`, `reason`, `suggestion`, `required`, and optional `timed_out`.

Overall status aggregation:

1. Any **required** `failed` check → overall `failed`
2. Else any `failed` or `degraded` check → overall `degraded`
3. Else `ok`
4. Empty check list → `failed` (never invent readiness)

## Integration (reuse, not parallel invent)

| Check | Existing owner |
| --- | --- |
| Data providers | `build_data_provider_runtime_status` |
| LLM | `SystemConfigService.get_setup_status` (`llm_primary`) + generation-backend cheap status |
| Task queue | Injected `ApplicationServices` queue, else an already fully initialized `AnalysisTaskQueue` singleton (`get_task_stats` / `max_workers`). Never `get_task_queue()`. |
| Dependencies | Setup projection (`storage`, `stock_list`, `notification`, `llm_agent`) |

First-run readiness (`GET /api/v1/onboarding/first-run`) and setup status (`GET /api/v1/system/config/setup/status`) keep their existing payloads. This module is the shared structured composition layer for diagnostics and operators.

Run diagnostics can project a readiness report via `readiness_report_to_diagnostic_components` without inventing a second health model.

## API

```http
GET /api/v1/system/readiness
```

- Read-only; does **not** write config
- Does **not** run generation smoke tests
- **Not** invoked automatically at process startup
- Probe exceptions and per-check timeouts never become `ok`

## Configuration

| Variable | Default | Notes |
| --- | --- | --- |
| `READINESS_CHECK_TIMEOUT_SECONDS` | `1.0` | Per-check timeout; clamped to `0.1`–`5.0` |

Registered in the shared config registry and loaded into `Config.readiness_check_timeout_seconds`.

## Fail-closed rules

- Data runtime `not_initialized` / `error` → `failed`
- All markets / all providers unavailable → `failed`
- Missing primary model → LLM check `degraded` (data-only still possible)
- Configured backend unavailable → LLM check `failed`
- Task queue missing, shut down, zero workers, or stats failure → `failed`
- Check timeout → `failed` for required checks (`reason_code=check_timeout`)

## Task queue probe

The default task-queue check is **observational**. Explicit `queue=` /
`queue_factory=` seams are unchanged. When neither is supplied, readiness
calls `resolve_existing_task_queue()`:

1. Return a constructor-injected queue from an **already installed**
   `ApplicationServices` root. Do not touch the lazy `task_queue` property
   (that would call operational `get_task_queue()`).
2. Otherwise return `get_existing_initialized_task_queue()`, which reads
   `AnalysisTaskQueue._instance` under `_instance_lock` only when it is
   already fully initialized.
3. Never install a default composition root.

`get_task_queue()` remains the operational accessor: it may construct the
singleton, read config, `sync_max_workers`, and shut down or replace an idle
executor. Readiness must not use it. If no owner exists, the check is
`failed` with `reason_code=task_queue_missing` and the overall report is
`failed` because the check is required. Live and shutdown queues are observed
in place; readiness never constructs, config-syncs, shuts down, or replaces
queue state.

Generation-backend status payload fields and test-double obligations:
[Shared runtime session contract owners](runtime-session-contract-owners.md).

## Related endpoints

- `GET /api/v1/system/config/setup/status`
- `GET /api/v1/onboarding/first-run`
- `GET /api/v1/system/config/data-providers/runtime-status`
- `GET /api/v1/system/config/generation-backends/status`
- `GET /api/v1/health` — liveness only (not readiness)
