# Data Provider Plugin Authoring Guide

This guide turns the version 1 Data Provider contract into a complete external
package. Start with the tested reference package at
[`examples/plugins/example-provider/`](../examples/plugins/example-provider/).
The broader lifecycle and extension contracts remain authoritative in
[`plugin-extension-contract.md`](plugin-extension-contract.md).

## Reference Package

An external plugin must be one direct child of the configured plugin root:

```text
<PLUGINS_DIR>/
  example-provider/
    manifest.json
    plugin.py
    README.md
```

`PLUGINS_DIR` points to the parent directory. The loader does not recurse into
containers and does not scan any default directory when the setting is unset,
empty, or whitespace-only. The reference provider is intentionally
deterministic: it reads no environment values, requires no secret, performs no
network request, and returns two normalized daily-data rows.

The package has two stable identities:

- manifest plugin ID: `stockpulse.example-provider`;
- Data Provider registration ID: `example-daily-data`.

The provider runtime name is `ExampleReferenceProvider`. Plugin IDs,
registration IDs, and runtime names must not collide with built-ins or another
enabled plugin.

## Manifest Fields

`manifest.json` is validated before `plugin.py` is imported. Unknown fields and
invalid types fail closed.

| Field | Author requirement |
| --- | --- |
| `id` | Stable lowercase identifier matching `[a-z0-9][a-z0-9._-]*`. Do not reuse it for unrelated code. |
| `name` | Non-empty operator-facing name. |
| `version` | Plugin release in exact `MAJOR.MINOR.PATCH` form. |
| `minAppVersion` | Earliest StockPulse `MAJOR.MINOR.PATCH` version actually tested by the author. |
| `description` | Non-empty operator-facing purpose. |
| `author` | Non-empty maintainer or organization. |
| `permissions` | Required list of descriptive IDs. It is metadata only and grants or denies nothing. |
| `apiVersion` | Overall plugin API major. Version 1 uses the string `"1"`. |
| `entrypoint` | Relative `file.py:Class` entrypoint contained by the plugin directory. |

Manifest `version`, manifest `apiVersion`, and the registration
`contract_version` are independent. The sample uses plugin release `1.0.0`,
plugin API `1`, and Data Provider contract `1`. StockPulse rejects unsupported
application or API versions instead of guessing compatibility.

## Provider And Registration

