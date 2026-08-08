# Beginner client install and configuration

This guide is for users who do not want to read code: download the desktop client, paste a model API key, add stock codes, and generate the first research report.

> StockPulse produces **research assistance** only. It is **not investment advice**. You are responsible for trading decisions and risk.

Chinese version: [beginner-client-setup.md](beginner-client-setup.md). After install, continue with the [UI operation manual](ui-manual/README_EN.md).


## Zero-config first success (no API key)

You can complete a useful first run without a cloud key. **Local / zero-cost paths are the primary path**; cloud keys are an optional upgrade.

1. **Local Ollama auto-detect**: setup readiness and `GET /api/v1/onboarding/first-run` probe loopback (`127.0.0.1` / `localhost` / `::1`) by default. Failures are log-only and **never block startup**. When Ollama is reachable, the primary CTA is **Start with a local model** and applies the official `local-first` preset fields (no secrets invented).
2. **Offline sample analysis**: if no model and no Ollama are available, open the built-in **sample analysis** (`GET /api/v1/onboarding/demo-analysis`). It is always labeled **Sample data — not a live analysis**. Use it only to learn the report layout.
3. **Data-only (same artifact as `--dry-run`)**: after setting a watchlist, run `python main.py --dry-run` to fetch market data without calling an LLM.
4. Turn detection off with `LOCAL_RUNTIME_AUTO_DETECT=false`. Timeout: `LOCAL_RUNTIME_DETECT_TIMEOUT_SECONDS=0.35` (default).

**Existing configurations are never overwritten** by first-run readiness. Beginner recommendations apply only when no primary model is configured (and the install looks fresh). Full AI analysis still needs a primary model (cloud key or an applied local Ollama profile). Cloud setup continues in **Configure an AI model** below.

## Before you start

