# Personal Investment Framework Backend Contract

[Chinese](personal-investment-framework.md) | [English](personal-investment-framework_EN.md)

## Current Scope (Product Narrative Freeze)

Issue #465 started as a **backend** slice. Current `main` also wires a **partial** analysis inject and a **minimal Settings editor**. Keep marketing and docs aligned with the tree:

**Shipped:**

- Versioned local storage, CRUD/history APIs, optimistic concurrency
- Stable `InvestmentFrameworkContextReader` read adapter
- **Settings → Agent Behavior** minimal editor: create, versioned save, deactivate, delete (title/description/free-form rules/line-based risk and tracking; full decision-tree and dimension-matrix UI can come later)
- **Stock analysis path** inject: active framework is attached as **read-only research context** via `inject_framework_into_analysis_context` (`src/core/stages/analysis_stock.py` → analyzer prompt key `personal_investment_framework_prompt`)
- Report-strata **alignment slot enrichment** when a framework is active (`enrich_dashboard_framework_alignment`); otherwise `framework_alignment.status=not_configured` with a localized empty-slot summary

**Not shipped / not full product:**

- No import/export and no automated trading
- Not a general inject into Multi-agent, Research/Chat, or `AnalysisContextPack` as a pack field
- Inject is research context only—not live trading authority, and not a guarantee the model follows every rule

`framework_alignment.status=not_configured` means **no active framework** (missing or deactivated). It is an expected empty slot, not an analysis failure or bug.

## Account And Authorization Boundary

The current product has an optional single administrator session, not a user or tenant principal that can own authorization. The framework is therefore server-bound to the `local` scope. Requests cannot supply `owner_id`, `user_id`, or a tenant selector. With `ADMIN_AUTH_ENABLED=true`, the API uses the same valid administrator session cookie required by other `/api/v1/*` routes; with authentication disabled, it retains the existing local deployment semantics. This slice does not pre-implement the multi-tenant account or RBAC work in #230.

## Content Schema

Every immutable version stores a strict `InvestmentFrameworkContent`:

- `schema_version`: persisted-content contract version, currently `investment-framework-content-v1`; requests default to the current version when omitted.
- `title`: framework name.
- `description`: optional description.
- `root_node_id` plus `decision_tree`: stable node IDs and branch targets; terminal branches use `outcome`.
- `evaluation_dimensions`: names, relative weights, criteria, and optional descriptions.
- `risk_rules`: explicit risk and position rules.
- `tracking_criteria`: ongoing review conditions.
- `free_form_rules`: optional rules that do not fit a structured field.

Unknown fields and scalar coercion are rejected: for example, string `"1"` in a JSON body cannot stand in for an integer revision and string `"25"` cannot stand in for a numeric weight; response DTOs likewise cannot mask service-layer type drift. The `DELETE` revision continues to use the existing typed parsing contract for HTTP query parameters. The same strict boundary applies to persisted-content reads, so type drift or an unknown `schema_version` in old data fails closed instead of being silently converted. A framework must contain at least one substantive criterion; tree targets must reference declared nodes, every node must be reachable from the root, cycles are forbidden, and node IDs and dimension names must be unique. Weights are relative values in the `0..100` range; this phase does not require them to sum to 100.

## Storage And Version Semantics

Migration `202607240003_investment_framework_schema` adds:

- `investment_frameworks`: the local aggregate, `latest_version`, nullable `active_version`, an independent monotonic `revision`, and timestamps.
- `investment_framework_versions`: immutable content JSON, version, change summary, and creation time, unique on `(framework_id, version)`.

Creation starts at `version=1`, `active_version=1`, and `revision=1`. Every `PUT` creates a version and activates it; history is never edited in place. Deactivation clears only `active_version`, increments revision, and retains readable history. A later `PUT` creates and activates another version. Repeating deactivation on an already inactive framework is an idempotent no-op only when the caller supplies the **current** `expected_revision`; retrying with the stale revision from before the first deactivation still returns `409` and cannot bypass optimistic concurrency.

Every read and mutation validates the complete aggregate in one repository session: exactly one `local` aggregate is allowed; versions must be contiguous from 1 through `latest_version` and all belong to that aggregate; `active_version` must be null or equal to latest; and every historical content payload and change summary must decode strictly. Reachable revision states are bounded: for latest version `N`, an active aggregate permits `N <= revision <= 2N-1`, while an inactive aggregate permits `N+1 <= revision <= 2N`. History length is compared with the persisted counter before the actual rows are enumerated, so a corrupt enormous counter fails without allocating a synthetic range proportional to that claim. Orphan or foreign-owner versions, gaps, future versions, impossible revision/active combinations, malformed timestamps, excessively nested or otherwise corrupt content, and invalid summaries all fail closed as data errors. Create and delete cannot conceal that corruption, and the context reader cannot misreport it as "not configured."

After create, update, or deactivation flushes, the repository expires its ORM identity state, rereads persisted rows, and proves the exact requested aggregate transition and complete immutable-history fingerprint before commit. A database trigger or other write-side behavior that changes requested content, counters, activation, summaries, timestamps, or an older version therefore causes the whole transaction to roll back; responses are serialized only from that refreshed persisted state.

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