The factory passed to `DataProviderRegistration` runs during plugin load. It
must return a `DataProvider` with a stable, non-empty `name` and every method
declared by `capabilities`. Contract version 1 supports the markets `cn`, `hk`,
`us`, `jp`, `kr`, and `tw`; the complete capability-to-method table is in the
[Data Providers contract](plugin-extension-contract.md#data-providers).

The reference plugin declares only `daily_data` for `cn`. Its implementation
returns the normalized columns expected by the current daily-data path:
`date`, `open`, `high`, `low`, `close`, `volume`, `amount`, and `pct_chg`.
Production plugins should validate and normalize their upstream response before
returning it. A provider that performs network or SDK I/O must configure finite
transport timeouts at its client or transport layer and raise a meaningful
exception when that single attempt fails. `DataFetcherManager` does not wrap
every provider call in a universal deadline.

`onload()` registers the declaration through the supplied `PluginContext`:

```python
registration = DataProviderRegistration(
    provider_id="example-daily-data",
    factory=ExampleDataProvider,
    markets=frozenset({"cn"}),
    capabilities=frozenset({"daily_data"}),
)
context.register(
    "data_provider",
    registration.provider_id,
    registration,
    contract_version="1",
    priority=90,
)
```

Do not retain `PluginContext`; it closes after `onload()` returns. The plugin
manager owns the returned registration handle and removes the exact provider
when the plugin is disabled. `onunload()` is needed only for resources the
plugin itself owns, such as clients or worker threads.

## Load And Verify

Data Provider activation requires the same registry instance owned by the
target `DataFetcherManager`. The default process plugin manager is bound to the
Agent Tool registry, so setting `PLUGINS_DIR` on the default process root alone
does not fabricate or select a process-wide provider manager. A composition
caller must bind the exact target explicitly.

From the repository root, with project dependencies installed, this command
uses `PLUGINS_DIR` as the startup opt-in and prints discovery, load,
registration, and disable results:

```bash
PLUGINS_DIR="$PWD/examples/plugins" python - <<'PY'
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
    print("load", services.plugin_load_results)
    print(
        "providers",
        [
            item.registration_id
            for item in plugins.registrations("data_provider")
            if item.plugin_id == "stockpulse.example-provider"
        ],
    )
    print("disable", plugins.disable("stockpulse.example-provider"))
finally:
    services.close()
PY
```

The reference candidate should be `registered` during discovery, `enabled`
after load, present as `example-daily-data`, and `disabled` after cleanup.
Keeping `PLUGINS_DIR` unset or blank skips external discovery entirely. The
setting is read once at startup; restart after changing it. Relative paths are
resolved from the process working directory, so deployments should use a
reviewed absolute path.

To install a reviewed plugin, copy its complete direct-child directory under an
operator-owned plugin root. StockPulse does not run `pip install` for plugins;
any reviewed dependency must already exist in the application environment.

## Diagnostics And Failure Isolation

Inspect `ApplicationServices.external_plugin_results` for discovery/import
results and `ApplicationServices.plugin_load_results` for `onload()` and native
registration results. Both are immutable per-candidate operation snapshots.
Representative fail-closed codes include:

| Phase | Example code | Meaning |
| --- | --- | --- |
| Discovery | `external_manifest_invalid` | JSON, field, type, version, or entrypoint validation failed. |
| Discovery | `external_entrypoint_missing` | The declared entrypoint file does not exist. |
| Discovery | `external_import_failed` | Importing the trusted Python module raised. |
| Discovery | `external_constructor_failed` | Constructing the `Plugin` class raised. |
| Discovery | `plugin_id_conflict` | Another registered plugin already owns the manifest ID. |
| Load | `native_registry_registration_failed` | The provider factory or native provider validation failed. |
| Load | `extension_registration_conflict` | The provider registration ID is already owned. |
| Load | `plugin_onload_failed` | Plugin `onload()` raised outside a typed registry failure. |

One invalid manifest, import error, constructor error, provider initialization
failure, or `onload()` failure is isolated to that candidate. Later candidates
continue through registration and load, and the core application remains
available. Isolation is an availability contract, not a security boundary.

For deterministic regression coverage, run:

```bash
python -m py_compile examples/plugins/example-provider/plugin.py tests/plugins/test_example_provider_plugin.py
python -m pytest -q tests/plugins/test_example_provider_plugin.py
python -m pytest -q tests/plugins tests/data_provider/test_data_provider_plugins.py
```

The first test module exercises the repository copy of the sample rather than a
duplicate test-only implementation. It covers an unset `PLUGINS_DIR`,
register/load/disable, an invalid manifest, provider factory failure, and later
plugin availability.

## Routing And Runtime Ownership

A plugin registers a provider; it does not become the routing authority.
`DataFetcherManager` continues to own market and capability eligibility,
operator-pinned routes, numeric-priority boundaries, adaptive ordering, health
and circuit admission, serialized calls, diagnostics, cache attribution, and
fresh/stale fallback. Existing cache entries retain their normal TTL when a
plugin is disabled.

The manager does not impose a universal deadline around `get_daily_data()` or
`_call_fetcher_method()`. A production plugin must set finite connect/read or
SDK transport timeouts for every network call it owns. When that transport
times out, raise the failure from the current provider attempt so the manager
can record it and continue its eligible fallback chain.

Do not add a private cross-provider fallback loop, cache, route table, or
dynamic provider-priority override to the plugin. Handle one provider attempt,
including its bounded transport I/O, and let the manager apply the shared
cross-provider policies from
[ADR-005](adr/ADR-005-provider-fallback-and-circuit-control.md) and
[data-source stability](data-source-stability_EN.md).

## Trust And Distribution

Setting `PLUGINS_DIR` opts into arbitrary Python code running with the same OS
user privileges as StockPulse. Plugin code can access process files,
environment values, imported objects, memory, and network routes. There is no
sandbox, subprocess boundary, signature verification, marketplace, remote
install, dependency installer, automatic update, or hot reload.

The manifest `permissions` list is descriptive metadata only. An empty list is
not proof of safety, and a listed permission is neither enforced nor granted.
Operators must review the complete plugin and its dependencies before opting
in, restrict ownership and write access to the plugin directory, and keep
`PLUGINS_DIR` unset when no trusted external code is required.
