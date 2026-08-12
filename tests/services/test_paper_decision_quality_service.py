# -*- coding: utf-8 -*-
"""Process-quality scores for paper trades (Issue #1134).

Acceptance: two fixtures with similar PnL but different discipline get different
process scores. Scores never use return fields.

Also covers the production account path: paper gate, signal lookback linkage,
equity-as-of trade date, and HTTP endpoint smoke.
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from src.config import Config
from src.services.decision_signal_service import DecisionSignalService
from src.services.paper_decision_quality_service import (
    FORMULA_VERSION,
    SCORE_KIND,
    PaperAccountNotFoundError,
    PaperDecisionQualityService,
    score_paper_decision_context,
)
from src.services.paper_portfolio_service import (
    PaperAccountRequiredError,
    PaperPortfolioService,
)
from src.services.portfolio_service import PortfolioService
from src.storage import DatabaseManager, DecisionSignalRecord, StockDaily


# Shared PnL so fixtures prove process ≠ return evaluation.
_SAME_PNL = {
    "realized_pnl_pct": 5.0,
    "return_pct": 5.0,
    "outcome": "hit",
    "win_rate": 1.0,
}

_INITIAL_CASH = 100_000.0
_NOW = datetime(2024, 6, 3, 15, 0, 0)
_AS_OF = _NOW.date()


def _disciplined_buy() -> dict:
    return {
        "side": "buy",
        "symbol": "600519",
        "trade_date": "2024-06-03",
        "position_weight_pct": 12.0,
        "concentration_alert_pct": 35.0,
        **_SAME_PNL,
        "linked_signal": {
            "id": 101,
            "action": "buy",
            "confidence": 0.82,
            "invalidation": "Close below 95 for two sessions",
            "stop_loss": 95.0,
            "reason": "Trend and volume confirm a controlled entry.",
            "risk_summary": "Gap risk if earnings surprise.",
            "plan_quality": "complete",
            "source_type": "analysis",
            "data_quality_level": "high",
            "evidence": [{"id": "e1"}],
        },
    }


def _undisciplined_buy() -> dict:
    return {
        "side": "buy",
        "symbol": "600519",
        "trade_date": "2024-06-03",
        "position_weight_pct": 55.0,
        "concentration_alert_pct": 35.0,
        **_SAME_PNL,
        # No linked signal: no analysis support, unverifiable risk gate, oversized.
    }


def test_similar_pnl_different_discipline_get_different_scores() -> None:
    good = score_paper_decision_context(_disciplined_buy())
    bad = score_paper_decision_context(_undisciplined_buy())

    assert good["score_kind"] == SCORE_KIND == "process"
    assert bad["score_kind"] == "process"
    assert good["formula_version"] == FORMULA_VERSION
    assert good["process_score"] > bad["process_score"]
    assert good["process_score"] >= 80.0
    assert bad["process_score"] <= 40.0

    # PnL fields must be recorded as ignored, not consumed.
    assert "realized_pnl_pct" in good["evidence"]["ignored_return_fields"]
    assert "return_pct" in good["evidence"]["ignored_return_fields"]
    assert "realized_pnl_pct" in bad["evidence"]["ignored_return_fields"]


def test_reasons_are_human_readable_and_traceable() -> None:
    good = score_paper_decision_context(_disciplined_buy())
    bad = score_paper_decision_context(_undisciplined_buy())

    assert good["reasons"]
    assert all(item["message"] for item in good["reasons"])
    assert all(item["code"] for item in good["reasons"])
    assert any(item["code"] == "signal_linked" for item in good["reasons"])
    assert any(item["code"] == "invalidation_or_stop_present" for item in good["reasons"])

    assert any(item["code"] == "no_analysis_support" for item in bad["reasons"])
    assert any(item["code"] == "risk_gate_unverifiable" for item in bad["reasons"])
    assert "process" in good["disclaimer"].lower()
    assert "not a return" in good["disclaimer"].lower() or "not a return" in good["disclaimer"]


def test_trade_against_watch_signal_penalizes_risk_gate() -> None:
    context = _disciplined_buy()
    context["linked_signal"] = {
        **context["linked_signal"],
        "action": "watch",
        "confidence": 0.4,
    }
    scored = score_paper_decision_context(context)
    risk = scored["dimensions"]["risk_gate_compliance"]
    assert risk["score"] < 80.0
    assert any(
        reason["code"] == "trade_against_risk_gate" for reason in risk["reasons"]
    )


def test_poor_data_quality_large_size_penalizes_position_discipline() -> None:
    context = _disciplined_buy()
    context["position_weight_pct"] = 40.0
    context["linked_signal"] = {
        **context["linked_signal"],
        "data_quality_level": "poor",
    }
    scored = score_paper_decision_context(context)
    position = scored["dimensions"]["position_discipline"]
    assert position["score"] < 70.0
    assert any(
        reason["code"] == "size_not_reduced_for_gaps" for reason in position["reasons"]
    )


def test_score_ignores_outcome_fields_even_when_only_difference() -> None:
    """Identical process inputs with opposite fabricated PnL yield the same score."""
    base = _disciplined_buy()
    win = {**base, "realized_pnl_pct": 20.0, "outcome": "hit"}
    lose = {**base, "realized_pnl_pct": -20.0, "outcome": "miss"}
    assert (
        score_paper_decision_context(win)["process_score"]
        == score_paper_decision_context(lose)["process_score"]
    )


# ---------------------------------------------------------------------------
# Production account path
# ---------------------------------------------------------------------------


def _portfolio_service() -> PortfolioService:
    return PortfolioService(now_provider=lambda: _NOW)


@pytest.fixture()
def isolated_db(tmp_path):
    old_database_path = os.environ.get("DATABASE_PATH")
    old_initial_cash = os.environ.get("PAPER_PORTFOLIO_INITIAL_CASH")
    db_path = tmp_path / "paper_dq.db"
    os.environ["DATABASE_PATH"] = str(db_path)
    os.environ["PAPER_PORTFOLIO_INITIAL_CASH"] = str(_INITIAL_CASH)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    db = DatabaseManager.get_instance()
    try:
        yield db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        for key, value in (
            ("DATABASE_PATH", old_database_path),
            ("PAPER_PORTFOLIO_INITIAL_CASH", old_initial_cash),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _add_close(db, *, code: str = "600519", as_of: date = _AS_OF, close: float = 100.0) -> None:
    with db.get_session() as session:
        session.add(StockDaily(code=code, date=as_of, close=close, data_source="test"))
        session.commit()


def _create_account(service: PortfolioService, *, account_type: str) -> dict:
    return service.create_account(
        name=f"{account_type} book",
        broker=None,
        market="cn",
        base_currency="CNY",
        account_type=account_type,
    )


def _create_signal(
    db,
    *,
    as_of: date = _AS_OF,
    **overrides,
) -> dict:
    """Create a DecisionSignal and pin created_at onto the trade lookback window."""

    payload = {
        "stock_code": "600519",
        "stock_name": "贵州茅台",
        "market": "cn",
        "source_type": "analysis",
        "source_report_id": 9001,
        "trace_id": "trace-paper-dq",
        "market_phase": "postmarket",
        "trigger_source": "api",
        "action": "buy",
        "confidence": 0.8,
        "score": 75,
        "horizon": "3d",
        "invalidation": "Break 90",
        "stop_loss": 90.0,
        "reason": "Supported entry for paper process quality",
        "risk_summary": "Earnings gap risk",
        "plan_quality": "complete",
    }
    payload.update(overrides)
    item = DecisionSignalService(db_manager=db).create_signal(payload)["item"]
    # Production lookback is by trade_date; pin created_at into that window.
    with db.get_session() as session:
        row = session.get(DecisionSignalRecord, int(item["id"]))
        assert row is not None
        row.created_at = datetime.combine(as_of, time(12, 0, 0))
        session.commit()
    item["created_at"] = datetime.combine(as_of, time(12, 0, 0)).isoformat()
    return item


def _error_code(response) -> str:
    payload = response.json()
    if isinstance(payload, dict):
        if isinstance(payload.get("detail"), dict) and payload["detail"].get("error"):
            return str(payload["detail"]["error"])
        if payload.get("error"):
            return str(payload["error"])
    return ""


def test_score_paper_account_rejects_real_account(isolated_db) -> None:
    service = _portfolio_service()
    real = _create_account(service, account_type="real")
    scorer = PaperDecisionQualityService(portfolio_service=service)

    with pytest.raises(PaperAccountRequiredError):
        scorer.score_paper_account(account_id=real["id"])


def test_score_paper_account_rejects_missing_account(isolated_db) -> None:
    service = _portfolio_service()
    scorer = PaperDecisionQualityService(portfolio_service=service)

    with pytest.raises(PaperAccountNotFoundError):
        scorer.score_paper_account(account_id=999999)


def test_score_paper_account_links_signal_and_uses_trade_date_equity(
    isolated_db,
) -> None:
    service = _portfolio_service()
    paper = PaperPortfolioService(service)
    account = _create_account(service, account_type="paper")
    _add_close(isolated_db, close=100.0)
    signal = _create_signal(isolated_db)

    # Ensure signal is visible in the lookback window for trade date.
    trade = paper.record_paper_trade(
        account_id=account["id"],
        symbol="600519",
        trade_date=_AS_OF,
        side="buy",
        quantity=100,  # 10_000 notional on 100_000 cash book
        price=100.0,
    )

    report = PaperDecisionQualityService(portfolio_service=service).score_paper_account(
        account_id=account["id"]
    )

    assert report["score_kind"] == "process"
    assert report["formula_version"] == FORMULA_VERSION
    assert report["account_type"] == "paper"
    assert report["sample_size"] == 1
    item = report["items"][0]
    assert item["trade_id"] == trade["id"]
    assert item["linked_signal_id"] == signal["id"]
    assert item["process_score"] >= 70.0
    assert item["evidence"]["equity_basis"] == "trade_date_snapshot"
    assert item["evidence"]["equity_as_of"] is not None
    assert item["evidence"]["equity_as_of"] > 0
    assert item["evidence"]["signal_candidate_count"] >= 1
    assert item["evidence"]["ignored_return_fields"] == []


def test_score_paper_account_marks_ambiguous_signal_linkage(isolated_db) -> None:
    service = _portfolio_service()
    paper = PaperPortfolioService(service)
    account = _create_account(service, account_type="paper")
    _add_close(isolated_db, close=100.0)
    _create_signal(isolated_db, source_report_id=9001, trace_id="trace-a", reason="First plan")
    _create_signal(
        isolated_db,
        source_report_id=9002,
        trace_id="trace-b",
        reason="Second plan",
        confidence=0.9,
    )
    paper.record_paper_trade(
        account_id=account["id"],
        symbol="600519",
        trade_date=_AS_OF,
        side="buy",
        quantity=10,
        price=100.0,
    )

    report = PaperDecisionQualityService(portfolio_service=service).score_paper_account(
        account_id=account["id"]
    )
    evidence = report["items"][0]["evidence"]
    assert evidence["signal_candidate_count"] >= 2
    assert evidence["signal_linkage_ambiguous"] is True
    assert evidence["linked_signal_id"] is not None


def test_http_endpoint_paper_gate_and_score_smoke(tmp_path) -> None:
    """HTTP smoke uses the same isolated env pattern as paper portfolio API tests."""

    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    env_path = tmp_path / ".env"
    db_path = tmp_path / "paper_dq_api.db"
    env_path.write_text(
        "\n".join(
            [
                "ADMIN_AUTH_ENABLED=false",
                f"DATABASE_PATH={db_path}",
                f"PAPER_PORTFOLIO_INITIAL_CASH={_INITIAL_CASH}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    old_env = {
        "ENV_FILE": os.environ.get("ENV_FILE"),
        "DATABASE_PATH": os.environ.get("DATABASE_PATH"),
        "PAPER_PORTFOLIO_INITIAL_CASH": os.environ.get("PAPER_PORTFOLIO_INITIAL_CASH"),
    }
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
    os.environ["PAPER_PORTFOLIO_INITIAL_CASH"] = str(_INITIAL_CASH)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    app = create_app(static_dir=Path(static_dir))
    client = TestClient(app)
    db = DatabaseManager.get_instance()
    try:
        today = date.today()
        real = client.post(
            "/api/v1/portfolio/accounts",
            json={"name": "Real", "market": "cn", "account_type": "real"},
        )
        assert real.status_code == 200, real.text
        paper = client.post(
            "/api/v1/portfolio/accounts",
            json={"name": "Paper", "market": "cn", "account_type": "paper"},
        )
        assert paper.status_code == 200, paper.text
        paper_id = paper.json()["id"]
        real_id = real.json()["id"]

        _add_close(db, as_of=today, close=100.0)
        _create_signal(db, as_of=today, source_report_id=9100, trace_id="http-trace")
        traded = client.post(
            f"/api/v1/portfolio/accounts/{paper_id}/paper-trades",
            json={
                "symbol": "600519",
                "trade_date": today.isoformat(),
                "side": "buy",
                "quantity": 10,
                "price": 100.0,
            },
        )
        assert traded.status_code == 200, traded.text

        denied = client.get(
            f"/api/v1/portfolio/accounts/{real_id}/paper-decision-quality"
        )
        assert denied.status_code == 400, denied.text
        assert _error_code(denied) == "paper_account_required"

        missing = client.get("/api/v1/portfolio/accounts/999999/paper-decision-quality")
        assert missing.status_code == 404, missing.text
        assert _error_code(missing) == "account_not_found"

        ok = client.get(f"/api/v1/portfolio/accounts/{paper_id}/paper-decision-quality")
        assert ok.status_code == 200, ok.text
        body = ok.json()
        assert body["score_kind"] == "process"
        assert body["formula_version"] == FORMULA_VERSION
        assert body["sample_size"] == 1
        assert body["items"][0]["evidence"]["equity_basis"] == "trade_date_snapshot"
        assert body["items"][0]["linked_signal_id"] is not None
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_date_range_validation(isolated_db) -> None:
    service = _portfolio_service()
    account = _create_account(service, account_type="paper")
    scorer = PaperDecisionQualityService(portfolio_service=service)

    with pytest.raises(ValueError, match="date_from"):
        scorer.score_paper_account(
            account_id=account["id"],
            date_from=_AS_OF,
            date_to=_AS_OF - timedelta(days=1),
        )
