from __future__ import annotations

from pathlib import Path

import pytest

from scripts.merge_resolvers.additive_entries import resolve
from scripts.merge_resolvers.common import RefusalError


PATH = Path("apps/dsa-web/src/i18n/translations/de.ts")


def _conflict(ours: str, theirs: str) -> str:
    return f"{{\n<<<<<<< HEAD\n{ours}=======\n{theirs}>>>>>>> branch\n}}\n"


def test_merges_distinct_mapping_entries(context_factory):
    output = resolve(
        context_factory(
            PATH,
            current=_conflict('  "b": "B",\n', '  "a": "A",\n'),
        )
    )
    assert output.index('"a"') < output.index('"b"')


def test_merges_distinct_array_entries(context_factory):
    output = resolve(
        context_factory(
            Path("apps/dsa-web/src/i18n/translations/en.ts"),
            current=_conflict('  "t00.beta",\n', '  "t00.alpha",\n'),
        )
    )
    assert output.index('"t00.alpha"') < output.index('"t00.beta"')
    assert "<<<<<<<" not in output


def test_merges_non_ascii_mapping_entries(context_factory):
    output = resolve(
        context_factory(
            PATH,
            current=_conflict('  "问候": "你好",\n', '  "farewell": "再见",\n'),
        )
    )
    assert "farewell" in output
    assert "问候" in output
    assert "你好" in output
    assert "再见" in output
    assert "<<<<<<<" not in output


def test_refuses_same_key_on_both_sides(context_factory):
    with pytest.raises(RefusalError, match="changed on both sides"):
        resolve(
            context_factory(
                PATH,
                current=_conflict('  "a": "ours",\n', '  "a": "theirs",\n'),
            )
        )


def test_refuses_empty_conflict(context_factory):
    with pytest.raises(RefusalError, match="no conflict hunks"):
        resolve(context_factory(PATH, current="{}\n"))


def test_refuses_multiline_semantic_edit(context_factory):
    with pytest.raises(RefusalError, match="purely additive"):
        resolve(context_factory(PATH, current=_conflict("  doThing();\n", '  "a": "A",\n')))


def test_refuses_executable_mapping_value(context_factory):
    with pytest.raises(RefusalError, match="purely additive"):
        resolve(
            context_factory(
                PATH,
                current=_conflict('  "a": makeValue(),\n', '  "b": "B",\n'),
            )
        )
