"""Contract tests for the derived-file merge resolver suite."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.merge_resolvers import common, settings_help
from scripts.merge_resolvers.common import ConflictContext, RefusalError
from scripts.merge_resolvers.resolve import SUPPORTED_DISPLAY, main, plan_resolutions


HELP_PATH = Path("apps/dsa-web/src/locales/settingsHelp.en.ts")


def _context(
    current: str,
    *,
    path: Path = HELP_PATH,
    base: str = "",
    ours: str = "",
    theirs: str = "",
) -> ConflictContext:
    return ConflictContext(path, base, ours, theirs, current)


def _help_file(blocks: list[str]) -> str:
    return "const settingsHelpEnUS = {\n" + "".join(blocks) + "};\n"


def _help_block(key: str, title: str) -> str:
    return f"  '{key}': {{\n    title: '{title}',\n  }},\n"


def _conflict(ours: str, theirs: str) -> str:
    return (
        "const settingsHelpEnUS = {\n"
        f"<<<<<<< HEAD\n{ours}=======\n{theirs}>>>>>>> branch\n"
        "};\n"
    )


def test_settings_help_unions_both_sides_blocks():
    output = settings_help.resolve(
        _context(
            _conflict(
                _help_block("settings.ours", "Ours"),
                _help_block("settings.theirs", "Theirs"),
            )
        )
    )
    assert "settings.ours" in output
    assert "settings.theirs" in output
    assert "<<<<<<<" not in output
    assert output.index("settings.ours") < output.index("settings.theirs")


def test_settings_help_refuses_same_key_with_different_bodies():
    with pytest.raises(RefusalError, match="differently"):
        settings_help.resolve(
            _context(
                _conflict(
                    _help_block("settings.same", "Ours"),
                    _help_block("settings.same", "Theirs"),
                )
            )
        )


def test_settings_help_merges_a_hunk_cut_inside_the_appended_block():
    current = (
        "const settingsHelpEnUS = {\n"
        "  'settings.a': {\n    title: 'A',\n  },\n"
        "<<<<<<< HEAD\n"
        "  'settings.ours': {\n    title: 'Ours',\n"
        "=======\n"
        "  'settings.theirs': {\n    title: 'Theirs',\n    summary: 'S',\n"
        ">>>>>>> branch\n"
        "  },\n"
        "};\n"
    )
    output = settings_help.resolve(_context(current))
    assert "<<<<<<<" not in output
    assert output.count("  },\n") == 3
    assert output.index("settings.ours") < output.index("settings.theirs")
    assert "summary: 'S'" in output


def test_settings_help_refuses_when_only_one_side_ends_mid_block():
    current = (
        "const settingsHelpEnUS = {\n"
        "<<<<<<< HEAD\n"
        "  'settings.ours': {\n    title: 'Ours',\n"
        "=======\n"
        "  'settings.theirs': {\n    title: 'Theirs',\n  },\n"
        ">>>>>>> branch\n"
        "  },\n"
        "};\n"
    )
    with pytest.raises(RefusalError, match="only one side ends inside an entry block"):
        settings_help.resolve(_context(current))


def test_settings_help_refuses_unexpected_lines():
    with pytest.raises(RefusalError, match="not a settings-help entry block"):
        settings_help.resolve(
            _context(
                _conflict(
                    "  ...spreadOurs,\n",
                    _help_block("settings.theirs", "Theirs"),
                )
            )
        )


def test_settings_help_refuses_empty_conflict():
    with pytest.raises(RefusalError, match="no conflict hunks"):
        settings_help.resolve(_context(_help_file([_help_block("settings.a", "A")])))


def test_settings_help_refuses_empty_side():
    with pytest.raises(RefusalError, match="empty side"):
        settings_help.resolve(_context(_conflict("", _help_block("settings.theirs", "Theirs"))))


def test_settings_help_refuses_unsupported_path():
    with pytest.raises(RefusalError, match="unsupported settings-help file"):
        settings_help.resolve(
            _context(
                _conflict(
                    _help_block("settings.ours", "Ours"),
                    _help_block("settings.theirs", "Theirs"),
                ),
                path=Path("apps/dsa-web/src/locales/settingsHelp.ts"),
            )
        )


@pytest.mark.parametrize(
    "path",
    [
        Path("apps/dsa-web/src/locales/settingsHelp.ts"),
        Path("apps/dsa-web/src/locales/settingsHelpTypes.ts"),
        Path("apps/dsa-web/src/locales/settingsHelp.en.js"),
    ],
)
def test_settings_help_does_not_claim_non_catalogue_files(path):
    assert settings_help.is_supported(path) is False


def test_settings_help_matches_language_catalogues():
    assert settings_help.is_supported(HELP_PATH) is True
    assert settings_help.is_supported(Path("apps/dsa-web/src/locales/settingsHelp.zh.ts"))


def test_cli_list_includes_settings_help_and_existing_derived_files(capsys):
    assert main(["--list"]) == 0
    listed = capsys.readouterr().out.splitlines()
    assert "apps/dsa-web/src/locales/settingsHelp.<lang>.ts" in listed
    assert "apps/dsa-web/scripts/bundle-size-budget.json" in listed
    assert "apps/dsa-web/src/i18n/translations/*.ts" in listed
    assert listed == list(SUPPORTED_DISPLAY)


def test_cli_refuses_empty_batch(capsys):
    assert main([]) == 2
    err = capsys.readouterr().err
    assert "REFUSE" in err
    assert "no conflict files were provided" in err


def test_cli_refuses_unsupported_path(capsys):
    assert main(["src/core/pipeline.py"]) == 2
    err = capsys.readouterr().err
    assert "REFUSE" in err
    assert "unsupported conflict file" in err


def test_plan_resolutions_refuses_empty_path_list(tmp_path):
    with pytest.raises(RefusalError, match="no conflict files were provided"):
        plan_resolutions(tmp_path, [])


def test_plan_resolutions_refuses_duplicate_paths(tmp_path):
    with pytest.raises(RefusalError, match="duplicate conflict paths"):
        plan_resolutions(tmp_path, [HELP_PATH, HELP_PATH])


def test_atomic_write_refuses_all_zero_batch(tmp_path):
    with pytest.raises(RefusalError, match="all-zero/no-op"):
        common.atomic_write_and_stage(tmp_path, {})
