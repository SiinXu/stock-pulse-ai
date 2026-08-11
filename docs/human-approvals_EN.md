# Human-in-the-Loop Approval Safety Gate

Human-in-the-Loop (HITL) approval provides a default-off, one-shot, auditable exception to the existing Agent risk override. It handles only `risk_control_bypass`: when an existing `risk_veto` or `risk_downgrade` would make the final recommendation more conservative, the administrator may approve preserving the original recommendation for a short window. This is not trade approval; it neither connects to a broker nor expands Agent tool authority.

## When to enable

The rule is **off by default** (`enabled=false`). Consider enabling `risk_control_bypass` only when all of the following hold:

1. Administrator authentication is on (`ADMIN_AUTH_ENABLED=true`) and an operator can reach Web `/approvals` or the approval API within the proposal lifetime.
2. You understand Agent risk override: `risk_veto` / `risk_downgrade` rewrite a more aggressive original recommendation to a more conservative result; HITL only allows a **one-shot**, short-window administrator exception to keep the original recommendation.
3. You accept fail-closed behavior: timeout, rejection, expiry, audit failure, or pipeline deadline always applies the conservative override and never silently relaxes risk control.

Do not enable this for unattended batch jobs, auth-disabled public deployments, or multi-level IAM / broker order-approval workflows—those are outside the current contract.

## Defaults and timeouts (operations)

| Item | Default / range | Notes |
| --- | --- | --- |
| Rule switch | **Off** | With no persisted rule, behavior matches the pre-HITL path and no proposal is created |
| Proposal lifetime `expires_in_seconds` | **300** seconds (allowed **30–3600**) | Measured from proposal creation; becomes `expired` at the deadline |
| Poll interval | about 1 second | Worker sleep granularity while waiting for a decision—not a separate “analysis timeout” knob |
| Owner | fixed `local_admin` | Single administrator; no multi-tenant owners and no multi-level approval chains |

Web countdowns and API `expires_at` both use that lifetime. Shorter lifetimes reduce how long a pipeline may block on a pending proposal; longer values must not exceed 3600 seconds.

## Proposal timeout vs analysis pipeline deadline

These clocks are **independent**:

1. **Proposal lifetime**  
   Controlled by rule `expires_in_seconds`. After expiry the status is `expired` and every worker must apply the conservative override. An `approved` proposal that is not successfully CAS-consumed before expiry also cannot authorize a bypass.

2. **Analysis pipeline deadline (orchestrator budget)**  
   Driven by the Agent orchestrator timeout (`AGENT_ORCHESTRATOR_TIMEOUT_S`; commonly 600 seconds by default, `0` disables). Pipeline entry sets `_approval_deadline_epoch` to `start + timeout` (or empty when the budget is disabled). While polling, `await_risk_control_bypass` calls `stop_waiting_check`; when the deadline has passed it **stops waiting immediately and returns `None`** (fail closed → conservative override), **even if the proposal is still `pending` and has not reached `expires_at`**.

3. **Cancellation**  
   If `cancelled_check` becomes true while the proposal is still `pending`, the worker cancels the proposal and returns `None` (conservative override).

**Operational implication:** when HITL is enabled, the administrator must decide within **min(proposal lifetime, remaining pipeline budget)**. If the pipeline budget is shorter than the proposal lifetime, waiting ends at the pipeline deadline; the proposal may remain listed until natural expiry, but that execution will not obtain a bypass from overtime waiting. After restart, workers never treat leftover `pending` state as authorization.

## Security boundary

- The identity model remains the local **single administrator**, with owner fixed to `local_admin`. Approval APIs require `ADMIN_AUTH_ENABLED=true` and a valid administrator session. Disabled authentication returns `403`; a missing or invalid session returns `401`. There is no multi-level approval, layered RBAC, or SSO identity switch.
- The rule is off by default. When enabled, its default lifetime is 300 seconds and its allowed range is 30–3600 seconds. Risk sources are limited to the existing `risk_veto` and `risk_downgrade` categories.
- Proposals only transition `pending → approved | rejected | expired | cancelled`. Terminal states are irreversible and versions increase monotonically. Decisions use `expected_version` CAS; replaying the same completed decision is an idempotent read and does not mutate state again.
- A unique SHA-256 idempotency key is derived from execution input. The same execution and bounded context reuse the original proposal. A persisted proposal survives process restart and eventually expires.
- Only a same-owner, unexpired, `approved`, unconsumed proposal with the matching version can be consumed by one CAS. A second worker, stale version, foreign owner, expired proposal, or consumed proposal cannot preserve the original recommendation.
- Proposal creation/reuse, transitions, consumption, and final authorization completion record attempt/completion events through `SecurityAuditService`. Rule changes and explicit decisions are attributed to `administrator/local_admin`; worker proposal, automatic expiry, consumption, and completion events are attributed to `runtime_principal/approval_worker`. Audit metadata contains stable enums, versions, and proposal identifiers only—never prompts, cookies, credentials, complete model parameters, or unbounded reasoning.
- Storage, audit, polling, concurrency, and unknown failures fail closed to the existing conservative risk override. Approval failure can never relax risk control.

