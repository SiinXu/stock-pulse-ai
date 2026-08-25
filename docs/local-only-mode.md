# 本地专用模式（隐私 / 离线出站闸门）

本文说明在 `LOCAL_ONLY_MODE` 关闭与开启时，**机器上究竟有哪些数据可能出站**。
这是可核验的安全契约，不是营销表述。

相关文档：[出站 HTTP 安全策略（英文）](security-outbound-policy.md)、
[安全基线](security-baseline.md)、Issue #218。

英文版：[local-only-mode_EN.md](local-only-mode_EN.md)

## 摘要

| 模式 | 配置 | 非回环 HTTP(S) | 纯回环 HTTP(S) | 失败行为 |
| --- | --- | --- | --- | --- |
| 默认 | `LOCAL_ONLY_MODE=false`（或未设置） | 在[出站策略](security-outbound-policy.md)允许时可达（默认公网 HTTPS；私网/元数据需 allowlist） | 默认拒绝，除非 allowlist 或 Ollama 管理回环例外 | 拦截时抛出 `OutboundPolicyError` |
| 本地专用 | `LOCAL_ONLY_MODE=true` | **全部拒绝**（公网、局域网、allowlist 远程、元数据） | **允许**（`127.0.0.0/8`、`::1`、`localhost` / `*.localhost`） | 拦截时 reason 为 `local_only_mode_blocked`，错误信息点名 **LOCAL_ONLY_MODE** |

**失败即关闭（fail-closed）：** 被拦截的调用必须显式报错，**绝不能**静默放行到网络传输层。

## 什么会离开本机

### 本地专用 **关闭**（默认）

典型分析可能对以下目标发起出站 HTTP(S)：

- 行情数据源（如 Tushare、TickFlow、类 Yahoo 报价路径）
- 配置为生成 / Agent 后端的云端 LLM API
- 搜索 / 新闻 / 情报类 HTTP 源
- 通知 Webhook 与渠道 HTTP API
- 其他走 `safe_get` / `safe_post` / `guard_outbound_urls` 的路径

回环与其他非公网目标仍默认拒绝，除非写入 `OUTBOUND_HTTP_ALLOWLIST`（或窄范围的 Ollama 管理回环例外）。

### 本地专用 **开启**

| 面 | 是否出站 | 说明 |
| --- | --- | --- |
| 云端 LLM | **否** | 在共享出站策略处以 `local_only_mode_blocked` 拦截 |
| 走 `safe_*` / `guard_outbound_urls` 的远程行情 / 搜索 / 新闻 HTTP | **否** | 同上；这些数据源应按既有稳定性规则降级到缓存或显式错误 |
| 通知 HTTP Webhook | **否** | 渠道失败不得变成静默安全放行 |
| 本地 Ollama / 回环模型 HTTP | **是（仅回环）** | `127.0.0.0/8`、`::1`、`localhost` |
| `OUTBOUND_HTTP_ALLOWLIST` 远程主机 | **否** | 本地专用开启时，allowlist **不能**把边界扩到回环以外 |
| 桌面端 GitHub 更新检查 | **否（桌面壳跳过）** | 壳查询 `GET /api/v1/security/local-only`；模式开启或状态未知时不联系 GitHub |
| 非 HTTP 数据源套接字（如 pytdx / baostock TCP） | **不在本闸门范围** | 按设计不在 HTTP 策略内 |
| 经 `plugin_safe_*` 的插件 HTTP | 非回环为 **否** | 插件受支持的 HTTP 走同一出站策略，拦截 reason 为 `local_only_mode_blocked` |
| 插件直接使用 `requests` / `socket` | **无法真正隔离** | 插件在进程内运行。捆绑/示例插件的直接 HTTP 客户端由测试标记；恶意插件仍可绕过 wrapper |
| SMTP / 数据库 / 其他非 HTTP | **不在本闸门范围** | 与出站 HTTP 策略文档相同限制 |

本地专用是 **出站闸门**，并不单独保证「离线分析质量足够好」。可接受的离线分析仍依赖缓存覆盖与本地模型（#178、#203）。本模式让策略管辖的远程 HTTP **可核验且 fail-closed**。

## 威胁模型

| 威胁 | 缓解 |
| --- | --- |
| 用户以为开了隐私模式，云端 LLM 仍在跑 | 单一配置键 `LOCAL_ONLY_MODE`，在 `src/security/outbound_policy.py` 对所有 `safe_*` / `validate_outbound_url` / DNS 守卫路径强制生效 |
| 插件在本地专用开启时调用 `requests.get` | 捆绑/示例插件必须使用 `plugin_safe_*`；测试会标记直接 HTTP 客户端。这 **不是** 进程沙箱——进程内 Python 仍可 `import socket` |
| 静默降级（拦截却返回空成功） | 建连前抛错；reason 码稳定且点名模式 |
| 用 allowlist 在「本地专用」下重新打开云端 | 本地专用对非回环忽略 allowlist 扩权 |
| `localhost` DNS 重绑定到公网 IP | 本地专用下 DNS 答案必须是回环，否则拦截 |
| 活动面板通过主机名/URL 泄露密钥 | 活动记录只保留目标**类别**、scheme、host 类型、reason、correlation id |

## 如何启用

```dotenv
LOCAL_ONLY_MODE=true
```

1. 优先使用本地生成后端（回环 Ollama，或无需云端 HTTP 的本地 CLI）。
2. 为需要离线分析的标的预热行情缓存。
3. 重启长驻进程（`--serve`、Docker、桌面后端），确保 worker 重新加载环境变量。
4. 打开 **设置 → 认证与安全 → 出站活动**，确认模式徽标为开启。
5. 触发依赖远程的操作，确认非回环类别为 `blocked` / `local_only_mode_blocked`，仅 `loopback` 可为 `allowed`。

## 核验面

| 面 | 路径 |
| --- | --- |
| 配置 / 设置开关 | `LOCAL_ONLY_MODE`（系统 / 认证与安全） |
| 状态 API | `GET /api/v1/security/local-only` |
| 活动 API | `GET /api/v1/security/outbound-activity` |
| Web 面板 | 设置 → 认证与安全 → 出站活动 |
| 自动化证明 | `tests/security/test_local_only_mode.py`（分析路径夹具：零非回环允许） |
| 插件 HTTP 契约 | `tests/plugins/test_plugin_outbound_http.py`（受支持 helper 被拦截；直接客户端守卫；分析隔离） |

## 限制

- 活动记录为进程内环形缓冲（默认容量 100），重启清空。
- 绕过 `src.security.outbound_policy` 的 HTTP 调用不在本合同内；新增调用点必须使用共享 helper。当前包括非 HTTP 数据源套接字。桌面 GitHub 更新检查在本模式开启时由桌面壳跳过。
- 插件是进程内 Python。`plugin_safe_*` 是受支持的 API，在本地专用下 fail-closed。它不是沙箱，也无法阻止插件 `import socket` 或原始 HTTP 客户端。
- 本模式不会自动安装模型或历史数据。

## 回滚

将 `LOCAL_ONLY_MODE=false`（或删除）并重启进程。回滚代码时还原相关变更集即可，无数据库迁移。
