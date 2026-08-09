# Plugin Development Guide

Status: Living entry point for trusted system plugins (surface v1).

This guide is the **consolidated starting point** for authors who need
code-backed extensions. It does not replace the frozen contract or the
per-hook authoring documents. Runnable code and
[`docs/plugin-extension-contract.md`](plugin-extension-contract.md) remain
authoritative when anything disagrees.

Chinese twin: [`plugin-development-guide_zh.md`](plugin-development-guide_zh.md).

## What And Why

StockPulse plugins let a **trusted operator** add reviewed Python behavior for
exactly six extension points without forking the application:

| Point | When to use it |
| --- | --- |
| `data_provider` | New market-data source behind `DataFetcherManager` routing |
| `analysis_strategy` | Declarative `Skill` definition published through the plugin lifecycle |
| `agent_tool` | ToolSurface-owned `ToolDefinition` registration (see security note) |
| `notification_channel` | Additional delivery adapter for the notification dispatcher |
| `report_template` | Code-backed Markdown / WeChat / brief report renderer |
| `event_hook` | Observational callbacks on analysis / market-review lifecycle events |

Prefer a **smaller** mechanism when it is enough:

- Natural-language strategies and tool *metadata* → YAML / `SKILL.md` under
  `AGENT_SKILL_DIR` (no trusted process code).
- Jinja-only report layout changes → `REPORT_TEMPLATES_DIR`.
- UI panels, Settings pages, remote marketplaces, dependency installers, or a
  seventh extension point → new ADR. They are **not** surface v1.

## Security Model (Read This First)

Setting `PLUGINS_DIR` opts the process into **arbitrary Python** with the same
OS privileges as StockPulse. There is:

- no remote marketplace or auto-download;
- no dependency installer for plugins;
- no enforced permission sandbox from manifest `permissions` (metadata only);
- no hot reload (change requires process restart).

