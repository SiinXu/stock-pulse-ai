# 外部框架适配指南

状态：通过冻结的 StockPulse 插件扩展面（v1）吸收外部框架的薄适配编写指南。

English edition: [`external-framework-adapter-guide.md`](external-framework-adapter-guide.md).

相关文档（与本指南冲突时以可运行代码与下列契约为准）：

- [插件扩展契约（英文）](plugin-extension-contract.md) / [ADR-007](adr/ADR-007-versioned-plugin-extension-boundary.md)
- [Data Provider 插件编写指南](data-provider-plugin-authoring.md)
- [Analysis Strategy 插件编写指南](analysis-strategy-plugin-authoring.md)
- [插件开发指南](plugin-development-guide_zh.md)
- [外部能力吸收提案](plans/external-capability-absorption-proposal.md)

可运行示范（OpenBB → `data_provider`）：
[`docs/examples/external-framework-data-provider/`](examples/external-framework-data-provider/)。

## 目的

StockPulse **不会**把完整外部框架（OpenBB、Qlib、FinRL 等）嵌进核心进程。
支持的吸收路径是**薄适配插件**，它应当：

1. 将外部能力映射到**恰好一个**冻结扩展点；
2. 不为 CI 或默认部署强制安装重型依赖；
3. 把路由、回退、缓存与熔断留给该扩展点既有的宿主权威组件。

本指南是外部能力吸收提案阶段二的操作说明。

## 不可妥协规则

| 规则 | 说明 |
| --- | --- |
| 不新增扩展点 | 仅 `data_provider`、`analysis_strategy`、`agent_tool`、`notification_channel`、`report_template`、`event_hook`。第七扩展点需要新 ADR 与 surface 主版本升级。 |
| 仅薄适配 | 接线 + 字段归一 + 有界 I/O。不要在插件内重做 `DataFetcherManager`、StrategyEngine、ToolSurface 或报告流水线。 |
| 依赖手动安装 | 运维方自行安装并固定外部包版本。StockPulse 从不替插件执行 `pip install`。 |
| 默认关闭 | 示范与第三方适配器不进入默认加载集。启用必须显式设置并审阅 `PLUGINS_DIR`。 |
| 显式失败，宿主回退 | 依赖缺失、超时或上游空数据必须**抛错**（或返回宿主已理解的类型化失败）。禁止用 `return None` / `[]` / 空成功帧伪装成功。 |
| 信任 = 完整进程权限 | 外部适配插件是**无沙箱的可信进程内代码**。manifest `permissions` 仅为描述元数据。 |

## 决策树：选哪个扩展点？

```text
外部框架主要提供什么？
│
├─ 与其他 fetcher 同类的行情 / 基本面时序
│    → data_provider
│      例：OpenBB 股权历史 K 线、其他行情供应商
│
├─ 仅自然语言投资准则 / 角色提示
│    → 优先 AGENT_SKILL_DIR 下的 YAML Skill（无需插件）
│    → 仅当需要加载期 Python 时使用 analysis_strategy 插件
│
├─ Agent 应按类型参数按需调用的能力
│    → agent_tool（注意：在线 Agent 执行加固见 issue #539）
│      例：Qlib 因子查询、FinRL 策略信号服务客户端
│
├─ 额外通知投递后端
│    → notification_channel
│
├─ 代码型报告渲染（markdown / wechat / brief）
│    → report_template
│      （仅 Jinja 版式 → 改用 REPORT_TEMPLATES_DIR）
│
└─ 分析 / 大盘复盘生命周期上的旁观副作用
     → event_hook（绝不可中断主流程）
```

若能力需要 UI 面板、设置页、应用商店、依赖自动安装或热加载，**停止**。
这些不在 surface v1 内；应开 ADR，而不是硬撑邻近注册 API。

### 本示范为何选择 OpenBB → `data_provider`

| 维度 | OpenBB 数据路径 | Qlib 因子路径 |
| --- | --- | --- |
| 最近的冻结扩展点 | `data_provider`（日线） | 通常是 `agent_tool`（因子查询） |
| 契约同构性 | 与内置 fetcher 相同的 OHLCV 归一 + Manager 回退 | 需要工具参数/结果模式，并受 #539 约束 |
| 运维安装面 | 可选 `openbb` 包 | 更重的量化栈 / 常宜作为旁路服务 |
| 阶段二示范价值 | 「外部数据进入、宿主路由」最高 | 更适合作为后续 tool 适配 |

