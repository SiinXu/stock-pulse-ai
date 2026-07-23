# Plugin Extension Contract

Status: Accepted with [ADR-007](adr/ADR-007-versioned-plugin-extension-boundary.md)

This document is the living contract for StockPulse plugins. It defines the
first supported extension boundaries and the signatures that implementation
work must converge on. Runnable code remains authoritative while a listed
integration is not yet wired.

## Implementation Status

| Surface | Current authority | Track X delivery |
| --- | --- | --- |
| Plugin lifecycle, manifest, registry | `src/plugins/` core; Data Provider native adapter wired, other points fail closed | #273 X2a core implemented |
| Built-in/external startup wiring | `src/application_services.py` composition root | #273 X2b implemented |
| Data Providers | `DataProvider`, `BaseFetcher`, and `DataFetcherManager` | #276 X3 implemented |
| Analysis Strategies | `Skill`, `SkillManager`, `StrategyEngine` | Contract only in this batch |
| Agent Tools | `ToolDefinition`, `ToolRegistry`, Tool Surface | Contract only; `src/agent/**` stays untouched |
| Notification Channels | `NotificationChannel`, sender mixins, `NotificationService` | Contract only in this batch |
| Report Templates | `src/services/report_renderer.py`, `templates/report_*.j2` | Contract only in this batch |
| Event Hooks | Task and Agent runtime event streams | Contract only in this batch |

"Contract only" means a plugin cannot yet rely on runtime wiring for that
extension point. It does not mean the existing core path is deprecated.

The X2a core validates manifests, owns lifecycle transitions and registrations,
and exposes an explicit external-directory loader. X2b wires that core into
`ApplicationServices`: after a root is installed and therefore discoverable,
the root registers its explicitly supplied built-in plugin catalog, scans an
external directory only when `PLUGINS_DIR` is non-empty, and loads the resulting
manager snapshot. Root replacement and process exit disable the snapshot in
reverse registration order. Registration, discovery, load, and unload results
remain available on the root for diagnostics and deterministic tests.

X3 exposes its configured unified registry as
`DataFetcherManager.plugin_registry`. Programmatic composition may pass that
exact registry to `PluginManager`; the provider manager and plugin manager must
not be given separate registries. The default process plugin manager does not
invent a process-wide `DataFetcherManager`, because current provider consumers
own distinct managers. A composition caller that activates Data Provider
plugins must inject a `PluginManager` bound to the exact target manager registry.
X2b does not silently redirect or replace those existing provider-manager
ownership boundaries.

## Startup Composition

`main.py` and `server.py` already install an `ApplicationServices` root after
environment setup. Installing the root now starts plugin composition without an
entrypoint edit:

1. register caller-supplied built-in `Plugin` objects with `source="builtin"`;
2. when and only when `PLUGINS_DIR` is non-empty, scan its direct child
   directories in deterministic name order and register valid external plugins;
3. load the complete registration snapshot in registration order, continuing
   after every isolated plugin failure; and
4. disable that snapshot in reverse order when the root is replaced, reset, or
   closed at process exit.

Composition-root transitions are serialized around that shutdown boundary. The
previous root remains the discoverable root until its complete reverse-order
unload finishes; only then is a successor published and started. A lifecycle
callback that resolves `get_application_services()` during the transition sees
the root that owns the callback, so reset and process-exit cleanup cannot
implicitly create a fresh root. Re-entrant or concurrent replacement requests
made during a lifecycle callback are queued without waiting for that callback;
the most recent installable explicit request becomes the next root after the
active transition finishes. A root is one-shot once shutdown begins: requests
for that closing root are skipped in favor of the next-latest installable target,
and a closed root cannot be installed again or remain the stable global root. A
retain-current request remains valid during load, before shutdown starts. If a
root closes itself during startup, the next stable lookup creates a fresh root.
Normal reset remains reusable, but the process-exit handler first enters a
terminal shutdown state: unload callbacks can still resolve their owning root,
while later atexit callbacks cannot lazily create or install another root.
Calling `close()` directly on the installed process root uses this same
serialized boundary; it cannot expose or start a callback-requested successor
until the complete reverse-order unload has finished. If a lifecycle callback
or its worker requests that close while a transition is already active, the
request is queued without waiting; the returned tuple is the current immutable
shutdown-result snapshot, and the transition owner completes the shutdown after
the callback returns. This non-blocking overlap rule prevents callback-worker
joins from deadlocking the root-local lifecycle lock.