Review every line before enabling a package. Keep `PLUGINS_DIR` unset in
production unless the packages are reviewed and pinned. The operator trust
boundary is also summarized in the
[security baseline](security-baseline.md#operator-security-boundaries) and
[ADR-007](adr/ADR-007-versioned-plugin-extension-boundary.md).

### Agent tool caveat (#539)

The `agent_tool` registration path validates `ToolDefinition` objects and can
place them on the process `ToolRegistry`. Live agent invocation still depends
on ToolSurface sandbox hardening tracked by issue **#539**. Until that gate is
met, treat external agent-tool plugins as **load-and-register only**: contract
tests may assert registration and direct handler calls, but must not claim a
hardened live-agent execution path. The
[`example-agent-tool`](../examples/plugins/example-agent-tool/) package
documents this boundary explicitly.

## Quickstart (Under 10 Minutes)

From a clone of this repository with a working Python environment:

```bash
# 1) Point PLUGINS_DIR at the parent of plugin packages (never a single package)
export PLUGINS_DIR="$PWD/examples/plugins"

# 2) Smoke-load the official notification reference through the composition root
python - <<'PY'
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.config import Config

reset_application_services()
services = ApplicationServices(
    config=Config(stock_list=[]),
    plugins_dir="examples/plugins",
)
set_application_services(services)
loads = {r.plugin_id: r for r in services.plugin_load_results}
print("loaded", sorted(k for k, v in loads.items() if v.success))
assert loads["example-notification-channel"].success
print("channels", sorted(
    e.channel_id for e in services.notification_channel_registry.snapshot()
))
services.close()
reset_application_services()
PY
```

Expected: every well-formed package under `examples/plugins/` appears in the
load snapshot; `example_log` is present on the notification channel registry.

Optional live notification exercise (writes only route metadata to logs):

```bash
export PLUGINS_DIR="$PWD/examples/plugins"
export NOTIFICATION_REPORT_CHANNELS="example_log"
python main.py --stocks 600519 --dry-run
```

### Minimal package layout

```text
my-plugins/                 # value of PLUGINS_DIR
  my-channel/
    manifest.json
    plugin.py               # defines class Plugin(src.plugins.Plugin)
    README.md               # operator-facing trust notes
```

`manifest.json` fields, version rules, and entrypoint containment are defined
in the [package and manifest](plugin-extension-contract.md#package-and-manifest)
section of the contract. Copy any official example and change the stable IDs.

## Frozen Author Import Surface

External plugins should import only:

1. Names re-exported from `src.plugins` listed in
   `PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS`
2. `data_provider.DataProvider` / `DataProviderRegistration` for providers
3. Host-owned types required by a specific point when not on the plugin root:
   - `Skill` from `src.agent.skills.base` for `analysis_strategy`
   - `ToolDefinition` / `ToolParameter` / `ToolPolicy` from
     `src.agent.tools.registry` for `agent_tool` (ToolSurface-owned)

Do not import `PluginManager`, `ExternalPluginLoader`, private
`src.plugins.*` modules, or invent a seventh extension point name.

Lifecycle is always:

```python
class Plugin(BasePlugin):
    def onload(self, context: PluginContext) -> None:
        context.register("<point>", "<canonical-id>", implementation, contract_version="1")

    def onunload(self) -> None:
        """Release plugin-owned resources only; registration cleanup is manager-owned."""
```

## Official Examples

Point `PLUGINS_DIR` at `examples/plugins` (the parent directory).

| Package | Point | What the tests prove |
| --- | --- | --- |
| [`example-provider`](../examples/plugins/example-provider/) | `data_provider` | Loads, routes daily data, disables cleanly (manager-bound registry) |
| [`example-analysis-strategy`](../examples/plugins/example-analysis-strategy/) | `analysis_strategy` | Loads and publishes a detached `Skill` into the process catalog |
| [`example-agent-tool`](../examples/plugins/example-agent-tool/) | `agent_tool` | Loads and registers on `ToolRegistry`; handler callable in tests only |
| [`example-notification-channel`](../examples/plugins/example-notification-channel/) | `notification_channel` | Full dispatch lifecycle on the default process root |
| [`example-report-template`](../examples/plugins/example-report-template/) | `report_template` | Loads and renders Markdown through the frozen render path |
| [`example-event-hook`](../examples/plugins/example-event-hook/) | `event_hook` | Loads and receives observational analysis lifecycle events |

A smaller Markdown illustration also remains under
[`docs/examples/report-template-plugin/`](examples/report-template-plugin/) for
inline documentation; prefer the `examples/plugins/` package for new work.

## Per-Hook Deep Links

| Topic | Document |
| --- | --- |
| Frozen surface, lifecycle, all six points | [Plugin extension contract](plugin-extension-contract.md) |
| Architecture decision | [ADR-007](adr/ADR-007-versioned-plugin-extension-boundary.md) |
| Data provider authoring | [Data Provider Plugin Authoring Guide](data-provider-plugin-authoring.md) |
| Analysis strategy authoring | [Analysis Strategy Plugin Authoring Guide](analysis-strategy-plugin-authoring.md) |
| Operator security boundaries | [Security baseline](security-baseline.md#operator-security-boundaries) |
| Surface freeze + reference notification tests | `tests/plugins/test_extension_surface_v1.py` |


## Operator / Operations View

This section is for deployers and on-call operators, not plugin authors.

### Lifecycle audit trail

Lifecycle transitions record security-audit events (`event_type=plugin.lifecycle`)
via the existing security-audit store. Automatic startup loading is best-effort,
so an unavailable recorder does not block unrelated plugins. Administrator
enable/disable/reload requests are fail-closed before mutation when the attempt
event cannot be stored. If the completion write fails after the operation, the
API returns `503 security_audit_unavailable` and reports the real completed
state; it does not claim rollback.

### Data Provider auto-bind (opt-in)

| Setting | Default | Effect |
| --- | --- | --- |
| `PLUGIN_DATA_PROVIDER_AUTO_BIND` | off | When enabled, the default `ApplicationServices` composition root binds `PluginManager` to a process `DataFetcherManager.plugin_registry` (created or injected) so registered providers route without extra glue |

Leave the flag unset to keep historical manual mode. When enabled without an
injected manager, `ApplicationServices` constructs one `DataFetcherManager` and
exposes it as `services.data_fetcher_manager`. Stock quote/history service calls
resolve this installed owner, so plugin providers and built-in fallback use the
same registry. Custom roots may still call `try_build_auto_bound_registry`
directly.

```python
from data_provider import DataFetcherManager
from src.plugins import (
    PLUGIN_APPLICATION_VERSION,
    PluginManager,
    try_build_auto_bound_registry,
)

providers = DataFetcherManager()
registry, error = try_build_auto_bound_registry(providers)
if error:
    raise RuntimeError(error)
plugins = PluginManager(
    application_version=PLUGIN_APPLICATION_VERSION,
    registry=registry or providers.plugin_registry,  # explicit when flag off
)
```

### Health check

```python
report = plugin_manager.health_check()
for entry in report.plugins:
    print(entry.plugin_id, entry.state, entry.last_error_code, entry.extension_points)
```

Use `last_error_code` for the most recent stable failure (for example
`plugin_onload_failed`). Disable/intent changes preserve it; a successful
load/reload clears it as recovered. A single failed plugin must not prevent
other plugins or core startup.

## Verification Commands

Offline plugin suite (preferred local gate for this topic):

```bash
python -m pytest tests/plugins -m "not network and not benchmark" -q
```

After editing only examples or their contract tests, you can narrow to:

```bash
python -m pytest tests/plugins/test_example_*.py tests/plugins/test_extension_surface_v1.py -q
```

## What This Guide Does Not Cover

- Marketplace distribution, signature verification, or multi-tenant isolation
- Enforced sandboxing of plugin code (process-equivalent trust only)
- Migrating built-in tools into plugins without ToolSurface preservation (#432 / #539)
- UI, Settings, or MCP connector extension points

Those remain separate design tracks. Do not stretch a nearby registration API
to simulate them.