## API

All endpoints are under `/api/v1/approvals`:

| Method | Path | Contract |
| --- | --- | --- |
| `GET` | `/rules/risk-control-bypass` | Read the default or persisted rule |
| `PUT` | `/rules/risk-control-bypass` | Update enablement, risk sources, and lifetime with `expected_version` |
| `GET` | `/` | List current-owner proposals with status filtering and pagination |
| `GET` | `/{id}` | Read one current-owner proposal |
| `POST` | `/{id}/decision` | Submit `approved`, `rejected`, or `cancelled` with `expected_version` |

Proposal responses expose only `id`, owner, status, version, expiry, consumption time, and bounded redacted context. Context contains a stock code, original signal, conservative signal, stable risk source, and a fixed risk summary capped at 240 characters. Version conflicts and invalid terminal transitions return `409`. Foreign-owner and missing proposals both return `404` to avoid disclosing another owner's records.

The Web page is `/approvals`, reached from the Home To-dos card without adding a primary navigation domain. It shows pending and terminal states, countdowns, original and conservative signals, approve/reject controls, and minimal rule settings. Local controls suppress duplicate clicks, and a `409` refreshes server state.

The page states default preconditions honestly instead of looking “broken”:

- Disabled authentication (`403` / `approval_auth_required`) or a missing session (`401`) shows a warning banner, disables rule edits and decision actions, and deep-links to Auth & Security settings or the sign-in page.
- When the rule is off by default, the page explains that no pending approvals are created and the mandatory Risk Manager final action still applies automatically.
- When the rule can load, the page explains that every conservative `downgrade` or `reject` runs first; only a matched rule plus successful one-shot approval and consumption preserves the original recommendation with an audited approval ID.

## Execution semantics

The multi-agent decision exit still runs through `AgentOrchestrator._apply_risk_override`, which evaluates the mandatory Risk Manager final-action authority (see `docs/risk-manager-gate_EN.md`). The HITL approval rule is consulted for a conservative `downgrade` or `reject`, including profile-driven decisions that do not depend on a legacy `AGENT_RISK_OVERRIDE` plan. An off rule or unselected risk category keeps the conservative final action. When matched, the worker creates or reuses a proposal and polls while Web/API decisions complete asynchronously:

1. `approved` plus successful CAS consumption preserves the original, more aggressive recommendation and records the consumed proposal id in internal runtime facts.
2. `rejected`, `cancelled`, `expired`, missing, stale, foreign-owner, replayed consumption, audit failure, or concurrency failure applies the existing conservative recommendation.
3. Restarted workers never treat persisted `pending` state as authorization; only explicit approval followed by successful current-execution consumption permits the bypass.

## Migration and rollback

Registered migration `202607250001_approval_gate_schema` creates:

- `approval_rules`: unique owner/action rule, risk-source JSON, lifetime, and CAS version.
- `approval_proposals`: state, unique idempotency key, execution identifier, bounded context, expiry, decision time, and one-shot consumption time, plus an owner/status/expiry index.

The forward-only migration is idempotent and fails closed on partial or lookalike storage. At startup it verifies column names and order, SQLite type affinities, `NOT NULL` constraints, primary and unique keys, query indexes, DDL clauses, table options, foreign-key absence, and the complete inventory of both target tables and every target index. Back up SQLite before deployment. To roll back application behavior safely, first disable the approval rule and then deploy the old code; the additive tables may remain because old code does not read them. A schema rollback requires stopping writes, restoring a pre-migration backup, and deploying the matching old version. Never delete `schema_migrations` rows manually.

This feature does not implement live trading, multi-level enterprise IAM, a distributed workflow engine, the other collaboration surfaces in Issue #199, or self-improvement from Issue #450.
