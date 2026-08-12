# Upstream drift inventory

Actionable maintainer inventory for `ZhuLinsen/daily_stock_analysis` drift. Machine commit classification remains the source of truth in `scripts/check_upstream_parity.py` and tracking issue **#1002**. Governance cadence: **#1061**.

- Generated at (UTC): `2026-08-12T10:30:10Z`
- Local ref: `origin/main`
- Upstream ref: `upstream/main`
- Upstream repository: `ZhuLinsen/daily_stock_analysis`
- Fork point (merge-base): `55946536a9765b3d4e2620edef6a50e79d0928d0`
- Upstream-only commits: **60**
- Attention (shared paths, not ported): **25**
- Already ported (`Ported-from`): **35**
- Informational (whitelist-only): **0**

## What upstream has vs this repository

| Dimension | Upstream (since fork point) | This repository |
| --- | --- | --- |
| Commits only on upstream | 60 | n/a (local has its own history) |
| Unported shared-path commits (Attention) | 25 | Needs triage (table below) |
| Matched `Ported-from` trailers | n/a | 35 upstream SHAs marked ported |
| Deliberately diverged only | 0 | Expected product/governance divergence |

### Suggested-action histogram (Attention only)

| Suggested action | Count | Meaning |
| --- | --- | --- |
| `port_now` | 5 | Focused foundation fix; port with tests + `Ported-from` |
| `design_needed` | 1 | Entangled product prototype; design issue first |
| `record_trailer` | 11 | Likely already absorbed; spot-check then record trailers |
| `skip_docs` | 5 | Docs/changelog/marketing only; do not mirror blindly |
| `manual_triage` | 3 | Mixed signal; human classification required |

## Difference list (Attention commits)

For each Attention commit: upstream subject, local path presence, missing shared paths, and suggested action. **Do not treat this table as closed work** — open or update child issues for real residual gaps.

