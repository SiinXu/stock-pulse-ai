# 有界图片 OCR Agent 工具

StockPulse 可选用 Tesseract 从本地图片提取**原始文字**。`document_kind` 覆盖截图、公告/PDF 页图像、表格型对账单与图表标注；结果始终为不可信文档信封，**不得**作为权威决策结论。本工具仍不声称可靠表格单元格、OCR 置信度、对账单精度或 K 线语义（语义图表请用 `read_price_chart`）。高影响结论前的可选二次校验、与其它 Agent 工具共享的预算/限流仍开放。#218 仅作关联引用。

## 能力分工

| 路径 | 图片字节 | 结果 | 用途 |
| --- | --- | --- | --- |
| `extract_image_text` | 留在本机 | 脱敏后的不可信原始文字 | 有界文字/数字恢复 |
| `read_price_chart` | 发给配置的 Vision 模型 | 图表语义 | K 线趋势/价位 |
| 图片提股票 | 发给配置的 Vision 模型 | 股票代码/名称 | 标的提取 |
| PDF 解析 | 留在本机 | 既有文字层 | 非扫描 PDF |

## 目标类型

| `document_kind` | 用途 | 明确不声称 |
| --- | --- | --- |
| `screenshot` | 通用截图 | 版面结构 |
| `filing_page` / `pdf_page` | 公告/PDF 页图像（含嵌入位图 PDF） | 完整 PDF 文字层解析 |
| `table_statement` | 表格型对账单候选行 | 已校验单元格 |
| `chart_annotation` | 图表标注/价位标签 | K 线语义 |

成功 OCR 后，同一执行轮次内 BoundToolSession 会阻止 follow-on 工具，直至新的用户回合。

## 隐私与信任边界

“本地 OCR”仅表示**图片字节不离开主机**。返回文字会成为 Agent tool-result，可能发送给配置的模型。服务在返回前始终遮蔽受支持的邮箱、secret 赋值、券商/账户标识、带标签电话和中文身份证号；本服务不记录或持久化 OCR 原文。

脱敏是有界防护，并不能证明任意个人信息都已移除。要求零远端出站时，必须启用统一的 `LOCAL_ONLY_MODE=true` 并使用回环模型。启用默认关闭的 OCR 工具是当前 operator opt-in 边界；本阶段不实现逐用户同意或多租户数据所有权。

所有 OCR 文字都按攻击者可控文档数据处理。结果标记为 `untrusted_document_data`，明确禁止服从文档内指令或把它当成授权。工具权限仍由 ToolSurface 管理，文档文字不能授予 capability。

## 资源与文件边界

- 路径必须位于 `OCR_FILE_ROOT`（或 `MULTIMODAL_FILE_ROOT`）内。
- 解析后的路径只打开一次；拒绝非普通文件；最多读取 5 MiB + 1 字节；校验扩展名与图片签名。
- RGB 转换前由 Pillow 检查 header：宽/高最多 10,000，解码像素最多 25,000,000，只接受单帧；decompression-bomb 警告/错误一律拒绝。
- OCR 在独立进程组运行；1–120 秒 wall-clock 超时会终止并回收 worker 与 POSIX 子进程。
- 完整 JSON tool result 最多 32 KiB UTF-8；文字只保存一份，在合法 UTF-8 边界截断，并报告原始计数与截断状态。
- 来源只记录 MIME、字节数、尺寸、帧数、SHA-256、语言、引擎与版本，不暴露本地路径或文件名。

## 注册与安装

`builtin.ocr` 仅在开关、文件根、`requirements-ocr.txt`、系统 Tesseract 与语言包全部就绪后注册 `extract_image_text`。配置和安装命令见英文文档 `docs/agent-ocr-tool_EN.md` 与 `.env.example`。

默认 Docker/Desktop 包不安装 Tesseract 二进制或语言数据，operator 未自行安装并验证前视为不支持。合成 EN/ZH fixture 只证明注入 engine 输出下的安全信封；真实英文检查仅在主机已有 Tesseract 时可选运行，本阶段不声称已验证中文/密集表格质量。

## 回滚

设置 `OCR_AGENT_TOOL_ENABLED=false` 后重启，或 revert PR；无数据库迁移。
