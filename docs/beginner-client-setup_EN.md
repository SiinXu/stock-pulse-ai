# Beginner client install and configuration

This guide is for users who do not want to read code: download the desktop client, paste a model API key, add stock codes, and generate the first research report.

> StockPulse produces **research assistance** only. It is **not investment advice**. You are responsible for trading decisions and risk.

Chinese version: [beginner-client-setup.md](beginner-client-setup.md). After install, continue with the [UI operation manual](ui-manual/README_EN.md).

## Before you start

1. A Windows or macOS computer.
2. A model API key from one of:
   - [Anspire Open](https://open.anspire.cn/) — mainstream models; one key can cover model + news search for the simplest first setup.
   - [AIHubMix](https://aihubmix.com/) — multi-model aggregation if you want to switch models on one platform.
3. Symbols to analyze, for example `600519,hk00700,AAPL`.

## 1. Download the client

Open the releases page:

<https://github.com/SiinXu/stock-pulse-ai/releases>

Installers are only available when a formal release has **Assets**. If the page is empty or the latest release has no matching package, StockPulse has not published a downloadable client yet — run from source / WebUI per the [README](../README.md). Do **not** download third-party packages that claim to be StockPulse.

Under **Assets**, pick:

| Computer | Download |
| --- | --- |
| Windows | `stockpulse-windows-installer-<version>.exe` |
| Windows portable | `stockpulse-windows-noinstall-<version>.zip` |
| macOS Apple silicon | `stockpulse-macos-arm64-<version>.dmg` |
| macOS Intel | `stockpulse-macos-x64-<version>.dmg` |

Do not download `latest.yml` or `*.blockmap` — they are not installers.

Mac chip type: Apple menu → About This Mac. M1/M2/M3/M4 → `arm64`; Intel → `x64`.

## 2. Install and open

- Windows installer: run the `.exe`, accept defaults.
- Windows portable: unzip and run `StockPulse.exe`.
- macOS: open the `.dmg`, drag to Applications. If Gatekeeper blocks it, allow the app under Privacy & Security.

Before upgrading on macOS, export a configuration backup from Settings when possible.

## 3. Configure an AI model

In the client open:

**Settings → AI & Models** (path labels: **System settings → AI models** / **Model Access**)

Use **one** of the plans below.

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
| Deeper deploy / env (advanced) | [Full guide](full-guide.md) / [Full guide (EN)](full-guide_EN.md) if present |
| LLM provider details | [LLM config guide (EN)](LLM_CONFIG_GUIDE_EN.md) |
