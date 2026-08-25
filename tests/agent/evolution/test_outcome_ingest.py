# -*- coding: utf-8 -*-
"""Red-contract tests for the forecast-outcome adapter overlay (Issue #1106)."""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from src.agent.evolution import adapters as adapters_mod
from src.agent.evolution import outcome_ingest as overlay_mod
from src.agent.evolution.adapters import ADAPTER_INFLUENCE_META_KEY, rank_tools
from src.agent.evolution.guards import (
    snapshot_soul_identity,
    snapshot_tool_surface_denials,
)
from src.agent.evolution.outcome_ingest import (
    FORECAST_OUTCOME_LIST_LIMIT,
    ForecastOutcomeMemory,
    apply_forecast_outcome_calibration,
    forecast_calibration_stats,
    load_scored_forecast_rows,
)
from src.agent.memory import AgentMemory
from src.agent.protocols import AgentContext
from src.agent.soul import AGENT_SOUL_HASH
from src.agent.tools.execution import ToolAccessContext
from src.agent.tools.registry import ToolDefinition, ToolParameter, ToolPolicy, ToolRegistry
from src.agent.tools.surface import ToolSurface
from src.config import Config
from src.repositories.agent_episode_repo import AgentEpisodeRepository
from src.repositories.agent_forward_return_repo import AgentForwardReturnRepository
from src.repositories.agent_prediction_repo import AgentPredictionRepository
from src.repositories.base import RepositoryError
from src.schemas.agent_episode import AgentEpisodeCreate
from src.schemas.agent_prediction import (
    STATUS_DATA_UNAVAILABLE,
    STATUS_PENDING,
    STATUS_RESOLVED,
    AgentPredictionInsert,
)
from src.schemas.prediction_claim_scoring import OUTCOME_NUMERIC_SCORE
from src.storage import DatabaseManager

_TEST_CAPABILITY = "analysis_context:read"


def _config(*, enabled: bool = False, min_samples: int = 30) -> SimpleNamespace:
    return SimpleNamespace(
        agent_online_adapters_enabled=enabled,
        agent_online_adapters_min_samples=min_samples,
        agent_memory_enabled=True,
    )


def _backtest_memory(
    *,
    enabled: bool = True,
    samples: int = 80,
    accuracy: float = 1.0,
    avg_confidence: float = 0.1,
    min_samples: int = 30,
) -> AgentMemory:
    memory = AgentMemory(enabled=enabled, min_samples=min_samples)

    def _get_accuracy_stats(
        agent_name: str,
        stock_code: Optional[str],
        skill_id: Optional[str],
    ) -> Dict[str, Any]:
        return {
            "total": samples,
            "accuracy": accuracy,
            "direction_accuracy": accuracy,
            "avg_confidence": avg_confidence,
        }

    memory._get_accuracy_stats = _get_accuracy_stats  # type: ignore[method-assign]
    return memory


class _FakeRepo:
    def __init__(self, rows: Optional[List[Any]] = None) -> None:
        self.rows = list(rows or [])
        self.calls: List[Any] = []

    def list_by_symbol_market(self, *, symbol: str, market: str, limit: int = 50) -> List[Any]:
        self.calls.append(("list_by_symbol_market", symbol, market, limit))
        return list(self.rows)

    def list_due(self, **kwargs: Any) -> List[Any]:
        self.calls.append(("list_due", kwargs))
        raise AssertionError("forecast overlay must not call list_due")


def _record(
    *,
    status: str = STATUS_RESOLVED,
    label: Optional[str] = "hit",
    mean_confidence: Any = None,
    claims: Optional[List[Any]] = None,
    outcome: Optional[Dict[str, Any]] = None,
    model_meta: Optional[Dict[str, Any]] = None,
) -> SimpleNamespace:
    if outcome is None:
        outcome = {}
        if label is not None:
            outcome["label"] = label
        if mean_confidence is not None:
            outcome["score"] = {"aggregate": {"mean_confidence": mean_confidence}}
    return SimpleNamespace(
        status=status,
        outcome=outcome,
        claims=claims if claims is not None else [{"confidence": 0.7}],
        model_meta=model_meta or {"hidden_confidence": 0.99, "soul": "leak"},
    )


