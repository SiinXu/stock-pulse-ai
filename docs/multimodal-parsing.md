# 多模态解析（PDF 与图表）— 第一阶段

StockPulse 可将财经 PDF 解析为结构化文本/表格，并将行情图表读成结构化视觉观察。本文描述 issue #253 的**第一阶段**：后端服务 + 默认关闭的可选 Agent Tools。

HTTP 上传 UI、默认分析路径的报告/Prompt 投影、扫描件 PDF 的视觉辅助，以及第三方转录自动拉取，均留到后续阶段。用户提供的财报电话会转录解析见 `docs/earnings-transcript-parsing.md`（工具 `parse_earnings_transcript`）。

## 诚实契约

| 表面 | 行为 |
| --- | --- |
| PDF | 优先本地文本抽取。空/稀疏 PDF 返回 `unavailable` / `degraded` 与稳定 `reason_code`，不编造数字。 |
| 图表 | 复用既有 `VISION_MODEL` 路径（与图片股票提取相同的 LiteLLM Vision 表面）。模型/密钥缺失时返回 `unavailable` 并给出明确原因。 |
| 上传 | 用户文件永不执行。路径沙箱限制在 `MULTIMODAL_FILE_ROOT` 内。施加体积上限与 MIME/魔数校验。 |

成功或降级结果均带研究用途免责声明。

## 默认与注册契约

Agent Tools `parse_financial_pdf` 与 `read_price_chart` **默认关闭**。

| 条件 | 行为 |
| --- | --- |
| `MULTIMODAL_AGENT_TOOLS_ENABLED=false`（默认） | 工厂返回 `None`，进程工具目录不变 |
| 开启但未配置 `MULTIMODAL_FILE_ROOT` | 工具不注册，并记录 warning |
| 两者均配置且进程重启 | 工具注册进缓存的 `ToolRegistry` |
| 图表工具在 Vision 未就绪时 | 仍可注册；每次调用以 `vision_model_unavailable` 等原因降级 |

启用后需重启进程，以便重建工具注册缓存。

## 配置

```bash
MULTIMODAL_AGENT_TOOLS_ENABLED=false
# MULTIMODAL_FILE_ROOT=/absolute/path/to/multimodal-uploads
# VISION_MODEL=openai/gpt-5.5   # 图表阅读在配置后使用
```

## 服务

| 模块 | 职责 |
| --- | --- |
| `src/services/pdf_parsing_service.py` | 本地 PDF 解析 → `schema_version=pdf-parse-v1` |
| `src/services/chart_reading_service.py` | Vision 图表阅读 → `schema_version=chart-reading-v1` |
| `src/agent/tools/multimodal_tools.py` | 默认关闭的 `ToolDefinition` 工厂 |

### PDF 输出（摘要）

- `status` / `reason_code` / `method`
- `source`（文件名、字节数、页数）
- `text`、`pages[]`、尽力而为的 `tables[]`
- 第一阶段 `vision_assist` 为 `not_applicable` / `skipped`（不做页面栅格化）

### 图表输出（摘要）

- `chart_type`、`symbol_hints`、`timeframe_hint`、`trend`
- `key_levels[]`、`observations[]`、`confidence`
- 选中路由时的 `vision_model`

图表 Prompt 位于 `CHART_READ_PROMPT`，并记录在 `docs/chart-read-prompt.md`。修改时需同步该文档，并在 PR 描述中附完整 Prompt（与 `EXTRACT_PROMPT` 同规则）。

## 路径沙箱

- 相对路径在 `MULTIMODAL_FILE_ROOT` 下解析
- 绝对路径在 `resolve()` 后必须仍位于根目录内
- 拒绝：`..` 逃逸、URL、`~` 展开、空字节、缺失文件
- 体积上限：PDF 10 MiB，图片 5 MiB（与图片股票提取对齐）

## 延后（非第一阶段）

- HTTP 上传 API / Web UI
- 财报电话会纪要分析
- 扫描件 PDF 页面栅格化 + 视觉辅助
- 默认分析路径投影与报告证据链接入

## 回滚

1. 设置 `MULTIMODAL_AGENT_TOOLS_ENABLED=false`（或删除该变量）
2. 可选清空 `MULTIMODAL_FILE_ROOT`
3. 重启进程，使工具注册缓存在无这些工具的情况下重建

不涉及数据库迁移。
