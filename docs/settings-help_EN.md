# Settings help maintenance (English)

This document mirrors repository rules for the Web settings help inventory. Configuration semantics, defaults, runtime priority, and troubleshooting still follow `.env.example`, `docs/full-guide.md` / topic docs, and the live config registry.

For the full Chinese maintenance guide (including historical PR coverage of field help), see `docs/settings-help.md`.

## Non-settings education help (Issue #201)

Plain-language explanations for risk levels, Risk Manager gate verdicts, portfolio structural health, and common indicators (MA / MACD / RSI) reuse the same `settingsHelp` inventory and `getSettingsHelpContent` resolver under `education.*` keys.

- Source copy lives in `apps/dsa-web/src/locales/settingsHelp.zh.ts` and `settingsHelp.en.ts`.
- The Web mounts a shared `HelpKeyButton` at real display points (report risk strata, risk-gate banner, beginner risk badge, portfolio risk heatmap/metrics, chart MA legend, alert MA/MACD/RSI forms). Do not hardcode educational body text in components.
- After adding keys, run `cd apps/dsa-web && npm run i18n:resources -- --write` and update every locale bundle. Values in non-English bundles must not be byte-identical to English (identical-to-English ratchet). Mark interim non-zh/en copy as `PENDING_NATIVE_REVIEW` until a native reviewer lands.
- Education copy is research framing only; it must not replace professional metrics or invent risk-gate verdicts.

## Related

- Settings field help structure: `docs/settings-help.md`
- Risk gate Web presentation: `docs/risk-manager-gate_EN.md`
