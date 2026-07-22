# Plugin Extension Contract

Status: Accepted with [ADR-007](adr/ADR-007-versioned-plugin-extension-boundary.md)

This document is the living contract for StockPulse plugins. It defines the
first supported extension boundaries and the signatures that implementation
work must converge on. Runnable code remains authoritative while a listed
integration is not yet wired.

## Implementation Status

| Surface | Current authority | Track X delivery |
| --- | --- | --- |
| Plugin lifecycle, manifest, registry | No shared implementation | #273 X2a |
| Built-in/external startup wiring | `src/application_services.py` composition root | #273 X2b, only after GATE-P3 |
| Data Providers | `BaseFetcher` and `DataFetcherManager` | #276 X3 |
| Analysis Strategies | `Skill`, `SkillManager`, `StrategyEngine` | Contract only in this batch |
| Agent Tools | `ToolDefinition`, `ToolRegistry`, Tool Surface | Contract only; `src/agent/**` stays untouched |
| Notification Channels | `NotificationChannel`, sender mixins, `NotificationService` | Contract only in this batch |
| Report Templates | `src/services/report_renderer.py`, `templates/report_*.j2` | Contract only in this batch |
| Event Hooks | Task and Agent runtime event streams | Contract only in this batch |

"Contract only" means a plugin cannot yet rely on runtime wiring for that
extension point. It does not mean the existing core path is deprecated.

## Package And Manifest

Every plugin has a validated manifest. Built-in plugins may construct it in
Python. An external plugin is one direct child directory of the explicitly
configured plugins directory:

```text
<PLUGINS_DIR>/
  example-provider/
    manifest.json
    plugin.py
```

Example `manifest.json`:

```json
{
  "id": "example-provider",
  "name": "Example Provider",
  "version": "1.2.0",
  "minAppVersion": "1.0.0",
  "description": "Adds an example market-data source.",
  "author": "Example Maintainer",
  "permissions": ["network", "environment"],
  "apiVersion": "1",
  "entrypoint": "plugin.py:Plugin"
}
```

| Field | Contract |
| --- | --- |
| `id` | Required stable lowercase ID matching `[a-z0-9][a-z0-9._-]*`; never reused for a different plugin. |
| `name` | Required non-empty display name. |
| `version` | Required plugin release version using semantic `MAJOR.MINOR.PATCH` form. |
| `minAppVersion` | Required minimum compatible StockPulse application version. |
| `description` | Required non-empty operator-facing summary. |
| `author` | Required non-empty author or organization name. |
| `permissions` | Required list of descriptive permission IDs; metadata only and not enforced in this batch. |
| `apiVersion` | Optional plugin API major; defaults to `"1"`. |
| `entrypoint` | Optional external entrypoint; defaults to `plugin.py:Plugin`. It must remain relative to the plugin directory. |

`version`, `minAppVersion`, and `apiVersion` have different meanings. A plugin
release does not change the extension contract version, and an extension
contract bump does not rewrite the plugin's historical release versions.

The loader resolves the entrypoint to a class, calls it with the already
validated `PluginManifest`, and requires a `Plugin` instance. Constructor and
module-import failures are isolated before any registration is committed.

The external loader scans only when `PLUGINS_DIR` is non-empty. It does not scan
a default home directory, follow a remote catalog, download packages, install
dependencies, or hot-reload files. Invalid manifests, incompatible application
or API versions, duplicate plugin IDs, missing entrypoints, and import failures
are recorded against that plugin and skipped without aborting the scan.

## Lifecycle

The signature-level lifecycle contract is:

```python
PluginSource = Literal["builtin", "external"]
PluginState = Literal["registered", "enabled", "disabled", "failed"]


@dataclass(frozen=True)
class PluginOperationResult:
    plugin_id: str
    operation: str
    success: bool
    state: PluginState
    error_code: str | None = None


class Plugin:
    def __init__(self, manifest: PluginManifest) -> None: ...

    @property
    def manifest(self) -> PluginManifest: ...

    def onload(self, context: "PluginContext") -> None:
        """Register extension implementations for one enable transition."""

    def onunload(self) -> None:
        """Release plugin-owned resources for one disable transition."""
```

Manager operations converge on these signatures:

```python
class PluginManager:
    def register(
        self,
        plugin: Plugin,
        *,
        source: PluginSource,
    ) -> PluginOperationResult: ...

    def load(self, plugin_id: str) -> PluginOperationResult: ...
    def enable(self, plugin_id: str) -> PluginOperationResult: ...
    def disable(self, plugin_id: str) -> PluginOperationResult: ...
```

