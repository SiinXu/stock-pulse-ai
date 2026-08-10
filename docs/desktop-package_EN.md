# Desktop packaging (Electron + React UI)

English twin of [desktop-package.md](desktop-package.md). Packaging build matrices, Windows NSIS details, and macOS notarization notes that are not repeated here remain authoritative in the Chinese document when they differ only in language.

## Architecture

- The React UI (`apps/dsa-web`, Vite build) is served by the local FastAPI backend.
- On launch, Electron starts the backend, waits for `/api/health`, then loads the UI.
- Visible product name, loading page, executables, and release artifacts use **StockPulse**.
- Windows internal `appId` stays `com.daily-stock-analysis.desktop` for stable NSIS upgrade identity (not user-facing branding).
- Database migrations run when the Python backend first initializes `DatabaseManager`; Electron does not re-implement schema upgrades. Generic `/api/health` is not a database readiness probe.
- Windows portable/installed: `.env`, database, and provider cache live next to the executable. macOS packaged: Electron userData holds those runtime files.
- Desktop picks a free port in `8000–8100` and pins the backend to it; it does **not** use `.env` `WEBUI_PORT` for the window connect URL.
- Report Markdown http(s) links that would leave the private local origin are opened in the system browser.

Share-image generation remains **Web-only** when `window.dsaDesktop` is present (no desktop IPC share path yet).

## First-run and one-click local install

On a **fresh install** (runtime directory had no `.env` before bootstrap), after `/api/health` succeeds the shell opens the existing Web first-run route:

`/settings?section=overview&view=readiness&from=onboarding`

That reuses `FirstRunWizard` (cloud API / local model / CLI). There is no second desktop-only wizard UI. Inbound `stockpulse://` deep links take priority. Returning users with incomplete setup keep the Home guided banner instead of a forced modal every launch.

**Window state:** the main `BrowserWindow` is created with `show: false` and is revealed after the loading page (or error page) is ready, avoiding a blank chrome flash. After the UI loads, the shell warms local-model detection (system / embedded Ollama) so the wizard's local-model step can show runtime status without an extra Detect click.

**One-click local install** composes existing Model Pack + Ollama paths only:

1. The user clicks **Import Model Pack** in Local Models (or the same control inside the wizard local-model step) and explicitly picks a `.modelpack` / `.zip` or unpacked folder. Multi-GB weights are **never** downloaded silently.
2. Main process order: detect runtime → if `stopped`, start system or embedded Ollama → validate and import the pack, with a single progress stream.
3. Failures return actionable messages and stable codes (`ollama_unavailable`, disk/hash errors, etc.) without stack traces in the UI.
4. Catalog Ollama pulls still require explicit user selection and only allowlisted pullable models. Kronos weights stay opt-in via `scripts/download_kronos_weights.py` / source installs; prebuilt desktop packages do not ship PyTorch or Kronos weights (see [kronos-local-model_EN.md](kronos-local-model_EN.md)).

First open does **not** consume cloud LLM tokens. Cloud LLM and market data APIs may still be required depending on the path chosen in the wizard.

## Local models (desktop)

**Settings → AI & Models → Local Models** is the single download/import surface for Desktop and Web. Tray **Local Models…** focuses the main window on `/settings?section=ai_models&view=local_models`. The old standalone model window and `model-preload.js` are retired.

- Detection prefers a healthy `LLM_OLLAMA_BASE_URL` (default `http://127.0.0.1:11434`), then system `ollama`, then the checksum-verified embedded runtime under `resources/ollama/`.
- Statuses: `running` / `stopped` / `not-installed` / `starting` / `error`.
- Pull: allowlisted catalog models only, with progress and hard timeouts; no arbitrary names.
- Start/Stop: managed `serve` only for desktop-spawned processes; embedded runtime is loopback-only.
- Import: after explicit pack selection, auto detect/start then import (one-click path above).
- Activation and assignment go through backend `SystemConfigService` with desktop attestation; Electron does not re-implement config mutation.

Embedded model data is isolated from system Ollama (`data/ollama/models` under the Windows app dir or macOS userData). See the Chinese doc for update backup size, uninstall cleanup, and security baselines (allowlisted binaries, fixed argv arrays, main-window IPC sender checks).

## Local development

```bash
cd apps/dsa-web && npm install && npm run build
cd ../dsa-desktop && npm install && npm run dev
```

Or on Windows: `powershell -ExecutionPolicy Bypass -File scripts\\run-desktop.ps1`.

On first run, Electron copies `.env.example` to the runtime `.env` when missing.

### Desktop verification

```bash
cd apps/dsa-desktop
npm ci
npm audit
npm audit --omit=dev
npm ls js-yaml tar
npm run lint
npm test
# optional: npm run typecheck  (// @ts-check; incomplete JSDoc diagnostics may remain)
```

## Dependencies and toolchain (Desktop)

