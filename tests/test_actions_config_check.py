# -*- coding: utf-8 -*-
"""Deterministic tests for Actions configuration check (issue #847)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.services.actions_config_check import (
    CheckSeverity,
    env_from_mapping,
    format_report_markdown,
    format_report_text,
    run_config_check,
)

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "config-check.yml"
SCRIPT_PATH = ROOT / "scripts" / "actions_config_check.py"


def _complete_env(**overrides: str) -> dict[str, str]:
    base = {
        "STOCK_LIST": "600519,hk00700,AAPL",
        "GEMINI_API_KEY": "test-gemini-key-value-ok",
        "WECHAT_WEBHOOK_URL": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=demo",
    }
    base.update(overrides)
    return env_from_mapping(base)


def test_complete_env_passes_without_probe(tmp_path: Path) -> None:
    report = run_config_check(
        _complete_env(),
        strict_notify=False,
        probe_llm=False,
        repo_root=tmp_path,
    )
    assert report.ok
    assert report.exit_code == 0
    assert not report.hard_failures
    codes = {item.code for item in report.items}
    assert "config.watchlist.ok" in codes
    assert "config.llm.ok" in codes
    assert "config.notify.ok" in codes
    assert "config.llm.probe.skipped" in codes


def test_missing_llm_is_hard_failure(tmp_path: Path) -> None:
    env = _complete_env()
    del env["GEMINI_API_KEY"]
    report = run_config_check(env, repo_root=tmp_path)
    assert not report.ok
    assert report.exit_code == 1
    fails = [item for item in report.hard_failures if item.code == "config.llm.missing"]
    assert len(fails) == 1
    assert "LLM_ZHIPU_API_KEY" in fails[0].hint_en or "GEMINI_API_KEY" in fails[0].hint_en


def test_missing_watchlist_is_hard_failure(tmp_path: Path) -> None:
    env = _complete_env()
    del env["STOCK_LIST"]
    report = run_config_check(env, repo_root=tmp_path)
    assert not report.ok
    codes = {item.code for item in report.hard_failures}
    assert "config.watchlist.missing" in codes


def test_malformed_watchlist_only_commas(tmp_path: Path) -> None:
    report = run_config_check(
        _complete_env(STOCK_LIST=", , ;"),
        repo_root=tmp_path,
    )
    assert not report.ok
    assert any(item.code == "config.watchlist.malformed" for item in report.hard_failures)


def test_malformed_llm_placeholder_fails(tmp_path: Path) -> None:
    report = run_config_check(
        _complete_env(GEMINI_API_KEY="xxx"),
        repo_root=tmp_path,
    )
    assert not report.ok
    assert any(item.code == "config.llm.malformed" for item in report.hard_failures)


def test_channel_llm_key_counts(tmp_path: Path) -> None:
    env = env_from_mapping(
        {
            "STOCK_LIST": "600519",
            "LLM_ZHIPU_API_KEY": "zhipu-key-long-enough",
        }
    )
    report = run_config_check(env, repo_root=tmp_path)
    assert any(item.code == "config.llm.ok" for item in report.items)
    assert report.ok
    assert any(item.code == "config.notify.missing" for item in report.warnings)


def test_missing_notify_is_warning_not_failure(tmp_path: Path) -> None:
    env = env_from_mapping(
        {
            "STOCK_LIST": "600519",
            "OPENAI_API_KEY": "sk-test-openai-key-value",
        }
    )
    report = run_config_check(env, strict_notify=False, repo_root=tmp_path)
    assert report.ok
    warn = next(item for item in report.warnings if item.code == "config.notify.missing")
    assert "Artifact" in warn.detail_en or "artifact" in warn.detail_en.lower()


def test_strict_notify_elevates_missing_channel(tmp_path: Path) -> None:
    env = env_from_mapping(
        {
            "STOCK_LIST": "600519",
            "OPENAI_API_KEY": "sk-test-openai-key-value",
        }
    )
    report = run_config_check(env, strict_notify=True, repo_root=tmp_path)
    assert not report.ok
    assert any(item.code == "config.notify.missing" for item in report.hard_failures)


def test_partial_telegram_is_warning(tmp_path: Path) -> None:
    env = _complete_env()
    del env["WECHAT_WEBHOOK_URL"]
    env["TELEGRAM_BOT_TOKEN"] = "123456:ABC-DEF_long_enough_token"
    report = run_config_check(env, repo_root=tmp_path)
    assert any(
        item.code == "config.notify.telegram.incomplete" for item in report.items
    )


def test_malformed_webhook_url_warns(tmp_path: Path) -> None:
    report = run_config_check(
        _complete_env(WECHAT_WEBHOOK_URL="not-a-url"),
        repo_root=tmp_path,
    )
    assert report.ok
    assert any("malformed_url" in item.code for item in report.items)


def test_stock_list_config_preferred(tmp_path: Path) -> None:
    env = _complete_env(STOCK_LIST="600519", STOCK_LIST_CONFIG="000001,AAPL")
    report = run_config_check(env, repo_root=tmp_path)
    watch = next(item for item in report.items if item.code == "config.watchlist.ok")
    assert "STOCK_LIST_CONFIG" in watch.detail_en
    assert "2 symbol" in watch.detail_en


def test_report_never_contains_secret_values(tmp_path: Path) -> None:
    secret = "super-secret-gemini-key-do-not-leak"
    report = run_config_check(
        _complete_env(GEMINI_API_KEY=secret),
        repo_root=tmp_path,
    )
    text = format_report_text(report)
    md = format_report_markdown(report)
    assert secret not in text
    assert secret not in md
    assert "GEMINI_API_KEY" in text


def test_optional_data_sources_info_when_absent(tmp_path: Path) -> None:
    report = run_config_check(_complete_env(), repo_root=tmp_path)
    codes = {item.code for item in report.items}
    assert "config.datasource.tushare_token.absent" in codes
    assert "config.datasource.tickflow_api_key.absent" in codes


def test_cli_main_exit_codes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts import actions_config_check as cli

    monkeypatch.setenv("STOCK_LIST", "600519")
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key-value-ok")
    monkeypatch.delenv("WECHAT_WEBHOOK_URL", raising=False)
    summary = tmp_path / "summary.md"
    code = cli.main(["--summary-file", str(summary), "--no-text"])
    assert code == 0
    assert summary.is_file()
    body = summary.read_text(encoding="utf-8")
    assert "Config Check" in body
    assert "test-gemini-key-value-ok" not in body

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    code = cli.main(["--no-text"])
    assert code == 1


def test_workflow_yaml_structure_and_pins() -> None:
    assert WORKFLOW_PATH.is_file()
    assert SCRIPT_PATH.is_file()
    doc = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    assert doc["name"] == "Config Check"
    on_block = doc.get("on", doc.get(True))
    assert on_block is not None
    assert "workflow_dispatch" in on_block
    job = doc["jobs"]["config-check"]
    assert job["permissions"] == {"contents": "read"}
    steps = job["steps"]
    uses = [step.get("uses", "") for step in steps if "uses" in step]
    assert any(u.startswith("actions/checkout@") for u in uses)
    assert any(u.startswith("actions/setup-python@") for u in uses)
    for use in uses:
        ref = use.split("@", 1)[1].split("#", 1)[0].strip()
        assert len(ref) == 40, f"Action not SHA-pinned: {use}"
        assert all(c in "0123456789abcdef" for c in ref.lower())
    run_step = next(s for s in steps if s.get("name") == "Run configuration check")
    env = run_step["env"]
    assert "STOCK_LIST_CONFIG" in env
    assert "GEMINI_API_KEY" in env
    assert "LLM_ZHIPU_API_KEY" in env
    assert "WECHAT_WEBHOOK_URL" in env
    run_script = run_step["run"]
    assert "actions_config_check.py" in run_script
    assert "echo $" not in run_script


def test_format_markdown_bilingual_headers() -> None:
    report = run_config_check(
        env_from_mapping({"STOCK_LIST": "600519", "OPENAI_API_KEY": "sk-long-enough-key"}),
        repo_root=Path.cwd(),
    )
    md = format_report_markdown(report)
    assert "配置自检" in md
    assert "Config Check" in md
    assert "StockPulse Daily Analysis" in md
    fail_report = run_config_check(env_from_mapping({}), repo_root=Path.cwd())
    fail_md = format_report_markdown(fail_report)
    assert "Settings" in fail_md
