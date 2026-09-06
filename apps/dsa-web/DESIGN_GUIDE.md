# StockPulse Web 设计准则

> `src/index.css` 和公共组件是当前可执行视觉事实；本文档是 StockPulse **已采纳视觉规则**的
> 权威。[UI 信息架构审计](../../docs/stockpulse-ui-information-architecture.md) 的 HITL-H1～H8
> 已于 2026-07-17 由维护者批准（结论见其 §18.1），自此是导航、页面归属、URL、状态与交互
> 契约的已批准目标；实施仍须按其 §17 顺序、tracker 登记与各 slice 门禁推进，不得越序启动
> UI-02～UI-07 父任务。Coinstax/Figma 仅是外部模式参考；只有 `docs/DESIGN.md` 明确批准并
> 完成 StockPulse 语义映射的颜色变量值可作为目标 token，外部变量名、raw fill、产品需求、
> 组件 API、页面 IA 和像素细节均不是权威。

## 0. 铁律

1. **任务范围先行**：纯视觉任务禁止修改组件 props / TS 接口与类型、hooks、事件处理、
   状态管理、API、数据流、i18n key 和路由，只允许改已批准的样式面。IA、交互或 URL
   任务必须在独立 slice 中获得明确批准；UI-01 获批后才遵循其冻结的 IA 契约，不能把候选
   结论夹带在视觉 diff 中。
2. **红涨绿跌不可动**：Layer 0 `--price-red`/`--price-green` 色相与 `--price-up`/`--price-down` 方向 token
   （默认 `data-price-direction=cn` 红涨绿跌）是中国市场约定，与「绿色品牌强调色」是两套独立语义，严禁合并、串色或改值。
3. **遇到问题必须求助，不许猜**：项目 token 未覆盖、外部参考与产品语义冲突、
   lint/build 报错涉及任务范围外逻辑、拿不准是否需要扩展公共组件——一律停下提问。
   提问时给出：页面/文件、现状、StockPulse 依据、外部参考（如有）和倾向方案。
4. **禁止硬编码**：
   - 组件和普通生产 `TS/TSX/JS/CSS` 不得出现 raw hex；新增运行时颜色必须引用
     `src/index.css` 的 semantic token。唯一允许声明 raw color source value 的生产入口，是
     `src/index.css` 的 `:root` / `.dark` 内 semantic-token custom-property declaration。这不是
     `index.css` 整文件豁免；非 token CSS declaration、组件、types、utils 和 renderer 均不得
     使用 raw hex，组件内也禁止 `bg-[#151514]`、`text-[#41B83D]` 等任意值类名或内联 hex。
   - 设计文档中的 HSL-to-hex 换算值只用于人工审阅，不是可复制到生产组件或样式的实现值。
     测试与 fixture 如确需固定 hex，必须进入具名显式白名单，并逐项记录文件、值及颜色语义或
     guard sentinel 用途；目录级排除不等同于白名单。
   - 当前 `productionDesignGuard.test.ts` 的可执行生产扫描覆盖 `TSX`，以及由 CSS 路径完整性
     断言约束的 `App.css` / `index.css`；尚未加载 `.ts` / `.js`，当前 types/utils 中的 `.ts` 与
     其它 `.ts/.js` 生产路径缺口继续登记在 `UI01-P2-06`。因此本规则尚未对所有生产源类型自动执行。
   - 字号/圆角优先用现有 tailwind 阶梯与 `--radius` 体系，不写魔法数字。
     **结构间距**（页面/区块/工具条/叠层 pad 与 gap）必须用 `src/index.css` 的 `--density-*`
     与 `density-gap-*` / `density-surface-pad-*` / `density-overlay-pad*`，不要在已接入密度
     的共享组件或页面上退回固定 `p-4` / `gap-4`。舒适密度是默认值；区域可设
     `data-density="compact"`。可执行棘轮与固定几何豁免见
     [`docs/web-ui-foundation.md`](../../docs/web-ui-foundation.md) 的 D5 与
     `src/design/density.ts`。
   - 产品页不要新增原生 `<button>` 或 `role="button"` 宿主；使用共享 `Button` /
     `IconButton` / `Pressable`（或已登记的复合控件）。可执行棘轮与无障碍豁免见
     [`docs/web-ui-foundation.md`](../../docs/web-ui-foundation.md) 的 Shared-control
     adoption ratchet 与 `src/design/sharedControlAdoptionBaseline.json`。本规则不要求
     一次性改完现有页面。
   - 不写死密钥、账号、路径、模型名、端口或环境差异逻辑（仓库硬规则）。

## 1. 设计基调

- **中性极简**：米白/近黑双主题，大量留白，极浅边框分层，轻投影。
- **禁止**：cyan/purple 辉光（glow）、pulse-glow 动画、彩色渐变发光、玻璃拟态强模糊。
- **字体**：Geist。标题通过字号、SemiBold 字重和层级建立差异，`letter-spacing: 0`。
- **形状**：按钮一律软圆角 `rounded-lg`（`var(--radius)`），禁止胶囊形 `rounded-full`；装饰性圆点用 `--radius-dot`；卡片保留大圆角（`--radius` 体系不变）。

