<div align="center">

# StockPulse · AI Stock Analysis & Investment Research Workbench

[![GitHub stars](https://img.shields.io/github/stars/SiinXu/stock-pulse-ai?style=social)](https://github.com/SiinXu/stock-pulse-ai/stargazers)
[![CI](https://github.com/SiinXu/stock-pulse-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/SiinXu/stock-pulse-ai/actions/workflows/ci.yml)
[![License: MIT + AGPL-3.0](https://img.shields.io/badge/License-MIT%20%2B%20AGPL--3.0-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub Actions](https://img.shields.io/badge/GitHub%20Actions-Ready-2088FF?logo=github-actions&logoColor=white)](https://github.com/features/actions)

**Open-source AI stock analysis for A-shares, Hong Kong, US, Japan, Korea, and Taiwan markets**

Local-first research workbench: multi-market data → technical & news context → LLM / multi-agent analysis → stratified reports → notifications (Telegram, Discord, Slack, Email, WeChat Work, Feishu).

[Features](#key-features) · [Why StockPulse](#why-stockpulse) · [Quick Start](#quick-start) · [Sample Output](#sample-output) · [Docs](docs/INDEX_EN.md) · [Full Guide](docs/full-guide_EN.md)

**English** | [简体中文](docs/README_CN.md) | [繁體中文](docs/README_CHT.md)

</div>

> [!NOTE]
> StockPulse builds on [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) with thanks to the original authors. Project licensing: original portions under MIT; StockPulse additions under **AGPL-3.0**. See [LICENSE](LICENSE).

<a id="why-stockpulse"></a>
## Why StockPulse

StockPulse is a **local-first investment research workbench**: multi-market data, evidence-aware analysis, optional agents, and notifications under **your** control—not a black-box stock tip service. It emphasizes **auditable risk controls**, **plugin-friendly extension**, and **honest report structure** so research stays inspectable.

| Highlight | On `main` | Docs |
| --- | --- | --- |
| **Report strata (trust UX)** | Facts / gaps / inference / risks / framework alignment / disclaimer in Markdown, brief, WeChat, and Web full report | [CHANGELOG](docs/CHANGELOG.md) |
| **Human-in-the-loop risk gate** | Default-off approvals for high-risk control paths; durable proposals + `/approvals` UI | [Human approvals](docs/human-approvals_EN.md) |
| **Strict Agent ToolSurface** | Deny-by-default tools, grants, schema/stock scope, outbound URL policy | [Security baseline](docs/security-baseline.md) |
| **Local Model Packs** | Versioned offline GGUF import (Web + Desktop Ollama), integrity checks | [Model packs](docs/model-packs.md) |
| **Scheduled research tasks** | Schema-v2 daily analysis, research brief, risk check; Home “today” view | [Scheduled tasks](docs/scheduled-tasks.md) |
| **Trusted plugins** | Strategies, report templates, notification channels, event hooks, data providers | [Plugin contract](docs/plugin-extension-contract.md) |
| **Agent Soul + Personas** | Charter across Single/Multi/Chat; optional committee Personas (default off) | [Agent Soul](docs/agent-soul.md) |
| **Bounded Critic loop** | Default-off critic before multi-agent decisions (pass / retry / fail-soft) | [CHANGELOG](docs/CHANGELOG.md) |
| **Investment framework (backend)** | Versioned personal framework API/storage; Web editor still minimal | [Framework](docs/personal-investment-framework_EN.md) |
| **Security audit Phase 1** | Durable privileged-path audit trail | [Security audit](docs/security-audit.md) |
| **Offline quality panel** | Deterministic fixtures + local runner (no live LLM scoring) | [CONTRIBUTING](docs/CONTRIBUTING_EN.md) |
| **Open source licensing** | MIT (original portions) + AGPL-3.0 (StockPulse additions) | [LICENSE](LICENSE) |

### Explicit non-claims

- **Not** multi-tenant SaaS / RBAC after admin login ([AUTH-05](docs/security-baseline.md), [#230](https://github.com/SiinXu/stock-pulse-ai/issues/230)).
- **Plugins = trusted process code** (env, secrets, DB, files)—never load untrusted packages.
- Free market data can run without tokens; **stability is not guaranteed**.
- **Research only—not investment advice** and not regulated advisory.

## Key features

| Area | What you get |
| --- | --- |
| **AI research reports** | Scores, trends, levels, risks, catalysts, checklists; **stratified** facts vs inference vs disclaimer |
| **Multi-market data** | A / HK / US / JP / KR / TW + ETFs; quotes, K-lines, indicators, news, filings, fundamentals — [market boundaries](docs/market-support.md) |
| **Web + desktop workbench** | Analysis, history, full Markdown, backtest, portfolio (incl. paper trading type), settings, light/dark UI |
| **Agent strategy chat** | Multi-turn Q&A; built-in strategies; tools under ToolSurface; Bot/API/Web |
| **Risk & governance** | HITL approvals, security audit, outbound HTTP policy, public-bind safeguards |
| **Local & offline AI** | Ollama catalog pulls, **Model Pack** GGUF import, optional Kronos tool (default off) |
| **Automation** | GitHub Actions, Docker, process-local scheduled tasks, FastAPI service |
| **Notifications** | WeChat Work, Feishu, Telegram, Discord, Slack, email + **notification channel plugins** |
| **Screening & signals** | AlphaSift / Discover, decision signals, alerts, market review |
| **Import & watchlist** | Image / CSV / Excel / clipboard; code · name · pinyin autocomplete |

Deep field contracts, data-source priority, and deploy paths: [Full Guide (EN)](docs/full-guide_EN.md).

### Stack & data sources

| Type | Examples |
| --- | --- |
| AI models | Anspire, AIHubMix, Gemini, OpenAI-compatible, DeepSeek, Qwen, Claude, **Ollama** |
| Market data | TickFlow, AkShare, Tushare, Pytdx, Baostock, YFinance, Longbridge |
| News search | Anspire, SerpAPI, Tavily, Bocha, Brave, MiniMax, SearXNG |
| Social (optional, US) | Stock Sentiment API (Reddit / X / Polymarket) |

## Repository map

| Area | Path |
| --- | --- |
| Backend | `src/`, `data_provider/`, `api/`, `bot/` |
| Clients | `apps/dsa-web/`, `apps/dsa-desktop/` |
| Strategies & reports | `strategies/`, `templates/` |
| Docs & tests | `docs/`, `tests/` |
| Ops | `scripts/`, `docker/`, `.github/workflows/` |
| Entrypoints | `main.py`, `server.py`, `webui.py` |

Architecture: [overview](docs/architecture-overview.md).

## Quick start

### Option A — GitHub Actions (no server)

1. **Fork** this repository.
2. **Secrets** → `Settings` → `Secrets and variables` → `Actions`  
   - At least one model key: `ANSPIRE_API_KEYS` or `AIHUBMIX_KEY` (or Gemini / Anthropic / OpenAI-compatible).  
   - At least one channel: Telegram / Discord / Slack / Email / WeChat / Feishu secrets.  
   - Required: `STOCK_LIST` e.g. `600519,hk00700,AAPL,2330.TW`  
   - Recommended: news keys (Anspire / SerpAPI / Tavily / …).  
   Details: [LLM guide](docs/LLM_CONFIG_GUIDE_EN.md), [Full guide](docs/full-guide_EN.md).
3. Enable **Actions**, then run workflow **StockPulse Daily Analysis**.
4. Default schedule: weekdays **18:00 Asia/Shanghai** (trading-day rules apply).

### Option B — Local / Docker / desktop

```bash
git clone https://github.com/SiinXu/stock-pulse-ai.git && cd stock-pulse-ai

python -m pip install --upgrade --constraint constraints.txt pip
python -m pip install --build-constraint build-constraints.txt -r requirements.txt
python -m pip check

cp .env.example .env   # add model + optional data/news keys
python main.py         # one-shot analysis
```

Useful commands:

```bash
python main.py --debug
python main.py --dry-run
python main.py --stocks 600519,hk00700,AAPL,2330.TW
python main.py --market-review
python main.py --schedule
python main.py --serve-only
python main.py --webui          # http://127.0.0.1:8000
```

Install pins and extras: [Full guide — install](docs/full-guide_EN.md). Desktop packaging: [desktop package](docs/desktop-package.md). Beginner install: [beginner client setup (EN)](docs/beginner-client-setup_EN.md).

## Sample output

### Decision dashboard (notification)

```text
🎯 Decision dashboard
3 symbols | 🟢 buy:0 🟡 hold:2 🔴 sell:1

📊 Summary
⚪ EXAMPLE_A: hold | score 65 | bullish bias
⚪ EXAMPLE_B: hold | score 48 | range
🟡 EXAMPLE_C: sell | score 35 | bearish bias
```

Reports also include **stratified sections** (verified facts, missing data, model inference, risks, framework alignment, non-advice disclaimer) in Markdown / Web full report.

### Market review

```text
🎯 Market review
Major indices, advance/decline, leading and lagging sectors
```

## Web UI & Agent

```bash
python main.py --webui
# or: python main.py --webui-only
```

Workbench: settings, tasks, history, full reports (with strata), Agent chat (`/chat`), backtest, portfolio, Discover/screening, **Approvals** when HITL is enabled.

- Built-in strategies (MA, Chan, Elliott-style, themes, events, growth, …)
- Multi-turn chat, export, notify, background runs
- Set `AGENT_MODE=false` to disable Agent surfaces

See [Full guide](docs/full-guide_EN.md) and [LLM config](docs/LLM_CONFIG_GUIDE_EN.md).

## FAQ (SEO / GEO)

**What is StockPulse?**  
An open-source **AI stock analysis** system and **local-first research workbench** for multi-market equities (China A-shares, Hong Kong, US, Japan, Korea, Taiwan).

**Is it free?**  
The software is open source (MIT upstream + AGPL-3.0 StockPulse code). You pay for optional cloud LLM/news/data APIs you configure.

**Does it place trades?**  
No. It produces research reports and signals. Optional paper portfolios simulate fills; live broker paths are limited and out of scope for “auto-trading.”

**Can I run fully offline?**  
You can use **Ollama** and **Model Packs** for local models. Market data and news still depend on configured providers (some free sources work without keys).

**Is this investment advice?**  
No. Research and education only. You own trading decisions and risk.

## Links

[Repository](https://github.com/SiinXu/stock-pulse-ai) · [Issues](https://github.com/SiinXu/stock-pulse-ai/issues) · [English docs index](docs/INDEX_EN.md) · [Chinese docs index](docs/INDEX.md) · [Security baseline](docs/security-baseline.md) · [Changelog](docs/CHANGELOG.md)

## License

- **Upstream original code**: MIT (Copyright © ZhuLinsen)  
- **StockPulse new / substantial modifications**: AGPL-3.0  

Network services (Web UI, API, hosted Agent) must satisfy AGPL-3.0 where applicable. Full text: [LICENSE](LICENSE). Ownership process: [license inventory](docs/license-ownership-inventory.md).

## Disclaimer

For learning and research only. Not investment advice. Markets involve risk. Authors are not liable for losses from use of this software.
