# 竞品格局：本地优先金融 AI 同类项目

- 状态：`Living`（持续维护）
- 信息时点：**2026-08-12**（星标数与公开竞品主张快照来自 GitHub API / 公开 README）
- 范围：相对 [#799](https://github.com/SiinXu/stock-pulse-ai/issues/799) / [#1063](https://github.com/SiinXu/stock-pulse-ai/issues/1063) 点名对象的诚实外部定位
- English: [competitive-landscape.md](competitive-landscape.md)

本文帮助外部用户做有意识的选型，帮助贡献者优先补真实短板，并禁止营销式夸大。**不是**持续竞品监控流程，也**不**为「赢过别人」而虚构功能。

**表述规则：** 优先使用「投资研究工作台」表述，避免荐股服务话术。输出仅供研究学习，不构成受监管投顾意见。

首页已有产品叙事：[README · 为什么选 StockPulse](../README.md#why-stockpulse) / [简体 README](README_CN.md#why-stockpulse)。上游分叉策略见 [Foundation Pipeline And Product Layer](foundation-product-architecture.md)、[上游一致性检查](upstream-parity_CN.md)。主张卫生跟踪：[#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008)、[#1056](https://github.com/SiinXu/stock-pulse-ai/issues/1056)。

---

## 如何阅读本文

| 标签 | 含义 |
| --- | --- |
| **已交付 (Shipped)** | 在 StockPulse `main` 上可触达，有文档或 UI 入口，而非仅 Playground / 仅接线 |
| **默认关闭 (Default-off)** | 已交付但需显式配置或 opt-in；不得宣传为始终开启 |
| **部分可达 (Partial)** | 后端或部分 UI 存在，不能诚实写成完整产品面（[#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008)、[#1056](https://github.com/SiinXu/stock-pulse-ai/issues/1056)） |
| **规划 / 缺口 (Planned / gap)** | 由 Issue 跟踪；不是当前差异化主张 |
| **竞品强项 (Peer strength)** | 对方做得更好；StockPulse 可不刻意复制 |

下方星标数为 **2026-08-12 前后的人气近似信号**，不是质量排名。

---

## StockPulse 定位（一段话）

StockPulse 是面向多市场权益（A 股 / 港股 / 美股 / 日股 / 韩股 / 台股及相关标的）的**本地优先投资研究工作台**：多源行情 → 技术与资讯上下文 → LLM / 多 Agent 分析 → **分层**报告 → 可选通知。它是 [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) 的独立维护分叉（上游相关部分 **MIT**；StockPulse 新增与大幅修改部分 **AGPL-3.0**）。优化目标是**可审计的风险控制**、**默认拒绝的 Agent 工具面**、**诚实的报告结构**，以及**运维者自持**的部署形态（CLI、Docker、Web、桌面、GitHub Actions）——不是多租户 SaaS，也不是黑盒荐股服务。

---

## 竞品快照（#799 点名对象）

| 对象 | 约略星标 (2026-08-12) | 公开入口 | 竞品核心强项 | 相对 StockPulse |
| --- | ---: | --- | --- | --- |
| **上游 `daily_stock_analysis`** | ~62.5k | [ZhuLinsen/daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis) | 零成本 GitHub Actions 日更推送；fork 即安装的社区路径 | 共享基础血缘；StockPulse 在治理、分层报告、ToolSurface、插件等方向分化——见 [相对上游](#相对上游-daily_stock_analysis) |
| **go-stock** | ~7.2k | [ArvinLovegood/go-stock](https://github.com/ArvinLovegood/go-stock) | 成熟中文**桌面优先**打包；数据本地留存；多 LLM；Windows 向快速发版 | StockPulse 有 Web + Electron，但**桌面首启 / 一键安装仍落后**（[#798](https://github.com/SiinXu/stock-pulse-ai/issues/798)） |
| **FinRobot（含 Desktop）** | 平台约 ~7.8k | [AI4Finance-Foundation/FinRobot](https://github.com/AI4Finance-Foundation/FinRobot)；[Desktop 发布](https://github.com/AI4Finance-Foundation/FinRobot/releases/tag/desktop-v0.1.0) | 股权研究工作流、多 Agent 研究管线、**代码计算估值** + LLM 叙述、IC 风格备忘（Desktop v0.1.0 公开说明为 macOS aarch64） | StockPulse 估值 / 研究备忘深度更浅；委员会与估值路径存在但多为**默认关闭 / 有界**——勿宣称达到 FinRobot 级研究备忘 |
| **TradingAgents（及中文生态分叉）** | 核心约 ~97.7k；中文生态体量大 | [TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) | 多 Agent 辩论、角色分工、交易框架叙事 | StockPulse 有可选委员会 / Persona / Critic（**默认关闭**）；流程可视化与完整辩论 UX 相对专业框架仍是产品缺口（[#545](https://github.com/SiinXu/stock-pulse-ai/issues/545) 已交付 V1 模式；可视化仍有限） |
| **StockAI / OpenCandle 一类** | 碎片化；例如 [Kahtaf/OpenCandle](https://github.com/Kahtaf/OpenCandle) 约数十星 | 多个同名或相近小仓库 | 干净的本地 / 终端研究体验，或视觉化 / 多分析师侧重（视具体项目） | 按**品类**理解，不当作单一产品；未交付的「分享卡片 / 终端打磨」勿夸大 |

> Issue #799 中的 **Argus-style** 指与 TradingAgents 同设计家族的*角色辩论 / 委员会*多 Agent 系统，并非单一权威仓库。相关主张指流程 UX（角色、辩论、否决），而非某一固定产品名。

---

## 维度对照表

StockPulse 状态为 2026-08-12 诚实标注。竞品单元格概括公开定位，不是对竞品代码库的完整审计。

| 维度 | StockPulse | 上游 DSA | go-stock | FinRobot Desktop | TradingAgents 一类 |
| --- | --- | --- | --- | --- | --- |
| 主形态 | CLI + FastAPI Web + Electron 桌面 | CLI + Actions + WebUI 血缘 | 桌面优先（Wails） | 原生桌面研究驾驶舱（公开说明为 Tauri 栈） | 框架 / 库 / 研究管线 |
| 本地优先与运维可控 | **已交付**（本机绑定、本地模型、可选 local-only） | Actions 与本地选项均强 | 桌面本地留存强 | 桌面本地应用 | 视部署而定 |
| 多市场数据与降级 | **已交付**（多 provider、健康/降级文档） | 共享强血缘 | A/港/美本地侧重 | 研究数据源（Desktop 叙事偏美股研究） | 视分叉而定 |
| 报告信任 UX（事实/缺口/推断/风险/免责） | **已交付**分层报告 | 决策看板血缘 | AI 分析输出 | 可追溯多章节研究 / IC 备忘（竞品主张） | 更偏 Agent 辩论记录 |
| 默认拒绝 Agent 工具（ToolSurface） | **已交付** | 非 StockPulse 式治理亮点 | 多 LLM 工具；威胁模型不同 | 多 Agent 平台；产品边界不同 | 工具型 Agent；框架各异 |
| HITL 高风险门控 | **已交付，默认关闭** | 非产品亮点 | 非产品亮点 | 研究工作流，非同类审批产品 | 风险 Agent / 否决模式（框架层） |
| 个人投资框架注入 | **已交付**（版本化 API + 报告对齐槽；更深编辑器**规划中**） | 无对等物 | 无对等物 | 估值 / IC 叙事更深 | 角色提示词，非同类产品对象 |
| 可信插件契约（六扩展点） | **已交付**（非应用商店） | 模型不同 | 应用中心扩展 | 平台扩展性 | 代码级组合 |
| 本地 Model Pack（版本化 GGUF） | **已交付** | 可本地模型；Pack 产品为 StockPulse 侧 | Ollama / LMStudio 等 | 依发布形态的本地/桌面栈 | 自备 LLM |
| 零配置 / 小白首次成功 | **已交付**（本地 Ollama 检测 + 样例路径） | Actions「fork = 安装」极强 | 安装包 / 绿色版 EXE 强 | DMG 首启（macOS aarch64） | 偏开发者 |
| 桌面打包成熟度 | 相对 go-stock / FinRobot Desktop **部分/缺口**（[#798](https://github.com/SiinXu/stock-pulse-ai/issues/798)） | 次要 | **竞品强项** | **竞品强项**（OS 范围有限） | 不适用 |
| 多 Agent 流程可视化 | **部分**（委员会默认关闭；流程剧场有限） | 血缘中有可选多 Agent | 更轻量的 AI 辅助 | 研究管线叙事强 | **竞品强项** |
| 社区 / 星标 | 很小 | **竞品强项** | 中文桌面社区大 | AI4Finance 品牌 | 极大 |

---

## StockPulse 差异点（应强调什么）

只主张 **已交付** 或明确标注 **默认关闭** 的能力。链到文档；不要没有产品面的形容词堆砌。

### 1. 研究工作台，而非荐股神谕 — **已交付**

- 首页与文档以工作台定位，并写明**非承诺**（非多租户 SaaS、非受监管投顾、免费源稳定性不保证）。
- 报告分层区分 **事实 / 缺口 / 推断 / 风险 / 框架对齐 / 免责声明**，便于核对信任边界。
- 文档：[report strata 契约](report-strata-contract_EN.md)、[为什么选 StockPulse](README_CN.md#why-stockpulse)。

### 2. Agent 与控制面治理 — **已交付**（多数默认关闭）

| 能力 | 状态 | 文档 / Issue |
| --- | --- | --- |
| 严格 Agent **ToolSurface**（默认拒绝、授权、股票范围、出站 URL 策略） | 已交付 | [安全基线](security-baseline.md) |
| 高风险路径 HITL 审批 | 已交付，默认关闭 | [人工审批](human-approvals.md) |
| 特权路径持久安全审计 | 已交付 | [安全审计](security-audit_zh.md) |
| Agent Soul + 可选 Persona / 委员会 | 已交付，委员会默认关闭 | [agent-soul](agent-soul.md)、[投资委员会模式](investment-committee-mode.md)（#545） |
| 多 Agent 决策前有界 Critic | 已交付，默认关闭 | CHANGELOG / Agent 文档 |

### 3. 扩展但不假装插件商店 — **已交付**

- 可信进程插件（策略、模板、通知渠道、事件钩子、数据源等）。
- 明确信任模型：插件与进程同权——**禁止**把不可信第三方包当「应用」加载。
- 文档：[插件扩展契约](plugin-extension-contract.md)。

### 4. 本地模型产品化 — **已交付**

- Ollama 目录路径 + **版本化 Model Pack** GGUF 导入（Web + 桌面）与完整性校验。
- 文档：[model-packs](model-packs.md)、[local-model-catalog](local-model-catalog.md)。

### 5. 配置与主张卫生 — **方向已交付 + 持续审计**

- 注册表驱动 Settings、预设/档案、零配置首次成功路径。
- 对「已合并但用户不可达」能力的主动审计（[#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008)、[#1056](https://github.com/SiinXu/stock-pulse-ai/issues/1056)）。
- 文档：[零配置首次成功](zero-config-first-run.md)、[配置预设](config-presets-profiles.md)。

### 6. 双许可证与独立维护 — **既成事实**

- 源自上游的部分保持 **MIT**；StockPulse 新增与大幅修改为 **AGPL-3.0**。
- 手动上游移植 + 一致性检查工具——不是对上游的静默换皮。
- 文档：[LICENSE](../LICENSE)、[上游一致性](upstream-parity_CN.md)、[foundation-product-architecture](foundation-product-architecture.md)。

---

## 相对上游 `daily_stock_analysis`

本节**不得与**已关闭的差异化议题 [#624](https://github.com/SiinXu/stock-pulse-ai/issues/624) 矛盾：首页已用白话回答「为什么不只用上游」。本文为贡献者与评估者提供更深一层对照。

| 主题 | 上游强项 | StockPulse 选择 |
| --- | --- | --- |
| 采用路径 | Fork + GitHub Actions 是病毒式安装 | 保留 Actions；并投入工作台 UX、治理、桌面 |
| 叙事 | 多市场日更分析 + 推送 | 同一基础血缘 + **研究工作台 / 信任 UX** 强调 |
| 许可证 | MIT | MIT（原始）+ **AGPL-3.0**（StockPulse 新增） |
| 产品治理 | 社区速度 | ToolSurface、HITL、审计、插件信任模型、报告分层 |
| 同步模型 | 上游正典 | **手动**移植 + 每周漂移报告（[上游一致性](upstream-parity_CN.md)） |

**不要主张：**「StockPulse 是上游严格超集」「报告永远更好」「与 Actions-only 用户安装摩擦相同」。星标与社区规模仍是上游优势。

历史差异化工作跟踪：[#624](https://github.com/SiinXu/stock-pulse-ai/issues/624)（首页差异化落地后关闭）。

---

## 诚实缺口（优先补；不要绕着吹）

| 缺口 | 为何影响采用 | 跟踪 |
| --- | --- | --- |
| 相对 go-stock / FinRobot Desktop 的桌面首启与一键安装 | 大量中文用户先看 EXE/DMG 再看 Web | [#798](https://github.com/SiinXu/stock-pulse-ai/issues/798) |
| 相对 FinRobot Desktop 的研究备忘 / 估值综合深度 | 股权研究用户比 IC 备忘深度与数字溯源 | 估值文档有边界；避免夸大；见 [估值模型](valuation-models.md) |
| 相对 TradingAgents 一类的多 Agent 流程可视化 | 用户把「多 Agent」等同于实时辩论 UX | 委员会模式已默认关闭交付（#545）；可视化仍有限 |
| 相对上游的社区引力 | 用户默认去 6 万+ 星仓库 | 叙事与主张卫生（#799、#1063）；不是堆功能竞赛 |
| 功能列车后的可达性诚实 | README/功能表可能超前于用户可达 UI | [#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008)、[#1056](https://github.com/SiinXu/stock-pulse-ai/issues/1056) |

格局调研中亦点名的相关议题：[#589](https://github.com/SiinXu/stock-pulse-ai/issues/589)（助手引导配置，已关）、[#796](https://github.com/SiinXu/stock-pulse-ai/issues/796)（零配置首次成功，已关）。

---

## StockPulse 明确不主张

与 README 非承诺及安全文档对齐：

1. **不是**多租户 SaaS / 登录后 RBAC 工作区隔离（[安全基线 AUTH-05](security-baseline.md)、[#230](https://github.com/SiinXu/stock-pulse-ai/issues/230)）。
2. **插件不是沙箱应用商店**——是与进程同权的可信代码。
3. **免费行情源**可无 token 运行；**稳定性不保证**。
4. **仅供研究学习**——不构成投资建议，亦非受监管投顾。
5. **默认关闭**的 Agent/治理能力不是「始终开启的多 Agent 交易」。
6. **星标 /「最强 AI 选股」**排名不是产品主张。

---

## 读者入口

| 读者 | 从这里开始 |
| --- | --- |
| 选型中的新用户 | [为什么选 StockPulse](README_CN.md#why-stockpulse) → 本文 → [FAQ](FAQ.md) |
| 要排优先级的贡献者 | 上方缺口表 + 链接 Issue |
| 要安全部署的运维者 | [安全基线](security-baseline.md)、[部署指南](DEPLOY.md) |
| 只和上游比较的人 | [相对上游](#相对上游-daily_stock_analysis) + [上游一致性](upstream-parity_CN.md) |

文档中心：[INDEX.md](INDEX.md)。

---

## 维护规则

1. 刷新星标或竞品主张时更新 **信息时点**。
2. 优先链到 **Issue 与文档**，少用含糊形容词。
3. 缺口关闭后，仅当产品面**用户可达**（非仅接线）才从「诚实缺口」挪到「差异点」。
4. 实质主张变更保持中英对等。
5. 根 README 保持**首页级**信息；深度竞品表放在本文（符合 AGENTS.md 对 README 的聚焦规则）。由 INDEX / FAQ 链入，而非扩张首页功能矩阵。
6. 范围外：营销官网、持续竞品监控机器人、仅为赢对比格而发明功能。

---

## 参考

- Issues：[#799](https://github.com/SiinXu/stock-pulse-ai/issues/799)、[#1063](https://github.com/SiinXu/stock-pulse-ai/issues/1063)、[#624](https://github.com/SiinXu/stock-pulse-ai/issues/624)、[#798](https://github.com/SiinXu/stock-pulse-ai/issues/798)、[#545](https://github.com/SiinXu/stock-pulse-ai/issues/545)、[#796](https://github.com/SiinXu/stock-pulse-ai/issues/796)、[#1008](https://github.com/SiinXu/stock-pulse-ai/issues/1008)、[#1056](https://github.com/SiinXu/stock-pulse-ai/issues/1056)
- 竞品仓库（2026-08-12）：[daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis)、[go-stock](https://github.com/ArvinLovegood/go-stock)、[FinRobot](https://github.com/AI4Finance-Foundation/FinRobot)、[TradingAgents](https://github.com/TauricResearch/TradingAgents)、[OpenCandle（品类示例）](https://github.com/Kahtaf/OpenCandle)