## 2. 颜色 Token（当前项目定义）

下表是审计基线 `ed729c1b` 中 `src/index.css` semantic token 的文档快照。HSL 源值是精确
代码事实，hex 仅是便于人工审阅的换算值，不是生产实现值或测试 fixture 的默认来源。代码
取值与本表不一致时，应先核对当前实现和变更历史，再更新本表；不得用外部文件变量静默
覆盖项目 token。

### 2.1 基础色

| 语义 / 变量 | Light 源值（换算） | Dark 源值（换算） |
|---|---|---|
| 背景 `--background` | `120 7% 97%` (`#F7F8F7`) | `60 3% 8%` (`#151514`) |
| 主文本 `--foreground` | `60 3% 8%` (`#151514`) | `0 0% 100%` (`#FFFFFF`) |
| 卡片 `--card` | `0 0% 100%` (`#FFFFFF`) | `70 4% 11%` (`#1D1D1B`) |
| 次级文本 `--secondary-text` | `74 5% 38%` (`#63665C`) | `75 5% 72%` (`#B9BBB4`) |
| 弱化文本 `--muted-text` | `74 4% 52%` (`#878980`) | `75 4% 55%` (`#8F9188`) |
| 边框 `--border` | `80 7% 92%` (`#EBECE9`) | `75 4% 20%` (`#343531`) |

### 2.2 状态源色

| 状态 / 变量 | Light 源值（换算） | Dark 源值（换算） |
|---|---|---|
| Success `--color-success` | `118 50% 42%` (`#39A136`) | `118 50% 72%` (`#96DB94`) |
| Warning `--color-warning` | `50 90% 42%` (`#CBAB0B`) | `50 88% 72%` (`#F6E179`) |
| Error `--destructive` / `--color-danger` | `345 79% 58%` (`#E93F6A`) | `350 89% 72%` (`#F7788D`) |
| Error alert text `--color-danger-alert-text` | `345 79% 42%` (`#C01641`) | `350 89% 78%` (`#F995A6`) |

审计基线没有独立的固定 Success/Warning/Error 背景与边框 hex 三件套。Badge、Alert 等公共
组件由上述源色按透明度派生背景和边框；不得把外部参考中的不透明色值写成项目 token。

### 2.3 品牌强调色 = 绿

- `--primary` = light `118 50% 48%` (`#41B83D`) / dark `118 50% 72%`
  (`#96DB94`)。它是品牌色，不与 `--color-success` 合并；两者在 dark 下同值不代表语义相同。
- 用途：导航激活态、链接、焦点环（focus ring）、选中态。
- **主 CTA 按钮不用绿**，用黑白反色（见 §4.1）。

### 2.4 ⚠️ 涨跌色（不可触碰）

- **Layer 0 色相身份**：`--price-red` = 红、`--price-green` = 绿。与品牌绿 / success 是独立语义，**禁止合并变量、禁止互相引用、禁止改值**。
- **方向 token**：`--price-up` / `--price-down` 由 `data-price-direction` 映射（默认 `cn` = 红涨绿跌；`us` = 绿涨红跌）。
- **遗留别名**：`--home-price-up` → `var(--price-red)`，`--home-price-down` → `var(--price-green)`（色相身份，非方向）。
- 审计快照：`--price-red` light `0 88% 62%` (`#F34949`) / dark
  `0 88% 64%` (`#F45252`)；`--price-green` light `149 100% 42%`
  (`#00D668`) / dark `149 100% 44%` (`#00E06C`)。
- 运行时偏好：Settings `MARKET_REVIEW_COLOR_SCHEME`（`red_up`/`green_up`）同步到 `data-price-direction`；`marketFormat.changeSemantics` 按市场惯例/用户偏好映射方向 → 色相 paint。
- 持仓、回测、选股结果、市场结构、财务计算器的涨跌/盈亏展示走 `SignedChangeText`（`changeSemantics` + `changeColorCssVar`），偏好读取现有 ThemeAppearance / `data-price-direction`，不要再加并行 preference hook。禁止把有符号值映射到 `text-success` / `text-danger`。零值、缺失、非有限值、无法解析的市场保持未上色，禁止把未知代码默认成 `cn`。符号或文案作为非颜色线索。

### 2.5 Theme Contract v1（#162 / #880）

- 目录：`src/design/theme.ts` + `themePacks.ts` + `themeTokenInventory.ts`；运行时：`data-theme-pack` / `data-price-direction`。
- Pack 仅可写 Layer 1 核心语义；**禁止** pack 覆盖 Layer 0 涨跌色。
- 内置 pack：`classic`（默认 / `:root`）、`slate`（中性品牌验证变体）。
- 守卫：`themeContractGuard.test.ts` 采用与 production design guard 相同的「基线只减不增」天花板。
- 格式策略：Layer 1 继续使用 bare HSL channel triples（Tailwind 互操作）；Layer 0 使用完整 `hsl(...)` 颜色串。

