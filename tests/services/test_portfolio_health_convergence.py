"""Regression coverage for portfolio-health convergence contracts."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
import math
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from api.v1.schemas.portfolio_health import PortfolioHealthResponse
from src.config import Config
from src.repositories.base import RepositoryError
from src.repositories.portfolio_health_repo import PortfolioHealthRepository
from src.services.portfolio_health_service import (
    PortfolioHealthService,
    resolve_weights,
)
from src.services.portfolio_risk_metrics_service import PortfolioRiskMetricsService
from src.storage import DatabaseManager


def _snapshot(**overrides):
    payload = {
        "currency": "CNY",
        "total_equity": 100_000.0,
        "total_cash": 10_000.0,
        "total_market_value": 90_000.0,
        "unrealized_pnl": 5_000.0,
        "fx_stale": False,
        "data_quality": "ok",
        "limitations": [],
        "accounts": [
            {
                "account_id": 1,
                "base_currency": "CNY",
                "positions": [
                    {
                        "symbol": "AAA",
                        "market_value_base": 90_000.0,
                        "quantity": 100.0,
                        "price_stale": False,
                        "price_source": "stored_daily",
                        "price_date": "2026-04-01",
                    }
                ],
            }
        ],
    }
    payload.update(overrides)
    return payload


def _risk(*, var_pct=2.0, status="ok"):
    return {
        "status": status,
        "currency": "CNY",
        "concentration": {
            "status": "ok",
            "top_weight_pct": 20.0,
            "diversification_score": 0.9,
            "position_count": 3,
            "weights": [{"symbol": "AAA", "weight_pct": 20.0}],
        },
        "var": {
            "status": "ok" if var_pct is not None else "insufficient_history",
            "var_pct": var_pct,
            "status_message": status,
        },
        "history": {
            "aligned_trading_days": 252,
            "aligned_start": "2025-04-01",
            "aligned_end": "2026-04-01",
        },
    }


def _service(snapshot, risk, *, repo=None):
    portfolio = MagicMock()
    portfolio.preview_portfolio_snapshot.return_value = snapshot
    risk_service = MagicMock()
    risk_service.get_risk_metrics.return_value = risk
    service = PortfolioHealthService(
        portfolio_service=portfolio,
        risk_metrics_service=risk_service,
        health_repo=repo or MagicMock(),
        config=Config(stock_list=["600519"]),
    )
    return service


def test_missing_var_cannot_create_a_higher_comparable_score() -> None:
    full_risk = _risk(var_pct=8.0)
    full = _service(_snapshot(), full_risk).get_health(
        as_of=date(2026, 4, 1), persist=False
    )
    partial_risk = _risk(var_pct=None, status="insufficient_history")
    partial = _service(_snapshot(), partial_risk).get_health(
        as_of=date(2026, 4, 1), persist=False
    )
    assert full["score"] is not None
    assert full["band"] is not None
    assert partial["score"] is None
    assert partial["band"] is None
    assert partial["comparable"] is False
    assert partial["coverage_ratio"] == pytest.approx(0.75)
    assert partial["partial_score"] <= full["score"]
    codes = {item["code"] for item in partial["insights"]}
    assert "risk_exposure_unavailable" in codes
    assert "within_thresholds" not in codes


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf])
def test_non_finite_weights_and_metrics_are_rejected(invalid: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        resolve_weights({"risk_exposure": invalid})
    risk = _risk(var_pct=invalid)
    with pytest.raises(ValueError, match="finite"):
        _service(_snapshot(), risk).get_health(
            as_of=date(2026, 4, 1), persist=False
        )


def test_dry_compute_reuses_one_snapshot_and_writes_nothing() -> None:
    snapshot = _snapshot()
    repo = MagicMock()
    service = _service(snapshot, _risk(), repo=repo)
    result = service.get_health(as_of=date(2026, 4, 1), persist=False)
    assert result["persisted"] is False
    service.portfolio_service.preview_portfolio_snapshot.assert_called_once()
    service.portfolio_service.get_portfolio_snapshot.assert_not_called()
    assert (
        service.risk_metrics_service.get_risk_metrics.call_args.kwargs["snapshot"]
        is snapshot
    )
    repo.upsert_snapshot.assert_not_called()


def test_risk_metrics_accepts_supplied_snapshot_without_replay() -> None:
    portfolio = MagicMock()
    service = PortfolioRiskMetricsService(
        portfolio_service=portfolio,
        stock_repo=MagicMock(),
    )
    result = service.get_risk_metrics(
        as_of=date(2026, 4, 1),
        snapshot={"currency": "CNY", "accounts": []},
    )
    assert result["status"] == "empty_portfolio"
    portfolio.get_portfolio_snapshot.assert_not_called()


def test_cash_only_and_negative_equity_are_explicit() -> None:
    cash_only = _snapshot(
        total_equity=100_000.0,
        total_cash=100_000.0,
        total_market_value=0.0,
        unrealized_pnl=0.0,
        accounts=[{"account_id": 1, "positions": []}],
    )
    empty_risk = {
        "status": "empty_portfolio",
        "currency": "CNY",
        "concentration": {"status": "empty_portfolio", "position_count": 0},
        "var": {"status": "unavailable", "var_pct": None},
    }
    cash_result = _service(cash_only, empty_risk).get_health(
        as_of=date(2026, 4, 1), persist=False
    )
    assert cash_result["status"] == "partial"
    assert cash_result["dimensions"]["cash_ratio"]["status"] == "ok"
    assert cash_result["inputs"]["cash_pct"] == 100.0

    negative = _snapshot(total_equity=-1.0)
    negative_result = _service(negative, _risk()).get_health(
        as_of=date(2026, 4, 1), persist=False
    )
    assert negative_result["status"] == "unavailable"
    assert negative_result["score"] is None
    assert negative_result["data_quality"]["partial_reasons"] == ["negative_equity"]


def test_repository_does_not_create_missing_schema(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "missing-health-schema.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    database = DatabaseManager(db_url=f"sqlite:///{db_path}")
    with database.get_session() as session:
        session.execute(text("DROP TABLE portfolio_health_snapshots"))
        session.commit()
    repo = PortfolioHealthRepository(database)
    with pytest.raises(RepositoryError) as exc_info:
        repo.get_snapshot(
            account_id=None,
            snapshot_date=date(2026, 4, 1),
            cost_method="fifo",
        )
    assert exc_info.value.error_code == "portfolio_health_migration_required"
    with database.get_session() as session:
        names = session.execute(
            text("SELECT name FROM sqlite_master WHERE type='table'")
        ).scalars()
        assert "portfolio_health_snapshots" not in set(names)
    DatabaseManager.reset_instance()
    Config.reset_instance()


def test_atomic_upsert_converges_for_same_and_different_keys(
    tmp_path, monkeypatch
) -> None:
    db_path = tmp_path / "atomic-health.db"
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    Config.reset_instance()
    DatabaseManager.reset_instance()
    database = DatabaseManager(db_url=f"sqlite:///{db_path}")
    repo = PortfolioHealthRepository(database)
    payload = {
        "status": "ok",
        "score": 80.0,
        "band": "healthy",
        "persisted": True,
        "provenance": {
            "snapshot_hash": "a" * 64,
            "risk_hash": "b" * 64,
            "config_hash": "c" * 64,
            "calculated_at": "2026-04-01T00:00:00+00:00",
        },
    }

    def write(account_id: int) -> None:
        repo.upsert_snapshot(
            account_id=account_id,
            snapshot_date=date(2026, 4, 1),
            cost_method="fifo",
            payload=payload,
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(write, [1, 1, 2, 1, 2, 1, 2, 1]))

    with database.get_session() as session:
        rows = session.execute(
            text(
                "SELECT account_key, COUNT(*) FROM portfolio_health_snapshots "
                "GROUP BY account_key ORDER BY account_key"
            )
        ).all()
    assert rows == [("1", 1), ("2", 1)]
    DatabaseManager.reset_instance()
    Config.reset_instance()


def test_strict_response_rejects_non_finite_nested_values() -> None:
    result = _service(_snapshot(), _risk()).get_health(
        as_of=date(2026, 4, 1), persist=False
    )
    result["inputs"]["total_cash"] = math.nan
    with pytest.raises(ValidationError):
        PortfolioHealthResponse(**result)
