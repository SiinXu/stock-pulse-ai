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
npm install
npm run lint
npm test
```

## Packaging and release

Windows/macOS build steps, CI release workflow, auto-update modes, brand migration, and troubleshooting remain documented in [desktop-package.md](desktop-package.md) (Chinese). Product version line notes for the `0.x` restart and the need for a one-time manual reinstall from `3.x` desktop clients are the same in both languages.
