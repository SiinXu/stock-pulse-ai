# StockPulse UI User Manual

> **Scope**: How to use the **Web workbench and desktop client UI**.  
> **Out of scope**: Deployment, Docker, GitHub Actions, full environment-variable lists, server ops.  
> For install and first API key setup, see [Beginner client setup](../beginner-client-setup.md) (Chinese). For deployment, see the [Full guide (EN)](../full-guide_EN.md).

Welcome. This manual assumes you are opening StockPulse **for the first time**. You may not yet know A-share / Hong Kong / US ticker formats, or what “Analysis”, “Signals”, and “Portfolio” each mean. We will walk through them step by step.

> 💡 **Friendly reminder**  
> Output is for **learning and research only** and is **not investment advice**. Make your own risk and compliance decisions before any real trade.

## Suggested reading order

```mermaid
flowchart LR
  A[Install and API key] --> B[Shell and Home]
  B --> C[First analysis]
  C --> D[How to read a report]
  D --> E[Daily 5-minute workflow]
  E --> F[Signals / Portfolio / Backtest]
```

| Your stage | Start with | Then |
| --- | --- | --- |
| Not installed / no model key yet | [Beginner client setup](../beginner-client-setup.md) (CN) | Modules 01 → 02 |
| UI already opens | [01 Shell](01-shell_EN.md), [02 Home](02-home_EN.md) | [03 Analysis workbench](03-analysis-workbench_EN.md) |
| You already have a report | [08 Reading reports](08-reading-reports_EN.md) | [11 Daily workflows](11-daily-workflows_EN.md) |
| Alerts or bookkeeping | [06 Signals](06-signals_EN.md), [07 Portfolio](07-portfolio_EN.md) | [09 Backtest](09-backtest_EN.md) |

Most people only need **01 + 02 + 03 + 08 + 11** in the first week.

## Module index

| Module | Description |
| --- | --- |
| [01 Shell and global actions](01-shell_EN.md) | Navigation, command palette, notification bell, language and theme |
| [02 Home](02-home_EN.md) | Today focus, todos, configuration gap prompts |
| [03 Analysis workbench](03-analysis-workbench_EN.md) | Start analysis, task progress, history and compare |
| [04 Market review](04-market-review_EN.md) | Trigger review, read review history |
| [05 Agent chat](05-agent-chat_EN.md) | Multi-turn Q&A and strategy selection |
| [06 Signal center](06-signals_EN.md) | AI suggestion pool, alert rules, delivery history, outcomes |
| [07 Portfolio](07-portfolio_EN.md) | Accounts, bookkeeping, import, risk, one-click analysis |
| [08 Reading reports](08-reading-reports_EN.md) | How to read a stock report |
| [09 Backtest](09-backtest_EN.md) | Post-hoc checks on historical AI advice |
| [10 Settings](10-settings_EN.md) | Models, watchlist, notifications, data sources in the UI |
| [11 Daily workflows](11-daily-workflows_EN.md) | Recommended flows and common UI questions |

## Quick glossary

| Term | Plain meaning |
| --- | --- |
| **Watchlist** | The list of tickers you care about; used for batch analysis and summaries |
| **Single-stock analysis** | A research report for **one** symbol (technicals, news, risk, suggestion, …) |
| **Market review** | A market-wide session summary (e.g. A-shares), not a single-name trade ticket |
| **Decision signal** | A structured, queryable “advice asset” extracted from a report for later review |
| **Strategy / Skill** | An optional analysis style pack; omit to use the system default |
| **Support / resistance** | Support is a lower zone where buying interest may appear; resistance is an upper zone where selling pressure may appear |
| **Stop-loss** | A pre-planned exit price or condition to limit losses when the thesis fails |
| **UI language vs report language** | UI language changes menus and buttons; report language changes report body text. They are **independent** |

## Languages

- [简体中文](README.md)
- English (this file)

In-app UI language is separate from this documentation set. Conventions: [TRANSLATION.md](TRANSLATION.md).

**Disclaimer**: Output is for learning and research only and is not investment advice.