### 2.6 Theme token freeze（Phase 0 / #1300）

- **冻结当前自定义属性名集合**，不在本阶段删除 page-scoped 遗留、不统一格式、不引入第二套 token 系统。
- 可执行清单：`THEME_DEFINED_TOKEN_NAMES`（`src/index.css` 的 unique 定义）+ `classifyThemeToken()`。
- **禁止新增** `--home-*` / `--settings-*` / `--chat-*` / `--backtest-*` / `--portfolio-*`。这些名字记为 `page-scoped-debt`，不得晋升为 Layer 1 来让 CI 变绿。`--home-price-up/down` 仍是 Layer 0 色相别名。`--login-*`、`--backtest-*`、`--portfolio-*`、`--chat-*`、`--settings-*`、`--home-action-*` 与 `--home-prose-*` 已在 Phase 2 清零，`--home-title-accent` 也已收敛，禁止重新引入这些前缀或 action/prose/title-accent 遗留。
- 新 UI 只用 Layer 1 + `components/common`；缺色用 `hsl(var(--token) / alpha)`，不要为每个透明度再开 token。
- 未定义的 `var(--*)`（如 `--home-border`、`--info`、`--color-purple`、`.input-surface` 可选槽）登记在 freeze 守卫测试里的 `THEME_UNGOVERNED_REFERENCE_DEBT`（`themeTokenFreezeGuard.test.ts`），只减不增，且**不得**写进已定义清单冒充合法 token。
- Desktop 嵌入的 WebView 走同一套 Web token。`apps/dsa-desktop/renderer/assistant.html` / `loading.html` 是独立 chrome 清单，禁止把 `--bg` / `--panel` 并进 Web Layer 1。
- 有意新增：写入 `THEME_LAYER1_CSS_VARS`（或仅市场色可写 Layer 0）→ 在 `:root` 与 `.dark` 赋值 → 追加 `THEME_DEFINED_TOKEN_NAMES`。领域几何可用 `--nav-*` / `--report-*` / `--input-surface-*`。守卫：`themeTokenFreezeGuard.test.ts`。详细失败码见 [`docs/web-ui-foundation.md`](../../docs/web-ui-foundation.md)。
- **WAIT_FOR 密度集成**：若把 18 个结构间距自定义属性名写成 `themeTokenInventory.ts` 字符串字面量，`densityAdoptionRatchet` 会把该清单测成 `new-density-aware-file`（`densityTokenCount=18`）。这是目录字符串假阳性，不是主题消费者接入。T24 **不改** 密度扫描器；间距名从已有 `DENSITY_STRUCTURAL_CSS_VARS` 组合进来。是否把非 `density.ts` 的 design catalog 排除出消费者清单，留给密度实现/审查决定。

### 2.7 Phase 2 域收敛：Login（#1300）

- 七个 `--login-*` 定义（light + dark）已删除，`LoginPage` 直接消费 Layer 1；未新增 `--auth-*` 领域 token。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 107 降到 100；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 由 32 条降到 26 条。
- 映射：`--login-bg-main` → `bg-background`；`--login-bg-card` → `bg-card`；`--login-border-card` → `border-border`；`--login-text-primary` → `text-foreground`；`--login-text-secondary` → `text-secondary-text`；`--login-text-muted` → `text-muted-text`；`--login-accent-soft` → `selection:bg-[hsl(var(--primary)/0.08)]`。
- 文字色映射在两种模式下逐一等值或对比度更好；仅卡片描边是有意变化：`--border` 已经是 App 外壳 / Home 面板 / 侧栏的卡片边界，Login 不再自持一套灰阶。
- 因为改用 Layer 1，`data-theme-pack="slate"` 首次能够为登录页换色，与 pack 契约一致。详细对比数值见 [`docs/web-ui-foundation.md`](../../docs/web-ui-foundation.md)。

### 2.8 Phase 2 域收敛：Backtest（#1300）

- 六个 `--backtest-*` 定义（light + dark）已删除；未新增页面级 token。`BacktestPage.tsx` 仍只用既有 class name，不含 `--backtest-*`。
- 四个无引用定义直接删除：`--backtest-border-light`、`--backtest-spinner-head`、`--backtest-spinner-track`、`--backtest-table-bg`。
- 两个在用的描边在 Backtest Workspace 配方处内联为当前 light/dark 的 `hsl(var(--foreground) / alpha)`：`--backtest-border-dim` → `.backtest-metric-row` / `.backtest-summary` 的 `0.05`（`.dark` 下 `0.06`）；`--backtest-border-subtle` → `.backtest-status-chip` 的 `0.06`（无 tone 的 `.dark` 回退为 `0.08`）。成功 / 危险 / 中性 chip 颜色与 `.backtest-metric-footer`（仍为 `--border / 0.40`）不变。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 100 降到 94；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 26（这六个名字不在格式债清单中）。
- 这些描边现已使用 Layer 1 既有 `--foreground` 语义 token 加透明度，因此可以跟随覆盖 `--foreground` 的主题包换色；当前 `slate` pack 覆盖 `--border`、不覆盖 `--foreground`，所以目前不会给这些描边换色。

