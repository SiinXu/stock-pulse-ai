# Actions regular-user capability split (v1)

> Subscription-layer (path A) experience differentiation plan. Existing issue: https://github.com/SiinXu/stock-pulse-ai/issues/847

Related: #797 #796 #795 #624 #241

## Overview

| Priority | Theme | Status |
|----------|-------|--------|
| P0 | Config Check | #847 |
| P0 | Failure/skip plain-language Summary + short error notification | To create |
| P0 | Actions three-line preset docs | To create |
| P1 | No IM: GitHub Issue daily report inbox | To create |
| P1 | Simple report honesty layers + decision structure | To create |
| P1 | alert-only: notify only on notable moves | To create |
| P2 | Weekly digest workflow | To create |

## Issue 2 — Failure plain-language Summary

Title: `[Feature] Actions: Daily Analysis failure/skip plain-language Summary + short error notification`

Plan: always/failure step at end of `00-daily-analysis.yml`; `run_status.json`; `GITHUB_STEP_SUMMARY`; short system-error notification.
Cause codes: `missing_llm` / `missing_watchlist` / `non_trading_day` / `data_source` / `timeout` / `unknown`
User path: run analysis → read cause in Summary → optional IM → fix config or use #847
Config: `NOTIFICATION_SYSTEM_ERROR_CHANNELS`; optional `FAILURE_NOTIFY_ENABLED`; no new Web page

## Issue 3 — Three-line preset docs

Title: `[Docs] Actions regular-user three-line preset`

Minimum: `LLM_ZHIPU_API_KEY` or `LLM_SILICONFLOW_API_KEY` or `GEMINI_API_KEY`; `STOCK_LIST`; optional webhook
Path: Fork → fill 2–3 items → Config Check → Daily Analysis → IM/Artifact

## Issue 4 — Issue inbox

Title: `[Feature] Actions: GitHub Issue daily report inbox`

`REPORT_ISSUE_INBOX_ENABLED` (default false); upsert a single Daily analysis inbox issue; follow upstream-parity patterns; public-repo privacy notes

## Issue 5 — Report honesty layers

Title: `[Feature] simple report: facts / gaps / inference + decision structure`

Default simple layout fixed sections: facts, data gaps, inference, observation framework; footnotes for model and data sources; `REPORT_HONESTY_LAYERS` default true

## Issue 6 — alert-only

Title: `[Feature] alert-only mode`

`mode=alert-only`; reuse #241 rules; no spam when nothing triggers; Web extends existing Alerts UI

## Issue 7 — Weekly digest

Title: `[Feature] Actions weekly digest`

`01-weekly-digest.yml`; summarize last ~5 days without a full re-run; honest note when sample is insufficient

## Order

847 → failure Summary → three-line docs → inbox → honesty layers → alert-only → weekly digest
