# -*- coding: utf-8 -*-
"""Tests for the paper trading portfolio layer (Issue #370)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.app import create_app
from src.config import Config
from src.services.paper_portfolio_service import (
    PaperAccountRequiredError,
    PaperInsufficientCashError,
    PaperPortfolioService,
    PaperQuoteUnavailableError,
)
from src.services.portfolio_service import PortfolioService
from src.storage import DatabaseManager, StockDaily


_INITIAL_CASH = 100000.0
_NOW = datetime(2024, 6, 3)
_AS_OF = _NOW.date()


def _service() -> PortfolioService:
    """A PortfolioService with a fixed clock so paper cash is seeded on _AS_OF."""
    return PortfolioService(now_provider=lambda: _NOW)


@pytest.fixture()
def isolated_db(tmp_path):
    old_database_path = os.environ.get("DATABASE_PATH")
    old_initial_cash = os.environ.get("PAPER_PORTFOLIO_INITIAL_CASH")
    db_path = tmp_path / "paper.db"
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


def _account_cash(service: PortfolioService, account_id: int, *, as_of: date = _AS_OF) -> float:
    snapshot = service.get_portfolio_snapshot(
        account_id=account_id, as_of=as_of, include_realtime=False
    )
    entry = next(a for a in snapshot["accounts"] if a["account_id"] == account_id)
    return float(entry["total_cash"])


def _create_account(service: PortfolioService, *, account_type: str) -> dict:
    return service.create_account(
        name=f"{account_type} book",
        broker=None,
        market="cn",
        base_currency="CNY",
        account_type=account_type,
    )


def test_create_paper_account_seeds_cash_and_kind(isolated_db) -> None:
    service = _service()
    account = _create_account(service, account_type="paper")

    assert account["account_type"] == "paper"
    assert _account_cash(service, account["id"]) == pytest.approx(_INITIAL_CASH)


def test_create_real_account_defaults_and_no_seeded_cash(isolated_db) -> None:
    service = _service()
    account = service.create_account(
        name="real book", broker=None, market="cn", base_currency="CNY"
    )

    assert account["account_type"] == "real"
    assert _account_cash(service, account["id"]) == pytest.approx(0.0)


def test_list_accounts_surfaces_account_type(isolated_db) -> None:
    service = _service()
    paper = _create_account(service, account_type="paper")
    real = _create_account(service, account_type="real")

    by_id = {item["id"]: item["account_type"] for item in service.list_accounts()}
    assert by_id[paper["id"]] == "paper"
    assert by_id[real["id"]] == "real"


def test_paper_trade_autofills_latest_close(isolated_db) -> None:
    service = _service()
    paper = PaperPortfolioService(service)
    account = _create_account(service, account_type="paper")
    _add_close(isolated_db, close=100.0)

    result = paper.record_paper_trade(
        account_id=account["id"],
        symbol="600519",
        trade_date=_AS_OF,
        side="buy",
        quantity=10,
    )

    assert result["price"] == pytest.approx(100.0)
    assert result["price_source"] == "latest_close"
    assert _account_cash(service, account["id"]) == pytest.approx(_INITIAL_CASH - 1000.0)


def test_paper_trade_uses_explicit_price(isolated_db) -> None:
    service = _service()
    paper = PaperPortfolioService(service)
    account = _create_account(service, account_type="paper")

    result = paper.record_paper_trade(
        account_id=account["id"],
        symbol="600519",
        trade_date=_AS_OF,
        side="buy",
        quantity=10,
        price=50.0,
    )

    assert result["price"] == pytest.approx(50.0)
    assert result["price_source"] == "manual"


def test_paper_buy_rejected_when_insufficient_cash(isolated_db) -> None:
    service = _service()
    paper = PaperPortfolioService(service)
    account = _create_account(service, account_type="paper")
    _add_close(isolated_db, close=100.0)

    with pytest.raises(PaperInsufficientCashError):
        paper.record_paper_trade(
            account_id=account["id"],
            symbol="600519",
            trade_date=_AS_OF,
            side="buy",
            quantity=2000,  # 2000 * 100 = 200000 > 100000 initial cash
        )


def test_paper_trade_requires_paper_account(isolated_db) -> None:
    service = _service()
    paper = PaperPortfolioService(service)
    real = _create_account(service, account_type="real")
    _add_close(isolated_db, close=100.0)

    with pytest.raises(PaperAccountRequiredError):
        paper.record_paper_trade(
            account_id=real["id"],
            symbol="600519",
            trade_date=_AS_OF,
            side="buy",
            quantity=1,
        )


def test_paper_trade_quote_unavailable(isolated_db) -> None:
    service = _service()
    paper = PaperPortfolioService(service)
    account = _create_account(service, account_type="paper")

    with pytest.raises(PaperQuoteUnavailableError):
        paper.record_paper_trade(
            account_id=account["id"],
            symbol="600519",
            trade_date=_AS_OF,
            side="buy",
            quantity=1,
        )


def test_paper_positions_and_pnl_tracked_via_snapshot(isolated_db) -> None:
    service = _service()
    paper = PaperPortfolioService(service)
    account = _create_account(service, account_type="paper")
    _add_close(isolated_db, close=100.0)

    paper.record_paper_trade(
        account_id=account["id"],
        symbol="600519",
        trade_date=_AS_OF,
        side="buy",
        quantity=10,
        price=100.0,
    )
    _add_close(isolated_db, as_of=date(2024, 6, 4), close=120.0)

    snapshot = service.get_portfolio_snapshot(
        account_id=account["id"], as_of=date(2024, 6, 4), include_realtime=False
    )
    entry = next(a for a in snapshot["accounts"] if a["account_id"] == account["id"])
    positions = {p["symbol"]: p for p in entry["positions"]}
    assert positions["600519"]["quantity"] == pytest.approx(10.0)
    assert entry["unrealized_pnl"] == pytest.approx(200.0)  # (120 - 100) * 10


@contextmanager
def _client(tmp_path):
    old_env_file = os.environ.get("ENV_FILE")
    old_database_path = os.environ.get("DATABASE_PATH")
    old_initial_cash = os.environ.get("PAPER_PORTFOLIO_INITIAL_CASH")
    env_path = tmp_path / ".env"
    db_path = tmp_path / "paper_api.db"
    static_dir = tmp_path / "empty-static"
    static_dir.mkdir()
    env_path.write_text(
        "\n".join(
            [
                "STOCK_LIST=600519",
                "GEMINI_API_KEY=test",
                "ADMIN_AUTH_ENABLED=false",
                f"DATABASE_PATH={db_path}",
                f"PAPER_PORTFOLIO_INITIAL_CASH={_INITIAL_CASH}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    os.environ["ENV_FILE"] = str(env_path)
    os.environ["DATABASE_PATH"] = str(db_path)
    os.environ["PAPER_PORTFOLIO_INITIAL_CASH"] = str(_INITIAL_CASH)
    Config.reset_instance()
    DatabaseManager.reset_instance()
    app = create_app(static_dir=Path(static_dir))
    client = TestClient(app)
    db = DatabaseManager.get_instance()
    try:
        yield client, db
    finally:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        for key, value in (
            ("ENV_FILE", old_env_file),
            ("DATABASE_PATH", old_database_path),
            ("PAPER_PORTFOLIO_INITIAL_CASH", old_initial_cash),
        ):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_paper_trading_api_round_trip(tmp_path) -> None:
    with _client(tmp_path) as (client, db):
        created = client.post(
            "/api/v1/portfolio/accounts",
            json={"name": "Sim", "market": "cn", "account_type": "paper"},
        )
        assert created.status_code == 200, created.text
        account = created.json()
        assert account["account_type"] == "paper"

        # The endpoint seeds paper cash at creation time (real "now"), so trade and
        # quote use today's date to stay on/after the funding date.
        today = date.today()
        _add_close(db, as_of=today, close=100.0)
        traded = client.post(
            f"/api/v1/portfolio/accounts/{account['id']}/paper-trades",
            json={
                "symbol": "600519",
                "trade_date": today.isoformat(),
                "side": "buy",
                "quantity": 10,
            },
        )
        assert traded.status_code == 200, traded.text
        body = traded.json()
        assert body["price"] == pytest.approx(100.0)
        assert body["price_source"] == "latest_close"
