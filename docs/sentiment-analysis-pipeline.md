# Sentiment Analysis Pipeline (Issue #179)

First-class **news/event sentiment evidence** for symbols. Sentiment is a
structured supporting signal for AnalysisContextPack and audit snapshots, not a
trading conclusion and not a replacement for model decision outputs.

## Scope

**In scope (this version):**

- Deterministic scoring from already-fetched intelligence artifacts:
  - multi-dimensional `SearchService.search_comprehensive_intel` results
  - optional free-text `news_context` fallback
  - optional local intelligence pool items when provided to the service
- Stable `sentiment-snapshot-v1` schema with:
  - score (0–100) / label / confidence
  - source coverage rows (traceable)
  - freshness (`fresh` / `aging` / `stale` / `unknown`)
  - evidence snippets with `as_of` when available
  - explicit degradation reason codes
- Runtime attachment as AnalysisContextPack block `sentiment` (role=`evidence`)
- Persistence of `sentiment_snapshot` inside `analysis_history.context_snapshot`
  when context snapshots are saved

**Out of scope (follow-up):**

- New ungoverned external social/news APIs
- Replacing LLM `sentiment_score` report field semantics
- Automatic re-ranking of watchlist / alerts / daily brief (consumers can read
  the stable schema later)
- Sector-level aggregate snapshots as a separate product surface

## Hard boundary: no ungoverned sources

The pipeline **does not** open new outbound providers. It only scores artifacts
the analysis path already owns under existing `NEWS_*` / search / local
intelligence configuration. Optional US `SocialSentimentService` remains an
existing opt-in path that still injects text into `news_context`; this pipeline
does not add a second social network.

To add a new external sentiment vendor, use the repository provider/plugin
contract process separately.

## Schema

`src/schemas/sentiment_snapshot.py` defines `SentimentSnapshot`
(`schema_version=sentiment-snapshot-v1`):

| Field | Meaning |
| --- | --- |
| `role` | Always `evidence` (not a conclusion) |
| `status` / `degraded` / `reason_code` | `available`, `degraded`, or `unavailable` with a stable reason |
| `score` / `label` | Optional 0–100 score and `bullish` / `bearish` / `neutral` / `mixed` / `unclear` |
| `confidence` / `confidence_basis` | 0–1 confidence plus short basis string |
| `freshness` / `freshness_as_of` | Evidence recency grading and newest dated stamp |
| `sources[]` | Source family coverage (`news_search`, `local_intel`, …) |
| `evidence[]` | Capped snippets with source id, optional link, polarity, timestamps |
| `gaps[]` | Explicit missing/partial reasons |
| `method` | `news_lexicon_v1` |
| `disclaimer` | Mandatory non-authority statement |

Unavailable results set `score=None` and `confidence=None` (never invent a
neutral 50 when there is no evidence).

### Reason codes

| Code | When |
| --- | --- |
| `ok` | Usable score with full coverage |
| `partial_coverage` | Some dimensions/sources missing or failed |
| `news_source_unavailable` | Search/news path not available |
| `no_data` | Sources available but no scorable items |
| `stale_evidence` | Dated evidence outside freshness window |
| `unknown_freshness` | Missing publish timestamps |
| `low_signal` | Weak or conflicting lexicon signal |
| `scoring_failed` | Fail-open exception path |

## Runtime wiring

1. Ordinary analysis (`src/core/stages/analysis_stock.py`) builds a snapshot
   after intelligence search using structured `intel_results` plus any combined
   `news_context`.
2. Agent analysis (`src/core/stages/analysis_agent.py`) builds from
   `news_context` only (Agent path does not always re-run multi-dimensional
   search).
3. `PipelineAnalysisArtifacts.sentiment_snapshot` carries the public dict into
   `AnalysisContextBuilder`.
4. Builder maps it to auxiliary block `sentiment` with
   `metadata.role=evidence`, `quality_weighted=false` (does not reweight core
   data-quality scores).
5. Context snapshot stores `sentiment_snapshot` for audit when
   `SAVE_CONTEXT_SNAPSHOT` keeps history snapshots.

Failures in the sentiment step are fail-open: analysis continues, and the
snapshot records `scoring_failed` / `unavailable`.

## Method notes (`news_lexicon_v1`)

- Bilingual bullish/bearish lexicon over title + snippet text
- Dimension weights (announcements / risk slightly higher than industry)
- Recency weights from `published_date` / `published_at`
- Aggregate polarity → score in 0–100; label from score and polarity mix
- Confidence from signal strength, dated coverage, and item volume

This is intentionally transparent and offline-testable. It is **not** a claim
of institutional-grade NLP accuracy.

## Downstream consumption

Stable entry points:

- `SentimentPipelineService.build_from_intel_results(...)`
- `SentimentPipelineService.build_from_news_context(...)`
- `SentimentSnapshot.to_public_dict()`
- AnalysisContextPack block `sentiment`
- `context_snapshot["sentiment_snapshot"]`

Screening, alerts, daily brief, and agent tools can consume the same schema in
later issues without changing this contract.

## Verification

```bash
python -m py_compile \
  src/schemas/sentiment_snapshot.py \
  src/services/sentiment_pipeline_service.py \
  src/services/analysis_context_builder.py \
  src/core/stages/analysis_stock.py \
  src/core/stages/analysis_agent.py \
  src/core/stages/persistence.py

python -m pytest \
  tests/schemas/test_sentiment_snapshot.py \
  tests/services/test_sentiment_pipeline_service.py \
  tests/services/test_analysis_context_builder.py \
  -q
```

## Rollback

Revert the Issue #179 PR. There is no database migration and no new required
configuration key. Historical records without `sentiment_snapshot` remain valid.
## CI note

Pipeline facade binding requires `SentimentPipelineService` imports on both `src.core.stages.analysis` and `src.core.pipeline` because stage methods are rebound onto those module globals.

