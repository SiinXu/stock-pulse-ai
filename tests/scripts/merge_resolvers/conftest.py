from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.merge_resolvers.common import ConflictContext


@pytest.fixture
def context_factory():
    def build(
        path: str | Path,
        *,
        base: str = "",
        ours: str = "",
        theirs: str = "",
        current: str = "",
    ) -> ConflictContext:
        return ConflictContext(Path(path), base, ours, theirs, current)

    return build


@pytest.fixture
def budget_documents():
    base = {
        "version": 1,
        "description": "do not raise budgets to hide regressions without justification",
        "outDir": "../../static",
        "gzipLevel": 9,
        "measuredAt": "2026-08-13",
        "defaults": {"jsMaxGzipBytes": 100, "cssMaxGzipBytes": 100},
        "rules": [
            {"id": "alpha", "match": "alpha-*.js", "maxGzipBytes": 100, "measuredGzipBytes": 80},
            {"id": "beta", "match": "beta-*.js", "maxGzipBytes": 100, "measuredGzipBytes": 80},
        ],
    }
    ours = json.loads(json.dumps(base))
    theirs = json.loads(json.dumps(base))
    ours["rules"][0].update(
        maxGzipBytes=110,
        measuredGzipBytes=90,
        note="Combined build measured 90 B + 20 B headroom.",
    )
    theirs["rules"][1].update(
        maxGzipBytes=120,
        measuredGzipBytes=100,
        note="Combined build measured 100 B + 20 B headroom.",
    )
    return tuple(json.dumps(value) + "\n" for value in (base, ours, theirs))
