#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Refresh recorded data-provider contract fixtures (network required).

This script is intentionally **not** part of the offline CI gate. Run it
manually or from the nightly ``network-smoke`` workflow to re-capture raw
provider payloads. Review shape diffs before committing updates under
``tests/fixtures/provider_contracts/``.

Examples:

    python scripts/refresh_provider_fixtures.py --write
    python scripts/refresh_provider_fixtures.py --output-dir /tmp/provider_contracts_refresh --skip-unavailable
    python scripts/refresh_provider_fixtures.py --providers tencent,yfinance
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "provider_contracts"

# Keep refresh windows short to limit payload size and upstream load.
_DAILY_LOOKBACK_DAYS = 10


def _log(message: str) -> None:
    print(message, flush=True)


def _ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_text(path: Path, text: str) -> None:
    path.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")


def _date_window() -> tuple[str, str]:
    end = datetime.utcnow().date()
    start = end - timedelta(days=_DAILY_LOOKBACK_DAYS)
    return start.isoformat(), end.isoformat()


def _sanitize_mapping(value: Any) -> Any:
    """Drop token-like keys recursively; fixtures must never store secrets."""
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"token", "api_key", "apikey", "authorization", "password", "secret"}:
                continue
            cleaned[str(key)] = _sanitize_mapping(item)
        return cleaned
    if isinstance(value, list):
        return [_sanitize_mapping(item) for item in value]
    return value


def refresh_tencent_daily(output_dir: Path) -> Path:
    import requests

    symbol = "sz000001"
    start, end = _date_window()
    lookback = min(30, _DAILY_LOOKBACK_DAYS * 2)
    url = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    response = requests.get(
        url,
        params={"param": f"{symbol},day,{start},{end},{lookback},qfq"},
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"},
        timeout=15,
    )
    response.raise_for_status()
    payload = response.json()
    out = {
        "meta": {
            "provider": "tencent",
            "endpoint": url,
            "symbol": symbol,
            "recorded_at": datetime.utcnow().isoformat() + "Z",
            "recorded_note": "Live Tencent fqkline capture; sanitized of credentials.",
        },
        "payload": _sanitize_mapping(payload),
    }
    path = output_dir / "tencent_daily_kline.json"
    _write_json(path, out)
    return path


def refresh_akshare_em_daily(output_dir: Path) -> Path:
    import akshare as ak

    symbol = "600519"
    start, end = _date_window()
    df = ak.stock_zh_a_hist(
        symbol=symbol,
        period="daily",
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust="qfq",
    )
    if df is None or df.empty:
        raise RuntimeError("ak.stock_zh_a_hist returned empty data")
    # Keep a small sample for the contract suite.
    sample = df.tail(5)
    out = {
        "meta": {
            "provider": "akshare",
            "api": "stock_zh_a_hist",
            "symbol": symbol,
            "adjust": "qfq",
            "recorded_at": datetime.utcnow().isoformat() + "Z",
            "recorded_note": "Live Eastmoney daily capture via AkShare.",
        },
        "columns": [str(c) for c in sample.columns.tolist()],
        "rows": json.loads(sample.to_json(orient="values", force_ascii=False)),
    }
    path = output_dir / "akshare_em_daily.json"
    _write_json(path, out)
    return path


def refresh_akshare_sina_daily(output_dir: Path) -> Path:
    import akshare as ak

    symbol = "sz000001"
    start, end = _date_window()
    df = ak.stock_zh_a_daily(
        symbol=symbol,
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
        adjust="qfq",
    )
    if df is None or df.empty:
        raise RuntimeError("ak.stock_zh_a_daily returned empty data")
    sample = df.tail(5)
    # Persist native English columns (pre-rename) for the offline sina path test.
    out = {
        "meta": {
            "provider": "akshare",
            "api": "stock_zh_a_daily",
            "symbol": symbol,
            "adjust": "qfq",
            "recorded_at": datetime.utcnow().isoformat() + "Z",
            "recorded_note": "Live Sina daily capture via AkShare (English columns).",
        },
        "columns": [str(c) for c in sample.columns.tolist()],
        "rows": json.loads(sample.to_json(orient="values", force_ascii=False)),
    }
    path = output_dir / "akshare_sina_daily.json"
    _write_json(path, out)
    return path