@pytest.fixture()
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "forecast-overlay.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()


def _fixed_now() -> datetime:
    return datetime(2026, 8, 12, 12, 0, 0)


def _direction_claim(confidence: Any = 0.7) -> dict:
    return {
        "claim_id": "direction-0",
        "type": "direction",
        "confidence": confidence,
        "payload": {"direction": "up"},
    }


def _insert(
    repo: AgentPredictionRepository,
    *,
    prediction_id: str,
    symbol: str = "600519",
    market: str = "cn",
    claims: Optional[List[Any]] = None,
    model_meta: Optional[Dict[str, Any]] = None,
) -> None:
    created, record = repo.insert_pending(
        AgentPredictionInsert(
            prediction_id=prediction_id,
            run_id="run-1",
            symbol=symbol,
            market=market,
            as_of=_fixed_now().date(),
            horizon="5d",
            resolve_after=_fixed_now() - timedelta(hours=1),
            claims=claims if claims is not None else [_direction_claim()],
            model_meta=model_meta if model_meta is not None else {"mode": "analysis"},
            created_at=_fixed_now() - timedelta(days=1),
        )
    )
    assert created is True
    assert record.status == STATUS_PENDING


def _resolve(
    repo: AgentPredictionRepository,
    *,
    prediction_id: str,
    label: Optional[str] = None,
    mean_confidence: Optional[float] = None,
    extra_outcome: Optional[Dict[str, Any]] = None,
) -> None:
    outcome: Dict[str, Any] = {}
    if label is not None:
        outcome["label"] = label
    if mean_confidence is not None:
        outcome["score"] = {"aggregate": {"mean_confidence": mean_confidence}}
    if extra_outcome:
        outcome.update(extra_outcome)
    applied, resolved = repo.resolve(
        prediction_id=prediction_id,
        outcome=outcome,
        as_of=_fixed_now(),
    )
    assert applied is True
    assert resolved is not None
    assert resolved.status == STATUS_RESOLVED


def _seed_resolved(
    repo: AgentPredictionRepository,
    *,
    count: int,
    label: str,
    confidence: float,
    symbol: str = "600519",
    market: str = "cn",
    prefix: str = "pred",
) -> None:
    for index in range(count):
        prediction_id = f"{prefix}-{index}"
        _insert(
            repo,
            prediction_id=prediction_id,
            symbol=symbol,
            market=market,
            claims=[_direction_claim(confidence)],
        )
        _resolve(
            repo,
            prediction_id=prediction_id,
            label=label,
            mean_confidence=confidence,
        )


def _echo_registry(calls: List[Any]) -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="echo",
            description="Echo a message.",
            parameters=[
                ToolParameter(name="message", type="string", description="Message"),
            ],
            handler=lambda message: calls.append(message) or {"message": message},
            category="data",
            policy=ToolPolicy.declared(
                read_only=True,
                side_effects=[],
                permissions=[_TEST_CAPABILITY],
            ),
        )
    )
    return registry


def test_overlay_does_not_copy_adapter_arithmetic_or_hook_runtime() -> None:
    source = inspect.getsource(overlay_mod)
    assert "calibrate_confidence" in source
    assert "OUTCOME_NUMERIC_SCORE" in source
    assert "list_by_symbol_market" in source
    assert "ForecastOutcomeMemory" in source
    assert "._get_accuracy_stats =" not in source
    assert ".list_due" not in source
    assert "list_all" not in source
    assert "historical_accuracy / avg_confidence" not in source
    assert "accuracy / avg_confidence" not in source
    assert "base_agent" not in source
    assert "orchestrator" not in source
    import src.agent.agents.base_agent as base_agent_mod

    assert "outcome_ingest" not in inspect.getsource(base_agent_mod)
    assert "calibrate_confidence" in inspect.getsource(adapters_mod.calibrate_confidence)


