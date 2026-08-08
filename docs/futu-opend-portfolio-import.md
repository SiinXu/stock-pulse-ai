# Futu OpenD 组合持仓导入

StockPulse 可通过本地 [Futu OpenD](https://openapi.futunn.com/futu-api-doc/) 网关读取**真实多头正股持仓**，用于两类能力：

1. **分析范围** — `python main.py --portfolio futu` 用符合条件的实盘正股代码覆盖 `STOCK_LIST` / `--stocks`（既有能力）。
2. **组合账本导入** — `POST /api/v1/portfolio/imports/futu` 将持仓映射为共享组合交易导入路径中的合成买入（成本价）。

本文说明 OpenD 安装配置、导入 API、降级语义与网络策略依据。

## 前置条件

1. 在可信机器上安装并登录 **Futu OpenD**。
2. 安装 StockPulse 依赖，确保固定版本 `futu-api` 可用（见 `requirements.txt`）。
3. OpenD 已开启 API 监听（默认 `127.0.0.1:11111`）。
4. 准备好接收导入成交的 StockPulse 组合账户。

## 配置项

设置页 **数据源 → Futu OpenD** 中可见以下四项（已从 Web 隐藏列表移除）：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `FUTU_OPEND_HOST` | `127.0.0.1` | OpenD IPv4 主机 |
| `FUTU_OPEND_PORT` | `11111` | OpenD TCP 端口 |
| `FUTU_ACC_ID` | 空 | 可选单一真实账户过滤 |
| `FUTU_SECURITY_FIRM` | `NONE` | SecurityFirm 枚举；`NONE` 为 SDK 自动识别 |

同步见 `.env.example` 与完整指南环境变量表。

### 导入范围

- 账户：`ACTIVE` + `REAL` + 角色 `NORMAL` 或 `MASTER`
- 持仓：非零 `LONG`，且证券类型明确为 `STOCK`
- 市场：沪深 / 港股 / 美股（项目代码格式）
- 价格：优先正数 `cost_price`，否则正数 `nominal_price`
- 跳过：空头、零仓、ETF/期权等非正股、B 股、暂不支持市场

集成仅调用账户列表、持仓列表与证券基础信息查询，不解锁交易，也不下单、改单或撤单。

### 幂等

每条持仓映射为买入成交，稳定 `trade_uid`：

```text
futu:{futu_acc_id}:{symbol}:{quantity:.8f}:{price:.8f}
```

相同快照再次导入会增加 `duplicate_count`，不会重复加仓。数量或成本变化会生成新的成交行（快照导入，非整仓对账替换）。

## API

预览（不写库）：

```http
POST /api/v1/portfolio/imports/futu/preview?as_of=2026-08-06
```

提交：

```http
POST /api/v1/portfolio/imports/futu
Content-Type: application/json
Idempotency-Key: optional-client-key

{
  "account_id": 1,
  "dry_run": false,
  "as_of": "2026-08-06",
  "operation_id": "optional-client-key"
}
```

响应字段与 CSV 导入提交一致（`inserted_count`、`duplicate_count`、`failed_count`、`errors`）。

OpenD 不可达或配置无效时返回 **503**，`error=futu_opend_unavailable`，并给出可操作错误信息；该请求不会写入任何部分成交。

> **Web UI：** 组合页导入按钮为后续工作。设置页已暴露 OpenD 连接字段；当前可通过 API / 自动化调用导入。

## 降级与安全

| 失败场景 | 行为 |
| --- | --- |
| OpenD 未启动 / 主机端口错误 | 导入失败并返回明确 503；其他分析与数据源不受影响 |
| 未安装 `futu-api` | 明确安装提示；不会静默空导入 |
| 无符合条件持仓 | 成功返回 0 条记录（非错误） |
| 个别持仓无有效成本 | 跳过并记日志，其余行仍可导入 |
| 证券类型不可信 | 整次导入失败，避免写入未知品种 |

`--portfolio futu` 在 OpenD 失败时仍保持既有 fail-closed 分析范围语义。

## 网络策略：为何不走 HTTP 允许列表

出站 HTTP 策略（见 `docs/security-outbound-policy.md`）对 **HTTP(S)** 私网目标默认拒绝。Futu OpenD 是 **本地 TCP 网关**，由 Futu SDK 直连，语义接近 Pytdx 行情服务器：

- 运维主动配置 `FUTU_OPEND_HOST` / `FUTU_OPEND_PORT`（默认回环地址）。
- 流量不经过共享 HTTP 客户端，也不使用 `OUTBOUND_HTTP_ALLOWLIST`。
- 优先使用回环地址；局域网主机属于显式信任决策（与 Pytdx 指向私网 IP 同类）。
- Docker 中需配置容器网络可达主机；`127.0.0.1` 指向容器自身。

请勿将 OpenD 暴露到不受信网络。

## Docker 提示

```dotenv
FUTU_OPEND_HOST=host.docker.internal
FUTU_OPEND_PORT=11111
```

具体网络与端口映射取决于运行环境。启用定时 futu 分析前，请先在容器内验证连通性。

## 相关文档

- 完整指南：环境变量表与 CLI `--portfolio futu`
- 安全：[出站 HTTP 安全策略](security-outbound-policy.md)（仅 HTTP；OpenD 按设计不在其管辖范围）
- 组合 CSV 导入仍使用 `/api/v1/portfolio/imports/csv/*`
