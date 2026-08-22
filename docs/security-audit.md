# Durable Security Audit

StockPulse persists privileged-operation decisions in the main SQLite database
under the versioned `security-audit-v1` contract. This trail is separate from
application logs, Agent runtime events, Run Diagnostics, and the cross-stage
observability work tracked by #222.

Human approval proposal creation/reuse, every state transition, one-shot
consumption, and final risk-bypass authorization use this same mandatory
attempt/completion service. Their metadata is limited to proposal ids, stable
risk/status enums, and CAS versions. See
[Human-in-the-Loop Approval Safety Gate](human-approvals_EN.md); prompts,
cookies, credentials, full model parameters, and unbounded reasoning are not
approval audit fields.

This document is the privileged-path coverage map for
[#1062](https://github.com/SiinXu/stock-pulse-ai/issues/1062). It is not a
rebuild of the trail. Phase 1 storage, redaction, administrator query, and
the original HTTP/MCP/tool/HITL/plugin/local-process connections already
exist. Remaining work is sequenced coverage, not a mega-PR.

Chinese version: [持久安全审计](security-audit_zh.md).

## Event Contract

Every row is append-oriented and contains:

- a UTC `occurred_at` timestamp and stable `event_type`;
- `attempt` or `completion` phase;
- bounded actor and execution identities;
- stable action and bounded target type/id;
- outcome and reason code;
- one correlation ID reused by the attempt and completion;
- recursively redacted, size-bounded metadata.

Metadata is bounded to 16 object keys, 64 items per list, 256 characters per
string, and two nested collection levels. Oversized general metadata fails
closed.

System Configuration updates can legitimately contain more than 64 dynamic
Connection fields, so their audit metadata uses bounded evidence rather than a
request-size limit. `key_sample` contains the first 64 sorted, distinct key
strings after central redaction; ordinary keys remain exact, while a sampled
key longer than 256 characters is represented by its `sha256:<hex>` marker.
`key_count` covers the complete distinct set,
`item_count` preserves duplicate-item evidence, `keys_truncated` states whether
the sample omits keys, and `keys_sha256` is SHA-256 over the compact ASCII JSON
encoding of the complete sorted distinct key list. Configuration version and
reload intent remain in the event. Values are never included.

## Privileged-Path Coverage Map

Inventory against current `main`. Status is based on production
`SecurityAuditService` / `record_attempt` call sites, not file existence.
[#1062](https://github.com/SiinXu/stock-pulse-ai/issues/1062) Workstream A–D
checkboxes and several baseline gap rows were written after Phase 1 landed and
are **stale** relative to this map. Do not re-implement **Landed** rows.

Legend:

| Status | Meaning |
| --- | --- |
| **Landed** | Attempt and completion are written at the accept/reject boundary |
| **Partial** | Some entry points emit; others of the same privileged operation do not |
| **Missing** | Privileged accept/reject has no durable security-audit row |
| **Deferred** | Out of #1062 acceptance, or needs a named owner before implementation |

### Original issue map (Workstream A)

| Operation | `event_type` | Status | Owner / notes |
| --- | --- | --- | --- |
| Login success/failure | `auth.login` | **Landed** | `src/api/v1/endpoints/auth.py` |
| Auth enable/disable | `auth.policy` | **Landed** | Same; AUTH-04 reauth remains; password is not stored |
| Logout / session invalidation | `auth.logout` | **Landed** | Session-secret rotation stays nested in this path |
| Password change | `auth.password_change` | **Landed** | Success and denial audited |
| Sensitive config create/update | `system_config.write` | **Partial** | HTTP `src/api/v1/endpoints/system_config.py` only. `SystemConfigService.update` itself has no recorder; config profiles, onboarding apply, and local-model config writes bypass. Owner: DAG-5 |
| Config export (env backup) | `system_config.export` | **Landed** | Byte length / version only; no `.env` body |
| Config import (env restore) | `system_config.import` | **Landed** | Same bound |
| Config last-good rollback | `system_config.rollback` | **Landed** | Attempt failure blocks restore |
| Tool allow/deny | `tool.execute` | **Landed** | `src/agent/runtime/tool_session.py`; completion-write failure is `retriable=false` |
| Analysis policy accept/reject | `analysis.submit` | **Landed** | `AnalysisSubmissionService` plus shared `record_audit`: HTTP async `/analyze`, HTTP **sync** `/analyze`, MCP `trigger_analysis`, event-triggered alerts, bot `/analyze`, scheduled-task dispatch, and portfolio `analyze_position`. Market-review / candidate discovery / AlphaSift remain a different queue API (not this event). |
| Audit-package / evidence-chain export | `audit_package.export` / `evidence_chain.export` | **Landed** | `src/api/v1/endpoints/evidence_pack.py`. Product package completeness remains [#127](https://github.com/SiinXu/stock-pulse-ai/issues/127); this is not a second security sink. See [Evidence chain audit package](evidence-chain-audit-package_EN.md) |

### Additional landed types (do not re-implement)

| Operation | `event_type` | Status | Owner / notes |
| --- | --- | --- | --- |
| HITL proposal / transition / consume / rule | `approval_proposal`, `approval_transition`, `approval_consume`, `approval_rule`, `approval_completion` | **Landed** | [#251](https://github.com/SiinXu/stock-pulse-ai/issues/251) closed 2026-07-25. `src/services/approval_service.py`. Default-off; see [human-approvals_EN.md](human-approvals_EN.md) |
| Plugin load/enable/disable/reload | `plugin.lifecycle` | **Landed** | Administrator mutations fail closed; **startup** load is best-effort so one recorder outage does not block unrelated plugins |
| MCP auth | `mcp.auth` | **Landed** | `src/mcp_server/auth_gate.py`, `src/mcp_server/server.py` |
| MCP tool list / call / cancel | `mcp.request` | **Landed** | Includes `action=mcp.request.cancel`. HTTP analysis cancel is a different privileged stop (DAG-3) |
| Local OCR / CLI process | `local_process.execute` | **Landed** | Targets `local_process.ocr` / `local_process.cli` |
| Capability register/update/retire and unauthenticated deny | `capability.write` | **Landed** | `src/capability_registry/write_audit.py`; capability writes are **not** auth-exempt |
| Research API conclusions | `research_api.request` | **Landed** | `src/api/v1/endpoints/research.py` |
| Research pack export | `research_pack.export` | **Landed** | Fail-closed attempt-before-bytes |
| Reasoning-trace export | `reasoning_trace.export` | **Landed** | Fail-closed attempt-before-bytes |

### Remaining privileged gaps

| Operation | Surface | Status | Why it is in scope | Owner |
| --- | --- | --- | --- | --- |
| Bot `/analyze` | `src/bot/commands/analyze.py` → `AnalysisSubmissionService.submit` (`query_source="bot"`, actor `bot`/`bot`) | **Landed** | Attempt-before-queue; request_context stays on the task, not in audit metadata | DAG-1 |
| Scheduled-task dispatch | `src/services/scheduled_task_service.py` → `submit_tasks_batch` (`query_source="scheduled_task"`, actor `scheduler`/`scheduled_task`) | **Landed** | Attempt is committed before the admission fence so SQLite is not double-locked; retry of an owned execution is not a new `analysis.submit` | DAG-1 |
| Portfolio position analysis | `src/api/v1/endpoints/portfolio.py` `analyze_position` (`query_source="portfolio"`, actor `api_client`/`portfolio_submitter`) | **Landed** | HTTP analysis admission; holding quantity/cost/account are queue kwargs only | DAG-1 |
| HTTP sync `/analyze` | `src/api/v1/services/analysis_api_service.py` `handle_sync_analysis` | **Landed** | Same `analysis.submit` contract as async; attempt before `analyze_stock`, completion `success`/`failure` | DAG-1 |
| Scheduled-task create/enable/disable | `src/api/v1/endpoints/scheduled_tasks.py` | **Missing** | Privileged automation control plane. No PUT/PATCH/DELETE definition routes exist | DAG-2 |
| Analysis HTTP cancel | Open PR [#1466](https://github.com/SiinXu/stock-pulse-ai/pull/1466); not on `main` | **Missing (incoming)** | Privileged stop of running analysis. #1466 adds the route **without** security-audit. Do not stack audit onto that PR | DAG-3 after #1466 merges |
| Report Markdown/HTML/PDF export | `src/api/v1/endpoints/report_export.py` | **Missing** | AUDIT-02 export / protected-data. Optional follow-on | DAG-4 |
| History delete (by code / by ids) | `src/api/v1/endpoints/history.py` | **Missing** | Protected-data destruction. Optional follow-on | DAG-4 |
| Config profiles apply/save | `src/services/config_profile_service.py` → `SystemConfigService.update` | **Missing** | Same privileged config mutation as HTTP `system_config.write` | DAG-5 |
| Onboarding apply | `src/services/onboarding_plan_service.py` → `SystemConfigService.update` | **Missing** | Same unaudited config writer | DAG-5 |
| Local model register/assign/delete that writes config | `src/services/local_model_service.py` → `SystemConfigService.update` | **Missing** | Runtime model control plane via the same unaudited updater | DAG-5 |
| Model pack import / desktop activation | `src/api/v1/endpoints/model_packs.py` | **Missing** | Trusted artifact install | DAG-5 / defer with owner |
| HTTP market-review / candidate discovery / AlphaSift | `submit_background_task` in analysis API, `candidate_discovery.py`, `alphasift.py` | **Missing** | Privileged background execution on a different queue API. **Not** DAG-1 | Named coverage-map row; later owner |
| Investment-framework mutations | `src/services/investment_framework_service.py` | **Missing** | Analysis-policy content; defer unless framed as policy | Deferred unless reclassified |

DAG-1 extended `AnalysisSubmissionCommand` with `query_source`, `request_context`, `portfolio_context`, `strict_skill_selection`, and actor identity, and shares `record_audit` plus attempt-before-protected-operation fail-closed order. HTTP async / MCP / event-trigger keep `api_client` / `analysis_submitter`. Do not fold market-review, candidate discovery, or AlphaSift into this event.

DAG-5 should audit `SystemConfigService.update` once rather than patching each caller. The already-audited HTTP `system_config.write` path must not double-emit.

### Deferred (not in this DAG)

| Operation | Status | Reason |
| --- | --- | --- |
| CLI / GitHub Actions daily analysis (`src/app/analysis.py` / `main.py`) | **Deferred** | Operator TTY / Actions identity is the actor; not an untrusted API |
| Security-audit query itself (`GET /api/v1/security/audit-events`) | **Deferred** | Read of security records; #1062 acceptance did not require self-audit |
| Watchlist / portfolio CRUD / alerts | **Deferred** | Product data, not the original privileged map; would unbounded-expand #1062 |
| Cryptographic tamper-evidence (hash chain / HMAC / WORM) | **Deferred** | AUDIT-03 is append-oriented and access-controlled, not HSM/WORM. Residual operator-trust limitation |
| SIEM / bulk audit export | **Deferred** | Explicit #1062 non-goal |
| Multi-tenant actors | **Deferred** | [#230](https://github.com/SiinXu/stock-pulse-ai/issues/230) closed not-planned; AUTH-05 remains single-admin |
| Agent observability traces | **Deferred** | Separate sink owned by [#222](https://github.com/SiinXu/stock-pulse-ai/issues/222) |
| Replacing the product evidence package | **Deferred** | Explicit non-goal; remaining product completeness is #127 |

Export/import/rollback metadata carries only bounded config version, flags, and
byte length—never raw `.env` content or secret values. Auth policy/password
events never store password material. Local-process metadata is limited to
engine/preset identifiers, language codes, timeouts, status, and file extension
or size evidence—never image bytes, prompts, stdout, or secrets.

## Remaining Coverage DAG

Do not merge DAG-1 through DAG-5. Do not include watchlist, portfolio CRUD, or
alerts. Do not fold market-review, candidate discovery, or AlphaSift into
DAG-1.

```text
DAG-0  this coverage map (docs only; no runtime behavior)
  │
  ├── DAG-1  analysis admission (landed)
  │            bot + scheduled dispatch + portfolio analyze_position
  │            + HTTP sync /analyze
  │            preserve query_source / context kwargs / actor identity
  │
  ├── DAG-2  scheduled-task create/enable/disable
  │            independent of DAG-1
  │
  ├── DAG-3  analysis HTTP cancel audit
  │            blocked on PR #1466 merge; rebase onto that head;
  │            do not stack onto the in-flight cancel PR
  │
  └── DAG-4  report export + history delete
               optional AUDIT-02; independent

DAG-5  SystemConfigService.update bypasses
         (profiles / onboarding / local-model config writes)
         + model packs if still marked privileged
         coverage-map Missing now; implement after DAG-1;
         one service-level audit, no HTTP double-emit
```

Suggested later titles (English, no tool prefix):

1. `docs: publish privileged security-audit coverage map for #1062` (DAG-0, landed)
2. `fix: audit analysis admission on bot scheduler portfolio and sync HTTP paths` (DAG-1, landed)
3. `feat: emit security-audit events for scheduled-task mutations`
4. `feat: audit analysis task cancel at the HTTP boundary` (after #1466)
5. `feat: audit report export and history deletion`

Keep #1062 open until remaining in-scope rows are **Landed** or explicitly
**Deferred** with an owner. Do not close #535 as a substitute for this map.

## Issue And Baseline Hygiene

These are documentation facts, not GitHub mutations performed by this page:

- #1062 Workstream A–D and acceptance checkboxes are still unchecked on the
  live issue. The original A-list HTTP/MCP/tool/HITL/plugin/local-process
  paths and evidence-package export are already **Landed** or **Partial**.
  Remaining boxes should later list DAG-1..5 only.
- [#251](https://github.com/SiinXu/stock-pulse-ai/issues/251) HITL gates are
  closed and emitting `approval_*` events. A Current Gaps row that still says
  gates are missing is stale; see [security-baseline.md](security-baseline.md).
- [#535](https://github.com/SiinXu/stock-pulse-ai/issues/535) is the parent
  product requirement. Remaining **security-audit coverage** is #1062.
  Remaining **product evidence-package completeness** is #127. Do not treat
  evidence-package export as an unimplemented second security sink.
- [#191](https://github.com/SiinXu/stock-pulse-ai/issues/191) ToolSurface
  sandbox and durable deny are landed. Workstream C tool boxes being
  unchecked is issue hygiene, not missing code.

## Persistence And Redaction

`SecurityAuditService` calls the central `src.utils.sanitize` recursive
redactor before `SecurityAuditRepository` receives an event. The repository
exposes append, bounded query, time-based retention, and hard capacity
enforcement only; it has no event update or per-row deletion API. Raw SQLite
regression tests prove that tokens, cookies, secret-labelled fields, and
credential-bearing URLs do not reach the table.

## Retention And Capacity

Defaults (override via shared `Config` / environment):

| Setting | Env | Default | Bounds |
| --- | --- | --- | --- |
| Time retention | `SECURITY_AUDIT_RETENTION_DAYS` | 90 | 1–3650 |
| Hard capacity | `SECURITY_AUDIT_MAX_EVENTS` | 10000 | 100–1000000 |

Retention runs on append and query (once per UTC day per service/database pair).
Capacity runs after every successful append and deletes the oldest rows first
when the table exceeds the configured maximum. Both bounds are independent:
either can remove rows. Operators that need longer legal hold must export or
archive outside this table before retention or capacity removes rows.

## Access Control

`GET /api/v1/security/audit-events` supports bounded pagination and exact
event-type, outcome, correlation, and UTC time filters. It requires a valid
single-administrator session. The endpoint explicitly returns `403`
`security_audit_auth_required` when administrator authentication is disabled
and `401` `unauthorized` for a missing or invalid session. Store failure
returns `503` `security_audit_unavailable`. A **read-only Web UI** under
Settings → System & Security → Auth & Security (Security audit panel) consumes
the same GET API, trusts server-side redaction, and surfaces an honest blocked
state when auth is disabled. There is no multi-tenant RBAC, bulk export, or
SIEM integration in this delivery.

Auth middleware exemptions are login, status, health, scorecard, docs, and
OpenAPI only. Capability writes are **not** exempt; an unauthenticated deny
emits `capability.write` or fails closed with `503`. Actor ids are bounded
tokens (`admin_session`, `unauthenticated`, `capability_registry`,
`analysis_submitter`, `bot`, `scheduled_task`, `portfolio_submitter`), not emails. MCP capability `security_audit_admin` is
`not_exposed`.

The in-memory outbound-activity ring (`GET /api/v1/security/outbound-activity`)
is a **separate** NET-06 sink, not the durable `security_audit_events` table.

## Tamper And Integrity Limits

The repository is append-oriented: it exposes append, bounded query, time
retention, and capacity deletion only. There is no event update or per-id
delete API. Retention and capacity **are** deletes (oldest rows first) and are
not a legal-hold archive.

The SQLite file is operator-writable. This delivery has no hash chain, HMAC,
or WORM device. Cryptographic tamper-evidence was a historical #535 comment
and is **not** in #1062 acceptance. Treat that as a residual operator-trust
limitation, not a hidden bug of this issue.

## Failure Semantics

Protected paths persist the attempt before executing the protected operation.
If that write fails, the operation fails closed with
`security_audit_unavailable`: login does not issue a cookie, configuration does
not call the mutation service, auth policy/session/password changes do not
proceed, config export/import/rollback do not run, a tool handler is not
invoked, analysis work is not enqueued, MCP discovery/tool calls are rejected,
administrator plugin mutations stop, and local OCR/CLI process starts do not
proceed. Completion-write failures are also surfaced rather than swallowed.

Audit write failures are never silent: the service logs a redacted
`security_audit_append_failed` / related error via `log_safe_exception`, and
callers receive the stable `security_audit_unavailable` code (HTTP `503` on API
paths). Operators must treat that code as a visible availability alert for the
audit store.

The dependency factory and its FastAPI validation wrapper are separate, so a
test or integration override that returns a missing or malformed recorder is
still rejected with the same stable `503` contract. Login, System
Configuration, asynchronous analysis, and the audit query endpoint validate
their injected dependency at entry. `BoundToolSession` cannot be constructed
without a recorder that provides callable `record_attempt` and
`record_completion` methods.

SQLite audit writes are not atomic with password/configuration files, tool side
effects, or the in-memory task queue. A completion failure can therefore mean
that an action happened while the caller received `security_audit_unavailable`;
the earlier attempt remains durable. Operators must correlate the attempt with
ordinary operational diagnostics and must not treat a missing completion as
proof that no side effect occurred.

For tools specifically, a completion-write failure returns `retriable=false`
and explicitly says execution may already have occurred. The result is memoized
under the existing tool name/argument cache key, so an identical call in the
same `BoundToolSession` cannot dispatch the handler a second time.

For a batch analysis submission, all attempts are persisted before the queue is
called. Once the queue accepts/rejects the batch, completions are appended in
request order. If one completion write fails, the endpoint immediately returns
`security_audit_unavailable`; already written completions remain, later items
retain attempt-only records, and any tasks accepted by the queue may continue.

Plugin **startup** load uses best-effort audit writes (`required=False`) so a
recorder outage does not block unrelated plugins. Administrator plugin
mutations opt into the same fail-closed contract as other privileged paths.

## Relationship To Agent Observability (#222)

Security audit is a **separate sink** from Agent runtime events, tool
diagnostics, and cross-stage traces owned by #222. They may share redaction
helpers and correlation identifiers, but security-audit rows are:

- append-only and retention/capacity bounded in SQLite;
- administrator-queryable via `/api/v1/security/audit-events`;
- required (fail closed) at privileged acceptance boundaries.

Debug traces and run diagnostics must not be treated as the security-audit
trail.

## Rollback

Prefer a forward fix. Migration `202607240001_security_audit_events` has no
downgrade, and an older application can reject a database containing the newer
applied migration. A full rollback requires stopping writers and restoring the
pre-change application and database backup as a matching pair. Never delete an
applied migration row or individual audit rows to simulate rollback.
Reverting configuration of `SECURITY_AUDIT_RETENTION_DAYS` /
`SECURITY_AUDIT_MAX_EVENTS` only changes future enforcement bounds; already
deleted rows are not restored.