def test_forecast_outcome_memory_preserves_zero_accuracy_and_zero_confidence() -> None:
    zero_accuracy = ForecastOutcomeMemory(
        total=40,
        accuracy=0.0,
        avg_confidence=0.4,
        min_samples=30,
    )
    zero_confidence = ForecastOutcomeMemory(
        total=40,
        accuracy=1.0,
        avg_confidence=0.0,
        min_samples=30,
    )
    insufficient = ForecastOutcomeMemory(
        total=29,
        accuracy=0.0,
        avg_confidence=0.9,
        min_samples=30,
    )
    assert isinstance(zero_accuracy, AgentMemory)
    zero_cal = zero_accuracy.get_calibration("technical", stock_code="600519")
    assert zero_cal.historical_accuracy == 0.0
    assert zero_cal.avg_confidence == 0.4
    assert zero_cal.calibrated is True
    assert zero_cal.calibration_factor == pytest.approx(0.5)
    conf_cal = zero_confidence.get_calibration("technical", stock_code="600519")
    assert conf_cal.avg_confidence == 0.0
    assert conf_cal.historical_accuracy == 1.0
    assert conf_cal.calibration_factor == pytest.approx(1.0)
    low = insufficient.get_calibration("technical", stock_code="600519")
    assert low.total_samples == 29
    assert low.historical_accuracy == 0.0
    assert low.calibrated is False
    assert low.calibration_factor == pytest.approx(1.0)
    memory_source = inspect.getsource(ForecastOutcomeMemory)
    assert "BacktestService" not in memory_source
    assert "0.6" not in memory_source


def test_flag_off_and_missing_config_do_not_query_store() -> None:
    repo = _FakeRepo(rows=[_record() for _ in range(40)])
    raw = 0.8
    ctx = AgentContext(stock_code="600519")

    off_value, off_meta = apply_forecast_outcome_calibration(
        raw,
        ctx=ctx,
        config=_config(enabled=False),
        repo=repo,
        agent_name="technical",
        stock_code="600519",
    )
    missing_value, missing_meta = apply_forecast_outcome_calibration(
        raw,
        ctx=ctx,
        config=None,
        repo=repo,
        agent_name="technical",
        stock_code="600519",
    )
    empty_value, empty_meta = apply_forecast_outcome_calibration(
        raw,
        ctx=AgentContext(stock_code="600519"),
        config=SimpleNamespace(),
        repo=repo,
        agent_name="technical",
        stock_code="600519",
    )

    assert off_value == raw
    assert missing_value == raw
    assert empty_value == raw
    assert off_meta["applied"] is False
    assert off_meta["factor"] == 1.0
    assert missing_meta["applied"] is False
    assert empty_meta["applied"] is False
    assert ADAPTER_INFLUENCE_META_KEY not in ctx.meta
    assert repo.calls == []


def test_missing_stock_code_is_identity_without_store_query() -> None:
    repo = _FakeRepo(rows=[_record() for _ in range(40)])
    ctx = AgentContext(stock_code="")
    raw = 0.72
    adjusted, meta = apply_forecast_outcome_calibration(
        raw,
        ctx=ctx,
        config=_config(enabled=True),
        repo=repo,
        agent_name="technical",
        stock_code=None,
    )
    whitespace, whitespace_meta = apply_forecast_outcome_calibration(
        raw,
        ctx=ctx,
        config=_config(enabled=True),
        repo=repo,
        agent_name="technical",
        stock_code="   ",
    )
    assert adjusted == raw
    assert whitespace == raw
    assert meta["applied"] is False
    assert meta["reason"] == "missing_scope"
    assert whitespace_meta["reason"] == "missing_scope"
    assert repo.calls == []
    influence = ctx.meta[ADAPTER_INFLUENCE_META_KEY]
    assert influence["confidence"]["reason"] == "missing_scope"
    assert influence["tool_effectiveness"] == {"applied": False, "reason": "stub_neutral"}