`register` validates `plugin.manifest` and records a plugin without invoking its
lifecycle. `load` performs the first `registered -> enabled` transition.
`enable` performs `disabled -> enabled` and is idempotent for an already enabled
plugin. `disable` invokes `onunload`, removes every registration owned by the
plugin in reverse registration order, and then records it disabled. Cleanup of
owned registrations still occurs if `onunload` raises.

`onload` runs at most once per enable transition and `onunload` at most once per
disable transition. If `onload` raises, its partial registrations are removed,
the plugin is marked failed, the exception is safely logged, and loading
continues with other plugins. A plugin callback exception never propagates into
core startup or another plugin's lifecycle.

External module import itself executes arbitrary Python before `onload` and must
receive the same isolation treatment. Error isolation protects application
availability; it is not a security boundary.

## Unified Registration API

The common API is intentionally small. Extension-specific validation happens
inside the registry selected by `extension_point`:

```python
ExtensionPoint = Literal[
    "data_provider",
    "analysis_strategy",
    "agent_tool",
    "notification_channel",
    "report_template",
    "event_hook",
]

class RegistrationHandle(Protocol):
    @property
    def extension_point(self) -> ExtensionPoint: ...

    @property
    def registration_id(self) -> str: ...

    def unregister(self) -> None: ...


class PluginContext(Protocol):
    def register(
        self,
        extension_point: ExtensionPoint,
        registration_id: str,
        implementation: object,
        *,
        contract_version: str = "1",
        priority: int = 100,
        metadata: Mapping[str, JSONValue] | None = None,
    ) -> RegistrationHandle: ...
```

Registration IDs are stable within an extension point. The registry stores the
owning plugin ID, rejects duplicate `(extension_point, registration_id)` pairs,
validates the implementation against the point's contract, and returns an
idempotent handle. A plugin may unregister early; the manager still retains
ownership bookkeeping for cleanup.

The registration ID is also the canonical native key. It cannot be an alias
that hides a collision in a point-specific registry:

| Extension point | Required canonical identity |
| --- | --- |
| Data Provider | `DataProviderRegistration.provider_id` |
| Analysis Strategy | `Skill.name` |
| Agent Tool | `ToolDefinition.name` |
| Notification Channel | `NotificationChannelAdapter.channel_id` |
| Report Template | `ReportTemplate.template_id` |
| Event Hook | `EventHookRegistration.hook_id` |

The unified registry serializes registration under one manager-owned lock. It
first validates exact identity equality and checks both its own keyspace and the
target native registry. Only then may it delegate to the native registry and
commit ownership. Existing permissive `SkillManager.register()` and
`ToolRegistry.register()` overwrite behavior must never be called when their
native key already exists. If delegation or later bookkeeping fails, the new
native entry and unified reservation are rolled back before the error reaches
the plugin. Unregistration removes only the exact implementation owned by that
handle, so a stale handle cannot remove a built-in or another plugin's entry.

Lower numeric priority runs first where ordering is meaningful. Equal priority
uses registration order for deterministic process-local behavior. Priority does
not let a plugin cross core eligibility boundaries or silently replace an
existing registration.

## Official Extension Points

### Data Providers

Registration shape:

```python
@dataclass(frozen=True)
class DataProviderRegistration:
    provider_id: str
    factory: Callable[[], DataProvider]
    markets: frozenset[str]
    capabilities: frozenset[str]
```

`DataProvider` is extracted by #276 as the stable, `BaseFetcher`-compatible
interface. The registration priority is the provider's static priority. Stable
provider ID, markets, and capabilities replace class-name-only capability
inference for new plugins; existing providers retain their current names and
behavior through compatibility adapters.

The provider factory supplies an implementation. `DataFetcherManager` remains
the only routing authority. For daily data, fresh L1/L2 cache lookup wraps the
provider route and may return before provider selection. On a miss, the manager
applies configuration and market/capability eligibility, preserves explicit
market routes and static-priority boundaries, and performs eligible adaptive
ordering. It then applies health/circuit admission immediately before each
serialized provider call, records the attempt in `RunDiagnosticContext`, stores
non-empty successes, and preserves stale last-good fallback only after the
eligible provider chain fails. Plugins cannot supply their own fallback loop or
bypass any of these policies.