The same boundary wraps public lifecycle operations invoked through the
installed root's `PluginManager` (`load`, `load_all`, `enable`, `disable`, and
`disable_all`). A root replacement requested by one of those callbacks is
deferred until the complete manager operation returns; the old root then
finishes reverse-order shutdown before any successor starts. A root that is
not installed runs manager lifecycle operations and its own close outside the
transition authority, so its callback-owned workers may keep using the module
accessors. A direct installer rejects a target whose local startup or manager
lifecycle operation is already in flight, so a callback or its worker cannot
wait on itself. If a local operation races after the installer owns the global
transition, that transition drains the complete operation before starting the
target, so an operation never straddles installation. A target accepted into
the pending queue retains that transition authority during handoff and drains
any existing local lifecycle operation instead of re-entering direct-install
validation. When no previous root exists, the authorized transition target is
lookup-visible before publication so its callback workers never wait on their
own installer. The drain covers pre-manager startup and its final close cleanup;
only after the current target drains does the transition consume the latest
pending request. A superseded target finishes complete cleanup before any
successor starts; selecting the latest request retains cleanup debt for every
older or already-closing queued root instead of discarding it. If a published
target requests shutdown during that drain, it remains discoverable through its
complete unload and continues to anchor lookups while superseded cleanup debt
runs, including cleanup queued by those callbacks. It is unpublished only after
the transition reaches that cleanup fixed point.
Each `PluginManager` is owned by exactly one `ApplicationServices` root and
cannot be rebound to another root. Once that root starts shutdown, manager
`load`, `load_all`, and `enable` operations fail closed with
`plugin_owner_closed`; `disable` and `disable_all` remain available for
idempotent cleanup and cleanup-debt retries. The close request is terminal as
soon as it is made: queued activation is rejected, and a callback cannot
supersede its own close by requesting the same root again. A direct installer
also rejects that root. If an already-authorized transition races with the
shutdown request, it drains cleanup and clears the target without making it
stable.
Closing a local root also disables plugins activated directly through its
manager, even when composition startup was never invoked. A close requested by
a local startup or manager callback, or by its worker, is deferred until that
outer operation finishes; the root then performs the same state-based cleanup
exactly once. The installer drain remains active through that deferred cleanup,
including every `onunload()` callback, before a successor may start.

There is currently no default lifecycle-style built-in catalog to fabricate:
existing Data Provider built-ins remain owned by each `DataFetcherManager`, and
the other five extension points are contract-only. `ApplicationServices`
therefore accepts an explicit built-in iterable while its default is empty.
Adding a real built-in later must use that seam rather than a parallel startup
hook.

`PLUGINS_DIR` is read once for each root startup. Unset, empty, or whitespace-only
values do not instantiate the external loader and do not probe a default path.
Changing the value requires a process restart; there is no hot reload. Relative
paths use the process working directory, so production deployments should use a
reviewed absolute path. Missing, unreadable, invalid, incompatible, or failing
candidates produce isolated result codes and never abort later candidates or
the core application. Because this setting authorizes arbitrary startup code, it
is read only from the process environment or startup `ENV_FILE`; it is not a
runtime-mutable Web setting.

Manifest `minAppVersion` is checked against the current released StockPulse
compatibility line (`3.26.3` for this delivery). That value is maintained with
the release line; it is not an operator override that can bypass compatibility.

Default extension-point contracts enforce canonical identity but reject every
implementation until composition supplies that point's concrete validator.
Identity alone is never treated as proof that an implementation satisfies its
full protocol. The native adapters delivered by X2b, X3, or a later integration
must inject the validator and optional native backend before registrations for
that point can succeed.

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
core startup or another plugin's lifecycle. Disabling a failed plugin retries any
remaining registration cleanup; once no owned handles remain, it converges to
`disabled` without invoking `onunload`, so a later enable may retry `onload`.

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
the plugin. If native rollback itself fails, the registry retains a quarantined
owner reservation and recovery handle, excludes that implementation from active
unified snapshots, and lets manager cleanup retry the exact native removal. The
same plugin cannot be marked enabled merely because it catches that registration
error. Unregistration removes only the exact implementation owned by that handle,
so a stale handle cannot remove a built-in or another plugin's entry.

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

