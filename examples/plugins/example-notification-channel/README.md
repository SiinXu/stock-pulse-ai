# Example Notification Channel

This trusted in-process plugin registers the deterministic `example_log`
notification channel. It writes only route and payload-size metadata to the
application log; it performs no network requests and requires no secret.

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
the adapter from subsequent dispatch snapshots.

External plugins execute with the same OS privileges as StockPulse. Review all
code before opting in. StockPulse does not sandbox plugins, install their
dependencies, or provide a remote marketplace.
