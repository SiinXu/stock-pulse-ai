# Runtime capability inventory

`GET /api/v1/capabilities` exposes a read-only observation of capabilities
currently known to the running process. It is an inventory foundation for
issue #221, not a central capability registry: the endpoint cannot register,
resolve, grant, execute, budget, or health-check a capability.

## Owners and consistency

The projection does not maintain provider or tool catalogs. Each domain is
read from its existing owner:

| Domain | Authoritative owner | Inventory records |
| --- | --- | --- |
| `data` | provider runtime of the process manager that already serves callers | Active providers and the methods they declare |
| `tool` | Agent `ToolRegistry` | Registered definitions, owner-declared optional members, and scopes |
| `extension` | `PluginManager` and its unified extension registry | Plugin lifecycle observations and active contributions |
| `skill` | Installed `ApplicationServices` analysis-strategy catalog plus declarative `SkillManager` | Plugin analysis strategies and custom skill definitions actually loaded in-process |
| `pipeline` | Shared pipeline stage contract (`PIPELINE_STAGE_NAMES` / `PipelineStageName`) | Bound analysis pipeline stages; unbound names are reported, never invented |

Availability is never copied from a static readiness catalog. When a registry or
configuration owner cannot be read, that source is `error` or `not_initialized`
with an explicit `error_code`, and the response is `partial=true`. The inventory
never installs a substitute composition root to fabricate a successful snapshot.

Each source supplies one stable snapshot and generation. All records from that
source carry the same `source_generation` and `as_of`. Plugin lifecycle records
are deliberately separate from extension registrations: an enabled plugin with
no active registrations is not an executable capability.

The data source is observation-only. It reads the provider runtime of the
manager that already serves this process — the `ApplicationServices`
composition-root manager used by the analysis pipeline and stock services
first, then the process-shared Agent tool manager — and never constructs one:
a new `DataFetcherManager` would own a different provider runtime whose active
registrations belong to no caller. When neither manager exists yet, the data
source is reported as `not_initialized` instead of an empty inventory.

The extension and skill sources likewise observe only an already-installed
composition root. Calling the inventory never constructs a default
`ApplicationServices` instance: absence is `not_initialized`
(`application_services_not_initialized`). Skill configuration or catalog load
failures surface as `skill_config_unavailable` or `skill_catalog_unavailable`.

The tool source observes only an already-built process `ToolRegistry` and never
constructs one. Skill source generations include plugin identities plus a bounded
canonical hash of every record-visible declarative field (`name`, `source`,
`enabled`, `display_name`, and `required_tools`), so same-name metadata changes
and equal-count catalog swaps both advance generation. Pipeline stages are
bound only when the live `StockAnalysisPipeline` type exposes a stage runner
and bound stage methods reference the stage; registration alone never sets
`healthy=true`.

Owner generations cover every change a record can expose. Tool entries are
frozen copies captured at registration, so a later in-place mutation of a live
`ToolDefinition` cannot change a published inventory; a real change requires
registration and advances the generation. Plugin lifecycle transitions advance
a dedicated lifecycle counter that is part of the published extension
generation, because they never touch an extension-registration generation.

If an owner cannot be read, the endpoint returns `200` with `partial=true`, an
explicit source status (`error`, `generation_drift`, or `not_initialized`), and
no fabricated records for that source. Consumers must not interpret missing
records from a failed source as disabled or unregistered capabilities.

## State semantics

The schema version is `capability-inventory/v1`. State fields are independent:

- `registered`: observed in the authoritative owner.
- `configured`: whether required configuration is known to be present.
- `dependency_ready`: whether runtime dependencies are known to be ready.
- `grantable`: whether the current ToolSurface/security context can grant use.
- `executable`: whether execution is known to be possible now.
- `healthy` and `degraded`: live operational health when an owner provides it.

Except for facts supplied by an owner, readiness remains `null`; registration
alone does not imply configuration, authorization, execution, budget, or
health. A plugin lifecycle record has `executable=false` and
`reason_code=lifecycle_not_capability` because lifecycle state is diagnostic,
not a contributed capability.

`reason_code` carries the owner's own explanation for an absent optional tool.
`feature_disabled` and `missing_config` describe configuration, while
`construction_failed` and `construction_produced_no_tool` describe a configured
factory that raised or produced nothing. `not_registered` is used only when the
owner supplied no reason at all, so a dependency failure is never presented as
a plain absence.

Owner identity is never collapsed into one scalar. `provider` names the single
owning identity, `providers` lists every identity supplying the capability, and
`provider_count` is the true supplier count. A method served by many providers
therefore cannot overflow a bounded field and turn a healthy source into an
error. If the count ever exceeds the list bound, the listed subset is reported
with `reason_code=provider_list_truncated` and the full count preserved.

## Request and response

Use repeated `domain` parameters to select sources:

```http
GET /api/v1/capabilities?domain=data&domain=tool
```

Example (abbreviated):

