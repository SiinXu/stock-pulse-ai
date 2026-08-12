# Web PWA (shell-only)

StockPulse Web can be installed as a Progressive Web App on supported mobile
and desktop browsers. The implementation is intentionally conservative.

## What is included

| Capability | Behavior |
| --- | --- |
| Web App Manifest | `apps/dsa-web/public/manifest.webmanifest` with name, icons, `standalone` display, start URL `/` |
| Installability | Manifest + production service worker registration from `src/main.tsx` |
| Icons | `public/icons/` (192 / 512 / maskable / apple-touch) derived from the project logo |
| Service worker | Build-time `sw.js` emitted by `vite-plugin-shell-pwa.ts` into `static/` |

## Cache boundary (hard rule)

**Cache only the application shell and static assets.**

| May be cached | Must never be cached |
| --- | --- |
| `/`, `/index.html` (shell HTML for offline boot) | `/api/**` (analysis, history, portfolio, signals, …) |
| Entry `assets/index-*.{js,css}` (precache) | `/health`, `/api/health` |
| Other `/assets/**` (cache-first on first successful fetch) | `/stocks.index.json` (market autocomplete index) |
| `/icons/**`, `/manifest.webmanifest`, `/vite.svg` | OpenAPI UI (`/docs`, `/redoc`, `/openapi.json`) |
| | Non-GET methods |

Install precache stays small (shell + entry chunks + icons). Lazy route chunks
are still allowed as static assets via cache-first after the network responds
successfully; they are never backfilled from API JSON.

Policy source of truth for unit tests: `apps/dsa-web/src/pwa/shellCachePolicy.ts`.
The generated service worker mirrors the same rules.

This boundary is **not** offline analysis mode. Offline / local-first analysis
and market-data caching are owned by issues **#218** and **#990**. Do not extend
this service worker to store analysis reports, quotes, or SSE streams.

## Runtime registration

- Production builds only (`import.meta.env.PROD`).
- Dev server does not register a service worker (HMR and `/api` proxy stay clean).
- Registration failures are non-fatal and logged with `[pwa]`.

## Serving notes

- The FastAPI SPA host serves `static/` including `sw.js` and
  `manifest.webmanifest`.
- `.webmanifest` is registered as `application/manifest+json` in
  `api/app.py` so install prompts work when the OS MIME map is incomplete.
- Installable PWAs require HTTPS (or `localhost`) in real browsers.

## Verification

```bash
cd apps/dsa-web
npm test -- src/pwa
npm run build
# After build, static/sw.js must exist and must not list stocks.index.json
grep -n 'stocks.index.json' ../../static/sw.js && exit 1 || true
test -f ../../static/manifest.webmanifest
test -f ../../static/sw.js
```

## Related issues

- #234 — mobile experience and PWA support (this document)
- #146 — responsive multi-device optimization (layout; separate from cache policy)
- #218 / #990 — offline analysis / local-first data (out of scope here)
