# Agent ToolSurface（默认拒绝）

状态：Agent 工具注册与执行的现行契约。
Issue: [#1077](https://github.com/SiinXu/stock-pulse-ai/issues/1077)。

**English**: [agent-tool-surface.md](agent-tool-surface.md)

规范实现：`src/agent/tools/surface.py`。
兼容导入：`src.agent.tool_surface`（仅再导出）。

## 必需调用链

```text
ToolRegistry.resolve / bind_definition
  → ToolSurface.execute_tool (authz, timeout, audit)
    → implementation handler
```

生产运行时只能通过 `BoundToolSession.execute` 进入该调用链：

- Native runner（`src/agent/runner_parts/tools.py`）
- AgentExecutor / `run_agent_loop`
- PydanticAI toolset（`src/agent/runtime/pydantic_ai_toolset.py`）

`ToolRegistry.execute` 已永久禁用（`direct_tool_execution_disabled`）。
未注册名称与缺失能力会在 handler 启动前失败关闭。

## 新工具检查清单

每个新增 Agent 工具都必须在
`src.agent.tools.surface.NEW_TOOL_CHECKLIST` 中声明全部四项：

| 项 | 要求 |
| --- | --- |
| `permission` | 使用 `ToolPolicy.declared(...)`，且必须是 `SUPPORTED_AGENT_TOOL_CAPABILITIES` 的非空子集。缺少授权时返回 `permission_denied`。 |
| `timeout` | 遵守 `ToolAccessContext.timeout_seconds` / `deadline_monotonic`。不要另加绕过 surface 围栏的私有等待。 |
| `audit` | 由 ToolSurface 在成功与拒绝时发出 `build_tool_audit`。不要记录原始密钥或不可信文档正文。 |
| `hitl_need` | 工具**不得**再加一条并行审批路径。高风险建议覆写仍走既有 HITL 风控门（`docs/human-approvals.md`）。默认不做工具级 HITL。 |

## 注册所有者

| 所有者 | 路径 | 说明 |
| --- | --- | --- |
| 进程注册表 | `src/agent/runtime_assembly.py` `get_tool_registry()` | 内置 data / analysis / market / backtest 工具，然后刷新插件，再接入可选工具 |
| 插件 `agent_tool` | `src/plugins/agent_tools.py` | 只注册 `ToolDefinition` 对象；实际调用仍走 ToolSurface |
| `@tool` 装饰器 | `src/agent/tools/registry.py` | 注册到默认注册表；不是生产执行路径 |
| 可选工厂 | `src/agent/tools/{search,multimodal,earnings_transcript,valuation,ocr,kronos}_tools.py` | 由配置门控；所有权仍属于 ToolSurface |

内置模块仍与注册表并列（`src/agent/tools/*.py`）。物理迁到
`src/agent/tools/builtins/` 已暂缓：那会改写 `runtime_assembly`
以及大量超出本 issue 文件边界的 import / 补丁目标。

## 兼容导入与补丁目标

保持以下路径可用：

- `from src.agent.tool_surface import ToolSurface, build_tool_error_result, validate_tool_parameter_value`
- Logger 名称 `src.agent.tool_surface`
- 出站 URL 探测的规范补丁目标：`src.agent.tools.surface.validate_outbound_url`

新代码优先导入 `src.agent.tools.surface`。

## 暂缓的直调面

| 表面 | 仍保留的原因 | 所有者 |
| --- | --- | --- |
| 已注册工具上的 `ToolDefinition.handler(...)` | Issue #539 的插件契约测试明确允许加载期 handler 探测，且不得声称这是封闭的 live-agent 路径 | 插件 / #539 |
| 未注册的 `build_*_tools()` handler 单元测试 | 实现形态测试；不是生产执行入口 | 工具模块测试 |
| MCP 工具 | 按设计使用独立注册表（`src/mcp_server/`） | MCP |
| Planning-loop invoker | 由调用方提供；生产调用方必须包装 `ToolSurface.execute_tool` | Planning |

已注册 handler 若未经过 ToolSurface，**不会**设置
`tool_surface_dispatch_authorized()`。生产 runner / executor 分发会设置。
不要把 handler 单元测试通过当作 ToolSurface 授权的证明。

## 相关

- [安全基线](security-baseline.md)
- [人工审批（HITL）](human-approvals.md)
- [插件开发指南](plugin-development-guide_zh.md)
- [另类数据插件契约](alternative-data-plugin-contract_zh.md)
- [共享运行时 session 契约所有权](runtime-session-contract-owners_CN.md) — BoundToolSession / ToolAccessContext 字段与 test double 义务
