# GitHub Actions Quickstart (Three Steps)

English | [简体中文](actions-quickstart_CN.md)

This guide is the **minimum path** to run daily analysis on a fork with GitHub Actions. You do **not** need the full secret table in the deploy guide.

Source of truth for name mapping: [`.github/workflows/00-daily-analysis.yml`](../.github/workflows/00-daily-analysis.yml) (and [`.github/workflows/config-check.yml`](../.github/workflows/config-check.yml) for the Config Check workflow).

## What you need

| Name | Type | Required | Example / notes |
|------|------|----------|-----------------|
| `LLM_ZHIPU_API_KEY` **or** `LLM_SILICONFLOW_API_KEY` **or** `GEMINI_API_KEY` | Repository **Secret** | Choose **one** | Never commit a real key |
| `STOCK_LIST` | Repository **Variable** (preferred) | Recommended | `600519,000001` |
| One notification webhook (e.g. `WECHAT_WEBHOOK_URL`) | Repository **Secret** | Optional | Without IM, download the Actions Artifact |

Free market-data providers are used when token-based sources (for example Tushare) are not configured. Stability of free sources is not guaranteed.

---

## Step 1 — One model Secret (choose one)

1. Fork [SiinXu/stock-pulse-ai](https://github.com/SiinXu/stock-pulse-ai).
2. In the fork: **Settings** → **Secrets and variables** → **Actions** → **Secrets** → **New repository secret**.
3. Create **exactly one** of:

| Secret name | Provider |
|-------------|---------|
| `LLM_ZHIPU_API_KEY` | Zhipu (智谱) |
| `LLM_SILICONFLOW_API_KEY` | SiliconFlow (硅基流动) |
| `GEMINI_API_KEY` | Google Gemini |

These names are injected as `secrets.LLM_ZHIPU_API_KEY`, `secrets.LLM_SILICONFLOW_API_KEY`, and `secrets.GEMINI_API_KEY` in `00-daily-analysis.yml`. Other providers (OpenAI-compatible, Anthropic, Anspire, AIHubMix, …) also work; see [Advanced configuration](#advanced-configuration).

---

## Step 2 — Watchlist Variable `STOCK_LIST`

1. Same page: open the **Variables** tab → **New repository variable**.
2. Name: `STOCK_LIST`
3. Value (example): `600519,000001`

Comma-separated codes. Multi-market examples: `600519,hk00700,AAPL,2330.TW`.

The daily workflow reads `vars.STOCK_LIST` (or `secrets.STOCK_LIST`) into `STOCK_LIST_CONFIG`, then exports `STOCK_LIST` for the run. A repository **Variable** is the recommended placement. A Secret with the same name also works.

> Note: the job uses `environment: STOCK_LIST` for compatibility with older setups that stored configuration in a GitHub Environment of that name. For new forks, a repository Variable is enough; you do not need to create a GitHub Environment unless you already rely on one.

---

## Step 3 — Optional notification Secret

Without any notification channel, the run still produces reports you can download from the workflow **Artifacts** (see [Get the report](#get-the-report)).

To push to a chat app, add **one** of these repository Secrets (names from `00-daily-analysis.yml`):

| Secret name | Channel |
|-------------|---------|
| `WECHAT_WEBHOOK_URL` | WeCom (企业微信) bot webhook |
| `FEISHU_WEBHOOK_URL` | Feishu (飞书) bot webhook |
| `DINGTALK_WEBHOOK_URL` | DingTalk webhook |
| `DISCORD_WEBHOOK_URL` | Discord webhook |
| `SLACK_WEBHOOK_URL` | Slack incoming webhook |
| `CUSTOM_WEBHOOK_URLS` | Custom webhook URL(s), comma-separated |

Telegram needs **two** Secrets: `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` (not a single webhook URL). Email needs sender/password/receivers; see the deploy guide.

---

## Run Config Check, then Daily Analysis

1. Enable **Actions** on the fork if prompted.
2. **Actions** → **Config Check** → **Run workflow**
   Validates Secrets/Variables without a full analysis and without printing secret values ([#847](https://github.com/SiinXu/stock-pulse-ai/issues/847)).
3. After Config Check is green: **Actions** → **StockPulse Daily Analysis** → **Run workflow**
   Modes: `full` (default), `market-only`, `stocks-only`.
   Default schedule: weekdays **18:00 Asia/Shanghai** (`cron: '0 10 * * 1-5'` UTC), subject to trading-day rules and GitHub schedule delay.

If a run fails or is skipped, open the run’s **Job Summary** for a plain-language cause ([#850](https://github.com/SiinXu/stock-pulse-ai/issues/850)).

---

## Get the report

| Path | How |
|------|-----|
| **Artifact (no IM)** | Open the completed run → **Artifacts** → download `analysis-reports-<run_number>` (retained ~30 days) |
| **Notification** | Message arrives on the channel configured in Step 3 |
| **Logs** | Expand steps in the Actions run UI |

---

## Advanced configuration

Everything beyond the three steps lives in the existing docs. Do not expand this quickstart into a full env dump.

| Topic | Document |
|-------|----------|
| Full Actions deploy steps, complete secret tables | [Deploy Guide (EN) — Option 4](DEPLOY_EN.md#option-4-github-actions-deployment-serverless) · [部署指南（中文）](DEPLOY.md) |
| LLM providers, models, multi-channel routing | [LLM Config Guide (EN)](LLM_CONFIG_GUIDE_EN.md) · [LLM 配置指南](LLM_CONFIG_GUIDE.md) · [Provider guide](llm-providers.md) |
| Full install / local / Docker | [Full Guide (EN)](full-guide_EN.md) · [完整指南](full-guide.md) |
| Config Check CLI | `python scripts/actions_config_check.py` (optional `--strict-notify` / `--probe-llm`) |
| Workflow source | [`.github/workflows/00-daily-analysis.yml`](../.github/workflows/00-daily-analysis.yml) |

Examples of **advanced** (not required for first success) names already wired in the daily workflow: news keys (`SERPAPI_API_KEYS`, `TAVILY_API_KEYS`, …), `TUSHARE_TOKEN`, `AIHUBMIX_KEY`, `ANSPIRE_API_KEYS`, model overrides (`GEMINI_MODEL`, `LLM_*_MODELS`), and notification routing (`NOTIFICATION_REPORT_CHANNELS`, `NOTIFICATION_SYSTEM_ERROR_CHANNELS`).

---

## Related

- [#852](https://github.com/SiinXu/stock-pulse-ai/issues/852) — Three-line Actions preset for regular users (this document)
- [#847](https://github.com/SiinXu/stock-pulse-ai/issues/847) — Config Check (validate Secrets/Variables without full analysis)
- [#850](https://github.com/SiinXu/stock-pulse-ai/issues/850) — Plain-language run summary and short failure notification
