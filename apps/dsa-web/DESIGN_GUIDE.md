# DSA Web 设计准则（Figma 对齐版）

> 本文档是 UI 重构期间的样式唯一真源。与旧代码风格冲突时，以本文档为准；
> 本文档未覆盖的细节，用 Figma MCP 查 `Design` 页（node `0:1`，左列亮/右列暗）
> 和 `Style Guide & Components` 页（node `117:279`），仍不确定就向负责人提问。

## 0. 铁律

1. **零逻辑改动**：禁止修改组件 props / TS 接口与类型、导入导出结构、hooks
   （useTheme / useUiLanguage / useAuth 等）、事件处理、状态管理、API 调用、
   数据流、i18n key、路由。只允许改：`className`、`style`、CSS 变量取值、
   变体样式对象（如 `BUTTON_VARIANT_STYLES`）、`tailwind.config.js`、字体接入。
2. **红涨绿跌不可动**：`--home-price-up` 是红、`--home-price-down` 是绿，
   这是中国市场约定，与「绿色品牌强调色」是两套独立语义，严禁合并、串色或改值。
3. **遇到问题必须求助，不许猜**：Figma 找不到对应设计、设计与零逻辑约束冲突、
   token 表未覆盖、lint/build 报错涉及逻辑层、拿不准是否算逻辑改动——一律停下提问。
   提问时给出：页面/文件、现状、Figma 依据、倾向方案。
4. **禁止硬编码**：
   - 颜色一律走 CSS 变量 / tailwind token；**hex 色值只允许出现在
     `src/index.css` 的 `:root` / `.dark` 变量定义里（WP1 唯一入口）**，
     禁止在组件里写 `bg-[#151514]`、`text-[#41B83D]` 这类任意值类名或内联 hex。
   - 字号/圆角/间距优先用现有 tailwind 阶梯与 `--radius` 体系，不写魔法数字。
   - 不写死密钥、账号、路径、模型名、端口或环境差异逻辑（仓库硬规则）。

## 1. 设计基调

- **中性极简**：米白/近黑双主题，大量留白，极浅边框分层，轻投影。
- **禁止**：cyan/purple 辉光（glow）、pulse-glow 动画、彩色渐变发光、玻璃拟态强模糊。
- **字体**：Geist。标题 SemiBold + 负字距（letter-spacing 约 -0.02em）。
- **形状**：按钮一律软圆角 `rounded-lg`（`var(--radius)`），禁止胶囊形 `rounded-full`；装饰性圆点用 `--radius-dot`；卡片保留大圆角（`--radius` 体系不变）。

## 2. 颜色 Token（Figma get_variable_defs 精确值）

### 2.1 基础色

| 语义 | Light | Dark | 映射到代码变量 |
|---|---|---|---|
| 背景 Base | `#F7F8F7` | `#151514` | `--background` |
| 主文本 Text | `#151514` | `#FFFFFF` | `--foreground` |
| 次级文本/图标 | `#878980` | `#9B9D95` | `--secondary-text` / `--muted-text` |
| 边框 Border | `#EAEBE8` | `#343531` | `--border` |
| 浅边框 Light Border | `#F0F0EF` | `#1F201D` | 分隔线/内层描边 |

### 2.2 状态色（文本 / 底 / 边 三件套）

| 状态 | Light 文本/底/边 | Dark 文本/底/边 |
|---|---|---|
| Success | `#41B83D` / `#F0FAF0` / `#DDF9DC` | `#96DB94` / `#1A3A18` / `#275624` |
| Error   | `#E9415D` / `#FEECEF` / `#FDD8DE` | `#F8778D` / `#3D161D` / `#74202E` |
| Warning | `#E9C40C` / `#FEFBEC` / `#FDF7D8` | `#F8E277` / `#4E4204` / `#746206` |

### 2.3 品牌强调色 = 绿

- `--primary` = Success 绿（light `#41B83D` / dark `#96DB94`）。
- 用途：导航激活态、链接、焦点环（focus ring）、选中态。
- **主 CTA 按钮不用绿**，用黑白反色（见 §4.1）。

### 2.4 ⚠️ 涨跌色（不可触碰）

- `--home-price-up` = 红（涨）、`--home-price-down` = 绿（跌）。中国市场约定。
- 与品牌绿是两套独立语义：**禁止合并变量、禁止互相引用、禁止改值**。

## 3. 字体阶（全部 Geist）

| 用途 | 字号 | 字重 |
|---|---|---|
| H1 / H2 / H3 | 32 / 28 / 24 | SemiBold，负字距 |
| Title | 20 / 18 / 16 | SemiBold |
| Body | 18 / 16 / 14 / 12 | Medium 或 Regular |

## 4. 组件规格（Figma 节点索引）

### 4.1 Button（Figma `1051:20280`）

- 形状：所有尺寸 `rounded-lg`，禁止 `rounded-full` 胶囊按钮。
- **primary（主 CTA）= 反色**：亮色主题黑底白字（`#151514` 底），暗色主题白底黑字，
  即 `bg-foreground text-background`，带 Figma 的 inset + drop 双投影。
- secondary/outline：透明或卡片底 + `--border` 描边 + `--foreground` 文字。
- ghost：无边框，hover 出浅底。
- danger 系列：用 §2.2 Error 三件套。
- 焦点环：绿色 `ring-primary`（约 30% 透明度），替换旧 `ring-cyan/15`。

### 4.2 Card（`1051:20258`）

- 卡片底 = `--card`，1px `--border` 描边，轻投影，无辉光。

### 4.3 Modal / ConfirmDialog（`1051:20237`）、Badge（`1051:20212`）、Toggle（`1051:20222`）

- Badge 用状态色三件套（文本/底/边）。
- Toggle 选中态用品牌绿。

### 4.4 Sidebar（`1047:27036`）

- 中性面 + 浅边框；激活项：绿色文字/指示 + 浅绿底
  （由 `--nav-active-*` 派生自 `--primary` 自动生效，需复核明暗对比度）。

### 4.5 图表与情绪仪表

- recharts 曲线/面积图配色收敛为中性 + 品牌绿 + 状态色。
- ScoreGauge 保留 `data-sentiment` 语义（greed/fear 等），只换配色不改逻辑。

## 5. Do / Don't

| Do | Don't |
|---|---|
| 只改 className、CSS 变量值、变体样式对象 | 改 props、hooks、事件、i18n key、路由 |
| 保留 CSS 变量名，只改取值 | 重命名/删除现有 token 变量 |
| 保留 tailwind 的 cyan/purple key（值改为新色） | 删除 key 导致未清扫处编译爆炸 |
| 用边框补层次（去辉光后） | 用新的发光/渐变替代旧辉光 |
| 颜色走 token/CSS 变量，hex 只进 `index.css` 变量定义 | 组件里写 `bg-[#xxx]` 任意值类名或内联 hex |
| 尺寸用 tailwind 阶梯 / `--radius` 体系 | 魔法数字（`h-[37px]` 之类） |
| token 缺口 → 停下提问 | 自己发明颜色值 |

## 6. 施工顺序（严格分层，禁止跳层）

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
- [ ] Playwright 逐页明/暗截图（存 `.playwright-mcp/`）与 Figma `0:1` 对应画面一致
- [ ] 抽查交互无回归：登录、主题切换、导航、Analyze 触发、历史列表、设置保存

## 8. 仓库规则

- 未经负责人明确确认，不执行 `git commit` / `push` / `tag`。
- commit message 用英文，不加 `Co-Authored-By`。
- 截图只放 PR 描述/评论，不作为文件合入仓库。
