# High-risk i18n semantic audit

This document records the evidence boundary for StockPulse Web copy that can alter a user's understanding of a trade action, financial risk, authentication state, credential, error, or investment disclaimer.

## Audit identity

| Field | Value |
| --- | --- |
| Foundation | `I18N-01` |
| Track | `TRACK-E2` |
| Sequence | `33/34` |
| Repository | `SiinXu/stock-pulse-ai` |
| Merged-copy baseline | `origin/main@59f49297cf744a93cfcd2286f0216f17c3ac546d` |
| Audit date | 2026-07-20 |
| Machine-readable evidence | `apps/dsa-web/scripts/high-risk-i18n-audit.json` |
| Enforced command | `cd apps/dsa-web && npm run i18n:high-risk` |

Only copy merged at the recorded baseline was audited. Open PRs #94, #95, and #96 were excluded. Their current diffs do not edit an i18n resource or high-risk string; their only E2 file overlap is the append-only `[Unreleased]` changelog. PR #90 was merged before the final baseline: its three localized `interrupted` task-state labels were reviewed and remain outside the six high-risk categories. Dependencies #51, #56, and #64 were merged before this audit.

## Result

The executable audit covers six required categories, ten UI locales, and 247 distinct stable translation keys. Category counts overlap where one string has more than one risk dimension.

| Category | Stable keys | Boundary |
| --- | ---: | --- |
| Trading action | 18 | Decision-signal and portfolio action codes remain internal; labels are informational display states. |
| Risk | 26 | Volume, turnover, score, confidence, cost method, watchlist, alert severity, cooldown, and related labels keep their product meaning. |
| Authentication | 80 | Login, password, session, transport, password-change, and retry-limit copy states the actual authentication condition. |
| Credential | 36 | Credential, password, API key, provider-key routing, CLI login state, and runtime secret remain distinct concepts. |
| Error | 102 | Stable error codes remain contract values; localized title/message pairs are display copy. |
| Disclaimer | 3 | Screening notices preserve research scope, no-investment-advice language, and user responsibility. |

All currently shipped keys in these selectors are snapshotted per locale. Adding, removing, or changing an audited key fails `npm run i18n:high-risk` until the evidence and semantic decision are reviewed together.

## Evidence status

`PRODUCT_SOURCE` identifies the product's canonical source copy. It is provenance, not a native-language approval label. No real native financial reviewer was available for this audit, so every translated bundle remains `PENDING_NATIVE_REVIEW` even where an obvious mistranslation was corrected.

| Locale | Evidence status | Native reviewer |
| --- | --- | --- |
| `zh` | `PRODUCT_SOURCE` | Not applicable to translation provenance |
| `en` | `PRODUCT_SOURCE` | Not applicable to translation provenance |
| `zh-TW` | `PENDING_NATIVE_REVIEW` | None recorded |
| `ja` | `PENDING_NATIVE_REVIEW` | None recorded |
| `ko` | `PENDING_NATIVE_REVIEW` | None recorded |
| `de` | `PENDING_NATIVE_REVIEW` | None recorded |
| `es` | `PENDING_NATIVE_REVIEW` | None recorded |
| `ms` | `PENDING_NATIVE_REVIEW` | None recorded |
| `fr` | `PENDING_NATIVE_REVIEW` | None recorded |
| `id` | `PENDING_NATIVE_REVIEW` | None recorded |

Resource completeness, placeholder parity, NFC checks, semantic snapshots, and automated language review are not native financial sign-off. The audit manifest rejects an unsubstantiated approval status and requires reviewer identity plus date before a locale can be marked `NATIVE_REVIEWED`.

## Product source and recommendations

The source and candidate layers are recorded separately. Source changes were made only where the English source itself collapsed two concepts or omitted essential transaction context.

| Stable key | Previous product value | Current product value | Reason |
| --- | --- | --- | --- |
| `locales.screening.SCREENING_TEXT.turnover` | `Turnover` | `Turnover value` | Distinguishes traded monetary value from turnover rate and share volume. |
| `i18n.uiText.UI_TEXT.stockTrend.turnoverRate` | `Turnover` | `Turnover rate` | Names the ratio explicitly. |
| `locales.portfolio.PORTFOLIO_TEXT.side` | `Side` | `Trade side` | Makes the buy/sell transaction context explicit. |
| `locales.screening.SCREENING_TEXT.heat` | `Heat` | `Theme interest` | Describes attention/popularity, not temperature. |
| `locales.screening.SCREENING_TEXT.leader` | `Leader` | `Leading stock` | Describes a security, not a person. |

Other `zh` / `en` high-risk source values were retained because they match the current product contract. The candidate bundle corrections below remain subject to native review.

## Corrected candidates

| Concept | Previous examples | Candidate direction |
| --- | --- | --- |
| Trading volume | `音量の急増`, `Lautstärkespitze`, `Lonjakan kelantangan` | Explicit securities trading volume, such as `出来高急増` and `Sprung im Handelsvolumen`. |
| Theme interest and leading stock | `Hitze`, `Calor`, `Chef`, `Anführer` | Popularity/attention and a leading security, not temperature or a person. |
| Cost method and trade side | `コストベースアプローチ`, `Bahagian`, `Sisi` | Acquisition-cost method and buy/sell transaction direction. |
| Signal action | `避けてください`, `피하세요`, `Vermeiden Sie` | Neutral signal-state labels rather than second-person commands. |
| Confidence and score | `Selbstvertrauen`, `Clasificación`, `Classement` | Model confidence and a numeric score, not self-confidence or ranking. |
| Alert semantics | `Propina`, `自己選択株`, `Temps de recharge`, `Auslösergeschichte` | Information severity, watchlist, suppression interval, and trigger record. |
| API key and provider access | `API Legende`, `touches`, `teclas`, omitted routing paths, and broken credential-file warnings | API key/secret terminology, provider-key precedence, and the boundary between StockPulse and CLI login state. |
| Authentication errors | Mixed formality and malformed password/session text | Consistent recovery text while retaining stable internal error codes. |
| Screening disclaimer | Fragmented machine-translated clauses | Experimental/research scope, no investment advice, and user responsibility all remain explicit. |