Pinned in `apps/dsa-desktop/package.json` (landed for #615 via PR #776 / #907; keep the lockfile and `tests/lint-and-deps.test.js` in sync):

| Package | Pin | Role |
| --- | --- | --- |
| `electron` | `43.3.0` | Declared as a devDependency, but shipped as the packaged runtime |
| `electron-builder` | `26.15.7` | Packaging toolchain (`app-builder-lib` 26.15.7) |
| `electron-updater` | `6.8.9` | Auto-update (production dependency) |
| `app-builder-lib` → `tar` override | `7.5.22` | Build-chain audit pin; archive-path compatibility is unit-tested |
| Top-level `js-yaml` override | `4.3.1` | Forces the updater/builder `^4.1.0` / `^4.3.0` graph past the 4.x advisory floor |

Expected: `npm audit` and `npm audit --omit=dev` both report **0 vulnerabilities**. Do not treat Electron as "dev-only exposure" because it is embedded in release artifacts.

### Advisory basis (#615)

Representative advisories that motivated leaving Electron 31 / builder 24 / older updater, and how current pins clear them:

| Component | Advisory | Severity | Affected range (summary) | Current disposition |
| --- | --- | --- | --- | --- |
| Electron runtime | Multiple 2026 GHSA/CVE lines (iframe/popup, DevTools, contextBridge; e.g. [GHSA-9f4c-93c8-jc8g](https://github.com/advisories/GHSA-9f4c-93c8-jc8g) / CVE-2026-70608) | High / Moderate | Primarily 39.x–42.x patch lines; **43.3.0 stable is not listed as vulnerable** | Pin `43.3.0` (npm `latest` / `43-x-y`) |
| electron-updater | [GHSA-9jxc-qjr9-vjxq](https://github.com/advisories/GHSA-9jxc-qjr9-vjxq) / CVE-2024-39698 | High | `<= 6.3.0-alpha.5` | `6.8.9` |
| electron-builder | No separate open npm GHSA node; legacy 24.x trees showed high findings under local audit | — | Pre-26 packaging graph | `26.15.7` |
| `tar` (builder transitive) | e.g. [GHSA-23hp-3jrh-7fpw](https://github.com/advisories/GHSA-23hp-3jrh-7fpw) / CVE-2026-59873, [GHSA-r292-9mhp-454m](https://github.com/advisories/GHSA-r292-9mhp-454m) | Critical / High / Moderate | `<=7.5.18`, `<=7.5.20`, etc. | Override `7.5.22` |
| `js-yaml` 4.x | [GHSA-5p4m-2wfm-xmqj](https://github.com/advisories/GHSA-5p4m-2wfm-xmqj) (**no** standalone CVE ID) | High | `>=4.0.0, <4.3.1` | Override `4.3.1` |
| `js-yaml` 5.x (do not conflate) | [GHSA-724g-mxrg-4qvm](https://github.com/advisories/GHSA-724g-mxrg-4qvm) / CVE-2026-59870 | Moderate | `>=5.0.0, <=5.2.0` | Desktop stays on the 4.x line |

Do not clear findings with `npm audit fix --force` or blanket audit suppressions. New advisories need an applicability decision (shipped runtime / updater vs build-host-only) before changing pins.

### Breaking changes and migration notes (Electron 31 → 43 / builder 24 → 26)

- **Multi-major Chromium/Node/V8 jump**: isolation defaults can change upstream; this app keeps `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true`, and locks protocol/IPC isolation with desktop unit tests.
- **electron-builder 26 archive API**: archive helpers take a single **options object** (not legacy positional args); see `tests/dependency-overrides.test.js`.
- **Windows protocol registration**: builder 24–26 does **not** write Windows registry entries from `build.protocols`. `stockpulse://` still depends on `installer.nsh` plus runtime `app.setAsDefaultProtocolClient`. macOS still uses `protocols` for `CFBundleURLTypes`.
- **Auto-update**: production `electron-updater@6.8.9`; `build.win.publish` remains GitHub Releases (`SiinXu/stock-pulse-ai`). `main.js` keeps `autoDownload = true` and Windows install-directory backup/restore around updates. The product `0.x` line still cannot auto-update from installed `3.x` clients (semver); see the Chinese doc version-restart section.
- **Startup / local models / CLI**: this stack upgrade does not change Ollama resolution order, embedded runtime manifests, generation-backend CLI discovery policy, or desktop port selection (`8000–8100`). PATH/CLI visibility diagnostics belong to #884 and are out of the #615 dependency boundary.
- **Release artifacts**: full NSIS/DMG with frozen backend + embedded Ollama, signing/notarization, and installed-client update cycles require Windows release runners or macOS with Apple identity. A host-local `electron-builder --mac dir` layout smoke is not release-equivalent.

### Rollback

1. Restore `apps/dsa-desktop/package.json` and `package-lock.json` to the previous pins (or `git revert` the dependency commits).
2. Reinstall from the restored lock and rebuild desktop artifacts.
3. No database/config schema migration; `appId` (`com.daily-stock-analysis.desktop`) is unchanged, so NSIS install identity does not flip solely because of a dependency rollback.

## Packaging and release

Windows/macOS build steps, CI release workflow, auto-update modes, brand migration, and troubleshooting remain documented in [desktop-package.md](desktop-package.md) (Chinese). Product version line notes for the `0.x` restart and the need for a one-time manual reinstall from `3.x` desktop clients are the same in both languages.
