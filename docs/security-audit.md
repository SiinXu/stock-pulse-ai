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

## Connected Privileged Paths

| Operation | `event_type` | Status |
| --- | --- | --- |
| Login success/failure | `auth.login` | Connected |
| Auth enable/disable | `auth.policy` | Connected |
| Logout / session invalidation | `auth.logout` | Connected |
| Password change | `auth.password_change` | Connected |
| System config write | `system_config.write` | Connected |
| Config export (env backup) | `system_config.export` | Connected |
| Config import (env restore) | `system_config.import` | Connected |
| Config last-good rollback | `system_config.rollback` | Connected |
| Tool allow/deny | `tool.execute` | Connected |
| Analysis accept/reject | `analysis.submit` | Connected |
| HITL proposal/transition/consume | `approval_*` | Connected |
| Plugin load/enable/disable/reload | `plugin.lifecycle` | Connected |
| MCP auth / tool list / tool call / cancel | `mcp.auth` / `mcp.request` | Connected |
| Local OCR worker accept/reject | `local_process.execute` (`local_process.ocr`) | Connected |
| Local CLI subprocess accept/reject | `local_process.execute` (`local_process.cli`) | Connected |
| Analysis evidence-package export (#127) | — | Out of scope (separate product) |

Export/import/rollback metadata carries only bounded config version, flags, and
byte length—never raw `.env` content or secret values. Auth policy/password
events never store password material. Local-process metadata is limited to
engine/preset identifiers, language codes, timeouts, status, and file extension
or size evidence—never image bytes, prompts, stdout, or secrets.

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
single-administrator session. The endpoint explicitly returns `403` when
administrator authentication is disabled and `401` for a missing or invalid
session. A **read-only Web UI** under Settings → System & Security → Auth &
Security (Security audit panel) consumes the same GET API, trusts server-side
redaction, and surfaces an honest blocked state when auth is disabled. There is
no multi-tenant RBAC, bulk export, or SIEM integration in this delivery.

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
