"""Documentation contract for the personal investment framework backend."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_framework_topic_documents_api_scope_context_and_rollback() -> None:
    chinese = _read("docs/personal-investment-framework.md")
    english = _read("docs/personal-investment-framework_EN.md")

    for document in (chinese, english):
        for path in (
            "/api/v1/investment-framework",
            "/api/v1/investment-framework/history",
            "/api/v1/investment-framework/deactivate",
        ):
            assert path in document
        assert "202607240002_investment_framework_schema" in document
        assert "InvestmentFrameworkContextReader" in document
        assert "expected_revision" in document
        assert "schema_migrations" in document
        assert "prompt" in document.lower()


def test_framework_docs_are_discoverable_without_expanding_readmes() -> None:
    index = _read("docs/INDEX.md")
    index_en = _read("docs/INDEX_EN.md")
    changelog = _read("docs/CHANGELOG.md")

    assert "[个人投资框架后端合同](personal-investment-framework.md)" in index
    assert (
        "[Personal Investment Framework Backend Contract]"
        "(personal-investment-framework_EN.md)"
    ) in index_en
    assert "versioned local personal investment framework backend" in changelog