### 2.9 Phase 2 域收敛：Portfolio（#1300）

- 唯一剩余的 `--portfolio-control-border` 定义（light + dark）已删除；未新增页面级或领域 token。`THEME_PAGE_SCOPED_PREFIXES` 仍永久禁止 `--portfolio-*`。
- 唯一在用的调用点是 light 下 `.portfolio-page .btn-secondary:not(:disabled)` 的描边，现内联为 `hsl(var(--foreground) / 0.2)`，与 Backtest 的 Layer 1 + use-site alpha 配方一致。`:not(:disabled)`、hover 阴影、focus 与默认 `.btn-secondary` 的 dark 回退（`--border-subtle` = `--foreground / 0.08`）不变。
- dark 赋值原先等于 `--border`（`75 4% 20%`），且没有 `.dark .portfolio-page .btn-secondary` 消费者，因此随定义一起删除，不另加 dark 覆盖。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 94 降到 93；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 26（该名字不在格式债清单中）。
- 当前 `slate` pack 覆盖 `--border`、不覆盖 `--foreground`，所以目前不会给这条 leftover 描边换色。

### 2.10 Phase 2 域收敛：Chat（#1300）

- 17 个 `--chat-*` 定义已删除：10 个 avatar / bubble 名字（`:root` + `.dark`），7 个 `--chat-prose-*` 名字（定义在 `.chat-prose` 规则内）。未新增页面级或领域 token，`THEME_PAGE_SCOPED_PREFIXES` 仍永久禁止 `--chat-*`。
- 调用点改为 Layer 1 + use-site alpha，基础规则保留原 light 值：`.chat-avatar-user` = `hsl(var(--primary) / 0.5)` / `hsl(var(--foreground))` / `hsl(var(--primary) / 0.3)`；`.chat-avatar-ai` = `hsl(var(--primary) / 0.1)` / `hsl(var(--foreground) / 0.8)` / `hsl(var(--primary) / 0.2)`；`.chat-bubble-user` = `hsl(var(--primary) / 0.1)` 底 + `hsl(var(--primary) / 0.2)` 描边；`.chat-bubble-ai` = `hsl(var(--card) / 0.85)` 底。
- 真正存在差异的 dark 赋值改为显式 `.dark .chat-avatar-user`、`.dark .chat-avatar-ai`，以及在既有 `.dark .chat-bubble-ai` 上补 `background-color`，选择条件仍是同一个 `.dark` 祖先。`--chat-bubble-user-bg` / `--chat-bubble-user-border` 的 light 与 dark 取值相同，因此不加 dark 覆盖。
- `--chat-bubble-ai-border` 无任何消费者（`.chat-bubble-ai` 是 `border: 0`），随定义一起删除，不做替换。
- Prose：`--chat-prose-fg` 在三处调用点内联为 `hsl(var(--foreground) / 0.86)`，原 `.dark .chat-prose { --chat-prose-fg }` 改为覆盖 `.chat-prose` / `h1`–`h4` / `strong` 的显式 `.dark` 分组；后面的 `.dark .chat-prose h2`（`--secondary-text`）仍按源码顺序胜出，行为不变。`--chat-prose-border` / `--chat-prose-border-strong` 原本就是 `--home-prose-border(-strong)` 的别名，当时改为直接引用后者；随后在 §2.13 把 `--home-prose-*` 也内联为 Layer 1。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 93 降到 76；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 26（这 17 个名字不在格式债清单中）；`TOKEN_FORMAT_OVERRIDES` 中两条 prose 描边别名同步删除，因为该守卫要求 override key 必须仍有定义。
- `themeContractGuard` / `themeTokenFreezeGuard` 的非空下界由 200 降到 190：它们只是「清单被截断」的兜底断言，四次 Phase 2 收敛已把已定义清单从 210 降到 196。
- 主题包行为不变：被删除的名字原本就定义在 `:root` 上且以 `--primary` / `--card` / `--foreground` / `--background` 表达，因此收敛前后 Chat 都会跟随 pack 换色。渲染对比显示 `data-theme-pack="slate"` 在前后两个构建里换色的是同样 8 个元素（`chat-avatar-ai`、`chat-avatar-user`、`chat-bubble-ai`、`chat-bubble-user`，以及 prose 的 link / code / pre / blockquote）。

### 2.11 Phase 2 域收敛：Settings（#1300）