| SHA | Date | Subject | Present/Total | Suggested action | Cluster | Missing sample |
| --- | --- | --- | --- | --- | --- | --- |
| `487e49e56` | 2026-07-16 | feat: 支持保存决策风格重评估结果 (#2014) | 17/18 (94%) | `record_trailer` | decision profile | tests/test_decision_profile_policy.py |
| `628c5b6ef` | 2026-07-19 | feat: add Codex App Server agent prototype (#2004) | 48/69 (70%) | `design_needed` | session skill | apps/dsa-web/src/components/settings/AgentBackendStatusPanel.tsx, apps/dsa-web/src/components/settings/__tests__/AgentBackendStatusPanel.test.tsx, apps/dsa-web/src/hooks/__tests__/useStockIndex.test.tsx, … (+17) |
| `52e787a73` | 2026-07-19 | Update Anspire info (#2033) | 2/2 (100%) | `skip_docs` | docs | — |
| `e685751f1` | 2026-07-19 | docs: add v3.27.0 release changelog (#2041) | 1/1 (100%) | `skip_docs` | docs | — |
| `16e3421c1` | 2026-07-21 | fix: secure fork PR review workflow (#2057) | 5/6 (83%) | `record_trailer` | likely-absorbed | tests/test_ai_review_github_api.py |
| `8c22263f6` | 2026-07-22 | feat: persist skill opinion samples (#2058) | 13/14 (93%) | `record_trailer` | skill opinion | tests/test_skill_opinion_samples.py |
| `a54f46e1e` | 2026-07-22 | ci: temporarily disable automatic PR review (#2068) | 4/4 (100%) | `record_trailer` | likely-absorbed | — |
| `aa68d45d7` | 2026-07-23 | feat: add decision profile outcome calibration (#2072) | 19/21 (90%) | `record_trailer` | decision profile | tests/test_decision_signal_outcome_api.py, tests/test_decision_signal_outcome_service.py |
| `905c339d8` | 2026-07-26 | docs: add v3.28.0 release changelog | 1/1 (100%) | `skip_docs` | docs | — |
| `85ded1d70` | 2026-07-28 | feat: add skill opinion outcome evaluation core (#2116) | 6/10 (60%) | `port_now` | skill opinion | src/core/skill_opinion_outcome_evaluator.py, src/services/stock_daily_start_resolver.py, tests/test_backtest_service.py, … (+1) |
| `03bae035a` | 2026-07-30 | feat: add skill opinion outcome performance statistics (#2119) | 6/10 (60%) | `port_now` | skill opinion | src/services/stock_daily_start_resolver.py, tests/test_backtest_service.py, tests/test_skill_opinion_outcome_stats.py, … (+1) |
| `831ada537` | 2026-07-31 | feat: apply Bayesian skill outcome weights (#2123) | 12/16 (75%) | `record_trailer` | skill opinion | apps/dsa-web/src/locales/settingsHelp.test.ts, tests/test_skill_load_warning.py, tests/test_skill_opinion_outcome_stats.py, … (+1) |
| `bcb7ae4e1` | 2026-08-01 | feat: 将参考 AlphaSift 的选股实现纳入主项目 (#2136) | 43/89 (48%) | `manual_triage` | screening / alphasift | THIRD_PARTY_NOTICES.md, api/v1/endpoints/screening.py, apps/dsa-web/src/api/__tests__/screening.test.ts, … (+17) |
| `e430fcfe4` | 2026-08-02 | fix: 收敛选股排序、缓存与热点并发契约 (#2145) | 21/42 (50%) | `manual_triage` | screening / alphasift | api/v1/endpoints/screening.py, apps/dsa-web/src/api/__tests__/screening.test.ts, apps/dsa-web/src/api/screening.ts, … (+17) |
| `84ba462b0` | 2026-08-02 | docs: prepare v3.29.0 release | 1/1 (100%) | `skip_docs` | docs | — |
| `4dda5d714` | 2026-08-05 | feat: add explicit Responses API channel routing (#2157) | 25/34 (74%) | `manual_triage` | screening / alphasift | src/services/screening/config.py, src/services/screening/ranker.py, src/services/screening_service.py, … (+6) |
| `03dd26ac2` | 2026-08-05 | ci: shard backend tests across runners (#2165) | 6/8 (75%) | `record_trailer` | likely-absorbed | tests/test_ci_test_shard.py, tests/test_ci_workflow_contract.py |
| `ae19329d6` | 2026-08-05 | fix: stabilize watchlist details and workspace state (#2126) | 16/16 (100%) | `record_trailer` | likely-absorbed | — |
| `ed848da6f` | 2026-08-05 | feat: persist Agent Chat Skill selection by session (#2160) | 19/24 (79%) | `port_now` | session skill | src/agent/chat_executor.py, tests/test_agent_chat_api.py, tests/test_agent_chat_executor.py, … (+2) |
| `46d5bf347` | 2026-08-09 | fix: 恢复桌面端报告分享图 (#2169) | 11/15 (73%) | `port_now` | share image | src/share_image.py, tests/test_history_share_image.py, tests/test_md2img_template.py, … (+1) |
| `5698068fe` | 2026-08-09 | fix: split level-one headings without recursion (#2176) | 3/3 (100%) | `record_trailer` | likely-absorbed | — |
| `40b8c6c3c` | 2026-08-09 | fix: 修复首页移动端个股栏触摸滚动 (#2171) | 8/9 (89%) | `record_trailer` | likely-absorbed | apps/dsa-web/tests/home-mobile-scroll-styles.test.ts |
| `071c5aa3c` | 2026-08-09 | fix: stabilize Xiaohongshu share image caption (#2179) | 6/9 (67%) | `port_now` | share image | src/share_image.py, tests/test_md2img_template.py, tests/test_share_image.py |
| `396d43a4c` | 2026-08-09 | docs: prepare v3.30.0 release (#2180) | 1/1 (100%) | `skip_docs` | docs | — |
| `3b98aa1d7` | 2026-08-10 | docs: update AIHubMix referral links to InferEra (#2182) | 12/12 (100%) | `record_trailer` | likely-absorbed | — |

### Per-commit rationale (Attention)

#### `487e49e56` — feat: 支持保存决策风格重评估结果 (#2014)

- Date: `2026-07-16`
- Areas: `apps`, `tests`, `docs`, `src`, `api`
- Local path presence: **17/18** (94%)
- Suggested action: **`record_trailer`**
- Rationale: Most shared paths exist locally (ratio=94%); treat as already absorbed under cluster 'decision profile' and add Ported-from trailers after a quick semantic spot-check.
- Missing shared paths (sample):
  - `tests/test_decision_profile_policy.py`
- Present shared paths (sample):
  - `api/v1/endpoints/decision_signals.py`
  - `api/v1/schemas/decision_signals.py`
  - `apps/dsa-web/src/api/__tests__/decisionSignals.test.ts`
  - `apps/dsa-web/src/api/decisionSignals.ts`
  - `apps/dsa-web/src/i18n/uiText.ts`
  - `apps/dsa-web/src/pages/DecisionSignalsPage.tsx`

#### `628c5b6ef` — feat: add Codex App Server agent prototype (#2004)

- Date: `2026-07-19`
- Areas: `src`, `apps`, `tests`, `docs`, `api`, `env.example`
- Local path presence: **48/69** (70%)
- Suggested action: **`design_needed`**
- Rationale: Touches a large product prototype (e.g. Codex App Server); needs a design issue before any port.
- Missing shared paths (sample):
  - `apps/dsa-web/src/components/settings/AgentBackendStatusPanel.tsx`
  - `apps/dsa-web/src/components/settings/__tests__/AgentBackendStatusPanel.test.tsx`
  - `apps/dsa-web/src/hooks/__tests__/useStockIndex.test.tsx`
  - `scripts/codex_app_server_gate_a.py`
  - `src/agent/agent_backend.py`
  - `src/agent/chat_executor.py`
  - `src/agent/codex_agent_backend.py`
  - `src/agent/codex_app_server_transport.py`
  - `src/agent/codex_tool_process.py`
  - `src/services/agent_backend_status_service.py`
- Present shared paths (sample):
  - `.env.example`
  - `api/v1/endpoints/agent.py`
  - `api/v1/endpoints/system_config.py`
  - `api/v1/schemas/system_config.py`
  - `apps/dsa-web/src/api/__tests__/agent.test.ts`
  - `apps/dsa-web/src/api/__tests__/systemConfig.test.ts`

#### `52e787a73` — Update Anspire info (#2033)

- Date: `2026-07-19`
- Areas: `README.md`, `docs`
- Local path presence: **2/2** (100%)
- Suggested action: **`skip_docs`**
- Rationale: Shared paths are documentation or marketing only.
- Present shared paths (sample):
  - `README.md`
  - `docs/assets/anspire.png`

#### `e685751f1` — docs: add v3.27.0 release changelog (#2041)

- Date: `2026-07-19`
- Areas: `docs`
- Local path presence: **1/1** (100%)
- Suggested action: **`skip_docs`**
- Rationale: Docs/changelog-only surface; do not port upstream release notes as-is.
- Present shared paths (sample):
  - `docs/CHANGELOG.md`

#### `16e3421c1` — fix: secure fork PR review workflow (#2057)

- Date: `2026-07-21`
- Areas: `docs`, `github`, `tests`
- Local path presence: **5/6** (83%)
- Suggested action: **`record_trailer`**
- Rationale: Most shared paths exist locally (ratio=83%); spot-check behavior, then record Ported-from trailers.
- Missing shared paths (sample):
  - `tests/test_ai_review_github_api.py`
- Present shared paths (sample):
  - `.github/scripts/ai_review.py`
  - `.github/workflows/pr-review.yml`
  - `docs/CHANGELOG.md`
  - `docs/CONTRIBUTING.md`
  - `docs/CONTRIBUTING_EN.md`

#### `8c22263f6` — feat: persist skill opinion samples (#2058)

- Date: `2026-07-22`
- Areas: `src`, `tests`, `docs`
- Local path presence: **13/14** (93%)
- Suggested action: **`record_trailer`**
- Rationale: Most shared paths exist locally (ratio=93%); treat as already absorbed under cluster 'skill opinion' and add Ported-from trailers after a quick semantic spot-check.
- Missing shared paths (sample):
  - `tests/test_skill_opinion_samples.py`
- Present shared paths (sample):
  - `docs/CHANGELOG.md`
  - `docs/multi-strategy-contract.md`
  - `src/agent/protocols.py`
  - `src/agent/runtime_facts.py`
  - `src/agent/skills/engine.py`
  - `src/agent/skills/skill_agent.py`

#### `a54f46e1e` — ci: temporarily disable automatic PR review (#2068)

- Date: `2026-07-22`
- Areas: `docs`, `github`
- Local path presence: **4/4** (100%)
- Suggested action: **`record_trailer`**
- Rationale: Most shared paths exist locally (ratio=100%); spot-check behavior, then record Ported-from trailers.
- Present shared paths (sample):
  - `.github/workflows/pr-review.yml`
  - `docs/CHANGELOG.md`
  - `docs/CONTRIBUTING.md`
  - `docs/CONTRIBUTING_EN.md`

#### `aa68d45d7` — feat: add decision profile outcome calibration (#2072)

- Date: `2026-07-23`
- Areas: `apps`, `docs`, `tests`, `api`, `src`
- Local path presence: **19/21** (90%)
- Suggested action: **`record_trailer`**
- Rationale: Most shared paths exist locally (ratio=90%); treat as already absorbed under cluster 'decision profile' and add Ported-from trailers after a quick semantic spot-check.
- Missing shared paths (sample):
  - `tests/test_decision_signal_outcome_api.py`
  - `tests/test_decision_signal_outcome_service.py`
- Present shared paths (sample):
  - `api/v1/schemas/__init__.py`
  - `api/v1/schemas/decision_signals.py`
  - `apps/dsa-web/src/api/__tests__/decisionSignals.test.ts`
  - `apps/dsa-web/src/api/decisionSignals.ts`
  - `apps/dsa-web/src/components/decision-signals/DecisionSignalProfileCalibration.tsx`
  - `apps/dsa-web/src/components/decision-signals/__tests__/DecisionSignalProfileCalibration.test.tsx`

#### `905c339d8` — docs: add v3.28.0 release changelog

- Date: `2026-07-26`
- Areas: `docs`
- Local path presence: **1/1** (100%)
- Suggested action: **`skip_docs`**
- Rationale: Docs/changelog-only surface; do not port upstream release notes as-is.
- Present shared paths (sample):
  - `docs/CHANGELOG.md`

#### `85ded1d70` — feat: add skill opinion outcome evaluation core (#2116)

- Date: `2026-07-28`
- Areas: `src`, `docs`, `tests`
- Local path presence: **6/10** (60%)
- Suggested action: **`port_now`**
- Rationale: Small residual shared-code gap against an otherwise present surface; prefer a focused port with regression tests.
- Missing shared paths (sample):
  - `src/core/skill_opinion_outcome_evaluator.py`
  - `src/services/stock_daily_start_resolver.py`
  - `tests/test_backtest_service.py`
  - `tests/test_skill_opinion_outcomes.py`
- Present shared paths (sample):
  - `docs/CHANGELOG.md`
  - `docs/multi-strategy-contract.md`
  - `src/repositories/skill_opinion_outcome_repo.py`
  - `src/services/backtest_service.py`
  - `src/services/skill_opinion_outcome_service.py`
  - `src/storage.py`

#### `03bae035a` — feat: add skill opinion outcome performance statistics (#2119)

- Date: `2026-07-30`
- Areas: `src`, `tests`, `docs`
- Local path presence: **6/10** (60%)
- Suggested action: **`port_now`**
- Rationale: Small residual shared-code gap against an otherwise present surface; prefer a focused port with regression tests.
- Missing shared paths (sample):
  - `src/services/stock_daily_start_resolver.py`
  - `tests/test_backtest_service.py`
  - `tests/test_skill_opinion_outcome_stats.py`
  - `tests/test_skill_opinion_outcomes.py`
- Present shared paths (sample):
  - `docs/CHANGELOG.md`
  - `docs/multi-strategy-contract.md`
  - `src/repositories/skill_opinion_outcome_repo.py`
  - `src/services/backtest_service.py`
  - `src/services/skill_opinion_outcome_service.py`
  - `src/services/skill_opinion_performance_service.py`

#### `831ada537` — feat: apply Bayesian skill outcome weights (#2123)

- Date: `2026-07-31`
- Areas: `src`, `tests`, `apps`, `docs`, `env.example`
- Local path presence: **12/16** (75%)
- Suggested action: **`record_trailer`**
- Rationale: Most shared paths exist locally (ratio=75%); treat as already absorbed under cluster 'skill opinion' and add Ported-from trailers after a quick semantic spot-check.
- Missing shared paths (sample):
  - `apps/dsa-web/src/locales/settingsHelp.test.ts`
  - `tests/test_skill_load_warning.py`
  - `tests/test_skill_opinion_outcome_stats.py`
  - `tests/test_skill_opinion_weights.py`
- Present shared paths (sample):
  - `.env.example`
  - `apps/dsa-web/src/locales/settingsHelp.ts`
  - `apps/dsa-web/src/utils/systemConfigI18n.ts`
  - `docs/CHANGELOG.md`
  - `docs/multi-strategy-contract.md`
  - `src/agent/skills/aggregator.py`

#### `bcb7ae4e1` — feat: 将参考 AlphaSift 的选股实现纳入主项目 (#2136)

- Date: `2026-08-01`
- Areas: `src`, `apps`, `tests`, `docs`, `api`, `scripts`
- Local path presence: **43/89** (48%)
- Suggested action: **`manual_triage`**
- Rationale: Path presence is mixed; maintainer must classify Port / Design / Skip.
- Missing shared paths (sample):
  - `THIRD_PARTY_NOTICES.md`
  - `api/v1/endpoints/screening.py`
  - `apps/dsa-web/src/api/__tests__/screening.test.ts`
  - `apps/dsa-web/src/api/screening.ts`
  - `docs/screening-engine.md`
  - `src/services/screening/LICENSE`
  - `src/services/screening/__init__.py`
  - `src/services/screening/candidate_context.py`
  - `src/services/screening/config.py`
  - `src/services/screening/context.py`
- Present shared paths (sample):
  - `.env.example`
  - `README.md`
  - `api/v1/endpoints/__init__.py`
  - `api/v1/endpoints/alphasift.py`
  - `api/v1/router.py`
  - `apps/dsa-web/src/api/__tests__/alphasift.test.ts`

#### `e430fcfe4` — fix: 收敛选股排序、缓存与热点并发契约 (#2145)

- Date: `2026-08-02`
- Areas: `src`, `docs`, `apps`, `tests`, `env.example`, `README.md`
- Local path presence: **21/42** (50%)
- Suggested action: **`manual_triage`**
- Rationale: Path presence is mixed; maintainer must classify Port / Design / Skip.
- Missing shared paths (sample):
  - `api/v1/endpoints/screening.py`
  - `apps/dsa-web/src/api/__tests__/screening.test.ts`
  - `apps/dsa-web/src/api/screening.ts`
  - `docs/screening-engine.md`
  - `src/services/screening/config.py`
  - `src/services/screening/daily.py`
  - `src/services/screening/dsa.py`
  - `src/services/screening/hotspot.py`
  - `src/services/screening/models.py`
  - `src/services/screening/pipeline.py`
- Present shared paths (sample):
  - `.env.example`
  - `README.md`
  - `apps/dsa-web/src/api/error.ts`
  - `apps/dsa-web/src/components/common/Select.tsx`
  - `apps/dsa-web/src/i18n/uiText.ts`
  - `apps/dsa-web/src/locales/settingsHelp.ts`

#### `84ba462b0` — docs: prepare v3.29.0 release

- Date: `2026-08-02`
- Areas: `docs`
- Local path presence: **1/1** (100%)
- Suggested action: **`skip_docs`**
- Rationale: Docs/changelog-only surface; do not port upstream release notes as-is.
- Present shared paths (sample):
  - `docs/CHANGELOG.md`

#### `4dda5d714` — feat: add explicit Responses API channel routing (#2157)

- Date: `2026-08-05`
- Areas: `apps`, `tests`, `src`, `docs`, `api`, `env.example`
- Local path presence: **25/34** (74%)
- Suggested action: **`manual_triage`**
- Rationale: Path presence is mixed; maintainer must classify Port / Design / Skip.
- Missing shared paths (sample):
  - `src/services/screening/config.py`
  - `src/services/screening/ranker.py`
  - `src/services/screening_service.py`
  - `tests/test_generation_backend_status_service.py`
  - `tests/test_image_stock_extractor_litellm.py`
  - `tests/test_llm_channel_config.py`
  - `tests/test_screening_api.py`
  - `tests/test_screening_ranker.py`
  - `tests/test_system_config_service.py`
- Present shared paths (sample):
  - `.env.example`
  - `.github/workflows/00-daily-analysis.yml`
  - `api/v1/endpoints/system_config.py`
  - `api/v1/schemas/system_config.py`
  - `apps/dsa-web/src/api/__tests__/systemConfig.test.ts`
  - `apps/dsa-web/src/api/systemConfig.ts`

#### `03dd26ac2` — ci: shard backend tests across runners (#2165)

- Date: `2026-08-05`
- Areas: `tests`, `github`, `scripts`, `docs`
- Local path presence: **6/8** (75%)
- Suggested action: **`record_trailer`**
- Rationale: Most shared paths exist locally (ratio=75%); spot-check behavior, then record Ported-from trailers.
- Missing shared paths (sample):
  - `tests/test_ci_test_shard.py`
  - `tests/test_ci_workflow_contract.py`
- Present shared paths (sample):
  - `.github/ci-test-durations.json`
  - `.github/workflows/ci.yml`
  - `docs/CHANGELOG.md`
  - `scripts/ci_gate.sh`
  - `scripts/ci_test_shard.py`
  - `tests/test_futu_distribution_contract.py`

#### `ae19329d6` — fix: stabilize watchlist details and workspace state (#2126)

- Date: `2026-08-05`
- Areas: `apps`, `docs`, `gitignore`
- Local path presence: **16/16** (100%)
- Suggested action: **`record_trailer`**
- Rationale: Most shared paths exist locally (ratio=100%); spot-check behavior, then record Ported-from trailers.
- Present shared paths (sample):
  - `.gitignore`
  - `apps/dsa-web/src/api/history.ts`
  - `apps/dsa-web/src/components/tasks/TaskPanel.tsx`
  - `apps/dsa-web/src/components/tasks/__tests__/TaskPanel.test.tsx`
  - `apps/dsa-web/src/components/watchlist/HomeStockWorkspace.tsx`
  - `apps/dsa-web/src/components/watchlist/__tests__/HomeStockWorkspace.test.tsx`

#### `ed848da6f` — feat: persist Agent Chat Skill selection by session (#2160)

- Date: `2026-08-05`
- Areas: `tests`, `apps`, `src`, `docs`, `api`
- Local path presence: **19/24** (79%)
- Suggested action: **`port_now`**
- Rationale: Small residual shared-code gap against an otherwise present surface; prefer a focused port with regression tests.
- Missing shared paths (sample):
  - `src/agent/chat_executor.py`
  - `tests/test_agent_chat_api.py`
  - `tests/test_agent_chat_executor.py`
  - `tests/test_agent_models_api.py`
  - `tests/test_conversation_manager.py`
- Present shared paths (sample):
  - `api/deps.py`
  - `api/v1/endpoints/agent.py`
  - `apps/dsa-web/src/api/__tests__/agent.test.ts`
  - `apps/dsa-web/src/api/agent.ts`
  - `apps/dsa-web/src/pages/ChatPage.tsx`
  - `apps/dsa-web/src/pages/__tests__/ChatPage.test.tsx`

#### `46d5bf347` — fix: 恢复桌面端报告分享图 (#2169)

- Date: `2026-08-09`
- Areas: `docs`, `tests`, `apps`, `src`, `env.example`, `api`
- Local path presence: **11/15** (73%)
- Suggested action: **`port_now`**
- Rationale: Small residual shared-code gap against an otherwise present surface; prefer a focused port with regression tests.
- Missing shared paths (sample):
  - `src/share_image.py`
  - `tests/test_history_share_image.py`
  - `tests/test_md2img_template.py`
  - `tests/test_share_image.py`
- Present shared paths (sample):
  - `.env.example`
  - `api/v1/endpoints/history.py`
  - `apps/dsa-web/src/components/report/ShareImageButton.tsx`
  - `apps/dsa-web/src/components/report/__tests__/ShareImageButton.test.tsx`
  - `docs/CHANGELOG.md`
  - `docs/desktop-package.md`

#### `5698068fe` — fix: split level-one headings without recursion (#2176)

- Date: `2026-08-09`
- Areas: `docs`, `src`, `tests`
- Local path presence: **3/3** (100%)
- Suggested action: **`record_trailer`**
- Rationale: Most shared paths exist locally (ratio=100%); spot-check behavior, then record Ported-from trailers.
- Present shared paths (sample):
  - `docs/CHANGELOG.md`
  - `src/formatters.py`
  - `tests/test_formatters.py`

#### `40b8c6c3c` — fix: 修复首页移动端个股栏触摸滚动 (#2171)

- Date: `2026-08-09`
- Areas: `apps`, `docs`
- Local path presence: **8/9** (89%)
- Suggested action: **`record_trailer`**
- Rationale: Most shared paths exist locally (ratio=89%); spot-check behavior, then record Ported-from trailers.
- Missing shared paths (sample):
  - `apps/dsa-web/tests/home-mobile-scroll-styles.test.ts`
- Present shared paths (sample):
  - `apps/dsa-web/src/components/history/StockBar.tsx`
  - `apps/dsa-web/src/components/watchlist/HomeStockWorkspace.tsx`
  - `apps/dsa-web/src/components/watchlist/__tests__/HomeStockWorkspace.test.tsx`
  - `apps/dsa-web/src/index.css`
  - `apps/dsa-web/src/pages/HomePage.tsx`
  - `docs/CHANGELOG.md`

#### `071c5aa3c` — fix: stabilize Xiaohongshu share image caption (#2179)

- Date: `2026-08-09`
- Areas: `docs`, `tests`, `env.example`, `src`
- Local path presence: **6/9** (67%)
- Suggested action: **`port_now`**
- Rationale: Small residual shared-code gap against an otherwise present surface; prefer a focused port with regression tests.
- Missing shared paths (sample):
  - `src/share_image.py`
  - `tests/test_md2img_template.py`
  - `tests/test_share_image.py`
- Present shared paths (sample):
  - `.env.example`
  - `docs/CHANGELOG.md`
  - `docs/full-guide.md`
  - `docs/full-guide_EN.md`
  - `docs/notifications.md`
  - `docs/share-images.md`

#### `396d43a4c` — docs: prepare v3.30.0 release (#2180)

- Date: `2026-08-09`
- Areas: `docs`
- Local path presence: **1/1** (100%)
- Suggested action: **`skip_docs`**
- Rationale: Docs/changelog-only surface; do not port upstream release notes as-is.
- Present shared paths (sample):
  - `docs/CHANGELOG.md`

#### `3b98aa1d7` — docs: update AIHubMix referral links to InferEra (#2182)

- Date: `2026-08-10`
- Areas: `docs`, `apps`, `env.example`, `README.md`, `src`, `tests`
- Local path presence: **12/12** (100%)
- Suggested action: **`record_trailer`**
- Rationale: Most shared paths exist locally (ratio=100%); spot-check behavior, then record Ported-from trailers.
- Present shared paths (sample):
  - `.env.example`
  - `README.md`
  - `apps/dsa-web/src/components/settings/__tests__/llmProviderTemplates.test.ts`
  - `apps/dsa-web/src/components/settings/llmProviderTemplates.ts`
  - `docs/CHANGELOG.md`
  - `docs/README_CHT.md`

## Governance cadence (who / when)

- **Machine report:** Weekly Monday 04:00 UTC via `.github/workflows/upstream-parity.yml` (plus workflow_dispatch). Updates tracking issue #1002 in place.
- **Human triage:** Within a few days of each #1002 refresh: triage Attention using this inventory; open or update child issues; never half-port entangled clusters.
- **After ports:** After port PRs land: re-run this script and `scripts/check_upstream_parity.py` so Attention shrinks.

### Consumers

- Maintainers triaging #1002 (upstream-parity tracking issue)
- Issue #1061 cadence owners (Port now / DESIGN-NEEDED / Whitelist)
- Port PR authors who need a prioritized residual-gap list

### Recommended run frequency

1. **Weekly** (or on each `upstream-parity` workflow run): generate this inventory after #1002 refreshes.
2. **On demand** before planning a port wave: re-run with `--fetch` to pick up new upstream commits.
3. **After merge of port PRs**: re-run to confirm Attention shrinks and trailers match.

## Notes and limits

- Path presence is a heuristic, not semantic equivalence. Fork-native renames (e.g. screening → alphasift, share_image package) can show missing upstream paths while behavior is already absorbed.
- Suggested actions never replace maintainer judgment for foundation ports.
- Record Ported-from: ZhuLinsen/daily_stock_analysis@<sha> only after a semantic spot-check confirms the intent is covered.

## Local commands

```bash
python scripts/check_upstream_parity.py --self-test
python scripts/inventory_upstream_drift.py --self-test
python scripts/inventory_upstream_drift.py \
  --fetch \
  --local-ref origin/main \
  --upstream-ref upstream/main \
  --output /tmp/upstream-drift-inventory.md
```

Related docs: [Upstream Parity Checker](../upstream-parity.md), tracking issue #1002, cadence issue #1061.


## Human residual findings (this run)

Automated path presence can miss behavioral gaps and fork-native renames. Spot-checks on `origin/main` for this inventory:

| Upstream SHA | Inventory action | Human residual | Track as |
| --- | --- | --- | --- |
| `5698068fe` | record_trailer (100% paths) | **Bug still present:** `_chunk_by_separators` detects `\n# ` but still splits on `\n## ` | Child issue: port H1 heading split fix |
| `628c5b6ef` | design_needed | Codex App Server modules absent (`src/agent/codex_*`, gate script) | Child design issue |
| `3b98aa1d7` | record_trailer | StockPulse still documents AIHubMix; InferEra referral rename not applied | Child docs/chore issue or skip as product choice |
| `85ded1d70` / `03bae035a` / `831ada537` | port_now / record_trailer | Fork-native skill-opinion outcome path exists (`src/services/skill_opinion_*`, schemas); missing upstream file names are often renames | Record trailers after spot-check; do not dual-implement evaluator |
| `bcb7ae4e1` / `e430fcfe4` | manual_triage | Screening lives under AlphaSift (`api/v1/endpoints/alphasift.py`, `src/services/alphasift_service.py`); upstream `screening/` layout not mirrored | Register on #325 / prior ports; record trailers for absorbed SHAs |
| `46d5bf347` / `071c5aa3c` | port_now | Share image is a package (`src/share_image/`), not `src/share_image.py` | Record trailers after caption spot-check |
| `ed848da6f` | port_now | Session skill persistence largely present via `agent_chat_session_service` / ChatPage; `chat_executor.py` name is upstream-only | Record trailer after spot-check (related merged port wave) |
| docs-only changelogs | skip_docs | Do not mirror upstream release notes | No child issue |

### Child issues opened from this inventory

| Issue | Kind | Upstream SHAs / topic |
| --- | --- | --- |
| #1219 | Port now | `5698068fe` H1 heading chunk split bug still present |
| #1220 | DESIGN-NEEDED | `628c5b6ef` Codex App Server prototype |
| #1221 | Record trailers | Already-absorbed Attention SHAs + fork-native renames spot-check |
| #1222 | Docs / product | `3b98aa1d7` AIHubMix → InferEra referral decision |

Also registered: screening/AlphaSift path divergence remains under existing #325 (and prior ports); multi-strategy design remains #805.

