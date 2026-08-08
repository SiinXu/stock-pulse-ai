# 财报电话会转录解析

StockPulse 可将**用户提供的**财报电话会转录解析为结构化分段、Q&A 轮次，以及**可溯源到原文**的数字指标。这是 issue #253 在 phase 1（PDF/图表，PR #844）之后剩余的后端能力项。

自动从第三方拉取转录、HTTP 上传 UI、默认分析路径 / 报告证据链投影**不在**本模块范围。

完整契约（诚实抽取、配置门闩、输出字段、数据源策略）见英文版：
[earnings-transcript-parsing_EN.md](earnings-transcript-parsing_EN.md)。

## 快速配置

```bash
MULTIMODAL_AGENT_TOOLS_ENABLED=false
# MULTIMODAL_FILE_ROOT=/absolute/path/to/multimodal-uploads
```

启用并配置文件根后重启进程，Agent 可调用工具 `parse_earnings_transcript`。

## 与 PDF 解析的关系

- 路径沙箱复用 `pdf_parsing_service.resolve_safe_file_path`
- PDF 转录先走 PDF 文本抽取，再进入转录结构化管线
- 分块与 Q&A/数字抽取为转录专用逻辑，不平行复制 PDF 表格启发式

## 回滚

关闭 `MULTIMODAL_AGENT_TOOLS_ENABLED` 并重启，或 revert 引入该能力的 PR。
