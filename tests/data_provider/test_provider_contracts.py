# -*- coding: utf-8 -*-
"""Offline provider contract tests on recorded fixtures.

These tests feed recorded raw payloads through each fetcher's parse / normalize
path and assert the shape analysis actually consumes. They are offline and must
run inside the blocking gate (not marked ``network``).

Why each assertion exists is documented next to it: the consumer is
``src/stock_analyzer.py`` (daily close/volume) and
``UnifiedRealtimeQuote`` / ``DataFetcherManager`` (realtime + market routing).

Refresh live fixtures with ``scripts/refresh_provider_fixtures.py`` (network only).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from data_provider.akshare_fetcher import (
    AkshareFetcher,
    _to_sina_tx_symbol,
)
from data_provider.akshare_parts.realtime_cache import store_a_share_snapshot
from data_provider.base import STANDARD_COLUMNS
from data_provider.realtime_types import RealtimeSource
from data_provider.tencent_fetcher import (
    TencentFetcher,
    _extract_kline_rows,
    _to_tencent_symbol,
)
from data_provider.tushare_fetcher import TushareFetcher, _TushareHttpClient
from data_provider.yfinance_fetcher import YfinanceFetcher

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "provider_contracts"

# Columns the analysis path requires after BaseFetcher._clean_data.
# stock_analyzer uses close for MA/MACD and volume for volume_ratio_5d.
DAILY_REQUIRED = list(STANDARD_COLUMNS)


def _load_json(name: str) -> dict[str, Any]:
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _load_text(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


def _frame_from_table(payload: dict[str, Any]) -> pd.DataFrame:
    return pd.DataFrame(payload["rows"], columns=payload["columns"])


def _assert_daily_contract(df: pd.DataFrame, *, min_rows: int = 1) -> None:
    """Assert the normalized daily shape analysis depends on."""
    # Why: STANDARD_COLUMNS is the BaseFetcher contract; missing columns break MA/volume.
    for column in DAILY_REQUIRED:
        assert column in df.columns, f"missing daily column {column!r}"

    assert len(df) >= min_rows, "daily fixture must yield at least one bar"

    # Why: stock_analyzer does float(latest['close']) and volume ratios.
    assert pd.api.types.is_numeric_dtype(df["close"]) or all(
        pd.notna(pd.to_numeric(df["close"], errors="coerce"))
    )
    closes = pd.to_numeric(df["close"], errors="coerce")
    volumes = pd.to_numeric(df["volume"], errors="coerce")
    assert closes.notna().all() and (closes > 0).all()
    assert volumes.notna().all() and (volumes >= 0).all()

    # Why: _clean_data sorts ascending; consumers use iloc[-1] as latest bar.
    dates = pd.to_datetime(df["date"], errors="coerce")
    assert dates.notna().all()
    assert dates.is_monotonic_increasing


def _assert_realtime_basic(quote, *, code: str, require_pre_close: bool = True) -> None:
    """Assert UnifiedRealtimeQuote fields used by has_basic_data and reports.

    EM spot currently maps 今开/最高/最低 but does not populate ``pre_close``
    even when 昨收 is present in the raw row; Sina/Tencent always set it.
    """
    assert quote is not None
    assert quote.code == code
    # Why: has_basic_data() requires price > 0 for analysis to treat quote as usable.
    assert quote.price is not None and quote.price > 0
    # Why: change_pct / OHLC feed snapshot and report templates.
    assert quote.change_pct is not None
    assert quote.open_price is not None
    assert quote.high is not None
    assert quote.low is not None
    if require_pre_close:
        # Why: Sina/Tencent derive change from pre_close; reports surface 昨收.
        assert quote.pre_close is not None
    assert quote.volume is not None and quote.volume >= 0
    assert quote.name


class _AlwaysAvailableBreaker:
    def is_available(self, source: str) -> bool:
        return True

    def record_success(self, source: str) -> None:
        return None

    def record_failure(self, source: str, error=None) -> None:
        return None


class _HttpTextResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.status_code = status_code
        self.text = text
        self.encoding = None


# ---------------------------------------------------------------------------
# Daily contracts
# ---------------------------------------------------------------------------


def test_akshare_em_daily_normalize_contract() -> None:
    """Eastmoney Chinese-column hist → STANDARD_COLUMNS."""
    payload = _load_json("akshare_em_daily.json")
    raw = _frame_from_table(payload)
    fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)

    normalized = fetcher._normalize_data(raw, "600519")
    cleaned = fetcher._clean_data(normalized)

    _assert_daily_contract(cleaned, min_rows=3)
    # Why: code column is attached for multi-stock pipelines and diagnostics.
    assert "code" in normalized.columns
    assert set(normalized["code"].unique()) == {"600519"}
    # Why: EM maps 收盘 → close; first frozen bar close is part of the fixture contract.
    assert float(cleaned.iloc[0]["close"]) == pytest.approx(1695.5)


def test_akshare_sina_daily_rename_and_normalize_contract() -> None:
    """Sina English daily columns are renamed then normalized like production."""
    payload = _load_json("akshare_sina_daily.json")
    raw_english = _frame_from_table(payload)
    fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)

    # Mirror _fetch_stock_data_sina rename boundary without network.
    renamed = raw_english.rename(
        columns={
            "date": "日期",
            "open": "开盘",
            "high": "最高",
            "low": "最低",
            "close": "收盘",
            "volume": "成交量",
            "amount": "成交额",
        }
    )
    renamed["涨跌幅"] = renamed["收盘"].pct_change() * 100
    renamed["涨跌幅"] = renamed["涨跌幅"].fillna(0)

    cleaned = fetcher._clean_data(fetcher._normalize_data(renamed, "000001"))
    _assert_daily_contract(cleaned, min_rows=3)
    assert float(cleaned.iloc[0]["close"]) == pytest.approx(10.5)
    # Why: Sina volume is already shares; must remain positive for volume_ratio_5d.
    assert float(cleaned.iloc[0]["volume"]) == pytest.approx(1234500.0)


def test_tencent_daily_kline_parse_contract() -> None:
    """Tencent fqkline JSON → lots→shares volume + STANDARD_COLUMNS."""
    payload = _load_json("tencent_daily_kline.json")["payload"]
    rows = _extract_kline_rows(payload, symbol="sz000001")
    assert len(rows) == 3

    raw = pd.DataFrame(rows)
    fetcher = TencentFetcher()
    cleaned = fetcher._clean_data(fetcher._normalize_data(raw, "000001"))

    _assert_daily_contract(cleaned, min_rows=3)
    # Why: Tencent volume is in lots; parser multiplies by 100 for share-scale consumers.
    assert float(cleaned.iloc[0]["volume"]) == pytest.approx(1234500.0)
    assert float(cleaned.iloc[0]["close"]) == pytest.approx(10.5)
    assert float(cleaned.iloc[0]["amount"]) == pytest.approx(67890.0)


def test_tencent_daily_end_to_end_with_recorded_http_payload() -> None:
    """get_daily_data parses recorded HTTP JSON without live network."""
    fixture = _load_json("tencent_daily_kline.json")
    payload = fixture["payload"]

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return payload

    with patch("data_provider.tencent_fetcher.requests.get", return_value=FakeResponse()):
        df = TencentFetcher().get_daily_data(
            "000001",
            start_date="2026-05-01",
            end_date="2026-05-10",
        )

    _assert_daily_contract(df, min_rows=3)
    # Why: full pipeline also attaches MA / volume_ratio used by reports.
    assert "ma5" in df.columns
    assert "volume_ratio" in df.columns


def test_tushare_daily_http_and_normalize_contract() -> None:
    """Tushare Pro fields/items body → vol*100 / amount*1000 A-share scaling."""
    body = _load_json("tushare_daily_pro.json")["response"]
    client = _TushareHttpClient(token="fixture-token-not-real", timeout=5)
    response = MagicMock(status_code=200, text=json.dumps(body))

    with patch("data_provider.tushare_fetcher.safe_post", return_value=response):
        raw = client.query(
            "daily",
            ts_code="600519.SH",
            start_date="20260506",
            end_date="20260508",
        )

    assert list(raw.columns) == body["data"]["fields"]
    assert len(raw) == 3

    with patch(
        "data_provider.tushare_fetcher.get_config",
        return_value=SimpleNamespace(tushare_token=""),
    ):
        fetcher = TushareFetcher()

    cleaned = fetcher._clean_data(fetcher._normalize_data(raw, "600519"))
    _assert_daily_contract(cleaned, min_rows=3)
    # Why: A-share Tushare vol is 手; analysis volume scale is 股 (×100).
    assert float(cleaned.iloc[0]["volume"]) == pytest.approx(24567.89 * 100)
    # Why: amount is 千元 → 元 (×1000) for consistent amount consumers.
    assert float(cleaned.iloc[0]["amount"]) == pytest.approx(4156789.012 * 1000)
    # Why: trade_date YYYYMMDD must become sortable datetime dates.
    assert pd.Timestamp(cleaned.iloc[0]["date"]).strftime("%Y-%m-%d") == "2026-05-06"


def test_yfinance_daily_normalize_contract() -> None:
    """Yahoo Title-Case OHLCV → STANDARD_COLUMNS with derived pct_chg/amount."""
    payload = _load_json("yfinance_daily.json")
    raw = pd.DataFrame(payload["rows"])
    raw = raw.set_index(pd.to_datetime(raw["Date"]))
    raw = raw.drop(columns=["Date"])

    fetcher = YfinanceFetcher()
    cleaned = fetcher._clean_data(fetcher._normalize_data(raw, "AAPL"))

    _assert_daily_contract(cleaned, min_rows=3)
    assert float(cleaned.iloc[-1]["close"]) == pytest.approx(190.0)
    # Why: yfinance has no amount; fetcher estimates volume * close for STANDARD_COLUMNS.
    assert float(cleaned.iloc[-1]["amount"]) == pytest.approx(190.0 * 38890000)
    # Why: first bar pct_chg is filled 0 when no prior close exists.
    assert float(cleaned.iloc[0]["pct_chg"]) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Realtime contracts
# ---------------------------------------------------------------------------


def test_akshare_em_spot_realtime_contract() -> None:
    """EM spot row via cache → UnifiedRealtimeQuote with valuation fields."""
    from data_provider.akshare_parts import realtime_cache as _rc

    payload = _load_json("akshare_em_spot.json")
    snapshot = _frame_from_table(payload)
    previous = (_rc._realtime_cache.get("data"), _rc._realtime_cache.get("timestamp"))
    store_a_share_snapshot(snapshot)

    try:
        fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)
        with patch(
            "data_provider.akshare_fetcher.get_realtime_circuit_breaker",
            return_value=_AlwaysAvailableBreaker(),
        ):
            quote = fetcher.get_realtime_quote("600519", source="em")

        # Why: EM path does not set pre_close today; assert the fields it does map.
        _assert_realtime_basic(quote, code="600519", require_pre_close=False)
        assert quote.source == RealtimeSource.AKSHARE_EM
        # Why: EM is the only free source that routinely supplies PE/PB/量比 for reports.
        assert quote.volume_ratio is not None
        assert quote.pe_ratio is not None
        assert quote.pb_ratio is not None
        assert quote.turnover_rate is not None
        assert float(quote.price) == pytest.approx(1695.5)
    finally:
        # Restore process-local cache so suite order does not leak fixture rows.
        _rc._realtime_cache["data"] = previous[0]
        _rc._realtime_cache["timestamp"] = previous[1]


def test_akshare_sina_realtime_text_contract() -> None:
    """Sina hq.sinajs.cn text body → core quote fields (no PE/量比)."""
    body = _load_text("akshare_sina_realtime.txt")
    fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)

    with patch(
        "data_provider.akshare_fetcher.get_realtime_circuit_breaker",
        return_value=_AlwaysAvailableBreaker(),
    ), patch(
        "data_provider.akshare_fetcher.requests.get",
        return_value=_HttpTextResponse(body),
    ):
        quote = fetcher.get_realtime_quote("600519", source="sina")

    _assert_realtime_basic(quote, code="600519")
    assert quote.source == RealtimeSource.AKSHARE_SINA
    assert float(quote.price) == pytest.approx(1695.5)
    assert quote.volume == 2456789
    assert float(quote.amount) == pytest.approx(4156789012.50)


def test_akshare_tencent_realtime_text_contract() -> None:
    """Tencent qt.gtimg.cn text body → quote + turnover/volume_ratio fields."""
    body = _load_text("akshare_tencent_realtime.txt")
    fetcher = AkshareFetcher(sleep_min=0, sleep_max=0)

    with patch(
        "data_provider.akshare_fetcher.get_realtime_circuit_breaker",
        return_value=_AlwaysAvailableBreaker(),
    ), patch(
        "data_provider.akshare_fetcher.requests.get",
        return_value=_HttpTextResponse(body),
    ):
        quote = fetcher.get_realtime_quote("600519", source="tencent")

    _assert_realtime_basic(quote, code="600519")
    assert quote.source == RealtimeSource.TENCENT
    assert float(quote.price) == pytest.approx(1695.50)
    assert quote.volume is not None and quote.volume > 0
    # Why: Tencent path supplies 换手率 / 量比 used when EM is rate-limited.
    assert quote.turnover_rate is not None
    assert quote.volume_ratio is not None
    assert float(quote.amount) == pytest.approx(4156789012.50)


# ---------------------------------------------------------------------------
# Market routing contracts (symbol forms analysis routing depends on)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("600519", "sh600519"),
        ("000001", "sz000001"),
        ("920748", "bj920748"),
        ("512400", "sh512400"),
    ],
)
def test_a_share_sina_tencent_symbol_routing(code: str, expected: str) -> None:
    # Why: wrong SH/SZ/BJ prefix yields empty realtime/history from Sina/Tencent.
    assert _to_sina_tx_symbol(code) == expected
    assert _to_tencent_symbol(code) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("600519", "600519.SS"),
        ("000001", "000001.SZ"),
        ("hk00700", "0700.HK"),
        ("AAPL", "AAPL"),
    ],
)
def test_yfinance_symbol_routing(code: str, expected: str) -> None:
    # Why: Yahoo market suffixes determine whether CN/HK/US history resolves.
    assert YfinanceFetcher()._convert_stock_code(code) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("600519", "600519.SH"),
        ("000001", "000001.SZ"),
        ("920748", "920748.BJ"),
    ],
)
def test_tushare_symbol_routing(code: str, expected: str) -> None:
    with patch(
        "data_provider.tushare_fetcher.get_config",
        return_value=SimpleNamespace(tushare_token=""),
    ):
        fetcher = TushareFetcher()
    # Why: Tushare Pro requires exchange-qualified ts_code; wrong market 404s silently empty.
    assert fetcher._convert_stock_code(code) == expected


def test_fixture_manifest_lists_all_recorded_files() -> None:
    """Guard against accidental fixture file drops without manifest update."""
    manifest = _load_json("manifest.json")
    for entry in manifest["fixtures"]:
        path = FIXTURE_DIR / entry["file"]
        assert path.is_file(), f"missing fixture file {entry['file']}"
    # Why: daily contract list must stay aligned with STANDARD_COLUMNS.
    assert manifest["consumer_contract"]["daily_columns"] == DAILY_REQUIRED
