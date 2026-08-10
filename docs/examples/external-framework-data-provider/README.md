# OpenBB External Framework Data Provider (Demonstration)

This directory is a **thin, default-off** demonstration of absorbing an external
framework (OpenBB) through the frozen StockPulse `data_provider` extension
point. It is the runnable companion to the
[External Framework Adapter Guide](../../external-framework-adapter-guide.md).

## What this is

| Item | Value |
| --- | --- |
| Manifest plugin ID | `stockpulse.openbb-data-provider` |
| Provider registration ID | `openbb-daily-data` |
| Runtime provider name | `OpenBBAdapterProvider` |
| Extension point | `data_provider` only (surface v1 — **no new points**) |
| Markets | `us`, `hk`, `cn` |
| Capabilities | `daily_data` |
| Default load set | **Not included**. Must be copied or opted in explicitly. |

## Trust model (read first)

External adapter plugins run as **trusted in-process Python** with the same OS
privileges as StockPulse. There is no sandbox, no dependency installer, no
remote marketplace, and no hot reload. Manifest `permissions` are descriptive
metadata only.

Before enabling:

1. Review every file in this directory.
2. Install and pin OpenBB yourself in the application environment
   (`pip install openbb` or your org's approved mirror). StockPulse will not
   install it.
3. Point `PLUGINS_DIR` at a reviewed parent directory that contains this package
   as a **direct child**. Prefer an absolute, operator-owned path in production.

## Install (operator steps)

```bash
# 1) Install the external dependency manually (outside StockPulse)
pip install 'openbb>=4'

# 2) Copy this package under an operator-owned plugin root
mkdir -p /opt/stockpulse/plugins
cp -R docs/examples/external-framework-data-provider \
  /opt/stockpulse/plugins/openbb-data-provider

# 3) Opt in at process start (absolute path recommended)
export PLUGINS_DIR=/opt/stockpulse/plugins
```

Data Provider plugins require a `PluginManager` bound to the target
`DataFetcherManager.plugin_registry`. Setting `PLUGINS_DIR` alone does not
fabricate a process-wide provider manager. See the
[Data Provider Plugin Authoring Guide](../../data-provider-plugin-authoring.md)
for the composition pattern and lifecycle diagnostics.

## Behavior contract

- **Field normalization** → `date`, `open`, `high`, `low`, `close`, `volume`,
  `amount`, `pct_chg` (same contract as other daily providers).
- **Missing OpenBB dependency** → raises `MissingOpenBBDependencyError` with an
  explicit install message. Never returns `None` or an empty frame to fake
  success.
- **Upstream empty / failure** → raises so `DataFetcherManager` records the
  attempt and continues its eligible fallback chain.
- **Timeouts** → the SDK call has an adapter-owned wall-clock deadline and
  raises `OpenBBProviderTimeoutError`, allowing `DataFetcherManager` to continue
  its eligible fallback chain. The host does not wrap every provider call in a
  universal deadline.
- **No private fallback loop** → one attempt only; shared routing stays with
  `DataFetcherManager`.

## Offline verification

```bash
python -m py_compile docs/examples/external-framework-data-provider/plugin.py
python -m pytest -q tests/plugins/test_external_framework_openbb_provider.py
```

Tests inject a fixture client and never require a live OpenBB install or
network access (`pytest -m "not network"` safe).

## V1 surface declaration

This package does **not** introduce a seventh extension point, marketplace,
sandbox, or dependency installer. It only wires OpenBB onto the existing
`data_provider` registration path described by ADR-007 and the plugin extension
contract.
