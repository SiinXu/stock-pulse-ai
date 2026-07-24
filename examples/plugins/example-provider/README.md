# Example Data Provider Plugin

This directory is a deterministic teaching package, not a production market
data source. It performs no network requests, reads no secrets, and returns a
small normalized daily-data fixture.

Set `PLUGINS_DIR` to this directory's parent (`examples/plugins`), not to
`example-provider` itself. Data Provider plugins must use a `PluginManager`
bound to the exact target `DataFetcherManager.plugin_registry`.

See the [Data Provider Plugin Authoring Guide](../../../docs/data-provider-plugin-authoring.md)
for the tested load command, lifecycle diagnostics, manifest fields, trust
model, and routing boundaries.
