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
2. Install and pin the supported OpenBB minor in the application environment
   (`pip install 'openbb>=4.7,<4.8'` or your org's approved mirror). StockPulse will not
   install it.
3. Point `PLUGINS_DIR` at a reviewed parent directory that contains this package
   as a **direct child**. Prefer an absolute, operator-owned path in production.

## Install (operator steps)

```bash
# 1) Install the external dependency manually (outside StockPulse)
pip install 'openbb>=4.7,<4.8'

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
  `amount`, `pct_chg`. Required OHLCV/date values must be numeric, finite, and
  structurally valid; volume is required and cannot be synthesized.
- **Ordering and duplicates** → parse and sort timestamps ascending, retain the
  latest observation for each UTC date, then derive `amount` (when absent) and
  `pct_chg`.
- **Symbols** → US passes through; Shanghai/Shenzhen and HK forms are mapped to
  yfinance (`600519.SS`, `000001.SZ`, `0700.HK`). BSE is explicitly unsupported
  by this example and raises before I/O so the manager can fall back.
- **Missing OpenBB dependency** → raises `MissingOpenBBDependencyError` with an
  explicit install message. Never returns `None` or an empty frame to fake
  success.
- **Upstream empty / failure** → raises so `DataFetcherManager` records the
  attempt and continues its eligible fallback chain.
- **Timeouts** → the single OpenBB/yfinance request runs in an isolated process
  group. At the configured positive deadline, the adapter terminates and reaps
  that process tree before raising `TimeoutError`; no timed-out worker thread is
  left behind.
- **One supported call** → OpenBB `>=4.7,<4.8`,
  `obb.equity.price.historical(..., provider="yfinance")`, exactly once. SDK
  `TypeError` is propagated and never used as signature negotiation.
- **No private fallback loop** → shared routing stays with `DataFetcherManager`.

## Offline verification

```bash
python -m py_compile docs/examples/external-framework-data-provider/plugin.py
python -m pytest -q tests/plugins/test_external_framework_openbb_provider.py
```

Tests use deterministic OpenBB 4.7-shaped OBBject/provider fakes and a real
short-lived subprocess timeout probe; they never require a live OpenBB install
or network access (`pytest -m "not network"` safe). A live OpenBB/network smoke
is intentionally not part of the offline gate.

## V1 surface declaration

This package does **not** introduce a seventh extension point, marketplace,
sandbox, or dependency installer. It only wires OpenBB onto the existing
`data_provider` registration path described by ADR-007 and the plugin extension
contract.