- 20 个 `--settings-*` 定义（light + dark）已删除；未新增页面级或领域 token。`THEME_PAGE_SCOPED_PREFIXES` 仍永久禁止 `--settings-*`。
- 八个无引用定义直接删除：`--settings-accent-shadow`、`--settings-border-overlay`、`--settings-primary-border`、`--settings-secondary-bg`、`--settings-secondary-bg-hover`、`--settings-secondary-border`、`--settings-secondary-border-hover`、`--settings-surface-overlay`。
- 在用调用点改为 Layer 1 + use-site alpha：`--settings-surface` / `--settings-surface-strong` → `bg-card`；`--settings-surface-hover` → `bg-hover`；`--settings-surface-panel` → `bg-background`；`--settings-surface-overlay-soft` → `bg-muted`；`--settings-surface-overlay-muted` → `bg-[hsl(var(--background)/0.12)]`；`--settings-border` → `border-border`；`--settings-border-soft` → `border-border/60`；`--settings-border-strong` → `border-foreground/20` / `hover:border-foreground/20`；`--settings-skeleton-strong` → `bg-muted`；`--settings-skeleton-soft` → `bg-muted/50`。
- Settings 输入框 rest 描边仍由 `.settings-page .input-surface:not(:hover):not(:focus):not(:disabled)` 覆盖，light 内联 `hsl(var(--border) / 0.72)`，dark 内联 `hsl(var(--border) / 0.58)`。hover / focus / error / disabled 仍走共享 `.input-surface`、`Input`、`border-danger` 与 disabled opacity，不新增 token。
- 删除包装这些 token 的 helper class（`.settings-surface-strong` / `.settings-surface-panel` / `.settings-surface-overlay-soft` / `.settings-surface-overlay-muted` / `.settings-border` / `.settings-border-strong` / `.settings-skeleton-strong` / `.settings-skeleton-soft`）。`.settings-accent-text` 与 `.settings-drag-active` 已使用 Layer 1 `--primary`，予以保留。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 76 降到 56；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 由 26 条降到 12 条（删除 14 条 Settings raw `hsl()` 债）。非空下界由 190 降到 170。
- 因为改用 Layer 1，`data-theme-pack="slate"` 首次能够为 Settings 卡片与描边换色。Layer 0 涨跌色与 `--home-price-*` 别名不变。亮色卡片描边从旧 `--settings-border`（`80 7% 82%`）软化为 Layer 1 `--border`（`80 7% 92%`），与 Login 相同，属于非文字装饰差；详细对比方法见 [`docs/web-ui-foundation.md`](../../docs/web-ui-foundation.md)。

### 2.12 Phase 2 域收敛：Home-action（#1300）

- 八个 `--home-action-*` 定义（light + dark）已删除；未新增页面级或领域 token，也未新增 `--chat-jump-*` / `--chat-copy-*`。`THEME_PAGE_SCOPED_PREFIXES` 仍永久禁止 `--home-*`。
- 四个无引用定义直接删除：`--home-action-report-bg`、`--home-action-report-border`、`--home-action-report-text`、`--home-action-report-hover-bg`。
- 唯一在用调用点是 Chat「最新消息」跳转按钮 `.chat-copy-btn`（`ChatPage.tsx` 的 `showJumpToBottom`；class 名是历史遗留）。消息复制 / 下载仍走 `IconButton`，不使用该 class。配方改为 Layer 1 `--primary` + use-site alpha：底 `hsl(var(--primary) / 0.1)`、描边 `hsl(var(--primary) / 0.2)`、文字 `hsl(var(--primary))`；light hover `0.18`，dark hover 用显式 `.dark .chat-copy-btn:hover` 保持 `0.2`，二者不得抹平。
- `:active` 位移、与 `.session-item` / `.delete-btn` 共用的 `:focus-visible` 主色环（`box-shadow: 0 0 0 3px hsl(var(--primary) / 0.16)`）、以及 `min-height: 2.75rem` 均保持不变。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 56 降到 48；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 12（这八个名字不在格式债清单中）。非空下界由 170 降到 160。
- 这些值原本就包装 `--primary`，因此 `data-theme-pack="slate"` 在收敛前后都会给跳转按钮换色，**不是**首次换色。Layer 0 涨跌色与 `--home-price-up/down` 别名不变。其余 `--home-*` 族（prose / cool / shadow / panel / surface）不在本切片。

### 2.13 Phase 2 域收敛：Home-prose（#1300）

- 四个 `--home-prose-*` 定义（light + dark）已删除：`--home-prose-border`、`--home-prose-border-strong`、`--home-prose-blockquote-border`、`--home-prose-blockquote-bg`。未新增页面级或领域 token。`THEME_PAGE_SCOPED_PREFIXES` 仍永久禁止 `--home-*`。
- 在用调用点改为 Layer 1 + use-site alpha，基础规则保留原 light 值，dark 差值用显式 `.dark` 规则覆盖，不得抹平：`--home-prose-border` → `hsl(var(--foreground) / 0.1)`（`.dark` `0.12`）；`--home-prose-border-strong` → `hsl(var(--foreground) / 0.16)`（`.dark` `0.18`）；`--home-prose-blockquote-border` → `hsl(var(--primary) / 0.28)`（`.dark` `0.3`）；`--home-prose-blockquote-bg` → `hsl(var(--primary) / 0.06)`（`.dark` `0.08`）。
- 消费者保持既有 class：`.report-markdown-prose` 的 `h1` / `pre` / `th, td` / `th` / `hr` / `blockquote`；共享 `.prose` 表格的 `th, td` / `th`；`.chat-prose` 的 `pre` / `th, td` / `hr`。`.chat-prose blockquote` 原本就用 `--secondary-text` alpha，不在本族，保持不变。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 48 降到 44；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 12（这四个名字不在格式债清单中）。非空下界保持 160（已定义清单约 164）。
- 这些描边原本就包装 `--foreground` / `--primary`，因此 `data-theme-pack="slate"` 在收敛前后都会给 prose 换色（slate 覆盖 `--primary`、不覆盖 `--foreground`），**不是**首次换色。Layer 0 涨跌色与 `--home-price-up/down` 别名不变。其余 `--home-*` 族（cool / shadow / panel / surface）不在本切片。

