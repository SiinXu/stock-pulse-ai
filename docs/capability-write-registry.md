# Capability write registry and task-aware routing

This document covers the write-side capability control plane for issues #221
and #204. It complements the read-only inventory at
[`docs/capability-inventory.md`](capability-inventory.md).

## Boundaries

| Surface | Role |
| --- | --- |
| `GET /api/v1/capabilities` | Live-owner inventory only. Never registers, resolves, or mutates. |
| `GET/POST /api/v1/capabilities/registry` | Operator-declared write registry list / register |
| `PUT /api/v1/capabilities/registry/{id}` | Update non-retired entry |
| `POST /api/v1/capabilities/registry/{id}/retire` | Soft-offline (retire) |
| `POST /api/v1/capabilities/registry/resolve` | Dependency + version compatibility |
| `POST /api/v1/capabilities/route` | Explainable task-aware model selection |

Failed registrations **never** appear in the read inventory and **never** leave
a partial success snapshot on disk.

## Write domains

`data`, `tool`, `skill`, `pipeline`, `llm`, `persona` with matching
`capability_type` values. Active `llm` entries require `model_route`.

## Security audit

Register / update / retire reuse the privileged-operation security audit chain
(`event_type=capability.write`, actions `capability.register` /
`capability.update` / `capability.retire`). Audit unavailability fails closed
before durable writes. Unauthorized writes (auth enabled, no session) are
rejected with `401` and leave a `denied` completion event.

## Dependency resolution

Dependencies accept tokens:

- `capability_id`
- `capability_id@1.2.3` / `==`
- `capability_id>=1.0.0`
- `capability_id~=1.2`

Resolution checks the write registry first, then the live inventory. Cycles,
missing deps, retired targets, and version mismatches return explicit
`reason_code` values with `ready=false`.

## Task-aware routing

Config (default off):

| Key | Default | Meaning |
| --- | --- | --- |
| `TASK_ROUTING_ENABLED` | `false` | Enable automatic registry-based selection |
| `TASK_ROUTING_POLICY` | `quality` | `quality` / `cost` / `local_first` |
| `TASK_ROUTING_PIN_*` | empty | Explicit per-task pin; always wins |
| `CAPABILITY_WRITE_REGISTRY_PATH` | empty | Durable JSON path override |

Decision outcomes are structured (`task-route-decision/v1`) with `reason_code`,
`explain`, and scored `candidates`. When a run diagnostic context is active,
`POST /route` records an `event_type=task_route_decision` agent event so the
selection can be reconstructed later.

Manual pins always win. When routing is disabled or no LLM candidate matches,
the existing `LITELLM_MODEL` / `AGENT_LITELLM_MODEL` / `VISION_MODEL`
assignments are used as explicit fallbacks.

## Deferred

Optional multi-model ensemble remains deferred: no budgeted ensemble vote path
is shipped in this slice. Track remaining work on #204.

## Chinese

See [`docs/capability-write-registry_CN.md`](capability-write-registry_CN.md).

## Operators

Administrator authentication is required for write mutations when `ADMIN_AUTH_ENABLED=true`.