def test_zero_scored_rows_are_identity(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert(repo, prediction_id="pred-pending")
    ctx = AgentContext(stock_code="600519")
    raw = 0.66
    adjusted, meta = apply_forecast_outcome_calibration(
        raw,
        ctx=ctx,
        config=_config(enabled=True),
        repo=repo,
        agent_name="technical",
        stock_code="600519",
    )
    assert adjusted == raw
    assert meta["applied"] is False
    assert meta["samples"] == 0
    assert meta["reason"] == "no_scored_outcomes"
    assert ctx.meta[ADAPTER_INFLUENCE_META_KEY]["confidence"]["samples"] == 0


def test_data_unavailable_unlabeled_and_invalid_confidence_do_not_count(
    isolated_db,
) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _insert(repo, prediction_id="pred-unlabeled")
    _insert(repo, prediction_id="pred-garbage")
    _insert(repo, prediction_id="pred-pending")
    _resolve(repo, prediction_id="pred-unlabeled", extra_outcome={"score": 1.0})
    applied, _ = repo.resolve(
        prediction_id="pred-garbage",
        outcome={"label": "garbage", "score": 1.0},
        as_of=_fixed_now(),
    )
    assert applied is True
    _insert(
        repo,
        prediction_id="pred-unavailable-src",
        claims=[_direction_claim(0.9)],
    )
    claimed = repo.claim_for_resolve(
        prediction_id="pred-unavailable-src",
        lease_owner="worker-1",
        lease_token="token-unavailable",
        lease_ttl_seconds=120,
        as_of=_fixed_now(),
    )
    assert claimed is not None
    marked, unavailable = repo.mark_data_unavailable(
        prediction_id="pred-unavailable-src",
        reason="provider_timeout",
        expected_lease_token="token-unavailable",
        as_of=_fixed_now(),
    )
    assert marked is True
    assert unavailable is not None
    assert unavailable.status == STATUS_DATA_UNAVAILABLE

    ctx = AgentContext(stock_code="600519")
    raw = 0.7
    adjusted, meta = apply_forecast_outcome_calibration(
        raw,
        ctx=ctx,
        config=_config(enabled=True, min_samples=30),
        repo=repo,
        agent_name="technical",
        stock_code="600519",
    )
    assert adjusted == raw
    assert meta["applied"] is False
    assert meta["samples"] == 0
    assert meta["reason"] == "no_scored_outcomes"


def test_invalid_confidence_rows_do_not_increment_n() -> None:
    repo = _FakeRepo(
        [
            _record(label="hit", mean_confidence=float("nan"), claims=[]),
            _record(label="miss", mean_confidence=1.5, claims=[]),
            _record(label="partial", claims=[{"confidence": None}]),
            _record(label="hit", claims=[{"confidence": True}]),
        ]
    )
    ctx = AgentContext(stock_code="600519")
    raw = 0.7
    adjusted, meta = apply_forecast_outcome_calibration(
        raw,
        ctx=ctx,
        config=_config(enabled=True),
        repo=repo,
        agent_name="technical",
        stock_code="600519",
    )
    assert adjusted == raw
    assert meta["applied"] is False
    assert meta["samples"] == 0
    assert meta["reason"] == "no_scored_outcomes"


def test_n_equals_min_samples_minus_one_is_identity(isolated_db) -> None:
    repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _seed_resolved(repo, count=29, label="miss", confidence=0.95)
    ctx = AgentContext(stock_code="600519")
    raw = 0.8
    adjusted, meta = apply_forecast_outcome_calibration(
        raw,
        ctx=ctx,
        config=_config(enabled=True, min_samples=30),
        repo=repo,
        agent_name="technical",
        stock_code="600519",
    )
    assert adjusted == raw
    assert meta["applied"] is False
    assert meta["factor"] == 1.0
    assert meta["samples"] == 29
    assert meta["reason"] == "insufficient_samples"
    influence = ctx.meta[ADAPTER_INFLUENCE_META_KEY]
    assert influence["confidence"]["reason"] == "insufficient_samples"
    assert influence["route_preference"]["applied"] is False


def test_overconfident_and_underconfident_forecasts_match_1502_direction(
    isolated_db,
) -> None:
    over_repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _seed_resolved(
        over_repo,
        count=30,
        label="miss",
        confidence=0.9,
        prefix="miss",
    )
    raw = 0.6
    over_ctx = AgentContext(stock_code="600519")
    over_value, over_meta = apply_forecast_outcome_calibration(
        raw,
        ctx=over_ctx,
        config=_config(enabled=True),
        repo=over_repo,
        agent_name="technical",
        stock_code="600519",
    )
    assert over_meta["applied"] is True
    assert over_meta["samples"] == 30
    assert over_meta["factor"] == pytest.approx(0.5)
    assert over_value < raw
    assert over_value == pytest.approx(0.3)

    _seed_resolved(
        over_repo,
        count=30,
        label="hit",
        confidence=0.4,
        symbol="AAPL",
        market="us",
        prefix="hit",
    )
    under_ctx = AgentContext(stock_code="AAPL")
    under_value, under_meta = apply_forecast_outcome_calibration(
        raw,
        ctx=under_ctx,
        config=_config(enabled=True),
        repo=over_repo,
        agent_name="technical",
        stock_code="AAPL",
    )
    assert under_meta["applied"] is True
    assert under_meta["factor"] == pytest.approx(1.5)
    assert under_value > raw
    assert under_value == pytest.approx(0.9)


def test_zero_half_one_accuracy_preserves_1502_calibration_table() -> None:
    cases = [
        # accuracy via labels, avg_confidence, raw, expected_factor, expected_adjusted
        ("miss", 0.4, 0.6, 0.5, 0.3),
        ("miss", 0.4, 0.0, 0.5, 0.0),
        ("miss", 0.4, 1.0, 0.5, 0.5),
        ("partial", 0.5, 0.6, 1.0, 0.6),
        ("partial", 1.0, 0.6, 0.5, 0.3),
        ("partial", 0.25, 0.6, 1.5, 0.9),
        ("hit", 1.0, 0.6, 1.0, 0.6),
        ("hit", 0.4, 0.6, 1.5, 0.9),
        ("hit", 0.4, 1.0, 1.5, 1.0),
        ("hit", 0.0, 0.6, 1.0, 0.6),
    ]
    for label, avg_confidence, raw, expected_factor, expected_adjusted in cases:
        rows = [
            _record(label=label, mean_confidence=avg_confidence) for _ in range(40)
        ]
        repo = _FakeRepo(rows)
        ctx = AgentContext(stock_code="600519")
        adjusted, meta = apply_forecast_outcome_calibration(
            raw,
            ctx=ctx,
            config=_config(enabled=True),
            repo=repo,
            agent_name="technical",
            stock_code="600519",
        )
        assert meta["applied"] is True
        assert meta["factor"] == pytest.approx(expected_factor)
        assert adjusted == pytest.approx(expected_adjusted)
        assert 0.0 <= adjusted <= 1.0
        assert OUTCOME_NUMERIC_SCORE[label] in {0.0, 0.5, 1.0}


def test_never_blend_contradictory_backtest_stats_when_forecast_n_meets_threshold() -> None:
    rows = [_record(label="miss", mean_confidence=0.9) for _ in range(40)]
    repo = _FakeRepo(rows)
    backtest = _backtest_memory(accuracy=1.0, avg_confidence=0.1, samples=80)
    calls: List[str] = []
    original = backtest.get_calibration

    def _spy(agent_name: str, stock_code: Optional[str] = None, **kwargs: Any):
        calls.append(agent_name)
        return original(agent_name, stock_code=stock_code, **kwargs)

    backtest.get_calibration = _spy  # type: ignore[method-assign]
    raw = 0.6
    ctx = AgentContext(stock_code="600519")
    adjusted, meta = apply_forecast_outcome_calibration(
        raw,
        ctx=ctx,
        config=_config(enabled=True),
        repo=repo,
        agent_name="technical",
        stock_code="600519",
    )
    assert calls == []
    backtest_cal = backtest.get_calibration("technical", stock_code="600519")
    assert calls == ["technical"]
    assert backtest_cal.calibration_factor == pytest.approx(1.5)
    assert meta["applied"] is True
    assert meta["factor"] == pytest.approx(0.5)
    assert adjusted == pytest.approx(0.3)
    assert meta["factor"] != pytest.approx(backtest_cal.calibration_factor)
    assert repo.calls == [("list_by_symbol_market", "600519", "cn", FORECAST_OUTCOME_LIST_LIMIT)]


def test_store_failure_is_identity_and_does_not_fabricate_samples() -> None:
    repo = MagicMock()
    repo.list_by_symbol_market.side_effect = RepositoryError(
        "prediction list failed",
        error_code="agent_prediction_list_failed",
    )
    ctx = AgentContext(stock_code="600519")
    raw = 0.77
    adjusted, meta = apply_forecast_outcome_calibration(
        raw,
        ctx=ctx,
        config=_config(enabled=True),
        repo=repo,
        agent_name="technical",
        stock_code="600519",
    )
    assert adjusted == raw
    assert meta["applied"] is False
    assert meta["samples"] == 0
    assert meta["reason"] == "no_scored_outcomes"
    repo.list_due.assert_not_called()
    repo.resolve.assert_not_called()


def test_load_scored_forecast_rows_filters_and_never_calls_list_due() -> None:
    rows = [
        _record(status=STATUS_PENDING, label="hit"),
        _record(status=STATUS_RESOLVED, label="data_unavailable"),
        _record(status=STATUS_RESOLVED, label=None),
        _record(status=STATUS_RESOLVED, label="hit"),
        _record(status=STATUS_RESOLVED, label="partial"),
        _record(status=STATUS_RESOLVED, label="miss"),
    ]
    repo = _FakeRepo(rows)
    scored = load_scored_forecast_rows(
        repo, symbol="600519", market="CN", limit=9000
    )
    labels = [_record_label(item) for item in scored]
    assert labels == ["hit", "partial", "miss"]
    assert repo.calls == [("list_by_symbol_market", "600519", "cn", FORECAST_OUTCOME_LIST_LIMIT)]
    assert all(call[0] != "list_due" for call in repo.calls)


def _record_label(record: Any) -> str:
    return str(record.outcome["label"])


def test_forecast_stats_exclude_invalid_confidence_and_preserve_zero() -> None:
    rows = [
        _record(label="hit", mean_confidence=float("nan"), claims=[]),
        _record(label="hit", mean_confidence=float("inf"), claims=[]),
        _record(label="hit", mean_confidence=-0.1, claims=[]),
        _record(label="hit", mean_confidence=1.1, claims=[]),
        _record(label="miss", mean_confidence=0.0),
        _record(label="miss", claims=[{"confidence": 0.0}], mean_confidence=None),
        _record(label="hit", claims=[], outcome={"label": "hit"}),
        _record(
            label="hit",
            claims=[{"confidence": 0.2}],
            outcome={
                "label": "hit",
                "score": {"aggregate": {"mean_confidence": 0.8}},
            },
        ),
    ]
    stats = forecast_calibration_stats(rows, min_samples=3)
    assert stats["total"] == 3
    assert stats["accuracy"] == pytest.approx((0.0 + 0.0 + 1.0) / 3.0)
    assert stats["avg_confidence"] == pytest.approx((0.0 + 0.0 + 0.8) / 3.0)
    assert stats["used"] is True
    below = forecast_calibration_stats(rows[:6], min_samples=3)
    assert below["total"] == 2
    assert below["used"] is False
    assert below["accuracy"] == pytest.approx(0.0)


def test_model_meta_is_not_a_confidence_source() -> None:
    row = _record(
        label="hit",
        claims=[{"confidence": "nope"}],
        model_meta={"mean_confidence": 0.99, "confidence": 0.99},
        outcome={"label": "hit", "score": 1.0},
    )
    stats = forecast_calibration_stats([row], min_samples=1)
    assert stats["total"] == 0
    assert stats["used"] is False


def test_denied_tool_stays_permission_denied_after_overlay() -> None:
    calls: List[Any] = []
    surface = ToolSurface(_echo_registry(calls))
    denied = ("echo",)
    denials = ("permission_denied",)
    soul_before = snapshot_soul_identity()
    tools_before = snapshot_tool_surface_denials(
        surface,
        denied_tools=denied,
        denial_codes=denials,
    )
    soul_hash_before = AGENT_SOUL_HASH
    repo = _FakeRepo([_record(label="miss", mean_confidence=0.9) for _ in range(40)])
    ctx = AgentContext(stock_code="600519")
    apply_forecast_outcome_calibration(
        0.6,
        ctx=ctx,
        config=_config(enabled=True),
        repo=repo,
        agent_name="technical",
        stock_code="600519",
    )
    ranked = rank_tools(["echo", "quote"], denied_names=["echo"])
    result = surface.execute_tool(
        ranked[0],
        {"message": "should-not-run"},
        ToolAccessContext(),
    )
    assert result["error"]["code"] == "permission_denied"
    assert calls == []
    assert AGENT_SOUL_HASH == soul_hash_before
    assert snapshot_soul_identity() == soul_before
    assert tools_before == snapshot_tool_surface_denials(
        surface,
        denied_tools=denied,
        denial_codes=denials,
    )


def test_episode_schema_has_no_adapter_field_and_overlay_does_not_update_episodes() -> None:
    field_names = set(AgentEpisodeCreate.model_fields)
    assert all("adapter" not in name.lower() for name in field_names)
    assert ADAPTER_INFLUENCE_META_KEY not in field_names
    repo = MagicMock(name="agent_episode_repo")
    overlay_repo = _FakeRepo([_record(label="hit", mean_confidence=0.4) for _ in range(40)])
    ctx = AgentContext(stock_code="600519")
    apply_forecast_outcome_calibration(
        0.6,
        ctx=ctx,
        config=_config(enabled=True),
        repo=overlay_repo,
        agent_name="technical",
        stock_code="600519",
    )
    assert ADAPTER_INFLUENCE_META_KEY in ctx.meta
    repo.update.assert_not_called()
    repo.save.assert_not_called()
    repo.append.assert_not_called()


def test_forward_return_sidecar_rows_do_not_change_overlay_n(isolated_db) -> None:
    pred_repo = AgentPredictionRepository(isolated_db, clock=_fixed_now)
    _seed_resolved(pred_repo, count=29, label="hit", confidence=0.9)
    AgentEpisodeRepository(isolated_db).append(
        AgentEpisodeCreate(
            episode_id="ep-1",
            run_id="run-1",
            mode="analysis",
            symbol="600519",
            market="cn",
            started_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
            completed_at=datetime(2026, 8, 10, 12, 0, tzinfo=timezone.utc),
            success=True,
        )
    )
    AgentForwardReturnRepository(isolated_db).upsert(
        episode_id="ep-1",
        run_id="run-1",
        horizon="1d",
        forward_return_bucket="1d_up",
    )
    ctx = AgentContext(stock_code="600519")
    adjusted, meta = apply_forecast_outcome_calibration(
        0.8,
        ctx=ctx,
        config=_config(enabled=True, min_samples=30),
        repo=pred_repo,
        agent_name="technical",
        stock_code="600519",
    )
    assert adjusted == 0.8
    assert meta["applied"] is False
    assert meta["samples"] == 29
    assert meta["reason"] == "insufficient_samples"


def test_list_limit_is_clamped_to_500() -> None:
    repo = _FakeRepo([])
    load_scored_forecast_rows(repo, symbol="600519", market="cn", limit=10_000)
    load_scored_forecast_rows(repo, symbol="600519", market="cn", limit=0)
    assert repo.calls[0][3] == FORECAST_OUTCOME_LIST_LIMIT
    assert repo.calls[1][3] == 1
    assert FORECAST_OUTCOME_LIST_LIMIT == 500


def test_apply_queries_list_by_symbol_market_only_with_limit_500() -> None:
    repo = _FakeRepo([_record(label="miss", mean_confidence=0.0) for _ in range(40)])
    ctx = AgentContext(stock_code="600519")
    adjusted, meta = apply_forecast_outcome_calibration(
        0.6,
        ctx=ctx,
        config=_config(enabled=True),
        repo=repo,
        agent_name="technical",
        stock_code="600519",
    )
    assert meta["applied"] is True
    assert meta["samples"] == 40
    assert meta["factor"] == pytest.approx(1.0)
    assert adjusted == pytest.approx(0.6)
    assert repo.calls == [
        ("list_by_symbol_market", "600519", "cn", FORECAST_OUTCOME_LIST_LIMIT)
    ]
    assert all(call[0] == "list_by_symbol_market" for call in repo.calls)
    assert all(call[3] <= 500 for call in repo.calls)
