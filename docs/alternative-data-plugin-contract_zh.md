# 另类数据插件契约（ToolSurface）

状态：Issues **#139** / **#1144** 的已实现契约说明。

英文主文档：[`alternative-data-plugin-contract.md`](alternative-data-plugin-contract.md)。
实现与测试以英文主文档及可运行代码为准；本中文版为同义摘要。

## 目标

为公司事件、持仓变动、供应链标签、量化情绪等**另类 / 结构化数据**提供标准插件契约：能力标签、权限声明、证据引用、类型化失败→缺口（不编造）。

## 非目标

- 在核心内置付费另类数据源。
- 新增第七个插件扩展点。
- 将另类数据视为已核实事实或决策权威。

## 默认关闭

- 未配置 `PLUGINS_DIR` 时不发现外部插件。
- `get_corporate_events_brief` **不**进入默认 `ALL_*_TOOLS` 目录。
- 调用需要 ToolSurface 能力 `alt_data:read`。
- 载荷强制 `authority=non_authoritative`、`role=supporting_only`。

## 权限与清单

- Manifest `permissions` 必须覆盖 `ToolPolicy.permissions`（#944 加载期子集校验）。
- 会话缺少 `alt_data:read` → `permission_denied`。
- 声明不是沙箱隔离。

## 端到端参考类型：公司事件

接入（插件/fixture）→ ToolSurface 工具 →
`alternative_data_governance` 治理投影 → AnalysisContext 可选块 + 支持性证据分层。

## 证据分层

- 禁止投影到 `verified_fact` / `decision`。
- 核心 `data_quality.overall_score` 在附加另类数据块之前计算，不被稀释或抬高。
- 无效/缺失/超时 → gap，且 `confidence=null`、不发明事件列表。

可运行示例：[`examples/plugins/example-alternative-data/`](../examples/plugins/example-alternative-data/)。
