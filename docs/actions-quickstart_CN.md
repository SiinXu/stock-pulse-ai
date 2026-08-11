# GitHub Actions 三步上手

[English](actions-quickstart.md) | 简体中文

本文是 fork 后用 GitHub Actions 跑日更分析的**最小路径**。不必先读部署文档里的完整 Secret 表。

名称映射以 [`.github/workflows/00-daily-analysis.yml`](../.github/workflows/00-daily-analysis.yml) 为准（Config Check 见 [`.github/workflows/config-check.yml`](../.github/workflows/config-check.yml)）。

## 你需要什么

| 名称 | 类型 | 是否必须 | 示例 / 说明 |
|------|------|----------|-------------|
| `LLM_ZHIPU_API_KEY` **或** `LLM_SILICONFLOW_API_KEY` **或** `GEMINI_API_KEY` | 仓库 **Secret** | **三选一** | 切勿把真实 Key 提交进仓库 |
| `STOCK_LIST` | 仓库 **Variable**（推荐） | 建议配置 | `600519,000001` |
| 任一通知 webhook（如 `WECHAT_WEBHOOK_URL`） | 仓库 **Secret** | 可选 | 不配 IM 也可从 Actions Artifact 下载报告 |

未配置 Tushare 等 token 型数据源时，会走内置免费行情源；免费源稳定性不保证。

---

## 第一步 — 配置一个模型 Secret（三选一）

1. Fork [SiinXu/stock-pulse-ai](https://github.com/SiinXu/stock-pulse-ai)。
2. 在 fork 仓库：**Settings** → **Secrets and variables** → **Actions** → **Secrets** → **New repository secret**。
3. 只需创建下面**其中一个**：

| Secret 名称 | 服务商 |
|-------------|--------|
| `LLM_ZHIPU_API_KEY` | 智谱 |
| `LLM_SILICONFLOW_API_KEY` | 硅基流动 |
| `GEMINI_API_KEY` | Google Gemini |

以上名称分别对应 workflow 中的 `secrets.LLM_ZHIPU_API_KEY`、`secrets.LLM_SILICONFLOW_API_KEY`、`secrets.GEMINI_API_KEY`。其它服务商（OpenAI 兼容、Anthropic、Anspire、AIHubMix 等）同样可用，见 [高级配置](#高级配置)。

---

## 第二步 — 自选股 Variable `STOCK_LIST`

1. 同一设置页，打开 **Variables** 标签 → **New repository variable**。
2. Name：`STOCK_LIST`
3. Value 示例：`600519,000001`

逗号分隔代码。多市场示例：`600519,hk00700,AAPL,2330.TW`。

日更 workflow 将 `vars.STOCK_LIST`（或 `secrets.STOCK_LIST`）写入 `STOCK_LIST_CONFIG`，再导出为运行时的 `STOCK_LIST`。**推荐**使用仓库 Variable；同名 Secret 也可。

> 说明：job 使用 `environment: STOCK_LIST` 是为了兼容旧配置（曾把配置放在同名 GitHub Environment 中）。新 fork 一般只需仓库 Variable，不必新建 Environment。

---

## 第三步 — 可选：通知 Secret

不配置任何通知渠道时，仍可在 workflow **Artifacts** 中下载报告（见 [获取报告](#获取报告)）。

若要推送到聊天软件，在仓库 Secrets 中配置**任意一个**（名称来自 `00-daily-analysis.yml`）：

| Secret 名称 | 渠道 |
|-------------|------|
| `WECHAT_WEBHOOK_URL` | 企业微信机器人 webhook |
| `FEISHU_WEBHOOK_URL` | 飞书机器人 webhook |
| `DINGTALK_WEBHOOK_URL` | 钉钉 webhook |
| `DISCORD_WEBHOOK_URL` | Discord webhook |
| `SLACK_WEBHOOK_URL` | Slack Incoming Webhook |
| `CUSTOM_WEBHOOK_URLS` | 自定义 webhook（多个用逗号分隔） |

Telegram 需要**两个** Secret：`TELEGRAM_BOT_TOKEN` 与 `TELEGRAM_CHAT_ID`（不是单一 webhook）。邮件需发件人/授权码/收件人，见部署指南。

---

## 先跑 Config Check，再跑日更分析

1. 如提示，先在 fork 上启用 **Actions**。
2. **Actions** → **Config Check** → **Run workflow**
   只校验 Secrets/Variables，不跑完整分析，也不打印 Secret 值（[#847](https://github.com/SiinXu/stock-pulse-ai/issues/847)）。
3. Config Check 通过后：**Actions** → **StockPulse Daily Analysis** → **Run workflow**
   模式：`full`（默认）、`market-only`、`stocks-only`。
   默认定时：工作日 **北京时间 18:00**（UTC `cron: '0 10 * * 1-5'`），受交易日规则与 GitHub 调度延迟影响。

运行失败或跳过时，查看该次运行的 **Job Summary** 获取可读原因说明（[#850](https://github.com/SiinXu/stock-pulse-ai/issues/850)）。

---

## 获取报告

| 方式 | 操作 |
|------|------|
| **Artifact（无需 IM）** | 打开已完成的 run → **Artifacts** → 下载 `analysis-reports-<run_number>`（约保留 30 天） |
| **通知推送** | 第三步配置的渠道收到消息 |
| **日志** | 在 Actions 运行页展开各 step |

---

## 高级配置

三步以外的选项请读现有文档，本文不展开完整环境变量列表。

| 主题 | 文档 |
|------|------|
| Actions 完整部署步骤与 Secret 总表 | [部署指南（中文）](DEPLOY.md) · [Deploy Guide (EN) — Option 4](DEPLOY_EN.md#option-4-github-actions-deployment-serverless) |
| LLM 服务商、模型、多通道路由 | [LLM 配置指南](LLM_CONFIG_GUIDE.md) · [LLM Config Guide (EN)](LLM_CONFIG_GUIDE_EN.md) · [服务商指南](llm-providers.md) |
| 本地 / Docker 安装 | [完整指南](full-guide.md) · [Full Guide (EN)](full-guide_EN.md) |
| Config Check 本地命令 | `python scripts/actions_config_check.py`（可选 `--strict-notify` / `--probe-llm`） |
| Workflow 源文件 | [`.github/workflows/00-daily-analysis.yml`](../.github/workflows/00-daily-analysis.yml) |

日更 workflow 中已接入、但**首次上手不必配置**的示例：新闻 Key（`SERPAPI_API_KEYS`、`TAVILY_API_KEYS` 等）、`TUSHARE_TOKEN`、`AIHUBMIX_KEY`、`ANSPIRE_API_KEYS`、模型覆盖（`GEMINI_MODEL`、`LLM_*_MODELS`）、通知路由（`NOTIFICATION_REPORT_CHANNELS`、`NOTIFICATION_SYSTEM_ERROR_CHANNELS`）。

---

## 相关

- [#852](https://github.com/SiinXu/stock-pulse-ai/issues/852) — 普通用户 Actions 三行预设（本文档）
- [#847](https://github.com/SiinXu/stock-pulse-ai/issues/847) — Config Check（不跑分析，只校验配置）
- [#850](https://github.com/SiinXu/stock-pulse-ai/issues/850) — 日更失败/跳过的可读 Summary 与短错误通知
