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


def test_keeps_one_sided_aggregate_rules_while_merging_per_asset_changes(context_factory, budget_documents):
    base, ours, theirs = budget_documents
    ours_value = json.loads(ours)
    ours_value["aggregateRules"] = [
        {
            "id": "alpha-family",
            "match": ["alpha-*.js", "alpha*.js"],
            "maxGzipBytes": 110,
            "measuredGzipBytes": 90,
            "note": "Measured 90 B + 20 B headroom.",
        }
    ]

    result = json.loads(
        resolve(
            context_factory(
                SUPPORTED_PATH,
                base=base,
                ours=json.dumps(ours_value),
                theirs=theirs,
                current=CONFLICT,
            )
        )
    )

    assert [rule["measuredGzipBytes"] for rule in result["rules"]] == [90, 100]
    assert result["aggregateRules"] == ours_value["aggregateRules"]


def test_merges_distinct_aggregate_rule_changes(context_factory, budget_documents):
    base_value = json.loads(budget_documents[0])
    base_value["aggregateRules"] = [
        {
            "id": "alpha-family",
            "match": "alpha-*.js",
            "maxGzipBytes": 100,
            "measuredGzipBytes": 80,
        },
        {
            "id": "beta-family",
            "match": ["beta-*.js"],
            "maxGzipBytes": 100,
            "measuredGzipBytes": 80,
        },
    ]
    ours_value = json.loads(json.dumps(base_value))
    theirs_value = json.loads(json.dumps(base_value))
    ours_value["aggregateRules"][0].update(
        maxGzipBytes=110,
        measuredGzipBytes=90,
        note="Combined build measured 90 B + 20 B headroom.",
    )
    theirs_value["aggregateRules"][1].update(
        maxGzipBytes=120,
        measuredGzipBytes=100,
        note="Combined build measured 100 B + 20 B headroom.",
    )

    result = json.loads(
        resolve(
            context_factory(
                SUPPORTED_PATH,
                base=json.dumps(base_value),
                ours=json.dumps(ours_value),
                theirs=json.dumps(theirs_value),
                current=CONFLICT,
            )
        )
    )

    assert [rule["measuredGzipBytes"] for rule in result["aggregateRules"]] == [90, 100]


def test_refuses_aggregate_rule_changed_on_both_sides(context_factory, budget_documents):
    base_value = json.loads(budget_documents[0])
    base_value["aggregateRules"] = [
        {
            "id": "alpha-family",
            "match": "alpha-*.js",
            "maxGzipBytes": 100,
            "measuredGzipBytes": 80,
        }
    ]
    ours_value = json.loads(json.dumps(base_value))
    theirs_value = json.loads(json.dumps(base_value))
    ours_value["aggregateRules"][0]["maxGzipBytes"] = 110
    theirs_value["aggregateRules"][0]["maxGzipBytes"] = 111

    with pytest.raises(RefusalError, match="changed on both sides"):
        resolve(
            context_factory(
                SUPPORTED_PATH,
                base=json.dumps(base_value),
                ours=json.dumps(ours_value),
                theirs=json.dumps(theirs_value),
                current=CONFLICT,
            )
        )
