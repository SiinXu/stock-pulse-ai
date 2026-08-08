# TanStack Query page rollout — wave 1

**Status**: Implementation in progress on stack base **#788** (`refactor/data-fetching-pilot-v0`).  
Do not merge this PR into `main` until pilot **#788** is merged; rebase onto main after the pilot lands.  
**Issue**: #789  
**Branch**: `refactor/tanstack-rollout-v1`  
**PR**: #822

## Hard dependency

| Item | Requirement |
| --- | --- |
| Pilot PR #788 | Must merge before this PR can target a clean main merge |
| Provider / deps | Reused from pilot — **not** duplicated here |
| Shared client defaults | `query/createAppQueryClient.ts` (`retry: false`, focus defaults) |

## Wave 1 implemented

| Surface | Hooks | Parity |
| --- | --- | --- |
| Decision Signals list feed | `useDecisionSignalListQuery` | No poll; no focus refetch; key = scope/page/filters/watchlist readiness; list reducer owns loading/error |
| Outcome stats | `useDecisionSignalOutcomeStatsQuery` | Mount load; no focus/poll |
| Detail outcomes + feedback | `useDecisionSignalDetailQueries` | Selection-gated; independent queries; `retry: false` |
| Status update | page-owned `updateStatus` (deferred) | Keeps in-flight double-click guard; not migrated to `useMutation` in wave 1 to preserve parity tests |
| Alerts rules/triggers/notifications | `useAlertWorkspaceQueries` | No poll/focus; create/update/delete stay page-owned; transport still `api/alerts` |
| Skill Outcomes performance | `useSkillOutcomesQuery` | reloadToken initial loads; icon refresh stays page-owned `load('refresh')` |
| Approvals workspace | `useApprovalsWorkspaceQuery` | First full load; 5s proposal poll; poll off when auth-blocked |
| Stock Details quote/history | `useStockDetailsQueries` | Keyed by code/days; no poll/focus |

## Open-PR exclusions (later waves)

| Exclusion | Open PR |
| --- | --- |
| Home history / HomePage | #813 |
| Settings / useSystemConfig | #813, #819, #814 |
| Portfolio | #790, #812 |
| Stock screening | #781 |
| `api/error.ts` | #793 |
| Alerts API module rewrite | #787 |
| Agent API rewrite | #801 |

## Remainder after wave 1

Home history lifecycle → Portfolio projection → Alerts page hooks → Settings → Screening → remaining Chat/agent status polls.

## Refactor contract

- Transport stays in `api/*`
- Zero new i18n strings
- Match prior cadence (Decision Signals list: **no** interval, **no** focus refresh)
- Tests wrap `QueryClientProvider`