def refresh_akshare_em_spot(output_dir: Path) -> Path:
    import akshare as ak

    symbol = "600519"
    df = ak.stock_zh_a_spot_em()
    if df is None or df.empty:
        raise RuntimeError("ak.stock_zh_a_spot_em returned empty data")
    row = df[df["代码"].astype(str) == symbol]
    if row.empty:
        raise RuntimeError(f"symbol {symbol} missing from EM spot snapshot")
    sample = row.head(1)
    out = {
        "meta": {
            "provider": "akshare",
            "api": "stock_zh_a_spot_em",
            "symbol": symbol,
            "recorded_at": datetime.utcnow().isoformat() + "Z",
            "recorded_note": "Single-row EM spot capture for offline realtime contract.",
        },
        "columns": [str(c) for c in sample.columns.tolist()],
        "rows": json.loads(sample.to_json(orient="values", force_ascii=False)),
    }
    path = output_dir / "akshare_em_spot.json"
    _write_json(path, out)
    return path


def refresh_akshare_sina_realtime(output_dir: Path) -> Path:
    import requests

    symbol = "sh600519"
    url = f"http://hq.sinajs.cn/list={symbol}"
    response = requests.get(
        url,
        headers={
            "Referer": "http://finance.sina.com.cn",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=10,
    )
    response.encoding = "gbk"
    response.raise_for_status()
    text = response.text.strip()
    if not text or '=""' in text:
        raise RuntimeError("Sina realtime returned empty quote")
    path = output_dir / "akshare_sina_realtime.txt"
    _write_text(path, text)
    return path


def refresh_akshare_tencent_realtime(output_dir: Path) -> Path:
    import requests

    symbol = "sh600519"
    url = f"http://qt.gtimg.cn/q={symbol}"
    response = requests.get(
        url,
        headers={
            "Referer": "http://finance.qq.com",
            "User-Agent": "Mozilla/5.0",
        },
        timeout=10,
    )
    response.encoding = "gbk"
    response.raise_for_status()
    text = response.text.strip()
    if not text or '=""' in text:
        raise RuntimeError("Tencent realtime returned empty quote")
    path = output_dir / "akshare_tencent_realtime.txt"
    _write_text(path, text)
    return path


def refresh_tushare_daily(output_dir: Path) -> Path:
    token = (os.getenv("TUSHARE_TOKEN") or "").strip()
    if not token:
        raise RuntimeError("TUSHARE_TOKEN is required to refresh Tushare fixtures")

    # Import after path setup so local package resolves.
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    from data_provider.tushare_fetcher import _TushareHttpClient, _resolve_tushare_api_url

    start, end = _date_window()
    client = _TushareHttpClient(token=token, timeout=30, api_url=_resolve_tushare_api_url())
    df = client.query(
        "daily",
        ts_code="600519.SH",
        start_date=start.replace("-", ""),
        end_date=end.replace("-", ""),
    )
    if df is None or df.empty:
        raise RuntimeError("Tushare daily returned empty data")
    sample = df.tail(5)
    # Reconstruct the HTTP body shape used by _TushareHttpClient (fields + items).
    fields = [str(c) for c in sample.columns.tolist()]
    items = json.loads(sample.to_json(orient="values", force_ascii=False))
    out = {
        "meta": {
            "provider": "tushare",
            "api_name": "daily",
            "ts_code": "600519.SH",
            "recorded_at": datetime.utcnow().isoformat() + "Z",
            "recorded_note": "Live Tushare Pro daily capture; token never written.",
        },
        "response": {
            "code": 0,
            "msg": "",
            "data": {
                "fields": fields,
                "items": items,
            },
        },
    }
    path = output_dir / "tushare_daily_pro.json"
    _write_json(path, _sanitize_mapping(out))
    return path


def refresh_yfinance_daily(output_dir: Path) -> Path:
    import yfinance as yf

    ticker = "AAPL"
    start, end = _date_window()
    df = yf.download(
        tickers=ticker,
        start=start,
        end=end,
        progress=False,
        auto_adjust=True,
        multi_level_index=False,
    )
    if df is None or df.empty:
        raise RuntimeError("yfinance.download returned empty data")
    sample = df.tail(5).reset_index()
    # Normalize date column name for the fixture schema.
    date_col = sample.columns[0]
    sample = sample.rename(columns={date_col: "Date"})
    sample["Date"] = sample["Date"].astype(str).str.slice(0, 10)
    keep = [c for c in ["Date", "Open", "High", "Low", "Close", "Volume"] if c in sample.columns]
    sample = sample[keep]
    out = {
        "meta": {
            "provider": "yfinance",
            "ticker": ticker,
            "recorded_at": datetime.utcnow().isoformat() + "Z",
            "recorded_note": "Live Yahoo Finance daily capture.",
        },
        "index_name": "Date",
        "columns": [c for c in keep if c != "Date"],
        "rows": json.loads(sample.to_json(orient="records", force_ascii=False)),
    }
    path = output_dir / "yfinance_daily.json"
    _write_json(path, out)
    return path


PROVIDERS: Dict[str, Callable[[Path], Path]] = {
    "tencent": refresh_tencent_daily,
    "akshare_em_daily": refresh_akshare_em_daily,
    "akshare_sina_daily": refresh_akshare_sina_daily,
    "akshare_em_spot": refresh_akshare_em_spot,
    "akshare_sina_realtime": refresh_akshare_sina_realtime,
    "akshare_tencent_realtime": refresh_akshare_tencent_realtime,
    "tushare": refresh_tushare_daily,
    "yfinance": refresh_yfinance_daily,
}


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh recorded provider contract fixtures (network required)."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to write fixtures (default: tests/fixtures/provider_contracts when --write).",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Write into the repo fixture directory (same as --output-dir default path).",
    )
    parser.add_argument(
        "--providers",
        type=str,
        default="all",
        help=f"Comma-separated providers or 'all'. Choices: {','.join(PROVIDERS)}",
    )
    parser.add_argument(
        "--skip-unavailable",
        action="store_true",
        help="Continue when a provider fails (record failure; exit 0 if any succeeded).",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)

    if args.output_dir is not None:
        output_dir = args.output_dir
    elif args.write:
        output_dir = DEFAULT_FIXTURE_DIR
    else:
        _log(
            "Refusing to write: pass --write to update repo fixtures, "
            "or --output-dir PATH for a separate capture directory."
        )
        return 2

    _ensure_dir(output_dir)

    if args.providers.strip().lower() == "all":
        selected = list(PROVIDERS.keys())
    else:
        selected = [part.strip() for part in args.providers.split(",") if part.strip()]
        unknown = [name for name in selected if name not in PROVIDERS]
        if unknown:
            _log(f"Unknown providers: {', '.join(unknown)}")
            return 2

    succeeded: List[str] = []
    failed: List[str] = []

    for name in selected:
        _log(f"[refresh] {name} ...")
        try:
            path = PROVIDERS[name](output_dir)
            _log(f"[refresh] {name} ok -> {path}")
            succeeded.append(name)
        except Exception as exc:  # noqa: BLE001 - network script; report and continue
            _log(f"[refresh] {name} failed: {type(exc).__name__}: {exc}")
            failed.append(name)
            if not args.skip_unavailable:
                return 1

    _log(
        f"[refresh] done: succeeded={len(succeeded)} failed={len(failed)} "
        f"output_dir={output_dir}"
    )
    if failed and not succeeded:
        return 1
    if failed and args.skip_unavailable:
        return 0
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
