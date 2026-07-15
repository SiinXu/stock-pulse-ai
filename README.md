<div align="center">

# StockPulse

**AI-assisted stock research, decision reports, and portfolio workflows**

[![CI](https://github.com/SiinXu/stock-pulse-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/SiinXu/stock-pulse-ai/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![GitHub stars](https://img.shields.io/github/stars/SiinXu/stock-pulse-ai?style=social)](https://github.com/SiinXu/stock-pulse-ai/stargazers)

[Features](#features) | [Quick Start](#quick-start) | [Web and Desktop](#web-and-desktop) | [Documentation](#documentation) | [Contributing](#contributing)

English | [Simplified Chinese documentation](docs/INDEX.md) | [Traditional Chinese](docs/README_CHT.md)

</div>

> [!NOTE]
> StockPulse is developed and released as an independent project with its own product direction, user experience, CI, and release process. It began as a fork of [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) and continues to preserve its upstream MIT license and copyright notices. StockPulse is not an official upstream release.

StockPulse analyzes watchlists across A-share, Hong Kong, US, Japanese, Korean, and Taiwan markets. It combines market data, technical signals, news research, and configurable AI models to produce decision-oriented reports, then exposes the same workflow through Web, Desktop, API, bots, scheduled jobs, and notification channels.

<p align="center">
  <img src="docs/assets/readme_workspace_tour_20260510.gif" alt="StockPulse Web workspace" width="760">
</p>

## Features

| Area | What StockPulse provides |
| --- | --- |
| Decision reports | Conclusions, scores, trend assessment, entry and exit levels, risk alerts, catalysts, and action checklists |
| Multi-market data | Quotes, candles, technical indicators, news, announcements, fundamentals, and report context for six regional markets and ETFs |
| Web workspace | Manual analysis, live task progress, history, Markdown reports, strategy chat, backtests, portfolios, alerts, screening, and settings |
| Desktop app | Electron packaging around the Web workspace with the same backend and configuration contracts |
| Model access | Provider catalog, multiple connections per provider, connection-aware model routing, discovery, and fallback configuration |
| Automation | GitHub Actions, Docker, local scheduling, FastAPI, and WeChat Work, Feishu, Telegram, Discord, Slack, and email delivery |
| Import and discovery | Image, CSV/Excel, and clipboard import plus stock code, name, pinyin, and alias autocomplete |

See [market support](docs/market-support.md) for source-specific coverage and limitations.

## Quick Start

### Local development

```bash
git clone https://github.com/SiinXu/stock-pulse-ai.git
cd stock-pulse-ai

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

python main.py --serve-only
```

Open `http://127.0.0.1:8000`.

Common commands:

```bash
python main.py
python main.py --debug
python main.py --dry-run
python main.py --stocks 600519,hk00700,AAPL
python main.py --market-review
python main.py --schedule
python main.py --serve
python main.py --serve-only
```

### GitHub Actions

1. Fork this repository.
2. Open `Settings` -> `Secrets and variables` -> `Actions`.
3. Configure a watchlist with `STOCK_LIST`.
4. Configure at least one model provider and one notification channel.
5. Enable Actions and run `StockPulse Daily Analysis` manually once.

The minimum model setup can use one of `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, or an OpenAI-compatible `OPENAI_API_KEY` plus its model settings. The complete provider, search, market-data, notification, and scheduling matrix lives in the [full guide](docs/full-guide_EN.md).

### Docker

```bash
docker compose -f docker/docker-compose.yml up -d --build
```

Review the [Docker and deployment guide](docs/full-guide_EN.md) before exposing the service outside a trusted network.

## Web and Desktop

The Web app lives in `apps/dsa-web/` and the Electron wrapper lives in `apps/dsa-desktop/`.

```bash
cd apps/dsa-web
npm ci
npm run dev
```

For production checks:

```bash
cd apps/dsa-web
npm run lint
npm run test:i18n
npm run test
npm run build
```

Desktop packaging instructions are in [docs/desktop-package.md](docs/desktop-package.md).

## Architecture

The main analysis path is:

```text
market data -> technical and news research -> AI analysis -> report -> notification
```

Important entry points:

| Path | Responsibility |
| --- | --- |
| `main.py` | Analysis, scheduling, and service CLI |
| `server.py` | FastAPI service entry point |
| `src/core/` | Main workflow orchestration |
| `src/services/` | Business services |
| `src/repositories/` | Persistence boundaries |
| `data_provider/` | Market-data adapters and fallback behavior |
| `api/` | HTTP API |
| `bot/` | Bot integrations |
| `apps/dsa-web/` | React Web application |
| `apps/dsa-desktop/` | Electron desktop application |

## Documentation

- [Documentation index](docs/INDEX_EN.md)
- [Full configuration and deployment guide](docs/full-guide_EN.md)
- [LLM configuration](docs/LLM_CONFIG_GUIDE_EN.md)
- [Provider and model routing](docs/llm-providers.md)
- [Web internationalization](docs/web-i18n_EN.md)
- [OpenAPI specification](docs/architecture/api_spec.json)
- [Contributing guide](docs/CONTRIBUTING_EN.md)
- [Changelog](docs/CHANGELOG.md)

## Contributing

Read [AGENTS.md](AGENTS.md) and the [contributing guide](docs/CONTRIBUTING_EN.md) before opening a change. Pull requests should be focused, tested against the affected runtime boundaries, and written in English for all GitHub-facing content.

Bug reports and feature proposals belong in [GitHub Issues](https://github.com/SiinXu/stock-pulse-ai/issues).

## License and Upstream Attribution

StockPulse is licensed under the [MIT License](LICENSE). It retains the upstream copyright and license notices from [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis).

## Disclaimer

StockPulse is provided for research and educational use. AI-generated analysis is not investment advice. Markets involve risk; verify all data and conclusions independently and consult a licensed professional when appropriate.