### 2.14 Phase 2 域收敛：Home-title-accent（#1300）

- 唯一剩余的 `--home-title-accent` 定义（light + dark）已删除；未新增页面级或领域 token。`THEME_PAGE_SCOPED_PREFIXES` 仍永久禁止 `--home-*`。
- 历史 class `.home-title-accent` 保留。唯一 CSS 消费者改为内联 `color: hsl(var(--foreground));`。light 与 dark 原先就是同一 Layer 1 wrap，**不加** `.dark` 拆分。不要写成 `color: var(--foreground)`（`--foreground` 是 HSL 三元组），也不要把颜色挪到 Tailwind `text-foreground`（那会改 TSX）。
- `.home-title-accent` 与 `.label-uppercase` 都是单 class、同等 specificity。`.home-title-accent` 规则必须保持在前（`color: hsl(var(--foreground))`）；后面的 `.label-uppercase` 仍设置 `color: var(--text-secondary-text)`，因此赢得渲染后的 eyebrow 颜色。计算色保持 `--text-secondary-text`。不要挪规则或提高 specificity 来让 `--foreground` 赢——那会改变 playground 画色。`DashboardPanelHeader` 的 class 名与 `accentEyebrow` 默认 `false` 不变；flag 为 true 时仍同时挂两个 class。生产 Home / watchlist / report / history / task 调用点当前省略该 flag，因此生产页眉颜色不变；在用调用点是 playground `dashboard-panel-header`。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 44 降到 43；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 12（该名字不在格式债清单中）。非空下界保持 160（已定义清单约 163）。
- 该 token 原本就包装 `--foreground`，且当前 `slate` pack 不覆盖 `--foreground`，因此 **不是**首次 `data-theme-pack="slate"` 换色。Layer 0 涨跌色与 `--home-price-up/down` 别名不变。其余 `--home-*` 族（cool / shadow / panel / surface / unused wrappers）不在本切片。

### 2.15 Phase 2 无引用包装删除：Home loading-ring（#1300）

- 两个无引用定义已删除：`--home-loading-ring-track`、`--home-loading-ring-head`（`:root` 与 `.dark` 各一份）。未新增页面级或领域 token，也没有调用点需要迁移。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 43 降到 41；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 12（这两个名字不在格式债清单中）。非空下界保持严格 `> 160`（已定义清单约 161）。
- 这两个名字没有生产或测试消费者，因此亮色 / 暗色计算样式与 theme-pack 行为不变，**不是**视觉改版。Layer 0 涨跌色与 `--home-price-up/down` 别名不变。`--home-divider-border` 与其余在用 `--home-*` 族不在本切片。

### 2.16 Phase 2 无引用包装删除：Home divider（#1300）

- 无引用定义 `--home-divider-border` 已删除（`:root` 与 `.dark` 各一份）。未新增页面级或领域 token，也没有调用点需要迁移。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 41 降到 40；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 12（该名字不在格式债清单中）。非空下界由严格 `> 160` 调整为 `> 159`（已定义清单约 160）。
- 该名字没有生产或测试消费者，因此亮色 / 暗色计算样式与 theme-pack 行为不变，**不是**视觉改版。Layer 0 涨跌色与 `--home-price-up/down` 别名不变。其余在用 `--home-*` 族（panel / surface / hero / price）不在本切片。

### 2.17 Phase 2 无引用包装删除：Home state-icon（#1300）

- 无引用定义 `--home-state-icon-muted` 已删除（`:root` 与 `.dark` 各一份）。未新增页面级或领域 token，也没有调用点需要迁移。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 40 降到 39；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 12（该名字不在格式债清单中）。非空下界由严格 `> 159` 调整为 `> 158`（已定义清单约 159）。
- 该名字没有生产或测试消费者，因此亮色 / 暗色计算样式与 theme-pack 行为不变，**不是**视觉改版。Layer 0 涨跌色与 `--home-price-up/down` 别名不变。其余在用 `--home-*` 族（panel / surface / hero / price）不在本切片。

### 2.18 Phase 2 无引用包装删除：Home secondary-accent（#1300）