```json
{
  "schema_version": "capability-inventory/v1",
  "partial": false,
  "sources": [
    {"source": "tool", "state": "ok", "generation": "31", "as_of": "2026-08-09T08:00:00+00:00", "error_code": null}
  ],
  "items": [
    {
      "id": "tool:get_realtime_quote",
      "domain": "tool",
      "type": "agent_tool",
      "owner": "agent.tool_registry",
      "provider": "get_realtime_quote",
      "version": "1",
      "source_generation": "31",
      "as_of": "2026-08-09T08:00:00+00:00",
      "registered": true,
      "configured": null,
      "dependency_ready": null,
      "grantable": null,
      "executable": null,
      "healthy": null,
      "degraded": null,
      "dependencies": [],
      "scopes": ["market_data:read"],
      "markets": [],
      "providers": [],
      "provider_count": null,
      "reason_code": null,
      "display_name": "get_realtime_quote"
    }
  ],
  "total": 1,
  "executable_count": 0,
  "non_executable_count": 0,
  "unknown_executable_count": 1
}
```

An unknown domain returns `400`. With `ADMIN_AUTH_ENABLED=true`, the production
application requires a valid signed admin session cookie and rejects missing or
invalid sessions with the standard `401 unauthorized` envelope.

## Extension example and compatibility

When an enabled plugin contributes registration `demo_tool` at extension point
`agent_tool`, the inventory adds an `extension_registration` record such as
`extension.registration:agent_tool:demo_tool`. Its `version` is the extension
contract version, `provider` is the plugin ID, and `dependencies` contains the
extension point. Plugin compatibility is enforced by the existing plugin
manager before a registration becomes active; this inventory does not perform
a second compatibility decision.

Consumers must branch on `schema_version`, tolerate new records and nullable
states, and treat source errors as unknown.


## Write-side registry (control plane)

In addition to the read-only inventory, the process exposes a durable
**write-side** capability control plane (schema
`capability-write-registry/v1`) for operator-declared metadata used by
dependency resolution and task-aware routing. It does **not** replace live
owners: registration here does not install tools, plugins, or models into the
execution path by itself.

| Operation | Endpoint | Notes |
| --- | --- | --- |
| List declarations | `GET /api/v1/capabilities/registry` | Optional `domain`, `include_retired` |
| Register | `POST /api/v1/capabilities/registry` | Privileged; security-audit attempt/completion required |
| Update | `PUT /api/v1/capabilities/registry/{capability_id}` | Identity fields immutable |
| Retire | `POST /api/v1/capabilities/registry/{capability_id}/retire` | Idempotent for already-retired ids |
| Resolve dependencies | `POST /api/v1/capabilities/resolve` | Fail-closed ready flags + reason codes |
| Task-aware route | `POST /api/v1/capabilities/route` | Explainable decision for diagnostics |

Write domains: `data`, `tool`, `skill`, `pipeline`, `llm`, `persona`.

Hard rules:

- Mutations require the privileged-operation security audit chain
  (`event_type=capability.write`). Audit unavailability returns `503` with
  `security_audit_unavailable` and **does not** apply the write.
- Validation, identity conflicts, and store corruption return explicit error
  codes. The API never returns a fabricated success snapshot for a failed
  registration.
- Storage defaults to
  `<dir-of-DATABASE_PATH>/capability_write_registry.json`
  (override with `CAPABILITY_WRITE_REGISTRY_PATH`). Corrupt files fail closed.

### Dependency resolution

`POST /api/v1/capabilities/resolve` evaluates declared dependencies against the
write registry and, optionally, the live inventory. Supported dependency tokens:

- `capability_id`
- `capability_id@1.2.3` / `capability_id==1.2.3` (exact)
- `capability_id>=1.0.0`
- `capability_id~=1.2` (compatible release)

Missing, retired, non-executable, or version-incompatible dependencies yield
`ready=false` with an explicit `reason_code` (never fail-open ready).

### Task-aware model routing

`POST /api/v1/capabilities/route` returns a versioned
`task-route-decision/v1` decision for task classes:
`report`, `agent`, `vision`, `market_review`, `cheap_scan`, `deep_reasoning`,
`coding`.

Selection order:

1. Explicit task pin (`TASK_ROUTING_PIN_*`) when set
2. Existing shared model pin (`LITELLM_MODEL` / `AGENT_LITELLM_MODEL` /
   `VISION_MODEL` as applicable)
3. When `TASK_ROUTING_ENABLED=true`, score active write-side `llm` capabilities
   by tags + `TASK_ROUTING_POLICY` (`quality` | `cost` | `local_first`)
4. Otherwise return an empty selection with `reason_code` such as
   `routing_disabled` or `no_matching_candidate`

Every decision includes `reason_code`, `explain[]`, scored `candidates[]`, and
`pin_source` so operators can audit routing in diagnostics without opaque
behavior. Manual pins always win.

Optional multi-model ensemble remains out of this slice and is still tracked
under issue #204.

## Still open (issues #221 / #204)

- ToolSurface grant/budget policy enforcement on every execution path
- Full migration of every extension class onto the write-side contract at
  startup/enable/reload
- Product UI for capability installation, enablement, and governance
- Optional budget-limited ensemble/vote mode

