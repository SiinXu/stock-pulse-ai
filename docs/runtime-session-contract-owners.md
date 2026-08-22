# Shared Runtime Session Contract Owners

- Status: `Living`
- Last verified: 2026-08-22 against `origin/main` `39657d6b9` (after [#1466](https://github.com/SiinXu/stock-pulse-ai/pull/1466) landed analysis-task HTTP cancel)
- Issue: [#1055](https://github.com/SiinXu/stock-pulse-ai/issues/1055) T1 (docs / owner inventory only)
- Chinese: [runtime-session-contract-owners_CN.md](runtime-session-contract-owners_CN.md)

This page is the owner map for **shared runtime session, probe, and presentation
contracts**. It exists so a production-required field cannot land while the
standard test double or public-surface mock still omits it.

It does **not** change runtime behavior. Follow-up fail-closed BoundToolSession
double work is T2 of #1055 and is listed under Remaining.

## Purpose

Recent canary and cross-module failures share one pattern:

1. Production adds an immutable field (`deadline_monotonic`,
   `is_cancel_requested`, `ANALYSIS_TASK_HTTP_CANCEL_AVAILABLE`, …).
2. Hand-written `SimpleNamespace` / partial `vi.mock` factories omit the field.
3. Path-selective suites stay green until a later shard, Web gate, or
   cross-module job reads the field.

This inventory names the owner module, the production constructor, the tests
that must move in the same PR, the fail-closed expectation, and the deprecation
path for leftover ducks.

## Scope

In scope:

- Agent `BoundToolSession` / runner completion fences / ToolAccessContext
- Process-local `TaskRunContext` cancel protocol, including the HTTP cancel
  field that landed in #1466
- Web analysis-task cancel flag and `cancelTask`
- Generation-backend status payload consumed by readiness
- Config-registry documented-key presentation vs `.env.example`

Out of scope (do not implement here):

- Full Agent redesign
- New product features
- Bulk config-key registration ([#1023](https://github.com/SiinXu/stock-pulse-ai/issues/1023))
- Task-aware routing ([#204](https://github.com/SiinXu/stock-pulse-ai/issues/204))
- Desktop-only analysis clients (none exist; Desktop embeds the Web bundle)
- Weakening timeouts, redaction, or ToolSurface deny-by-default

## How to change a listed contract

When adding, renaming, or making required a field on a row below, the **same
PR** must:

1. Update the production constructor / frozen dataclass / generated OpenAPI
   surface named in that row.
2. Update every **must-update-together** test and the standard helper it uses.
3. Keep fail-closed behavior: missing required fields raise, deny, or mark
   `failed`. Do not `getattr(..., False)` / `getattr(..., None)` a required
   field into a silent unlimited run.
4. Prefer a small contract PR. Do not fold unrelated Agent, Settings, or
   research rewrites into the same change.
5. Update this inventory (both languages) if owners, constructors, or paired
   tests change.

## Fail-closed baseline

| Layer | Required reaction when the contract is missing or broken |
| --- | --- |
| Native tool dispatch | `src/agent/runner_parts/tools.py` reads `tool_session.deadline_monotonic` directly. A duck without the attribute raises `AttributeError`; it must not become an unbounded wait. |
| Analysis runner cancel | `TaskRunContext.is_cancel_requested` is a required frozen-dataclass field. `_run_analysis_command` treats a missing callable as a contract error, not silent `False`. |
| ToolSurface cancellation probe | A broken `cancelled_check()` fails closed (`cancelled=True`) before the handler starts. |
| ToolSurface deny-by-default | Unregistered names and missing capabilities are denied before the handler. Do not add a parallel executor. |
| Readiness generation probe | Probe exceptions and timeouts never become `ok`. Configured backend + unreadable status → `reason_code=generation_backend_probe_failed`. |
| Config presentation | Every `.env.example` key must be explicitly registered. Inference is not the Settings contract for a documented key. |
| Web analysis cancel | `ANALYSIS_TASK_HTTP_CANCEL_AVAILABLE` is typed against generated `paths`. Factory mocks that drop the flag or `cancelTask` are contract drift. |

Known remaining leniency (document, do not extend):

- `resolve_session_category_timeout_seconds` treats a missing
  `category_timeout_seconds` callable as **no category cap** (`0.0`). That
  helper is not a license to omit `deadline_monotonic` on objects passed to
  `_execute_tools`.
- `ToolSurface._effective_dispatch_deadline` still uses
  `getattr(context, "deadline_monotonic", None)`. A duck `ToolAccessContext`
  without the field currently means “no absolute deadline”. T2 must not
  silently preserve that as the desired production path.

## Contract inventory

| Contract | Owner module | Production constructor | Must update together | Fail-closed expectation |
| --- | --- | --- | --- | --- |
| BoundToolSession `deadline_monotonic` | `src/agent/runtime/tool_session.py` | `BoundToolSession(...)` in `src/agent/runner_parts/loop.py` and `src/agent/planning/product.py` | `tests/agent/runtime/test_tool_session.py` (`_session`), `tests/agent/runtime/test_native_session_bridge.py` (`_native_session`), `tests/test_agent_frozen_context.py` (`_native_session`), `tests/agent/test_agent_runner_public_surface.py` (`_ToolCompletionFence.deadline_monotonic`) | Native `_execute_tools` requires the attribute. Standard helpers must construct the real class, not a partial duck. |
| Runner completion fence `deadline_monotonic` | `src/agent/runner.py` `_ToolCompletionFence` | Built inside `_execute_tools` from the earlier of batch timeout and `tool_session.deadline_monotonic` | `tests/agent/test_agent_runner_public_surface.py`, `tests/agent/test_tool_timeout.py` | Fence methods stay on the production class; AST/public-surface pins catch runner-module shape drift. |
| ToolAccessContext timeout / deadline / cancel | `src/agent/tools/execution.py` `ToolAccessContext`; fences in `src/agent/tools/surface.py` | `BoundToolSession` builds the context per call; callers do not invent a second context type | `tests/agent/runtime/test_tool_session.py`, `tests/agent/test_tool_timeout.py`, `docs/agent-tool-surface.md` | Deny-by-default and timeout/cancel fences stay in ToolSurface. Do not add a private wait that bypasses the surface. |
| `TaskRunContext.is_cancel_requested` | `src/task_execution.py` | `src/services/task_queue/worker.py` `_execute_command` passes `lambda: self._is_cancel_requested(task_id)` | `tests/test_task_execution.py`, `tests/services/test_local_first_boundaries.py` (`_analysis_task_context`, `test_async_analysis_command_requires_explicit_cancel_protocol`) | Missing callable is `AttributeError`, not `False`. Cooperative cancel also returns true after `cancelled` / `interrupted`. |
| Analysis HTTP cancel flag + `cancelTask` | `apps/dsa-web/src/api/analysis.ts`; route `POST /api/v1/analysis/tasks/{task_id}/cancel` | Generated OpenAPI `paths` plus `analysisApi.cancelTask`; TaskPanel reads `ANALYSIS_TASK_HTTP_CANCEL_AVAILABLE` | `apps/dsa-web/src/api/__tests__/analysis.test.ts`; every `vi.mock('../../api/analysis')` / `vi.mock('../../../api/analysis')` must `importActual` and spread | Kind-scoped: discovery cancel is a different path. Mocks that replace the whole module drop the landed cancel field. |
| Generation-backend probe payload | `src/services/generation_backend_status_service.py`; consumed by `src/core/readiness.py` `check_llm_runtime` | `GenerationBackendStatusService(effective_map=...).get_status()` | `tests/services/test_generation_backend_status_service.py`, `tests/core/test_readiness.py` (`generation_status` / probe exceptions) | Probe exceptions → `failed` with `generation_backend_probe_failed`. Do not invent `ok` from a partial mapping. |
| Documented config-key registry guard | `src/core/config_registry.py` + `src/core/config_registry_parts/` | Explicit field metadata in the matching registry part, not `_infer_*` | `tests/core/test_env_example_config_registry_guard.py` (`test_every_documented_env_example_key_is_registered`), `python scripts/check_config_doc_consistency.py --fail-on all`, bilingual `docs/environment-variables.md` / `_EN.md` | Documented `.env.example` keys without registry metadata fail CI. Do not raise the unregistered-debt baseline to green a new key. |
| LLM channel / route map (stable metadata only) | `src/services/config/llm_channel_map.py` | Pure readers from an effective `.env` map shared by setup, connection tests, and generation-backend config views | `tests/services/test_generation_backend_status_service.py` custom-literal / gateway route cases; SystemConfig public-surface exports | Do not implement #204 task-aware routing here. Route readers must stay one authority; status service builds a config view from the effective map, not a second parser. |

## 1. BoundToolSession `deadline_monotonic`

**Boundary.** `BoundToolSession` is the only supported runtime path for
financial tool calls. Identity, allowlist, grants, stock scope, budgets, the
absolute monotonic deadline, and the cancellation token are frozen at
construction. `deadline_monotonic` is an absolute `time.monotonic()` instant
(the old relative `deadline_seconds` name is retired).

**Owners.** Construction: `src/agent/runtime/tool_session.py`. Production
callers: native loop (`src/agent/runner_parts/loop.py`) and planning product
session factory (`src/agent/planning/product.py`). Native dispatch:
`src/agent/runner_parts/tools.py`. PydanticAI reuses the same session
(`src/agent/runtime/pydantic_ai_toolset.py`); it is not a second authority.

**Standard test helper (preferred).** Real-class helpers already exist:

- `tests/agent/runtime/test_tool_session.py` `_session`
- `tests/agent/runtime/test_native_session_bridge.py` `_native_session`
- `tests/test_agent_frozen_context.py` `_native_session`

T2 should promote one of these (or a shared import of it) as **the** standard
double. Until then, new tests that drive `_execute_tools` must use a real
`BoundToolSession`, not `SimpleNamespace`.

**Current ducks (do not copy).**

- `tests/agent/test_tool_timeout.py` `RecordingSession` / `CappedSession` set
  `deadline_monotonic = None` by hand.
- `tests/security/test_sensitive_redaction.py` `RecordingSession` does the same
  so redaction can observe dispatch without a full session.
- `test_resolve_session_category_timeout_accepts_minimal_and_invalid_doubles`
  documents that the **category-cap helper** accepts a `MinimalSession` with
  only `execution_id`. That is helper semantics, not an `_execute_tools`
  license.

**Validation.** `python -m pytest tests/agent/runtime/test_tool_session.py tests/agent/test_tool_timeout.py tests/test_agent_frozen_context.py tests/agent/test_agent_runner_public_surface.py tests/security/test_sensitive_redaction.py -q` after session-field changes. If `_execute_tools` or `_ToolCompletionFence` AST changes, the public-surface hash/pin test is the ratchet.

## 2. TaskRunContext `is_cancel_requested` (landed with #1466)

**Boundary.** `src.task_execution.TaskRunContext` is the runner-facing
process-local contract. `AnalysisTaskQueue` is the adapter. HTTP adapters may
project `cancel` for **one kind at a time**; they must not invent a second
lifecycle. See [task-execution-contract.md](task-execution-contract.md).

**Production constructor.**

```text
src/services/task_queue/worker.py  _execute_command
  → TaskRunContext(
        ...,
        is_cancel_requested=lambda: self._is_cancel_requested(task_id),
        commit_final_result=...,
      )
```

The stock-analysis adapter polls the callable before `analyze_stock`, on
progress, and after pipeline return. Local-model pulls poll between stream
chunks. Missing the callable is a contract error.

**Standard test helper.** `tests/services/test_local_first_boundaries.py`
`_analysis_task_context` builds a real `TaskRunContext`. The regression
`test_async_analysis_command_requires_explicit_cancel_protocol` passes a
`SimpleNamespace` **without** `is_cancel_requested` and expects
`AttributeError`.

**Do not** construct analysis runner stubs with `SimpleNamespace` that omit
`is_cancel_requested`, `update_progress`, `append_flow_event`, or
`commit_final_result`.

**Validation.** `python -m pytest tests/test_task_execution.py tests/services/test_local_first_boundaries.py -q`

## 3. Analysis HTTP cancel field (landed with #1466)

**Boundary.** Kind-scoped route:

```text
POST /api/v1/analysis/tasks/{task_id}/cancel
```

Discovery cancel (`/api/v1/discover/screen/tasks/{task_id}/cancel`) is a
different kind and must not be reused. Desktop has no separate analysis client;
TaskPanel ships inside the Web bundle.

**Production surface.** `apps/dsa-web/src/api/analysis.ts`:

- `ANALYSIS_TASK_HTTP_CANCEL_AVAILABLE` is `true` iff the generated `paths`
  type includes the cancel route.
- `analysisApi.cancelTask` posts to that route.
- `apps/dsa-web/src/components/tasks/TaskPanel.tsx` renders cancel only when
  the flag is true.

**Must-update-together mocks.** Spread the real module:

```ts
vi.mock('../../api/analysis', async () => {
  const actual = await vi.importActual<typeof import('../../api/analysis')>(
    '../../api/analysis',
  );
  return {
    ...actual,
    analysisApi: {
      ...actual.analysisApi,
      // override only the methods this test needs
    },
  };
});
```

Factory mocks of the form `() => ({ analysisApi: { getStatus, getTasks } })`
are **deprecated**. They drop `ANALYSIS_TASK_HTTP_CANCEL_AVAILABLE` and
`cancelTask` the next time either lands or is renamed.

Known paired tests (non-exhaustive; grep `api/analysis` mocks when adding
fields):

- `apps/dsa-web/src/api/__tests__/analysis.test.ts`
- `apps/dsa-web/src/components/tasks/__tests__/TaskPanel.test.tsx`
- `apps/dsa-web/src/components/portfolio/__tests__/usePortfolioAnalysisTasks.test.tsx`
- `apps/dsa-web/src/components/run-flow/__tests__/RunFlowPanel.test.tsx`
- `apps/dsa-web/src/pages/__tests__/PortfolioPage.test.tsx`
- `apps/dsa-web/src/pages/__tests__/SettingsPage.testHarness.tsx`
- `apps/dsa-web/src/pages/__tests__/MarketReviewPage.test.tsx`
- `apps/dsa-web/src/pages/__tests__/ResearchAnalysisWorkbenchPage.test.tsx`
- `apps/dsa-web/src/stores/__tests__/stockPoolStore.test.ts`
- `apps/dsa-web/src/utils/__tests__/setupSmokeTask.test.ts`
- `apps/dsa-web/src/hooks/__tests__/useRunFlowSnapshot.test.tsx`
- `apps/dsa-web/src/hooks/__tests__/useMarketReviewRunner.test.tsx`
- `apps/dsa-web/src/hooks/__tests__/useTaskStream.test.tsx`

**Validation.** `cd apps/dsa-web && npx vitest run src/api/__tests__/analysis.test.ts src/components/tasks/__tests__/TaskPanel.test.tsx` plus any page test whose mock you touched. OpenAPI drift is owned by `openapi-types-gate`.

## 4. ToolAccessContext fences

**Boundary.** `ToolAccessContext` carries `timeout_seconds`,
`deadline_monotonic`, `cancelled_check`, grants, and audit context into
ToolSurface. Callers cannot set `enforce_contract=False` to bypass security
(the field is retained for call-site compatibility only).

**Owner.** ToolSurface (`src/agent/tools/surface.py`) owns authz, timeout,
audit, and deny-by-default. Checklist: `NEW_TOOL_CHECKLIST` in
[agent-tool-surface.md](agent-tool-surface.md).

**Fail-closed.** Broken cancellation probes fail closed before the handler.
Unregistered tools and missing capabilities are denied. Do not add a
tool-local wait that ignores `deadline_monotonic`.

**Deprecation path for ducks.** New production and test call sites should
pass a real `ToolAccessContext` (or let `BoundToolSession` build it). Do not
add more `getattr(context, "deadline_monotonic", None)` readers. T2 may
tighten the remaining getattr.

## 5. Generation-backend probe payload

**Boundary.** `GenerationBackendStatusService.get_status()` returns a mapping
with `primary_backend_id`, `fallback_backend_id`, `primary`, `fallback`, and
`backends`. Each backend block includes at least `backend_id`, `available`,
`health_status`, capability flags, and `last_error_*`. This is a **config
view** from the effective env map, not a persisted health store and not a
test double.

Readiness (`src/core/readiness.py` `check_llm_runtime`) consumes `primary`
(`backend_id`, `available`, `health_status`). A probe exception is recorded
as `generation_probe_error` and, when setup says the primary is configured,
fails the LLM check with `generation_backend_probe_failed`.

**Must-update-together.** If you add a field readiness reads, update:

- `src/services/generation_backend_status_service.py` `_build_status`
- `tests/services/test_generation_backend_status_service.py`
- `tests/core/test_readiness.py` injected `generation_status` mappings
- [readiness-self-check.md](readiness-self-check.md) /
  [readiness-self-check_EN.md](readiness-self-check_EN.md) if the fail-closed
  rule changes

Do not hand-build a status mapping that reports `ok` while omitting
`available` / `health_status`.

**Validation.** `python -m pytest tests/services/test_generation_backend_status_service.py tests/core/test_readiness.py -q`

## 6. Config-registry documented-key guard

**Boundary.** Three-way contract, already documented in
[environment-variables.md](environment-variables.md):

| Source | Path |
| --- | --- |
| Documented env | `.env.example` |
| Registry metadata | `src/core/config_registry_parts/` |
| Bilingual inventory | `docs/environment-variables.md` / `docs/environment-variables_EN.md` |

#1055 does **not** own bulk key registration. This row only records that the
presentation contract is already fail-closed: `test_every_documented_env_example_key_is_registered`
and `python scripts/check_config_doc_consistency.py --fail-on all`.

Do not expand `TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_*` to green a new key.

**Validation.** `python scripts/check_config_doc_consistency.py --fail-on all` and `python -m pytest tests/core/test_env_example_config_registry_guard.py -q`

## Test-double obligations (summary)

| Double kind | Allowed? | Obligation |
| --- | --- | --- |
| Real `BoundToolSession` via `_session` / `_native_session` | Required for `_execute_tools` and session-gate tests | Add new required constructor fields to the helper in the same PR |
| Real `TaskRunContext` via `_analysis_task_context` or the dataclass | Required for analysis/queue runner tests | Include `is_cancel_requested` |
| `vi.importActual` spread of `apps/dsa-web/src/api/analysis.ts` | Required for Web analysis mocks | Override only methods the test needs |
| `SimpleNamespace` / factory `vi.mock` that lists a subset of fields | Deprecated except for an explicit negative test | The negative test must expect `AttributeError` / type failure, not silent success |
| `MinimalSession` with only `execution_id` | Allowed only as input to `resolve_session_category_timeout_seconds` | Missing category cap means no cap (`0.0`); do not pass this object to `_execute_tools` as a general session |
| Security `RecordingSession` duck | Temporary until T2 | Already carries `deadline_monotonic`; adding another production-required session field requires updating this duck **or** switching it to the real helper in the same PR |

## Deprecation path

| Legacy shape | Replacement | When it may be removed |
| --- | --- | --- |
| Relative `deadline_seconds` on the session | Absolute `deadline_monotonic` | Already renamed in production. Do not reintroduce the relative name. |
| Analysis runner `SimpleNamespace` stubs | Real `TaskRunContext` | #1466 already requires the cancel callable. Remaining stubs must follow `_analysis_task_context`. |
| Factory-style `vi.mock('../../api/analysis', () => ({ analysisApi: {...} }))` | `importActual` + spread | After #1466 this is the required Web pattern. New factory mocks are contract bugs. |
| Duck sessions used as the “standard double” | Shared real `BoundToolSession` helper | T2 of #1055. This T1 docs slice does not delete the existing timeout/redaction ducks. |
| `getattr(context, "deadline_monotonic", None)` as the desired API | Required field on `ToolAccessContext` | T2 may fail closed. Do not add more getattr fallbacks in the meantime. |
| Inferred Settings metadata for a documented env key | Explicit `config_registry_parts` entry | Already fail-closed. Inference remains only for runtime-only compatibility values. |

Do not add parallel session types, a second task lifecycle, a second analysis
cancel route, or a second generation-backend parser.

## Validation (this inventory)

Commands used to verify this page against the tree at last-verified SHA:

```bash
# Production constructors and required fields exist
python3 - <<'PY'
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.tools.execution import ToolAccessContext
from src.task_execution import TaskRunContext
from src.services.generation_backend_status_service import GenerationBackendStatusService
assert "deadline_monotonic" in BoundToolSession.__init__.__code__.co_varnames
assert "deadline_monotonic" in ToolAccessContext.__dataclass_fields__
assert "is_cancel_requested" in TaskRunContext.__dataclass_fields__
assert hasattr(GenerationBackendStatusService, "get_status")
PY

# Changelog fragments remain well-formed
python3 scripts/collect_changelog.py --check
```

Confirm filenames in this page with `ls` / editor search before changing a
row. Docs-only edits do not require the full offline pytest suite.

## Remaining (#1055 T2, not this slice)

- Promote the real `BoundToolSession` helper as the standard double.
- Add a regression that fails if that helper omits a production-required
  session field (today: at least `deadline_monotonic`).
- Keep the documented “missing category cap means no cap” helper test, or
  stop calling `_execute_tools` with incomplete objects.
- Do not weaken ToolSurface deny-by-default, redaction, or timeouts.

## Related

- [Agent ToolSurface](agent-tool-surface.md) ([中文](agent-tool-surface_CN.md))
- [Task execution contract](task-execution-contract.md)
- [Environment variable inventory](environment-variables_EN.md) ([中文](environment-variables.md))
- [Readiness / self-check](readiness-self-check_EN.md) ([中文](readiness-self-check.md))
- [Config-access ratchet](config-access-ratchet.md)
- [Sensitive-data redaction](security-sensitive-data-redaction.md)
- [Contributing](CONTRIBUTING_EN.md) ([中文](CONTRIBUTING.md))
