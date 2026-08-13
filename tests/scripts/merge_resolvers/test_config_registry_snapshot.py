from __future__ import annotations

from pathlib import Path

import pytest

from scripts.merge_resolvers.common import RefusalError
from scripts.merge_resolvers.config_registry_snapshot import SUPPORTED_PATH, resolve


BASE = '''EXPECTED_REGISTERED_KEYS_SHA256 = (
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
)
EXPECTED_SCHEMA_SHA256 = (
    "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
)
'''


def _conflict(ours: str, theirs: str) -> str:
    return f"EXPECTED_REGISTERED_KEYS_SHA256 = (\n<<<<<<< HEAD\n{ours}=======\n{theirs}>>>>>>> branch\n)\n"


def _hashes(_root: Path, _path: Path):
    return "c" * 64, "d" * 64


def test_recomputes_both_hashes(context_factory, tmp_path):
    current = BASE.replace(
        '    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n',
        "<<<<<<< HEAD\n"
        '    "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"\n'
        "=======\n"
        '    "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"\n'
        ">>>>>>> branch\n",
    )
    output = resolve(context_factory(SUPPORTED_PATH, current=current), tmp_path, _hashes)
    assert "c" * 64 in output
    assert "d" * 64 in output


def test_refuses_same_hash_on_both_sides(context_factory, tmp_path):
    line = '    "eeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee"\n'
    current = BASE.replace(
        '    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"\n',
        f"<<<<<<< HEAD\n{line}=======\n{line}>>>>>>> branch\n",
    )
    with pytest.raises(RefusalError, match="same snapshot"):
        resolve(context_factory(SUPPORTED_PATH, current=current), tmp_path, _hashes)


def test_refuses_empty_conflict(context_factory, tmp_path):
    with pytest.raises(RefusalError, match="no conflict hunks"):
        resolve(context_factory(SUPPORTED_PATH, current=BASE), tmp_path, _hashes)


def test_refuses_non_hash_structure(context_factory, tmp_path):
    with pytest.raises(RefusalError, match="non-hash structure"):
        resolve(
            context_factory(
                SUPPORTED_PATH,
                current=_conflict("    do_thing()\n", '    "f' + 'f' * 63 + '"\n'),
            ),
            tmp_path,
            _hashes,
        )