Contract version 1 accepts the markets `cn`, `hk`, `us`, `jp`, `kr`, and `tw`.
It accepts these capabilities, each of which requires the corresponding callable
on the factory result:

| Capability | Required method |
| --- | --- |
| `daily_data` | `get_daily_data` |
| `realtime_quote` | `get_realtime_quote` |
| `chip_distribution` | `get_chip_distribution` |
| `stock_name` / `stock_list` | `get_stock_name` / `get_stock_list` |
| `belong_boards` | `get_belong_board` |
| `main_indices` / `market_stats` | `get_main_indices` / `get_market_stats` |
| `sector_rankings` / `concept_rankings` | `get_sector_rankings` / `get_concept_rankings` |
| `hot_stocks` / `limit_up_pool` | `get_hot_stocks` / `get_limit_up_pool` |

Existing `prefetch_*` paths remain built-in manager optimizations and are not
plugin capabilities in contract version 1.

The factory runs during the X2 registration transaction. It must return a
`DataProvider` with a non-empty runtime `name`; IDs and runtime names cannot
collide with built-ins or another active plugin. A factory or validation failure
fails that plugin load without modifying the manager route. Disabling the plugin
removes only its exact provider instance, and the manager applies the new
registration snapshot before its next route selection. Existing fresh/stale
cache entries and process-local health observations keep their normal TTL/reset
semantics; disabling a provider does not rewrite cached market data.
The manager pins the validated factory-time runtime name for routing, health,
cache attribution, and diagnostics. Later mutation of the provider object's
`name` cannot rename the active registration or impersonate a fixed built-in
route.
Once routing selects an eligible provider adapter snapshot, that attempt calls
the exact selected adapter. A concurrent disable, enable, or same-name
replacement affects the next route selection; it cannot rebind the current
attempt to a provider with different market eligibility. The adapter also pins
the immutable declared markets, capabilities, and registration priority, so
removing live registry state cannot broaden or reorder the in-flight snapshot.

Built-ins use stable IDs `efinance`, `tencent`, `akshare`, `tushare`, `tickflow`,
`pytdx`, `baostock`, `yfinance`, `longbridge`, `finnhub`, and `alphavantage`.
Their existing runtime names, optional credential gates, constructor order, and
instance-derived priorities remain unchanged. The legacy `fetchers=` constructor
and `add_fetcher()` remain compatibility inputs, but plugins must use the unified
registry so lifecycle ownership can be enforced.

Minimal programmatic registration:

```python
manager = DataFetcherManager()
plugins = PluginManager(
    application_version=application_version,
    registry=manager.plugin_registry,
)

class ExampleProviderPlugin(Plugin):
    def onload(self, context: PluginContext) -> None:
        registration = DataProviderRegistration(
            provider_id="example-market-data",
            factory=ExampleDataProvider,
            markets=frozenset({"cn", "hk"}),
            capabilities=frozenset({"daily_data"}),
        )
        context.register(
            "data_provider",
            registration.provider_id,
            registration,
            priority=20,
        )
```

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

Lower plugin priority values run earlier only inside routes governed by numeric
priority. Existing named routes remain hard anchors: U.S. index, U.S. stock, and
Longbridge-preferred built-in chains execute in their historical order, and an
eligible plugin is appended as fallback. Realtime market-specific and configured
built-in routes follow the same rule. This prevents a plugin priority from
silently rewriting an operator's fixed route while still providing dynamic
fallback.

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
Setting it is a startup-time trust decision and requires a process restart.
There is no remote marketplace, automatic update, dependency installation,
signature verification, sandbox, subprocess boundary, or hot reload in scope.

## Deferred Surfaces

UI components, Settings panels, and Custom commands are later-phase extension
candidates. This batch defines no registration names, payloads, frontend bundle
format, command parser, permission behavior, or implementation plan for them.
They require a separate design that accounts for Web/Desktop compatibility,
authentication, localization, and frontend supply-chain risk.
