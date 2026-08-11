# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Regressions for the three-way config documentation consistency checker."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.check_config_doc_consistency import (
    DEFAULT_FAIL_ON,
    FAIL_CLASS_DOCS,
    FAIL_CLASS_ENV,
    FAIL_CLASS_REGISTRY,
    INVENTORY_END,
    INVENTORY_START,
    collect_report,
    main,
    parse_env_example,
    parse_fail_on,
    parse_inventory_table,
    render_inventory_table,
    replace_inventory_block,
    write_inventory_docs,
)


ROOT = Path(__file__).resolve().parents[2]


def _write_skeleton(path: Path, rows: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Inventory\n\n"
        f"{INVENTORY_START}\n\n"
        f"{rows}"
        f"{INVENTORY_END}\n",
        encoding="utf-8",
    )


def test_self_test_cli_exits_zero() -> None:
    assert main(["--self-test"]) == 0


def test_repository_docs_aligned_under_default_fail_on() -> None:
    """Docs/env/cn_en/defaults must be clean; registry debt is non-fatal by default."""

    assert main(["--fail-on", "default"]) == 0
    # Registry debt is currently expected; all mode should fail until workers finish.
    assert main(["--fail-on", "registry"]) == 1


def test_parse_env_example_captures_commented_keys(tmp_path: Path) -> None:
    env = tmp_path / ".env.example"
    env.write_text(
        "# Feature toggle\n"
        "# CRYPTO_PROVIDER_ENABLED=false\n"
        "STOCK_LIST=600519\n",
        encoding="utf-8",
    )
    entries = parse_env_example(env)
    assert entries["CRYPTO_PROVIDER_ENABLED"].active is False
    assert entries["CRYPTO_PROVIDER_ENABLED"].default == "false"
    assert "Feature toggle" in entries["CRYPTO_PROVIDER_ENABLED"].description
    assert entries["STOCK_LIST"].active is True
    assert entries["STOCK_LIST"].default == "600519"


def test_write_inventory_closes_doc_gaps(tmp_path: Path) -> None:
    env = tmp_path / ".env.example"
    env.write_text("STOCK_LIST=a\n# MCP_SERVER_ENABLED=false\n", encoding="utf-8")
    doc_cn = tmp_path / "docs" / "environment-variables.md"
    doc_en = tmp_path / "docs" / "environment-variables_EN.md"
    _write_skeleton(doc_cn)
    _write_skeleton(doc_en)
    registry = {"STOCK_LIST"}

    report = collect_report(
        root=tmp_path,
        env_path=env,
        doc_cn_path=doc_cn,
        doc_en_path=doc_en,
        registry_keys=registry,
    )
    assert "MCP_SERVER_ENABLED" in report.missing_from_docs
    assert "MCP_SERVER_ENABLED" in report.missing_from_registry

    write_inventory_docs(
        root=tmp_path,
        env_path=env,
        doc_cn_path=doc_cn,
        doc_en_path=doc_en,
        registry_keys=registry,
    )
    report2 = collect_report(
        root=tmp_path,
        env_path=env,
        doc_cn_path=doc_cn,
        doc_en_path=doc_en,
        registry_keys=registry,
    )
    assert report2.missing_from_docs == []
    assert report2.cn_en_mismatch == []
    assert report2.default_mismatch == []
    assert "MCP_SERVER_ENABLED" in report2.missing_from_registry
    assert not report2.has_findings(DEFAULT_FAIL_ON - {FAIL_CLASS_ENV})


def test_detects_missing_env_and_cn_en_and_defaults(tmp_path: Path) -> None:
    env = tmp_path / ".env.example"
    env.write_text("STOCK_LIST=600519\n", encoding="utf-8")
    doc_cn = tmp_path / "cn.md"
    doc_en = tmp_path / "en.md"
    rows_cn = (
        "| 键名 | 默认值 | 已注册 | 备注 |\n"
        "|------|--------|--------|------|\n"
        "| `STOCK_LIST` | `600519` | 是 | ok |\n"
        "| `ORPHAN_DOC` | `x` | 否 | leftover |\n"
    )
    rows_en = (
        "| Key | Default | Registered | Notes |\n"
        "|-----|---------|------------|-------|\n"
        "| `STOCK_LIST` | `WRONG` | yes | ok |\n"
    )
    _write_skeleton(doc_cn, rows_cn)
    _write_skeleton(doc_en, rows_en)

    report = collect_report(
        root=tmp_path,
        env_path=env,
        doc_cn_path=doc_cn,
        doc_en_path=doc_en,
        registry_keys={"STOCK_LIST", "ORPHAN_REGISTRY"},
    )
    assert "ORPHAN_DOC" in report.missing_from_env
    assert "ORPHAN_REGISTRY" in report.missing_from_env
    assert "ORPHAN_DOC" in report.cn_en_mismatch
    assert any(item["key"] == "STOCK_LIST" and item["locale"] == "en" for item in report.default_mismatch)
    assert report.has_findings({FAIL_CLASS_DOCS, FAIL_CLASS_ENV})


def test_parse_fail_on_helpers() -> None:
    assert FAIL_CLASS_REGISTRY not in parse_fail_on("default")
    assert FAIL_CLASS_REGISTRY in parse_fail_on("all")
    assert parse_fail_on("none") == set()
    assert parse_fail_on("docs,env") == {FAIL_CLASS_DOCS, FAIL_CLASS_ENV}
    with pytest.raises(ValueError):
        parse_fail_on("not-a-class")


def test_render_and_parse_inventory_roundtrip(tmp_path: Path) -> None:
    from scripts.check_config_doc_consistency import EnvEntry

    entries = {
        "STOCK_LIST": EnvEntry("STOCK_LIST", "1,2", True, "Watchlist"),
        "CRYPTO_PROVIDER_ENABLED": EnvEntry(
            "CRYPTO_PROVIDER_ENABLED", "false", False, "Crypto toggle"
        ),
    }
    registry = {"STOCK_LIST"}
    body = render_inventory_table(entries, registry, locale="en")
    path = tmp_path / "inv.md"
    _write_skeleton(path)
    replace_inventory_block(path, body)
    parsed = parse_inventory_table(path)
    assert set(parsed) == {"STOCK_LIST", "CRYPTO_PROVIDER_ENABLED"}
    assert parsed["STOCK_LIST"]["default"] == "1,2"
    assert parsed["CRYPTO_PROVIDER_ENABLED"]["registered"] in {"no", "否"}
