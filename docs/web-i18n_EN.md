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
locales/reportContent.ts
```

Each domain registry must use `Record<UiLanguage, ...>` or an equivalent typed constraint so every language has the same structure. To add a language, extend `UiLanguage` and then implement the same keys in every domain. Do not add broad `language === 'en' ? ... : ...` branches in JSX.

Use named interpolation parameters such as `{count}` and `{name}`. Every language must expose the same parameter set. Dynamic server values may fall back to their original text only in explicitly allowed fields.

## Errors and Formatting

Backend errors exposed to the Web use one envelope: `error` is the stable business code, `params` contains localization interpolation values, and `message`, `details`, plus optional `trace_id` are diagnostic-only. The UI maps `error + params` to primary copy in the current UI language. Unknown codes show a localized generic error; the legacy raw-string adapter preserves the original value in Details instead of promoting it to primary copy.

Agent session history follows the same contract. For a failed history entry, the history API returns safe compatibility `content` and identifies the localizable failure with `error + params`; ordinary messages omit those two fields. The Web resolves the error at render time in the current UI language, and message display, single-message copy, and session export must reuse that same result so loaded history updates immediately after a language switch. The server adapts historical `[分析失败]...` entries to a stable error code. New failures must not persist raw Provider errors or return them to clients.

Diagnostic fallbacks must remain layered: a known `error` uses its localized copy and `params`; an unknown `error` uses the localized generic error; legacy raw strings, `message`, `details`, and `trace_id` remain diagnostic-only and must not become primary copy. Safe history `content` exists for compatibility with older clients and must not override localization for a stable error code.

Task POST, SSE, and polling payloads use stable `message_code` and `message_params`. Components format them at render time in the current UI language so existing tasks update immediately after a language switch. A legacy server `message` is diagnostic compatibility data and must not bypass localization as the primary task status.

Use `src/utils/uiLocale.ts` for dates, numbers, currency, and lists. Keep display locale separate from market business time zones. ISO form values, stock symbols, and model IDs are not localized.

## Overlays and Accessibility Copy

`Modal`, `Drawer`, `ConfirmDialog`, and mobile history panels share one overlay stack. Only the top layer handles Escape and Tab; opening a layer isolates the background and locks scrolling, and closing restores focus. Titles, descriptions, close controls, aria labels, and pending-state copy follow UI language. Report content inside an overlay still follows report language, while the overlay chrome does not.

## Verification

```bash
cd apps/dsa-web
npm run test:i18n
npm run test
npx tsc -b
npm run build
npm run test:smoke
```

`test:i18n` checks zh/en keys, empty translations, interpolation parameters, duplicate keys, and Chinese or English user-facing copy in production TSX JSX text/expressions, template literals, `aria-label`, `aria-description`, `alt`, `placeholder`, `title`, `label`, `message`, `description`, notification/error setters, toasts, and document titles. The scanner resolves direct and indirect references to local `const` values, including aliased and nested destructuring, object properties, object spreads, and JSX spreads so intermediate variables cannot bypass the guard; dynamic values and mutable bindings are not treated as static copy. Every allowance must identify the exact file, string, context, and purpose and remain in active use; file-wide and directory-wide exclusions are prohibited. Playwright scenarios need independent readable test names and key assertions; loops or numbered comments do not count as semantic coverage.
