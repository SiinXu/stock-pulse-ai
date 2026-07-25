"""Documentation guards for the scheduled-task runtime contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scheduled_task_topic_is_indexed_and_documents_runtime_boundaries() -> None:
    topic = (ROOT / "docs" / "scheduled-tasks.md").read_text(encoding="utf-8")
    adr = (
        ROOT / "docs" / "adr" / "ADR-004-process-local-task-execution-authority.md"
    ).read_text(encoding="utf-8")
    schedule_adr = (
        ROOT
        / "docs"
        / "adr"
        / "ADR-008-persisted-schedule-process-local-execution-boundary.md"
    ).read_text(encoding="utf-8")
    architecture = (ROOT / "docs" / "architecture-overview.md").read_text(
        encoding="utf-8"
    )
    index = (ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
    index_en = (ROOT / "docs" / "INDEX_EN.md").read_text(encoding="utf-8")

    assert "scheduled-tasks.md" in index
    assert "scheduled-tasks.md" in index_en
    for required in (
        "AnalysisTaskQueue ->\nAnalysisService",
        "non_trading_day_policy",
        "202607240002_scheduled_task_schema",
        "python main.py --schedule",
        "python main.py --serve-only",
        "process-local",
        "interrupted",
        "classify_market_session",
        "scheduled_task_calendar_unavailable",
        "complete execution contract",
        "unsupported_schema",
        "exchange timezone",
        "fall-back fold",
        "append-only audit history",
        "DSA_DESKTOP_MODE=true",
        "scheduled_task_runtime_reconcile_deferred",
        "expected schema version",
        "after disable is interrupted",
        "SCHEDULE_ENABLED` settings may still start or rebuild",
        "earliest valid UTC instant",
        "execution generation",
        "BEGIN IMMEDIATE",
        "dispatch_failure_count",
        "notification_failed_channels",
        "does not change the occurrence from `succeeded`",
        "research_brief",
        "risk_check",
        "persona_tail_risk",
        "/scheduled-tasks/today?timezone=<IANA>",
        "23 or",
        "25 UTC hours",
        "adds no database migration or configuration",
        "schema-v2 definitions as opaque unsupported records",
        "effective canonical Agent skill catalog",
        "never replays the old",
        "Each item is isolated",
    ):
        assert required in topic
    assert "both valid UTC instants are eligible" not in topic
    assert "amended by [ADR-008]" in adr
    assert "occurrence/audit projection" in schedule_adr
    assert "Amends: [ADR-004]" in schedule_adr
    assert "at most once per schedule-local date" in schedule_adr
    assert "never replays the whole analysis" in schedule_adr
    assert "next future occurrence" in schedule_adr
    assert "structural-corruption quarantine" in schedule_adr
    assert "ScheduledTaskService.tick()" in architecture


def test_bilingual_migration_docs_publish_new_registry_target() -> None:
    for filename in ("database-migrations.md", "database-migrations_EN.md"):
        content = (ROOT / "docs" / filename).read_text(encoding="utf-8")
        assert "202607240002_scheduled_task_schema" in content
        assert "SCHEDULED_TASK_SCHEMA_VERSION" in content
        assert "opaque" in content
