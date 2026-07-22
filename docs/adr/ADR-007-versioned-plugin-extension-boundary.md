# ADR-007: Establish A Versioned Plugin Extension Boundary

- Status: `Accepted`
- Decision date: 2026-07-21
- Decision owners: StockPulse maintainers
- References: [Issue #274](https://github.com/SiinXu/stock-pulse-ai/issues/274), [Issue #273](https://github.com/SiinXu/stock-pulse-ai/issues/273), [Issue #276](https://github.com/SiinXu/stock-pulse-ai/issues/276), [PR #339](https://github.com/SiinXu/stock-pulse-ai/pull/339), [plugin extension contract](../plugin-extension-contract.md), [ADR-005](ADR-005-provider-fallback-and-circuit-control.md), [PR #312](https://github.com/SiinXu/stock-pulse-ai/pull/312), [serialized artifact versioning](../database-migrations_EN.md#serialized-artifact-versioning)

## Context

StockPulse already has several local extension-like seams, but they do not form
one plugin contract. `DataFetcherManager` accepts and orders `BaseFetcher`
instances, `SkillManager` registers analysis skills, and `ToolRegistry`
registers Agent tools. Notifications instead use a fixed channel enum and
dispatch branch, while report templates are resolved by the Jinja renderer in
`src/services/report_renderer.py`. Task and Agent runtimes publish internal
events, but there is no process-wide plugin Hook bus.

Exposing those local APIs directly would also expose the wrong authority. The
data manager owns market filtering, fallback, circuit health, layered cache,
adaptive ordering, and diagnostics. The Tool Surface owns tool policy and
execution guards. `NotificationService` owns route selection, noise control,
per-channel isolation, and result aggregation. The report renderer owns its
fallback behavior. Plugins may supply implementations, but must not bypass
those policies.

PR #312 later added bounded health-based ordering among eligible providers at
the same static priority while retaining ADR-005's capability, static-priority,
circuit, and process-local authority boundaries. That PR explicitly recorded
the change as compatible evolution rather than a new architectural decision.
This ADR preserves the current behavior and links the history in both records;
it does not recast ADR-005 as the source of the adaptive-ordering mechanics.

Python code loaded from outside the application is trusted process code. A
manifest cannot prevent it from reading files, environment variables, or
network credentials. This batch has no sandbox, capability broker, package
installer, or separate plugin process.

## Decision

Establish one versioned plugin boundary with a shared lifecycle, ownership-aware
registration context, and these first official extension points:

- Data Providers
- Analysis Strategies
- Agent Tools
- Notification Channels
- Report Templates
- Event Hooks

Every registration carries an extension-point identity, plugin-owned stable ID,
contract version, implementation, priority, and optional structured metadata.
The plugin context tracks ownership so disabling a plugin removes all of its
registrations even when its unload callback fails. Duplicate IDs within an
extension point are rejected rather than silently overwritten.

The existing managers and services remain policy authorities. In particular,
provider plugins enter through `DataFetcherManager`; they do not own fallback,
health, cache, bounded adaptive ordering, capability filtering, or run
diagnostics. Tool plugins enter
through `ToolRegistry` and the Tool Surface. Notification adapters enter before
the existing route/noise/aggregation path, and report templates retain the
existing fallback renderer. Event Hooks are synchronous, observational,
process-local callbacks over immutable sanitized events; they cannot alter task
state or replace existing task/runtime event streams.

Plugin manifests use the fields `id`, `name`, `version`, `minAppVersion`,
`description`, `author`, and `permissions`, plus an API version and deterministic
entrypoint for external packages. `permissions` is descriptive metadata only in
this batch. It is not an authorization decision and must never be presented as
enforced protection.

External plugin discovery is opt-in. An unset or blank plugin directory loads
no external code. Configuring a directory explicitly trusts code under that
directory to run with the application's OS privileges. Discovery does not
download code or install dependencies, and one invalid or failing plugin does
not stop other plugins or the core application.

Extension contracts use independent major versions. Additive optional fields
and event names remain within a major version; removals, renames, type changes,
or semantic changes require a new major version and an explicit compatibility
path. Serialized registration/event payloads follow the repository's existing
[serialized artifact versioning](../database-migrations_EN.md#serialized-artifact-versioning)
policy rather than defining a second persistence policy.

UI components, Settings panels, and Custom commands are later-phase candidates.
This decision does not define their interfaces or authorize runtime wiring for
them. It also does not authorize changes to current composition entrypoints
while their cross-track gate is closed.

The detailed signatures, lifecycle transitions, extension-specific adapters,
and implementation status live in the
[plugin extension contract](../plugin-extension-contract.md).

## Consequences

- Plugin implementations gain one discoverable lifecycle and registration
  vocabulary without replacing domain-specific policy owners.
- Built-in and external plugins can use the same manifest and registration
  validation, while external loading remains disabled by default.
- Registration ownership and error isolation make enable/disable behavior
  deterministic and prevent a failing plugin from crashing core startup.
- Contract versions can evolve without coupling plugin releases to application
  or serialized artifact versions.
- External plugins still have arbitrary code execution within the application
  process. Operators must review and trust them; `permissions` offers no
  containment in this batch.
- Notifications, reports, strategies, tools, and Hooks require later adapter
  wiring before they are runtime-extensible. The ADR documents a boundary, not
  a claim that those integrations already exist.
- Additional registry and lifecycle code creates maintenance cost, so new
  extension points require a later ADR amendment or superseding decision rather
  than ad hoc registration APIs.