Exact `before` and `recommended` values for the highest-impact decisions are stored in the audit manifest. Per-category, per-locale SHA-256 snapshots cover the rest of the audited values.

## Display and code separation

Localized strings are never business identifiers.

| Contract | Internal values | Display mapping |
| --- | --- | --- |
| `DecisionAction` | `buy`, `add`, `hold`, `reduce`, `sell`, `watch`, `avoid`, `alert` | `UI_TEXT.history.action*` |
| `PortfolioSide` | `buy`, `sell` | `PORTFOLIO_SIDE_LABELS` and portfolio display text |
| Stable API errors | 38 codes including `unauthorized`, `invalid_password`, and `portfolio_oversell` | `STABLE_ERROR_TEXT.<code>.title/message` |
| Model-access failures | Values such as `auth`, `missing_api_key`, and `api_key_rejected` | `MODEL_ACCESS_ERROR_LABELS`, `MODEL_ACCESS_ISSUES`, and `MODEL_ACCESS_REASON_HINTS` |

The guard parses the actual TypeScript unions for `DecisionAction` and `PortfolioSide`, derives stable API error and model-access codes from the live display-key inventory, and compares them with the manifest. It also checks that every internal value maps to a distinct stable display key and is not exposed verbatim as localized display copy.

## External evidence

External sources define concepts and risk boundaries; they do not prove that a candidate translation is natural in every locale.

| Authority | Use in this audit |
| --- | --- |
| [FINRA order types](https://www.finra.org/investors/investing/investment-products/stocks/order-types) | Buy/sell/stop terminology and the fact that order controls do not eliminate market or investment risk. |
| [FINRA Rule 2210](https://www.finra.org/rules-guidance/rulebooks/finra-rules/2210) | Fair and balanced investment communications, buy/sell/hold recommendation terminology, and caution against implied future profitability. |
| [HKEX glossary](https://www.hkex.com.hk/Global/Exchange/Glossary?sc_lang=en) | Exchange context for market turnover and trading concepts. |
| [NIST credential glossary](https://csrc.nist.gov/glossary/term/credential) | Credential as evidence binding identity or authority; supports separating credentials from passwords and API keys. |
| [NIST SP 800-63B](https://pages.nist.gov/800-63-4/sp800-63b.html) | Authenticator, password, and retry-limiting concepts. |
| [RFC 9110, 401 Unauthorized](https://www.rfc-editor.org/rfc/rfc9110.html#name-401-unauthorized) | HTTP authentication challenge and credential semantics. |

Sources were accessed on 2026-07-20. The repository product contract and [multilingual financial terminology guide](financial-terminology-guide.md) remain authoritative for StockPulse-specific meanings.

## Automated checks

Run:

```bash
cd apps/dsa-web
npm run i18n:resources
npm run i18n:high-risk
npm run test:i18n
```

The high-risk guard fails on:

- a missing required category, source, locale status, or evidence decision;
- a translated locale mislabeled as product source;
- a pending locale that names a native reviewer or review date;
- unsupported approval language without the native-review evidence contract;
- drift between TypeScript internal codes and stable display mappings;
- an added, removed, or changed audited key without refreshed evidence;
- a corrected high-impact value that no longer matches its recorded recommendation.

`npm run test:i18n` also checks complete key sets, non-empty values, interpolation parameters, Unicode normalization, corruption markers, and hardcoded UI copy. Those checks prove structural integrity, not financial translation quality.

To review an intentional change, update the product source or candidate bundle first, update the semantic decision and sources, then run:

```bash
cd apps/dsa-web
npm run i18n:resources -- --write
npm run i18n:high-risk -- --print-snapshot
```

Copy the reviewed snapshot into `high-risk-i18n-audit.json`, run the normal guard, and keep translated locales pending unless a real native financial reviewer is identified with a review date.

## Deferred to UIUX

No open UI PR changed a high-risk string during the audit. Two component-embedded diagnostic fallbacks remain outside E2 file ownership and were not edited:

- `pages/StockScreeningPage.tsx`: `Screening failed` is a legacy diagnostic fallback inside a stable `alphasift_screen_failed` error envelope; localized stable error copy remains the primary message.
- `components/settings/SettingsPanelErrorBoundary.tsx`: `Unknown frontend runtime error` is a sanitized diagnostic summary fallback; localized title and recovery copy remain primary.

These items should be moved behind stable locale keys by the UIUX owner when those component paths are next changed. They are not evidence that the high-risk bundles received native review.

## Limitations

- The audit does not translate user content, model output, provider diagnostics, symbols, model IDs, URLs, enum values, or error codes.
- It does not audit strings that exist only in an open PR.
- It does not certify legal or regulatory compliance in any jurisdiction.
- It does not claim that automated checks establish linguistic naturalness or native financial review.
- Screenshots are PR evidence, not repository governance assets; affected pages must be captured in a non-credential-bearing session or the PR must state why a screenshot was unavailable and provide reproducible alternative evidence.
