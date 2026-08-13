from __future__ import annotations

from pathlib import Path

import pytest

from scripts.merge_resolvers.common import RefusalError
from scripts.merge_resolvers.public_surface import resolve


PATH = Path("tests/agent/test_agent_orchestrator_public_surface.py")
BASE_FILE = '''EXPECTED_PUBLIC_EXPORTS = frozenset(
    """
    Alpha
    """.split()
)
EXPECTED_EXECUTION_METHODS = ("run",)
EXPECTED_CHAT_METHODS = ("chat",)
EXPECTED_PIPELINE_METHODS = ("pipeline",)
EXPECTED_DASHBOARD_METHODS = ("dashboard",)
EXPECTED_AST_HASHES = {
    "_ExecutionMethods": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
}
'''


def _provider(_root: Path, _path: Path):
    return {
        "EXPECTED_PUBLIC_EXPORTS": ["Alpha", "Beta"],
        "EXPECTED_EXECUTION_METHODS": ["run", "prepare"],
        "EXPECTED_CHAT_METHODS": ["chat"],
        "EXPECTED_PIPELINE_METHODS": ["pipeline"],
        "EXPECTED_DASHBOARD_METHODS": ["dashboard"],
        "EXPECTED_AST_HASHES": {
            "_ExecutionMethods": "c" * 64,
            "_ChatMethods": "d" * 64,
        },
    }


def _conflicted(ours: str, theirs: str) -> str:
    return BASE_FILE.replace(
        '    "_ExecutionMethods": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",\n',
        f"<<<<<<< HEAD\n{ours}=======\n{theirs}>>>>>>> branch\n",
    )


def test_recomputes_snapshot_from_merged_implementation(context_factory, tmp_path):
    base_line = '    "_ExecutionMethods": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",\n'
    our_line = '    "_ExecutionMethods": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",\n'
    their_line = '    "_ExecutionMethods": "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee",\n'
    current = _conflicted(
        our_line,
        their_line,
    )
    output = resolve(
        context_factory(
            PATH,
            base=BASE_FILE,
            ours=BASE_FILE.replace(base_line, our_line),
            theirs=BASE_FILE.replace(base_line, their_line),
            current=current,
        ),
        tmp_path,
        _provider,
    )
    assert "Beta" in output
    assert "'prepare'" in output
    assert "'cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc'" in output


def test_refuses_same_snapshot_entry_on_both_sides(context_factory, tmp_path):
    line = '    "_ExecutionMethods": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",\n'
    with pytest.raises(RefusalError, match="both sides changed the same"):
        resolve(
            context_factory(
                PATH,
                ours=BASE_FILE.replace(
                    '    "_ExecutionMethods": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",\n',
                    line,
                ),
                theirs=BASE_FILE.replace(
                    '    "_ExecutionMethods": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",\n',
                    line,
                ),
                current=_conflicted(line, line),
            ),
            tmp_path,
            _provider,
        )


def test_refuses_empty_conflict(context_factory, tmp_path):
    with pytest.raises(RefusalError, match="no conflict hunks"):
        resolve(context_factory(PATH, current=BASE_FILE), tmp_path, _provider)


def test_refuses_conflict_outside_snapshot(context_factory, tmp_path):
    current = BASE_FILE + "<<<<<<< HEAD\ndef alpha(): pass\n=======\ndef beta(): pass\n>>>>>>> branch\n"
    with pytest.raises(RefusalError, match="not inside one EXPECTED"):
        resolve(
            context_factory(
                PATH,
                ours=BASE_FILE + "def alpha(): pass\n",
                theirs=BASE_FILE + "def beta(): pass\n",
                current=current,
            ),
            tmp_path,
            _provider,
        )


def test_accepts_identifier_rows_inside_export_snapshot(context_factory, tmp_path):
    current = BASE_FILE.replace(
        "    Alpha\n",
        "<<<<<<< HEAD\n    Alpha Existing\n=======\n    Alpha Added\n>>>>>>> branch\n",
    )
    output = resolve(
        context_factory(
            PATH,
            ours=BASE_FILE.replace("    Alpha\n", "    Alpha Existing\n"),
            theirs=BASE_FILE.replace("    Alpha\n", "    Alpha Added\n"),
            current=current,
        ),
        tmp_path,
        _provider,
    )
    assert "Alpha Beta" in output
