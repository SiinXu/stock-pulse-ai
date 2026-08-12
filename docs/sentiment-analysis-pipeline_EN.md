# Sentiment Analysis Pipeline (Issue #179)

English mirror of [sentiment-analysis-pipeline.md](sentiment-analysis-pipeline.md).
Keep both versions in sync when the contract changes.

First-class **news/event sentiment evidence** for symbols. Sentiment is a
structured supporting signal for AnalysisContextPack and audit snapshots, not a
trading conclusion and not a replacement for model decision outputs.

## Scope

**In scope (this version):**

- Deterministic scoring from already-fetched intelligence artifacts
- Stable `sentiment-snapshot-v1` schema with score, label, confidence, source
  coverage, freshness, evidence snippets, and explicit degradation codes
- Runtime attachment as AnalysisContextPack block `sentiment` (`role=evidence`)
- Persistence of `sentiment_snapshot` inside `analysis_history.context_snapshot`
  when context snapshots are saved

**Out of scope (follow-up):** new ungoverned external sources; replacing LLM
`sentiment_score` report fields; automatic watchlist/alerts/daily-brief
re-ranking; sector aggregate product surfaces.

## Hard boundary: no ungoverned sources

The pipeline does **not** open new outbound providers. It only scores artifacts
the analysis path already owns under existing `NEWS_*` / search / local
intelligence configuration. Adding a new external sentiment vendor requires the
repository provider/plugin contract process.

## Schema and runtime

See the Chinese topic doc for field tables, reason codes, wiring steps, method
notes (`news_lexicon_v1`), verification commands, and rollback. Source anchors:

- `src/schemas/sentiment_snapshot.py`
- `src/services/sentiment_pipeline_service.py`
- `src/services/analysis_context_builder.py` (`sentiment` block)
- `src/core/stages/analysis_stock.py` / `analysis_agent.py` / `persistence.py`
