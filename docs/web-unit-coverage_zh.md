# Web 单测覆盖率门禁

- 状态：`Living`
- 最近核实：2026-08-19
- 相关：[贡献指南](CONTRIBUTING.md)、[离线测试门禁](testing-ci-gate.md)、`apps/dsa-web/vitest.config.ts`、`apps/dsa-web/scripts/web-coverage-baseline.json`

英文正文：[web-unit-coverage.md](web-unit-coverage.md)。中英流程一致；阈值、命令与排除项以英文文档和仓库内 JSON 为准。

## 目的

`apps/dsa-web` 的 Vitest 单测现在有**实测**的 v8 覆盖率下限。此前 `npm run test` 只证明测试通过，不能阻止覆盖率回退。下限来自对 `src/` 的真实测量，排除项仅覆盖生成物、开发专用资产和不可单测的数据文件。

这与后端 `scripts/coverage_floor_baseline.json` 覆盖率下限相互独立。

## 本地复现

```bash
cd apps/dsa-web
npm ci
# 默认本地循环：不含覆盖率
npm run test
# 与 web-gate 相同：同一套单测加上覆盖率下限
npm run test:coverage
```

`npm run test:coverage` 即 `vitest run --coverage`。CI 只跑这一次单测，不要再并行加一次 `npm run test`。

可选本地 HTML 报告：

```bash
cd apps/dsa-web
npx vitest run --coverage --coverage.reporter=html
```

报告写到已 gitignore 的 `apps/dsa-web/coverage/`。

## 测量范围

| 设置 | 值 | 原因 |
| --- | --- | --- |
| Provider | `@vitest/coverage-v8` `4.1.0`（与锁定的 `vitest@4.1.0` 对齐） | Vitest 支持的默认 provider |
| `all` | `true` | 未测文件计 0%，下限诚实 |
| Include | `src/**/*.{ts,tsx}` | 仅产品 TypeScript |
| 阈值 | `scripts/web-coverage-baseline.json` 中的整数 | 每项为 `floor(实测百分比 - epsilon)` |

在 `origin/main` `e441a0e8b` 上的初次测量（653 个产品文件，`all: true`）：

| 指标 | 实测 | 下限（`epsilon=1`） |
| --- | --- | --- |
| Lines | 86.46% | 85 |
| Statements | 85.09% | 84 |
| Functions | 83.32% | 82 |
| Branches | 71.45% | 70 |

### 允许的排除项

Vitest 4 的 `configDefaults.coverage.exclude` 为空，因此 baseline 把每一项额外忽略都写清楚：

| 模式 | 原因 |
| --- | --- |
| `src/types/api.generated.ts` | 生成的 OpenAPI 快照 |
| `src/dev/**` | 本地/开发 mock 与 annotator stub |
| `src/playground/**` | 开发 Playground，不是上线路由 |
| `src/locales/**` | 翻译字典（结构由 `npm run test:i18n` 门禁） |
| `src/i18n/translations/**` | `i18n:resources` 生成的语言包 |
| `src/assets/**` | 无执行逻辑的静态资源 |
| `src/**/__tests__/**` | 单测文件与 helper |
| `src/**/*.test.*` / `src/**/*.spec.*` | 就近单测 |
| `src/test-utils/**` | 测试夹具 helper |
| `src/setupTests.ts` | Vitest setup 文件 |

不要为了抬高数字而排除 pages、components、hooks、API client 或 store。

## 棘轮策略

1. 在与 `origin/main` 等价的单测集上运行 `npm run test:coverage`。
2. 从 `coverage/coverage-summary.json` 的 `total.{lines,functions,statements,branches}.pct` 记录 `measured`。
3. 每项阈值设为 `Math.floor(measured - epsilonPercent)`，其中 `epsilonPercent = 1`。
4. 覆盖率上升后，在干净复测后再提高阈值。
5. 不要为了掩盖回退而降低阈值。若正当产品变更导致覆盖率下降，重新测量，在 PR 中说明原因，并把更低下限当作审查项。

1 个百分点的 epsilon 用于吸收 v8 取整和插桩噪声，不是删除测试的许可。

## CI 接线

`web-gate` 在前端路径变更时用 `npm run test:coverage` 替换 `npm run test`。覆盖率插桩会让扫描全量源码的 glob/AST 守卫变慢，因此 `vitest.config.ts` **仅在**存在 `--coverage` 时把 `testTimeout` 提到 30 秒。默认 `npm run test` 仍是 5 秒。

Testing Library 的 `findBy` / `waitFor` **不会**继承 Vitest `testTimeout`。`vitest.config.ts` 在主进程（argv 可信）检测 `--coverage`，并通过 `test.env` 向 worker 注入 `WEB_VITEST_COVERAGE=1`。`src/setupTests.ts` 读取该标志，而不是 worker 的 `process.argv`（Vitest forks 下 argv 不含 `--coverage`），再把 `asyncUtilTimeout` 设为 10 秒。本地快速循环仍保持 1 秒默认值。`React.lazy` 报告面板（例如 `ReportSummary` 中的 `ReportDiagnostics`）在 chunk 解析完成前不会出现；测试必须把这些节点纳入就绪条件，而不能只等资讯区出现后再短等。超时策略集中在 `src/test-utils/coverageTimeouts.ts`。
