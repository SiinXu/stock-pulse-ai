# Kronos K-line Forecasting Agent Tool

StockPulse can expose the official Kronos financial time-series model as an
optional built-in Agent Tool. Kronos consumes recent daily OHLCV records and
returns sampled future K-line direction probabilities, return intervals,
annualized volatility intervals, and daily OHLC uncertainty bands.

Kronos is not an LLM and is never added to the chat-model catalog. It supplies
quantitative supporting evidence to Agent workflows. The tool is absent from a
default installation. After an operator explicitly enables it, the multi-agent
architecture exposes it only to the Technical Agent; the default single-agent
architecture exposes it to that one Agent with the rest of the process tool
registry. Single-Agent RUN and Chat both freeze a stock scope from the current
request/context before dispatch, so a call for another symbol fails closed.

## Default And Registration Contract

The tool registers only when all three gates pass:

1. `KRONOS_ENABLED=true`.
2. Every package in `requirements-kronos.txt` imports successfully.
3. `KRONOS_WEIGHTS_DIR` contains the selected official model and its matching
   tokenizer: both configs match the pinned architecture, both safetensors
   containers are structurally valid, and the official local-only loaders can
   construct the model/tokenizer pair.

If any gate fails, StockPulse does not register
`forecast_kline_with_kronos`. Startup logs provide a reason and remediation
without logging the configured local path. Default analysis, API, Web, desktop,
Docker, reports, and notifications continue without Kronos.

The plugin registers a declared `ToolDefinition` through the existing
`agent_tool` extension point. Calls still pass through the same
`ToolRegistry`, ToolSurface, stock-scope, timeout, serialization, audit, and
completion boundaries as core tools. Plugin definitions opt in to mandatory
contract enforcement, so argument and scope validation remains active even on
the native compatibility runner. Optional defaults are validated against their
schema and materialized before scope checks; the scoped `stock_code` identity is
always required. The Agent can supply only:

- `stock_code`: a bounded A-share, Hong Kong, or U.S. symbol;
- `lookback_days`: 30 through 512;
- `horizon_days`: 1 through 30.

An Agent cannot supply a filesystem path, model identifier, or URL. The model
and tokenizer paths come only from process configuration.

## Install Optional Dependencies

Install the normal StockPulse environment first. Then install the isolated,
exact Kronos dependency set:

```bash
python -m pip install --upgrade --constraint constraints.txt pip
python -m pip install --constraint constraints.txt --build-constraint build-constraints.txt -r requirements-kronos.txt
python -m pip check
```

`requirements.txt` does not include PyTorch, Einops, Safetensors, or the other
Kronos-only packages. Removing the optional environment therefore has no effect
on the default dependency contract.

Prebuilt desktop artifacts and the default Docker image intentionally do not
bundle this optional dependency set or model weights. Run Kronos from a source
environment with the optional requirements installed, or build a reviewed
custom backend image that installs them and mounts the local weight directory.

StockPulse vendors the official MIT inference implementation from
`shiyu-coder/Kronos` commit
`67b630e67f6a18c9e9be918d9b4337c960db1e9a`. Provenance, the limited
package-relative import change, and the upstream license are recorded under
`src/services/_kronos_vendor/`.

## Place Model Weights

Choose one supported model/tokenizer pair:

| `KRONOS_MODEL_SIZE` | Model | Tokenizer | Maximum StockPulse lookback |
| --- | --- | --- | --- |
| `mini` | `NeoQuasar/Kronos-mini` | `NeoQuasar/Kronos-Tokenizer-2k` | 512 |
| `small` | `NeoQuasar/Kronos-small` | `NeoQuasar/Kronos-Tokenizer-base` | 512 |
| `base` | `NeoQuasar/Kronos-base` | `NeoQuasar/Kronos-Tokenizer-base` | 512 |

The unified 512-day ceiling keeps the tool schema identical across sizes even
though the official mini model has a larger native context.

For example, prepare the mini pair outside the StockPulse process:

