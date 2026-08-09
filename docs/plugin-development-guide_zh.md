# 插件开发指南

状态：可信系统插件（扩展面 v1）的统一入口文档。

本指南是代码型扩展的**汇总起点**，不替代已冻结的契约与各扩展点专题文档。
可运行代码与
[`docs/plugin-extension-contract.md`](plugin-extension-contract.md)
在出现分歧时仍为权威来源。

English edition: [`plugin-development-guide.md`](plugin-development-guide.md).

## 是什么、为什么

StockPulse 插件允许**可信运维方**在不 fork 主程序的前提下，为恰好六个扩展点
加入经审阅的 Python 行为：

| 扩展点 | 适用场景 |
| --- | --- |
| `data_provider` | 在 `DataFetcherManager` 路由后新增行情数据源 |
| `analysis_strategy` | 通过插件生命周期发布声明式 `Skill` 定义 |
| `agent_tool` | 在 ToolSurface 拥有的 `ToolDefinition` 上注册（见安全说明） |
| `notification_channel` | 为通知分发器新增投递适配器 |
| `report_template` | 代码型 Markdown / 企业微信 / brief 报告渲染 |
| `event_hook` | 分析 / 大盘复盘生命周期上的旁观型回调 |

能用更小机制时优先更小机制：

- 自然语言策略与工具*元数据* → `AGENT_SKILL_DIR` 下的 YAML / `SKILL.md`（无需可信进程代码）
- 仅改 Jinja 报告版式 → `REPORT_TEMPLATES_DIR`
- UI 面板、设置页、远程应用商店、依赖安装器或第七扩展点 → 新 ADR；**不属于** surface v1

## 安全模型（先读）

设置 `PLUGINS_DIR` 即授权进程加载**任意 Python**，权限与 StockPulse 进程相同。当前：

- 无远程应用商店或自动下载；
- 无插件依赖安装器；
- manifest `permissions` 仅为描述元数据，**不**形成强制沙箱；
- 无热加载（修改后需重启进程）。

