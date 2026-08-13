# 桌面深链策略（stockpulse://）

本页是 #884 的深链策略收口：**已实现**，不是“暂不支持”。English: [desktop-deep-link-policy_EN.md](desktop-deep-link-policy_EN.md)。打包与注册细节见 [桌面端打包说明](desktop-package.md)。

## 规范形式

```text
stockpulse://app/<应用内路径>?<查询参数>
```

示例：

```text
stockpulse://app/portfolio?account=7
stockpulse://app/stocks/AAPL?period=weekly
```

- 协议：`stockpulse`
- Authority：固定 `app`（禁止用户名、密码、端口、非 `app` host）
- Fragment：禁止
- 最大长度：4096
- 控制字符 / 未编码空格：拒绝

## 路径白名单

仅接受 Web 稳定产品入口：

- `/`
- `/chat`
- `/portfolio`
- `/decision-signals`
- `/alerts`
- `/backtest`
- `/screening`
- `/settings`
- `/usage`
- `/stocks/<stockCode>`（单个 ASCII 路径段，`[A-Za-z0-9.]{1,16}`）

查询参数由 Web 路由继续规范化；桌面壳只保证仍落在私有本地 origin，并覆盖 `desktop_version` / `cache_bust`。

## 明确拒绝（含 UX）

以下一律拒绝，**不改变当前页面**，日志不记录原始 URL / 查询串；应用已运行时弹出不含原始链接的说明对话框：

- 非 `stockpulse` 协议、非 `app` authority
- 白名单外路径（例如 `/login`）
- host 走私（`stockpulse://evil.example/settings`）
- 编码 / 归一化走私、用户名密码、端口、fragment

不支持把任意 https Web URL 当作深链转发。

## 生命周期

- 冷启动：Windows/Linux 从 argv 提取；macOS 走 `open-url`
- 后端未就绪：排队到私有 Web origin 就绪后再导航
- 已运行：second-instance / `open-url` 聚焦主窗口后走同一解析入口

## 验证命令

```bash
open "stockpulse://app/portfolio?account=7"
open "stockpulse://app/login"   # 应拒绝且页面不变
```
