# Web 运行时性能预算

Issue [#883](https://github.com/SiinXu/stock-pulse-ai/issues/883) 在既有 bundle 体积预算（PR #905 / #920 / T20）之上，为 `apps/dsa-web` 的十个已审计运行时表面建立可复现的性能预算，并保留现已合入主干的 T16 共享 `DataTable` 虚拟化合同。

英文版：[web-runtime-performance.md](web-runtime-performance.md)。

## 设计原则

- **不得为达标缩小测量范围**（CI 合同保持完整输入规模）。
- **不得砍功能凑数字**。
- **不得把单机墙钟速度写成阻断预算**。
- **不得用过宽余量掩盖回归**。只有在有产品证据时才上调数字。
- **网络耗时和 Desktop 空闲功耗永远不阻断**。
- 结构型指标可在 CI 复现；墙钟目标用于参考硬件上手动剖析。

## 已审计表面

Issue #883 点名十个表面。T16 把共享 `DataTable` 窗口作为第十一个实测合同，必须保留。

| 表面 | 场景 | 类型 | 门 | 为何如此 |
| --- | --- | --- | --- | --- |
| 共享 DataTable | `data-table-virtualization` | 结构 | **阻断** | T16 对兼容表 ≥ 24 行窗口化；150 行输入，挂载表体 ≤40。 |
| 历史列表 | `history-list-virtualization` | 结构 | **阻断** | 虚拟窗口可复现；150 条输入，挂载行 ≤40。 |
| 信号列表 | `signals-list-pagination` | 结构 | **阻断** | 列表模型按 20 条分页；挂载剩余全集是回归。 |
| 筛选结果 | `screening-results-mounted-rows` | 结构 | **观察** | 150 行仍全部挂载（行详情无法窗口化）。在分页或兼容窗口落地前保持诚实 WARN。 |
| Settings 表单 | `settings-field-isolation` | 结构 | **阻断** | 单字段编辑不得重绘兄弟字段（0）。 |
| SSE 进度 | `sse-progress-batching` | 结构 | **阻断** | 60 个事件不得按事件提交 `progressSteps`（≤4）。 |
| 聊天气泡 | `chat-markdown-isolation` | 结构 | **阻断** | 进度更新时既有气泡保持 DOM 身份。 |
| Home 组件 | `home-widget-slots` | 结构 | **阻断** | 默认看板保持四个独立槽位。 |
| 路由分包 | `bundle-route-split` | 外部 | **跳过** | 已由 T20 `check-bundle-size.mjs` 聚合家族阻断，不是运行时计时。 |
| Desktop 空闲 | `desktop-idle-power` | 外部 | **跳过** | Web jsdom CI 不可测，仅手动。 |
| 首屏外壳 | `first-chrome-shell` | 结构 | **阻断** | 侧栏、主区、移动端顶栏在路由 outlet 之前挂载。约 300ms 路由切换仍是手动墙钟。 |

跳过是一等的 **不可用** 结果，不是通过。缺少 `skipReason` 会失败关闭。

## 预算（权威源）

机器可读：`apps/dsa-web/scripts/runtime-performance-budget.json`。

共享常量：`apps/dsa-web/src/performance/runtimeBudgets.ts`。

| 场景 | 输入规模 | 指标 | 预算 | 方向 |
| --- | --- | --- | --- | --- |
| `data-table-virtualization` | 150 行 DataTable | 已挂载表体行 DOM 数 | 40 | 至多 |
| `history-list-virtualization` | 150 条历史 | 已挂载行 DOM 数 | 40 | 至多 |
| `signals-list-pagination` | 150 条信号 | 分页后挂载卡片数 | 20 | 至多 |
| `screening-results-mounted-rows` | 150 条候选 | 已挂载表体行 | 40 | 至多（观察） |
| `settings-field-isolation` | 40 个字段 | 编辑一字后兄弟字段 commit 数 | 0 | 至多 |
| `sse-progress-batching` | 60 条 progress 事件 | `progressSteps` store commit 数 | 4 | 至多 |
| `chat-markdown-isolation` | 8 条已完成气泡 | 进度更新时丢失身份的气泡数 | 0 | 至多 |
| `home-widget-slots` | 4 个默认组件 | 独立槽位数 | 4 | 至少 |
| `first-chrome-shell` | 占位 outlet | 外壳地标数 | 3 | 至少 |

## 测量入口

```bash
cd apps/dsa-web
npm ci
npx vitest run src/performance/__tests__/runtimePerformance*.test.tsx
npx vitest run scripts/check-runtime-performance.test.mjs
node scripts/check-runtime-performance.mjs --print --warmup 1 --repeat 3
node scripts/check-runtime-performance.mjs --strict --print
```

检查器用 `DSA_RUNTIME_PERF_REPORT` 写临时报告，按 **warmup 之后的中位数** 聚合，再按场景门比较。`--report` 读取夹具报告（反例测试用），不启动 Vitest。

## 产品侧缓解

- **DataTable**：行数 ≥ 24 时用 `useVirtualWindow` 窗口化；明细行或 `virtualization={false}` 时关闭。默认/紧凑行高 48px/36px，overscan 为 6。窗口化表头使用不透明 `bg-card`。自动窗口不测量真实行高。事件日历、选股发现、历史趋势抽屉、RiskHeatmap、组合相关性矩阵、持仓信号格、Token 用量、导入失败行、个人表现原因列表、事件提醒及其他换行/堆叠表保持全量挂载。
- **HistoryList**：`useVirtualWindow` 窗口化 + `HistoryListItem` memo。
- **信号列表**：`PAGE_SIZE` 20 硬分页。
- **SettingsField**：`React.memo` + 属性相等比较。
- **SSE**：progress 事件 rAF 合批 + 聊天气泡 memo。
- **Home**：四个独立组件槽位。
- **Shell**：侧栏、主区、移动端顶栏独立于路由 outlet。

## 抖动策略 / 诊断 / 基线更新 / 回滚

- 阻断型结构指标不允许抖动；不要靠抬预算吞方差。
- 观察型超标只 WARN；提升为阻断前需要重复 CI 中位数稳定。
- 跳过打印 `[SKIP]` 和原因；缺测量对阻断/观察场景失败关闭。
- `kind=timing` / `kind=network` 不能设 `gate=blocking`。
- CI 不重试该步骤。`--print` 输出样品列表。
- 更新基线时保持声明的输入规模；优先修产品，而不是放宽数字。
- 回滚：还原本 PR。Bundle 聚合家族独立。

`--soft` 仅供本地把阻断降为 WARN，CI 不得传 `--soft`。

Web gate 在单元测试后运行 `node scripts/check-runtime-performance.mjs --print --warmup 1 --repeat 3`。阻断失败会失败关闭 Web gate；观察只告警；跳过表示不可用。

## Bundle 体积（单文件与聚合）

机器可读：`apps/dsa-web/scripts/bundle-size-budget.json`。

检查器：`apps/dsa-web/scripts/check-bundle-size.mjs`（生产构建后执行 `npm run build:check`）。

| 层 | 约束对象 | 防止的绕过 |
| --- | --- | --- |
| `rules` | 每个匹配的 `.js` / `.css` 资源 | 单个具名 chunk 超过 gzip 上限 |
| `aggregateRules` | 一族 glob 匹配到的资源的去重 gzip 合计 | 把一个路由/组件拆成多个更小 chunk，使每个都低于单文件上限 |

聚合规则用稳定家族 ID（`<named-rule>-family` 或 `home-watchlist-route` 这类路由前缀）索引。`match` 可以是一条 glob 或 glob 列表。同一家族内每个资源只计一次，即使多条 glob 命中同一带 hash 的文件名。家族匹配为零则失败，避免前缀被改名后静默掉出闸门。

`vendor-misc` 仍只做 first-match 残余单文件规则。它的 `assets/vendor-*.js` 若按聚合计算会把全部 vendor chunk 加总。

当前生产构建仍只产出一个产物的同模式家族继承既有具名单文件上限。当前 `main` 上的语言包已经拆成多个 `ja-*.js`（及其它语言同类文件）；这些家族使用测得的 zlib-9 合计再加 400 B。额外的路由家族（`settings-route`、`portfolio-route`、`screening-route`、`home-watchlist-route`、`backtest-route`）覆盖无法命中原具名 glob 的前缀子 chunk。不要靠抬高单文件上限来掩盖家族增长。

```bash
cd apps/dsa-web
npm run build
node scripts/check-bundle-size.mjs --print
```

检查器会打印命中资源、单文件 gzip、家族 gzip 合计，以及触发失败的预算。