启用任何包前请逐行审阅。生产环境默认保持 `PLUGINS_DIR` 未设置，除非包已审阅并固定。
运维信任边界亦见
[安全基线](security-baseline.md#operator-security-boundaries) 与
[ADR-007](adr/ADR-007-versioned-plugin-extension-boundary.md)。

### Agent 工具限制（#539）

`agent_tool` 注册路径会校验 `ToolDefinition` 并可写入进程级 `ToolRegistry`。
真正经 Agent 运行时调用仍取决于 issue **#539** 跟踪的 ToolSurface 沙箱加固。
在该门槛满足前，外部 agent-tool 插件应按 **仅加载并注册** 处理：契约测试可断言
注册与直接 handler 调用，但不得声称已具备加固后的 live Agent 执行路径。
官方示例 [`example-agent-tool`](../examples/plugins/example-agent-tool/)
会明确写出该边界。

## 快速开始（10 分钟内）

在已配置好的本仓库 Python 环境中：

```bash
# 1) PLUGINS_DIR 指向插件包的父目录（不要指向单个包）
export PLUGINS_DIR="$PWD/examples/plugins"

# 2) 通过 composition root 冒烟加载官方通知参考插件
python - <<'PY'
from src.application_services import (
    ApplicationServices,
    reset_application_services,
    set_application_services,
)
from src.config import Config

reset_application_services()
services = ApplicationServices(
    config=Config(stock_list=[]),
    plugins_dir="examples/plugins",
)
set_application_services(services)
loads = {r.plugin_id: r for r in services.plugin_load_results}
print("loaded", sorted(k for k, v in loads.items() if v.success))
assert loads["example-notification-channel"].success
print("channels", sorted(
    e.channel_id for e in services.notification_channel_registry.snapshot()
))
services.close()
reset_application_services()
PY
```

预期：`examples/plugins/` 下格式正确的包出现在加载快照中；
通知通道注册表含 `example_log`。

可选实机通知（仅将路由元数据写入日志）：

```bash
export PLUGINS_DIR="$PWD/examples/plugins"
export NOTIFICATION_REPORT_CHANNELS="example_log"
python main.py --stocks 600519 --dry-run
```

### 最小包结构

```text
my-plugins/                 # PLUGINS_DIR 的值
  my-channel/
    manifest.json
    plugin.py               # 定义 class Plugin(src.plugins.Plugin)
    README.md               # 面向运维的信任说明
```

manifest 字段、版本规则与入口路径约束见契约
[Package And Manifest](plugin-extension-contract.md#package-and-manifest)。
可直接复制任一官方示例并修改稳定 ID。

## 冻结的作者导入面

外部插件应只导入：

1. `src.plugins` 上 `PLUGIN_EXTENSION_SURFACE_V1_AUTHOR_EXPORTS` 列出的名称
2. 数据源用的 `data_provider.DataProvider` / `DataProviderRegistration`
3. 特定扩展点需要、但不在插件包根导出的宿主类型：
   - `analysis_strategy`：`src.agent.skills.base.Skill`
   - `agent_tool`：`src.agent.tools.registry` 中的
     `ToolDefinition` / `ToolParameter` / `ToolPolicy`（由 ToolSurface 拥有）

不要导入 `PluginManager`、`ExternalPluginLoader`、私有 `src.plugins.*` 模块，
也不要发明第七个扩展点名称。

生命周期始终为：

```python
class Plugin(BasePlugin):
    def onload(self, context: PluginContext) -> None:
        context.register("<point>", "<canonical-id>", implementation, contract_version="1")

    def onunload(self) -> None:
        """仅释放插件自有资源；注册清理由 manager 负责。"""
```

## 官方示例

将 `PLUGINS_DIR` 指向 `examples/plugins`（父目录）。

| 包 | 扩展点 | 测试证明 |
| --- | --- | --- |
| [`example-provider`](../examples/plugins/example-provider/) | `data_provider` | 加载、日线路由、干净 disable（绑定 manager 注册表） |
| [`example-analysis-strategy`](../examples/plugins/example-analysis-strategy/) | `analysis_strategy` | 加载并将分离后的 `Skill` 写入进程 catalog |
| [`example-agent-tool`](../examples/plugins/example-agent-tool/) | `agent_tool` | 加载并注册到 `ToolRegistry`；仅在测试中调用 handler |
| [`example-notification-channel`](../examples/plugins/example-notification-channel/) | `notification_channel` | 默认进程根上的完整分发生命周期 |
| [`example-report-template`](../examples/plugins/example-report-template/) | `report_template` | 加载并经冻结渲染路径输出 Markdown |
| [`example-event-hook`](../examples/plugins/example-event-hook/) | `event_hook` | 加载并接收旁观型分析生命周期事件 |

文档内联的较小 Markdown 示例仍位于
[`docs/examples/report-template-plugin/`](examples/report-template-plugin/)；
新工作优先使用 `examples/plugins/` 包。

## 分扩展点深读

| 主题 | 文档 |
| --- | --- |
| 冻结扩展面、生命周期、六个扩展点 | [插件扩展契约（英文）](plugin-extension-contract.md) |
| 架构决策 | [ADR-007](adr/ADR-007-versioned-plugin-extension-boundary.md) |
| 数据源作者指南 | [Data Provider Plugin Authoring Guide](data-provider-plugin-authoring.md) |
| 分析策略作者指南 | [Analysis Strategy Plugin Authoring Guide](analysis-strategy-plugin-authoring.md) |
| 运维安全边界 | [安全基线](security-baseline.md#operator-security-boundaries) |
| 扩展面冻结与通知参考测试 | `tests/plugins/test_extension_surface_v1.py` |


## 运维视角

本节面向部署与值班运维，而非插件作者。

### 生命周期审计

生命周期变更会通过既有安全审计设施写入事件（`event_type=plugin.lifecycle`）。
自动启动加载采用 best-effort，审计存储不可用时不会阻断其它插件。管理员发起
enable / disable / reload 时，如果 attempt 事件无法持久化，会在状态变更前以
fail-closed 方式返回错误；如果操作完成后 completion 写入失败，API 会返回
`503 security_audit_unavailable` 并说明真实完成状态，不会声称已回滚。

### Data Provider 自动绑定（显式开关）

| 配置项 | 默认 | 效果 |
| --- | --- | --- |
| `PLUGIN_DATA_PROVIDER_AUTO_BIND` | 关闭 | 开启后，默认 `ApplicationServices` 组合根会将 `PluginManager` 绑定到进程级 `DataFetcherManager.plugin_registry`（注入或自动创建），使已注册 provider 无需额外胶水即可路由 |

保持关闭即可维持历史手动模式。开启且未注入 manager 时，`ApplicationServices`
会构造一个 `DataFetcherManager` 并通过 `services.data_fetcher_manager` 暴露。
股票行情与历史服务及主分析流水线会解析这个已安装 owner，因此插件 provider
与内置 fallback 共用同一个 registry。注入 manager 时，组合根会在任何相关
插件注册之前原子补齐 Analysis Strategy、Notification Channel、Agent Tool 与
Event Hook 合同；无效或已冲突的 registry 会以稳定错误码阻断进程组合，绝不
静默退化为孤立 registry。自定义组合根仍可直接调用
`try_build_auto_bound_registry`。

```python
from data_provider import DataFetcherManager
from src.plugins import (
    PLUGIN_APPLICATION_VERSION,
    PluginManager,
    try_build_auto_bound_registry,
)

providers = DataFetcherManager()
registry, error = try_build_auto_bound_registry(providers)
if error:
    raise RuntimeError(error)
plugins = PluginManager(
    application_version=PLUGIN_APPLICATION_VERSION,
    registry=registry or providers.plugin_registry,  # 关闭开关时需显式绑定
)
```

### 健康检查

```python
report = plugin_manager.health_check()
for entry in report.plugins:
    print(entry.plugin_id, entry.state, entry.last_error_code, entry.extension_points)
```

`last_error_code` 表示最近一次稳定失败（例如 `plugin_onload_failed`）；禁用或
修改意图不会清除它，真正改变状态且成功的 load / reload 才表示恢复并清除；
幂等 enable 不会抹掉仍需运维处理的 reload 失败。单个插件失败不得影响其它
插件与核心启动。

## 验证命令

离线插件套件（本主题首选本地门禁）：

```bash
python -m pytest tests/plugins -m "not network and not benchmark" -q
```

仅改示例或其契约测试时可缩小为：

```bash
python -m pytest tests/plugins/test_example_*.py tests/plugins/test_extension_surface_v1.py -q
```

## 本指南不覆盖的内容

- 应用商店分发、签名校验或多租户隔离
- 对插件代码的强制沙箱（仅进程等价信任）
- 在不保留 ToolSurface 的前提下迁移内置 Tools（#432 / #539）
- UI、Settings 或 MCP 连接器扩展点

上述仍属独立设计轨道，请勿拉伸邻近注册 API 来模拟它们。
