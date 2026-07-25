# Durable Security Audit Phase 1

StockPulse persists representative privileged-operation decisions in the main
SQLite database under the versioned `security-audit-v1` contract. This trail is
separate from application logs, Agent runtime events, Run Diagnostics, and the
cross-stage observability work tracked by #222.

## Event Contract

Every row is append-oriented and contains:

- a UTC `occurred_at` timestamp and stable `event_type`;
- `attempt` or `completion` phase;
- bounded actor and execution identities;
- stable action and bounded target type/id;
- outcome and reason code;
- one correlation ID reused by the attempt and completion;
- recursively redacted, size-bounded metadata.

Metadata is bounded to 16 object keys, 256 items per list, 256 characters per
string, and two nested collection levels. The 256-item list bound covers the
complete current System Configuration catalog in one correlated audit event
while retaining explicit headroom for dynamic connection fields. Oversized
metadata fails closed; key identities are never silently truncated.

Phase 1 records login success and rejection, sensitive System Configuration
writes, real `BoundToolSession` allow/deny decisions, and asynchronous analysis
task acceptance or duplicate rejection. It records configuration key names,
never values. It does not yet cover every backup/restore, auth-policy, export,
session-invalidation, HITL, or protected-data boundary tracked by #535.

## Persistence And Redaction

`SecurityAuditService` calls the central `src/utils/sanitize.py` recursive
redactor before `SecurityAuditRepository` receives an event. The repository
exposes append, bounded query, and time-based retention only; it has no event
update or per-row deletion API. Raw SQLite regression tests prove that tokens,
cookies, secret-labelled fields, and credential-bearing URLs do not reach the
table.

The fixed Phase 1 retention window is 90 days. Retention runs on append and
query. This deliberately adds no new deployment configuration surface.

## Access Control

`GET /api/v1/security/audit-events` supports bounded pagination and exact
event-type, outcome, correlation, and UTC time filters. It requires a valid
single-administrator session. The endpoint explicitly returns `403` when
administrator authentication is disabled and `401` for a missing or invalid
session. Phase 1 has no Web UI, multi-tenant RBAC, export, or SIEM integration.

## Failure Semantics

Protected paths persist the attempt before executing the protected operation.
If that write fails, the operation fails closed with
`security_audit_unavailable`: login does not issue a cookie, configuration does
not call the mutation service, a tool handler is not invoked, and analysis work
is not enqueued. Completion-write failures are also surfaced rather than
swallowed.

SQLite audit writes are not atomic with password/configuration files, tool side
effects, or the in-memory task queue. A completion failure can therefore mean
that an action happened while the caller received `security_audit_unavailable`;
the earlier attempt remains durable. Operators must correlate the attempt with
ordinary operational diagnostics and must not treat a missing completion as
proof that no side effect occurred.

For a batch analysis submission, all attempts are persisted before the queue is
called. Once the queue accepts/rejects the batch, completions are appended in
request order. If one completion write fails, the endpoint immediately returns
`security_audit_unavailable`; already written completions remain, later items
retain attempt-only records, and any tasks accepted by the queue may continue.

## Rollback

Prefer a forward fix. Migration `202607240001_security_audit_events` has no
downgrade, and an older application can reject a database containing the newer
applied migration. A full rollback requires stopping writers and restoring the
pre-change application and database backup as a matching pair. Never delete an
applied migration row or individual audit rows to simulate rollback.
