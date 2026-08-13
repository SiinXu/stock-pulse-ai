# 有界本地 OCR Agent 工具

StockPulse 可选用 Tesseract 从**本地图片**以及**内嵌位图的 PDF 页**提取原始文字。
本阶段用于低成本文字恢复，不声称已校验的表格单元格、OCR 置信度、券商对账单精度
或图表语义理解。OCR 原文**不得**作为权威决策结论。

可选的高影响结论二次校验、与其它 Agent 工具共享的预算/限流计量仍在 issue #196
跟踪中。

## 路径选择

| 路径 | 图像字节 | 结果 | 适用 |
| --- | --- | --- | --- |
| `extract_image_text` | 留在本机 | 脱敏后的不可信原始文字 + 目标类型标签 | 截图、公告页、表格型对账单、图表标注、内嵌位图 PDF 页 |
| `read_price_chart` | 发给配置的 Vision 模型 | 图表语义 | K 线趋势/价位 |
| `parse_financial_pdf` | 留在本机 | 文本层抽取 | 非光栅/文本层 PDF |

## 目标类型 `document_kind`

| 值 | 输入 | 结构提示 |
| --- | --- | --- |
| `screenshot` | 图片 | 仅原文 |
| `filing_page` | 图片或内嵌位图 PDF 页 | 仅原文；文本层 PDF 请用 `parse_financial_pdf` |
| `table_statement` | 表格型图片 | 未验证的空白分隔候选行 |
| `chart_annotation` | 图表截图 | 稀疏标注 token；语义图表仍用 `read_price_chart` |
| `pdf_page` | 含内嵌图的 PDF | `page_index` 页首个内嵌图；无内嵌图则显式失败 |

## 信任与治理

- 结果带不可信文档信封（`untrusted_user_document` / `authoritative_for_decisions=false`）。
- 成功 OCR 后同一会话轮次内 follow-on 工具被围栏，需新的用户授权。
- 仅经 ToolSurface / BoundToolSession 白名单可调用；文档文本不能授予能力。
- 审计摘要不落完整对账单/OCR 原文。
- 配置与安装命令见英文文档 `docs/agent-ocr-tool_EN.md` 与 `.env.example`。

`builtin.ocr` 仅在开关、文件根、`requirements-ocr.txt`、系统 Tesseract 与语言包全部就绪后注册 `extract_image_text`。
