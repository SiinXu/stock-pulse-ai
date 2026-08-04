# English Documentation Index

This is the entry point for project documentation. The README covers the project overview and quick start; detailed setup, configuration, deployment, feature usage, and troubleshooting docs are linked below.

> For Chinese documentation, see [docs/INDEX.md](INDEX.md).

## Choose By Goal

| I want to | Start with | Then read |
| --- | --- | --- |
| Understand what the project does | [README (EN, root)](../README.md) | [Full Guide (EN)](full-guide_EN.md) |
| **Understand StockPulse positioning and highlights** | [README · Why StockPulse](../README.md#why-stockpulse) | [简体 README](README_CN.md#why-stockpulse), [Architecture overview](architecture-overview.md) |
| Run the project for the first time | [Beginner client setup (EN)](beginner-client-setup_EN.md) | [Why StockPulse](../README.md#why-stockpulse), [Security baseline — operator boundaries](security-baseline.md#operator-security-boundaries), [Full Guide (EN)](full-guide_EN.md), [UI User Manual](ui-manual/README_EN.md) |
| **Learn the Web / desktop UI** | [UI User Manual](ui-manual/README_EN.md) | Per-module chapters (analysis, signals, portfolio, …) |
| Configure model providers | [LLM Config Guide (EN)](LLM_CONFIG_GUIDE_EN.md) | [Local Model Catalog](local-model-catalog.md), [Provider Configuration Guide](llm-providers.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) |
| Import or publish a local GGUF model | [StockPulse Model Packs](model-packs.md) | [LLM Config Guide (EN)](LLM_CONFIG_GUIDE_EN.md) |
| Configure notifications | [Notification Baseline](notifications.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) | [Full Guide (EN)](full-guide_EN.md) |
| Deploy to a server or cloud platform | [Deploy Guide (EN)](DEPLOY_EN.md) | [Cloud WebUI Deployment](deploy-webui-cloud.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only), [Zeabur Deployment](docker/zeabur-deployment.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) |
| **Confirm security boundaries before a public or non-local bind** | [Security baseline — operator boundaries](security-baseline.md#operator-security-boundaries) | [Deploy Guide (EN)](DEPLOY_EN.md), [Outbound HTTP Policy](security-outbound-policy.md) |
| Understand the plugin trust model (not a marketplace sandbox) | [Plugin extension contract](plugin-extension-contract.md) | [Security baseline — operator boundaries](security-baseline.md#operator-security-boundaries) |
| Use Bot / IM integrations | [Bot Commands (EN)](bot-command_EN.md) | [Bot Platform Docs](bot/) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) |
| Troubleshoot runtime issues | [FAQ (EN)](FAQ_EN.md) | [Changelog](CHANGELOG.md) |
| Troubleshoot data-source failures | [Data-source Priority, Health, and Degradation](data-source-stability_EN.md) | [FAQ (EN)](FAQ_EN.md), [Chinese version](data-source-stability.md) |
| Review log/error/audit/trace secret handling | [Sensitive-Data Redaction](security-sensitive-data-redaction.md) | [Durable Security Audit Phase 1](security-audit.md), [Outbound HTTP Policy](security-outbound-policy.md) |
| Contribute code or docs | [Contributing Guide (EN)](CONTRIBUTING_EN.md) | [Business Architecture](business-architecture.md), [Technical Architecture](architecture-overview.md), [ADR Registry](adr/README.md), [API Spec](architecture/api_spec.json) |

## Getting Started

| Document | Contents |
| --- | --- |
| [README (EN, root)](../README.md) | Project homepage: positioning, differentiators, features, quick start |
| [README (简体中文)](README_CN.md) | Chinese project overview |
| [Beginner client setup (EN)](beginner-client-setup_EN.md) | Download desktop client, Anspire/AIHubMix keys, watchlist, first analysis; [中文](beginner-client-setup.md) |
| [UI User Manual](ui-manual/README_EN.md) | Modular Web/desktop UI usage (no deployment); [简体中文](ui-manual/README.md) |
| [Full Guide (EN)](full-guide_EN.md) | Environment setup, run modes, configuration, deployment paths, and common issues |
| [FAQ (EN)](FAQ_EN.md) | Common configuration, model, notification, deployment, and runtime issues |
| [Data-source Priority, Health, and Degradation](data-source-stability_EN.md) | Static/realtime priority, health scoring, adaptive ordering, fallback chains, deployment profiles, and troubleshooting |
| [Sensitive-Data Redaction](security-sensitive-data-redaction.md) | Redaction coverage, Agent trace behavior, debug guarantees, limits, incident response, and rollback |
| [Durable Security Audit Phase 1](security-audit.md) | Event schema, representative privileged paths, administrator query access, retention, failure semantics, and rollback |
| [Changelog](CHANGELOG.md) | Release notes, capability changes, and migration notes |

## Configuration

| Document | Contents |
| --- | --- |
| [LLM Config Guide (EN)](LLM_CONFIG_GUIDE_EN.md) | Model providers and connections, three-tier configuration, Web settings, and common model setup |
| [Local Model Catalog](local-model-catalog.md) | Curated local models, verified artifacts and licenses, RAM tiers, distribution status, and Ollama packaging guidance |
| [StockPulse Model Packs](model-packs.md) | Versioned GGUF pack format, offline import, validation failures, build tooling, and release limits |
| [Data-source Priority, Health, and Degradation](data-source-stability_EN.md) | Market-aware provider order, bounded health learning, circuit control, stale degradation, and production/zero-cost profiles |
| [Provider Configuration Guide](llm-providers.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) | Provider presets, GitHub Actions mapping, error categories, and diagnostics |
| [LiteLLM YAML Example](examples/litellm_config.example.yaml) | Example LiteLLM multi-provider configuration |
| [Notification Baseline](notifications.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) | WeChat Work, Feishu, Telegram, Discord, Slack, Email, and other notification channels |
| [Tushare Stock List Guide](TUSHARE_STOCK_LIST_GUIDE.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) | Tushare stock-list configuration and usage notes |

## Usage Topics

| Document | Contents |
| --- | --- |
| [UI User Manual](ui-manual/README_EN.md) | Module-by-module Web/desktop operations and daily workflows; see [TRANSLATION.md](ui-manual/TRANSLATION.md) |
| [Bot Commands (EN)](bot-command_EN.md) | Bot commands, webhooks, platform integration, and callback behavior |
| [Kronos K-line Forecasting Agent Tool](kronos-agent-tool.md) | Optional local model setup, registration gates, output contract, limitations, verification, and rollback |
| [Community Intelligence Agent Tool](community-intel-tool.md) | Default-off Phase A stock-scoped evidence contract, public citation boundary, deterministic degradation, and verification |
| [Agent Soul Contract](agent-soul.md) | Version/hash rules, Single/Multi/Chat assembly, Soul/Persona/Skill precedence, run metadata, and rollback |
| [Bot Platform Docs](bot/) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) | Feishu, DingTalk, Discord, and related Bot configuration screenshots and notes |
| [Real-Time Alert Center](alerts.md) <sub><sub>![P4 Badge](https://img.shields.io/badge/P4-yellow?style=flat)</sub></sub> (Chinese-only) | EventMonitor baseline, Web rule management, notification attempts, cooldown state, and phase boundaries |
| [Scheduled Tasks](scheduled-tasks.md) | Versioned daily analysis/research tasks, a read-only today view, trading-day policy, durable run records, bounded retry, and local/Docker/API ownership |
| [DecisionSignal Topic](decision-signals.md) <sub><sub>![P7 Badge](https://img.shields.io/badge/P7-orange?style=flat)</sub></sub> (Chinese-only) | AI signal fields, API, Web display, alert/notification/portfolio-risk linkage, outcome evaluation, redaction, migration, and rollback |
| [Personal Investment Framework](personal-investment-framework_EN.md) | Minimal Settings editor, versioned API, single-stock read-only injection, and report framework_alignment slot |
| [Analysis Context Pack Contract, Runtime Consumption, And Visibility](analysis-context-pack.md) <sub><sub>![P6 Badge](https://img.shields.io/badge/P6-orange?style=flat)</sub></sub> (Chinese-only) | AnalysisContextPack first-scope boundaries, field quality states, P1/P2 internal contracts, P3 prompt-summary consumption, P4 history/API/Web low-sensitivity visibility, P5 data-quality scoring, and P6 migration/rollback notes, plus source anchors; the full guide adds #1386 market-phase analysis, migration, and rollback entry points |
| [Image Extraction Prompt](image-extract-prompt.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) | Prompt and boundaries for extracting stock information from images |
| [OpenClaw Skill Integration](openclaw-skill-integration.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) | OpenClaw / Skill external integration notes |

## Deployment And Packaging

| Document | Contents |
| --- | --- |
| [Deploy Guide (EN)](DEPLOY_EN.md) | Server deployment, Docker, systemd, Supervisor, and related options |
| [Cloud WebUI Deployment](deploy-webui-cloud.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) | Cloud server WebUI access and deployment notes |
| [Zeabur Deployment](docker/zeabur-deployment.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) | Zeabur platform deployment |
| [Desktop Packaging](desktop-package.md) <sub><sub>![P2 Badge](https://img.shields.io/badge/P2-yellow?style=flat)</sub></sub> (Chinese-only) | Electron desktop app and Web artifact packaging |

## Reference And Development

| Document | Contents |
| --- | --- |
| [Business Architecture](business-architecture.md) | Stakeholders, business capabilities, outcomes, and the value flow from evidence acquisition to notification |
| [Technical Architecture](architecture-overview.md) | Current components, entrypoints, ownership boundaries, process modes, cache/fallback branches, and the eight-stage analysis data flow |
| [Foundation Pipeline And Product Layer](foundation-product-architecture.md) | Responsibility tracks, interaction boundaries, contribution placement, upstream porting, and license provenance |
| [ADR Registry And Process](adr/README.md) | Decision numbering, statuses, template, significant-PR consideration, and historical records |
| [API Spec](architecture/api_spec.json) | FastAPI OpenAPI artifact |
| [OpenAPI Web Types And Runtime Validation](openapi-web-types.md) | Generated web API types, CI drift gate, and stocks runtime-validation pilot |
| [Contributing Guide (EN)](CONTRIBUTING_EN.md) | Issues, pull requests, tests, documentation sync, and collaboration expectations |
| [Offline Analysis Quality Panel](analysis-quality-panel.md) | Fixed-panel offline trust fixtures, extension guide, and non-claims (#617 Phase A) |
| [Data Provider Plugin Authoring Guide](data-provider-plugin-authoring.md) | Loadable example, manifest, `PLUGINS_DIR`, lifecycle diagnostics, compatibility, trust, and routing boundaries |
| [Analysis Strategy Plugin Authoring Guide](analysis-strategy-plugin-authoring.md) | Declarative-first boundary, `Skill` registration fields, catalog precedence, lifecycle, diagnostics, tests, and trust |
| [Supply-Chain Maintenance](supply-chain-maintenance.md) | Dependency and GitHub Actions pinning, permissions, updates, exceptions, validation, and rollback policy |
| [Web UI Foundation Contract](web-ui-foundation.md) | Semantic controls, visible sizes, coarse-pointer targets, guardrails, and migration ownership |
| [Multilingual Financial Terminology Guide](financial-terminology-guide.md) | Product semantics and ten-language candidate terminology (guide body in Simplified Chinese) |
| [High-risk i18n Semantic Audit](high-risk-i18n-audit.md) | Sources, review status, code/display boundaries, and machine snapshots for financial and security-sensitive copy |
| [Web Internationalization Conventions](web-i18n_EN.md) | UI/report language boundaries, resource structure, errors, formatting, and validation |

## Languages

| Document | Contents |
| --- | --- |
| [Chinese Documentation Index](INDEX.md) | Chinese documentation entry point |
| [Traditional Chinese README](README_CHT.md) | Traditional Chinese project overview and quick start |
| [UI manual (Chinese)](ui-manual/README.md) | Modular Web/desktop UI guide |

## China-Market Glossary

| Term | Meaning |
| --- | --- |
| **A-shares** | Stocks listed on the Shanghai or Shenzhen stock exchanges, denominated in CNY |
| **Northbound capital flow** | Net buy/sell flow from foreign investors through Stock Connect programs |
| **Dragon-Tiger List** | Daily SSE/SZSE disclosure of heavily traded stocks and top trading seats |
| **Chip distribution** | Cost-basis distribution of outstanding shares, often used to estimate support and resistance |
| **Tushare** | Chinese financial data API that requires a token |
| **AkShare** | Open-source Python market data library |
| **Baostock** | Free Python SDK for historical A-share data |
| **WeChat Work** | Tencent enterprise messaging platform with webhook notifications |
| **Feishu** | ByteDance enterprise collaboration platform with webhook notifications |
| **PushPlus / ServerChan** | Chinese mobile push notification services |
