# Settings help maintenance (English)

This document mirrors repository rules for the Web settings help inventory. Configuration semantics, defaults, runtime priority, and troubleshooting still follow `.env.example`, `docs/full-guide.md` / topic docs, and the live config registry.

Optional, read-only, restart-required, and dependency-locked field status copy is shown in the existing Settings help tooltip rather than as always-visible label badges. Required badges, validation errors, and schema safety diagnostics such as `schema_ui_placement_missing` stay on the field.

For the full Chinese maintenance guide (including historical PR coverage of field help), see `docs/settings-help.md`.

## Non-settings education help (Issue #201)

Plain-language explanations for risk levels, Risk Manager gate verdicts, portfolio structural health, and common indicators (MA / MACD / RSI) use a dedicated education-help inventory and the `getEducationHelpContent` resolver under `education.*` keys.

- Source copy lives in `apps/dsa-web/src/locales/educationHelp.zh.ts` and `educationHelp.en.ts`. Non-configuration keys must not enter the Settings help contract.
- The Web mounts a shared `HelpKeyButton` at real display points (report risk strata, risk-gate banner, beginner risk badge, portfolio risk heatmap/metrics, chart MA legend, alert MA/MACD/RSI forms). Do not hardcode educational body text in components.
- Non-source-language education copy lives under `locales/educationHelpTranslations/` and is lazy-loaded for the active UI language. Update every language-specific education chunk when adding keys; copy must not be byte-identical to English. Mark interim non-zh/en copy as `PENDING_NATIVE_REVIEW` until a native reviewer lands.
- Education copy is research framing only; it must not replace professional metrics or invent risk-gate verdicts.

## Related

- Settings field help structure: `docs/settings-help.md`
- Risk gate Web presentation: `docs/risk-manager-gate_EN.md`
