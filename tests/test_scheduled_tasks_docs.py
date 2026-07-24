"""Documentation guards for the scheduled-task runtime contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_scheduled_task_topic_is_indexed_and_documents_runtime_boundaries() -> None:
    topic = (ROOT / "docs" / "scheduled-tasks.md").read_text(encoding="utf-8")
    index = (ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
    index_en = (ROOT / "docs" / "INDEX_EN.md").read_text(encoding="utf-8")

    assert "scheduled-tasks.md" in index
    assert "scheduled-tasks.md" in index_en
    for required in (
        "AnalysisTaskQueue ->\nAnalysisService",
        "non_trading_day_policy",
        "202607240001_scheduled_task_schema",
        "python main.py --schedule",
        "python main.py --serve-only",
        "process-local",
        "interrupted",
    ):
        assert required in topic


def test_bilingual_migration_docs_publish_new_registry_target() -> None:
    for filename in ("database-migrations.md", "database-migrations_EN.md"):
        content = (ROOT / "docs" / filename).read_text(encoding="utf-8")
        assert "202607240001_scheduled_task_schema" in content
        assert "SCHEDULED_TASK_SCHEMA_VERSION" in content
