# StockPulse Web 设计准则

> `src/index.css` 和公共组件是当前可执行视觉事实；本文档是 StockPulse **已采纳视觉规则**的
> 权威。当前 [UI 信息架构审计](../../docs/stockpulse-ui-information-architecture.md) 仅为
> `Ready for HITL review, not approved` 的候选材料。只有维护者明确批准后，它才能成为导航、
> 页面归属、URL、状态与交互契约；批准前不得据此启动 UI-02～UI-07。Coinstax/Figma 仅是
> 外部模式参考，不是项目需求、token、组件 API、页面 IA 或像素级验收来源。

## 0. 铁律

1. **任务范围先行**：纯视觉任务禁止修改组件 props / TS 接口与类型、hooks、事件处理、
   状态管理、API、数据流、i18n key 和路由，只允许改已批准的样式面。IA、交互或 URL
   任务必须在独立 slice 中获得明确批准；UI-01 获批后才遵循其冻结的 IA 契约，不能把候选
   结论夹带在视觉 diff 中。
2. **红涨绿跌不可动**：`--home-price-up` 是红、`--home-price-down` 是绿，
   这是中国市场约定，与「绿色品牌强调色」是两套独立语义，严禁合并、串色或改值。
3. **遇到问题必须求助，不许猜**：项目 token 未覆盖、外部参考与产品语义冲突、
   lint/build 报错涉及任务范围外逻辑、拿不准是否需要扩展公共组件——一律停下提问。
   提问时给出：页面/文件、现状、StockPulse 依据、外部参考（如有）和倾向方案。
4. **禁止硬编码**：
   - 颜色一律走 CSS 变量 / tailwind token；**hex 色值只允许出现在
     `src/index.css` 的 `:root` / `.dark` 变量定义里（WP1 唯一入口）**，
     禁止在组件里写 `bg-[#151514]`、`text-[#41B83D]` 这类任意值类名或内联 hex。
   - 字号/圆角/间距优先用现有 tailwind 阶梯与 `--radius` 体系，不写魔法数字。
   - 不写死密钥、账号、路径、模型名、端口或环境差异逻辑（仓库硬规则）。

## 1. 设计基调

- **中性极简**：米白/近黑双主题，大量留白，极浅边框分层，轻投影。
- **禁止**：cyan/purple 辉光（glow）、pulse-glow 动画、彩色渐变发光、玻璃拟态强模糊。
- **字体**：Geist。标题通过字号、SemiBold 字重和层级建立差异，`letter-spacing: 0`。
- **形状**：按钮一律软圆角 `rounded-lg`（`var(--radius)`），禁止胶囊形 `rounded-full`；装饰性圆点用 `--radius-dot`；卡片保留大圆角（`--radius` 体系不变）。

## 2. 颜色 Token（当前项目定义）

下表是审计基线 `ed729c1b` 中 `src/index.css` semantic token 的文档快照。HSL 源值是精确
代码事实，hex 仅是便于审阅的换算值。代码取值与本表不一致时，应先核对当前实现和变更
历史，再更新本表；不得用外部文件变量静默覆盖项目 token。

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

- `--home-price-up` = 红（涨）、`--home-price-down` = 绿（跌）。中国市场约定。
- 审计快照：`--home-price-up` light `0 88% 62%` (`#F34949`) / dark
  `0 88% 64%` (`#F45252`)；`--home-price-down` light `149 100% 42%`
  (`#00D668`) / dark `149 100% 44%` (`#00E06C`)。
- 与品牌绿是两套独立语义：**禁止合并变量、禁止互相引用、禁止改值**。

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
| 颜色走 token/CSS 变量，hex 只进 `index.css` 变量定义 | 组件里写 `bg-[#xxx]` 任意值类名或内联 hex |
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
- [ ] `git diff` 仅含样式面改动
- [ ] Playwright 逐页明/暗截图符合本指南和批准的产品语义；外部参考只记录采用/拒绝理由
- [ ] 抽查交互无回归：登录、主题切换、导航、Analyze 触发、历史列表、设置保存

## 8. 外部参考边界

- Coinstax/Figma 可用于评估中性基底、紧凑侧栏、数据密度、Dashboard、Portfolio、
  Empty State 和 light/dark 对称等模式。
- 不复制钱包、转账、兑换、交易等未批准 Web3 能力。
- 不从外部文件或截图复制/猜测 raw color、shadow、spacing、token 名或组件 API。
- 先复用 `components/common`、`components/layout` 和现有领域组件；确有语义缺口时，
  先提出规则与公共组件扩展，由对应 UI slice 负责。
- 保留中国市场红涨绿跌；外部品牌绿不能替代涨跌语义。

## 9. 仓库规则

- 未经负责人明确确认，不执行 `git commit` / `push` / `tag`。
- commit message 用英文，不加 `Co-Authored-By`。
- 截图只放 PR 描述/评论，不作为文件合入仓库。
