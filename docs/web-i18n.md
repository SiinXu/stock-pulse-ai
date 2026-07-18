# Web 国际化开发约定

StockPulse Web 的界面语言与报告语言是两套独立语义。

当前界面支持简体中文、繁體中文、English、日本語、한국어、Deutsch、Español、Bahasa Melayu、Français 和 Bahasa Indonesia。首次访问按浏览器语言选择；用户手动选择后以 `dsa.uiLanguage` 为准。繁体中文会识别 `zh-TW`、`zh-HK`、`zh-MO` 和 `zh-Hant`，印尼语兼容旧浏览器的 `in-*` 标识。

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

语言清单与 HTML/Intl locale 元数据集中在 `src/i18n/uiLanguages.ts`。新增的完整语言资源位于 `src/i18n/translations/`，以稳定的 `namespace.path` 为 key；每种语言文件都受同一个 `UiTranslationKey` 类型约束。8 个新增语言包按需加载，避免全部翻译进入首屏 bundle。`createUiLanguageRecord()` 将已有中英文领域结构投影到完整语言集合，缺少任一翻译 key、英文源文案与资源清单不一致，或资源清单含有已删除的 key，都会在资源校验、模块加载或 `test:i18n` 阶段直接失败，不会静默回退成英文。

设置字段标题按配置字段 key 使用 `utils.systemConfigI18n.fieldTitleMaps` 中的独立稳定资源；不能把可能被多个字段共享的 `helpKey` 标题当作字段身份。英文界面继续显示后端实时 Schema 标题，其余已知语言必须命中字段标题目录。新增或删除 `src/core/config_registry.py` 字段时，需同步该目录及全部语言资源；后端契约测试会校验字段注册表与前端标题目录完全一致。只有后端动态返回且目录未知的字段才允许显示 Schema 原文。

每个领域字典必须以 `Record<UiLanguage, ...>` 或等价的类型约束保证语言结构一致。新增语言时，先扩展语言 catalog，再为每个领域补齐同一组稳定 key；不得在 JSX 中批量新增 `language === 'en' ? ... : ...`。`value`、`filename`、`id`、`key`、`href`、`url`、`route`、`path` 字段属于契约值并保持原样，股票代码和模型路由也不得作为普通文案翻译；只翻译用户可见 label。

插值统一使用命名参数，例如 `{count}`、`{name}`。中英文的参数集合必须完全一致。动态服务端值只能在明确允许原文显示的字段中回退。

## 错误与格式化

面向 Web 的后端错误使用统一 envelope：`error` 是稳定业务码，`params` 是本地化插值参数，`message`、`details` 和可选 `trace_id` 只提供诊断信息。过渡期内响应还会输出 deprecated、read-only 的 `detail`，它始终是 `details` 的同值别名而不是第二份来源；字段只能在未来 major 或 versioned API 中移除。新客户端优先读取 `details`，旧客户端继续读取 `detail`，5xx 的两个字段都不会承载原始异常。前端按 UI language 将 `error + params` 映射为主错误；未知 code 显示通用本地化错误，legacy 裸字符串通过兼容适配器保留到 Details，不能直接成为主提示。

Agent 会话历史遵循同一契约。失败记录由历史 API 返回安全的兼容 `content`，并通过 `error + params` 标识可本地化的失败；普通消息不携带这两个字段。Web 必须在渲染时按当前 UI language 解析错误，且消息显示、单条复制和会话导出必须复用同一份解析结果，确保切换语言后已加载的历史立即更新。服务端会将历史 `[分析失败]...` 记录适配为稳定错误码；新失败不得把 Provider 原始错误写入历史或返回给客户端。

诊断回退必须保持分层：已知 `error` 使用对应本地化文案和 `params`；未知 `error` 使用通用本地化错误；legacy 原始字符串、`message`、`details` 和 `trace_id` 只能保留在诊断入口，不能提升为主错误文案。历史记录的安全 `content` 仅用于旧客户端兼容，不能覆盖稳定错误码的本地化结果。

任务的 SSE、轮询和 POST 响应使用稳定 `message_code` 与 `message_params`。组件应在渲染时按当前 UI language 格式化任务消息，确保切换语言后已有任务立即更新；服务端 legacy `message` 只作为兼容诊断，不能绕过本地化成为主状态文案。

日期、数字、货币和列表使用 `src/utils/uiLocale.ts`。显示 locale 与市场业务时区分离；ISO 表单值、股票代码和模型 ID 不做本地化。

语言选择器使用原生 `select` 语义，必须保留十个语言的本地名称、键盘操作和读屏 label。切换语言时同时更新 React 文案、`localStorage` 和 `<html lang>`；应用挂载前也会同步已保存语言，避免首帧语言标记错误。

## Overlay 与可访问性文案

`Modal`、`Drawer`、`ConfirmDialog` 和移动历史面板共用 Overlay stack。只允许最顶层响应 Escape 和 Tab，打开时隔离背景并锁定滚动，关闭后恢复焦点；标题、说明、关闭按钮、aria label 和 pending 状态均属于 UI language。报告正文位于 Overlay 内时仍遵循 report language，Overlay chrome 不随报告语言切换。

## 验证

```bash
cd apps/dsa-web
npm run i18n:resources
npm run test:i18n
npm run test
npx tsc -b
npm run build
npm run test:smoke
```

`npm run i18n:resources` 默认只读：它通过项目已有的 `esbuild` 在临时目录加载所有 `createUiLanguageRecord()` 源字典，检查英文稳定 key/源文案及 8 个新增语言资源的文件名、完整 key、非空值和插值参数，不需要在线翻译服务或本机专有路径。修改源文案或 key 后，运行 `npm run i18n:resources -- --write` 只会确定性重写 `src/i18n/translations/en.ts`；它不会生成或覆盖其它语言翻译。维护者仍需人工补齐并审查受影响语言，校验会持续失败直到全部资源重新一致。

`test:i18n` 会检查全部十种界面语言的稳定 key、空翻译、NFC、插值参数、零宽字符/生成标记、重复 key，并扫描生产 TSX 中中英文用户可见的 JSX 文本/表达式、模板字符串、`aria-label`、`aria-description`、`alt`、`placeholder`、`title`、`label`、`message`、`description`、通知/错误 setter、toast 和 document title。扫描器会解析本地 `const` 的直接或间接引用（包括别名与嵌套解构）、对象属性、对象 spread 与 JSX spread，避免硬编码文案通过中间变量绕过检查；动态值和可变绑定不会被当作静态文案。允许项必须按具体文件、字符串、语境和用途精确登记，并保持仍被实际使用；禁止整目录或整文件忽略。Playwright 场景应使用独立、可读的 test 名称和关键断言，不得用循环或注释编号代替语义覆盖。
