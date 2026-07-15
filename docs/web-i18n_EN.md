# Web Internationalization Conventions

StockPulse Web treats UI language and report language as separate settings.

- **UI language** controls navigation, buttons, forms, modals and drawers, feedback, errors, accessibility copy, document titles, and the display locale for dates, numbers, and currency.
- **Report language** controls generated report content, report structure, and report exports.
- User input, stock and company names, original news, model IDs, third-party strategy text, and raw diagnostics are not translated automatically.

When an English UI displays a Chinese report, the report body may remain Chinese, but copy, refresh, close, diagnostics, and other surrounding actions must remain English.

## Translation Files

Do not grow one monolithic dictionary. Cross-page copy belongs in `src/i18n/uiText.ts`; large pages and business domains use focused modules under `src/locales/`, for example:

```text
locales/alerts.ts
locales/portfolio.ts
locales/screening.ts
locales/settingsPage.ts
locales/settingsModelAccess.ts
locales/reportChrome.ts
```

Each domain registry must use `Record<UiLanguage, ...>` or an equivalent typed constraint so every language has the same structure. To add a language, extend `UiLanguage` and then implement the same keys in every domain. Do not add broad `language === 'en' ? ... : ...` branches in JSX.

Use named interpolation parameters such as `{count}` and `{name}`. Every language must expose the same parameter set. Dynamic server values may fall back to their original text only in explicitly allowed fields.

## Errors and Formatting

Backend errors exposed to the Web should include a stable `error` code, diagnostic `message`, and structured `details`. The UI maps the code to localized primary copy. Raw messages belong in expandable diagnostics and must not become a Chinese primary error in an English UI.

Use `src/utils/uiLocale.ts` for dates, numbers, currency, and lists. Keep display locale separate from market business time zones. ISO form values, stock symbols, and model IDs are not localized.

## Task Messages and Recovery

Analysis-task acceptance responses, task lists, individual status responses, and SSE events share one versioned contract. `message_code/message_params` and `error_code/error_params` drive primary UI copy; raw `message/error` fields are retained only for compatibility diagnostics. The Web translates codes using the current UI language on every render. Unknown codes and legacy payloads use localized generic copy, while original text appears only in expandable diagnostics.

POST, SSE, and polling snapshots for the same task merge by `task_id + revision`; an older revision must never overwrite newer state. When SSE disconnects, the Web immediately polls `/analysis/status/{task_id}` for each known non-terminal task and stops fallback polling after reconnecting. A refresh restores active tasks and terminal tasks inside the retention window. Dismissal is tied to the observed revision and has a TTL, so a newer revision becomes visible again.

## Verification

```bash
cd apps/dsa-web
npm run test:i18n
npm run test
npx tsc -b
npm run build
npx playwright test e2e/i18n.spec.ts
```

`test:i18n` checks zh/en keys, empty translations, interpolation parameters, duplicate keys, and hardcoded Chinese UI copy in production TSX. Allowances must identify a specific file and purpose; directory-wide exclusions are prohibited.
