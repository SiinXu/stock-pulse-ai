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
| `data` | manager-owned data-provider runtime | Active providers and the methods they declare |
| `tool` | Agent `ToolRegistry` | Registered definitions, owner-declared optional members, and scopes |
| `extension` | `PluginManager` and its unified extension registry | Plugin lifecycle observations and active contributions |

Each source supplies one stable snapshot and generation. All records from that
source carry the same `source_generation` and `as_of`. Plugin lifecycle records
are deliberately separate from extension registrations: an enabled plugin with
no active registrations is not an executable capability.

If an owner cannot be read, the endpoint returns `200` with `partial=true`, an
explicit source status (`error` or `generation_drift`), and no fabricated
records for that source. Consumers must not interpret missing records from a
failed source as disabled or unregistered capabilities.

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
states, and treat source errors as unknown. Central write-side registration,
dependency resolution, Stage/Skill/LLM/Persona metadata, ToolSurface grant and
budget evaluation, startup validation, and migration remain outside this API
and open under issue #221.
