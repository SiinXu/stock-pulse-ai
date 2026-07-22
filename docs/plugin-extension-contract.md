# Plugin Extension Contract

Status: Proposed with [ADR-007](adr/ADR-007-versioned-plugin-extension-boundary.md)

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

The external loader scans only when `PLUGINS_DIR` is non-empty. It does not scan
a default home directory, follow a remote catalog, download packages, install
dependencies, or hot-reload files. Invalid manifests, incompatible application
or API versions, duplicate plugin IDs, missing entrypoints, and import failures
are recorded against that plugin and skipped without aborting the scan.

## Lifecycle

The signature-level lifecycle contract is:

```python
class Plugin:
    manifest: PluginManifest

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
        manifest: PluginManifest,
        *,
        source: PluginSource,
    ) -> PluginOperationResult: ...

    def load(self, plugin_id: str) -> PluginOperationResult: ...
    def enable(self, plugin_id: str) -> PluginOperationResult: ...
    def disable(self, plugin_id: str) -> PluginOperationResult: ...
```

`register` validates identity and records a plugin without invoking its
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
the only routing authority and must apply, in order, configuration/availability,
market capability filtering, static priority, health/circuit admission,
eligible adaptive ordering, provider call serialization, cache behavior,
fallback, and `RunDiagnosticContext` recording. Plugins cannot supply their own
fallback loop or bypass these policies.

The frozen behavior is documented in [ADR-005](adr/ADR-005-provider-fallback-and-circuit-control.md)
and [data source stability](data-source-stability.md). X3 must preserve existing
return values, error classification, empty-result behavior, health keys,
provider names in diagnostics, cache attribution, and market-specific routes.

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
class NotificationChannelAdapter(Protocol):
    channel_id: str

    def is_available(self) -> bool: ...

    def send(
        self,
        request: NotificationRequest,
    ) -> ChannelAttemptResult: ...


NotificationChannelFactory = Callable[[Config], NotificationChannelAdapter]
```

The factory receives the application configuration and returns one adapter.
The core selects available registered adapters, applies route and noise-control
policy, prepares text/image inputs, invokes each adapter under per-channel error
isolation, and aggregates `ChannelAttemptResult` into the existing
`NotificationDispatchResult` semantics. One adapter failure must not stop later
channels or the analysis workflow.

Adapters do not send before route/noise decisions and do not claim success
without a real delivery attempt. User-influenced outbound endpoints remain
subject to the central outbound security policy when that policy is available.
No notification runtime wiring is part of this batch.

### Report Templates

Registration shape:

```python
class ReportTemplate(Protocol):
    template_id: str

    def render(self, request: ReportRenderRequest) -> str | None: ...
```

`ReportRenderRequest` carries a report kind/platform, an immutable result list,
report date, language, summary flag, and bounded extra context. Returning
`None` means "not rendered" and preserves the current fallback path. Raising is
recorded and also falls back; one template failure must not prevent a report or
notification when the built-in renderer can continue.

The real current path is `src/services/report_renderer.py` plus
`templates/report_markdown.j2`, `report_wechat.j2`, and `report_brief.j2`;
there is no `src/reports/` package. Template IDs cannot silently replace
built-ins. Existing `REPORT_TEMPLATES_DIR` remains the supported file-template
override until later plugin wiring is implemented.

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