先落地 OpenBB；Qlib/FinRL 复用同一薄适配纪律。

## 包布局

沿用仓库可复制插件惯例
（[`docs/examples/report-template-plugin/`](examples/report-template-plugin/)、
[`examples/plugins/example-provider/`](../examples/plugins/example-provider/)）：

```text
<PLUGINS_DIR>/
  openbb-data-provider/          # 仅直接子目录；loader 不递归
    manifest.json
    plugin.py
    README.md
```

`PLUGINS_DIR` 指向**父目录**。未设置 / 空 / 仅空白 → 不做外部发现（安全默认）。

### Manifest 清单

| 字段 | 要求 |
| --- | --- |
| `id` | 稳定 `[a-z0-9][a-z0-9._-]*`，不与内置或其他插件冲突 |
| `version` | 精确 `MAJOR.MINOR.PATCH` |
| `minAppVersion` | 你实际测试过的最早 StockPulse 版本 |
| `apiVersion` | surface v1 使用 `"1"` |
| `entrypoint` | 包内相对路径 `file.py:Class` |
| `permissions` | 仅描述性 — 向运维声明依赖与出站预期 |

### 注册示意（`data_provider`）

```python
from data_provider import DataProvider, DataProviderRegistration
from src.plugins import Plugin as BasePlugin

class Plugin(BasePlugin):
    def onload(self, context):
        registration = DataProviderRegistration(
            provider_id="openbb-daily-data",
            factory=MyProvider,  # 可调用对象 → DataProvider 实例
            markets=frozenset({"us", "hk", "cn"}),
            capabilities=frozenset({"daily_data"}),
        )
        context.register(
            "data_provider",
            registration.provider_id,
            registration,
            contract_version="1",
            priority=95,
        )
```

Data Provider 仍需将 `PluginManager` 绑定到目标
`DataFetcherManager.plugin_registry`。详见
[Data Provider 编写指南](data-provider-plugin-authoring.md)。

## 字段归一要求

日线适配器必须返回至少包含下列列的 `pandas.DataFrame`：

| 列 | 说明 |
| --- | --- |
| `date` | 优先 `YYYY-MM-DD` 字符串 |
| `open` / `high` / `low` / `close` | 数值 |
| `volume` | 可转为整数 |
| `amount` | 数值；上游缺失时可保守推导 |
| `pct_chg` | 涨跌幅百分比；缺失时可由 `close` 计算 |

不要用不完整行“凑成功”。应明确行处理策略；OpenBB 示范在任一必需日期或
OHLCV 值缺失、非数值、非有限、出现禁止的负值，或违反
`low <= open/close <= high` 时让整个 attempt 失败。它先按时间戳升序排序，
每个 UTC 日期保留最新观测，再推导 `amount` 与 `pct_chg`。

示范在固定 yfinance 调用前执行 StockPulse symbol 映射：

| StockPulse 形式 | yfinance 形式 |
| --- | --- |
| `AAPL` | `AAPL` |
| `600519`、`600519.SH`、`SH600519` | `600519.SS` |
| `000001`、`000001.SZ`、`SZ000001` | `000001.SZ` |
| `HK00700`、`00700.HK`、`0700` | `0700.HK` |
| `920748` / `920748.BJ` 等北交所形式 | 不支持；I/O 前抛错并交由 Manager 回退 |

## 失败、超时与降级

| 情形 | 要求行为 |
| --- | --- |
| 外部包未安装 | 抛出明确错误，点名包名并说明 StockPulse 不会自动安装 |
| 传输 / SDK 超时 | 对真实阻塞调用强制有限 deadline，终止并回收超时任务后抛错 |
| 上游空或畸形载荷 | 抛错；除非能力显式允许空数据且宿主契约已写明，否则不要返回空“成功”帧 |
| 批量多标的部分失败 | 按宿主契约使本次 attempt 失败或仅返回已校验行 — 禁止对缺失标的静默填零 |
| 跨 provider 回退 | **禁止在插件内实现**。仅一次 attempt；链路由 `DataFetcherManager` 拥有 |

宿主**不会**给每次 provider 调用套统一 deadline。OpenBB 示范支持
`openbb>=4.7,<4.8`，并在隔离进程组内只调用一次
`equity.price.historical(..., provider="yfinance")`。deadline 到期时终止并
回收该进程组；任意 SDK `TypeError` 会原样失败，绝不会触发第二次请求。

