# Async Task UX Contract (409 / busy / queue / long-running)

## Purpose

This document is the **client contract** for long-running work and related
rejection states under issue **#885**. It covers presentation and recovery for:

- HTTP **409** busy / duplicate / ledger contention
- **queued** (`pending`) and **in progress** (`processing`) tasks
- **cancel requested** and **terminal** outcomes
- **retryable** vs non-retryable launch failures

It does **not** redefine the full error taxonomy (auth, credential, outbound
policy, validation, …). That taxonomy remains the error-catalog /
`apiReasonMapper` track (#186 / #1064 / W6). This contract **consumes** the
actionable class `busy` and lifecycle wire values from the process-local task
execution authority ([task-execution-contract.md](./task-execution-contract.md)).

## Division of ownership

| Concern | Owner | Primary modules |
| --- | --- | --- |
| Error class taxonomy (`auth`, `network`, `credential`, …) | Taxonomy track (W6) | `apps/dsa-web/src/api/error/`, `apiReasonMapper` classes |
| Async lifecycle + busy recovery UX | This contract | `apps/dsa-web/src/utils/asyncTaskUx.ts`, TaskPanel, RunFlow, launch surfaces |
| Process-local queue lifecycle wire values | Backend task execution | `src.task_execution`, `src/services/task_queue.py` |

## Canonical lifecycle (client phases)

Backend wire statuses (do not invent a second enum on the client):

```text
pending → processing ⇄ cancel_requested → completed | failed | cancelled | interrupted
```

Client presentation phases (`AsyncTaskClientPhase`):

| Wire status | Client phase | Primary surface |
| --- | --- | --- |
| *(no task)* | `idle` | Launch control enabled |
| *(POST in flight)* | `submitting` | Button `isLoading` / `aria-busy`; no second submit |
| `pending` | `queued` | TaskPanel / progress notice; not bare task id |
| `processing` | `in_progress` | TaskPanel progress + `formatTaskMessage` |
| `cancel_requested` | `cancel_requested` | Warning pulse; still active |
| `completed` | `completed` | Terminal success; optional “view report” |
| `failed` | `failed` | Terminal danger; technical detail under disclosure |
| `cancelled` / `interrupted` | `cancelled` / `interrupted` | Terminal warning; dismiss allowed |

Helpers: `mapTaskStatusToClientPhase`, `isActiveTaskStatus`,
`isTerminalTaskStatus`, `normalizeTaskProgress` in
`apps/dsa-web/src/utils/asyncTaskUx.ts`.

Copy for known `messageCode` values comes from `formatTaskMessage`
(`apps/dsa-web/src/utils/taskMessage.ts`). Do not surface raw English enums
(`processing`) as the primary user message when a stable code or status
fallback exists.

## 409 and busy semantics

| Server code / reason | Actionable class | Launch control | Recovery kind |
| --- | --- | --- | --- |
| `duplicate_task` | `busy` | Block until dismiss / attach | `attach_or_view_tasks` — open TaskPanel / RunFlow for `existing_task_id` when present |
| `duplicate_market_review` | `busy` | Block until dismiss | `attach_or_view_tasks` when id present; else wait + dismiss (market lock may not expose id) |
| `scheduler_busy` / `analysis_already_running` | `busy` | Block / disable run-now | `wait_and_dismiss` — show reason; poll status; no blind retry storm |
| `portfolio_busy` | `busy` | Short block | `retry_same_operation` after settle, same operation id when required |
| `config_conflict` / `config_version_conflict` / revision conflicts | `config_conflict` | Block mutations | `reload` server state; preserve drafts where product already does |

**Deadlock rule:** a busy or conflict error that disables the primary CTA must
always offer at least one exit:

1. **Attach / view tasks** when an existing task identity is known, or
2. **Dismiss** the blocking alert (re-enable launch), or
3. **Reload** for revision conflicts.

Never leave the user with only a disabled button and no explanation.

Helpers: `isTaskBusyError`, `isLaunchBlockingError`, `extractExistingTaskId`,
`resolveBusyRecoveryKind`.

## Long-task progress and terminal presentation

Mandatory patterns:

1. **Accepted async work** attaches to TaskPanel, RunFlow, Settings tracked
   run-now state, Market Review runner notices, Screening progress, or an
   equivalent recoverable surface. **Forbidden:** success copy that is only an
   opaque `taskId` string with no navigation path (issue #885 / #879 A6).
2. **In progress:** determinate `Progress` when `progress` is known; pulse
   status when not. Message via `formatTaskMessage`.
3. **Terminal success:** green / success tone; optional deep link to report or
   history. Dismiss removes the card without losing history.
4. **Terminal failure / interrupted / cancelled:** danger or warning tone;
   technical code under disclosure; operation-owned Retry only when
   `isOperationRetryableError` is true (network / rate quota by default). Busy
   is never auto-retried.
5. **Partial batch:** show accepted + duplicate + failed counts; retry only
   unconfirmed symbols (Analysis Workbench contract from PR #934).

## Frontend presentation contract

| Concern | Pattern | Anti-pattern |
| --- | --- | --- |
| Form / launch errors | Inline `ActionableApiErrorInline` (or equivalent) near the control | Toast-only for busy/409 that blocks the form |
| Busy reason | Warning alert + disabled primary + recovery CTA | Silent disable |
| Task identity | TaskPanel / RunFlow deep link | Bare id as the only feedback |
| Technical codes | Collapsed “Details” | English enum as the only title |
| Double submit | `submitting` or launch-blocked while busy alert visible | Parallel POSTs for the same ownership key |

Toast may remain secondary for generic non-blocking errors
(`useAnalysisErrorToast` toast-only path for `generic` class). It must not be
the sole surface for busy or for accepted long-running work.

## Entry-point adoption map

| Entry | Busy / 409 | Progress / terminal | Notes |
| --- | --- | --- | --- |
| Analysis Workbench launch / batch | Actionable inline + TaskPanel / RunFlow | TaskPanel + RunFlow | Reference adoption (PR #934) |
| Portfolio position analysis | Reattach on `duplicate_task` + TaskPanel | Shared TaskPanel | Must not dead-end on toast |
| Market Review | Busy alert + launch block until dismiss | Runner notices + optional RunFlow | Lock 409 may omit task id |
| Settings run-now | Disable + busy reason + tracked state | Poll until idle | Not a bare task id |
| Settings first-run smoke | Busy/duplicate → workbench tasks link | Success links to Analysis Workbench tasks | No task-id-only success |
| Stock Screening | Capability / poll errors local | Local progress + `formatTaskMessage` | Domain-specific panel OK |
| Scheduler status API | `runNowAvailable` / `runNowBlockReason` | Tracked run lifecycle | Align copy with busy class |

## Related documents

- [task-execution-contract.md](./task-execution-contract.md) — backend lifecycle
- [web-ui-foundation.md](./web-ui-foundation.md) — StatePanel / Alert / Progress
- [openapi-web-types.md](./openapi-web-types.md) — Web error parse facade
- `apps/dsa-web/src/utils/apiReasonMapper.ts` — code/reason → actionable class
- `apps/dsa-web/src/utils/asyncTaskUx.ts` — lifecycle helpers for this contract
