from __future__ import annotations

import pytest

from scripts.merge_resolvers.common import RefusalError
from scripts.merge_resolvers.docs_index import EN_PATH, ZH_PATH, resolve_pair


def _conflict(ours: str, theirs: str) -> str:
    return f"# Index\n<<<<<<< HEAD\n{ours}=======\n{theirs}>>>>>>> branch\n"


def test_merges_bilingual_additive_rows(context_factory):
    contexts = {
        ZH_PATH: context_factory(
            ZH_PATH,
            current=_conflict("| [乙](b.md) | B |\n", "| [甲](a.md) | A |\n"),
        ),
        EN_PATH: context_factory(
            EN_PATH,
            current=_conflict("| [Beta](b_EN.md) | B |\n", "| [Alpha](a_EN.md) | A |\n"),
        ),
    }
    outputs = resolve_pair(contexts)
    assert outputs[ZH_PATH].index("a.md") < outputs[ZH_PATH].index("b.md")
    assert outputs[EN_PATH].index("a_EN.md") < outputs[EN_PATH].index("b_EN.md")


def test_refuses_same_document_target_on_both_sides(context_factory):
    contexts = {
        ZH_PATH: context_factory(
            ZH_PATH,
            current=_conflict("| [甲](a.md) | ours |\n", "| [甲](a.md) | theirs |\n"),
        ),
        EN_PATH: context_factory(
            EN_PATH,
            current=_conflict("| [Alpha](a_EN.md) | ours |\n", "| [Alpha](a_EN.md) | theirs |\n"),
        ),
    }
    with pytest.raises(RefusalError, match="added on both sides"):
        resolve_pair(contexts)


def test_refuses_empty_conflict(context_factory):
    contexts = {
        ZH_PATH: context_factory(ZH_PATH, current="# Index\n"),
        EN_PATH: context_factory(EN_PATH, current="# Index\n"),
    }
    with pytest.raises(RefusalError, match="no conflict hunks"):
        resolve_pair(contexts)


def test_refuses_non_row_conflict(context_factory):
    contexts = {
        ZH_PATH: context_factory(ZH_PATH, current=_conflict("paragraph\n", "other\n")),
        EN_PATH: context_factory(EN_PATH, current=_conflict("paragraph\n", "other\n")),
    }
    with pytest.raises(RefusalError, match="non-table-row"):
        resolve_pair(contexts)
