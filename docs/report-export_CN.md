# 报告导出（Markdown / PDF）

StockPulse 可以导出某条历史记录已经渲染完成的 Markdown，不会重新运行分析，也不会修改历史数据。Markdown 是无损归档格式；PDF 是可选、受资源上限保护的表现层转换。

English: [report-export.md](report-export.md)

## 本轮格式范围

| 格式 | 可用性 | 合同 |
| --- | --- | --- |
| Markdown (`.md`) | 始终可用 | 与现有历史 Markdown 接口完全一致的 UTF-8 内容 |
| PDF (`.pdf`) | 可选 | 需要通过验证的 fpdf2，以及覆盖报告全部可见字符的单字体 TTF/OTF |
| DOCX / XLSX | 未实现 | 保留为 Issue #163 后续范围 |

PDF 的依赖、字体解析、目标语言代表字符或字体/后端冒烟验证任一不通过时，能力接口都会如实报告不可用；Markdown 不受影响。

## 可选依赖

选择 fpdf2 是为了不把 Cairo/Pango 或无头浏览器加入默认安装。安装方式：

```bash
python -m pip install --build-constraint build-constraints.txt \
  -r requirements-report-export.txt
```

可选依赖文件精确锁定 `fpdf2==2.8.3`、`fonttools==4.63.0` 与
`markdown-it-py==4.2.0`，同时应用仓库 `constraints.txt`。三者均为惰性导入，因此未安装
PDF 套件时，默认应用仍可启动并使用无损 Markdown 导出。如果环境中存在占用同一 `fpdf`
导入命名空间的旧 PyFPDF，系统会拒绝启用 PDF，而不是误判为 fpdf2。

## 字体就绪合同

`REPORT_EXPORT_PDF_FONT_PATH` 由共享 Config 加载器和系统配置注册表统一管理，只接受单字体 `.ttf` / `.otf`。显式配置的无效路径会 fail-closed，不会悄悄切换到其他系统字体；未配置时只探测少量明确列出的单字体系统路径，不猜测 `.ttc` 字体集合下标。

字体验证分两层：

1. 能力接口解析字体，检查目标语言代表字符，并执行一次确定性的 fpdf2 冒烟渲染。
2. 每次 PDF 请求都检查该报告最终可见文本的全部字符。缺少任一字符时返回 `export_font_coverage_missing`，不会丢失图标或输出方框字。

例如 Arial Unicode 可能覆盖中文，却不覆盖报告常见的 `✅`、`⚠`、`🚨`、`📊`。绝对字体路径与解析器原始错误只进入脱敏后的运维日志，不会出现在公共能力或错误响应中。

## Markdown 到 PDF 的明确转换

导出器通过 `markdown-it-py` AST 处理内容，不再用正则解析图片：

- 标题、段落、引用、代码块、嵌套有序/无序列表和表格保留可见文字；
- 链接保留标签文字，移除目标地址；
- 图片完整移除目标地址和标题，不发起网络请求，保留 alt 与省略说明；
- 1 至 6 列表格按字体实测宽度换行，跨页重复表头，普通行优先整体移到下一页；
- 单行自身高于整页时允许分段，但不删除文字；
- 7 至 12 列表格使用完整的“表头：值”堆叠布局；
- 需要原始 Markdown 语法、链接或图片目标时，始终使用无损 `.md` 导出。

带嵌套括号、标题或签名查询参数的图片 URL 会作为完整目标被丢弃，不会残留密钥片段。

## 资源上限

| 上限 | 默认值 | 失败合同 |
| --- | ---: | --- |
| UTF-8 输入 | 1,000,000 字节 | 413 `export_input_too_large` |
| 页数 | 100 | 413 `export_page_limit_exceeded` |
| 单表行数 | 500 | 413 `export_table_rows_exceeded` |
| 单表列数 | 12 | 413 `export_table_columns_exceeded` |
| 表格总单元格 | 3,000 | 413 `export_table_cells_exceeded` |
| 单调时钟渲染期限 | 20 秒 | 503 `export_deadline_exceeded` |
| 单进程并发渲染 | 2 | 429 `export_busy` |

成功 PDF 使用有界进程内 LRU 缓存（12 项、24 MiB）；键包含 Markdown、标题和字体文件签名，导出器不会持久化 PDF。

## API

```http
GET /api/v1/history/export/capabilities?language=zh
GET /api/v1/history/{record_id}/export?format=md
GET /api/v1/history/{record_id}/export?format=pdf
```

能力语言限定为 `en | zh | zh-TW | ja | ko`，返回固定、类型化的 `md` / `pdf` 状态与公开上限，不包含字体路径。导出 `format` 是 OpenAPI 枚举 `md | pdf`，200 响应明确声明 `text/markdown` 与 `application/pdf` 二进制媒体类型。

下载头同时包含短 ASCII `filename=` 与有界 RFC 5987 `filename*=UTF-8''...`，Unicode 历史记录身份不会再触发 Starlette header 编码 500。

## Issue #163 剩余范围

- DOCX 结构化导出
- XLSX 评分/指标工作表
- 可选证据/审计附录开关（#127）
- 报告页与 DecisionSignal 的 Web 一键导出入口

本 PR 仅修改后端，不改报告模板、分析生成、Desktop、`pdf_parsing_service.py`、分享图或 `md2img`。