1. A Windows or macOS computer.
2. A model API key from one of:
   - [Anspire Open](https://open.anspire.cn/) — mainstream models; one key can cover model + news search for the simplest first setup.
   - [AIHubMix](https://aihubmix.com/) — multi-model aggregation if you want to switch models on one platform.
3. Symbols to analyze, for example `600519,hk00700,AAPL`.

## 1. Download the client

**Download only from this repository's releases page:**

<https://github.com/SiinXu/stock-pulse-ai/releases>

As of the published tags, the newest formal release that ships desktop installers is **`v3.29.0`**. A source/changelog version such as `4.0.0` does **not** mean a matching desktop installer exists. If the newest source tag has no `.exe` / `.zip` / `.dmg` under **Assets**, use the latest Desktop release that does, build locally per [desktop packaging](desktop-package.md), or run from source / WebUI per the [README](../README.md).

Do **not** install packages from the upstream `daily_stock_analysis` repo, app-store mirrors, or third-party mirrors that claim to be StockPulse, even when filenames look similar.

Under **Assets**, pick the file for your machine:

| Computer | Currently published names (example: `v3.29.0`) |
| --- | --- |
| Windows installer | `daily-stock-analysis-windows-installer-v3.29.0.exe` |
| Windows portable | `daily-stock-analysis-windows-noinstall-v3.29.0.zip` |
| macOS Apple silicon | `daily-stock-analysis-macos-arm64-v3.29.0.dmg` |
| macOS Intel | `daily-stock-analysis-macos-x64-v3.29.0.dmg` |

Notes:

- Published desktop assets still use the legacy `daily-stock-analysis-...` prefix (verify with `gh release view v3.29.0`).
- The packaging pipeline on current `main` (`apps/dsa-desktop/package.json` and `.github/workflows/desktop-release.yml`) prepares **future** Desktop releases as `stockpulse-windows-installer-<tag>.exe`, `stockpulse-windows-noinstall-<tag>.zip`, `stockpulse-macos-arm64-<tag>.dmg`, and `stockpulse-macos-x64-<tag>.dmg`. Trust the actual **Assets** names on this repo only.
- Skip `latest.yml` and `*.blockmap` — they are not installers.

Mac chip type: Apple menu → About This Mac. M1/M2/M3/M4 → `arm64`; Intel → `x64`.

## 2. Install and open

- Windows installer: run the `.exe`, accept defaults.
- Windows portable: unzip and run `StockPulse.exe`.
- macOS: open the `.dmg`, drag to Applications. If Gatekeeper blocks it, allow the app under Privacy & Security.

Before upgrading on macOS, export a configuration backup from Settings when possible.

On a **first** desktop open (fresh install), StockPulse opens the guided first-run wizard automatically. You can choose a cloud API, a **local model** path (Ollama / Model Pack import with one-click runtime start), or a local CLI backend. Opening the app does not call paid cloud models until you save a cloud path. Details: [Desktop packaging (EN)](desktop-package_EN.md).

## 3. Configure an AI model

If the wizard is not open, go to:

**Settings → AI & Models** (path labels: **System settings → AI models** / **Model Access**)

Use **one** of the plans below (or finish the wizard's local-model / CLI path instead).

> Important: after every change, click **Save**. Wait for success before leaving the page or returning to Home.

### Option A: Anspire Open

1. Open [Anspire Open](https://open.anspire.cn/), sign in, create an API key.
2. In the client: **AI & Models → Model Access** → **Add model service** → `Anspire Open`.
3. Paste the API key.
4. Add models: **Fetch models** and select, or type names enabled in the console (new connections do not prefill sample models). If unsure, pick a console-recommended or lightweight model.
5. **Save**, then **Test connection**.

### Option B: AIHubMix

1. Open [AIHubMix](https://aihubmix.com/), sign in, create an API key.
2. **AI & Models → Model Access** → **Add model service** → `AIHubmix (aggregator)` (label as in UI).
3. Paste the API key.
4. Choose models enabled in the console; if unsure, use a recommended model.
5. **Save**, then **Test connection**.

When the test succeeds, continue.

## 4. Watchlist

Open the basics / watchlist field (often under system / base settings — follow guided setup or the readiness checklist on Home):

Example:

`600519,hk00700,AAPL`

Comma-separated. Common formats:

- A-shares: `600519`, `300750`, `000001`
- Hong Kong: `hk00700`, `hk09988`
- US: `AAPL`, `TSLA`, `NVDA`

Save, wait for success, return to Home.

## 5. Optional: news sources

News is not strictly required for a basic technical run, but improves news, filings, events, themes, and risk notes.

Open **Settings → Data Sources** and, depending on your model provider:

1. Anspire Open: fill **Anspire API Keys** with the same Anspire key, then save.
2. AIHubMix: consider [SerpAPI](https://serpapi.com/baidu-search-api) or [Tavily](https://tavily.com/) keys in the matching fields, then save.

You may skip news for a first trial.

## 6. Run an analysis

On **Home**:

1. Prefer **Start analysis** / open **Research → Analysis Workbench**.
2. Enter a symbol such as `600519`.
3. Start the job; wait until it finishes (queued → running → done).
4. Open the report from Workbench **History** (or the completion CTA).

Read the report with [08 Reading reports](ui-manual/08-reading-reports_EN.md). Full UI map: [UI manual](ui-manual/README_EN.md).

## FAQ

### Too many files on the release page — which one?

Normal Windows users take the `.exe` installer. Skip `latest.yml` and `*.blockmap`.

### Key saved but still broken?

1. Key copied completely, no extra spaces.  
2. Provider account has balance/quota.  
3. Selected model is enabled on the provider.  
4. Test connection errors: missing model, permission, or balance.

### Configuration is a mess?

Export a config backup from Settings. On failure, import the backup, or reconfigure only: AI model, watchlist, news keys.

## Next steps

| Goal | Doc |
| --- | --- |
| Learn the shell and daily path | [UI manual](ui-manual/README_EN.md) |
| Deeper deploy / env (advanced) | [Full guide (EN)](full-guide_EN.md) · [Full guide (ZH)](full-guide.md) |
| LLM provider details | [LLM config guide (EN)](LLM_CONFIG_GUIDE_EN.md) |
