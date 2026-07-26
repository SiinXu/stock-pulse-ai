# 配图占位清单（待拍摄）

本文件是 UI 操作手册 **应配截图的完整清单**。章节正文使用统一占位块；真正的 PNG/WebP 按 [README.md](README.md) 命名落入本目录后，再把占位换成 `![alt](assets/….png)`。

## 占位块格式（写入章节时）

```markdown
> 🖼️ **配图占位** · `assets/<module>-<scene>[-zh|-en].png`  
> **应配内容**：……（画面里必须出现什么）  
> **拍摄要点**：……（裁剪、语言、脱敏）  
> **状态**：待补图
```

规则：

1. **未拍到图之前不要用** `![](assets/xxx.png)`，避免坏链。  
2. 占位必须写清 **文件名 stem + 应配内容 + 拍摄要点**。  
3. 界面文案以当前产品为准；占位里的按钮名用中文产品常用说法，英文章用英文标签。  
4. 禁止：API Key、真实资金规模、可识别账号、生产 Cookie。

---

## P0（首发必拍）

| 文件名 stem | 章节 | 应配内容 | 拍摄要点 |
| --- | --- | --- | --- |
| `shell-primary-nav` | 01 | 宽屏：左侧五级导航（首页/研究/组合/Agent/设置）+ 顶栏通知铃与语言/主题入口 | 中文 UI；研究可展开显示子菜单；无敏感信息 |
| `shell-command-palette` | 01 | 命令面板打开态（`Cmd/Ctrl+K`），可见搜索框与至少一条跳转结果 | 可输入「分析」后的结果列表；遮罩半透明即可 |
| `home-config-gap` | 02 | 首页「基础配置未完成」类横幅 + **开始引导配置** | 故意空模型或空自选以复现；裁剪横幅区 |
| `home-core-blocks` | 02 | 今日焦点、待办、信号摘要（可为空状态） | 标出三块标题；可含折叠区未展开 |
| `home-scheduled-tasks` | 02 | 「今日定时任务」只读列表（有 1 条任务或空状态文案） | 能看清只读说明；状态标签可读 |
| `analysis-workbench-three-segments` | 03 | 工作台三分段控件：发起 / 运行中任务 / 历史 | 高亮当前「发起」；URL 可为 `/research/analysis` |
| `analysis-workbench-launch-form` | 03 | 发起区：代码输入、策略/Skill、brief 或新手相关、开始分析 | 预填 `600519`；无真实 Key |
| `analysis-workbench-task-running` | 03 | 任务列表：排队或分析中状态 | 可演示数据；勿含密钥 |
| `analysis-workbench-history` | 03 | 历史列表 + 右侧摘要（或空历史） | 能看出可选中记录 |
| `report-header-action-phase` | 08 | 报告页头：操作建议/action、阶段或数据质量相关信息 | 脱敏标的；裁剪页头 |
| `report-reading-order` | 08 | 报告正文前半：结论与风险区域可见 | 标注「先看这里」类阅读起点（可用红框，发布前可去框） |

## P1（第二批）

| 文件名 stem | 章节 | 应配内容 | 拍摄要点 |
| --- | --- | --- | --- |
| `market-review-trigger` | 04 | 大盘复盘页：触发复盘按钮 + 历史列表区 | 干净 URL，无 `action=run` 误触提示可另截 |
| `agent-chat-empty` | 05 | 问股页：会话区 + 输入框 +（若有）当前标的上下文 | 侧栏名 Agent / 页内问股以界面为准 |
| `signals-tabs-empty` | 06 | 信号中心四 Tab + 信号流空状态 | 侧栏无「信号」时可只截主区 |
| `signals-rules-create` | 06 | 规则 Tab：新建规则表单或 `createRule=1` 打开态 | 价格条件示例，未保存草稿即可 |
| `signals-delivery-history` | 06 | 推送历史：触发/通知侧视图之一 | 可无真实推送记录 |
| `portfolio-overview` | 07 | 持仓页：账户选择 + 持仓表头 + 空或演示持仓 | 演示数量；勿真实大额 |
| `portfolio-import-preview` | 07 | CSV 导入预览/dry-run（若有） | 虚构流水 |
| `settings-save-control` | 10 | 设置页：保存配置按钮位置 + 未保存提示（若可复现） | 任意分段；高亮保存 |
| `settings-model-connections` | 10 | AI 与模型 → 模型接入列表/添加入口 | **遮罩 Key** |
| `settings-notification-cards` | 10 | 通知渠道卡片列表（已配置/未配置角标） | 无真实 Webhook |
| `settings-scheduling` | 10 | 系统与安全 → 调度（runtime）时间与开关 | 可演示时间 |
| `discover-hotspots` | 12 | 发现页：热点或策略入口 | 实验能力开启时 |
| `stock-details-quote-chart` | 13 | 个股页：报价卡 + K 线 + 分析/自选按钮 | `/stocks/600519` 或 `AAPL` |

## P2（可选增强）

| 文件名 stem | 章节 | 应配内容 |
| --- | --- | --- |
| `shell-narrow-nav` | 01 | 窄屏导航收起为菜单图标后的展开态 |
| `home-guided-setup-jump` | 02 | 从首页黄条点进设置就绪检查的落地页 |
| `analysis-run-flow` | 03 | 运行流抽屉/对话框某一阶段列表 |
| `backtest-results` | 09 | 回测结果区：样本数 + 主要指标 |
| `settings-readiness` | 10 | 概览/就绪检查项列表 |
| `workflows-chain` | 11 | 可用示意图（非截图）：五条主链路，亦可用 mermaid 代替 |

## 语言变体

| 后缀 | 用途 |
| --- | --- |
| `-zh` | 简体中文 UI 截图（默认主手册） |
| `-en` | English UI |
| 无后缀 | 语言中立 chrome，或双语并排时 |

中文章默认引用 `-zh` 或中性 stem；英文章引用 `-en` 或中性 stem。

## 状态

| 批次 | 二进制 | 章节嵌入 |
| --- | --- | --- |
| P0 | 待拍摄 | 正文已占位 |
| P1 | 待拍摄 | 正文已占位 |
| P2 | 可选 | 部分占位 |

拍摄完成后：更新本表状态 → 替换章节占位为真实 `![](...)` → 在 PR 中附 stem 列表。
