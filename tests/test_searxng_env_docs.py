from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_env_example_documents_searxng_actions_variable_mapping() -> None:
    env_example = (ROOT_DIR / ".env.example").read_text(encoding="utf-8")

    start = env_example.index("# SearXNG 实例地址")
    end = env_example.index("SEARXNG_PUBLIC_INSTANCES_ENABLED=true", start)
    searxng_block = env_example[start:end]

    assert "GitHub Actions" in searxng_block
    assert "Variables 优先" in searxng_block
    assert "Secrets" in searxng_block
    assert "需配置为 Secret" not in searxng_block


def test_daily_analysis_workflow_matches_documented_searxng_variable_mapping() -> None:
    workflow = (
        ROOT_DIR / ".github" / "workflows" / "00-daily-analysis.yml"
    ).read_text(encoding="utf-8")

    assert (
        "SEARXNG_BASE_URLS: ${{ vars.SEARXNG_BASE_URLS || secrets.SEARXNG_BASE_URLS }}"
        in workflow
    )
    assert "SEARXNG_BASE_URLS: ${{ secrets.SEARXNG_BASE_URLS }}" not in workflow


def test_changelog_mentions_searxng_actions_variable_mapping() -> None:
    changelog = (ROOT_DIR / "docs" / "CHANGELOG.md").read_text(encoding="utf-8")

    assert (
        "- [Fixed] GitHub Actions daily analysis workflow supports Variables priority "
        "and Secrets fallback when reading SearXNG self-hosted instance address; "
        "fixes the issue of URL not working when only Variables are configured."
    ) in changelog
