from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def test_env_example_documents_searxng_actions_variable_mapping() -> None:
    env_example = (ROOT_DIR / ".env.example").read_text(encoding="utf-8")

    start = env_example.index("# SearXNG instance address")
    end = env_example.index("SEARXNG_PUBLIC_INSTANCES_ENABLED=", start)
    searxng_block = env_example[start:end]

    assert "GitHub Actions" in searxng_block
    assert "Variables take priority" in searxng_block
    assert "Secrets provide the fallback" in searxng_block
    assert "must be configured as a Secret" not in searxng_block


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


def test_env_example_defaults_public_searxng_instances_off() -> None:
    env_example = (ROOT_DIR / ".env.example").read_text(encoding="utf-8")

    assert "SEARXNG_PUBLIC_INSTANCES_ENABLED=false" in env_example
    assert "SEARXNG_PUBLIC_INSTANCES_ENABLED=true" not in env_example


def test_runtime_default_disables_public_searxng_instances(monkeypatch) -> None:
    """Unset env must resolve to off; editing .env.example alone is not enough."""
    import os

    from src.config_parts.parsers import parse_env_bool

    monkeypatch.delenv("SEARXNG_PUBLIC_INSTANCES_ENABLED", raising=False)
    assert (
        parse_env_bool(os.getenv("SEARXNG_PUBLIC_INSTANCES_ENABLED"), default=False)
        is False
    )


def test_explicit_false_disables_public_searxng_instances() -> None:
    from src.config_parts.parsers import parse_env_bool

    assert parse_env_bool("false", default=False) is False
    assert parse_env_bool("0", default=False) is False
    assert parse_env_bool("false", default=True) is False


def test_explicit_true_enables_public_searxng_instances() -> None:
    from src.config_parts.parsers import parse_env_bool

    assert parse_env_bool("true", default=False) is True
    assert parse_env_bool("1", default=False) is True


def test_config_constructor_defaults_public_searxng_instances_off() -> None:
    from src.config import Config

    assert Config().searxng_public_instances_enabled is False


def test_config_module_uses_false_as_runtime_default() -> None:
    loading_src = (ROOT_DIR / "src" / "config_parts" / "loading.py").read_text(
        encoding="utf-8"
    )
    idx = loading_src.index("SEARXNG_PUBLIC_INSTANCES_ENABLED")
    window = loading_src[idx : idx + 200]
    assert "default=False" in window
    assert "default=True" not in window

    model_src = (ROOT_DIR / "src" / "config_parts" / "model.py").read_text(
        encoding="utf-8"
    )
    model_idx = model_src.index("searxng_public_instances_enabled")
    model_window = model_src[model_idx : model_idx + 80]
    assert "bool = False" in model_window
    assert "bool = True" not in model_window


def test_workflow_reports_disabled_when_variable_unset() -> None:
    workflow = (
        ROOT_DIR / ".github" / "workflows" / "00-daily-analysis.yml"
    ).read_text(encoding="utf-8")

    assert "enabled by default" not in workflow
    assert "disabled by default" in workflow


def test_docs_describe_public_searxng_discovery_as_opt_in() -> None:
    chinese_docs = [
        ROOT_DIR / "docs" / "full-guide.md",
        ROOT_DIR / "docs" / "DEPLOY.md",
        ROOT_DIR / "docs" / "docker" / "zeabur-deployment.md",
    ]
    for path in chinese_docs:
        content = path.read_text(encoding="utf-8")
        base_url_lines = [
            line for line in content.splitlines() if "`SEARXNG_BASE_URLS`" in line
        ]
        public_toggle_lines = [
            line
            for line in content.splitlines()
            if "`SEARXNG_PUBLIC_INSTANCES_ENABLED`" in line
        ]
        assert base_url_lines
        assert public_toggle_lines
        assert all("留空时默认自动发现公共实例" not in line for line in base_url_lines)
        assert all("默认 `false`" in line for line in public_toggle_lines)

    english_guide = (ROOT_DIR / "docs" / "full-guide_EN.md").read_text(
        encoding="utf-8"
    )
    english_base_url_lines = [
        line for line in english_guide.splitlines() if "`SEARXNG_BASE_URLS`" in line
    ]
    english_public_toggle_lines = [
        line
        for line in english_guide.splitlines()
        if "`SEARXNG_PUBLIC_INSTANCES_ENABLED`" in line
    ]
    assert english_base_url_lines
    assert english_public_toggle_lines
    assert all(
        "when empty the app auto-discovers public instances" not in line
        for line in english_base_url_lines
    )
    assert all("default `false`" in line for line in english_public_toggle_lines)
