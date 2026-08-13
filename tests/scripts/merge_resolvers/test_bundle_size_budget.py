from __future__ import annotations

import json

import pytest

from scripts.merge_resolvers.bundle_size_budget import SUPPORTED_PATH, resolve
from scripts.merge_resolvers.common import RefusalError


CONFLICT = "<<<<<<< HEAD\nours\n=======\ntheirs\n>>>>>>> branch\n"


def test_merges_distinct_rule_changes(context_factory, budget_documents):
    base, ours, theirs = budget_documents
    result = json.loads(
        resolve(
            context_factory(
                SUPPORTED_PATH,
                base=base,
                ours=ours,
                theirs=theirs,
                current=CONFLICT,
            )
        )
    )

    assert [rule["measuredGzipBytes"] for rule in result["rules"]] == [90, 100]


def test_refuses_rule_changed_on_both_sides(context_factory, budget_documents):
    base, ours, _ = budget_documents
    theirs_value = json.loads(ours)
    theirs_value["rules"][0]["maxGzipBytes"] = 111

    with pytest.raises(RefusalError, match="changed on both sides"):
        resolve(
            context_factory(
                SUPPORTED_PATH,
                base=base,
                ours=ours,
                theirs=json.dumps(theirs_value),
                current=CONFLICT,
            )
        )


def test_refuses_empty_conflict(context_factory, budget_documents):
    base, ours, theirs = budget_documents
    with pytest.raises(RefusalError, match="no conflict hunks"):
        resolve(context_factory(SUPPORTED_PATH, base=base, ours=ours, theirs=theirs, current=ours))


def test_refuses_unexpected_conflict_shape(context_factory, budget_documents):
    base, ours, theirs = budget_documents
    with pytest.raises(RefusalError, match="unterminated"):
        resolve(
            context_factory(
                SUPPORTED_PATH,
                base=base,
                ours=ours,
                theirs=theirs,
                current="<<<<<<< HEAD\nno separator\n",
            )
        )
