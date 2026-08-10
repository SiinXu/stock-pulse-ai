# 多模态解析（PDF + 图表）— Phase 1

对应 Issue：[\#253](https://github.com/SiinXu/stock-pulse-ai/issues/253)

Phase 1 提供**本地优先的财务 PDF 解析**与**基于 Vision 的 K 线/图表读图**，并通过默认关闭的 Agent 工具暴露：

| 变量 | 默认 | 作用 |
| --- | --- | --- |
| `MULTIMODAL_AGENT_TOOLS_ENABLED` | `false` | 为 true 且配置了 `MULTIMODAL_FILE_ROOT` 并重启后，注册 `parse_financial_pdf`、`read_price_chart` 与 `parse_earnings_transcript` |
| `MULTIMODAL_FILE_ROOT` | 空 | 用户文件沙箱根目录（拒绝 URL / 路径穿越） |

图表读图依赖既有 `VISION_MODEL`（兼容 `OPENAI_VISION_MODEL`）。无 Vision 时诚实降级。

## 范围说明

- Phase 1 **不**新增 HTTP 上传 API / Web UI（可后续把文件暂存到 `MULTIMODAL_FILE_ROOT`）
- 用户提供的电话会转录解析已单独交付，见 [earnings-transcript-parsing.md](earnings-transcript-parsing.md)
- 第三方转录自动拉取、证据链报告投影、扫描件 PDF 的 Vision 页渲染辅助属后续阶段

完整契约与安全边界见 [multimodal-parsing.md](multimodal-parsing.md) / [multimodal-parsing_EN.md](multimodal-parsing_EN.md)。
