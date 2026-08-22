---
applyTo: "apps/dsa-web/**,apps/dsa-desktop/**,scripts/run-desktop.ps1,scripts/build-desktop*.ps1,scripts/build-*.sh,docs/desktop-package.md"
---

# Client Instructions

- Preserve the existing Vite + React web structure and Electron desktop runtime assumptions; reuse current API/state patterns instead of adding parallel client abstractions.
- If a change affects API fields, auth state, route behavior, Markdown/chart rendering, local backend startup, or report payloads, assess both Web and Desktop compatibility.
- Validate Web changes with `cd apps/dsa-web && npm ci && npm run lint && npm run build` when feasible.
- Validate Desktop changes with `cd apps/dsa-desktop && npm ci && npm test` (PR `desktop-gate`). Full packaging still requires building Web first, then the desktop client; if platform limits prevent full Electron validation, call out the exact risk in the final delivery.