## 依赖声明与手动安装

1. 在插件 `README.md` 写明所需包与最低版本。
2. 优先在**调用时**（或 factory 时）惰性导入，使未启用该插件的开发环境不必安装重型依赖。
3. 运维安装到与 StockPulse **同一**运行环境：

   ```bash
   pip install 'openbb>=4.7,<4.8'
   export PLUGINS_DIR=/opt/stockpulse/plugins
   ```

4. StockPulse CI 必须在**没有**这些包时仍保持绿色。离线测试注入假客户端/fixture（`pytest -m "not network"`）。

## 信任责任声明

> **外部适配插件以完整进程权限运行。**
> 设置 `PLUGINS_DIR` 即表示运维方明确决定加载经审阅的 Python 代码，
> 该代码可访问 StockPulse 进程用户可见的内存、环境变量、本地文件与网络路径。
> surface v1 没有插件沙箱、签名库、应用商店或自动更新通道。
> 你负责代码审阅、依赖审阅、版本固定，并在不需要可信外部代码时保持
> `PLUGINS_DIR` 未设置。

## 运维照做步骤

以下步骤与 OpenBB 示范包一致。

```bash
# 在已安装 StockPulse 自身依赖的克隆上操作。

# 1) 审阅示范包
less docs/examples/external-framework-data-provider/plugin.py
less docs/examples/external-framework-data-provider/manifest.json

# 2) 手动安装外部框架（离线 fixture 测试可跳过）
pip install 'openbb>=4'

# 3) 显式启用：PLUGINS_DIR = 包目录的父目录
export PLUGINS_DIR="$PWD/docs/examples"

# 4) 离线契约测试（无需网络、无需真实 OpenBB）
python -m pytest -q tests/plugins/test_external_framework_openbb_provider.py

# 5) 组合冒烟（若不用假客户端直接 get_daily_data，则需要 OpenBB）
python - <<'PY'
from data_provider import DataFetcherManager
from src.application_services import ApplicationServices
from src.plugins import PLUGIN_APPLICATION_VERSION, PluginManager

providers = DataFetcherManager()
plugins = PluginManager(
    application_version=PLUGIN_APPLICATION_VERSION,
    registry=providers.plugin_registry,
)
services = ApplicationServices(plugin_manager=plugins)
try:
    services.start_plugins()
    print("discovery", services.external_plugin_results)
    print(
        "providers",
        [
            item.registration_id
            for item in plugins.registrations("data_provider")
            if item.plugin_id == "stockpulse.openbb-data-provider"
        ],
    )
finally:
    services.close()
PY
```

在完成包与依赖树审阅前，生产环境请保持 `PLUGINS_DIR` 未设置。

## 测试期望

| 层级 | 期望 |
| --- | --- |
| 单元 / 契约 | 使用 OpenBB 4.7 形状的 OBBject/provider fake；断言单调用、symbol 映射、进程超时清理、严格 OHLCV/日期校验、重复策略、Manager 回退归因与生命周期 |
| 网络 | 可选，标记 `@pytest.mark.network`；`ci_gate` 不得依赖。示范的离线 gate 不声称已执行真实 OpenBB 冒烟 |
| 核心机制 | **不要**为了“让示范跑通”去改 `src/plugins` 的 loader/manager/registry — 若宿主契约不足，应另开 ADR 任务 |

## V1 表面声明

本指南与 OpenBB 示范：

- **零**新增扩展点；
- 不修改 `registry.py` / `manager.py` / `loader.py` / `manifest.py`；
- 不修改 `data_provider/` 宿主实现；
- 仅依赖公开作者导入面（`src.plugins` 包根 + `data_provider.DataProvider` /
  `DataProviderRegistration`）。

## 后续候选

| 候选 | 建议扩展点 | 说明 |
| --- | --- | --- |
| Qlib 因子 | `agent_tool` | 优先旁路推理进程；薄查询工具 |
| FinRL 策略 | `agent_tool` | 同提案 §7.1 |
| TradingAgents 角色 | 先 YAML `analysis_strategy` / Skill | 仅必要时升到 Python |
| 分析导出 | `event_hook` | 仅旁观 |

## 回滚

从 `PLUGINS_DIR` 移除适配包（或取消 `PLUGINS_DIR`）并重启即可。
因未改宿主表面，核心行为零回归面。