Every mutation's `expected_revision` protects aggregate state, not just the content version. Only confirmed revision drift returns `409 investment_framework_revision_conflict` and exposes `params.current_revision` so the client can refresh before retrying. A version-history constraint inconsistency fails closed as a server-side data error instead of masquerading as a retryable revision conflict. Absence returns `404 investment_framework_not_found`; invalid request schemas use the existing stable `422 validation_error` envelope.

The history endpoint currently returns the complete history in one unpaginated response. That keeps this backend slice's contract simple, but frequent long-term updates make read cost and payload size grow with the version count. Any future pagination must separately define compatible ordering, cursor, and total semantics.

## Web editor

Settings → **Agent Behavior → Investment Framework** exposes a dedicated horizontal tab with the inline minimal editor and framework status:

- Create the single local framework (`POST /api/v1/investment-framework`)
- Save with `expected_revision` to create and activate a new version (`PUT`)
- Deactivate (`POST .../deactivate`) so analysis no longer injects the framework
- Delete (`DELETE`) removes the aggregate and all history

**Version history** opens a read-only drawer on the same page and lists immutable versions in descending order with the active state. A user can copy any historical version into the current draft, then save it as a new version using the aggregate's current `revision`; copying alone does not mutate history or activation.

The editor supports title, description, free-form rules, and line-based risk/tracking criteria. Full decision-tree UI can be added later; richer content already stored via API remains readable. Saving free-form fields preserves `decision_tree` / `evaluation_dimensions` from the draft source (the current version or a copied historical version) so the minimal editor does not wipe structured content. On HTTP 409 revision conflicts, the UI reloads server state.

The page always shows a research-only disclaimer: not investment advice.

## Analysis injection path

The stock analysis pipeline (`src/core/stages/analysis_stock.py`, decision-dashboard Single path):

1. Calls `inject_framework_into_analysis_context` for the active framework.
2. **Fails soft** when none is configured or deactivated (same analysis behavior as before).
3. When active, writes `personal_investment_framework_prompt` plus a JSON snapshot; prompt formatting appends the read-only section.
4. After successful JSON parse, `enrich_dashboard_framework_alignment` fills report strata `framework_alignment` (default `partial` with title/version; preserves model `aligned`/`conflict` when already present).

Implementation: `src/services/investment_framework_prompt.py` and `InvestmentFrameworkContextReader`.

## Analysis-Context Read Boundary

`src.services.investment_framework_context.InvestmentFrameworkContextReader.read()` returns:

- A top-level frozen `investment-framework-context-v1` read-adapter payload with framework ID, content version, strict content, and update time when a framework is active. Nested content is a detached snapshot decoded from persisted JSON: in-memory caller mutations never write back to the database, but the object is not deeply immutable.
- `None` when no framework exists or it is inactive, leaving every existing analysis path unchanged.
- A fail-closed data error for corrupt persisted content instead of misreporting corruption as "not configured."

The stock analysis pipeline loads the reader through `src/services/investment_framework_prompt.py` (soft-fail on load errors). The reader is **not** a general `AnalysisContextPack` field and is **not** wired into Multi-agent / Research / Chat assembly the same way. Future expansion must converge remaining paths, precedence, context-size limits, report disclosure, and regression coverage. Presence of an active framework must not be described as live trading authority or guaranteed rule compliance.

## Migration And Rollback

Fresh databases receive the tables from SQLAlchemy metadata and the registered migration verifies their shape before recording its applied row. Supported legacy databases receive the equivalent shape in the same startup transaction. Direct migration execution creates and verifies both tables idempotently, including ordered columns, SQLite affinities, nullability, defaults, primary keys, exact unique constraints, the foreign key, and DDL tokens that alter semantics. Verification is pinned to the `main` schema and requires the complete canonical object inventory: the two tables plus exactly one expected SQLite unique-constraint autoindex per table, no aggregate foreign key, and no target-table TEMP objects, triggers, or explicit indexes. A same-name lookalike or shadow with extra conflict policies, duplicate constraints, `AUTOINCREMENT`, `CHECK`, `COLLATE`, `MATCH`, `DEFERRABLE`, generated-column behavior, auxiliary schema objects, or drifted types and constraints fails closed without an applied row. A failure in DDL, verification, or applied-row persistence rolls the entire transaction back, leaving neither partial tables nor a false applied state.

Production migrations are forward-only:

1. Stop writes and back up the database before upgrading.
2. To remove framework influence without reverting schema, deactivate it so the stock-analysis inject becomes a no-op and strata return `not_configured`.
3. To roll back both application and schema, stop new clients, restore the pre-migration database backup, and deploy the matching older code.
4. Never delete a `schema_migrations` row or drop tables manually to simulate a downgrade. Older code fails closed on an unknown higher migration by design.

Reverting the PR code while retaining a migrated database is not a supported old-version restoration path. When current or newer code remains deployed, empty additive tables do not change analysis behavior in the absence of a framework.