[ADR-005](adr/ADR-005-provider-fallback-and-circuit-control.md) governs the
capability-first static-priority and circuit anchors. PR #312's compatible
evolution and [data source stability](data-source-stability.md) govern bounded
adaptive ordering inside those anchors, while the living document also owns
the layered-cache mechanics. X3 must preserve existing return values, error
classification, empty-result behavior, health keys, provider names in
diagnostics, cache attribution, and market-specific routes.

### Analysis Strategies

Registration shape:

```python
AnalysisStrategyRegistration = Skill
```

The current `Skill` definition is the first contract: stable `name`, prompt
instructions, category, tool requirements/allowlist, activation metadata,
market regimes, and execution hints. YAML and `SKILL.md` remain supported input
formats. `SkillManager` owns name lookup and activation; `StrategyEngine` owns
signal normalization, evidence partitioning, aggregation, and synthesis.

A plugin registers a definition. It does not replace `StrategyEngine`, write a
consensus result directly, or bypass required-tool and policy checks. Existing
custom skill directory loading remains a separate compatibility path until a
later implementation intentionally routes it through the plugin registry.

### Agent Tools

Registration shape:

```python
AgentToolRegistration = ToolDefinition
```

The implementation must be a `ToolDefinition` with an exact stable name,
serializable parameter schema, callable handler, category, and a declared
`ToolPolicy`. The plugin registry delegates to `ToolRegistry`; every execution
continues through the Tool Surface and its argument, stock-scope, timeout,
serialization, audit, and completion guards.

Plugin registration cannot grant a tool access, weaken strict policy
validation, publish a transport, or mutate Agent runner internals. Tool names
cannot overwrite built-ins. Runtime wiring is deferred because `src/agent/**`
belongs to the Agent decomposition track.

### Notification Channels

Registration shape:

```python
@dataclass(frozen=True)
class NotificationRequest:
    content: str
    route_type: str | None
    severity: str | None
    image_bytes: bytes | None
    stock_codes: tuple[str, ...]
    metadata: Mapping[str, JSONValue]


@dataclass(frozen=True)
class NotificationAdapterResult:
    success: bool
    error_code: str | None = None
    retryable: bool = False
    diagnostics: str | None = None


class NotificationChannelAdapter(Protocol):
    channel_id: str
    display_name: str

    def is_available(self) -> bool: ...

    def send(
        self,
        request: NotificationRequest,
    ) -> NotificationAdapterResult: ...


NotificationChannelFactory = Callable[[Config], NotificationChannelAdapter]
```

The factory receives the application configuration and returns one adapter.
The core, not the adapter, measures latency, binds the canonical channel ID, and
maps `NotificationAdapterResult` into the existing `ChannelAttemptResult` and
`NotificationDispatchResult` semantics. One adapter failure must not stop later
channels or the analysis workflow.

Dynamic routing extends the current plain-string route contract without
bypassing it. For each dispatch, the core takes an allowed-ID snapshot containing
`ROUTABLE_NOTIFICATION_CHANNELS` plus the canonical IDs of enabled registered
plugin adapters. Availability is evaluated separately. The core parses the
existing route configuration in user order and validates tokens against the
allowed-ID snapshot. An empty route configuration keeps all available channels.
A non-empty configuration keeps only configured, available IDs; unknown,
disabled, failed, and unloaded plugin IDs are reported as invalid, while an
enabled but unavailable adapter is valid but cannot become a target. A route
with no available matches remains empty rather than falling back to broadcast.
Target channel order remains the core's deterministic available-channel order.

Dispatch order remains: resolve available channels, apply route filtering,
reserve noise control, prepare optional image content once, invoke each adapter
under error isolation, aggregate attempts, then record or release noise state.
`NotificationRequest` is constructed only after those shared decisions. Its
metadata is bounded and sanitized and does not include credentials or raw
exceptions. The core also validates and sanitizes adapter error codes and
diagnostics before recording them. The plugin route adapter must generalize the
current fixed allowlist; it must not maintain a parallel route configuration.

Adapters do not send before route/noise decisions and do not claim success
without a real delivery attempt. User-influenced outbound endpoints remain
subject to the central outbound security policy when that policy is available.
No notification runtime wiring is part of this batch.

### Report Templates

Registration shape:

```python
@dataclass(frozen=True)
class ReportRenderRequest:
    platform: Literal["markdown", "wechat", "brief"]
    results: tuple[AnalysisResult, ...]
    report_date: str
    summary_only: bool
    report_language: str
    extra_context: Mapping[str, JSONValue]


class ReportTemplate(Protocol):
    template_id: str
    platforms: frozenset[str]

    def render(self, request: ReportRenderRequest) -> str | None: ...
```