```bash
export KRONOS_WEIGHTS_DIR="$HOME/.local/share/stockpulse/kronos"
hf download NeoQuasar/Kronos-mini --local-dir "$KRONOS_WEIGHTS_DIR/Kronos-mini"
hf download NeoQuasar/Kronos-Tokenizer-2k --local-dir "$KRONOS_WEIGHTS_DIR/Kronos-Tokenizer-2k"
```

Small and base use their corresponding model directory plus the shared
`Kronos-Tokenizer-base` directory. Every selected directory must contain at
least `config.json` and `model.safetensors`:

```text
<KRONOS_WEIGHTS_DIR>/
  Kronos-mini/
    config.json
    model.safetensors
  Kronos-Tokenizer-2k/
    config.json
    model.safetensors
```

Model weights are never packaged, fetched by pip, or downloaded by StockPulse.
`local_files_only=True` is enforced when the model loads. StockPulse never runs
the example `hf download` command, so it neither changes nor bypasses
`OUTBOUND_HTTP_ALLOWLIST`; the operator's shell and network policy govern that
separate download. In an offline or firewall-denied environment, download on an
approved machine, verify the artifacts, and copy the two directories into the
configured local root. Do not weaken the outbound policy or add a broad
allowlist entry. Trusted private HTTP services used elsewhere by StockPulse
still require an exact `host:port` allowlist entry as documented in [Outbound
HTTP Security Policy](security-outbound-policy.md).

## Enable

Set the three environment values and restart the process:

```dotenv
KRONOS_ENABLED=true
KRONOS_MODEL_SIZE=mini
KRONOS_WEIGHTS_DIR=/absolute/path/to/kronos-weights
```

Long-running CLI and API processes resolve the built-in plugin during
application-root startup. Source-based desktop backends do the same when their
Python environment contains the optional dependencies. Configuration changes
take effect only after restart. Enabling Kronos imports the optional modules and
loads the selected model/tokenizer during plugin registration so an unusable
tool is never advertised. Startup therefore incurs the selected model's local
I/O, memory, and device-initialization cost once; the loaded predictor is reused
for later calls.

## Output Contract

Successful calls return `schema_version=kronos-forecast-v1` with:

- the canonical stock code, data source, as-of date, lookback, and horizon;
- official model and tokenizer identities;
- sampled `up`, `flat`, and `down` horizon probabilities, with `dominant` set
  to `ambiguous` whenever the largest path counts are tied;
- p10/p50/p90 horizon-return and annualized-volatility intervals;
- p10/p50/p90 open/high/low/close bands for each future business day;
- sampling metadata, limitations, and the mandatory disclaimer.

StockPulse uses five independent official predictor calls with fixed
temperature and top-p values. The result is probabilistic model output, not a
calibrated likelihood or guaranteed price target. Exchange-specific holidays
are approximated with business days.

Every successful or typed error result carries:

> Experimental model forecast for research support only. It does not guarantee
> future performance and is not investment advice.

## Limitations

- Forecasts reflect patterns learned from historical data. Structural breaks,
  policy shocks, halted trading, corporate actions, and liquidity regime
  changes can invalidate those patterns.
- Direction probabilities are based on a small bounded sample of stochastic
  paths and must not be interpreted as calibrated confidence.
- Daily source quality and adjustment policy affect the input distribution.
- Larger models consume substantially more memory and CPU/GPU time.
- This tool does not place trades, size positions, guarantee returns, or replace
  licensed financial advice.

## Verification

The default suite mocks only the inference backend; readiness gates, plugin
registration, official config matching, safetensors container validation,
ToolRegistry delegation, schema/default validation, single-Agent stock scope,
and output aggregation run through their real code paths. The production
factory also performs the real local model load before registration; the
opt-in test below exercises that load with reviewed artifacts.

Real local inference is explicit and excluded from default CI:

```bash
KRONOS_RUN_REAL_TEST=1 \
KRONOS_MODEL_SIZE=mini \
KRONOS_WEIGHTS_DIR=/absolute/path/to/kronos-weights \
python -m pytest tests/services/test_kronos_real_inference.py -m network -q
```

## Rollback

Set `KRONOS_ENABLED=false` and restart. The built-in plugin will not load and
the tool will be removed from the executable catalog. Optional packages and
weight directories can then be removed independently. No database migration or
stored report conversion is required.
