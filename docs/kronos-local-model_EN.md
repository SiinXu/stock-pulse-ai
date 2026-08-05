# Kronos Local Finance Model (Install · Configure · Diagnose)

This page is the **productized install path**: optional dependencies, weight download, Web settings, and status verification.  
Tool contracts, registration gates, and output schema live in [Kronos Agent Tool](kronos-agent-tool.md).

## What Kronos does in analysis

- Kronos is **not** a chat LLM and is never added to the chat-model catalog.
- When ready, it registers the Agent Tool `forecast_kline_with_kronos`.
- Under multi-agent architecture it is consumed by the **Technical Agent**; under single-agent it joins that Agent's tool registry.
- It turns recent daily OHLCV into direction probabilities, return intervals, and volatility bands (research support only — **not investment advice**).
- A default install does **not** import PyTorch, download weights, or register the tool. The main analysis flow continues when Kronos is not ready.

## Hardware and platform expectations

| Topic | Detail |
| --- | --- |
| Dependencies | `requirements-kronos.txt` (includes `torch==2.13.0`, **not** installed by default) |
| Platforms | Linux x86_64/arm64, Windows x64, macOS Apple Silicon (macOS 14+); **macOS Intel unsupported** for this torch wheel |
| Memory | Start with mini; small/base need substantially more RAM and CPU/GPU |
| Desktop | **Prebuilt desktop packages do not support Kronos** (PyInstaller backend does not ship torch/weights). Use a supported source install |
| Default Docker image | Does not bundle optional deps or weights; use a custom image and mount the weights directory |

## Install optional dependencies

Install the normal StockPulse environment first, then the isolated Kronos set:

```bash
python -m pip install --upgrade --constraint constraints.txt pip
python -m pip install --constraint constraints.txt --build-constraint build-constraints.txt -r requirements-kronos.txt
python -m pip check
```

## Download weights (explicit size disclosure)

**The Web settings UI never triggers downloads.** Operators must download explicitly.

| `KRONOS_MODEL_SIZE` | Model repo | Tokenizer | Approx. download (model + tokenizer) |
| --- | --- | --- | --- |
| `mini` (recommended first install) | `NeoQuasar/Kronos-mini` | `NeoQuasar/Kronos-Tokenizer-2k` | ~40 MB |
| `small` | `NeoQuasar/Kronos-small` | `NeoQuasar/Kronos-Tokenizer-base` | ~150 MB |
| `base` | `NeoQuasar/Kronos-base` | `NeoQuasar/Kronos-Tokenizer-base` | ~500 MB |

Preferred helper (prints size first; requires `--yes` or interactive confirm; resumes when `huggingface_hub` supports it):

```bash
python scripts/download_kronos_weights.py --list-sizes
python scripts/download_kronos_weights.py \
  --size mini \
  --weights-dir "$HOME/.local/share/stockpulse/kronos" \
  --yes
```

You may also use `hf download` manually (see [kronos-agent-tool.md](kronos-agent-tool.md)). Layout example:

```text
<KRONOS_WEIGHTS_DIR>/
  Kronos-mini/
    config.json
    model.safetensors
  Kronos-Tokenizer-2k/
    config.json
    model.safetensors
```

## Configuration keys

| Key | Default | Notes |
| --- | --- | --- |
| `KRONOS_ENABLED` | `false` | Enable the local tool; **restart the process** after enabling so the plugin can register |
| `KRONOS_MODEL_SIZE` | `mini` | `mini` / `small` / `base` |
| `KRONOS_WEIGHTS_DIR` | empty | Absolute local root directory |

Web settings: **AI & Models → Local Models**, with a Kronos status panel and the three fields above. Help text documents restart and no-download policy.

```dotenv
KRONOS_ENABLED=true
KRONOS_MODEL_SIZE=mini
KRONOS_WEIGHTS_DIR=/absolute/path/to/kronos-weights
```

## Verify with the status panel

1. Open **Settings → AI & Models → Local Models**.
2. Use the **Kronos status** panel (`GET /api/v1/system/config/kronos/status`):
   - Optional dependency import probes (by package name; no module-level torch import)
   - Weights directory presence, size, and mtime
   - Enable flag
   - One **next step** message per state
3. After a fresh enable, restart, then exercise the Agent / Technical Agent path.

## Status matrix (summary)

| `reason` | Meaning | Next step |
| --- | --- | --- |
| `disabled` | Tool off | Install deps → download weights → set dir → enable → restart |
| `dependencies_missing` | Optional packages missing | `pip install -r requirements-kronos.txt` (command above) |
| `weights_dir_*` / `weights_incomplete` / `weights_invalid` | Path or artifact issues | `scripts/download_kronos_weights.py` or fix directories |
| `ready` | Local gates pass | Restart if the tool is not registered yet; then use Agent |
| `packaged_desktop_unsupported` | Prebuilt desktop | Use a source install |

## Failures must not break analysis

- Disabled or failed gates: tool is **not registered**; logs include actionable guidance.
- Tool call failures return a typed `kronos-forecast-v1` error payload and **do not** abort the wider analysis run.
- Analysis never auto-downloads weights from the network.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| No Kronos UI | Upgrade to a build that includes this feature; open Local Models |
| Dependency probe fails | Install `requirements-kronos.txt` and run `pip check` |
| Weights incomplete/invalid | Re-run the download helper or verify `config.json` + `model.safetensors` |
| Enabled but no tool | **Restart** the API/CLI process; confirm `KRONOS_ENABLED=true` |
| Desktop unsupported | Expected; use a source backend |
| macOS Intel cannot install torch | Outside the optional matrix; default app still works without Kronos |

## Related docs

- [Kronos Agent Tool contract](kronos-agent-tool.md)
- [FAQ](FAQ.md) / [FAQ (EN)](FAQ_EN.md)
- [Local Model Catalog (Ollama, etc.)](local-model-catalog.md)