- 无引用定义 `--home-secondary-accent-text` 已删除（`:root` 与 `.dark` 各一份）。未新增页面级或领域 token，也没有调用点需要迁移。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 39 降到 38；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 12（该名字不在格式债清单中）。非空下界由严格 `> 158` 调整为 `> 157`（已定义清单约 158）。
- 该名字没有生产或测试消费者，因此亮色 / 暗色计算样式与 theme-pack 行为不变，**不是**视觉改版。Layer 0 涨跌色与 `--home-price-up/down` 别名不变。其余在用 `--home-*` 族（accent chip / panel / surface / hero / price）不在本切片。

### 2.19 Phase 2 无引用包装删除：Home accent-bg-hover（#1300）

- 无引用定义 `--home-accent-bg-hover` 已删除（`:root` 与 `.dark` 各一份）。未新增页面级或领域 token，也没有调用点需要迁移。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 38 降到 37；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 12（该名字不在格式债清单中）。非空下界由严格 `> 157` 调整为 `> 156`（已定义清单约 157）。
- 该名字没有生产或测试消费者，因此亮色 / 暗色计算样式与 theme-pack 行为不变，**不是**视觉改版。Layer 0 涨跌色与 `--home-price-up/down` 别名不变。其余在用 `--home-*` 族（accent chip / panel / surface / hero / price）以及未使用的 `--home-accent-border-hover` 不在本切片。

### 2.20 Phase 2 无引用包装删除：Home accent-border-hover（#1300）

- 无引用定义 `--home-accent-border-hover` 已删除（`:root` 与 `.dark` 各一份）。未新增页面级或领域 token，也没有调用点需要迁移。
- `THEME_PAGE_SCOPED_TOKEN_CEILING` 由 37 降到 36；`themeContractGuard.test.ts` 的 `TOKEN_FORMAT_DEBT` 保持 12（该名字不在格式债清单中）。非空下界由严格 `> 156` 调整为 `> 155`（已定义清单约 156）。
- 该名字没有生产或测试消费者，因此亮色 / 暗色计算样式与 theme-pack 行为不变，**不是**视觉改版。Layer 0 涨跌色与 `--home-price-up/down` 别名不变。其余在用 `--home-*` 族（accent chip / panel / surface / hero / price）以及未使用的 hero / history / panel / rail leftovers 不在本切片。

## 3. 字体阶（全部 Geist）

| 用途 | 字号 | 字重 |
|---|---|---|
| H1 / H2 / H3 | 32 / 28 / 24 | SemiBold，`letter-spacing: 0` |
| Title | 20 / 18 / 16 | SemiBold |
| Body | 18 / 16 / 14 / 12 | Medium 或 Regular |

审计基线的可执行 CSS 和部分公共组件仍有与 `letter-spacing: 0` 不一致的 tracking 声明。
本轮仅修正文档，不修改生产代码；后续须由获批视觉 slice 收敛并补视觉回归证据。

## 4. 组件规格

括号内历史节点仅用于追溯曾参考的外部组件模式，不构成实现或验收权威。

### 4.1 Button（外部参考 `1051:20280`）

- 形状：所有尺寸 `rounded-lg`，禁止 `rounded-full` 胶囊按钮。
- **primary（主 CTA）= 反色**：亮色主题黑底白字，暗色主题白底黑字，
  即 `bg-foreground text-background`，投影复用项目 semantic shadow，不复制外部 raw shadow。
- secondary/outline：透明或卡片底 + `--border` 描边 + `--foreground` 文字。
- ghost：无边框，hover 出浅底。
- danger 系列：使用 §2.2 的 Error semantic source，并由公共组件派生背景与边框。
- 焦点环：绿色 `ring-primary`（约 30% 透明度），替换旧 `ring-cyan/15`。

### 4.2 Card（`1051:20258`）

- 卡片底 = `--card`，1px `--border` 描边，轻投影，无辉光。

### 4.3 Modal / ConfirmDialog（`1051:20237`）、Badge（`1051:20212`）、Toggle（`1051:20222`）

- Badge 用 §2.2 的状态源色和公共组件既有透明度派生规则。
- Toggle 选中态用品牌绿。

### 4.4 Sidebar（`1047:27036`）

- 中性面 + 浅边框；当前 `--nav-active-bg`、`--nav-active-border` 和图标主要使用中性色/
  `--foreground`，indicator 与 badge 使用 `--primary`。改变该映射前先更新本指南并复核明暗
  对比度，不得假设整个 `--nav-active-*` 家族都由品牌色自动派生。

### 4.5 图表与情绪仪表

- recharts 曲线/面积图配色收敛为中性 + 品牌绿 + 状态色。
- ScoreGauge 保留 `data-sentiment` 语义（greed/fear 等），只换配色不改逻辑。

## 5. Do / Don't

