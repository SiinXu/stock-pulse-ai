# High-risk i18n semantic audit

This document records the evidence boundary for StockPulse Web copy that can alter a user's understanding of a trade action, financial risk, authentication state, credential, error, or investment disclaimer.

## Audit identity

| Field | Value |
| --- | --- |
| Foundation | `I18N-01` |
| Track | `TRACK-E2` |
| Sequence | `33/34` |
| Repository | `SiinXu/stock-pulse-ai` |
| Merged-copy baseline | `origin/main@d760f9c4284e4b061a57d3d56984975d0dec7381` |
| Audit date | 2026-07-20 |
| Machine-readable evidence | `apps/dsa-web/scripts/high-risk-i18n-audit.json` |
| Enforced command | `cd apps/dsa-web && npm run i18n:high-risk` |
| Baseline verification | `cd apps/dsa-web && npm run i18n:high-risk -- --verify-baseline` |

Only copy merged at the recorded baseline was audited. Open PRs #94, #98, and #99 were excluded; none edits an i18n resource or a high-risk Web string, and their only E2 file overlap is the append-only `[Unreleased]` changelog. PRs #95, #96, and #100 merged while the audit was in review; none changed an i18n resource or high-risk string, so the baseline advanced without changing the audited source inventory. PR #90 was merged before the final baseline: its three localized `interrupted` task-state labels were reviewed and remain outside the six high-risk categories. Dependencies #51, #56, and #64 were merged before this audit.

## Result

The executable audit covers six required categories, ten UI locales, and 308 distinct stable translation keys. Category counts overlap where one string has more than one risk dimension. Its 93 recorded stable-key decisions and 501 locale-value revisions are protected by separate counts and SHA-256 digests, so removing or changing decision evidence fails the normal guard even when candidate bundle snapshots remain unchanged.

| Category | Stable keys | Boundary |
| --- | ---: | --- |
| Trading action | 18 | Decision-signal and portfolio action codes remain internal; labels are informational display states. |
| Risk | 73 | Volume, turnover, score, confidence, orchestrator risk-stage order, risk-agent veto, BIAS threshold, market-context guardrails, portfolio risk, alert severity, and strategy labels keep their product meaning. |
| Authentication | 87 | Login, password, session, transport, password-change, retry-limit, and admin-auth settings copy states the actual authentication condition. |
| Credential | 43 | Credential, password, API key, provider-key routing, CLI login state, runtime secret, and usage-telemetry HMAC secret remain distinct concepts. |
| Error | 102 | Stable error codes remain contract values; localized title/message pairs are display copy. |
| Disclaimer | 3 | Screening notices preserve research scope, no-investment-advice language, and user responsibility. |

All currently shipped keys in these selectors are snapshotted per locale. Adding, removing, or changing an audited key fails `npm run i18n:high-risk` until the evidence and semantic decision are reviewed together. The explicit baseline mode also parses the recorded `en.ts` and translated bundles with the TypeScript AST, checks that the current branch merge-base is the recorded audit commit, verifies every `before` value against that commit, and requires the actual baseline-to-candidate revision set to equal the complete decision set.

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
| Orchestrator, risk-agent, and BIAS controls | Reordered or missing pipeline stages, translated `full/specialist` values, malformed risk-stage gates, generic tracking, and average-return wording | Literal mode/stage values, explicit `tech→intel→risk→decision` order, risk-stage gating, chase-risk warnings, and mean-reversion risk. |
| Admin authentication | Sentence fragments that obscured login, persistence, and reset behavior | WebUI login scope, persisted auth data, refresh/restart behavior, and the exact reset command. |
| Usage HMAC secret | Broken wording that conflated a telemetry secret, key, and generic usage | Message-fingerprint signing, no login-secret reuse, local generation, cross-deployment comparison, and key-version rotation. |
| Screening disclaimer | Fragmented machine-translated clauses | Experimental/research scope, no investment advice, and user responsibility all remain explicit. |

Exact `before` and `recommended` values, rationale, and sources for every revised stable key are stored in the audit manifest. Per-category, per-locale SHA-256 snapshots also cover unchanged values inside the audited selectors.

## Display and code separation

Within the six audited contract inventories, localized display keys are distinct from business identifiers. This guard does not claim that every component-owned runtime fallback is already localized.

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
npm run i18n:high-risk -- --verify-baseline
npm run test:i18n
```

The high-risk guard fails on:

- a missing required category, source, locale status, or evidence decision;
- a translated locale mislabeled as product source;
- a pending locale that names a native reviewer or review date;
- unsupported approval language without the native-review evidence contract;
- decision or locale-revision evidence whose count or SHA-256 digest no longer matches the recorded layers;
- a recorded `before` value that differs from the merge-base bundle when baseline verification is requested;
- an actual baseline-to-candidate locale revision missing from the decision set, or an unexpected decision with no matching revision;
- drift between TypeScript internal codes and stable display mappings;
- an added, removed, or changed audited key without refreshed evidence;
- a corrected high-impact value that no longer matches its recorded recommendation.

`npm run test:i18n` also checks complete key sets, non-empty values, interpolation parameters, Unicode normalization, corruption markers, and hardcoded UI copy. Those checks prove structural integrity, not financial translation quality.

To review an intentional change, update the product source or candidate bundle first, update the semantic decision and sources, then run:

```bash
cd apps/dsa-web
npm run i18n:resources -- --write
npm run i18n:high-risk -- --print-snapshot
npm run i18n:high-risk -- --verify-baseline
```

Copy the reviewed snapshot into `high-risk-i18n-audit.json`, run the normal guard, and keep translated locales pending unless a real native financial reviewer is identified with a review date.

## Deferred to UIUX

No open UI PR changed a high-risk string during the audit. The following component-owned paths remain outside E2 file ownership and were not edited:

- `components/decision-signals/DecisionSignalDisplay.tsx`: feedback `reasonCode` is rendered directly below the localized feedback label.
- `pages/DecisionSignalsPage.tsx`: three reassessment warning lists render `warning.message || warning.code`, so an absent message exposes the internal warning code.

- `pages/StockScreeningPage.tsx`: `Screening failed` is a legacy diagnostic fallback inside a stable `alphasift_screen_failed` error envelope; localized stable error copy remains the primary message.
- `components/settings/SettingsPanelErrorBoundary.tsx`: `Unknown frontend runtime error` is a sanitized diagnostic summary fallback; localized title and recovery copy remain primary.

The first two paths need stable localized display mappings or a diagnostics-only presentation before the project can claim complete runtime code/display separation. All four items should be moved behind stable locale keys by the UIUX owner when those component paths are next changed. They are not evidence that the high-risk bundles received native review.

## Limitations

- The audit does not translate user content, model output, provider diagnostics, symbols, model IDs, URLs, enum values, or error codes.
- It does not audit strings that exist only in an open PR.
- It does not certify legal or regulatory compliance in any jurisdiction.
- It does not claim that automated checks establish linguistic naturalness or native financial review.
- Screenshots are PR evidence, not repository governance assets; affected pages must be captured in a non-credential-bearing session or the PR must state why a screenshot was unavailable and provide reproducible alternative evidence.
