# Alternative Data Plugin Contract (ToolSurface)

Status: Accepted implementation contract for Issues **#139** and **#1144**.

Chinese twin: [`alternative-data-plugin-contract_zh.md`](alternative-data-plugin-contract_zh.md).

Related authorities:

- [Plugin extension contract](plugin-extension-contract.md) / ADR-007
- [Plugin development guide](plugin-development-guide.md) (manifest permissions #944)
- [External framework adapter guide](external-framework-adapter-guide.md) (OpenBB-style default-off adapters #892 family)
- [Community intel tool](community-intel-tool.md) (non-authoritative ToolSurface pattern)

Runnable reference package:
[`examples/plugins/example-alternative-data/`](../examples/plugins/example-alternative-data/).

## Goal

Provide a **standard plugin contract** for alternative / structured data
(corporate events, holdings changes, supply-chain tags, quantified sentiment)
so operators can opt in without hard-wiring paid feeds into core.

## Non-goals

- Shipping paid alternative-data vendors in-core.
- A seventh plugin extension point.
- Treating alt-data as verified market fact or decision authority.

## Defaults (fail closed / off)

| Gate | Default |
| --- | --- |
| External discovery | Off unless `PLUGINS_DIR` points at a reviewed parent directory |
| Process tool catalog | Corporate-events factory is **not** in `ALL_*_TOOLS` |
| Capability | Every call requires ToolSurface capability `alt_data:read` |
| Authority labels | Payload fields `authority=non_authoritative`, `role=supporting_only` are mandatory |

## Schema

Domain models live in `src/schemas/alternative_data.py`
(`schema_version=alternative-data-v1`).

| Field group | Contract |
| --- | --- |
| `category` | `corporate_events` (v1 reference), `holdings`, `supply_chain`, `quantified_sentiment` |
| `status` / `reason_code` | `available` \| `degraded` \| `unavailable` with stable reason codes |
| `events` / `coverage` / `citations` / `gaps` | Bounded, revalidated; citations/events must reference covered sources |
| `confidence` | `null` when evidence is absent — **never invent a neutral score** |
| `authority` / `role` / `disclaimer` | Fixed non-authoritative supporting labels |

Invalid provider output is rejected and projected as a typed degradation /
gap. Handlers must not return empty success frames to pretend the source worked
(same discipline as the OpenBB adapter demo).

## Permissions

| Layer | Behavior |
| --- | --- |
| Manifest `permissions` | Must declare every `ToolPolicy.permissions` entry (load-time subset check, code `manifest_permissions_undeclared`) |
| ToolSurface session | Missing `alt_data:read` → `permission_denied` with `missing_capabilities` |
| Sandbox | Declaration is **not** process isolation (#944 / #539) |

Capability catalog entry: `alt_data:read` in
`SUPPORTED_AGENT_TOOL_CAPABILITIES`.

## Registration path

1. Plugin `onload` builds `ToolDefinition` via
   `build_corporate_events_tool(provider)`.
2. Registers on frozen extension point `agent_tool` with `contract_version="1"`.
3. Host composition binds Agent Tools to the process `ToolRegistry` (existing
   surface v1 wiring).
4. Callers execute only through `ToolSurface` / `BoundToolSession` with an
   explicit grant of `alt_data:read` and stock scope.

## Reference category: corporate events (end-to-end)

Path proved by tests and the example plugin:

1. **Ingest** — fixture / provider returns `AlternativeDataObservation`.
2. **ToolSurface** — `get_corporate_events_brief` revalidates and projects
   `AlternativeDataResult` (or typed degradation).
3. **Governance** — `src/services/alternative_data_governance.py`:
   - `attach_alternative_data_block` → AnalysisContext `alternative_data` block
     with `quality_weighted=false` / `pollutes_core_quality=false`;
   - `project_alternative_data_evidence` → supporting strata only
     (`model_inference` / `synthesis` / `gap`).
4. **Analysis context** — `PipelineAnalysisArtifacts.alternative_data` optional
   field; omitted by default so pack shape is unchanged.

## Evidence stratification (bad data must not pollute core)

| Rule | Enforcement |
| --- | --- |
| Forbidden conclusion strata | `verified_fact`, `decision` (see `ALTERNATIVE_DATA_FORBIDDEN_CONCLUSION_STRATA`) |
| Core quality score | Computed **before** alt-data attach; overall_score / weighted block_scores unchanged |
| Missing / invalid / timeout | Gap conclusion + `confidence=null` + empty `events` |
| Partial coverage | `status=degraded`, supporting conclusion may be `partial`, explicit gap note |

Consumers of future evidence-chain packages should ingest
`AlternativeDataEvidenceProjection` as supporting evidence only.

## Operator checklist

1. Review plugin source; install any external deps manually (none for the fixture).
2. Set `PLUGINS_DIR` to the parent of the package directory.
3. Restart the process.
4. Grant sessions `alt_data:read` only when the operator intends alt-data tools.
5. Treat tool output as supporting context; keep primary market / fundamental
   sources as the authority for core conclusions.

## Follow-on categories

`holdings`, `supply_chain`, and `quantified_sentiment` reuse the same schema
envelope, permission, authority labels, and governance projectors. Add a new
tool factory + provider protocol per category; do not widen `alt_data:read`
semantics into a sandbox bypass.