| Do | Don't |
|---|---|
| 纯视觉任务只改已批准的样式面 | 在视觉任务中夹带 props、hooks、事件、i18n key 或路由改动 |
| 保留 CSS 变量名，只改取值 | 重命名/删除现有 token 变量 |
| 保留 tailwind 的 cyan/purple key（值改为新色） | 删除 key 导致未清扫处编译爆炸 |
| 用边框补层次（去辉光后） | 用新的发光/渐变替代旧辉光 |
| 生产颜色引用 `index.css` semantic token；只在 `:root/.dark` 的 semantic-token declaration 声明 raw source value；文档 hex 只作审阅换算 | 在普通 CSS declaration、组件、types、utils 或 renderer 写 raw hex，或把 `index.css` 当作整文件豁免 |
| 测试 fixture 的固定 hex 有具名白名单，并记录值和颜色/guard-sentinel 语义 | 把目录级 fixture 排除当成白名单，或用无说明的 fixture hex 绕过生产 token 规则 |
| 尺寸用 tailwind 阶梯 / `--radius` 体系 | 魔法数字（`h-[37px]` 之类） |
| token 缺口 → 停下提问 | 自己发明颜色值 |

## 6. 纯视觉刷新施工顺序（严格分层，禁止跳层）

本节只适用于已批准的纯视觉刷新，不是未来 IA / 交互 / route migration 的永久限制。

1. **WP1 基座**：独占 `src/index.css` + `tailwind.config.js`，一次改完所有 token
   （含页面级 `--home-*` / `--settings-*` / `--chat-*` / `--login-*`）与全局工具类
   （`.terminal-card`、`.glass-card`、`.dashboard-card`、`.input-surface` 等），接入 Geist 字体。
2. **WP2 公共组件**：`src/components/common/*.tsx` + `components/theme/ThemeToggle.tsx`。
3. **WP3 布局外壳**：`components/layout/Shell.tsx`、`components/layout/SidebarNav.tsx`。
4. **WP4 页面**：11 个页面 + 特性组件夹（此阶段**禁止**再碰 `index.css` /
   `tailwind.config.js`，发现 token 缺口回报，不要自己往里加）。
5. **WP5 清扫**：`grep -rn 'cyan\|purple\|glow\|primary-gradient' src/`
   清残留（白名单：涨跌色相关命名）。
6. **WP6 验证**：见 §7。

## 7. 验收清单（每阶段过一遍）

- [ ] `npm run lint && npm run build` 通过（build 输出到根 `static/`）
- [ ] 明暗两主题背景/文字/边框符合 §2.1
- [ ] 主按钮软圆角（`rounded-lg`）+ 黑白反色；焦点环为绿
- [ ] 涨跌红绿未被改动
- [ ] `grep -rn 'cyan\|purple\|glow' src/` 无非白名单残留
- [ ] `productionDesignGuard.test.ts` 的生产 `TSX` / CSS guard 通过；在 `UI01-P2-06` 扩展
      `.ts` / `.js` 覆盖前，另行人工审计 types、utils 与其它 `.ts/.js` 生产路径，且不声称规则已
      全量自动执行
- [ ] `git diff` 仅含样式面改动
- [ ] Playwright 逐页明/暗截图符合本指南和批准的产品语义；外部参考只记录采用/拒绝理由
- [ ] 抽查交互无回归：登录、主题切换、导航、Analyze 触发、历史列表、设置保存

## 8. 外部参考边界

- Coinstax/Figma 可用于评估中性基底、紧凑侧栏、数据密度、Dashboard、Portfolio、
  Empty State 和 light/dark 对称等模式。
- 不复制钱包、转账、兑换、交易等未批准 Web3 能力。
- 除 `docs/DESIGN.md` 已批准并映射的颜色变量值外，不从外部文件或截图复制/猜测 raw
  color、shadow、spacing、token 名或组件 API。
- 先复用 `components/common`、`components/layout` 和现有领域组件；确有语义缺口时，
  先提出规则与公共组件扩展，由对应 UI slice 负责。
- 保留中国市场红涨绿跌；外部品牌绿不能替代涨跌语义。

## 9. 仓库规则

- 未经负责人明确确认，不执行 `git commit` / `push` / `tag`。
- commit message 用英文，不加 `Co-Authored-By`。
- 截图只放 PR 描述/评论，不作为文件合入仓库。

## 10. 交互与表面角色（跨文档）

本文件只约束 **token / 视觉**（颜色、字体、圆角、禁 glow/glass、组件外观规格）。

**Page / Drawer / Modal / Wizard / 页内 rail 的允许与禁止清单、密度规则、工作区断点、
Loading/Empty/Error/Partial 结构与 CTA、以及文字按钮 vs IconButton 动作分类矩阵**
的规范性契约写在：

- [`docs/web-ui-foundation.md`](../../docs/web-ui-foundation.md) → **Surface Roles And Density Contract**

该章同时标注 **Immediate**（新代码即刻生效）与 **Progressive**（存量渐进迁移）符合度。
结构性 UI PR（hubs、Settings 单区渲染、抽屉瘦身等）以 foundation 该章为验收判据；
不得与本指南 §1 的禁 glow/glass 等视觉铁律冲突。
