# External Framework Adapter Guide

Status: Authoring guide for thin adapters that absorb external frameworks
through the frozen StockPulse plugin surface (v1).

Chinese twin: [`external-framework-adapter-guide_zh.md`](external-framework-adapter-guide_zh.md).

Related documents (authoritative when anything disagrees with this guide):

- [Plugin extension contract](plugin-extension-contract.md) / [ADR-007](adr/ADR-007-versioned-plugin-extension-boundary.md)
- [Data Provider plugin authoring](data-provider-plugin-authoring.md)
- [Analysis Strategy plugin authoring](analysis-strategy-plugin-authoring.md)
- [Plugin development guide](plugin-development-guide.md)
- [External capability absorption proposal](plans/external-capability-absorption-proposal.md)

Runnable demonstration (OpenBB → `data_provider`):
[`docs/examples/external-framework-data-provider/`](examples/external-framework-data-provider/).

## Purpose

StockPulse does **not** embed full external frameworks (OpenBB, Qlib, FinRL, …)
inside the core process. The supported absorption path is a **thin adapter
plugin** that:

1. maps the external capability onto **exactly one** of the six frozen extension
   points;
2. installs **no** heavy dependencies for CI or default deployments;
3. leaves routing, fallback, caching, and circuit control with the existing
   host authority for that point.

This guide is the operational twin of the absorption proposal (phase 2).

## Non-negotiable rules

| Rule | Detail |
| --- | --- |
| No new extension points | Only `data_provider`, `analysis_strategy`, `agent_tool`, `notification_channel`, `report_template`, `event_hook`. A seventh point requires a new ADR and a surface major bump. |
| Thin adapter only | Wiring + field normalization + bounded I/O. Do not re-implement `DataFetcherManager`, StrategyEngine, ToolSurface, or report pipelines inside the plugin. |
| Manual dependency install | Operators install and pin external packages themselves. StockPulse never runs `pip install` for plugins. |
| Default off | Demonstration and third-party adapters stay out of the default load set. Enabling requires an explicit, reviewed `PLUGINS_DIR`. |
| Fail loudly, fall back host-side | Missing dependency, timeout, or empty upstream data must **raise** (or return a typed failure the host already understands). Never `return None` / `[]` / empty success frames to pretend the source worked. |
| Trust = full process privileges | External adapter plugins are **trusted in-process code with no sandbox**. Manifest `permissions` are descriptive metadata only. |

## Decision tree: which extension point?

```text
What does the external framework primarily provide?
│
├─ Market / fundamental time-series consumed like other fetchers
│    → data_provider
│      Examples: OpenBB equity historical bars, alternative quote vendors
│
├─ Natural-language investment criteria / persona prompts only
│    → Prefer YAML Skill under AGENT_SKILL_DIR (no plugin)
│    → analysis_strategy plugin only when load-time Python is required
│
├─ On-demand callable that agents should invoke with typed args
│    → agent_tool  (note: live agent execution hardening is issue #539)
│      Examples: Qlib factor query, FinRL policy signal service client
│
├─ Additional notification delivery backend
│    → notification_channel
│
├─ Code-backed report rendering for markdown / wechat / brief
│    → report_template
│      (Jinja-only layout → REPORT_TEMPLATES_DIR instead)
│
└─ Side-effect observer on analysis / market-review lifecycle
     → event_hook  (must never abort the main pipeline)
```

If the capability needs UI panels, Settings pages, a marketplace, dependency
auto-install, or hot reload, **stop**. Those are outside surface v1; open an ADR
instead of stretching a nearby registration API.

### Why this demonstration chose OpenBB → `data_provider`

| Criterion | OpenBB data path | Qlib factor path |
| --- | --- | --- |
| Closest frozen point | `data_provider` (daily bars) | Usually `agent_tool` (factor query) |
| Contract isomorphism | Same OHLCV normalization + manager fallback as built-in fetchers | Requires tool args/result schema + #539 caveats |
| Operator install surface | Optional `openbb` package | Heavier quant stack / often better as a side service |
| Demo value for phase 2 | Highest for “external data in, host routes” | Better as a follow-on tool adapter |

Ship OpenBB first; reuse the same thin-adapter discipline for Qlib/FinRL later.

## Package layout

Mirror the repository copyable-plugin convention
([`docs/examples/report-template-plugin/`](examples/report-template-plugin/),
[`examples/plugins/example-provider/`](../examples/plugins/example-provider/)):

```text
<PLUGINS_DIR>/
  openbb-data-provider/          # direct child only; loader does not recurse
    manifest.json
    plugin.py
    README.md
```

`PLUGINS_DIR` points at the **parent**. Unset / blank / whitespace → no external
discovery (safe default).

### Manifest checklist

| Field | Requirement |
| --- | --- |
| `id` | Stable `[a-z0-9][a-z0-9._-]*`, unique vs built-ins and other plugins |
| `version` | Exact `MAJOR.MINOR.PATCH` |
| `minAppVersion` | Earliest StockPulse version you actually tested |
| `apiVersion` | `"1"` for surface v1 |
| `entrypoint` | Relative `file.py:Class` inside the package |
| `permissions` | Descriptive only — list dependency and outbound expectations for operators |

### Registration sketch (`data_provider`)

```python
from data_provider import DataProvider, DataProviderRegistration
from src.plugins import Plugin as BasePlugin

class Plugin(BasePlugin):
    def onload(self, context):
        registration = DataProviderRegistration(
            provider_id="openbb-daily-data",
            factory=MyProvider,  # callable → DataProvider instance
            markets=frozenset({"us", "hk", "cn"}),
            capabilities=frozenset({"daily_data"}),
        )
        context.register(
            "data_provider",
            registration.provider_id,
            registration,
            contract_version="1",
            priority=95,
        )
```

