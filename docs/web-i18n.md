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
```

每个领域字典必须以 `Record<UiLanguage, ...>` 或等价的类型约束保证语言结构一致。新增语言时，先扩展 `UiLanguage`，再为每个领域补齐同一组 key；不得在 JSX 中批量新增 `language === 'en' ? ... : ...`。

插值统一使用命名参数，例如 `{count}`、`{name}`。中英文的参数集合必须完全一致。动态服务端值只能在明确允许原文显示的字段中回退。

## 错误与格式化

面向 Web 的后端错误应提供稳定 `error` code、诊断 `message` 和结构化 `details`。前端按 code 映射本地化主错误；原始 message 只进入可展开诊断，不能在英文界面直接作为中文主提示。

日期、数字、货币和列表使用 `src/utils/uiLocale.ts`。显示 locale 与市场业务时区分离；ISO 表单值、股票代码和模型 ID 不做本地化。

## 验证

```bash
cd apps/dsa-web
npm run test:i18n
npm run test
npx tsc -b
npm run build
npx playwright test e2e/i18n.spec.ts
```

`test:i18n` 会检查中英文 key、空翻译、插值参数、重复 key，并扫描生产 TSX 的硬编码中文界面文案。允许项必须按具体文件和用途精确登记，禁止整目录忽略。
