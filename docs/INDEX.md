# 文档中心

这里是项目文档入口。README 负责项目概览和快速开始；更完整的配置、部署、功能说明和排障内容从这里进入。

## 按场景选择

| 我想要 | 先看 | 继续看 |
| --- | --- | --- |
| 快速了解项目能做什么 | [README](../README.md) | [完整配置与部署指南](full-guide.md) |
| **了解 StockPulse 的定位与能力** | [English README · Why StockPulse](../README.md#why-stockpulse) | [简体 README · 为什么选 StockPulse](README_CN.md#why-stockpulse)、[技术架构总览](architecture-overview.md) |
| 第一次把项目跑起来 | [小白客户端安装与配置](beginner-client-setup.md)（[English](beginner-client-setup_EN.md)） | [README · 定位与亮点](../README.md#why-stockpulse)、[安全基线 · 运维边界](security-baseline.md#operator-security-boundaries)、[完整配置与部署指南](full-guide.md) |
| **学习 Web / 桌面界面怎么用** | [界面操作手册](ui-manual/README.md) | 各模块分册（分析、信号、持仓等） |
| 配置大模型渠道 | [LLM 配置指南](LLM_CONFIG_GUIDE.md) | [LLM 服务商配置指南](llm-providers.md) |
| 配置推送通知 | [通知能力基线](notifications.md) | [完整配置与部署指南](full-guide.md) |
| 部署到服务器或云平台 | [部署指南](DEPLOY.md) | [云端 WebUI 部署](deploy-webui-cloud.md)、[Zeabur 部署](docker/zeabur-deployment.md) |
| **公网 / 非本机暴露前先确认安全边界** | [安全基线 · 运维安全边界（英文专节）](security-baseline.md#operator-security-boundaries) | [部署指南](DEPLOY.md)、[出站 HTTP 安全策略（英文）](security-outbound-policy.md) |
| 理解插件信任模型（非应用商店沙箱） | [插件扩展契约（英文）](plugin-extension-contract.md) | [插件开发指南](plugin-development-guide_zh.md)（[EN](plugin-development-guide.md)）、[安全基线 · 运维安全边界](security-baseline.md#operator-security-boundaries) |
| **编写或加载系统插件** | [插件开发指南](plugin-development-guide_zh.md)（[EN](plugin-development-guide.md)） | [插件扩展契约（英文）](plugin-extension-contract.md)、[examples/plugins](../examples/plugins/) |
| 使用 Bot / IM 接入 | [Bot 命令与接入](bot-command.md) | [Bot 平台配置](bot/) |
| 排查运行问题 | [FAQ](FAQ.md) | [更新日志](CHANGELOG.md) |
| 处理数据源失败或降级 | [数据源稳定性与故障处理图示](data-source-stability.md) | [英文版](data-source-stability_EN.md)、[FAQ](FAQ.md) |
| 查看日志、错误、审计与 trace 的敏感数据边界 | [敏感数据脱敏（英文）](security-sensitive-data-redaction.md) | [持久安全审计 Phase 1（英文）](security-audit.md)、[出站 HTTP 安全策略（英文）](security-outbound-policy.md) |
| 参与开发或提交 PR | [贡献指南](CONTRIBUTING.md) | [业务架构](business-architecture.md)、[技术架构总览](architecture-overview.md)、[ADR 注册表](adr/README.md)、[API 规格](architecture/api_spec.json) |

## 快速开始

| 文档 | 内容 |
| --- | --- |
| [README（英文默认）](../README.md) | 项目定位、差异化、核心能力、快速开始（GitHub 首页） |
| [README（简体中文）](README_CN.md) | 同上中文版 |
| [小白客户端安装与配置](beginner-client-setup.md) | 面向不会代码用户的客户端下载、Anspire Open / AIHubMix 模型配置、新闻源配置和常见问题；[English](beginner-client-setup_EN.md) |
| [界面操作手册](ui-manual/README.md) | Web / 桌面分模块界面用法（不含部署）；[English](ui-manual/README_EN.md) |
| [完整配置与部署指南](full-guide.md) | 环境准备、运行方式、配置说明、部署路径和常见问题 |
| [FAQ](FAQ.md) | 常见配置、模型、通知、部署和运行问题 |
| [持久安全审计 Phase 1（英文）](security-audit.md) | 事件合同、代表性特权路径、管理员查询、保留、失败语义与回滚 |
| [数据源稳定性与故障处理图示](data-source-stability.md) | Tushare、TickFlow、AkShare、Efinance、YFinance、Longbridge 等已接入源的使用场景、fallback 链路和推荐配置 |
| [更新日志](CHANGELOG.md) | 版本变化、能力调整和迁移说明 |

## 配置

| 文档 | 内容 |
| --- | --- |
| [LLM 配置指南](LLM_CONFIG_GUIDE.md) | 模型服务商与连接、三层配置、Web 设置页和常见模型配置 |
| [数据源稳定性与故障处理图示](data-source-stability.md) | 市场感知的 provider 顺序、健康评分、自适应排序、熔断、stale 降级与推荐配置 |
| [LLM 服务商配置指南](llm-providers.md) | Provider 预设、Actions 映射、错误分类和诊断建议 |
| [LiteLLM YAML 示例](examples/litellm_config.example.yaml) | LiteLLM 多渠道配置示例 |
| [通知能力基线](notifications.md) | 企业微信、飞书、Telegram、Discord、Slack、邮件等通知渠道配置 |
| [Tushare 股票列表指南](TUSHARE_STOCK_LIST_GUIDE.md) | Tushare 股票列表相关配置和使用说明 |

## 使用专题

| 文档 | 内容 |
| --- | --- |
| [界面操作手册](ui-manual/README.md) | 按模块的 Web/桌面操作说明与日常工作流；翻译约定见 [TRANSLATION.md](ui-manual/TRANSLATION.md) |
| [Bot 命令与接入](bot-command.md) | Bot 命令、Webhook、平台接入和回调说明 |
| [Kronos 本地金融模型](kronos-local-model.md) | 安装依赖、显式下载权重、Web 设置与状态诊断、桌面端说明（[英文](kronos-local-model_EN.md)） |
| [Kronos K 线预测 Agent Tool（英文）](kronos-agent-tool.md) | 可选本地模型启用、注册门槛、输出契约、局限、验证与回滚 |
| [Community Intel Agent Tool（英文）](community-intel-tool.md) | Phase A 股票作用域社区情报契约、降级语义、默认目录隔离与验证 |
| [Agent Soul 行为宪章（英文）](agent-soul.md) | 版本/hash 规则、Single/Multi/Chat 装配、Soul/Persona/Skill 优先级、运行元数据与回滚 |
| [Bot 平台配置](bot/) | 飞书、钉钉、Discord 等 Bot 配置截图和补充说明 |
| [实时告警中心](alerts.md) | EventMonitor 基线、Web 规则管理、通知结果、冷却状态和 Phase 边界 |
| [定时任务 API 与执行契约（英文）](scheduled-tasks.md) | 版本化每日分析/研究任务、今日只读视图、交易日策略、运行记录、重试与 local/Docker/API 调度所有权边界 |
| [DecisionSignal 决策信号专题](decision-signals.md) | AI 建议池字段语义、API、Web 展示、告警/通知/组合风险联动、后验评估、脱敏、迁移与回滚 |
| [个人投资框架](personal-investment-framework.md) | Settings 最小编辑页、版本化 API、单股分析只读注入与报告 framework_alignment 槽位 |
| [多策略证据契约](multi-strategy-contract.md) | 多策略观点分拣、确定性合成、冲突检测、证据链隔离与报告渲染契约 |
| [组合风险指标（VaR / 相关 / 分散化）](portfolio-risk-metrics.md) | 历史法 VaR、相关矩阵、HHI/分散化得分公式与假设；`GET /api/v1/portfolio/risk-metrics` V0 边界 |
| [Skill Opinion 后验评估（英文）](skill-opinion-outcome-evaluation.md) | 个体策略样本、离线行情后验评估、样本充足度统计、迁移与 V0 边界 |
| [资讯 / 情报源](intelligence-sources.md) | RSS/Atom 合规资讯源配置、测试、拉取、去重、存储、查询与安全边界 |
| [分析上下文包契约、运行态消费与可见性](analysis-context-pack.md) | AnalysisContextPack 首版范围、字段质量状态、P1/P2 内部契约、P3 Prompt 摘要消费、P4 历史/API/Web 低敏可见性、P5 数据质量评分、P6 迁移回滚与源码锚点；完整指南补充 #1386 阶段感知分析、迁移与回滚入口 |
| [图片识别 Prompt](image-extract-prompt.md) | 图片识别股票信息的 Prompt 与使用边界 |
| [OpenClaw Skill 集成](openclaw-skill-integration.md) | OpenClaw / Skill 外部集成说明 |

## 部署与打包

| 文档 | 内容 |
| --- | --- |
| [部署指南](DEPLOY.md) | 服务器部署、Docker、systemd、Supervisor 等部署方式 |
| [云端 WebUI 部署](deploy-webui-cloud.md) | 云服务器访问 WebUI 的部署说明 |
| [Zeabur 部署](docker/zeabur-deployment.md) | Zeabur 平台部署说明 |
| [桌面端打包说明](desktop-package.md)（[EN](desktop-package_EN.md)） | Electron 桌面端首次启动、本地模型与打包说明 |

## 参考与开发

| 文档 | 内容 |
| --- | --- |
| [业务架构](business-architecture.md) | 利益相关者、业务能力、结果与从证据获取到通知的价值流 |
| [技术架构总览](architecture-overview.md) | 当前组件、入口、所有权边界、进程模式、缓存/fallback 旁路与八阶段分析数据流 |
| [Foundation Pipeline 与 Product Layer](foundation-product-architecture.md) | 双轨职责、交互边界、贡献归属、上游移植与许可证来源规则 |
| [上游一致性检查](upstream-parity_CN.md) | 每周漂移报告、有意分叉路径白名单、`Ported-from` trailer 与分诊流程（[English](upstream-parity.md)） |
| [ADR 注册表与流程](adr/README.md) | 架构决策编号、状态、模板、重大 PR 考量规则与历史决策入口 |
| [API 规格](architecture/api_spec.json) | FastAPI OpenAPI 规格产物 |
| [OpenAPI Web 类型与运行时校验（英文）](openapi-web-types.md) | 从 OpenAPI 生成 Web 类型、CI 漂移门禁与 stocks 运行时校验试点 |
| [贡献指南](CONTRIBUTING.md) | Issue、PR、测试、文档同步和协作要求 |
| [离线测试门禁（超时、覆盖率下限、marker）](testing-ci-gate.md) | 单测超时、faulthandler、实测覆盖率下限、严格 marker，以及手动 benchmark 说明（英文专题；中英流程一致） |
| [Import-cycle ratchet（英文）](import-cycle-ratchet.md) | 包级双向 import 对 shrink-only 门禁、失败读法与合法改 baseline 路径（ADR-010） |
| [Config-access ratchet（英文）](config-access-ratchet.md) | 生产路径 bare `get_config()` shrink-only 门禁、注入 / composition-root 优先路径与 baseline 合法变更说明（ADR-011 / issue #625） |
| [离线分析质量面板（英文）](analysis-quality-panel.md) | 固定面板离线信任夹具、扩展方式与非主张范围（#617 Phase A） |
| [插件开发指南](plugin-development-guide_zh.md) | 六个扩展点的统一入口：是什么/为什么、信任模型、10 分钟 quickstart、官方示例与专题链接（[English](plugin-development-guide.md)） |
| [Data Provider 插件作者指南（英文）](data-provider-plugin-authoring.md) | 可加载示例、manifest、`PLUGINS_DIR`、生命周期诊断、版本兼容、信任模型与路由边界 |
| [Analysis Strategy 插件作者指南（英文）](analysis-strategy-plugin-authoring.md) | 声明式优先边界、`Skill` 注册字段、catalog 优先级、生命周期、诊断、测试与信任模型 |
| [供应链维护策略](supply-chain-maintenance.md) | 依赖与 GitHub Actions 的固定、权限、更新、例外、验证和回滚契约（英文） |
| [Web UI 基础控件契约](web-ui-foundation.md) | Button、IconButton、Input、Field、Textarea 的语义、尺寸、命中区、守卫和迁移边界 |
| [导航信息架构提案](navigation-ia-proposal_zh.md) | 路由/导航现状审计、遗留重定向、孤儿项与 #368 目标选项（**需要决策**；[English](navigation-ia-proposal.md)） |
| [多语言金融术语指导](financial-terminology-guide.md) | 十语言 UI 金融术语单一治理源：语义边界、术语表、已知译文漂移、风险表达、格式化与审查流程 |
| [高风险 i18n 语义审计](high-risk-i18n-audit.md) | 交易动作、风险、认证、Credential、错误与免责声明的来源、审查状态、code/display 边界和机器快照 |
| [Web 国际化开发约定](web-i18n.md) | 界面语言与报告语言边界、翻译文件结构、错误/格式化、Overlay 与验证 |

## 多语言

| 文档 | 内容 |
| --- | --- |
| [英文文档索引](INDEX_EN.md) | English documentation index |
| [English README](../README.md) | English project homepage (repository root) |
| [简体中文 README](README_CN.md) | Chinese project overview |
| [繁中 README](README_CHT.md) | 繁體中文項目概覽與快速開始 |
| [UI manual (English)](ui-manual/README_EN.md) | Modular Web/desktop UI guide |
| [推荐配置预设与配置档案](config-presets-profiles.md) | 官方预设、不含密钥的 stockpulse-profile YAML 导入导出、本地优先排序 |

- [Agent 可观测性 L0](agent-observability.md)
