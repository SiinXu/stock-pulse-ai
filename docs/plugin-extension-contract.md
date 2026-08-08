# Plugin Extension Contract

Status: Accepted with [ADR-007](adr/ADR-007-versioned-plugin-extension-boundary.md)

This document is the living contract for StockPulse plugins. It defines the
first supported extension boundaries and the signatures that implementation
work must converge on. Runnable code remains authoritative while a listed
integration is not yet wired.

## V1 Surface Freeze

**Surface version:** `PLUGIN_EXTENSION_SURFACE_VERSION = 1` in
[`src/plugins/surface.py`](../src/plugins/surface.py) (re-exported from
`src.plugins`).

Version 1 of the plugin extension surface is **frozen**. Contributors and
operators may treat the items below as the stable external contract. Anything
not listed here is an **internal** host detail and may change without a surface
major bump.

### Frozen extension points (exactly six)

| Point | Registration key | Author-facing types (package root) |
| --- | --- | --- |
| `data_provider` | `DataProviderRegistration.provider_id` | `Plugin` / `PluginContext` plus `data_provider.DataProvider` / `DataProviderRegistration` |
| `analysis_strategy` | strategy `name` | `AnalysisStrategyDefinition` |
| `agent_tool` | tool `name` | Tool definitions remain ToolSurface-owned; default process adapter is wired with fail-closed policy validation |
| `notification_channel` | `channel_id` | `NotificationChannelAdapter`, `NotificationChannelFactory`, `NotificationRequest`, `NotificationAdapterResult` |
| `report_template` | `template_id` | `ReportTemplate`, `ReportRenderRequest`, `ReportPlatform` |
| `event_hook` | `hook_id` | `EventHook`, `EventHookRegistration`, `PluginEvent`, `EVENT_HOOK_NAMES` |

The ordered identity is also exposed as `PLUGIN_EXTENSION_SURFACE_V1_POINT_ORDER`
and must stay identical to runtime `EXTENSION_POINTS`.

### Frozen author import surface

External plugins should import only from:

- the `src.plugins` package root names in `PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS`
- the `data_provider` package for provider registrations (`DataProvider`,
  `DataProviderRegistration`)

