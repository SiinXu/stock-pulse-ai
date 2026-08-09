# 财报电话会转录解析

StockPulse 可对**用户提供的**财报电话会文本和本地转录文件进行确定性解析，输出有界、可溯源的结构化结果。自动从第三方拉取转录、HTTP 上传 UI 以及默认报告链路投影仍不在本能力范围内。

## 信任、隐私与出站边界

转录内容被标记为 `untrusted_user_document`。文档中的指令不能授予权限、改变股票范围、重定向 Agent、绕过 Local Only 模式或自动触发其他工具。该工具只读，并且只有声明的 `multimodal:read` 能力。

解析过程在本地执行，但紧凑的工具结果会进入 Agent 上下文，因此可能到达已配置的远程模型。若要求模型内容零非回环出站，请启用 `LOCAL_ONLY_MODE=true`。工具审计和诊断只保留有界元数据与内容摘要，不保留内联转录原文或结果摘录；解析器本身也不持久化原文。

操作者必须在提交前对来源进行分类，并确认自己有权处理。除非目标模型供应商、保留策略和操作者同意均允许，否则不要提交重大非公开信息、PII 或密钥；不需要的敏感字段应先脱敏。

## 来源与诚实契约

| 表面 | 契约 |
| --- | --- |
| 内联文本 | `start_char` / `end_char` 直接索引用户提交的原始 Python 字符串；不裁剪首尾空白，也不改写 CRLF/CR。 |
| 文本文件 | 文件只打开一次，必须是普通文件，以“上限 + 1 字节”读取，并严格按 UTF-8 或带 BOM 的 UTF-8 解码；非法 UTF-8 返回 `unsupported_encoding` 和原始字节摘要。 |
| PDF | 坐标索引确定性抽取出的 PDF 派生文本；`source.page_map` 与证据中的页内坐标可回映到抽取页，并分别记录 PDF 原始字节和派生文本 SHA-256。 |
| 指标 | 只有明确的财务标签—关系—数值结构才算语义指标；年份、电话/账户标识和无标签数字不会被标为已验证指标。`value_text` 仍必须等于原文精确切片。 |
| Q&A | 问题和回答摘要明确标记为经过空白折叠的派生字段；只附带有界精确摘录，不重复完整回答。 |
| 管理层语气 | 可选、主观、识别否定，只统计 `prepared_remarks`，不把分析师在 Q&A 中的用词算作管理层语气。 |
| 缺失值 | 保持缺失；不编造、不四舍五入、不换算出新的数字。 |

所有结果使用 `earnings-transcript-v2`，包含研究用途免责声明和类型化 `trust` 信任信封。

## 紧凑结果与按块检索

服务序列化结果必须是有效 JSON，硬上限为 96 KiB；原生 Agent 会话在结果进入下一条模型消息前再施加 128 KiB 防御上限。

首次返回的 `chunks[]` 只包含索引、精确坐标、长度和 SHA-256，不重复完整转录。需要原文时，以相同来源和已公布的 `chunk_index` 再次调用同一工具；响应只包含所选精确块，并受 `max_chunk_chars <= 6000` 限制。若其他结构仍超过预算，会按确定顺序删除 Q&A、前瞻信息、指标、块和分段，并通过 `result_budget` 报告省略数量，绝不返回被字节截断的残缺 JSON。

转录结果进入绑定 Agent 会话后，会话围栏只允许继续调用 `parse_earnings_transcript` 读取块。任何其他工具都会以 `untrusted_document_follow_on_denied` 拒绝；必须由新的用户回合重新授权。因此，即使模型复述了文档内指令，也不能由该文档启动后续动作。

## 注册与配置

`parse_earnings_transcript` 默认关闭，复用现有多模态门闩，不新增配置键。

| 条件 | 行为 |
| --- | --- |
| `MULTIMODAL_AGENT_TOOLS_ENABLED=false` | 不注册工具 |
| 已开启但无 `MULTIMODAL_FILE_ROOT` | 工具仍不注册 |
| 两者均配置并重启进程 | 注册内联文本和沙箱本地文件解析能力 |

```bash
MULTIMODAL_AGENT_TOOLS_ENABLED=false
# MULTIMODAL_FILE_ROOT=/absolute/path/to/multimodal-uploads
# LOCAL_ONLY_MODE=true  # 可选：禁止非回环模型出站
```

路径通过 `pdf_parsing_service.resolve_safe_file_path` 解析；拒绝 URL、主目录展开、目录穿越和配置根之外的路径。转录文件上限为 2 MiB，参与解析的文本前缀上限为 200,000 个字符。

## 输出摘要

- `status`、`reason_code`、`method`、`schema_version`
- `source`：净化后的文件名、大小、编码/坐标来源、SHA-256、截断状态，以及 PDF 页映射
- `segments[]`：管理层陈述、Q&A 或未知区段的精确坐标
- `qa_items[]`：有界派生问题/摘要和精确摘录证据
- `metrics[]`：类型化标签/数值关系、精确坐标、词法与语义验证标记
- `forward_looking[]`：有界指引/免责声明证据
- `management_tone`：可选且限定范围的主观判断
- `chunks[]` 与 `retrieval`：无正文索引，或一个明确请求的有界块
- `trust`、`result_budget` 与研究用途免责声明

## 数据源策略与回滚

支持内联文本以及本地 `.txt`、`.md`、`.pdf`；不支持自动 IR/供应商拉取或 HTTP 上传。

回滚时设置 `MULTIMODAL_AGENT_TOOLS_ENABLED=false` 并重启，或 revert 引入该能力的变更。不涉及数据库迁移。
