# Local Only Mode (Privacy / Offline Egress Gate)

This page states **exactly** what may leave the machine when `LOCAL_ONLY_MODE` is
off versus on. It is a security contract, not a marketing claim.

Related: [Outbound HTTP security policy](security-outbound-policy.md),
[Security baseline](security-baseline.md), issue #218.

## Summary

| Mode | Config | Non-loopback HTTP(S) | Pure loopback HTTP(S) | Fail behavior |
| --- | --- | --- | --- | --- |
| Default | `LOCAL_ONLY_MODE=false` (or unset) | Allowed when the [outbound policy](security-outbound-policy.md) accepts the target (public HTTPS by default; private/metadata denied unless allowlisted) | Denied unless allowlisted or the narrow admin-loopback Ollama path | Blocked calls raise `OutboundPolicyError` |
| Local Only | `LOCAL_ONLY_MODE=true` | **Denied** (public, private LAN, allowlisted remote, metadata) | **Allowed** (`127.0.0.0/8`, `::1`, `localhost` / `*.localhost`) | Blocked calls raise `OutboundPolicyError` with reason `local_only_mode_blocked` and a message that names **LOCAL_ONLY_MODE** |

**Fail closed:** a blocked call errors visibly. It never silently falls through to
the network transport.

## What leaves the machine

### When Local Only is **off** (default)

Typical analysis may open outbound HTTP(S) to:

- Market data providers (for example Tushare, TickFlow, Yahoo-style quote paths)
- Cloud LLM provider APIs configured as the generation/agent backend
- Search / news / intelligence HTTP sources
- Notification webhooks and channel HTTP APIs
- Any other path that uses `safe_get` / `safe_post` / `guard_outbound_urls`

Loopback and other non-public destinations remain denied unless listed in
`OUTBOUND_HTTP_ALLOWLIST` (or the narrow Ollama admin-loopback exception).

### When Local Only is **on**

| Surface | Leaves the machine? | Notes |
| --- | --- | --- |
| Cloud LLM (OpenAI, Anthropic, remote OpenAI-compatible bases, etc.) | **No** | Blocked at the shared outbound policy with `local_only_mode_blocked` |
| Remote market data / search / news HTTP | **No** | Same; providers must degrade to local cache/error per existing stability rules |
| Notification HTTP webhooks | **No** | Channel failures must not be silent security fall-through |
| Local Ollama / loopback model HTTP | **Yes (loopback only)** | `127.0.0.0/8`, `::1`, `localhost` |
| `OUTBOUND_HTTP_ALLOWLIST` remote hosts | **No** | Allowlist **cannot** expand the perimeter beyond pure loopback while Local Only is on |
| Desktop GitHub update checks | **Out of scope of this gate** | Owned by the desktop shell; not enforced by backend outbound policy |
| SMTP / DB / non-HTTP protocols | **Out of scope** | Same limits as the outbound HTTP policy document |

Local Only is an **egress gate**, not a guarantee of “full offline analysis
quality.” Acceptable offline analysis still depends on cache coverage and local
models (#178, #203). This mode makes remote egress **verifiable and fail-closed**.

## Threat model

| Threat | Mitigation |
| --- | --- |
| Operator believes Privacy Mode is on but cloud LLM still runs | Single env/config key `LOCAL_ONLY_MODE` enforced inside `src/security/outbound_policy.py` for all `safe_*` / `validate_outbound_url` / DNS-guarded SDK paths |
| Silent degradation (blocked call returns empty success) | Policy raises before connect; reason code is stable and named |
| Allowlist used to re-open cloud while “local only” is claimed | Local Only ignores allowlist expansion for non-loopback |
| DNS rebinding of `localhost` to a public IP | DNS answers under Local Only must be loopback or the call is blocked |
| Diagnostics leak secrets via host/URL in the activity UI | Activity records store only destination **class**, scheme, host type, reason, correlation id — never host or URL |

## How to enable

```dotenv
LOCAL_ONLY_MODE=true
```

1. Prefer a local generation backend (Ollama on loopback, or local CLI if it does not need cloud HTTP).
2. Ensure market data cache is warm for symbols you need offline.
3. Restart long-running processes (`python main.py --serve`, Docker, Desktop backend) so every worker reloads the environment.
4. Open **Settings → Auth & Security → Outbound activity** and confirm the mode badge is on.
5. Trigger a remote-dependent action and confirm rows show `blocked` / `local_only_mode_blocked` for non-loopback classes, and only `loopback` allows.

## Verification surfaces

| Surface | Path |
| --- | --- |
| Config registry / Settings switch | `LOCAL_ONLY_MODE` (system / Auth & Security) |
| Status API | `GET /api/v1/security/local-only` |
| Activity API | `GET /api/v1/security/outbound-activity` |
| Web panel | Settings → Auth & Security → Outbound activity |
| Automated proof | `tests/security/test_local_only_mode.py` (analysis-walk fixture: zero non-loopback allows) |

## Limits

- In-memory activity ring buffer (default capacity 100) is per process and clears on restart.
- Paths that bypass `src.security.outbound_policy` are outside this contract; new HTTP call sites must use the shared helpers.
- Local Only does not by itself install models or historical data.

## Rollback

Set `LOCAL_ONLY_MODE=false` (or remove it) and restart processes. Revert the
feature change set if rolling back code; no database migration is involved.
