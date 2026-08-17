# API Error Taxonomy

Stable machine-readable `error` codes are the primary contract of the version-one
API error envelope. This document defines the **taxonomy** that classifies those
codes into category, severity, and a default user action without replacing the
codes themselves.

Chinese: [api-error-taxonomy.md](api-error-taxonomy.md)

## Envelope fields

| Field | Role |
| --- | --- |
| `error` | Stable business code (authoritative identity) |
| `message` | Diagnostic / legacy fallback copy (not primary UI copy) |
| `params` | Bounded localization interpolation data |
| `details` / `detail` | Nested diagnostics (`detail` is a deprecated alias of `details`) |
| `category` | Taxonomy category derived from `error` (additive) |
| `severity` | `info` \| `warning` \| `error` \| `critical` (additive) |
| `trace_id` | Support correlation id |

## Categories

| Category | Typical failures | Default action |
| --- | --- | --- |
| `auth` | Session expired, auth disabled | login / settings |
| `credential` | Password / key validation | retry / login |
| `rate_quota` | Rate limits, quota, balance | retry / docs |
| `provider_network` | Upstream network / DNS / proxy | retry |
| `timeout` | Upstream or stream timeouts | retry |
| `validation` | Bad input, limits, format | none (fix input) |
| `busy` | Duplicate task, scheduler busy | none / retry later |
| `config_conflict` | Settings 409 / version conflict | reload + retry |
| `capability` | LLM missing, agent off, feature gates | settings / docs |
| `notification` | Channel missing / test failed | settings |
| `not_found` | Missing resource | none |
| `outbound_policy` | LOCAL_ONLY / SSRF blocks | settings / docs |
| `internal` | Unknown / server failures | retry |

## Default actions (Web contract)

| Action | UI behavior |
| --- | --- |
| `retry` | Show Retry **only** when the caller supplies a real operation handler. Clearing the error alone is not a retry. |
| `settings` | Navigate to a Settings deep link |
| `login` | Navigate to login |
| `docs` | Open related documentation (GitHub docs path) in a new tab |
| `none` | Guidance text only; no primary CTA |

Taxonomy severity controls the visual toast tone, while API operation failures
remain assertive `alert` announcements. Generic warning/info toasts remain polite
`status` announcements; visual tone must not silently downgrade error semantics.

Source of truth:

- Backend registry: `src/api/v1/error_taxonomy.py`
- Web mirror: `apps/dsa-web/src/api/error/taxonomy.ts`
- Envelope builder: `src/api/v1/errors.py`
- Web remediation: `resolveErrorRemediation` + `ApiErrorAlert` / `ActionableApiErrorInline`

## Adding a new error code

1. Choose a stable snake_case `error` code.
2. Register it in `src/api/v1/error_taxonomy.py` with category, severity, and default action.
3. Mirror the entry in `apps/dsa-web/src/api/error/taxonomy.ts`.
4. Add Web catalog copy under `STABLE_ERROR_TEXT` (reuse existing action labels; do not expand i18n baselines without justification).
5. Emit through `api_error` / `error_body`.
6. Run:

```bash
python scripts/check_error_taxonomy.py
python -m pytest tests/api/test_error_taxonomy.py tests/api/test_api_error_helpers.py tests/test_error_envelope_contract.py -q
cd apps/dsa-web && npm run test -- src/api/error/__tests__/taxonomy.test.ts src/api/__tests__/error.test.ts src/components/common/__tests__/ApiErrorAlert.test.tsx
```

## Relationship to #885 mapper

`apps/dsa-web/src/utils/apiReasonMapper.ts` maps codes/reasons to
`ActionableErrorClass` for inline analysis/settings UX. The taxonomy is the
broader category/severity/action registry; both preserve the stable `error` code.

## CI guard

`scripts/check_error_taxonomy.py` runs in `./scripts/ci_gate.sh deterministic` and
asserts:

1. every Web `STABLE_ERROR_TEXT` code is registered in the backend taxonomy;
2. backend and Web `ERROR_CODE_TAXONOMY` share the same codes and
   `(category, severity, default_action)` triples.
