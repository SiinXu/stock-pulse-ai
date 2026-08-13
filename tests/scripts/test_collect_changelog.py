# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for changelog fragment collection."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts import collect_changelog as cc


def test_parse_valid_fragment(tmp_path: Path) -> None:
    path = tmp_path / "1284-demo.md"
    path.write_text(
        "- [Added] Something useful (Refs #1).\n"
        "- [Fixed] Something else (Refs #1).\n",
        encoding="utf-8",
    )
    entries = cc.parse_fragment(path)
    assert [t for t, _ in entries] == ["Added", "Fixed"]


def test_parse_rejects_bad_type(tmp_path: Path) -> None:
    path = tmp_path / "bad.md"
    path.write_text("- [BugFix] no (Refs #1).\n", encoding="utf-8")
    with pytest.raises(cc.FragmentError) as exc:
        cc.parse_fragment(path)
    assert "bad.md:1:" in str(exc.value)


def test_parse_rejects_empty_fragment(tmp_path: Path) -> None:
    path = tmp_path / "empty.md"
    path.write_text("# only a comment\n\n", encoding="utf-8")
    with pytest.raises(cc.FragmentError):
        cc.parse_fragment(path)


def test_check_empty_dir_ok(tmp_path: Path) -> None:
    assert cc.main(["--check", "--fragments-dir", str(tmp_path)]) == 0


def test_check_invalid_fails(tmp_path: Path) -> None:
    (tmp_path / "x.md").write_text("not a valid line\n", encoding="utf-8")
    assert cc.main(["--check", "--fragments-dir", str(tmp_path)]) == 1


def test_consume_writes_and_deletes(tmp_path: Path) -> None:
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    (fragments / "a.md").write_text(
        "- [Fixed] First fix (Refs #9).\n"
        "- [Added] New capability (Refs #9).\n",
        encoding="utf-8",
    )
    (fragments / "README.md").write_text("keep me\n", encoding="utf-8")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        "# Changelog\n\n## [Unreleased]\n- [Chore] Existing entry.\n\n"
        "## [1.0.0] - 2026-01-01\n",
        encoding="utf-8",
    )
    assert (
        cc.main([
            "--consume",
            "--fragments-dir", str(fragments),
            "--changelog", str(changelog),
        ]) == 0
    )
    text = changelog.read_text(encoding="utf-8")
    assert "- [Added] New capability (Refs #9)." in text
    assert "- [Fixed] First fix (Refs #9)." in text
    assert "- [Chore] Existing entry." in text
    assert text.index("[Added]") < text.index("[Fixed]")
    assert not (fragments / "a.md").exists()
    assert (fragments / "README.md").exists()


def test_consume_is_idempotent_on_duplicates(tmp_path: Path) -> None:
    fragments = tmp_path / "fragments"
    fragments.mkdir()
    line = "- [Docs] Same line (Refs #2)."
    (fragments / "b.md").write_text(line + "\n", encoding="utf-8")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        f"# Changelog\n\n## [Unreleased]\n{line}\n\n## [1.0.0] - 2026-01-01\n",
        encoding="utf-8",
    )
    assert (
        cc.main([
            "--consume",
            "--fragments-dir", str(fragments),
            "--changelog", str(changelog),
        ]) == 0
    )
    assert changelog.read_text(encoding="utf-8").count(line) == 1


def test_require_entry_product_without_changelog_fails() -> None:
    assert cc.require_entry_for_diff(
        ["src/services/foo.py", "tests/services/test_foo.py"]
    ) == 1


def test_require_entry_accepts_fragment() -> None:
    assert cc.require_entry_for_diff(
        ["src/services/foo.py", "docs/changelog.d/foo-bar.md"]
    ) == 0


def test_require_entry_accepts_legacy_changelog() -> None:
    assert cc.require_entry_for_diff(
        ["api/v1/endpoints/x.py", "docs/CHANGELOG.md"]
    ) == 0


def test_require_entry_docs_only_ok() -> None:
    assert cc.require_entry_for_diff(["docs/FAQ.md", "README.md"]) == 0


def test_require_entry_ignores_readme_fragment_name() -> None:
    assert cc.require_entry_for_diff(
        ["src/main_workflow.py", "docs/changelog.d/README.md"]
    ) == 1
