# Example Notification Channel (surface v1 reference)

This trusted in-process plugin is the **official notification-channel
reference** for plugin extension surface v1 (ADR-007). It registers the
deterministic `example_log` channel using only the frozen `src.plugins` author
exports. It writes only route and payload-size metadata to the application log;
it performs no network requests and requires no secret.

Point `PLUGINS_DIR` at the parent examples directory and include the canonical
channel ID in a route when you want to select it explicitly:

```bash
export PLUGINS_DIR="$PWD/examples/plugins"
export NOTIFICATION_REPORT_CHANNELS="example_log"
python main.py --stocks 600519
```

Leaving a route empty includes every enabled and available channel, including
`example_log`. A non-empty route never falls back to broadcast when its enabled
and available intersection is empty. Disabling or unloading this plugin removes
the adapter from the next dispatch snapshot after all already-entered snapshots
have finished; new snapshots wait while that lifecycle change is pending. The
default aggregate stock-report path uses this same dispatcher, so
the command above delivers one `example_log` attempt without bypassing core
routing, noise control, or retry/idempotency accounting.

External plugins execute with the same OS privileges as StockPulse. Review all
code before opting in. StockPulse does not sandbox plugins, install their
dependencies, or provide a remote marketplace.
