# Web 国际化开发约定

StockPulse Web 的界面语言与报告语言是两套独立语义。

- **界面语言（UI language）**控制导航、按钮、表单、Modal/Drawer、提示、错误、可访问性文案、页面标题以及日期/数字/货币的显示 locale。
- **报告语言（report language）**控制模型生成的报告正文、正文结构和报告导出内容。
- 用户输入、股票与公司名称、新闻原文、模型 ID、第三方策略自由文本和原始诊断不会自动翻译。

因此，英文界面查看中文报告时，报告正文可以保持中文，但复制、刷新、关闭、诊断和其它外围操作必须保持英文。

## 翻译文件

不要把所有文案继续堆入单一字典。跨页面通用文案使用 `src/i18n/uiText.ts`；大型页面或业务域使用 `src/locales/` 下的领域文件，例如：

```text
locales/alerts.ts
locales/portfolio.ts
locales/screening.ts
locales/settingsPage.ts
locales/settingsModelAccess.ts
locales/reportChrome.ts
locales/reportContent.ts
```

每个领域字典必须以 `Record<UiLanguage, ...>` 或等价的类型约束保证语言结构一致。新增语言时，先扩展 `UiLanguage`，再为每个领域补齐同一组 key；不得在 JSX 中批量新增 `language === 'en' ? ... : ...`。

插值统一使用命名参数，例如 `{count}`、`{name}`。中英文的参数集合必须完全一致。动态服务端值只能在明确允许原文显示的字段中回退。

## 错误与格式化

面向 Web 的后端错误使用统一 envelope：`error` 是稳定业务码，`params` 是本地化插值参数，`message`、`details` 和可选 `trace_id` 只提供诊断信息。前端按 UI language 将 `error + params` 映射为主错误；未知 code 显示通用本地化错误，legacy 裸字符串通过兼容适配器保留到 Details，不能直接成为主提示。

任务的 SSE、轮询和 POST 响应使用稳定 `message_code` 与 `message_params`。组件应在渲染时按当前 UI language 格式化任务消息，确保切换语言后已有任务立即更新；服务端 legacy `message` 只作为兼容诊断，不能绕过本地化成为主状态文案。

日期、数字、货币和列表使用 `src/utils/uiLocale.ts`。显示 locale 与市场业务时区分离；ISO 表单值、股票代码和模型 ID 不做本地化。

## Overlay 与可访问性文案

`Modal`、`Drawer`、`ConfirmDialog` 和移动历史面板共用 Overlay stack。只允许最顶层响应 Escape 和 Tab，打开时隔离背景并锁定滚动，关闭后恢复焦点；标题、说明、关闭按钮、aria label 和 pending 状态均属于 UI language。报告正文位于 Overlay 内时仍遵循 report language，Overlay chrome 不随报告语言切换。

## 验证

```bash
cd apps/dsa-web
npm run test:i18n
npm run test
npx tsc -b
npm run build
npm run test:smoke
```

`test:i18n` 会检查中英文 key、空翻译、插值参数、重复 key，并扫描生产 TSX 的 JSXText、字符串、模板字符串、aria、placeholder、title、toast 和 document title。允许项必须按具体文件、字符串和用途精确登记，禁止整目录或整文件忽略。Playwright 场景应使用独立、可读的 test 名称和关键断言，不得用循环或注释编号代替语义覆盖。
