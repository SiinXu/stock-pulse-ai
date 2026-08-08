# 离线图片 OCR Agent 工具

StockPulse 可用**离线 OCR**（Tesseract）从本地图片提取原始文字与数字。这与会把图片发给云端模型的多模态 Vision 工具不同。

Issue：#196。与 #218 离线/隐私诉求部分相关（本工具只做本地图像文字提取）。

## 取舍：为何在 multimodal 之外仍需要 OCR

| 路径 | 网络 | 适用 |
| --- | --- | --- |
| **OCR** `extract_image_text` | 无 | 密集数字、对账单、隐私截图 |
| 图表阅读 `read_price_chart` | Vision API | K 线语义理解 |
| 图片提股票 | Vision API | 股票代码/名称 |
| PDF 解析 | 无 | 文本层 PDF |

OCR **不是**图表阅读的平行实现。

## 注册契约

门禁：`OCR_AGENT_TOOL_ENABLED=true` + 文件根 + `requirements-ocr.txt` + 系统 Tesseract。
任一失败则不注册。注册走 `builtin.ocr` 插件与 `agent_tool` 扩展点（同 Kronos），只调用 `register`。

## 配置与安装

见 `.env.example` 与 `docs/agent-ocr-tool_EN.md`。简体中文需 `chi_sim` 语言包。

## 回滚

`OCR_AGENT_TOOL_ENABLED=false` 后重启，或 revert PR。
