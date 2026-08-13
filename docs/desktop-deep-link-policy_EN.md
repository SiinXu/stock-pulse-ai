# Desktop deep-link policy (`stockpulse://`)

Policy closeout for #884: deep links are **implemented**, not deferred. Chinese: [desktop-deep-link-policy.md](desktop-deep-link-policy.md). Packaging/registration details: [desktop-package_EN.md](desktop-package_EN.md).

## Canonical form

```text
stockpulse://app/<in-app-path>?<query>
```

Examples:

```text
stockpulse://app/portfolio?account=7
stockpulse://app/stocks/AAPL?period=weekly
```

- Scheme: `stockpulse`
- Authority: fixed `app` (no username, password, port, or non-`app` host)
- Fragment: forbidden
- Max length: 4096
- Control characters / unencoded spaces: rejected

## Path allowlist

Only stable Web product entry points:

- `/`
- `/chat`
- `/portfolio`
- `/decision-signals`
- `/alerts`
- `/backtest`
- `/screening`
- `/settings`
- `/usage`
- `/stocks/<stockCode>` (single ASCII segment, `[A-Za-z0-9.]{1,16}`)

Query handling stays with Web routes. The Desktop shell only guarantees the private local origin and overlays `desktop_version` / `cache_bust`.

## Explicit rejections (with UX)

All of the following are rejected **without changing the current page**. Logs omit the raw URL/query. When the app is already running, an info dialog explains the rejection without echoing the original link:

- Non-`stockpulse` scheme or non-`app` authority
- Paths outside the allowlist (for example `/login`)
- Host smuggling (`stockpulse://evil.example/settings`)
- Encoding/normalization smuggling, credentials, ports, fragments

Arbitrary `https` Web URLs are not forwarded as deep links.

## Lifecycle

- Cold start: Windows/Linux from argv; macOS via `open-url`
- Backend not ready: queue until the private Web origin is ready
- Already running: second-instance / `open-url` focuses the main window, then uses the same parser

## Verification

```bash
open "stockpulse://app/portfolio?account=7"
open "stockpulse://app/login"   # must reject; page unchanged
```
