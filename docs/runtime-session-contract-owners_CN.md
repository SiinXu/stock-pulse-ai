# 共享运行时 Session 契约所有权

- 状态：`Living`
- 最近核验：2026-08-23，对照 `241e7e02d`（#1055 T3 ToolSurface 栅栏读取）
- Issue：[#1055](https://github.com/SiinXu/stock-pulse-ai/issues/1055) T1 清单 + T2 标准 BoundToolSession double + T3 ToolSurface 栅栏读取
- English：[runtime-session-contract-owners.md](runtime-session-contract-owners.md)

本页是**共享运行时 session、探针与配置展示契约**的 owner 地图。目的是避免生产侧新增必填字段后，标准 test double 或公开展示 mock 仍然漏字段。

#1055 T2 把 `make_bound_tool_session` 提升为标准 double，并为漏掉 `deadline_monotonic` / `cancelled_check` 增加 fail-closed 回归。T3 在 ToolSurface 中直接读取 `context.deadline_monotonic` 与 `context.cancelled_check`，duck 缺任一属性不得变成无限栅栏。真实 `ToolAccessContext` 仍可传入 `None`（无绝对 deadline / 无取消探针）。

## 目的

近期 canary / 跨模块失败是同一模式：

1. 生产对象增加不可缺字段（`deadline_monotonic`、`is_cancel_requested`、`ANALYSIS_TASK_HTTP_CANCEL_AVAILABLE` 等）。
2. 手写 `SimpleNamespace` 或部分 `vi.mock` factory 漏掉该字段。
3. 路径选择测试仍绿，直到后续 shard、Web gate 或跨模块任务读到该字段。

本清单给出：owner 模块、生产构造点、必须同 PR 更新的测试、fail-closed 期望，以及遗留 duck 的废弃路径。

## 范围

范围内：

- Agent `BoundToolSession` / runner 完成栅栏 / ToolAccessContext
- 进程内 `TaskRunContext` 取消协议，含 #1466 已落地的 HTTP cancel 字段
- Web 分析任务 cancel 标志与 `cancelTask`
- 就绪检查消费的 generation-backend 状态载荷
- 配置注册表已文档化键 vs `.env.example`

范围外（不要在此实现）：

- Agent 整体重设计
- 新产品功能
- 批量补注册配置键（[#1023](https://github.com/SiinXu/stock-pulse-ai/issues/1023)）
- 任务感知路由（[#204](https://github.com/SiinXu/stock-pulse-ai/issues/204)）
- 独立 Desktop 分析客户端（不存在；桌面端嵌入同一 Web bundle）
- 削弱超时、脱敏或 ToolSurface 默认拒绝

## 如何改清单中的契约

对下表任一行新增、重命名或改为必填字段时，**同一 PR** 必须：

1. 更新该行标明的生产构造器 / 冻结 dataclass / 生成 OpenAPI 表面。
2. 更新所有 **must-update-together** 测试及其标准 helper。
3. 保持 fail-closed：缺必填字段应抛错、拒绝或标记 `failed`。不要把必填字段 `getattr(..., False)` / `getattr(..., None)` 成静默无限运行。
4. 优先小契约 PR。不要把无关的 Agent、Settings 或研究路径重写塞进同一次变更。
5. 若 owner、构造点或成对测试变化，同步更新本清单的中英两份。

## Fail-closed 基线

| 层 | 契约缺失或损坏时的要求 |
| --- | --- |
| Native 工具分发 | `src/agent/runner_parts/tools.py` 直接读 `tool_session.deadline_monotonic`。duck 缺属性应 `AttributeError`，不得变成无界等待。 |
| 分析 runner 取消 | `TaskRunContext.is_cancel_requested` 是冻结 dataclass 的必填字段。`_run_analysis_command` 把缺 callable 当成契约错误，而不是静默 `False`。 |
| ToolSurface 取消探针 | 损坏的 `cancelled_check()` 在 handler 启动前 fail-closed（`cancelled=True`）。 |
| ToolSurface deadline / 取消栅栏 | `src/agent/tools/surface.py` 直接读 `context.deadline_monotonic` 与 `context.cancelled_check`。duck 缺任一属性应 `AttributeError`，不得变成无限运行。`None` 仍表示无绝对 deadline / 无取消 callable。 |
| ToolSurface 默认拒绝 | 未注册名称与缺 capability 在 handler 前拒绝。不要再加第二条执行器。 |
| 就绪 generation 探针 | 探针异常与超时不得变成 `ok`。已配置后端但状态不可读 → `reason_code=generation_backend_probe_failed`。 |
| 配置展示 | 每个 `.env.example` 键必须显式登记。推断不能作为已文档化键的 Settings 契约。 |
| Web 分析 cancel | `ANALYSIS_TASK_HTTP_CANCEL_AVAILABLE` 与生成的 `paths` 对齐。丢掉该标志或 `cancelTask` 的 factory mock 属于契约漂移。 |

已知仍偏宽松（只记录，不要扩大）：

- `resolve_session_category_timeout_seconds` 把缺失的 `category_timeout_seconds` callable 视为**无类别上限**（`0.0`）。这不是把缺 `deadline_monotonic` 的对象传给 `_execute_tools` 的许可。

## 契约清单

| 契约 | Owner 模块 | 生产构造点 | 必须同 PR 更新 | Fail-closed 期望 |
| --- | --- | --- | --- | --- |
| BoundToolSession `deadline_monotonic` | `src/agent/runtime/tool_session.py` | `BoundToolSession(...)`：`src/agent/runner_parts/loop.py`、`src/agent/planning/product.py` | `tests/agent/runtime/bound_tool_session_double.py`（`make_bound_tool_session`）、`tests/agent/runtime/test_bound_tool_session_double.py`、`tests/agent/runtime/test_tool_session.py`（`_session`）、`tests/agent/runtime/test_native_session_bridge.py`（`_native_session`）、`tests/test_agent_frozen_context.py`（`_native_session`）、`tests/agent/test_agent_runner_public_surface.py`（`_ToolCompletionFence.deadline_monotonic`） | Native `_execute_tools` 要求该属性。标准 helper 必须构造真实类，并传入 `deadline_monotonic` 与 `cancelled_check`。 |
| Runner 完成栅栏 `deadline_monotonic` | `src/agent/runner.py` `_ToolCompletionFence` | `_execute_tools` 内取 batch 超时与 `tool_session.deadline_monotonic` 的较早者 | `tests/agent/test_agent_runner_public_surface.py`、`tests/agent/test_tool_timeout.py` | 栅栏方法留在生产类上；AST / 公开展示钉住 runner 模块形状漂移。 |
| ToolAccessContext 超时 / deadline / 取消 | `src/agent/tools/execution.py` `ToolAccessContext`；栅栏在 `src/agent/tools/surface.py` | 由 `BoundToolSession` 按次构造；调用方不要发明第二种 context | `tests/agent/tools/test_agent_tool_surface.py`（缺属性负例）、`tests/agent/runtime/test_tool_session.py`、`tests/agent/test_tool_timeout.py`、`docs/agent-tool-surface.md` | 默认拒绝与超时/取消栅栏留在 ToolSurface。缺 `deadline_monotonic` / `cancelled_check` 属性应 `AttributeError`。不要加绕过 surface 的私有等待。 |
| `TaskRunContext.is_cancel_requested` | `src/task_execution.py` | `src/services/task_queue/worker.py` `_execute_command` 传入 `lambda: self._is_cancel_requested(task_id)` | `tests/test_task_execution.py`、`tests/services/test_local_first_boundaries.py`（`_analysis_task_context`、`test_async_analysis_command_requires_explicit_cancel_protocol`） | 缺 callable 是 `AttributeError`，不是 `False`。进入 `cancelled` / `interrupted` 后该 callable 仍为 true。 |
| 分析 HTTP cancel 标志 + `cancelTask` | `apps/dsa-web/src/api/analysis.ts`；路由 `POST /api/v1/analysis/tasks/{task_id}/cancel` | 生成 OpenAPI `paths` 与 `analysisApi.cancelTask`；TaskPanel 读 `ANALYSIS_TASK_HTTP_CANCEL_AVAILABLE` | `apps/dsa-web/src/api/__tests__/analysis.test.ts`；所有 `vi.mock('../../api/analysis')` / `vi.mock('../../../api/analysis')` 必须 `importActual` 并展开 | 按 kind 隔离：discovery cancel 是另一条路径。整模块替换的 mock 会丢掉已落地的 cancel 字段。 |
| Generation-backend 探针载荷 | `src/services/generation_backend_status_service.py`；由 `src/core/readiness.py` `check_llm_runtime` 消费 | `GenerationBackendStatusService(effective_map=...).get_status()` | `tests/services/test_generation_backend_status_service.py`、`tests/core/test_readiness.py`（`generation_status` / 探针异常） | 探针异常 → `failed` 且 `generation_backend_probe_failed`。不要用残缺 mapping 发明 `ok`。 |
| 已文档化配置键注册守卫 | `src/core/config_registry.py` + `src/core/config_registry_parts/` | 在对应 registry part 写显式字段元数据，而不是 `_infer_*` | `tests/core/test_env_example_config_registry_guard.py`（`test_every_documented_env_example_key_is_registered`）、`python scripts/check_config_doc_consistency.py --fail-on all`、双语 `docs/environment-variables.md` / `_EN.md` | `.env.example` 已文档化但未登记的键使 CI 失败。不要靠抬高未登记债务基线让新键变绿。 |
| LLM 渠道 / 路由表（仅稳定元数据） | `src/services/config/llm_channel_map.py` | 从 effective `.env` map 读取，供 setup、连接测试与 generation-backend 配置视图共用 | `tests/services/test_generation_backend_status_service.py` 的 custom-literal / gateway 路由用例；SystemConfig 公开展示导出 | 不要在此实现 #204 任务感知路由。路由读取必须只有一个权威；status service 从 effective map 构建配置视图，而不是第二套解析器。 |

## 1. BoundToolSession `deadline_monotonic`

**边界。** `BoundToolSession` 是运行时调用金融工具的唯一受支持路径。身份、允许列表、授权、标的范围、预算、绝对 monotonic deadline 与取消 token 在构造时冻结。`deadline_monotonic` 是绝对 `time.monotonic()` 时刻（旧的相对名 `deadline_seconds` 已退役）。

**Owner。** 构造：`src/agent/runtime/tool_session.py`。生产调用方：native loop（`src/agent/runner_parts/loop.py`）与 planning product session 工厂（`src/agent/planning/product.py`）。Native 分发：`src/agent/runner_parts/tools.py`。PydanticAI 复用同一 session（`src/agent/runtime/pydantic_ai_toolset.py`），不是第二权威。

**标准测试 helper。** `tests/agent/runtime/bound_tool_session_double.py` 的
`make_bound_tool_session` 构造真实 `BoundToolSession`，并始终传入
`deadline_monotonic` 与 `cancelled_check`。文件内 `_session` /
`_native_session` 包装器导入该 helper：

- `tests/agent/runtime/test_tool_session.py` `_session`
- `tests/agent/runtime/test_native_session_bridge.py` `_native_session`
- `tests/test_agent_frozen_context.py` `_native_session`

驱动 `_execute_tools` 的新测试必须使用该 helper，不要用 `SimpleNamespace`。
`tests/agent/runtime/test_bound_tool_session_double.py` 会在 helper 漏生产必填
字段时失败；缺 `deadline_monotonic` 时 `_execute_tools` 抛 `AttributeError`。
ToolSurface 缺属性负例见 `tests/agent/tools/test_agent_tool_surface.py`。

**遗留观察 double（不要当作标准 double 复制）。**

- `bound_tool_session_double.py` 中的 `ExecuteToolsObserverSession` 仅用于
  必须在没有 `canonical_tool_name` 的情况下分发密钥/未注册名称的脱敏轨迹。
  它仍然携带 `deadline_monotonic` 与 `cancelled_check`。
- `test_resolve_session_category_timeout_accepts_minimal_and_invalid_doubles`
  记录**类别上限 helper** 可以接受只有 `execution_id` 的 `MinimalSession`。
  这是 helper 语义，不是把该对象交给 `_execute_tools` 的许可。

**核验。** 改 session 字段后运行 `python -m pytest tests/agent/runtime/test_bound_tool_session_double.py tests/agent/runtime/test_tool_session.py tests/agent/test_tool_timeout.py tests/test_agent_frozen_context.py tests/agent/test_agent_runner_public_surface.py tests/security/test_sensitive_redaction.py -q`。若 `_execute_tools` 或 `_ToolCompletionFence` 的 AST 变化，公开展示 hash/pin 测试就是棘轮。

## 2. TaskRunContext `is_cancel_requested`（随 #1466 落地）

**边界。** `src.task_execution.TaskRunContext` 是面向 runner 的进程内契约。`AnalysisTaskQueue` 是适配器。HTTP 适配器可以按 **一个 kind** 投影 `cancel`，不得发明第二套生命周期。见 [task-execution-contract.md](task-execution-contract.md)。

**生产构造点。**

```text
src/services/task_queue/worker.py  _execute_command
  → TaskRunContext(
        ...,
        is_cancel_requested=lambda: self._is_cancel_requested(task_id),
        commit_final_result=...,
      )
```

股票分析适配器在 `analyze_stock` 前、进度回调中、管线返回后轮询该 callable。本地模型拉取在流式分块之间轮询。缺 callable 是契约错误。

**标准测试 helper。** `tests/services/test_local_first_boundaries.py` 的 `_analysis_task_context` 构造真实 `TaskRunContext`。回归 `test_async_analysis_command_requires_explicit_cancel_protocol` 传入**没有** `is_cancel_requested` 的 `SimpleNamespace`，并期望 `AttributeError`。

**不要**用漏掉 `is_cancel_requested`、`update_progress`、`append_flow_event` 或 `commit_final_result` 的 `SimpleNamespace` 充当分析 runner stub。

**核验。** `python -m pytest tests/test_task_execution.py tests/services/test_local_first_boundaries.py -q`

## 3. 分析 HTTP cancel 字段（随 #1466 落地）

**边界。** 按 kind 隔离的路由：

```text
POST /api/v1/analysis/tasks/{task_id}/cancel
```

Discovery cancel（`/api/v1/discover/screen/tasks/{task_id}/cancel`）是另一种 kind，不得复用。Desktop 没有独立分析客户端；TaskPanel 随 Web bundle 发布。

**生产表面。** `apps/dsa-web/src/api/analysis.ts`：

- `ANALYSIS_TASK_HTTP_CANCEL_AVAILABLE` 在生成的 `paths` 含 cancel 路由时为 `true`。
- `analysisApi.cancelTask` 向该路由 POST。
- `apps/dsa-web/src/components/tasks/TaskPanel.tsx` 仅在标志为 true 时渲染取消。

**必须同 PR 更新的 mock。** 展开真实模块：

```ts
vi.mock('../../api/analysis', async () => {
  const actual = await vi.importActual<typeof import('../../api/analysis')>(
    '../../api/analysis',
  );
  return {
    ...actual,
    analysisApi: {
      ...actual.analysisApi,
      // 只覆盖本测试需要的方法
    },
  };
});
```

`()` → `{ analysisApi: { getStatus, getTasks } }` 这种 factory mock **已废弃**。下一次新增或重命名字段时，它们会丢掉 `ANALYSIS_TASK_HTTP_CANCEL_AVAILABLE` 和 `cancelTask`。

已知成对测试（非穷尽；加字段时请 grep `api/analysis` mock）：

- `apps/dsa-web/src/api/__tests__/analysis.test.ts`
- `apps/dsa-web/src/components/tasks/__tests__/TaskPanel.test.tsx`
- `apps/dsa-web/src/components/portfolio/__tests__/usePortfolioAnalysisTasks.test.tsx`
- `apps/dsa-web/src/components/run-flow/__tests__/RunFlowPanel.test.tsx`
- `apps/dsa-web/src/pages/__tests__/PortfolioPage.test.tsx`
- `apps/dsa-web/src/pages/__tests__/SettingsPage.testHarness.tsx`
- `apps/dsa-web/src/pages/__tests__/MarketReviewPage.test.tsx`
- `apps/dsa-web/src/pages/__tests__/ResearchAnalysisWorkbenchPage.test.tsx`
- `apps/dsa-web/src/stores/__tests__/stockPoolStore.test.ts`
- `apps/dsa-web/src/utils/__tests__/setupSmokeTask.test.ts`
- `apps/dsa-web/src/hooks/__tests__/useRunFlowSnapshot.test.tsx`
- `apps/dsa-web/src/hooks/__tests__/useMarketReviewRunner.test.tsx`
- `apps/dsa-web/src/hooks/__tests__/useTaskStream.test.tsx`

**核验。** `cd apps/dsa-web && npx vitest run src/api/__tests__/analysis.test.ts src/components/tasks/__tests__/TaskPanel.test.tsx`，外加你改过 mock 的页面测试。OpenAPI 漂移由 `openapi-types-gate` 负责。

## 4. ToolAccessContext 栅栏

**边界。** `ToolAccessContext` 把 `timeout_seconds`、`deadline_monotonic`、`cancelled_check`、授权与审计上下文带入 ToolSurface。调用方不能靠 `enforce_contract=False` 绕过安全（该字段仅为调用点兼容保留）。

**Owner。** ToolSurface（`src/agent/tools/surface.py`）拥有鉴权、超时、审计与默认拒绝。清单见 `NEW_TOOL_CHECKLIST` 与 [agent-tool-surface_CN.md](agent-tool-surface_CN.md)。

**Fail-closed。** 损坏的取消探针在 handler 前失败关闭。未注册工具与缺 capability 被拒绝。不要增加忽略 `deadline_monotonic` 的工具内等待。漏掉 `deadline_monotonic` 或 `cancelled_check` **属性**是 `AttributeError`，不是无限栅栏。传入 `None` 仍表示“无绝对 deadline / 无取消探针”。

**Duck 废弃路径。** 新的生产与测试调用点应传入真实 `ToolAccessContext`（或让 `BoundToolSession` 构造）。不要再增加 `getattr(context, "deadline_monotonic", None)` 或 `getattr(context, "cancelled_check", None)` 读取点。T3 已收紧 ToolSurface 栅栏读取。

## 5. Generation-backend 探针载荷

**边界。** `GenerationBackendStatusService.get_status()` 返回含 `primary_backend_id`、`fallback_backend_id`、`primary`、`fallback`、`backends` 的 mapping。每个 backend 块至少包含 `backend_id`、`available`、`health_status`、能力标志和 `last_error_*`。这是从 effective env map 得到的**配置视图**，不是持久健康存储，也不是 test double。

就绪检查（`src/core/readiness.py` `check_llm_runtime`）消费 `primary`（`backend_id`、`available`、`health_status`）。探针异常记为 `generation_probe_error`；当 setup 显示主模型已配置时，LLM 检查以 `generation_backend_probe_failed` 失败。

**必须同 PR 更新。** 若就绪检查新读某个字段，请同步：

- `src/services/generation_backend_status_service.py` `_build_status`
- `tests/services/test_generation_backend_status_service.py`
- `tests/core/test_readiness.py` 注入的 `generation_status` mapping
- 若 fail-closed 规则变化：[readiness-self-check.md](readiness-self-check.md) / [readiness-self-check_EN.md](readiness-self-check_EN.md)

不要手写一个省略 `available` / `health_status` 却报告 `ok` 的状态 mapping。

**核验。** `python -m pytest tests/services/test_generation_backend_status_service.py tests/core/test_readiness.py -q`

## 6. 配置注册表已文档化键守卫

**边界。** 三方契约已在 [environment-variables.md](environment-variables.md) 说明：

| 事实源 | 路径 |
| --- | --- |
| 文档化环境变量 | `.env.example` |
| 注册表元数据 | `src/core/config_registry_parts/` |
| 双语清单 | `docs/environment-variables.md` / `docs/environment-variables_EN.md` |

#1055 **不**承担批量补注册。本行只记录展示契约已经 fail-closed：`test_every_documented_env_example_key_is_registered` 与 `python scripts/check_config_doc_consistency.py --fail-on all`。

不要靠扩大 `TEMP_ENV_EXAMPLE_UNREGISTERED_DEBT_*` 让新键变绿。

**核验。** `python scripts/check_config_doc_consistency.py --fail-on all` 以及 `python -m pytest tests/core/test_env_example_config_registry_guard.py -q`

## Test double 义务（摘要）

| Double 类型 | 是否允许 | 义务 |
| --- | --- | --- |
| 经 `make_bound_tool_session` 的真实 `BoundToolSession` | `_execute_tools` 与 session 栅栏测试必须使用 | 新的必填构造字段（`deadline_monotonic`、`cancelled_check` 等）必须在同一 PR 写入 `STANDARD_BOUND_TOOL_SESSION_FIELDS` 与 helper |
| 经 `_analysis_task_context` 或 dataclass 的真实 `TaskRunContext` | 分析/队列 runner 测试必须使用 | 必须包含 `is_cancel_requested` |
| 对 `apps/dsa-web/src/api/analysis.ts` 做 `vi.importActual` 展开 | Web 分析 mock 必须使用 | 只覆盖本测试需要的方法 |
| 只列出部分字段的 `SimpleNamespace` / factory `vi.mock` | 除明确的负例测试外已废弃 | 负例必须期望 `AttributeError` / 类型失败，而不是静默成功 |
| 只有 `execution_id` 的 `MinimalSession` | 仅允许作为 `resolve_session_category_timeout_seconds` 的输入 | 缺类别上限表示无上限（`0.0`）；不要把它当作通用 session 传给 `_execute_tools` |
| `ExecuteToolsObserverSession` | 仅允许用于未注册/密钥名称的脱敏轨迹 | 必须包含 `deadline_monotonic` 与 `cancelled_check`。不要把它当作标准 session double |

## 废弃路径

| 遗留形态 | 替换 | 可删除时机 |
| --- | --- | --- |
| session 上的相对 `deadline_seconds` | 绝对 `deadline_monotonic` | 生产侧已改名。不要重新引入相对名。 |
| 分析 runner 的 `SimpleNamespace` stub | 真实 `TaskRunContext` | #1466 已要求 cancel callable。其余 stub 必须跟随 `_analysis_task_context`。 |
| Factory 式 `vi.mock('../../api/analysis', () => ({ analysisApi: {...} }))` | `importActual` + 展开 | #1466 之后这是 Web 必用模式。新的 factory mock 属于契约缺陷。 |
| 把 duck session 当作“标准 double” | `make_bound_tool_session` | #1055 T2。timeout 的 `_execute_tools` duck 已替换。脱敏保留带必填字段的 `ExecuteToolsObserverSession`。 |
| 把 `getattr(context, "deadline_monotonic", None)` / `getattr(context, "cancelled_check", None)` 当成期望 API | `ToolAccessContext` 上的必填字段 | #1055 T3。ToolSurface 直接读这两个属性。不要在此栅栏上重新引入 getattr 回退。 |
| 对已文档化 env 键使用推断的 Settings 元数据 | 显式 `config_registry_parts` 条目 | 已经 fail-closed。推断只留给仅运行时兼容的值。 |

不要增加并行 session 类型、第二套任务生命周期、第二条分析 cancel 路由，或第二套 generation-backend 解析器。

## 核验（本清单）

最近核验 SHA 上用于对照代码树的命令：

```bash
# 生产构造点与必填字段存在
python3 - <<'PY'
from src.agent.runtime.tool_session import BoundToolSession
from src.agent.tools.execution import ToolAccessContext
from src.task_execution import TaskRunContext
from src.services.generation_backend_status_service import GenerationBackendStatusService
assert "deadline_monotonic" in BoundToolSession.__init__.__code__.co_varnames
assert "cancelled_check" in BoundToolSession.__init__.__code__.co_varnames
assert "deadline_monotonic" in ToolAccessContext.__dataclass_fields__
assert "is_cancel_requested" in TaskRunContext.__dataclass_fields__
assert hasattr(GenerationBackendStatusService, "get_status")
PY

# changelog fragment 格式
python3 scripts/collect_changelog.py --check
```

改某一行前，用 `ls` / 编辑器搜索确认本页文件名仍与仓库一致。纯文档改动不要求跑完整离线 pytest。

## Remaining（#1055 T3 之后）

本页范围内的 #1055 超时栅栏工作已完成：T1 完成 owner 清单，T2 标准化 BoundToolSession double，T3 让 ToolSurface 直接读取 `deadline_monotonic` / `cancelled_check`。不得削弱 ToolSurface 默认拒绝、脱敏或超时。范围外项（[#1023](https://github.com/SiinXu/stock-pulse-ai/issues/1023) 批量注册、[#204](https://github.com/SiinXu/stock-pulse-ai/issues/204) 路由、Agent 重设计）仍属各自 issue。

## 相关

- [Agent ToolSurface](agent-tool-surface_CN.md)（[EN](agent-tool-surface.md)）
- [任务执行契约](task-execution-contract.md)
- [环境变量清单](environment-variables.md)（[EN](environment-variables_EN.md)）
- [就绪 / 自检](readiness-self-check.md)（[EN](readiness-self-check_EN.md)）
- [Config-access ratchet](config-access-ratchet.md)
- [敏感数据脱敏](security-sensitive-data-redaction.md)
- [贡献指南](CONTRIBUTING.md)（[EN](CONTRIBUTING_EN.md)）