Lifecycle hooks remain `Plugin.onload` / `Plugin.onunload` with
`PluginContext.register(...)` using one of the six points above. Manifest fields
(`id`, `name`, `version`, `minAppVersion`, `description`, `author`,
`permissions`, `apiVersion`, `entrypoint`) stay as defined in
[Package And Manifest](#package-and-manifest).

### Explicitly internal (not part of surface v1)

The following are host-only and **must not** be treated as a stable plugin API:

- `PluginManager`, `ExternalPluginLoader`, composition roots, and native backends
- private modules under `src.plugins.*` beyond the package-root author exports
- any seventh extension point name (for example UI, Settings, marketplace,
  custom commands, connector/MCP)

Registering an unsupported extension point fails closed with
`PluginRegistryError("extension_point_unsupported")`. Using a closed
`PluginContext` after `onload` fails with
`PluginContextClosedError("plugin_context_closed")`.

### Freeze policy

- **No new extension points** without a new ADR (or an explicit ADR-007
  amendment) **and** a surface major bump.
- **No remote marketplace**, hot reload, dependency installer, or enforced
  permission sandbox in surface v1 (trusted in-process code only).
- Additive optional fields and event names may stay within major `1`; removals,
  renames, type changes, or semantic changes require a new contract major.

### Runnable reference packages

| Package | Point | Role |
| --- | --- | --- |
| [`examples/plugins/example-provider`](../examples/plugins/example-provider/) | `data_provider` | Network-free daily-data fixture; requires a manager-bound registry |
| [`examples/plugins/example-notification-channel`](../examples/plugins/example-notification-channel/) | `notification_channel` | Full lifecycle log-sink channel on the default process root |
| [`docs/examples/report-template-plugin`](examples/report-template-plugin/) | `report_template` | Minimal Markdown template illustration |

Point `PLUGINS_DIR` at the parent of the package directory (for example
`examples/plugins`), never at a single plugin folder. Each package README
includes the process-equivalent trust warning.

## Choosing An Extension Mechanism

Choose the smallest extension mechanism that matches the capability. A feature
request using the word "plugin" does not by itself make trusted Python code the
right boundary.

| Need | Choose | Current path | Boundary |
| --- | --- | --- | --- |
| Add investment criteria, prompt instructions, activation metadata, or declare existing tools required by a specialist without executing code | Skill / strategy package | Built-in content lives as YAML under `strategies/` (plus reserved `strategies/personas/`) and is published as first-class `analysis_strategy` plugins; custom definitions use top-level YAML or nested `SKILL.md` under `AGENT_SKILL_DIR` | Declarative input to the existing Skill runtime; `required_tools` narrows only an optional `SkillAgent` specialist, while imported `allowed_tools` is metadata rather than runtime access control |
| Add reviewed Python behavior for one of the six official extension points below | System plugin | `PLUGINS_DIR` provides package discovery and lifecycle only; an application composition path must also bind `PluginManager` to the exact point authority described by the implementation-status table | Trusted in-process code; the default process binds Analysis Strategies, Agent Tools, Report Templates, and the other implemented points listed below, while every unbound or contract-only point remains unavailable at runtime |
| Add UI components, Settings panels, custom commands, a remote marketplace, dependency installation, hot reload, a connector/MCP boundary, or another extension point | New design and ADR | Propose the authority, trust, compatibility, and lifecycle contract before implementation | Outside the version 1 plugin surface; do not route it through a nearby registration API |

Skill packages are appropriate when an author only needs natural-language
analysis behavior and optional required-tool metadata. `required_tools` narrows
the tool set only when the optional specialist path constructs a `SkillAgent`;
prompt-only and Single-Agent paths retain their normal runtime tool catalog.
Imported `allowed_tools` is metadata and does not enforce permissions.

System plugins are appropriate only when a trusted operator needs code-backed
behavior and an application composition path has bound the extension point's
exact native registry. `PLUGINS_DIR` alone discovers and manages package
lifecycle; it can activate only implementations whose point is bound by that
composition root. The default process root binds Agent Tools to its cached
`ToolRegistry`, Analysis Strategies to its root-owned declarative catalog
adapter, Notification Channels to its root-owned adapter registry, Report
Templates to the existing aggregate report render paths, and Event Hooks to the
stock-analysis and market-review lifecycle paths. Data Provider plugin execution
still requires programmatic composition with
`PluginManager(registry=manager.plugin_registry)`. A listed but unbound point
needs explicit wiring under the accepted contract, while a new surface requires
an ADR instead of an implicit registry expansion.

> **Operator trust boundary:** Setting `PLUGINS_DIR` opts into arbitrary Python
> code running with the StockPulse process's OS privileges. Keeping it unset or
> blank is the safe default. StockPulse does not download plugins, install their
> dependencies, sandbox them, or discover them from a remote marketplace.

## Implementation Status

| Surface | Current authority | Track X delivery |
| --- | --- | --- |
| Plugin lifecycle, manifest, registry | `src/plugins/` core; Data Provider, Analysis Strategy, Agent Tool, Notification Channel, Report Template, and Event Hook contracts are wired, while unconfigured points fail closed | #273 X2a core implemented; #538 Notification Channel, #541 Report Template, and #542 Event Hook validators implemented |
| Built-in/external startup wiring | `src/application_services.py` composition root | #273 X2b implemented |
| Data Providers | `DataProvider`, `BaseFetcher`, and `DataFetcherManager` | #276 X3 native adapter implemented; caller must inject the target manager registry |
| Analysis Strategies | `Skill`, `SkillManager`, `StrategyEngine` | Default process definition adapter wired; `SkillManager` and `StrategyEngine` remain authoritative |
| Agent Tools | `ToolDefinition`, `ToolRegistry`, Tool Surface | Default process adapter wired; strict registration validation remains fail-closed |
| Notification Channels | `NotificationChannel`, sender mixins, `NotificationService` | #538 runtime adapter implemented in the default process root |
| Report Templates | `src/services/report_renderer.py`, `templates/report_*.j2` | #541 runtime selection implemented; Jinja and hard-coded fallbacks retained |
| Event Hooks | `src/plugins/event_hooks.py` plus the stock-analysis and market-review lifecycle paths | Six observational lifecycle events wired; Task/Agent/SSE streams remain separate |

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

Consequently, setting `PLUGINS_DIR` on the default process root discovers and
loads plugin lifecycle objects but does not by itself activate a Data Provider
implementation. A composition caller must construct `PluginManager` with the
exact target `DataFetcherManager.plugin_registry`; no default process-wide
provider manager is fabricated for external plugins.

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

The default lifecycle-style built-in catalog is configuration-gated. Existing
Data Provider built-ins remain owned by each `DataFetcherManager`; the optional
Kronos Agent Tool is added only when its explicit enable flag is true. Analysis
Strategy and Notification Channel registration are available without built-in
lifecycle plugins. Other point statuses remain governed by the implementation
table above. `ApplicationServices`
continues to accept an explicit built-in iterable for tests and composition
callers. New built-ins must use that seam rather than a parallel startup hook.

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

Default extension-point contracts enforce canonical identity but reject an
implementation until composition supplies that point's concrete validator.
Identity alone is never treated as proof that an implementation satisfies its
full protocol. Wired bindings supply their validators and optional native
backends; an unconfigured point continues to reject registrations.

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

The tested [`example-provider` package](../examples/plugins/example-provider/)
and [Data Provider Plugin Authoring Guide](data-provider-plugin-authoring.md)
provide a complete manifest, implementation, load command, diagnostics, and
trust checklist.

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
    deferred: bool = False


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

The unified registry serializes registration under its registry-owned lock. A
contract with a pre-construction identity resolver first validates exact identity
equality. A factory contract whose runtime identity exists only on the returned
implementation may omit that resolver only when it supplies a native backend;
the registration ID is then canonical before construction, and that backend must
validate the returned identity before publication. A resolver-less contract
without a native backend is rejected. The registry checks both its own keyspace
and the target native registry before native delegation and ownership commit.
Existing permissive `SkillManager.register()` and
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
| `money_flow` | `get_money_flow` |
| `stock_name` / `stock_list` | `get_stock_name` / `get_stock_list` |
| `belong_boards` | `get_belong_board` |
| `main_indices` / `market_stats` | `get_main_indices` / `get_market_stats` |
| `sector_rankings` / `concept_rankings` | `get_sector_rankings` / `get_concept_rankings` |
| `hot_stocks` / `limit_up_pool` | `get_hot_stocks` / `get_limit_up_pool` |

`money_flow` is an additive contract v1 capability (Issue #862 / #619). Existing
providers that do not declare or implement it remain valid: registration still
requires only the capabilities listed on the registration object, and the
manager treats undeclared/unimplemented money-flow as a capability miss (returns
`None`) rather than a hard failure.

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

For the same contract in a directly loadable package, see the
[`example-provider` source](../examples/plugins/example-provider/plugin.py) and
the [authoring guide](data-provider-plugin-authoring.md). Its tests exercise the
repository copy through `PLUGINS_DIR`, including lifecycle cleanup and
per-candidate failure isolation.

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

`DataFetcherManager` does not impose a universal deadline around
`DataProvider.get_daily_data()` or `_call_fetcher_method()`. A provider that
performs network or SDK I/O must configure finite transport timeouts at its own
client or transport layer and raise a timeout failure from that single attempt.
The manager can then record the failure and continue the eligible provider
chain. This bounded-I/O responsibility does not let a plugin own a
cross-provider fallback loop, cache, route table, or dynamic priority override.

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
instructions, category, required-tool declarations, imported allowed-tool
metadata, activation metadata, market regimes, and execution hints. YAML and
`SKILL.md` remain supported input formats. `SkillManager` owns name lookup and
activation; `StrategyEngine` owns signal normalization, evidence partitioning,
aggregation, and synthesis.

`required_tools` narrows the tool names only when specialist mode constructs a
`SkillAgent`. Imported `allowed_tools` is retained as metadata and is not read
by the runtime access-policy path. Prompt-only and Single-Agent execution do not
gain a per-Skill tool allowlist, so a general tool-permission request cannot be
implemented by authoring Skill YAML or `SKILL.md` alone.

A plugin registers a definition. It does not replace `StrategyEngine`, write a
consensus result directly, or bypass required-tool and policy checks. The native
adapter validates and detaches the mutable `Skill`, pins plugin provenance, and
publishes it through the same generation-aware catalog used by Single-Agent
prompt assembly, Multi-Agent routing, and `SkillAgent` construction.

Built-in strategies are first-class plugins: each `strategies/` root YAML and
each reserved `strategies/personas/` YAML is registered as
`builtin.analysis-strategy.<name>` through the Analysis Strategy adapter at
startup. YAML remains the definition source; plugin lifecycle owns enable,
disable, and catalog publication. `SkillManager.load_builtin_skills()` is retained
only as a legacy YAML shim for offline tools and tests (it does not double-load
into the process reserved-name set). A configured `AGENT_SKILL_DIR` preserves
top-level YAML/YML plus nested `SKILL.md` discovery, and a custom definition may
still replace a built-in with the same name. A plugin may not replace a custom
definition or another plugin: initial collisions reject registration, while a
later custom-directory collision keeps the custom definition and excludes the
enabled plugin definition until the conflict is removed. Load, disable, enable,
custom-directory changes, and root replacement invalidate the next catalog clone
by root identity and generation. An in-flight clone remains stable.

The default `ApplicationServices` root owns the paired native adapter and unified
`PluginManager`. A caller supplying a custom manager must bind the exact
`AnalysisStrategyRegistry` backend consumed by that manager. The root derives
that backend or rejects an explicit mismatch instead of silently splitting
lifecycle and catalog authority. No-argument catalog and router calls resolve
the installed root's `config`. Explicit-config assembly passes its resolved
manager and config into Multi-Agent routing and specialist construction, so the
Single and Multi paths cannot silently switch catalogs.

A caller-built `AnalysisStrategyRegistry` also owns its reserved-name provider;
that callback must use the same root config. Catalog publication repeats the
collision check and excludes an ambiguous plugin definition fail closed, but a
divergent provider would delay the conflict from load diagnostics until runtime
assembly.

See the [Analysis Strategy Plugin Authoring Guide](analysis-strategy-plugin-authoring.md)
for definition fields, load commands, precedence, diagnostics, tests, and the
trust boundary.

### Agent Tools

Registration shape:

```python
AgentToolRegistration = ToolDefinition
```

The implementation must be a `ToolDefinition` with a stable, provider-portable
name of 1-64 ASCII letters, digits, underscores, or hyphens; a serializable
parameter schema; a callable handler; a category; and a declared `ToolPolicy`.
It must set `enforce_contract=True`, and its callable signature must exactly
match the declared schema: no positional-only, variadic, or hidden parameters;
optional defaults must match the handler, satisfy the declared
type/enum/pattern/bounds, and survive a lossless JSON round trip. Nested values
must use exact JSON scalar/container types, and object keys must be strings.
Defaults are materialized before validation and scope checks, and a stock-scoped
`stock_code` identity must be required. The plugin registry delegates to
`ToolRegistry`; every execution continues through the Tool Surface and its
capability, argument, stock-scope, recursively nested outbound-URL, timeout,
serialization, audit, and completion guards. Direct `ToolRegistry.execute`
dispatch is disabled, and neither core nor plugin tools can disable those
security contracts.

`ToolPolicy.permissions` is retained as the compatibility field for executable
capability declarations and is also published as `capabilities` in the public
descriptor. Every Agent Tool must declare one or more of the currently
supported capabilities: `analysis_context:read`, `backtest:read`,
`community_intel:read`, `intel:read`, `local_model:execute`,
`market_data:read`, `multimodal:read`, `news:read`, or `portfolio:read`. Unsupported, duplicate,
empty, or execution-ungranted declarations fail closed before the handler.
The `agent_tool` registration contract remains major version `1`: syntactically
valid v1 definitions can still register, while the existing ToolSurface policy
authority now denies unsafe capability declarations at execution. This is a
security-policy tightening under ADR-007's retained ToolSurface authority, not
a registration payload removal, rename, or type change.

Registration follows the existing Agent exposure model: the default single
Agent receives the process tool catalog, while multi-agent specialists receive
only their named subset. Registration cannot bypass those architecture rules,
weaken strict policy validation, publish a transport, or mutate Agent runner
internals. Single-Agent RUN resolves a frozen scope from its task/context before
dispatch, matching the Chat and specialist scope boundary. Tool names cannot
overwrite built-ins. `ApplicationServices`
supplies an exact-owner native adapter backed by the cached `ToolRegistry`;
unload removes only the definition registered by that plugin from the exact
registry instance selected during registration.

This completes the ToolSurface execution boundary in #191, not an OS or Python
process-containment sandbox. URL-bearing tool-call arguments use the shared
outbound policy, but external plugin handlers remain reviewed,
process-equivalent Python and can initiate raw network or other process access
internally. The top-level plugin manifest `permissions` list remains
descriptive; it is distinct from enforced `ToolPolicy.permissions`.

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

The factory receives the application configuration and returns one adapter. The
registration ID is the pre-construction canonical identity, so built-in and
duplicate collisions are rejected before executing the factory. The returned
adapter must expose the same `channel_id`; its bounded `display_name` is the
human-readable identity used by diagnostics. Plain functions and adapter classes
that accept one `Config` argument are both valid version-1 factories. Factories
and adapter methods may accept additional optional or variadic arguments, but
must accept the core call shape without requiring more arguments.
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

The default process wiring is implemented by
`src/plugins/notification_channels.py`, the root-owned registry exposed by
`ApplicationServices`, and the existing `NotificationService` dispatcher.
Factory validation and native/built-in canonical-ID collision checks happen
before publication. The registration ID must equal the returned adapter
`channel_id`; the adapter display name and callable signatures for construction,
`is_available()`, and `send(request)` are validated fail-closed. Runtime snapshots
intersect native registrations with a lock-free immutable snapshot of
lifecycle-stable `enabled` plugin owners. That owner snapshot is published only
after `onload()` commits and revoked before disable callbacks begin, so callback
workers can read it without waiting on the manager or unified-registry lifecycle
locks. Native adapters are paired to that immutable snapshot by both canonical
ID and an opaque token created for each native publication. A factory or
`onload()` worker therefore keeps unrelated stable channels dispatchable while
its own pending adapter remains invisible; the per-registration token also
prevents a stale owner from joining a replacement that reuses both the same
channel ID and the same callable factory or adapter class. An adapter registered
by an in-progress `onload()` is never dispatched if that load later fails. CLI
diagnostics report that pending native entry as unknown until the manager commit
makes it enabled. Disable and unload remove the exact owned adapter. A root-owned
read-side lease retains the complete resolved adapter tuple;
aggregate delivery derives both route readiness and its targets from that same
retained tuple instead of releasing an independent availability preflight.
concurrent destructive lifecycle work waits before `onunload()`, while a
same-thread lifecycle request is explicitly deferred until every already-entered
lease, including nested sends on that reader thread, exits. The writer reservation
blocks new snapshots until deferred lifecycle work finishes. The requesting send
may return first when another entered lease remains, so `deferred=True` is an
acceptance signal, not a completion signal. Each frozen target therefore completes
once and the next snapshot omits removed adapters. Availability exceptions and invalid values are
sanitized, logged, and excluded before dispatch, so they do not create channel
attempts. Invalid send results and send exceptions are isolated and mapped into
sanitized channel attempts. Aggregate delivery preserves the adapter error code,
retryability, and sanitized diagnostics; confirmed successes and non-retryable
attempts are fenced from duplicate physical sends. Factory construction and `NotificationService`
routing both resolve Config from the paired `ApplicationServices` authority.
Report-only `NotificationService` construction remains lazy and does not install
or start a default root; the first availability, route, or send operation binds
the delivery runtime and rejects a concurrently installed root with a different
Config identity. Adapters retain their enable-time Config; after a default-root
Config reload, disable plus re-enable rebuilds them from the new snapshot, while
an explicit root Config is unaffected by global singleton reset. The deterministic
[`example_log` adapter](../examples/plugins/example-notification-channel/README.md)
shows the complete external package shape without network access or secrets.

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
identity rule above. Contract version 1 accepts only the exact `markdown`,
`wechat`, and `brief` platform values. The request carries a tuple snapshot of
the current results and a detached, deeply immutable JSON-compatible
`extra_context` mapping. Candidate discovery includes only registrations owned
by lifecycle-stable enabled plugins. A disable or root shutdown that already
started is excluded before selection; a disable that starts after selection
does not cancel the in-flight render snapshot.

If no plugin candidate renders, the core calls the existing Jinja renderer
under its current `REPORT_RENDERER_ENABLED` setting. If that renderer is
disabled, missing, empty, or failed, the caller's existing hard-coded report
fallback remains final. Plugin priority can order explicitly enabled plugin
candidates, but cannot unregister or erase either legacy fallback layer.

The real current path is `src/services/report_renderer.py` plus
`templates/report_markdown.j2`, `report_wechat.j2`, and `report_brief.j2`;
there is no `src/reports/` package. Use `REPORT_TEMPLATES_DIR` for file-only
Jinja overrides. Use a `ReportTemplate` plugin only for trusted, reviewed Python
render logic; loading the plugin enables its candidates independently of
`REPORT_RENDERER_ENABLED`, which continues to gate only the Jinja fallback.
The loadable [report-template example](examples/report-template-plugin/README.md)
shows the minimal manifest, entrypoint, and registration call. As with every
external plugin, this code runs with the StockPulse process's OS privileges and
is not sandboxed.

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
veto it. The current emission boundaries are `process_single_stock` after its
resolve/admission stage and `run_market_review` after its task identity and
normalized region are fixed.

Version 1 projects only these fields:

- every event carries `task_id` plus the top-level `trace_id`;
- started events carry `stock_code` or `market_region` and `trigger_source`;
- terminal events carry the same subject plus `terminal_status`;
- completed events may carry `result_reference` (the stable task/query ID);
- failed events carry only a stable `error_code`, never exception text.

All string fields pass through the shared diagnostic sanitizer before the
payload is detached and deeply frozen. Candidate discovery reads only the
already-installed composition root and registrations owned by lifecycle-stable
enabled plugins; dispatch never installs a root. A disable or root shutdown
that already started is excluded before callback selection, while a lifecycle
transition that starts after selection does not cancel the in-flight snapshot.
Hook return values are ignored. Adding a new optional field or event name follows
the additive version-1 policy below; renaming/removing a field or changing
ordering, isolation, or mutability requires a new contract major.

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
signature verification, sandbox, or subprocess boundary in scope. Basic
in-process hot-reload for external packages is described in
[Lifecycle Controls](#lifecycle-controls-enable--disable--hot-reload);
it never fetches remote code or auto-enables new packages.

## Deferred Surfaces

UI components, Settings panels, and Custom commands are later-phase extension
candidates. This batch defines no registration names, payloads, frontend bundle
format, command parser, permission behavior, or implementation plan for them.
They require a separate design that accounts for Web/Desktop compatibility,
authentication, localization, and frontend supply-chain risk.

## Lifecycle Controls (Enable / Disable / Hot-Reload)

Version 1 of the extension **surface** remains frozen. Lifecycle **controls**
operate on the existing manager contract without adding author-facing export
names.

### Persisted enable / disable

- Operator intent is stored as a denylist of disabled plugin IDs in a JSON file
  resolved by `PLUGIN_STATE_PATH` (default:
  `<dir-of-DATABASE_PATH>/plugin_lifecycle_state.json`).
- Missing IDs default to **enabled**, matching historical `load_all` behavior for
  reviewed plugins already trusted via built-ins or `PLUGINS_DIR`.
- On `load` / `load_all`, a disabled plugin transitions to `disabled` **without**
  calling `onload`, so it never registers implementations for any extension
  point (`data_provider`, `analysis_strategy`, `agent_tool`,
  `notification_channel`, `report_template`, `event_hook`) and is never
  selected by `enabled_registrations*`.
- `enable` / `disable` update runtime state and the denylist. Process shutdown
  unload does **not** rewrite operator intent.
- Clear log lines record skip-load and disable outcomes.

### Basic hot-reload

- `PluginManager.reload(plugin_id)` re-imports **one** external package from its
  recorded package root, then re-registers and optionally reloads it.
- **Never** remote-fetches code, installs dependencies, or auto-enables a
  plugin that is persisted as disabled.
- **Never** scans `PLUGINS_DIR` for newly added sibling packages during reload
  (no auto-enable of new files).
- Built-in plugins always return `restart_required=true` because their code is
  part of the application package.
- If unload / cleanup cannot fully release registrations, the result is an
  honest `restart_required` rather than a silent partial swap.

### HTTP API (PLUG-02 contract)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/api/v1/plugins` | List registered plugins + lifecycle fields |
| `POST` | `/api/v1/plugins/{plugin_id}/lifecycle` | Body `{ "action": "enable" \| "disable" \| "reload" }` |

Auth follows neighbors: global admin-session middleware when
`ADMIN_AUTH_ENABLED=true`. Response models live in
`api/v1/schemas/plugins.py`.

### Security reasoning

Lifecycle controls do not weaken the trusted-plugin model:

1. Code still executes only from built-ins or an operator-configured local
   `PLUGINS_DIR` (no marketplace / remote fetch).
2. Persistence records only enable/disable intent for already-registered IDs.
3. Hot-reload re-imports an already-known package root; new directories are not
   discovered or auto-enabled by the reload path.

