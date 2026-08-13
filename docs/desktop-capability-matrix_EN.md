# Desktop vs Web capability matrix

Operator-facing matrix for Desktop vs pure Web. Both share the same React routes and API on a private local origin, but **process environment, protocol launch, and update retention** differ. This page closes the published matrix for #884. Packaging details remain in [desktop-package_EN.md](desktop-package_EN.md). Chinese: [desktop-capability-matrix.md](desktop-capability-matrix.md).

## Overview

| Capability | Web (browser) | Desktop (Electron) | Notes |
| --- | --- | --- | --- |
| Report / analysis / Settings UI | Yes | Yes (same build) | Desktop serves `static/` via local FastAPI |
| Login and session cookies | Yes | Yes | Same Web origin; brand migration copies session state |
| `stockpulse://` deep links | No | Yes | See [desktop deep-link policy](desktop-deep-link-policy_EN.md) |
| Browser address bar / shareable URLs | Yes | Private origin only | External links open in the system browser |
| Auto-update and version checks | No | Yes | `window.dsaDesktop` update API |
| Retain `.env` / DB / caches across updates | N/A | Yes | Windows NSIS backup/restore; macOS uses userData |
| Local Ollama start/stop / embedded runtime | Probe remote service | Yes | Local Models panel |
| Generation-backend CLIs (codex/claude/opencode) | Host PATH | Desktop child PATH | macOS GUI augments common Homebrew paths |
| CLI/PATH visibility diagnostics | No | Yes | `available` / `missing` / `unknown`; no raw paths |
| Actionable guidance when CLI is missing | No | Yes | Open terminal / install guide in Model Sources |
| Schedule process-mode wording | Web deploy semantics | Local Desktop semantics | Settings schedule block / #869 |
| Env / `.env` location | Server deploy directory | Windows: beside exe; macOS: userData | See packaging docs |
| `WEBUI_PORT` selects connect URL | Yes | No | Desktop picks a free port in `8000–8100` |

## PATH / CLI diagnostics and guidance

- Commands: `ollama`, `codex`, `claude`, `opencode`
- States: `available` / `missing` / `unknown` (timeout, permission, or PATH unavailable → `unknown`; **never fail-open as available**)
- Renderer / IPC receive only command names, statuses, reason codes, and pre-localized copy — **never** raw PATH, PATH entries, or absolute executable paths
- When missing or unknown, Model Sources Local CLI offers: **Open system terminal**, **Open install guide** (HTTPS allowlist), and **Recheck**

## Deep links

Allowlist and rejection behavior: [desktop deep-link policy](desktop-deep-link-policy_EN.md). Non-allowlisted links do not navigate and show a dialog that omits the raw URL.

## Update retention

Critical relative paths (Windows install dir / macOS userData):

- `.env`
- `data/stock_analysis.db` (plus `-wal` / `-shm`)
- `data/provider_cache/daily`
- `data/ollama/models`
- `data/alphasift/hotspots.json`, `hotspot.history.jsonl`, `hotspot_details/`, `snapshot.last_good.json`
- `logs/desktop.log`

Verification tests cover realistic trees (Chinese path segments, nested dirs, existing targets) in `apps/dsa-desktop/tests/main.test.js`.

## Non-goals

- Desktop is not a full OS automation host
- Env denylist is not relaxed for “same as my shell”
