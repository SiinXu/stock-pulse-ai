# Futu OpenD Portfolio Import

StockPulse can read **live long stock positions** from a local [Futu OpenD](https://openapi.futunn.com/futu-api-doc/) gateway for two purposes:

1. **Analysis scope** — `python main.py --portfolio futu` overrides `STOCK_LIST` / `--stocks` with eligible live stock codes (existing behavior).
2. **Portfolio ledger import** — `POST /api/v1/portfolio/imports/futu` maps those positions into the shared portfolio trade-import path as synthetic buys at cost price.

This page covers OpenD setup, configuration, the import API, degradation rules, and network policy reasoning.

## Prerequisites

1. Install and log in to **Futu OpenD** on a machine you trust (desktop or LAN host).
2. Install StockPulse dependencies so the pinned `futu-api` package is present (`requirements.txt`).
3. Ensure OpenD listens for API connections (default `127.0.0.1:11111`).
4. Create or choose a StockPulse portfolio **account** that should receive imported trades.

## Configuration

Settings appear under **Data Source → Futu OpenD** (the four keys are no longer hidden from the Web UI):

| Key | Default | Purpose |
| --- | --- | --- |
| `FUTU_OPEND_HOST` | `127.0.0.1` | IPv4 OpenD host |
| `FUTU_OPEND_PORT` | `11111` | OpenD TCP port |
| `FUTU_ACC_ID` | empty | Optional single live account filter |
| `FUTU_SECURITY_FIRM` | `NONE` | SecurityFirm enum; `NONE` = SDK auto-detect |

Also documented in `.env.example` and the environment variable tables in the full guides.

### What is imported

- Accounts: `ACTIVE` + `REAL` + role `NORMAL` or `MASTER`
- Positions: non-zero `LONG` quantities definitively classified as `STOCK`
- Markets: SH / SZ / HK / US (project code format)
- Price: `cost_price` when positive; otherwise `nominal_price` when positive
- Skipped: shorts, zero qty, ETFs/options/other non-stocks, B-shares, unsupported markets

The integration only calls account-list, position-list, and security basic-info queries. It never unlocks trading or places, modifies, or cancels orders.

### Idempotency

Each position becomes a **buy** trade with a stable `trade_uid`:

```text
futu:{futu_acc_id}:{symbol}:{quantity:.8f}:{price:.8f}
```

Re-importing the same snapshot increments `duplicate_count` and does not double inventory. Changed quantity or cost creates a new trade row (snapshot import, not full reconcile/replace).

## API

Preview (no writes):

```http
POST /api/v1/portfolio/imports/futu/preview?as_of=2026-08-06
```

Commit:

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

Response shape matches CSV import commit (`inserted_count`, `duplicate_count`, `failed_count`, `errors`).

When OpenD is unreachable or configuration is invalid, the API returns **503** with `error=futu_opend_unavailable` and an actionable message. No partial trades are written for that request.

> **Web UI:** Portfolio page controls for this endpoint are intentionally a follow-up. Settings expose OpenD connection fields; import can be called via API / automation.

## Degradation and safety

| Failure | Behavior |
| --- | --- |
| OpenD down / wrong host-port | Import fails with clear 503; other analysis and providers continue |
| Missing `futu-api` package | Clear install guidance; no silent empty import |
| Empty eligible positions | Success with zero records (not an error) |
| Partial bad rows (no cost) | Row skipped with log warning; other rows still import |
| Untrusted security-type answers | Fail the import rather than write partial unknown instruments |

`--portfolio futu` keeps its existing fail-closed analysis-scope contract when OpenD fails.

## Network policy: why OpenD is not on the HTTP allowlist

StockPulse outbound HTTP policy (`docs/security-outbound-policy.md`) fail-closes private destinations for **HTTP(S)** targets. Futu OpenD is a **local TCP gateway** opened by the Futu SDK, similar in spirit to Pytdx quote servers:

- The operator deliberately configures `FUTU_OPEND_HOST` / `FUTU_OPEND_PORT` (default loopback).
- Traffic never goes through the shared HTTP client or `OUTBOUND_HTTP_ALLOWLIST`.
- Prefer loopback. LAN hosts are an explicit trust decision (same class of risk as pointing Pytdx at a private IP).
- In Docker, set a host that is reachable from the container network; `127.0.0.1` is the container itself.

Do not expose OpenD to untrusted networks.

## Docker notes

```dotenv
FUTU_OPEND_HOST=host.docker.internal
FUTU_OPEND_PORT=11111
```

Host networking / published OpenD ports depend on your runtime. Verify connectivity from inside the container before enabling scheduled portfolio futu analysis.

## Related docs

- Full guide: environment variable tables and CLI `--portfolio futu`
- Security: [Outbound HTTP Security Policy](security-outbound-policy_EN.md) (HTTP only; OpenD is out of scope by design)
- Portfolio CSV import remains at `/api/v1/portfolio/imports/csv/*`
