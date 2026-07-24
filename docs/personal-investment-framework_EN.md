# Personal Investment Framework Backend Contract

[Chinese](personal-investment-framework.md) | [English](personal-investment-framework_EN.md)

## Current Scope

This phase delivers only the Issue #465 backend slice: versioned storage for the local account, CRUD/history APIs, optimistic concurrency, and a stable adapter for future analysis assembly. It does **not** include the complete Web page, import/export, automated trading, or real injection into Single, Multi, or Research prompts and reports. The existence of `InvestmentFrameworkContextReader` proves only a read boundary; it does not mean an Agent already follows the framework.

## Account And Authorization Boundary

The current product has an optional single administrator session, not a user or tenant principal that can own authorization. The framework is therefore server-bound to the `local` scope. Requests cannot supply `owner_id`, `user_id`, or a tenant selector. With `ADMIN_AUTH_ENABLED=true`, the API uses the same valid administrator session cookie required by other `/api/v1/*` routes; with authentication disabled, it retains the existing local deployment semantics. This slice does not pre-implement the multi-tenant account or RBAC work in #230.

## Content Schema

Every immutable version stores a strict `InvestmentFrameworkContent`:

- `title`: framework name.
- `description`: optional description.
- `root_node_id` plus `decision_tree`: stable node IDs and branch targets; terminal branches use `outcome`.
- `evaluation_dimensions`: names, relative weights, criteria, and optional descriptions.
- `risk_rules`: explicit risk and position rules.
- `tracking_criteria`: ongoing review conditions.
- `free_form_rules`: optional rules that do not fit a structured field.

Unknown fields are rejected. A framework must contain at least one substantive criterion; tree targets must reference declared nodes, every node must be reachable from the root, cycles are forbidden, and node IDs and dimension names must be unique. Weights are relative values in the `0..100` range; this phase does not require them to sum to 100.

## Storage And Version Semantics

Migration `202607240002_investment_framework_schema` adds:

- `investment_frameworks`: the local aggregate, `latest_version`, nullable `active_version`, an independent monotonic `revision`, and timestamps.
- `investment_framework_versions`: immutable content JSON, version, change summary, and creation time, unique on `(framework_id, version)`.

Creation starts at `version=1`, `active_version=1`, and `revision=1`. Every `PUT` creates a version and activates it; history is never edited in place. Deactivation clears only `active_version`, increments revision, and retains readable history. A later `PUT` creates and activates another version. Repeating deactivation on an already inactive framework is an idempotent no-op and does not advance revision again.

`DELETE` is intentionally different: under the revision guard, it deletes the aggregate and every historical version, after which a new framework can start again at version 1. Deletion is irreversible; use deactivation when history must remain.

## API

| Method | Path | Contract |
| --- | --- | --- |
| `POST` | `/api/v1/investment-framework` | Create the local framework; an existing aggregate returns `409` |
| `GET` | `/api/v1/investment-framework` | Read the latest version; inactive content remains readable with `is_active=false` |
| `PUT` | `/api/v1/investment-framework` | Supply `expected_revision` to create and activate a version |
| `GET` | `/api/v1/investment-framework/history` | Read complete immutable history in descending version order |
| `POST` | `/api/v1/investment-framework/deactivate` | Supply `expected_revision` to deactivate while retaining history |
| `DELETE` | `/api/v1/investment-framework?expected_revision=N` | Delete the aggregate and all history |

Every mutation's `expected_revision` protects aggregate state, not just the content version. A stale revision returns `409 investment_framework_revision_conflict` and exposes `params.current_revision` so the client can refresh before retrying. Absence returns `404 investment_framework_not_found`; invalid request schemas use the existing stable `422 validation_error` envelope.

## Analysis-Context Read Boundary

`src.services.investment_framework_context.InvestmentFrameworkContextReader.read()` returns:

- An immutable `investment-framework-context-v1` payload with framework ID, content version, strict content, and update time when a framework is active.
- `None` when no framework exists or it is inactive, leaving every existing analysis path unchanged.
- A fail-closed data error for corrupt persisted content instead of misreporting corruption as "not configured."

The reader is not wired into `AnalysisContextPack` or Agent prompts yet. Future real integration must converge Single, Multi, and Research assembly, precedence, context-size limits, report disclosure, and regression coverage.

## Migration And Rollback

Fresh databases receive the tables from SQLAlchemy metadata and the registered migration verifies their shape before recording its applied row. Supported legacy databases receive the equivalent shape in the same startup transaction. Direct migration execution creates and verifies both tables idempotently. A failure in DDL, verification, or applied-row persistence rolls the entire transaction back, leaving neither partial tables nor a false applied state.

Production migrations are forward-only:

1. Stop writes and back up the database before upgrading.
2. To remove framework influence without reverting schema, deactivate it; this slice does not inject it into prompts in the first place.
3. To roll back both application and schema, stop new clients, restore the pre-migration database backup, and deploy the matching older code.
4. Never delete a `schema_migrations` row or drop tables manually to simulate a downgrade. Older code fails closed on an unknown higher migration by design.

Reverting the PR code while retaining a migrated database is not a supported old-version restoration path. When current or newer code remains deployed, empty additive tables do not change analysis behavior in the absence of a framework.