Data Provider activation still needs a `PluginManager` bound to the exact
`DataFetcherManager.plugin_registry`. See the
[Data Provider authoring guide](data-provider-plugin-authoring.md).

## Field normalization requirements

Daily-data adapters must return a `pandas.DataFrame` with at least:

| Column | Notes |
| --- | --- |
| `date` | `YYYY-MM-DD` strings preferred |
| `open` / `high` / `low` / `close` | Numeric |
| `volume` | Integer-compatible |
| `amount` | Numeric; derive conservatively if upstream omits it |
| `pct_chg` | Percent change; compute from `close` if omitted |

Do not invent success from incomplete rows: drop unusable rows, and if nothing
remains, **raise** so the manager can fall back.

## Failure, timeout, and degradation

| Situation | Required behavior |
| --- | --- |
| External package not installed | Raise a clear error naming the package and that StockPulse will not auto-install it |
| Transport / SDK timeout | Enforce a finite client or adapter wall-clock deadline and raise from this attempt |
| Empty or malformed upstream payload | Raise; do not return an empty “success” frame unless the capability explicitly allows empty data **and** the host contract documents that |
| Partial multi-symbol batch failure | Fail the current attempt or return only validated rows per the host contract — never silent zeros for missing symbols |
| Cross-provider fallback | **Forbidden inside the plugin**. One attempt; `DataFetcherManager` owns the chain |

The host does **not** impose a universal deadline around every provider call.
Finite connect/read (or SDK) timeouts are the adapter author's responsibility.
The OpenBB example enforces its SDK deadline in the adapter and raises a typed
provider timeout so the host fallback chain can continue.

## Dependency declaration and manual install

1. Document required packages and minimum versions in the plugin `README.md`.
2. Prefer optional / lazy imports at **call time** (or factory time) so the
   plugin package can be reviewed without forcing the heavy dependency into
   developer laptops that never enable it.
3. Operators install into the **same** environment that runs StockPulse:

   ```bash
   pip install 'openbb>=4'   # example only — pin to your reviewed version
   export PLUGINS_DIR=/opt/stockpulse/plugins
   ```

4. CI for StockPulse must remain green **without** those packages. Offline
   tests inject fakes/fixtures (`pytest -m "not network"`).

## Trust responsibility statement

> **External adapter plugins run with full process privileges.**
> Setting `PLUGINS_DIR` is an explicit operator decision to load reviewed Python
> that can read process memory, environment values, local files, and network
> routes available to the StockPulse OS user. There is no plugin sandbox,
> signature store, marketplace, or automatic update channel in surface v1.
> You are responsible for code review, dependency review, pinning, and for
> keeping `PLUGINS_DIR` unset when no trusted external code is required.

## Operator walkthrough (copy these steps)

These steps match the OpenBB demonstration package.

```bash
# From a clone with project dependencies already installed for StockPulse itself.

# 1) Review the demonstration package
less docs/examples/external-framework-data-provider/plugin.py
less docs/examples/external-framework-data-provider/manifest.json

# 2) Install the external framework manually (skip for offline fixture tests)
pip install 'openbb>=4'

# 3) Opt in: PLUGINS_DIR = parent of the package directory
export PLUGINS_DIR="$PWD/docs/examples"

# 4) Offline contract tests (no network, no real OpenBB required)
python -m pytest -q tests/plugins/test_external_framework_openbb_provider.py

# 5) Composition smoke (requires OpenBB only if you call get_daily_data without a fake)
python - <<'PY'
from data_provider import DataFetcherManager
from src.application_services import ApplicationServices
from src.plugins import PLUGIN_APPLICATION_VERSION, PluginManager

providers = DataFetcherManager()
plugins = PluginManager(
    application_version=PLUGIN_APPLICATION_VERSION,
    registry=providers.plugin_registry,
)
services = ApplicationServices(plugin_manager=plugins)
try:
    services.start_plugins()
    print("discovery", services.external_plugin_results)
    print(
        "providers",
        [
            item.registration_id
            for item in plugins.registrations("data_provider")
            if item.plugin_id == "stockpulse.openbb-data-provider"
        ],
    )
finally:
    services.close()
PY
```

Keep `PLUGINS_DIR` unset in production until the package and its dependency
tree are reviewed.

## Testing expectations

| Layer | Expectation |
| --- | --- |
| Unit / contract | Fixture client; assert column contract, missing-dependency error text, empty-upstream raise, register/load/disable |
| Network | Optional, marked `@pytest.mark.network`; never required for `ci_gate` |
| Core mechanisms | Do **not** patch `src/plugins` loader/manager/registry to “make the demo work” — if the host contract is insufficient, that is a separate ADR task |

## V1 surface declaration

This guide and the OpenBB demonstration:

- add **zero** new extension points;
- do not change `registry.py` / `manager.py` / `loader.py` / `manifest.py`;
- do not modify `data_provider/` host implementations;
- rely only on the public author import surface (`src.plugins` package root +
  `data_provider.DataProvider` / `DataProviderRegistration`).

## Follow-ons

| Candidate | Suggested point | Note |
| --- | --- | --- |
| Qlib factors | `agent_tool` | Prefer side-process inference; thin query tool |
| FinRL policy | `agent_tool` | Same pattern as proposal §7.1 |
| TradingAgents personas | YAML `analysis_strategy` / Skills first | Escalate to Python only if needed |
| Analysis export | `event_hook` | Observational only |

## Rollback

Remove the adapter package from `PLUGINS_DIR` (or unset `PLUGINS_DIR`) and
restart. Core behavior is unchanged because the host surface was not modified.
