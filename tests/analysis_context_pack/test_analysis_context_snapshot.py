# -*- coding: utf-8 -*-
"""Issue #182: versioned sealed analysis-context snapshots."""

from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from src.agent.orchestrator_parts.dashboard import _DashboardMethods
from src.agent.protocols import AgentContext
from src.analysis_context_pack.snapshot import (
    SNAPSHOT_DATA_KEYS,
    SnapshotConsistencyError,
    SnapshotMutationError,
    assert_snapshots_consistent,
    concurrent_snapshot_reads,
    seal_analysis_context_snapshot,
    stamp_pack_snapshot_identity,
)
from src.schemas.analysis_context_pack import (
    PACK_VERSION,
    AnalysisContextBlock,
    AnalysisContextItem,
    AnalysisContextPack,
    AnalysisSubject,
    ContextFieldStatus,
)
from src.services.analysis_context_builder import (
    AnalysisContextBuilder,
    PipelineAnalysisArtifacts,
)
from src.task_execution import FrozenMapping


def _pack(**overrides) -> AnalysisContextPack:
    data = {
        "subject": AnalysisSubject(code="600519", stock_name="贵州茅台", market="cn"),
        "blocks": {
            "quote": AnalysisContextBlock(
                status=ContextFieldStatus.AVAILABLE,
                source="akshare_em",
                timestamp="2026-05-24T09:30:00+08:00",
                items={
                    "price": AnalysisContextItem(
                        status=ContextFieldStatus.AVAILABLE,
                        value=1880.0,
                        source="akshare_em",
                        timestamp="2026-05-24T09:30:00+08:00",
                    )
                },
            )
        },
        "created_at": datetime(2026, 5, 24, 1, 30, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return AnalysisContextPack(**data)


def test_builder_stamps_snapshot_identity_and_digest() -> None:
    pack = AnalysisContextBuilder.build(
        PipelineAnalysisArtifacts(
            code="600519",
            stock_name="贵州茅台",
            market="cn",
            phase={"market": "cn", "phase": "intraday"},
            base_context={
                "code": "600519",
                "date": "2026-05-24",
                "today": {"date": "2026-05-24", "close": 1880.0},
                "yesterday": {"date": "2026-05-23", "close": 1860.0},
            },
            enhanced_context={},
            realtime_quote=None,
            trend_result=None,
            chip_data=None,
            fundamental_context=None,
            news_context="headline",
            news_result_count=1,
            metadata={"query_id": "q-1", "trigger_source": "test"},
        )
    )

    assert pack.pack_version == PACK_VERSION
    assert pack.snapshot_id
    assert pack.snapshot_revision == 1
    assert pack.metadata.get("content_digest")
    assert pack.metadata.get("snapshot_sealed") is True
    identity = pack.audit_identity()
    assert identity["snapshot_id"] == pack.snapshot_id
    assert identity["content_digest"] == pack.metadata["content_digest"]


def test_seal_blocks_inplace_mutation_of_market_inputs() -> None:
    pack = stamp_pack_snapshot_identity(_pack())
    snapshot = seal_analysis_context_snapshot(
        pack,
        {
            "realtime_quote": {"price": 1880.0, "source": "akshare_em"},
            "news_context": "headline-a",
        },
    )

    with pytest.raises((TypeError, AttributeError)):
        snapshot.data["realtime_quote"]["price"] = 1.0  # type: ignore[index]

    with pytest.raises((TypeError, AttributeError)):
        snapshot.pack["blocks"]["quote"]["status"] = "missing"  # type: ignore[index]

    thawed = snapshot.read_data("realtime_quote")
    assert thawed == {"price": 1880.0, "source": "akshare_em"}
    thawed["price"] = 1.0
    assert snapshot.read_data("realtime_quote")["price"] == 1880.0


def test_agent_context_rejects_sealed_market_key_writes() -> None:
    ctx = AgentContext(query="analyze 600519", stock_code="600519")
    ctx.set_data("realtime_quote", {"price": 1880.0})
    ctx.set_data("news_context", "headline-a")
    snapshot = seal_analysis_context_snapshot(
        _pack(),
        {
            "realtime_quote": {"price": 1880.0},
            "news_context": "headline-a",
        },
        snapshot_id="snap-1",
        snapshot_revision=1,
    )
    ctx.seal_input_snapshot(snapshot)

    with pytest.raises(SnapshotMutationError):
        ctx.set_data("realtime_quote", {"price": 1.0})

    with pytest.raises(SnapshotMutationError):
        ctx.data["news_context"] = "mutated"

    # Stage outputs remain writable on non-snapshot keys.
    ctx.set_data("intel_opinion", {"signal": "hold"})
    assert ctx.get_data("intel_opinion")["signal"] == "hold"

    # get_data returns a detached copy; mutating it does not drift the seal.
    quote = ctx.get_data("realtime_quote")
    quote["price"] = 1.0
    assert ctx.get_data("realtime_quote")["price"] == 1880.0
    assert ctx.meta["analysis_context_snapshot"]["snapshot_id"] == "snap-1"
    assert isinstance(ctx.data["realtime_quote"], FrozenMapping)


def test_concurrent_stage_readers_see_identical_snapshot() -> None:
    snapshot = seal_analysis_context_snapshot(
        _pack(),
        {
            "realtime_quote": {"price": 1880.0, "change_pct": 1.2},
            "trend_result": {"ma5": 1870.0, "ma20": 1800.0},
            "news_context": "same-news",
        },
        snapshot_id="snap-concurrent",
        snapshot_revision=1,
    )

    reads = concurrent_snapshot_reads(snapshot, workers=8)
    assert len(reads) == 8
    first = reads[0]
    for other in reads[1:]:
        assert other["audit"] == first["audit"]
        assert other["data"] == first["data"]
        assert other["pack"]["snapshot_id"] == "snap-concurrent"

    # AgentContext multi-stage simulation: each stage reads via get_data.
    ctx = AgentContext(stock_code="600519")
    ctx.seal_input_snapshot(snapshot)

    def _stage_read(_: int) -> dict:
        return {
            "snapshot_id": ctx.meta["analysis_context_snapshot_id"],
            "quote": copy.deepcopy(ctx.get_data("realtime_quote")),
            "news": ctx.get_data("news_context"),
            "digest": ctx.input_snapshot.fingerprint() if ctx.input_snapshot else None,
        }

    with ThreadPoolExecutor(max_workers=6) as pool:
        stage_reads = list(pool.map(_stage_read, range(6)))
    assert all(item == stage_reads[0] for item in stage_reads)


def test_inconsistent_snapshot_identity_is_detected() -> None:
    left = seal_analysis_context_snapshot(
        _pack(),
        {"realtime_quote": {"price": 1880.0}},
        snapshot_id="snap-a",
        snapshot_revision=1,
    )
    right = seal_analysis_context_snapshot(
        _pack(),
        {"realtime_quote": {"price": 1880.0}},
        snapshot_id="snap-b",
        snapshot_revision=1,
    )
    with pytest.raises(SnapshotConsistencyError):
        assert_snapshots_consistent(left, right)

    # Same id but different market inputs => digest mismatch.
    mutated = seal_analysis_context_snapshot(
        _pack(),
        {"realtime_quote": {"price": 1.0}},
        snapshot_id="snap-a",
        snapshot_revision=1,
    )
    with pytest.raises(SnapshotConsistencyError):
        assert_snapshots_consistent(left, mutated)


def test_orchestrator_seals_shared_context_for_multi_agent() -> None:
    methods = _DashboardMethods()
    ctx = methods._build_context(
        "Analyze 600519",
        {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "realtime_quote": {"price": 1880.0, "source": "akshare_em"},
            "news_context": "headline",
            "trend_result": {"ma5": 1870.0},
            "analysis_context_snapshot": {
                "snapshot_id": "snap-orch-1",
                "snapshot_revision": 1,
                "as_of": "2026-05-24T09:30:00+08:00",
                "pack_version": PACK_VERSION,
            },
            "analysis_context_pack_summary": "## Analysis Context Pack Summary\n",
        },
    )

    assert ctx.input_snapshot is not None
    assert ctx.meta["analysis_context_snapshot"]["snapshot_id"] == "snap-orch-1"
    assert set(SNAPSHOT_DATA_KEYS).intersection(ctx.data.keys())
    with pytest.raises(SnapshotMutationError):
        ctx.set_data("realtime_quote", {"price": 0})
    # Direct nested mutation of the sealed bag is blocked by FrozenMapping.
    with pytest.raises((TypeError, AttributeError)):
        ctx.data["realtime_quote"]["price"] = 0  # type: ignore[index]
