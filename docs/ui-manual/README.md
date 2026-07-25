# StockPulse 界面操作手册

> **范围**：Web 工作台与桌面客户端的**界面操作**。  
> **不包含**：部署、Docker、GitHub Actions、环境变量清单、服务器运维。  
> 安装与首次填 Key 见 [小白客户端安装与配置](../beginner-client-setup.md)（[English](../beginner-client-setup_EN.md)）；部署见 [完整配置与部署指南](../full-guide.md)。

你好，欢迎来到 StockPulse。

这份手册按「第一次打开软件」的读者来写：你可能还不熟 A 股 / 港股 / 美股代码，也不确定「分析」「信号」「持仓」各自是干什么的。我们会用**亲切、清楚**的语气，把**点哪里、为什么、下一步做什么**说明白；表格用来速查，正文用来陪你走通。

写作约定（给维护者也给读者）：

- 先讲人话场景，再给路径与术语。  
- 重要按钮与路由写具体；界面文案若与手册不一致，**以你屏幕上的为准**。  
- 中英分册成对维护；产品 UI 还可以有更多语言。

> 💡 **温馨提示**  
> 本产品输出仅供**学习与研究**，**不构成投资建议**。真实买卖请自行判断风险与合规要求。

## 建议阅读顺序（按阶段）

```mermaid
flowchart LR
  A[安装与填 Key] --> B[认识壳层与首页]
  B --> C[跑通第一份分析]
  C --> D[学会读报告]
  D --> E[日常 5 分钟工作流]
  E --> F[信号 / 持仓 / 回测进阶]
```

| 你现在的阶段 | 先读 | 然后 |
| --- | --- | --- |
| 还没装好 / 还没有模型 Key | [小白客户端安装](../beginner-client-setup.md)（[EN](../beginner-client-setup_EN.md)） | 本手册 01 → 02 |
| 已经能打开界面 | [01 壳层](01-shell.md)、[02 首页](02-home.md) | [03 分析工作台](03-analysis-workbench.md) |
| 已经跑出报告 | [08 阅读报告](08-reading-reports.md) | [11 日常工作流](11-daily-workflows.md) |
| 想找候选标的 | [12 发现](12-discover.md) | [03 分析工作台](03-analysis-workbench.md) |
| 想盯盘或记账 | [06 信号中心](06-signals.md)、[07 持仓](07-portfolio.md) | [09 回测](09-backtest.md) |

不必一次读完。多数人第一周只需要 **01 + 02 + 03 + 08 + 11**。

## 模块一览

| 模块 | 说明 |
| --- | --- |
| [01 壳层与全局操作](01-shell.md) | 导航、命令面板、通知铃、语言与主题 |
| [02 首页](02-home.md) | 今日焦点、待办、配置缺口提示 |
| [03 分析工作台](03-analysis-workbench.md) | 发起分析、任务进度、历史与对比 |
| [04 大盘复盘](04-market-review.md) | 触发复盘、阅读复盘历史 |
| [12 发现](12-discover.md) | AlphaSift 选股、热点题材、候选转分析（实验能力） |
| [13 个股工作区](13-stock-details.md) | `/stocks/:code` 报价与 K 线、转分析/自选/规则 |
| [14 设置字段速查](14-settings-fields.md) | 设置页字段帮助汇总表（查字典） |
| [05 问股对话](05-agent-chat.md) | Agent 多轮追问与策略选择 |
| [06 信号中心](06-signals.md) | AI 建议池、告警规则、推送历史与再评估（**不在一级侧栏**；铃铛 / 命令面板 / `/signals`） |
| [07 持仓](07-portfolio.md) | 侧栏「组合」；账户、记账、导入、风险与一键分析 |
| [08 阅读报告](08-reading-reports.md) | 个股报告阅读顺序与字段含义 |
| [09 回测](09-backtest.md) | 历史建议事后验证 |
| [10 设置](10-settings.md) | 模型、自选、通知、数据源等界面操作 |
| [11 日常工作流](11-daily-workflows.md) | 推荐用法与界面常见问题 |

## 入门术语速查

| 术语 | 一句话解释 |
| --- | --- |
| **自选股（Watchlist）** | 你关心的股票代码列表，系统会按它做批量分析或首页摘要 |
| **个股分析** | 针对**一只**股票生成研究报告（技术面、资讯、风险、建议等） |
| **大盘复盘** | 对整个市场（如 A 股）的盘面摘要，不是单只股票买卖建议 |
| **信号（Decision Signal）** | 系统从分析报告里提炼出的、可查询的「建议资产」，方便事后核对 |
| **策略 / Skill** | 可选的分析风格包（例如更偏趋势或更偏质量），不选则用默认 |
| **支撑 / 压力** | 价格下方可能被买盘托住的区域叫支撑；上方可能遇卖压的区域叫压力 |
| **止损** | 预先想好的「错了就认错离场」的价格或条件，用于控制亏损 |
| **界面语言 vs 报告语言** | 前者改按钮和菜单；后者改报告正文语言，二者**互不影响** |
| **组合 vs 持仓** | 侧栏导航名多为「组合」；页面标题多为「持仓」——同一模块 |
| **Agent vs 问股** | 侧栏多为「Agent」；页面标题多为「问股」——同一模块 |

更完整的金融用词治理见 [多语言金融术语指导](../financial-terminology-guide.md)。

## 语言版本

| 手册语言 | 文件 |
| --- | --- |
| 简体中文（源） | `NN-topic.md`、`README.md` |
| English | `NN-topic_EN.md`、`README_EN.md` |

- 产品界面另支持 zh-TW / ja / ko / de / es / fr / id / ms 等；**操作手册**当前以简中 + English 维护，与产品 `locales` 分开。
- 界面语言在壳层切换；读手册时请对照你当前 UI 语言下的标签。约定见 [TRANSLATION.md](TRANSLATION.md)。
- 安装上手（桌面客户端）：[小白客户端安装](../beginner-client-setup.md) · [English](../beginner-client-setup_EN.md)
- 截图 figure pack 规范与命名：[assets/README.md](assets/README.md)

## 文档维护说明（给贡献者）

- 本手册只写「怎么点界面」，不写部署与密钥运维。
- 发现界面标签与手册不一致时，以**线上界面**为准，并开文档 PR 修正。
- **每个模块应写清**：入口路径（导航 + 路由 + 深链参数）、术语表、逐步操作、使用案例、与相邻模块关系。
- **有 UI / 路由 / 文案变更的 PR**：同一变更列车内检查并更新对应 `docs/ui-manual/*` 分册与本 README 导航表；中英成对修改。
- 对照源码时优先核对：`apps/dsa-web/src/routing/routes.ts`、`components/layout/navigation.ts`、`i18n/uiText.ts`、设置 IA `settingsInformationArchitecture.ts`、选股文案 `locales/screening.ts`。
- 扩写进度：01–13 分册已覆盖全部主业务路由；03/05/06/07/10 含「深度操作」对照上千行页面实现。仍持续按 PR 增量补字段级细节；截图二进制待 [assets/README.md](assets/README.md)（#599）。

## 在线 / 本地预览（GitBook 兼容）

本目录可用 Honkit（GitBook 兼容）本地预览，说明见 [GITBOOK.md](GITBOOK.md)。

## Multi-language packs

Product UI supports 10 languages. Manual packs: [i18n/README.md](i18n/README.md).
