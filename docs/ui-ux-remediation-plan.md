# StockPulse Web UI/UX 系统性修复计划

## 1. 状态、执行基线与证据

### 1.1 文档状态

- 状态：已执行完成；Batch 0-6 的代码迁移、守卫、单元/构建/安全/Playwright 验收和本地视觉证据均已完成。人工 200% zoom、真实软键盘和读屏器巡检不属于自动化证明范围，列为发布前人工复核项。
- 审查日期：2026-07-19。
- 审查范围：\`apps/dsa-web/\` 的页面、公共组件、领域组件、样式、单元测试与 Playwright 测试。
- 本轮范围：完成 Batch 0-6 的 Web UI/UX 修复；保留 Shell 与页面级大卡片，不改 API、配置 key、路由和持久化契约；未提交，未推送。
- 本文是实施入口，不以旧审查中的静态数字替代当前代码事实。

### 1.2 Git 与代码基线

| 项目 | 基线 |
| --- | --- |
| 当前分支 | \`pull-main-and-start\` |
| 当前工作树 HEAD | \`c2f5bace\` |
| 当前远端基线 | \`origin/main@50514720\` |
| 当前分支相对 \`origin/main\` | 9 个提交领先，18 个提交落后 |
| 未直接更新工作树原因 | 当前历史无法 fast-forward 且工作树包含本轮改动；未获授权前不能通过 merge、rebase、stash 或 reset 改变代码基线 |
| 基线处理 | 工作树有本轮 UI 修复，未 merge/rebase/reset；验收基于当前 HEAD 与工作树 |

实施任何 Batch 前必须重新执行：

\`\`\`bash
git status --short --branch
git fetch --all --prune
git diff --stat origin/main...
git diff -- apps/dsa-web
\`\`\`

若实施分支不能安全 fast-forward，应先决定 merge 或 rebase，不得把基线同步和 UI 修复混在同一个提交中。

### 1.3 证据来源与可信度

| 证据 | 状态 | 用途 |
| --- | --- | --- |
| 当前 Web 源码和测试 | 已逐项复核 | 页面结构、组件调用、硬编码、响应式和交互契约 |
| \`rg\` 静态统计 | 已执行 | 识别原生控件、重复表格、未使用 Pattern、样式泄漏和硬编码层级 |
| Figma MCP | 已读取 | 核对 Switch、Checkbox、Tabs、Search、Badge、Icon、Notification、Profile、Button 的 Dev Mode 结构与状态 |
| Figma 节点截图 | 已查看，保存在 gitignored 的 \`.context/ui-ux-plan-figma/\` | 设计参考，不作为仓库产物 |
| 本地应用浏览器截图 | 已完成 | 独立 Playwright 合成数据环境采集 11 路由 × 8 视口 × 2 主题，共 176 张，保存在 gitignored 的 \`.context/ui-ux-remediation-acceptance/\` |
| 旧 UI/UX 审查文档 | 当前仓库未找到原文件 | 仅使用任务附件中的结论，并以当前代码重新核验 |

已复核的 Figma 节点：

- Dashboard Light：\`535:9696\`
- Dashboard Dark：\`516:9954\`
- Portfolio：\`789:23658\`
- Watchlist Empty：\`348:8267\`
- Switch：\`225:3167\`
- Checkbox：\`235:2137\`
- Tabs：\`1047:21655\`、\`1051:20271\`
- Search：\`1051:20226\`
- Badge：\`1051:20210\`
- Icon：\`1047:21919\`
- Notification：\`956:22925\`
- Profile：\`1031:17853\`
- Button：\`1051:20279\`

### 1.4 本轮视觉证据与边界

- Conductor in-app Browser 没有可用实例，因此按 Browser skill 的故障处理边界改用独立 Playwright。
- \`.context/ui-ux-remediation-acceptance/manifest.json\` 记录 176 个文件，\`failures\`、\`missingFiles\`、\`documentOverflow\` 均为空；截图不入库。
- 完整 smoke 另行验证 320px CTA、390px 全一级路由无横溢、Light/Dark 对比度、Settings/Chat 控件尺寸及 767/768/900/1024 双侧栏边界。
- 自动化未替代真实设备上的 200% zoom、软键盘和读屏器人工巡检；发布前仍应按 13.2 的 Manual a11y 行执行一次。

## 2. 目标、非目标与设计原则

### 2.1 目标

1. 建立稳定、可复用、可测试的 Primitive 和跨页面 Pattern，消除页面内平行实现。
2. 修复会损害信任的语义错误，包括错误的 TLS 提示、API Key 自动填充、动作标签不一致和未本地化的运行状态。
3. 让 320px 至桌面视口的导航、筛选、表格、抽屉和操作区保持可理解、可触达、无横向页面溢出。
4. 用领域状态替代“零值仪表盘”和重复空卡，明确 Loading、Empty、Error、Disabled、Partial、Ready。
5. 通过守卫、单元测试、交互测试和截图证据阻止新硬编码与公共组件绕过。

### 2.2 非目标

- 不把 StockPulse 重做成 Figma 示例产品，不复制其品牌、文案、信息架构或像素坐标。
- 不在 UI 修复中重写后端业务、分析算法或数据模型。
- 不一次性替换全部页面；每个 PR 必须可独立验证和回滚。
- 不为统一而删除确有领域语义的组件。
- 不引入第二套 CSS 框架、表单框架或并行设计系统。
- 不以增加圆角、阴影、渐变或卡片数量作为“优化”。

### 2.3 设计原则

- **先契约后外观**：先统一状态、事件、焦点、错误和数据语义，再调整视觉。
- **页面是布局，组件是行为**：页面负责信息层级，公共组件负责交互和视觉状态。
- **卡片层级有语义**：保留 Shell、页面级主卡片和确需框定的独立对象；普通子区块优先用留白、分隔线和标题，避免无意义的 card-in-card。
- **一层主导航**：768 至 1023px 不同时展示全局抽屉逻辑和第二条固定业务侧栏。
- **操作与结果就近**：筛选操作、错误、加载进度、空状态 CTA 与其作用域保持邻近。
- **响应式是结构变化**：窄屏应折叠、转 Sheet、切换列表或隐藏次要列，不能只缩小间距。
- **主题使用语义 token**：禁止通过 raw white、hex 或领域 class 模拟主题。
- **触控和密度并存**：交互热区至少 44px；视觉图标可以更小，不能用超大可见按钮填满紧凑工具栏。
- **可见控件保持紧凑**：桌面常规可见高度以 32-40px 档位表达；44px 是触控热区，不等于所有控件都有 44px 实色背景。
- **单一主操作**：每页或每个独立表单区域最多一个高对比 Primary；普通按钮不使用胶囊，胶囊仅用于 chip、status 和 segmented item。
- **颜色语义分离**：品牌交互色、成功色、A 股涨跌色和国际市场涨跌色分别定义，不共用一个“绿色”状态。
- **可信文案**：只有在运行时可证明的安全、连接、成功状态才可展示。

## 3. 当前实现复核与差异

### 3.1 当前规模快照

| 指标 | 当前值 | 结论 |
| --- | ---: | --- |
| 页面文件 | 11 | 7 个常规业务页统一；Home、Chat、Login 为专用布局，NotFound 使用最小 AppPage |
| 使用 \`AppPage\` 的页面 | 8/11 | 7 个常规业务页加 NotFound；Home、Chat、Login 的例外由页面布局守卫记录 |
| 使用 \`PageHeader\` 的页面 | 7/11 | 常规业务页标题层级已统一；专用工作区保留领域标题结构 |
| 超过 1500 行的页面 | 6 | Home、Chat、Portfolio、DecisionSignals、StockScreening、Settings |
| \`SettingsPage.tsx\` | 2943 行 | 调度与首次配置已拆为领域组件；页面仍承担配置状态协调，不作为本轮视觉阻断项 |
| \`LLMChannelEditor.tsx\` | 3586 行 | 仍是后续可维护性拆分候选；其 Modal、Field、Select 与保存契约已统一 |
| \`index.css\` | 2670 行 | raw palette、无效 surface 和跨领域 class 守卫已清零；后续可按领域继续拆文件 |
| 公共 Pattern 调用 | \`DataTable\` 12 个生产文件、\`Toolbar\` 2、\`Section\` 4、\`StickyActionBar\` 2 | 已由多个领域验证，不是单页包装 |
| 公共目录外原生控件 | 0 | UI 架构守卫禁止 page/domain 绕过共享交互组件 |
| 独立 table 实现 | 0 | 生产代码唯一 \`table\` 位于共享 DataTable |
| \`border-dashed\` | 1 | 仅保留 IntelligentImport 的文件拖放区，不再用于空状态卡片 |
| 手绘操作图标 | 0 | 操作图标统一 Lucide；仅保留趋势线、Run Flow、ScoreGauge、Spinner 等真实可视化 SVG |
| 迁移 allowlist | 0 | native control、raw palette、无效 surface、overlay z、跨域 class、展示文本状态判断债务表均为空 |

这些数字用于定位，不是“全部替换”的完成指标。完成标准以调用边界、交互契约和验收证据为准。

### 3.2 旧结论复核

| 旧结论 | 当前证据 | 状态 |
| --- | --- | --- |
| Button 默认是胶囊圆角 | 尺寸现为 \`rounded-lg\` | 已修复 |
| 设计守卫无法解析 Button variant map | \`productionDesignGuard.test.ts\` 已使用 AST 解析共享 Button alias/style map | 已修复 |
| PageHeader 仅 3 个页面使用 | 当前 7 个常规业务页全部使用 | Batch 2 已修复 |
| 登录页声明 TLS 安全连接 | 已按 HTTPS、localhost HTTP、非 localhost HTTP 区分可信连接文案 | Batch 0 已修复 |
| API Key 可能被密码管理器错误填充 | LLM 编辑器与 FirstRunWizard 已使用独立 \`name\` 和 \`autocomplete="new-password"\` | Batch 0 已修复 |
| 报告动作与历史动作语义不一致 | 报告 Hero 已优先使用结构化 action，自由文本仅作补充说明 | Batch 0 已修复 |
| Chat 状态存在英文 fallback | stage code 已统一映射 i18n，十语言资源一致性门禁通过 | Batch 3 已修复 |
| LLM 访问问题依赖中文字符串 | 模型访问问题已改为 typed code，翻译只在渲染层执行 | Batch 0 已修复 |
| Drawer eyebrow 固定为“详情视图” | eyebrow 已改为显式可选 | Batch 1 已修复 |
| dialog focusable 过滤可靠 | 已同时检查可见矩形、样式和 inert/hidden 祖先 | Batch 1 已修复 |
| Shell 主内容被大卡片包裹 | 保留 rounded border shadow 壳层 | 已确认为产品视觉要求，不再作为缺陷 |
| 768px 导航层级冲突 | Home/Chat rail 在中间视口转 Drawer，Settings 分类转 Select；767/768/900/1024 自动化断言通过 | Batch 3 已修复 |
| 零数据页面展示完整零值仪表盘 | Portfolio 无账户、Token Usage 零调用、Backtest 未运行均改为单一 StatePanel/阶段状态 | Batch 4/5 已修复 |

### 3.3 Figma 参考采用矩阵

| 参考模式 | StockPulse 目标模块 | 采纳内容 | 拒绝照搬内容 | 公共组件/token | 响应式变化 | 验收证据 |
| --- | --- | --- | --- | --- | --- | --- |
| Dashboard Light/Dark | Home、Shell | 摘要优先、主内容与辅助信息层级、克制分隔 | 不复制两套不一致的像素布局、品牌绿和绝对定位 | AppPage、PageHeader、Surface、Section、semantic color | 桌面可双栏；平板只保留主内容；移动单列 | 8 视口、双主题、Ready/Loading/Error |
| Portfolio | Portfolio | 顶部摘要、一个核心分布图、扁平持仓表 | 不展示无账户时的零值仪表盘，不复制币种字段 | MetricGroup、DataTable、StatePanel | 图表与表格顺序重排；移动表格转摘要行/详情 | 无账户、空账户、有数据、错误 |
| Watchlist Empty | Screening、Portfolio、Alerts | 单一中心状态、明确 CTA、减少空卡重复 | 不复制插画资产和文案 | StatePanel、EmptyState compatibility | 移动端 CTA 满可用宽度但不超大 | Empty/Disabled 截图和键盘测试 |
| Component Library | 全局 Primitive | 明确尺寸、状态、主题与禁用变体 | 不导入 raw hex、负字距、低对比、全胶囊化 | Button、IconButton、InputPrimitive、Switch、Checkbox、Badge | 触控热区 44px，视觉密度按场景变化 | Story/测试页、状态矩阵截图 |
| Sidebar/Profile Panel | Shell | 底部单一 Profile 入口，语言和主题进入菜单 | 其他账户功能保持 disabled/placeholder，不伪造能力 | ProfileMenu、Menu、Theme/Locale controls | 桌面 popover，移动 bottom sheet | 键盘、Escape、外部点击、双主题 |
| Notification Panel | Alerts、Shell | 列表状态、已读/未读层级、空状态 | 不在没有通知数据契约时制造全局中心 | NotificationPanel、Badge、StatePanel | 桌面 popover，移动全宽 sheet | 空/有数据/网络错误 |
| Segmented Control/Tabs | Settings、Dashboard 子视图 | 选中态、可滚动标签、键盘箭头行为 | 不把跨页面导航伪装成 Tab | Tabs、SegmentedControl | 窄屏横向滚动且保持 active 可见 | aria/键盘/长文本/中文英文 |

实现采用的是语义适配而非像素复制：Switch 使用 40×24 轨道和 20px thumb，Checkbox 使用 24px 原生 input 语义；Tabs 使用 Figma 的 segmented 层级与键盘模型。Figma Button 的全胶囊外观未照搬，普通命令按钮按本项目规则保留 8px 圆角；Notification 只有展示 Pattern，因没有全局未读数据 API 而未接入 Shell。\`MARKET_REVIEW_COLOR_SCHEME\` 是有限枚举，继续使用共享 Select，不为它制造自由 ColorPicker。

### 3.4 实施后结构结论

1. **Primitive 已形成唯一入口**：page/domain 的原生 button/input/select/textarea 为 0，ref、Field 描述、错误和输入语义由共享层负责。
2. **Pattern 已有跨领域调用**：DataTable、Toolbar、Section、StickyActionBar、ResponsiveFilterPanel 和 StatePanel 均有生产调用与测试。
3. **领域泄漏已清理**：Chat、Run Flow、Task 不再依赖 \`home-*\`；共享 Button 不再携带 settings 领域 variant。
4. **Overlay 契约已统一**：Modal、Drawer、Select、SearchableSelect、Picker、Tooltip、Toast 使用统一层级和焦点恢复逻辑。
5. **主题 token 守卫已清零**：raw white/palette、无效 \`bg-surface\` 和硬编码 overlay z 无迁移债务。
6. **状态与表格已唯一化**：旧 EmptyState/DashboardStateBlock 已删除，所有生产 table 经 DataTable 输出。
7. **大卡片保留是明确产品决策**：Shell 与页面级 Card 保留；修复只移除无语义嵌套，不将页面扁平化为无边界画布。
8. **剩余是可维护性而非交互阻断**：SettingsPage、LLMChannelEditor 和 index.css 仍较大，后续拆分必须保持现有状态/API 契约，不应与本轮 UI 验收混为一谈。

## 4. 目标组件架构与依赖关系

### 4.1 分层边界

\`\`\`text
tokens
  -> primitives
    -> cross-page patterns
      -> domain components
        -> pages
\`\`\`

- tokens：颜色、圆角、间距、层级、动效、focus ring、控件高度。
- primitives：无领域文案和领域 class，负责基础交互与 accessibility。
- patterns：组合 Primitive，表达 Field、State、Toolbar、DataTable、Overlay 等跨页面结构。
- domain components：持仓、选股、建议、模型渠道等业务语义。
- pages：路由数据、页面编排和响应式信息层级。

页面不得反向把 \`home-*\`、\`settings-*\` 或页面文案注入 Primitive 的固定 variant。兼容 alias 仅用于迁移期，并必须有删除条件。

### 4.2 Primitive 迁移表

| Primitive | 当前问题 | 目标 API/行为 | 首批调用方 | 兼容策略 | 测试 | 删除条件 |
| --- | --- | --- | --- | --- | --- | --- |
| Button | \`React.FC\`、领域 variant、重复 alias | \`forwardRef<HTMLButtonElement>\`；\`intent=primary/secondary/tertiary/danger\`、size、loading、icon 明确；普通按钮 8-10px 圆角；默认 type 安全 | Settings、Login、Error Boundary | 保留旧 variant alias 一期并输出测试覆盖，不改变 DOM 事件 | variant、disabled、loading、ref、form type | Batch 5 后无旧 alias 调用 |
| IconButton | 75 处 h-11/w-11 组合中混有图标操作 | 独立 \`label\` 必填，支持 tooltip、loading、danger、pressed、badge；视觉图标与 44px 热区分离 | Shell、表格行操作、帮助按钮 | 原 Button icon-only 可继续工作 | aria-label、tooltip、pressed、loading、touch target | Batch 6 无手写图标按钮 |
| InputPrimitive | Input/Select/Search 结构和 ref 不一致 | ref、name、autocomplete、\`density=compact/default\`、invalid、describedBy、leading/trailing/unit slot，并透传合理原生 aria/data 属性 | Login、LLM、Settings | 旧 Input props 透传 | password manager、focus、error linkage | 所有敏感输入显式 autocomplete |
| Field/Textarea | label/help/error 分散 | Field 统一 label、required、description、error、unit、trailing action；Textarea 使用同一控制边界并 forwardRef | Portfolio account、Settings、Chat | 允许既有 label 逐页迁移 | error id、aria-invalid、submit focus | Batch 5 无 placeholder 代替错误 |
| Surface | Card default/bordered 相同，页面 card 过多 | \`level=0/1/2\`、padding、bordered、elevated、\`as\`；L0 无边框阴影，L1 克制分区，L2 仅交互对象/浮层 | Shell、Home、Settings | Card 保留，内部映射到 Surface | theme、nested-surface guard | Batch 6 删除重复 Card variant |
| StatePanel | EmptyState/DashboardStateBlock/局部虚线空态平行 | \`state=empty/loading/error/blocked\`、\`density=inline/section/page\`，可扩展 disabled/partial，支持 action/details/retry且默认不创建 Card | Portfolio、Usage、Screening | 两旧组件先转发到 StatePanel | 状态、CTA、details disclosure | Batch 5 无平行状态实现 |
| Alert | InlineAlert、SettingsAlert、ApiErrorAlert 外壳分裂，错误详情和关闭按钮过重 | 合并外壳；保留 API error localization/details；severity、title、description、action、折叠 details、compact dismiss | Error Boundary、表单、运行错误 | 保留现有 Alert 调用签名和 API error 适配 | dismiss、details、screen reader | Batch 5 完成错误展示迁移 |
| OverlayLayer | z-index 分散 | Select、Popover、Tooltip、DatePicker、TimePicker、Modal、Drawer、Toast 使用统一 layer 枚举和 portal root | 所有 overlay | \`OVERLAY_Z\` 作为唯一映射 | stacking、nested overlay、Escape | Batch 4 无硬编码 overlay z |
| Spinner/Progress | 页面自绘 spinner 和运行进度不一 | inline/block、label、determinate/indeterminate；最小可见进度由组件决定 | Backtest、Chat、Run Flow | 现有 Loader 可 alias | reduced motion、aria-live | Batch 5 无页面自绘 spinner |

### 4.3 跨页面 Pattern 迁移表

| Pattern | 当前问题 | 目标 API/职责 | 迁移调用点 | 兼容策略 | 响应式契约 | 测试与证据 | 删除条件 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AppPage | 页面各写 max-width/scroll | 常规业务页统一全宽内容容器、响应式边距和滚动边界；不负责创建或删除页面 Card | 7 个常规业务页 | Home、Chat、Login、NotFound 保持显式专用布局 | 320 无页面横溢；常规页边距一致 | 页面守卫和 8 视口 | 常规页无私有 max-width/padding 覆盖 |
| WorkspacePage/ResponsiveRail | Home/Chat 各自固定 rail | 主任务区、可折叠辅助区及单一触发器；不创建第二套全局导航 | Home、Chat、Reports | 保留业务 rail 内容组件，只替换容器 | >=1280 可折叠；1024-1279 并入正文；<1024 Drawer | 767/768/900/1024/1280 | 无页面手写 rail 断点 |
| PageHeader | 7 个常规业务页已使用，专用工作区保留领域标题 | title、description、primary/secondary/more、status；不嵌复杂筛选 | 常规业务页 | 专用工作区保持显式例外 | 操作窄屏换行/菜单化 | 长文案、双语言 | 常规页 h1 不再私有实现 |
| WorkspaceToolbar/Toolbar | 已存在 Toolbar 但调用为零 | 搜索、筛选、批量操作、结果计数；不承载主要内容 | Screening、Alerts、Usage | 保持现有 query handler | <1024 折叠高级筛选 | keyboard、overflow | 无同构页面 toolbar |
| Section | 普通分组与显式卡片职责混杂 | Section 提供无框 heading/description/action/divider；SectionCard 保留页面卡片语义 | Home、Settings、Portfolio | 两者并存，不机械互换 | 单列优先 | card nesting guard | 无意义嵌套消失，页面级卡片保留 |
| StickyActionBar | 已存在但调用为零 | dirty/status/primary/secondary，支持 safe area | Settings、LLM editor | 保持提交 handler 和表单归属 | 移动考虑键盘与 safe area | tab order、390x667 | 无页面私有 sticky footer |
| DataTable | 11 套 table 分别处理状态与窄屏 | columns、sort、loading/empty、rowAction、columnPriority；领域 formatter 外置 | 11 个 table，先 Screening/Usage | 保留原 sort/formatter adapter | 横滚边界或移动摘要/详情 | table a11y、320/390 | 无平行 table shell |
| FilterToolbar/AdvancedFilterSheet/AppliedFilterChips | 高级筛选在平板堆叠 | 基础筛选、高级 Sheet、已应用条件；不拥有 query state | Screening、DecisionSignals、Alerts | 复用现有状态和 URL 参数 | <1024 Bottom Sheet，桌面 inline | apply/reset/reopen/deep-link | 无页面自建筛选 overlay |
| SummaryStrip | 指标普遍拆成独立 Cards | 少量核心连续指标与趋势，不把每个字段卡片化 | Home、Portfolio、Usage | 旧 StatCard 可逐项映射 | 窄屏分行，不隐藏主指标 | zero/loading/data | 无零值卡墙 |
| Tabs | Tab/边框按钮/SegmentedControl 语义混杂 | 页面内容分区和 aria tab contract；单字段枚举仍用 SegmentedControl | Settings、Signals、Alerts、Reports | 保留 tab id 和 URL | 长标签可滚动且 active 可见 | arrows/Home/End | role=tab 不由普通 Button 拼装 |
| ProfileMenu | 语言和主题散落在 Sidebar | locale、theme、disabled placeholder items | Shell | 持久化 key 不变 | 桌面 Menu，移动 Sheet | focus/Escape/persist | 侧栏无平行主题/语言控件 |
| NotificationPanel | 只有设计参考，数据契约不完整 | empty/error/list/unread 展示；不伪造数据 | Shell、Alerts | 契约未完成时不挂载入口 | 桌面 Popover，移动 Sheet | states/unread/a11y | 数据契约完成或入口不发布 |
| ToastProvider | 页面 toast 和 z-index 分散 | 全局队列、live region、dismiss；不替代字段错误/长期 Alert | Settings、CRUD、运行任务 | 旧 toast adapter 转发 | 与 overlay stack 一致 | queue/dismiss/a11y | 页面 toast 容器为零 |
| Modal/BottomSheet | footer 随 body 滚动，移动长表单可达性不稳 | header/body/fixed footer，只有 body 滚动 | Settings、Alerts、Portfolio | 保留 open/onClose；旧 footer children 适配 | 桌面 Modal；移动 Bottom Sheet/全屏流程 | 390x667、soft keyboard、focus | 页面自建 fixed overlay 为零 |

### 4.3.1 原生交互语义分类

108 个页面/领域原生 button 不得机械替换成普通 Button。迁移清单必须先标为 \`Button\`、\`IconButton\`、\`MenuItem\`、\`PressableCard\`、\`PressableRow\`、\`DisclosureTrigger\`、\`TabTrigger\` 或 \`SuggestionChip\`，再由相应组件承担 Enter/Space、disabled、pressed、label 和 focus 行为。页面 \`className\` 只做布局和对齐，不覆盖控件圆角、核心 padding、surface、focus、disabled 或阴影。

### 4.4 依赖顺序

1. 正确性契约和守卫先于视觉迁移。
2. Token、Button、Field、Overlay、StatePanel 先于 Pattern。
3. AppPage、PageHeader、Toolbar、DataTable 先于页面迁移。
4. 复杂页面按 Home/Chat/Settings、Screening/Portfolio/DecisionSignals、其余页面分组。
5. Batch 6 仅删除兼容层和处理视觉/a11y 收尾，不再引入新架构。

## 5. Batch 0：基线、风险与守卫

**目标**：建立可复现的视觉基线，先关闭用户信任和数据语义风险，并让新增硬编码可被 CI 阻止。

**非目标**：不在本批次统一页面外观，不迁移全部原生控件。

**前置依赖**：同步目标分支；启动真实 Web、隔离测试后端与受控 mock；恢复可用 in-app Browser。

| 任务 ID | 问题/根因 | 目标 | 公共组件 | 主要文件 | 行为兼容 | 测试 | 截图 | 风险 | 前置依赖 | 完成标准 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B0-01 | 当前缺少统一视觉基线 | 采集 8 视口、双主题、关键状态基线 | 无 | \`tests/e2e/\`、PR 证据 | 不改行为 | Playwright smoke | 全部指定视口 | mock 与真实状态偏差 | 可用 Browser/Playwright | 基线命名、状态和数据固定 |
| B0-02 | 登录页无条件声明 TLS | HTTPS 显示可证明的安全状态；localhost HTTP 说明本地开发上下文；非 localhost HTTP 明确非加密或不显示安全声明 | Alert/StatusText | LoginPage、i18n | 登录流程不变 | 三种 protocol/host 条件单测、i18n | 三状态双主题 | 部署代理头语义 | 明确可信运行时信号 | HTTP 不再宣称 TLS |
| B0-03 | API Key password input 缺字段语义 | 显式 name 和 \`autocomplete="new-password"\` 或领域适配值，阻止管理员密码误填 | InputPrimitive | LLMChannelEditor、FirstRunWizard | 值与提交协议不变 | password manager 属性测试 | API Key 表单 | 浏览器实现差异 | Primitive API | 敏感字段均有明确 autocomplete |
| B0-04 | 报告 Hero 直接显示自由文本动作 | 以结构化 action 为唯一决策语义，operationAdvice 仅作说明 | DecisionAction | ReportOverview、history mapper、schema | 保留旧载荷 fallback 并记录弃用 | 旧/新载荷、语言、未知 action | 报告与历史同一记录 | 后端字段缺失 | 确认 API schema | 同一记录各入口动作一致 |
| B0-05 | 中文 issue 文本反查 code | 状态与错误使用稳定 typed code，翻译只在渲染层 | StatePanel/Alert | modelAccessIssues、LLMChannelEditor | 接受旧字符串一期，统一 normalize | code/legacy/unknown | 模型访问错误 | 外部数据仍返回旧值 | 状态 code 表 | 业务分支不比较中文展示文本 |
| B0-06 | 守卫未覆盖公共组件绕过 | 新增 native control、raw palette、invalid utility、overlay z、跨域 class、typed status 守卫 | Guard utilities | production/responsive/i18n tests | 初始 allowlist 不改现状 | AST/fixture tests | 无 | allowlist 永久化 | 完成现状清单 | 每条 allowlist 有 owner、目标 Batch、删除条件 |
| B0-07 | 768-1024 状态缺证据 | 为全局与业务侧栏建立断点行为断言 | Shell contracts | e2e、Shell | Home/Chat rail 延后至 \`xl\`，Drawer 行为保持不变 | 767/768/900/1024 | 四个中间视口 | 截图脆弱 | 固定数据和字体 | 能证明没有双固定侧栏 |

**API/数据变化**：B0-04 可能需要后端补充/稳定 \`action\` 字段；若现有 API 已提供则只改前端消费。B0-05 只改变前端内部错误表示，不改变外部 API。

**回滚**：每个正确性问题独立提交；保留旧载荷 normalize 一期。任何新守卫先以显式 allowlist 接纳历史债务，不得关闭 CI 或扩大通配豁免。

### 5.1 Batch 0 执行进度（2026-07-19）

| 任务 | 状态 | 已完成证据 |
| --- | --- | --- |
| B0-01 | 完成 | 独立 Playwright 环境采集 11 路由 × 8 视口 × 2 主题共 176 张截图；manifest 中 failures、missingFiles、documentOverflow 均为空 |
| B0-02 | 完成 | 三类连接上下文 helper 与 LoginPage 单测；HTTP 不再声明 TLS |
| B0-03 | 完成 | FirstRunWizard 与 LLMChannelEditor 敏感字段属性测试通过 |
| B0-04 | 完成 | ReportOverview 统一结构化 action，并覆盖矛盾旧载荷与 legacy fallback |
| B0-05 | 完成 | 模型访问问题改为 \`ModelAccessIssueCode\`，十语言资源完整性检查通过 |
| B0-06 | 完成 | 新增 UI 架构守卫，历史债务逐条记录 owner、目标 Batch 与删除条件 |
| B0-07 | 完成 | Home/Chat 在 767、768、900、1024px 均不会同时出现两条固定侧栏，Playwright 用例通过 |

已执行验证：

- \`npm run lint\`：通过。
- \`npm run test:i18n\`：94 项通过。
- \`npm run test\`：1827 项通过，2 项按既有条件跳过。
- \`npm run build\`：通过。
- \`npm run test:e2e-security-preflight\`：62 项通过。
- \`npm run test:smoke\`：136 项通过。

**推荐 PR**：

1. \`test: establish web UI visual and architecture guards\`
2. \`fix: correct login and credential field semantics\`
3. \`fix: unify decision action and model access status contracts\`

## 6. Batch 1：Foundation 与 Primitive

**目标**：建立可复用的交互基础，统一尺寸、状态、ref、field、overlay 和 loading 契约。

**非目标**：不在本批次批量改页面布局，不删除所有旧 variant。

**前置依赖**：B0 守卫和视觉基线完成。

| 任务 ID | 问题/根因 | 目标 | 公共组件 | 主要文件 | 行为兼容 | 测试 | 截图 | 风险 | 前置依赖 | 完成标准 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B1-01 | Button 无 ref 且领域 variant 重复 | forwardRef；收敛 appearance/size/loading/icon | Button | common/Button、调用测试 | 保留旧 alias 一期 | ref/form/disabled/loading | 状态矩阵双主题 | 默认 type 变化 | B0 guard | 领域 variant 有迁移清单 |
| B1-02 | 图标操作各自拼 44px button | 统一 IconButton、tooltip、pressed 和 badge | IconButton/Tooltip | Shell、帮助按钮、行操作 | aria-label 必填 | a11y/touch/keyboard | 工具栏紧凑状态 | 可见尺寸过大或过小 | Button | 热区 >=44px，视觉不笨重 |
| B1-03 | Field、Input、Textarea 错误关系不一 | 统一 name/autocomplete/ref/error/help | Field/InputPrimitive/Textarea | common forms | 旧 props 透传 | aria-describedby、focus error | 正常/错误/禁用 | 表单 DOM 变化 | B0-03 | 关键表单不靠 placeholder 报错 |
| B1-04 | Select 系列宽度、overlay、搜索行为不一 | 统一 trigger/content 宽度策略、portal、键盘导航 | Select/SearchableSelect/MultiSelect | common/selects | value/onChange 不变 | typeahead/Escape/width | 240/320/390 宽度 | portal stacking | OverlayLayer | 输入框和下拉内容按容器一致 |
| B1-05 | Switch/Checkbox 与 Figma 状态不一致 | 对齐尺寸、状态、focus、禁用和 label click | Switch/Checkbox | common controls | checked/onChange 不变 | keyboard/indeterminate | Figma 状态矩阵 | 外观影响全局 | Figma MCP | 全部业务调用使用公共组件 |
| B1-06 | Card/Surface 语义重复 | 建立 Surface 层级，Card 兼容映射 | Surface/Card | common/Card、styles | 保留 Card API | theme/nesting | light/dark surfaces | 全局视觉回归 | token audit | default/bordered 不再同义 |
| B1-07 | Overlay z、焦点过滤和 Drawer 固定 eyebrow 分裂 | 统一 OverlayLayer，修正 fixed overlay focusable 判定；Drawer eyebrow 由调用方提供或默认不渲染 | Modal/Drawer/Popover/Toast | overlayZ、useDialogA11y、Drawer | Escape/close 行为不变 | nested overlay/focus restore/optional eyebrow | modal/drawer/select | 焦点回归高 | B0 e2e | 无硬编码 overlay z，焦点可恢复且语义正确 |
| B1-08 | 页面自绘 spinner/progress | 统一加载语义和 reduced motion | Spinner/Progress | common、Backtest/Chat later | 先新增不迁移页面 | aria-live/motion | inline/block | 动画视觉差异 | tokens | API 和状态测试完备 |

**API/数据变化**：无后端变化。公共组件新增 props 必须向后兼容；弃用项通过 TypeScript 注释和迁移清单管理，不在同一 PR 突然删除。

**回滚**：每个 Primitive 独立 PR；旧组件或 alias 保留至最后一个调用方迁移。视觉 token 变更必须可单独 revert，不与页面重排混合。

**推荐 PR**：

1. \`refactor: standardize button and form primitives\`
2. \`refactor: unify selection and toggle controls\`
3. \`refactor: centralize surfaces overlays and progress states\`

### 6.1 Batch 1 执行进度（2026-07-19）

| 任务 | 状态 | 已完成证据 |
| --- | --- | --- |
| B1-01 | 完成 | Button 支持 ref、标准 loading spinner 与语义 variant；领域 alias 和兼容类型已删除，架构守卫债务表为空 |
| B1-02 | 完成 | IconButton 强制可访问名称并分离 44px 命中区与紧凑视觉；Modal、Drawer、表格和工具栏均已迁移 |
| B1-03 | 完成 | Field、Textarea 和描述关系 helper 统一 ref、hint、error 与 \`aria-describedby\` 契约 |
| B1-04 | 完成 | Select、SearchableSelect 与 ModelMultiSelect 统一 trigger/content 宽度、Portal 定位、ref、Escape 与 typeahead 行为 |
| B1-05 | 完成 | Switch/Checkbox 对齐 Figma 尺寸与状态，统一 focus、禁用、label click 和至少 44px 命中区；双主题页面截图与交互测试通过 |
| B1-06 | 完成 | Surface 的 plain/subtle/bordered/elevated 层级稳定，Card 保留兼容 API 且 default/bordered 不再同义 |
| B1-07 | 完成 | 公共 dropdown、picker、tooltip、toast 使用 OverlayLayer；fixed overlay 焦点过滤、Escape 和 Drawer eyebrow 契约已验证 |
| B1-08 | 完成 | 页面自绘加载状态已迁移到 reduced-motion-safe Spinner 和带 ARIA 语义的 determinate/indeterminate Progress |

已执行验证：

- \`npm run lint\`：通过。
- \`npm run test:i18n\`：94 项通过。
- \`npm run test\`：1849 项通过，2 项按既有条件跳过。
- \`npm run build\`：通过，共转换 3314 个模块。
- \`npm run test:e2e-security-preflight\`：62 项通过。
- \`npm run test:smoke\`：136 项通过，覆盖 overlay、Drawer focus、44px 触控目标与 767/768/900/1024px 断点。

视觉验收已通过独立 Playwright 完成：176 张截图覆盖八视口、双主题和 11 个一级路由，证据位于 gitignored 的 \`.context/ui-ux-remediation-acceptance/\`。Figma MCP 证据用于核对组件状态，不替代本地应用截图。

## 7. Batch 2：跨页面 Pattern

**目标**：把页面共同结构变成可迁移 Pattern，并给响应式行为明确契约。

**非目标**：不在 Pattern 中包含具体股票、模型、告警或报告业务规则。

**前置依赖**：Batch 1 Primitive 稳定；B0 截图与守卫可运行。

| 任务 ID | 问题/根因 | 目标 | 公共组件 | 主要文件 | 行为兼容 | 测试 | 截图 | 风险 | 前置依赖 | 完成标准 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B2-01 | 常规页面宽度、边距和标题层级不一 | AppPage/PageHeader 统一滚动、全宽内容边界和标题；保留 Shell 与页面级卡片 | AppPage/PageHeader/Surface | Shell、common/layout、7 个常规页面 | 路由、滚动目标和 Card 结构不变 | scroll/focus/route/guard | 8 视口 shell | 高度和 sticky 回归 | Surface | 常规页无私有 max-width/padding 覆盖，标题共用 PageHeader |
| B2-02 | Toolbar/Section/StickyActionBar 尚无生产调用 | 明确无框 Section/Toolbar 与显式 SectionCard 的职责后建立首批示例 | Toolbar/Section/SectionCard/StickyActionBar | common/patterns | 不改变 query/form state，不删除页面 Card | resize/keyboard | 390/900/1280 | 错误抽象扩散 | AppPage | 至少两个不同领域复用同一契约 |
| B2-03 | 11 个 table 独立实现 | DataTable 统一 header、loading、empty、row action 和列优先级 | DataTable | common/table | formatter/sort 回调兼容 | sort/a11y/mobile | empty/loading/data | 大范围迁移风险 | StatePanel | 先迁移两张代表表验证 |
| B2-04 | 高级筛选占满平板宽度 | 基础筛选 inline，高级筛选在 <1024 转 Sheet | ResponsiveFilterPanel | common/filters | URL/query state 不丢失 | open/apply/reset/restore | 767/768/900/1024 | 筛选状态丢失 | Drawer/Field | 关闭再打开值一致 |
| B2-05 | EmptyState 和 DashboardStateBlock 平行 | StatePanel 统一状态层级和 CTA | StatePanel | common/state | 旧组件转发 | all variants | 双主题状态矩阵 | 文案过度统一 | Alert/Spinner | 无新增 dashed empty card |
| B2-06 | 语言与主题入口散落在侧栏底部 | ProfileMenu 承载语言、主题，其他项明确不可用 | ProfileMenu/Menu | Sidebar/Shell | locale/theme persistence 不变 | focus/Escape/persist | desktop/mobile | 菜单可发现性 | Overlay | 单一入口且键盘可用 |
| B2-07 | Notification 仅有设计参考，数据能力不清 | 先定义展示 Pattern；仅在数据契约存在时接 Shell | NotificationPanel | common/notification、Alerts | 不伪造通知计数 | empty/error/list | panel states | 与 Alerts 重复 | API contract | 无契约时组件不进入主导航 |
| B2-08 | 长 Modal footer 随 body 滚走，Toast 与字段错误边界不清 | Modal 使用 header/body/fixed footer；移动长表单转 BottomSheet；瞬时反馈进入全局 ToastProvider | Modal/BottomSheet/ToastProvider | common overlays、Shell provider | 现有 open/onClose 和 toast 调用可适配 | focus/scroll/queue/soft keyboard | 390x667、390x844、desktop | portal 与 safe area | B1 Overlay | footer 始终可达，字段错误不发 Toast |

**API/数据变化**：DataTable 和筛选 Pattern 只消费现有页面数据；NotificationPanel 若需全局未读数，必须另立 API PR，未完成前不显示假 badge。

**回滚**：Pattern 与首批调用方同 PR，但每次最多迁移两个代表页面；旧实现保留到对比验证完成。页面宽度/标题可按 AppPage 调用点回滚，Shell 和页面 Card 外观不在本任务中删除。

**推荐 PR**：

1. \`refactor: standardize page shell and section patterns\`
2. \`refactor: add responsive filters and data table patterns\`
3. \`feat: move theme and locale controls into profile menu\`

### 7.1 Batch 2 执行进度（2026-07-19）

| 任务 | 状态 | 已完成证据 |
| --- | --- | --- |
| B2-01 | 完成 | Alerts、Backtest、DecisionSignals、Portfolio、Settings、StockScreening、TokenUsage 共用 AppPage、响应式边距和 PageHeader；NotFound 使用最小 AppPage；Shell 与页面级卡片保留；八视口截图和布局守卫通过 |
| B2-02 | 完成 | Section 为无框分组，SectionCard 继续作为显式卡片；DataTable 有 12 个生产文件调用，Toolbar 2 个、Section 4 个、StickyActionBar 2 个，均由多个领域验证 |
| B2-03 | 完成 | 所有连续数据表迁移到 DataTable；生产代码唯一 \`table\` 位于共享 DataTable，外层领域 Card 保留 |
| B2-04 | 完成 | Decision Signals 和 Stock Screening 复用 ResponsiveFilterPanel；小于 1024px 的高级筛选进入 Drawer，关闭/重开后受控值保持 |
| B2-05 | 完成 | StatePanel 成为唯一状态入口，旧 EmptyState 与 DashboardStateBlock 已删除；空状态不创建嵌套 Card |
| B2-06 | 完成 | ProfileMenu 在桌面侧栏和移动顶栏以单一入口承载语言、主题，持久化键不变 |
| B2-07 | 完成（契约边界） | NotificationPanel 覆盖 loading/error/empty/list/unread；因缺少全局通知与未读 API，按计划不伪造 Shell 入口或 badge |
| B2-08 | 完成 | 长 Modal 使用独立滚动 body 与固定 footer；全局 ToastProvider 统一瞬时反馈，领域调用迁移和语义测试完成 |

自动化已覆盖组件、页面布局守卫、响应式筛选、Profile、通知、Modal/Toast 与叠层焦点恢复；独立 Playwright 视觉矩阵覆盖 176 个页面/视口/主题组合。页面级大卡片为本轮明确保留项，不再列入删除清单。

已执行验证：

- \`npm run lint\`：通过。
- \`npx tsc -b --pretty false\`：通过。
- \`npm run test:i18n\`：94 项通过。
- \`npm run test\`：166 个测试文件通过，1881 项通过，2 项按既有条件跳过。
- \`npm run build\`：通过，共转换 3321 个模块。
- \`npm run test:e2e-security-preflight\`：62 项通过。
- Tooltip/ConfirmDialog 叠层场景修复后连续复跑 10 次：10 项通过。
- \`npm run test:smoke\`：136 项全部通过，覆盖 320/390px、767/768/900/1024px、双主题、路由、设置、回测和 overlay/focus 契约。
- \`git diff --check\`：通过。

## 8. Batch 3：首页、Chat、设置

**目标**：处理三个最大且最常用的页面，消除双侧栏、状态文案和表单交互问题。

**非目标**：不重写聊天协议、模型调用和设置后端配置结构。

**前置依赖**：Batch 2 AppPage、Section、StatePanel、ProfileMenu；Batch 1 Field、Overlay、Selection controls。

| 任务 ID | 问题/根因 | 目标 | 公共组件 | 主要文件 | 行为兼容 | 测试 | 截图 | 风险 | 前置依赖 | 完成标准 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B3-01 | Home 近 2000 行且 \`home-*\` 向外泄漏 | 拆分页面编排与领域区块，移除跨域 class 依赖 | AppPage/Section/MetricGroup | HomePage、home components/CSS | 数据请求和点击路径不变 | loading/error/history | 8 视口双主题 | 首页回归面大 | B2 shell | 页面只负责布局和状态编排 |
| B3-02 | Home 历史栏从 md 固定展示，与全局导航冲突 | <1024 使用 Drawer/Sheet，桌面保留辅助 rail | Drawer/ResponsiveRail | Home history | 选择历史记录不变 | 767/768/900/1024 | 中间视口 | 历史入口可发现性 | B2 shell | 任一视口最多一个固定侧栏 |
| B3-03 | Chat 会话栏同样从 md 固定，运行状态有英文 fallback | 会话列表平板转 Drawer；所有 stage 使用 code+i18n | ResponsiveRail/StatePanel | ChatPage、i18n | 会话和流式协议不变 | stream/timeout/locale | 390/768/1024 | 流式状态回归 | B0 typed status | 中文界面无英文运行状态 |
| B3-04 | Chat 使用 \`home-surface-button\` 等跨域样式 | 迁移到 Button/IconButton/Surface 语义 variant | primitives | Chat components/CSS | 操作行为不变 | button actions | 双主题 | 视觉差异 | B1 | Chat 不再引用 \`home-*\` |
| B3-05 | Settings 分类侧栏在 md 出现，与全局导航断点不一致 | 1024 以下使用 Select/Sheet，桌面侧栏 | Select/ResponsiveNav | SettingsPage | 当前 category/view 保持 | deep-link/change category | 768/900/1024 | URL 状态 | B1 Select | 中间视口无双导航 |
| B3-06 | Settings 巨型页面和 LLM 编辑器耦合 | 按 section/view 拆领域组件，公共 Field/Switch/Checkbox/Select 全覆盖 | Field/Section/StickyActionBar | SettingsPage、LLMChannelEditor | 配置 key 和提交 payload 不变 | dirty/save/cancel/error | 主要 section | 拆分导致状态丢失 | B1/B2 | 所有保存路径有就近反馈 |
| B3-07 | Tab 曾使用边框按钮且语义分散 | 配置视图统一 Tabs/SegmentedControl，长标签可滚动 | Tabs/SegmentedControl | SettingsViewTabs | role/tab keyboard 完整 | arrows/Home/End | 中英长标签 | 误用于分类导航 | Figma tabs | 分类与同页视图语义明确区分 |
| B3-08 | MultiSelect trigger 展示全部已选项导致高度膨胀 | trigger 显示摘要/有限 chips，完整项在菜单中管理 | MultiSelect | Settings fields | 选值和顺序不变 | 0/1/many/all | 240/320 宽度 | 已选可见性 | B1-04 | trigger 稳定单行或受控两行 |
| B3-09 | 日期、时间、颜色和普通下拉字段宽度/交互不一致 | 全部通过公共 DatePicker、TimePicker、ColorPicker、Select，trigger 默认填满字段网格 | Field/specialized controls | SettingsField、设置领域表单 | 配置序列化不变 | keyboard/value/clear/width | 240/320/390、双主题 | 专用 picker overlay | B1-04/B1-07 | 同一字段列内 trigger 等宽且层级正确 |

**API/数据变化**：无 API 变更。Chat 的 stage code 若服务端只返回自由文本，应在 API adapter 归一化，不在组件中比较英文或中文。

**回滚**：Home、Chat、Settings 分三个 PR；页面拆分与视觉变化分别提交。保留旧 rail 组件直到 Drawer 行为在 767/768/900/1024 验收通过。

**推荐 PR**：

1. \`refactor: simplify home layout and responsive history\`
2. \`fix: improve chat navigation and localized run states\`
3. \`refactor: standardize settings navigation and form controls\`

### 8.1 Batch 3 执行结果（2026-07-19）

| 任务 | 状态 | 结果 |
| --- | --- | --- |
| B3-01 | 完成 | Home 保留页面编排和领域状态，历史/自选、任务、报告使用领域组件；跨领域 \`home-*\` 泄漏守卫为 0 |
| B3-02 | 完成 | Home 历史 rail 仅在 \`xl\` 展示，中间与移动视口通过 Drawer 访问 |
| B3-03 | 完成 | Chat 会话 rail 同步转 Drawer；stage code 全部走 i18n，十语言资源门禁通过 |
| B3-04 | 完成 | Chat 操作迁移到 Button/IconButton/Surface，手绘操作图标替换为 Lucide |
| B3-05 | 完成 | Settings 在 1024px 以下使用共享 Select 切换分类，不再出现第二条固定导航 |
| B3-06 | 完成 | 首次配置与调度器拆为 \`FirstRunSetupCard\`、\`SchedulerSettingsCard\`；表单控件、长 Modal footer 和保存反馈统一，配置 key/payload 不变 |
| B3-07 | 完成 | 同页视图使用 SegmentedControl/Tabs 语义，箭头、Home、End 键盘行为有测试 |
| B3-08 | 完成 | MultiSelect trigger 改为选中数量摘要，完整选项只在菜单管理，优先级顺序保持 |
| B3-09 | 完成 | DatePicker、TimePicker、Select 与字段列等宽；有限颜色方案继续用 Select，属于明确语义例外 |

## 9. Batch 4：选股、持仓、AI 建议

**目标**：让筛选、账户状态和高密度建议页在桌面与平板上都保持清晰，并统一表格与筛选交互。

**非目标**：不改变筛选算法、持仓计算或 AI 建议生成规则。

**前置依赖**：DataTable、ResponsiveFilterPanel、StatePanel、Drawer、Field。

| 任务 ID | 问题/根因 | 目标 | 公共组件 | 主要文件 | 行为兼容 | 测试 | 截图 | 风险 | 前置依赖 | 完成标准 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B4-01 | Screening 筛选和结果密度高，禁用状态可能仍暴露 workspace | Disabled 时只展示原因和 CTA；Ready 时基础/高级筛选分层 | StatePanel/ResponsiveFilterPanel | StockScreeningPage | query 与结果不变 | disabled/empty/data/filter | 8 视口 | 隐藏可用信息 | 明确 capability | Disabled 不渲染不可用 workspace |
| B4-02 | Screening 自绘 table 和 raw surface utility | 迁移代表 DataTable，删除无效 \`bg-surface\` | DataTable/Surface | StockScreeningPage | 排序、分页、选择不变 | sort/select/pagination | mobile/tablet/desktop | 表格行为回归 | B2 table | 无无效 utility，窄屏可操作 |
| B4-03 | Portfolio 无账户仍展示零指标和空表 | 无账户使用单一 StatePanel；账户为空和有数据分别建模 | StatePanel/MetricGroup | PortfolioPage | 创建账户入口不变 | no-account/empty/data/error | 四状态双主题 | 状态判断错误 | 账户 schema | 无账户不出现零值仪表盘 |
| B4-04 | Portfolio 创建表单主操作弱、错误不就近 | 主提交使用 primary；Field 显示验证错误并聚焦首错 | Field/Button | Portfolio account form | payload 不变 | required/server error/success | modal/form states | 自动聚焦 | B1 Field | 不以 placeholder 表示 required |
| B4-05 | Portfolio 表格与图表在窄屏并列/宽度不可控 | 摘要、分布、持仓按优先级重排；表格使用列优先级 | DataTable/Section | PortfolioPage | 数值格式不变 | resize/data | 320-1280 | 信息隐藏过度 | B4-03 | 核心金额和操作始终可达 |
| B4-06 | DecisionSignals 筛选列过多，时间线 md 五列 | 基础筛选常驻，高级筛选 Sheet；结果详情 Drawer | ResponsiveFilterPanel/DataTable/Drawer | DecisionSignalsPage | 筛选和详情不变 | apply/reset/deep-link/drawer | 768/900/1024 | 查询状态丢失 | B2 filter | 900px 不出现挤压多列 |
| B4-07 | 动作 Badge/颜色可能绕过统一语义 | action/severity 映射统一到 Badge token | Badge | DecisionSignals、Portfolio | action code 不变 | all actions/themes | badge matrix | 颜色语义误用 | B0-04 | 同一 action 全站同标签和颜色 |

**API/数据变化**：只复用既有账户、筛选和建议数据。若 capability/disabled 原因没有结构化 code，先在 adapter 定义稳定映射。

**回滚**：三个页面独立 PR；DataTable 首次页面迁移保留旧 formatter 和事件适配层。状态逻辑修改必须单独提交，可在视觉问题时独立 revert。

**推荐 PR**：

1. \`fix: clarify screening availability and responsive filters\`
2. \`fix: simplify portfolio states and account workflow\`
3. \`refactor: improve decision signal filters and action semantics\`

### 9.1 Batch 4 执行结果（2026-07-19）

| 任务 | 状态 | 结果 |
| --- | --- | --- |
| B4-01 | 完成 | Screening Disabled 只渲染 StatePanel 与启用入口；Ready 才展示筛选 workspace |
| B4-02 | 完成 | Screening 结果迁移 DataTable/ResponsiveFilterPanel，排序、分页和选择行为保留 |
| B4-03 | 完成 | Portfolio 无账户改为单一 onboarding StatePanel，不再渲染零值指标和空表 |
| B4-04 | 完成 | 新建账户和交易表单使用 Field 就近错误、明确 Primary，并覆盖 320px 单列流程 |
| B4-05 | 完成 | 持仓明细使用 DataTable 列优先级，摘要/分布/明细在窄屏按信息优先级重排 |
| B4-06 | 完成 | Decision Signals 高级筛选转 Drawer，受控值关闭重开不丢失；内容视图使用 SegmentedControl |
| B4-07 | 完成 | 决策 action 的 label/tone 由稳定 code 映射，列表、时间线和报告共用语义 |

## 10. Batch 5：回测、告警、用量、报告与 Run Flow

**目标**：完成剩余业务页面迁移，统一表格、运行进度、错误详情和空状态。

**非目标**：不修改任务调度、计费统计或报告生成算法。

**前置依赖**：Batch 1/2 全部公共组件；B0 action/status contract。

| 任务 ID | 问题/根因 | 目标 | 公共组件 | 主要文件 | 行为兼容 | 测试 | 截图 | 风险 | 前置依赖 | 完成标准 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B5-01 | Backtest 无统一页头，未运行时仍展示空性能列，自绘 spinner | 未运行只展示输入和单一状态；运行中统一 progress；结果后再显示指标 | AppPage/PageHeader/Progress/StatePanel | BacktestPage | 启动/取消/重跑协议不变 | initial/running/error/result | 8 视口 | 任务状态竞态 | Progress | 各阶段只显示相关内容 |
| B5-02 | Backtest “1 日验证”“强制重跑”等选项使用普通 Button | 1 日验证使用 SegmentedControl；强制重跑进入高级选项并在执行前二次确认；真正二元字段才使用 Checkbox/Switch | Field/SegmentedControl/Switch/Checkbox/Modal | Backtest form | 参数值不变 | keyboard/form payload/confirm-cancel | form/confirm states | 控件语义变化 | B1 toggles/B2 Modal | 控件类型匹配数据语义且危险操作可撤销 |
| B5-03 | Alerts 多个独立 table 和状态展示 | 规则、触发历史迁移 DataTable；错误使用 Alert | DataTable/Alert/Toolbar | AlertsPage、AlertRuleList、AlertTriggerHistory | CRUD 和分页不变 | rule/history/error | empty/data | 行操作回归 | B2 table | 表格交互一致 |
| B5-04 | Token Usage 零调用仍展示统计卡和空 Recent Calls 表 | 无调用时单一 Empty；有数据才展示统计和明细 | StatePanel/MetricGroup/DataTable | TokenUsagePage | 统计值不变 | zero/data/error | three states | 0 与未加载混淆 | 明确 loading | 零、加载、错误不混淆 |
| B5-05 | 报告不同入口动作和错误呈现不一 | 统一 action、Alert、详情 disclosure 和图表状态 | Badge/Alert/StatePanel | report components | 报告字段兼容 | legacy/new/error | report states | 历史报告兼容 | B0-04 | 同一报告语义一致 |
| B5-06 | Run Flow 使用 \`home-*\`，节点详情和 summary 自成体系 | 迁移 Surface/Badge/Progress/Drawer，保留图节点领域实现 | primitives/patterns | RunFlow* | 图交互不变 | node select/run/error | desktop/mobile drawer | 图层和 overlay 冲突 | B1 overlay | 无跨域 home class |
| B5-07 | 错误详情和关闭按钮视觉过重 | Alert details 默认折叠；dismiss 使用紧凑 IconButton | Alert/IconButton | Error Boundary、运行错误、模态 | 错误文本可访问 | dismiss/details/copy | compact/full | 详情被隐藏 | B1 Alert | 默认不被大按钮和长堆栈占据 |
| B5-08 | NotFound/Login/Error 页面壳层不一致 | 使用最小 AppPage/StatePanel，不创建营销式卡片 | AppPage/StatePanel | NotFound、RouteErrorBoundary | 导航/retry 不变 | route/retry | mobile/desktop | 错误边界依赖 | B2 shell | 错误页清晰且按钮不过大 |

**API/数据变化**：无预期 API 改动。运行状态、usage loading 和 error 必须通过明确状态区分；若当前 adapter 把“0”与“未加载”合并，应先修 adapter 并补契约测试。

**回滚**：按 Backtest、Alerts、Usage、Report/Run Flow 分 PR。公共 Alert 的视觉变化与错误内容逻辑分提交，确保可单独恢复。

**推荐 PR**：

1. \`fix: clarify backtest stages and controls\`
2. \`refactor: standardize alert and usage data states\`
3. \`refactor: unify report and run flow feedback\`
4. \`fix: simplify route and runtime error presentation\`

### 10.1 Batch 5 执行结果（2026-07-19）

| 任务 | 状态 | 结果 |
| --- | --- | --- |
| B5-01 | 完成 | Backtest 按 setup/running/result 分阶段，运行进度使用 Progress，结果区按状态出现 |
| B5-02 | 完成 | 1 日验证使用 SegmentedControl，强制重跑进入高级选项并在执行前 ConfirmDialog 确认 |
| B5-03 | 完成 | Alerts 规则、触发历史、通知尝试统一到 DataTable/Toolbar/Alert |
| B5-04 | 完成 | Token Usage 零调用使用单一 StatePanel；有数据后才渲染统计和调用明细 |
| B5-05 | 完成 | 报告 action、错误、详情 disclosure 与外围状态统一，四种 UI/report language 组合通过 |
| B5-06 | 完成 | Run Flow 保留领域图 SVG，反馈、节点详情、Badge、Progress、Drawer 使用共享层且无 \`home-*\` 泄漏 |
| B5-07 | 完成 | ApiErrorAlert/RouteBoundary 默认折叠详情，关闭使用紧凑 IconButton，44px 热区保留 |
| B5-08 | 完成 | Login、NotFound、RouteErrorBoundary 使用最小页面/状态结构，按钮尺寸收敛且不创建营销页 |

## 11. Batch 6：视觉与无障碍收尾

**目标**：删除迁移兼容层，完成主题、视觉密度、无障碍和全站回归验收。

**非目标**：不在收尾批次新增页面功能或重构数据层。

**前置依赖**：Batch 0-5 完成，所有页面已迁移且有前后截图。

| 任务 ID | 问题/根因 | 目标 | 公共组件 | 主要文件 | 行为兼容 | 测试 | 截图 | 风险 | 前置依赖 | 完成标准 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| B6-01 | 迁移 alias 和 allowlist 可能永久残留 | 删除 Button 领域 alias、历史 guard allowlist、旧状态组件 | all | common、guard tests | 无运行行为变化 | full unit/lint/build | component matrix | 隐藏调用方 | 全页迁移 | allowlist 为零或有批准例外 |
| B6-02 | raw palette、无效 surface、硬编码 z、领域 class | 全部改为语义 token，CSS 按层组织 | tokens | index.css、Tailwind、components | 主题语义不变 | design guards | 双主题全页 | 全局视觉变化 | B6-01 | 守卫无新增豁免 |
| B6-03 | uppercase、圆角、阴影和卡片密度不一 | 按角色收敛 typography/radius/elevation | tokens/Surface | shared styles/pages | 信息层级不变 | visual regression | 8 视口 | 视觉主观性 | Figma matrix | 页面不再一层层 Card |
| B6-04 | 焦点、键盘、reduced motion 需全链路验证 | WCAG 关键路径：键盘、焦点恢复、label、live region、contrast | all | common/hooks/e2e | 鼠标行为不变 | axe/manual keyboard/motion | focus states | 自动测试不足 | stable UI | 无 P0/P1 a11y 问题 |
| B6-05 | 中英文长文本和短视口未系统覆盖 | 双语言、390x667、软键盘和 200% zoom 验收 | layout patterns | e2e/i18n | 文案含义不变 | i18n/zoom/keyboard | long-text matrix | 浏览器差异 | test env | 文本无遮挡和不可达操作 |
| B6-06 | 截图证据分散 | 建立 PR 截图模板和最终对比索引 | docs/test tooling | PR template/docs | 无 | artifact validation | 全矩阵 | 仓库误收临时图 | CI artifact | 临时截图不入库 |

**API/数据变化**：无。

**回滚**：token、兼容层删除、a11y 行为和视觉密度分别提交。若截图回归无法解释，回滚具体 token 或页面提交，不恢复被证实错误的安全/语义修复。

**推荐 PR**：

1. \`chore: remove legacy web UI compatibility paths\`
2. \`fix: complete web theme and accessibility consistency\`
3. \`test: finalize responsive visual acceptance coverage\`

### 11.1 Batch 6 执行结果（2026-07-19）

| 任务 | 状态 | 结果 |
| --- | --- | --- |
| B6-01 | 完成 | Button 领域 alias 和 UI 架构债务表清零；旧 EmptyState/DashboardStateBlock 删除 |
| B6-02 | 完成 | raw palette、无效 surface、硬编码 overlay z、跨领域 class 守卫均为 0 |
| B6-03 | 完成 | 命令按钮、chip、segmented、surface、radius 与 elevation 按语义收敛；Shell 和页面级 Card 按用户要求保留 |
| B6-04 | 自动化完成，人工复核保留 | 焦点 trap/restore、Escape、label、live region、reduced motion、关键对比度均有测试；读屏器与真实设备 200% zoom 仍是发布前人工项 |
| B6-05 | 自动化完成，人工复核保留 | 十语言门禁、390x667、320px、8 视口均通过；真实软键盘与操作系统缩放仍是人工项 |
| B6-06 | 完成 | gitignored 本地证据包含 176 张截图和 manifest；仓库未加入一次性图片 |

## 12. 模块级迁移矩阵

| 模块 | 当前主要问题 | 目标结构 | 关键公共组件 | 状态覆盖 | 主要响应式策略 | 风险等级 | 目标 Batch |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Shell | 页面容器宽度不一；overlay/profile 分散 | 保留主内容大 Card，内部常规页统一 AppPage，侧栏使用单一 profile 入口 | AppPage、ProfileMenu、OverlayLayer | route/error/menu | lg 以下 drawer，主内容 Card 保留 | 高 | 2 |
| Home | 巨型页面、历史 rail、home class 泄漏 | 摘要、主内容、可选历史 Sheet | Section、ResponsiveRail、StatePanel | loading/empty/error/ready | <1024 历史转 Sheet | 高 | 3 |
| Chat | 会话 rail、英文 fallback、跨域样式 | 会话 Sheet、结构化 stage、稳定 composer | ResponsiveRail、StatePanel、Button | idle/streaming/timeout/error | <1024 会话转 Sheet | 高 | 3 |
| Settings | 分类断点冲突、表单/LLM 过大 | responsive category nav、Section form | Field、Tabs、Select、StickyActionBar | clean/dirty/saving/error | <1024 category Select/Sheet | 高 | 3 |
| Stock Screening | 筛选过密、disabled/表格状态 | availability gate、响应筛选、DataTable | StatePanel、FilterPanel、DataTable | disabled/empty/loading/data/error | 高级筛选转 Sheet | 高 | 4 |
| Portfolio | 无账户零仪表盘、表单错误、表格 | account state、摘要/分布/持仓 | StatePanel、MetricGroup、Field、DataTable | no-account/empty/data/error | 单列重排、列优先级 | 高 | 4 |
| Decision Signals | 复杂筛选、多列时间线 | 基础筛选、advanced Sheet、详情 Drawer | FilterPanel、DataTable、Badge、Drawer | empty/loading/data/error | <1024 高级筛选 Sheet | 高 | 4 |
| Backtest | 初始空性能区、自绘进度、控件语义 | setup、running、result 三阶段 | PageHeader、Progress、StatePanel、Field | initial/running/error/result | 结果区按阶段出现 | 中 | 5 |
| Alerts | 多表格、错误/空态不一致 | 规则与历史统一 DataTable | Toolbar、DataTable、Alert | empty/loading/data/error | 工具栏折叠 | 中 | 5 |
| Token Usage | 零值卡片加空表 | 零状态或有数据仪表盘 | StatePanel、MetricGroup、DataTable | loading/zero/data/error | 指标换行、明细列优先 | 中 | 5 |
| Login/NotFound/Error | TLS 误导、壳层和大按钮 | 准确状态、最小页面结构 | Field、StatePanel、Alert、Button | default/error/retry | 单列，操作适度宽度 | 高 | 0/5 |
| Reports | action/错误语义分裂 | 结构化 action、统一错误与详情 | Badge、Alert、StatePanel | legacy/data/error | 内容优先，详情按需展开 | 高 | 0/5 |
| Run Flow | home class、节点详情与层级 | 领域图 + 公共反馈和 Drawer | Progress、Badge、Drawer、Surface | idle/running/partial/error | 详情移动端 Drawer | 中 | 5 |

### 12.1 功能级验收补充

| 模块 | 必须完成的交互与信息架构 | 预计主要文件 | 依赖 | 截图与完成证据 |
| --- | --- | --- | --- | --- |
| 全局外壳与导航 | 修复品牌截断；移动端只保留一个全局菜单；历史入口使用历史语义而非第二个汉堡；折叠状态下头像不抢过 active nav；语言/主题进入 ProfileMenu | Shell、SidebarNav、ProfileMenu | Batch 1 Overlay/IconButton，Batch 2 AppPage | 1280/1024/900/768/767/390/320，侧栏展开与折叠 |
| 登录与首次配置 | 保留克制单卡；三类连接上下文显示真实状态；登录失败/会话过期保留来源路由并解释；登录 Primary 与工作台一致；API Key 不接收管理员密码 autofill | LoginPage、FirstRunWizard、Input | B0 security，B1 Field/Button | HTTP/HTTPS、error/expired、双主题 |
| 首页与报告 | 首要流程只保留股票输入、必要策略摘要和分析 Primary；通知/策略进入分析选项；大盘复盘作为独立模式；报告操作为 Primary、Secondary、更多；Hero 合并结论/action/趋势/分数；资讯、诊断、追溯用 Tabs/Disclosure | HomePage、report components、history rail | canonical action、WorkspacePage、Tabs | 320 首屏输入可用且无双汉堡；1024-1279 rail 并入正文 |
| Chat | 消息画布扁平；空态只保留引导和紧凑 suggestion chips；点击推荐问题只填入 composer，不自动发送；composer 始终可见；未配置 Agent 的 CTA 指向设置且匹配 error code；历史按钮移出 h1；消息/会话操作使用 Pressable/IconButton | ChatPage、composer、session/message components | ResponsiveRail、Field、typed status | empty/config-missing/streaming/timeout，390x667 软键盘 |
| AlphaSift 选股 | Disabled 仅显示 Activation Gateway；Ready 按策略、参数、结果组织；热点是可折叠辅助区；运行状态有停止和跟踪入口；策略/热点使用 PressableCard + semantic tone；结果用 DataTable | StockScreeningPage、strategy/hotspot components | StatePanel、FilterPanel、DataTable | disabled/empty/running/data，所有中间断点 |
| 持仓 | 无账户仅 onboarding；空账户显示现金摘要和录入/导入；有持仓显示 SummaryStrip、DataTable、风险概览；主提交桌面正常宽、移动吸底；CSV 统一 FilePicker | PortfolioPage、account/import components | Field、FilePicker、SummaryStrip、DataTable | no-account/empty/data/error，创建/导入流程 |
| AI 建议 | 主筛选只保留股票/action/status；其他条件进入“筛选（N）”Bottom Sheet；当前股票显示 applied chip；信号列表、当前股票、时间线、表现统计用 Tabs；同一作用域不重复空态；技术口径进入 help | DecisionSignalsPage、filters/timeline | FilterPanel、Tabs、Badge、Drawer | filter count、四个 tab、empty/data、390/768/1024 |
| 回测 | 恢复 PageHeader；配置与结果分区；运行是唯一 Primary；1 日验证用 SegmentedControl；强制重跑进入高级设置并确认；未运行不显示指标空栏；运行中显示阶段、耗时、停止和日志入口 | BacktestPage | Progress、StatePanel、Modal | initial/running/result/error/confirm |
| 告警 | 规则、触发历史、通知结果使用 Tabs；无规则单一 onboarding CTA；刷新按钮有可区分 label；表单按对象、条件、通知与启用分组，每组最多两列；MACD/KDJ 窄屏不固定四列；footer 固定 | AlertsPage、AlertRuleList、AlertTriggerHistory、editor | Tabs、DataTable、Field、Modal | 390x667 + keyboard、empty/data/error |
| Token 用量 | SummaryStrip 突出总 Token；零数据只显示一个 Empty；有数据后才显示趋势、模型占比、最近调用；label 全部 i18n；时间范围视觉紧凑且热区合格 | TokenUsagePage | SummaryStrip、StatePanel、DataTable、Date control | zero/data/error、320/390/1280 |
| 设置 | 全局 nav、分类、内容 Tabs 不形成三层常驻导航；readiness 与快速配置合并为 checklist/stepper；默认值与已保存值视觉/状态分开；普通字段使用 FieldRow + divider；服务商选择移动端转 Bottom Sheet；保存使用全局 ToastProvider 与 StickyActionBar | SettingsPage、LLMChannelEditor、SettingsField | Batch 1/2 全部 | category/view、dirty/save/error、长表单和短屏 |
| 主题、Modal、Drawer、复杂表单 | Light/Dark 使用同一 surface level；warning/muted/disabled 对比度实测；Modal 只有 body 滚动且 footer 固定；关闭按钮视觉紧凑但热区 44px；下拉 trigger 填满网格；Escape、Tab 循环、恢复焦点和 portal stacking 全部通过 | common overlays/forms、index.css | OverlayLayer、Surface、Field | overlay 状态矩阵、390x667 软键盘、200% zoom |

模块迁移完成不以“引用了一个公共组件”为标准。必须同时满足：页面不再平行实现相同行为、状态覆盖完整、断点行为已验证、旧 class/alias 有删除证据。

## 13. 测试、截图与验收矩阵

### 13.1 必跑命令

\`\`\`bash
cd apps/dsa-web
npm ci
npm run lint
npm run test
npm run test:i18n
npm run build
npm run test:e2e-security-preflight
npm run test:smoke
\`\`\`

若只改 Primitive，也必须运行相关单测、lint 和 build；合并前由 CI 运行完整 Web gate 与真实后端隔离 smoke。API/Schema 联动改动还需运行对应后端测试。

### 13.2 测试层级

| 层级 | 必须覆盖 |
| --- | --- |
| TypeScript/unit | props、ref、event、状态转换、legacy adapter、formatter |
| Design guard | native control 边界、raw color、invalid utility、overlay z、领域 class、旧 alias |
| i18n guard | JSX 文本、aria、placeholder、toast、运行状态、错误文本 |
| Component interaction | keyboard、focus、Escape、outside click、restore focus、form submit、password field 属性 |
| Page integration | loading/empty/error/disabled/partial/ready、筛选持久化、路由深链 |
| Playwright | 导航、关键 CTA、overlay、表格、短视口、主题、语言 |
| Manual a11y | 200% zoom、screen reader 快速检查、contrast、reduced motion、软键盘 |

### 13.3 视口截图矩阵

| 视口 | 目标设备/风险 | 必查内容 | 主题 |
| --- | --- | --- | --- |
| 1280x820 | 标准桌面 | 全局侧栏、业务辅助区、表格、Popover | Light + Dark |
| 1024x768 | 小桌面断点 | 全局侧栏刚出现时不得再叠固定业务 rail | Light + Dark |
| 900x800 | 平板横向/中间宽度 | category/filter/session/history 转 Sheet | Light + Dark |
| 768x900 | 平板临界点 | \`md\` 与 \`lg\` 之间导航、表格和操作栏 | Light + Dark |
| 767x900 | 断点前一像素 | 无断点跳闪、无隐藏主操作 | Light + Dark |
| 390x844 | 常见移动端 | drawer、modal、select、长表单、表格替代视图 | Light + Dark |
| 390x667 | 短移动端 | 软键盘、sticky action、modal footer、滚动可达 | Light + Dark |
| 320x700 | 最窄支持宽度 | 无页面横溢、文本不遮挡、44px 热区 | Light + Dark |

每个页面至少采集 Ready；有业务意义的页面还必须采集 Loading、Empty、Error，以及适用的 Disabled、Partial、Running、No-account。截图使用固定 mock、固定时间和固定语言，存为 CI artifact 或 PR 附件，不合入仓库。

### 13.4 模块验收重点

| 模块 | 必须交互 | 必须状态 | 特殊证据 |
| --- | --- | --- | --- |
| Shell/Profile | open、locale、theme、Escape、restore focus | closed/open | 1024/900 导航对比 |
| Home | history open/select/close、retry | loading/empty/error/data | 业务 rail 不与全局侧栏并存 |
| Chat | new/select session、send、cancel、timeout | idle/streaming/error | 中英文 stage 文案 |
| Settings | category/view、edit/save/cancel | clean/dirty/saving/error | Select/MultiSelect 等宽 |
| Screening | filter/apply/reset、row action | disabled/empty/loading/data | advanced filter Sheet |
| Portfolio | create account、validation、row/detail | no-account/empty/data/error | 无账户不展示零 dashboard |
| Signals | filter、sort、detail drawer | empty/loading/data/error | action label 一致 |
| Backtest | configure/run/cancel/rerun | initial/running/result/error | 未运行不显示空性能面板 |
| Alerts | create/toggle/delete/history | empty/data/error | 行操作键盘可达 |
| Usage | range/filter/detail | zero/data/error | zero 不显示空 table |
| Report/Run Flow | action、details、node drawer | partial/error/ready | 错误详情默认折叠 |

## 14. 风险、兼容、回滚与依赖

### 14.1 主要风险

| 风险 | 影响 | 控制措施 |
| --- | --- | --- |
| 巨型页面拆分导致状态或闭包漂移 | 保存、流式、筛选行为回归 | 先补集成测试；拆布局不改状态所有权 |
| 公共 Button/Field 改动波及全站 | 表单提交、focus、尺寸回归 | 向后兼容 alias；首批代表调用；状态矩阵截图 |
| Overlay 栈重构 | Select 被 Modal 遮挡、焦点丢失 | 统一 portal/layer；nested overlay E2E |
| 表格抽象过度 | 领域单元格与行操作受限 | DataTable 只管结构，formatter 和 action 保持领域层 |
| 响应式隐藏信息 | 平板用户找不到筛选/历史 | 明确触发器、保留状态、断点两侧截图 |
| 状态 contract 兼容 | 历史报告或旧 API 无 action code | adapter fallback、unknown 状态、逐步弃用 |
| Figma 照搬 | 品牌偏移、低对比、布局不适业务 | 采用矩阵逐条审批；只借层级和组件状态 |
| allowlist 变成永久债务 | 守卫失效 | 每项记录 owner、introduced PR、remove_by_batch；Batch 6 清零 |

### 14.2 行为兼容原则

- 路由、query 参数、API payload、配置 key 和持久化 key 默认不变。
- 组件迁移不得改变 click、change、submit、Escape 和 focus restore 的可观察行为，除非该行为就是明确 bug。
- 旧 API 字段只在 adapter 层 fallback，UI 不直接判断历史字符串。
- 视觉 alias 最多跨两个 Batch；没有调用方后立即删除。
- 新状态必须区分“未加载”“加载中”“零数据”“错误”，不得用 \`0\`、空数组或 \`undefined\` 互相代替。

### 14.3 Allowlist 生命周期

任何守卫 allowlist 条目必须包含：

\`\`\`text
file/pattern | reason | owner | introduced_pr | remove_by_batch | delete_condition
\`\`\`

- 不接受无 owner 或无删除条件的条目。
- 新增产品代码不得进入历史 allowlist。
- Batch 6 完成条件是 allowlist 清零；确有第三方或生成代码例外时，需 maintainer 明确批准并写永久边界。

### 14.4 回滚策略

1. 正确性、Primitive、Pattern、页面迁移、视觉 token 分开提交。
2. 每个 PR 只覆盖一个可描述的行为集合，revert 后不要求恢复其他 PR。
3. 数据 contract 先兼容读取再切写入，最后删除 fallback。
4. 视觉回滚不能恢复虚假 TLS 文案、密码误填或错误动作语义。
5. 临时兼容组件必须有调用计数和删除测试，避免 revert 后产生双实现。

## 15. PR 切片与推荐实施顺序

### 15.1 推荐顺序

| 顺序 | PR 标题建议 | 范围 | 合入门槛 |
| ---: | --- | --- | --- |
| 1 | \`test: establish web UI visual and architecture guards\` | 基线、8 视口、守卫与 allowlist | 不改变产品行为，CI 稳定 |
| 2 | \`fix: correct login and credential field semantics\` | TLS 与敏感输入 | 安全语义测试通过 |
| 3 | \`fix: unify decision action and model access status contracts\` | action/status adapter | 新旧载荷均通过 |
| 4 | \`refactor: standardize button and form primitives\` | Button/IconButton/Field/Input | 兼容调用、ref、form 测试 |
| 5 | \`refactor: unify selection and toggle controls\` | Select/Search/MultiSelect/Switch/Checkbox | Figma 状态与键盘证据 |
| 6 | \`refactor: centralize surfaces overlays and progress states\` | Surface/State/Alert/Overlay/Progress | nested overlay 通过 |
| 7 | \`refactor: standardize page shell and section patterns\` | Shell/AppPage/PageHeader/Section | 8 视口壳层截图 |
| 8 | \`refactor: add responsive filters and data table patterns\` | Filter/DataTable + 两个样板调用 | 窄屏和键盘通过 |
| 9 | \`feat: move theme and locale controls into profile menu\` | ProfileMenu | persistence/a11y 通过 |
| 10 | \`refactor: simplify home layout and responsive history\` | Home | 状态和断点截图 |
| 11 | \`fix: improve chat navigation and localized run states\` | Chat | streaming/timeout 回归 |
| 12 | \`refactor: standardize settings navigation and form controls\` | Settings/LLM | save/dirty/error 回归 |
| 13 | \`fix: clarify screening availability and responsive filters\` | Screening | disabled/data 回归 |
| 14 | \`fix: simplify portfolio states and account workflow\` | Portfolio | 四状态与表单回归 |
| 15 | \`refactor: improve decision signal filters and action semantics\` | Signals | filter/action/drawer 回归 |
| 16 | \`fix: clarify backtest stages and controls\` | Backtest | stage contract 回归 |
| 17 | \`refactor: standardize alert and usage data states\` | Alerts/Usage | CRUD/zero state 回归 |
| 18 | \`refactor: unify report and run flow feedback\` | Report/Run Flow | legacy/partial/error 回归 |
| 19 | \`fix: simplify route and runtime error presentation\` | Error/NotFound | retry/dismiss 回归 |
| 20 | \`chore: remove legacy web UI compatibility paths\` | aliases/old components/classes | 调用为零、守卫通过 |
| 21 | \`fix: complete web theme and accessibility consistency\` | token/a11y/visual | 双主题、manual a11y |
| 22 | \`test: finalize responsive visual acceptance coverage\` | 最终截图与 E2E | 全矩阵稳定 |

### 15.2 每个 PR 必须包含

- 英文标题和英文 PR 正文。
- 原问题、根因、修复点和回归风险。
- 影响模块与明确非目标。
- 实际执行的测试命令及结果。
- 用户可见 UI 变更的前后截图；双主题和受影响视口。
- API/Schema/持久化兼容说明。
- 回滚方式。
- 新增兼容 alias 或 allowlist 的删除条件。

不得把 22 个建议 PR 强制机械执行。若两个连续 PR 的组件和调用方高度耦合，可合并，但单个 PR 不应跨越 Primitive、多个复杂页面和全局 token 三个风险层。

## 16. Definition of Done

### 16.1 架构

- 7 个常规业务页统一使用 AppPage/PageHeader，NotFound 使用最小 AppPage；Home、Chat、Login 的专用布局由页面守卫和本文记录为明确例外。
- 页面不再平行实现 Button、IconButton、Field、Select、Switch、Checkbox、Alert、StatePanel、Progress 和 Overlay 行为。
- \`pages/**\` 不直接渲染 raw button/input/select/textarea；语义例外通过公共 Pressable 或 Input primitive 表达。
- Toolbar、Section、DataTable 等 Pattern 至少由两个领域验证，不是只为单页包装。
- \`home-*\`、\`settings-*\` 不再泄漏到公共组件或其他领域。
- Card default/bordered、Button 领域 alias、旧 EmptyState 平行实现均完成删除或有批准的保留原因。
- 登录和 404 可以使用最小页面壳层，但必须记录为 AppPage 契约的明确例外。

### 16.2 正确性与交互

- HTTP 页面不宣称 TLS；敏感字段不被浏览器当作登录密码。
- 同一决策在历史、报告、列表和详情中的 action 标签与颜色一致。
- UI 逻辑不依赖中文或英文展示字符串判断状态。
- 所有表单错误就近展示并与输入建立 aria 关系。
- Modal、Drawer、Select、Popover、Toast 的层级、Escape、focus trap 和 focus restore 正确。
- 所有图标操作有可访问名称，触控热区至少 44px，视觉尺寸符合工具栏密度。
- 每页或每个独立表单区域最多一个高对比 Primary；危险操作不会伪装成普通主操作。

### 16.3 状态与响应式

- 每个数据模块明确覆盖 Loading、Empty、Error、Ready，以及适用的 Disabled、Partial、Running、No-account。
- 无账户/零调用/未运行页面不显示完整零值仪表盘或无意义空表。
- 1280、1024、900、768、767、390x844、390x667、320 八视口无页面横向溢出和操作遮挡。
- 任一视口最多一个固定侧栏；高级筛选、历史和会话在中间视口可通过明确触发器访问。
- 从 1280 缩到 1024、900、768、767 时内容宽度单调收敛，不出现更窄视口正文反而更宽或双侧栏重新出现。
- 长中文、长英文和自动化短视口下主操作可见可达；200% zoom 与真实软键盘列入发布前人工复核。

### 16.4 视觉与主题

- 所有颜色、surface、radius、elevation、focus 和 overlay layer 使用语义 token。
- \`bg-surface\` 等无效 utility 为 0；页面/domain 的 raw hex、raw palette、\`bg-white\`、\`border-white\` 为 0。
- Overlay 只从统一 layer 取值，overlay 目录外固定 \`z-*\` 或 \`z-[...]\` 为 0。
- 普通 Button 不默认 \`rounded-full\`；chip、status、SegmentedControl 与命令按钮视觉语义清楚。
- Shell 和页面级主卡片保留；普通子区块避免无语义 card-in-card，同一层级的 Card 宽度与间距一致。
- 连续数据表复用 DataTable 基础层；桌面筛选紧凑，移动高级筛选进入 Bottom Sheet。
- Light/Dark 均满足对比度和状态区分，Figma 只作为层级和组件状态参考。

### 16.5 验证与交付

- \`npm run lint\`、\`npm run test\`、\`npm run test:i18n\`、\`npm run build\`、安全预检和 smoke 全部通过。
- 本轮未改 API/Schema/持久化契约，无需新增后端契约测试。
- 最终证据包含八视口、双主题、11 个一级路由和 manifest 索引。
- 截图和一次性证据保存在 PR/Actions artifact，不提交进仓库。
- guard allowlist 清零或仅剩 maintainer 批准的永久边界。
- \`docs/CHANGELOG.md\` 已按扁平 \`[Unreleased]\` 格式更新。
- 风险、人工未验证项和回滚方式与当前工作树一致；本轮未 commit、未 push。

自动化范围内的 Definition of Done 已满足。发布前仍需在真实设备完成 200% zoom、系统读屏器与软键盘快速巡检；这些人工项不由本地自动化截图冒充完成。

## 17. 最终执行记录

### 17.1 自动化证据

| 检查 | 结果 |
| --- | --- |
| \`npm ci\` | 完成；安装 463 个包，报告 16 个既有依赖漏洞（1 low、5 moderate、10 high），未执行破坏性自动修复 |
| \`npm run lint\` | 通过 |
| \`npm run test\` | 168 个测试文件，1897 项通过，2 项按既有条件跳过 |
| \`npm run test:i18n\` | 94 项通过；197 条记录、3446 个 key、8 个 locale bundle 一致 |
| \`npm run build\` | 通过；转换 3324 个模块 |
| \`npm run test:e2e-security-preflight\` | 62 项通过 |
| \`npm run test:smoke\` | 136 项全部通过，耗时约 6.6 分钟 |
| 视觉矩阵 | 176 张截图；failures、missingFiles、documentOverflow 均为空 |
| \`git diff --check\` | 通过 |

证据目录：\`.context/ui-ux-remediation-acceptance/\`。该目录被 gitignore，仅用于本地验收，不会作为一次性图片进入仓库。

### 17.2 兼容、风险与回滚

- 路由、query、API payload、配置 key、持久化 key 和后端 Schema 均未改变。
- Shell 与页面级大卡片保留；页面宽度和标题仅由 AppPage/PageHeader 在常规业务页统一。
- 真实读屏器、200% 系统缩放和移动设备软键盘仍需发布前人工复核。
- 依赖审计中的 16 个漏洞不属于本 UI 修复范围，未通过 \`npm audit fix\` 引入额外依赖变更。
- 回滚时按共享 Primitive、跨页面 Pattern、领域页面迁移和视觉 token 分组恢复；安全语义、结构化 action 与密码字段修复不应随纯视觉回滚撤销。
- 当前工作树未 commit、未 push；合入前需先处理当前分支相对 \`origin/main\` 的 9 ahead / 18 behind 历史差异。
