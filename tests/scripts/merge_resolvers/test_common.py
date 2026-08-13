from __future__ import annotations

from pathlib import Path

import pytest

from scripts.merge_resolvers import common


def test_atomic_write_rolls_back_every_replaced_file(monkeypatch, tmp_path):
    first = Path("first.txt")
    second = Path("second.txt")
    (tmp_path / first).write_bytes(b"first-before\n")
    (tmp_path / second).write_bytes(b"second-before\n")
    (tmp_path / first).chmod(0o744)
    first_mode = (tmp_path / first).stat().st_mode

    def fail_git_add(_root, args, **_kwargs):
        assert args[0] == "add"
        raise RuntimeError("synthetic index failure")

    monkeypatch.setattr(common, "run_git", fail_git_add)
    with pytest.raises(RuntimeError, match="synthetic index failure"):
        common.atomic_write_and_stage(
            tmp_path,
            {first: b"first-after\n", second: b"second-after\n"},
        )

    assert (tmp_path / first).read_bytes() == b"first-before\n"
    assert (tmp_path / second).read_bytes() == b"second-before\n"
    assert (tmp_path / first).stat().st_mode == first_mode


def test_atomic_write_stages_all_outputs_once(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(common, "run_git", lambda root, args, **kwargs: calls.append((root, args)) or "")

    common.atomic_write_and_stage(
        tmp_path,
        {Path("first.txt"): b"first\n", Path("second.txt"): b"second\n"},
    )

    assert calls == [
        (
            tmp_path,
            ["add", "--", "first.txt", "second.txt"],
        )
    ]