The core normalizes the requested platform and selects only enabled plugin
templates whose `platforms` contain that exact value. Candidates run by numeric
registration priority and then registration order. The first non-empty string
wins; `None` or an empty string continues, and an exception is safely recorded
before continuing. Duplicate template IDs are rejected by the canonical
identity rule above.

If no plugin candidate renders, the core calls the existing Jinja renderer
under its current `REPORT_RENDERER_ENABLED` setting. If that renderer is
disabled, missing, empty, or failed, the caller's existing hard-coded report
fallback remains final. Plugin priority can order explicitly enabled plugin
candidates, but cannot unregister or erase either legacy fallback layer.

The real current path is `src/services/report_renderer.py` plus
`templates/report_markdown.j2`, `report_wechat.j2`, and `report_brief.j2`;
there is no `src/reports/` package. Existing `REPORT_TEMPLATES_DIR` remains the
supported Jinja file-template override until later plugin wiring is implemented.

### Event Hooks

Registration shape:

```python
@dataclass(frozen=True)
class PluginEvent:
    name: str
    schema_version: int
    occurred_at: datetime
    trace_id: str | None
    payload: Mapping[str, JSONValue]


EventHook = Callable[[PluginEvent], None]


@dataclass(frozen=True)
class EventHookRegistration:
    hook_id: str
    event_names: frozenset[str]
    callback: EventHook
```

The initial event names are:

| Event | Minimum sanitized payload |
| --- | --- |
| `analysis.started` | task/trace identity, stock code, trigger source |
| `analysis.completed` | task/trace identity, stock code, terminal status, optional result reference |
| `analysis.failed` | task/trace identity, stock code, terminal status, stable error code |
| `market_review.started` | task/trace identity, market region, trigger source |
| `market_review.completed` | task/trace identity, market region, terminal status, optional result reference |
| `market_review.failed` | task/trace identity, market region, terminal status, stable error code |

Hooks are synchronous, best-effort, process-local, and observational. Dispatch
uses registration priority/order, passes an immutable detached payload, catches
each callback failure, and continues. No retries or cross-process delivery are
promised. Payloads exclude credentials, raw exceptions, prompts, full reports,
and unrestricted tool results.

These Hooks do not replace `TaskEventStream`, Agent runtime events, SSE, or
pipeline diagnostics. Started events are emitted only after core admission;
terminal events observe the already-decided terminal state and cannot mutate or
veto it. Runtime wiring is deferred.

## Versioning

Three version axes remain independent:

1. Manifest `version` identifies a plugin release.
2. Manifest `apiVersion` identifies the overall plugin API major understood by
   that plugin.
3. Each registration `contract_version` identifies one extension-point major.

Version `"1"` permits additive optional fields, additional event names, and new
optional metadata with safe defaults. Removing or renaming fields, changing
types, changing callback ordering/failure semantics, or broadening mandatory
capabilities requires a new major. Released major values are never reused.

The manager rejects or skips a plugin/registration that requires an unsupported
major and records a safe diagnostic; it does not guess compatibility. During a
major transition, the core may support old and new adapters concurrently, but
must retain an explicit compatibility path and regression tests.

Serialized manifests, events, and metadata follow
[Serialized Artifact Versioning](database-migrations_EN.md#serialized-artifact-versioning):
that document remains the single source of truth for emitted version fields,
unknown-version degradation, historical payload handling, and bump procedure.
This contract does not define a second serialized-payload policy.

## Security And Trust

External plugins execute arbitrary Python in the StockPulse process. They have
the same OS user privileges and can access any file, environment value, network
route, imported module, or in-memory object available to that process. The
plugin manager provides availability isolation, not confidentiality or code
containment.

The `permissions` manifest field is schema and documentation only. It may help
reviewers understand intended access and may support a future enforcement
design, but the application does not grant, deny, intercept, or audit Python
capabilities from that list in this batch. An empty list does not mean a plugin
is safe.

Operators must review and trust external plugin code and dependencies. Keeping
`PLUGINS_DIR` unset or blank is the safe default and loads no external code.
There is no remote marketplace, automatic update, dependency installation,
signature verification, sandbox, subprocess boundary, or hot reload in scope.

## Deferred Surfaces

UI components, Settings panels, and Custom commands are later-phase extension
candidates. This batch defines no registration names, payloads, frontend bundle
format, command parser, permission behavior, or implementation plan for them.
They require a separate design that accounts for Web/Desktop compatibility,
authentication, localization, and frontend supply-chain risk.
