# Web 运行时性能预算

Issue [#883](https://github.com/SiinXu/stock-pulse-ai/issues/883) 在既有 bundle 体积预算（PR #905 / #920）之上，为 `apps/dsa-web` 的三类运行时场景建立可复现的性能预算：

1. 长列表渲染（`HistoryList`）
2. Settings 大表单（`SettingsField` 隔离）
3. SSE 聊天流（`agentChatStore` progress 批处理）

英文版：[web-runtime-performance.md](web-runtime-performance.md)。

## 设计原则

- **不得为达标缩小测量范围**（CI 合同保持完整输入规模）。
- **不得砍功能凑数字**。
- **软门先行**：超预算在 CI 中告警，默认不阻断 Web gate，待阈值稳定后再考虑 strict。
- 结构型指标可在 CI 复现；墙钟目标用于参考硬件上手动剖析。

## 预算（权威源）

机器可读：`apps/dsa-web/scripts/runtime-performance-budget.json`。

共享常量：`apps/dsa-web/src/performance/runtimeBudgets.ts`。

| 场景 | 输入规模 | 指标 | 预算 | 依据 |
| --- | --- | --- | --- | --- |
| `history-list-virtualization` | 150 条历史 | 已挂载行 DOM 数 | ≤ 40 | 超过 100 行需虚拟化或硬分页；History 已分页但会累积。 |
| `settings-field-isolation` | 40 个字段 | 编辑一字后兄弟字段 commit 数 | 0 | 单字段编辑不得拖垮整表。 |
| `sse-progress-batching` | 60 条 progress 事件 | `progressSteps` store commit 数 | ≤ 4 | rAF 批处理保证 Stop 可点。 |

## 测量入口

```bash
cd apps/dsa-web
npm ci
npx vitest run src/performance/__tests__/runtimePerformanceContracts.test.tsx
node scripts/check-runtime-performance.mjs
node scripts/check-runtime-performance.mjs --strict   # 未来硬门
```

## 产品侧缓解（与预算同 PR）

- **HistoryList**：`useVirtualWindow` 窗口化 + `HistoryListItem` memo。
- **SettingsField**：`React.memo` + 属性相等比较。
- **SSE**：progress 事件 rAF 合批 + 聊天气泡 memo。

## Bundle 体积（单文件与聚合）

机器可读：`apps/dsa-web/scripts/bundle-size-budget.json`。

检查器：`apps/dsa-web/scripts/check-bundle-size.mjs`（生产构建后执行 `npm run build:check`）。

| 层 | 约束对象 | 防止的绕过 |
| --- | --- | --- |
| `rules` | 每个匹配的 `.js` / `.css` 资源 | 单个具名 chunk 超过 gzip 上限 |
| `aggregateRules` | 一族 glob 匹配到的资源的去重 gzip 合计 | 把一个路由/组件拆成多个更小 chunk，使每个都低于单文件上限 |

聚合规则用稳定家族 ID（`<named-rule>-family` 或 `home-watchlist-route` 这类路由前缀）索引。`match` 可以是一条 glob 或 glob 列表。同一家族内每个资源只计一次，即使多条 glob 命中同一带 hash 的文件名。家族匹配为零则失败，避免前缀被改名后静默掉出闸门。

`vendor-misc` 仍只做 first-match 残余单文件规则。它的 `assets/vendor-*.js` 若按聚合计算会把全部 vendor chunk 加总。

当前生产构建仍只产出一个产物的同模式家族继承既有具名单文件上限。当前 `main` 上的语言包已经拆成多个 `ja-*.js`（及其它语言同类文件）；这些家族使用测得的 zlib-9 合计再加 400 B。额外的路由家族（`settings-route`、`portfolio-route`、`screening-route`、`home-watchlist-route`）覆盖无法命中原具名 glob 的前缀子 chunk。不要靠抬高单文件上限来掩盖家族增长。

```bash
cd apps/dsa-web
npm run build
node scripts/check-bundle-size.mjs --print
```

检查器会打印命中资源、单文件 gzip、家族 gzip 合计，以及触发失败的预算。

## CI 软门

前端变更时 Web gate 在单元测试后运行 `check-runtime-performance.mjs`；软模式只告警、不失败。
