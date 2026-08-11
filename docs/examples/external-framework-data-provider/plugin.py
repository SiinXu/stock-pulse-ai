# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Thin OpenBB → data_provider adapter (external-framework demonstration).

This package is intentionally **not** part of the default plugin load set. Copy
it under an operator-owned ``PLUGINS_DIR`` parent (or point ``PLUGINS_DIR`` at
``docs/examples``) and install OpenBB manually. StockPulse never auto-installs
plugin dependencies and never sandboxes plugin code.

Design rules (surface v1, uncompromising):

- Registers only the frozen ``data_provider`` extension point.
- Normalizes fields to the repository daily-data contract.
- Missing OpenBB dependency or upstream failure **raises** so
  ``DataFetcherManager`` can continue its eligible fallback chain; never
  returns an empty frame to pretend success.
- Network/SDK timeouts are owned by this adapter (no universal host deadline).
"""

from __future__ import annotations

from datetime import date, timedelta
from importlib.metadata import PackageNotFoundError, version as distribution_version
from io import StringIO
import json
import math
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
from typing import Any, Protocol

import numpy as np
import pandas as pd

from data_provider import DataProvider, DataProviderRegistration
from src.plugins import Plugin as BasePlugin
from src.plugins import PluginContext

# Lower priority numbers win. Stay behind typical built-ins so operators must
# deliberately prefer this adapter (pin / reorder) rather than having it steal
# traffic on first enable.
_DEFAULT_PRIORITY = 95
_DEFAULT_TIMEOUT_SECONDS = 15.0
_SUPPORTED_OPENBB_MINOR = (4, 7)
_OPENBB_WORKER_ARGUMENT = "--stockpulse-openbb-worker"
_OPENBB_WORKER_BOOTSTRAP = (
    "import runpy, sys; "
    "worker_path, worker_arg = sys.argv[1], sys.argv[2]; "
    "sys.argv = [worker_path, worker_arg]; "
    "runpy.run_path(worker_path, run_name='__main__')"
)
_REQUIRED_COLUMNS = (
    "date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "pct_chg",
)
_MISSING_OPENBB_MESSAGE = (
    "OpenBB is not installed in this environment. Install it manually "
    "(for example `pip install 'openbb>=4.7,<4.8'`) before enabling the "
    "stockpulse.openbb-data-provider plugin. StockPulse does not install "
    "plugin dependencies and does not sandbox external adapters; review the "
    "package before setting PLUGINS_DIR."
)


class OpenBBHistoricalClient(Protocol):
    """Minimal client surface used by the adapter (injectable for offline tests)."""

    def fetch_historical(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        timeout_seconds: float,
    ) -> pd.DataFrame:
        """Return a DataFrame with at least OHLCV columns (any reasonable casing)."""


class MissingOpenBBDependencyError(RuntimeError):
    """Raised when the optional OpenBB package is absent at call time."""


class OpenBBDailyDataProvider(DataProvider):
    """Map OpenBB equity historical bars onto the StockPulse daily-data contract."""

    name = "OpenBBAdapterProvider"
    priority = _DEFAULT_PRIORITY

    def __init__(
        self,
        client: OpenBBHistoricalClient | None = None,
        *,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        if not math.isfinite(float(timeout_seconds)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        self._client = client
        self._timeout_seconds = float(timeout_seconds)

    def get_daily_data(
        self,
        stock_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 30,
    ) -> pd.DataFrame:
        host_symbol = str(stock_code or "").strip()
        if not host_symbol:
            raise ValueError("stock_code is required")
        provider_symbol = to_yfinance_symbol(host_symbol)

        resolved_start, resolved_end = _resolve_window(
            start_date=start_date,
            end_date=end_date,
            days=days,
        )
        client = self._resolve_client()
        raw = client.fetch_historical(
            symbol=provider_symbol,
            start_date=resolved_start,
            end_date=resolved_end,
            timeout_seconds=self._timeout_seconds,
        )
        if raw is None:
            raise RuntimeError(
                f"OpenBB returned no payload for symbol={host_symbol!r}; "
                "failing this provider attempt so DataFetcherManager can fall back"
            )
        if not isinstance(raw, pd.DataFrame):
            raise TypeError(
                f"OpenBB historical client must return a pandas.DataFrame, got {type(raw)!r}"
            )
        if raw.empty:
            raise RuntimeError(
                f"OpenBB returned an empty historical frame for symbol={host_symbol!r}; "
                "failing this provider attempt so DataFetcherManager can fall back"
            )
        return normalize_openbb_daily_frame(raw)

    def _resolve_client(self) -> OpenBBHistoricalClient:
        if self._client is not None:
            return self._client
        return _SdkOpenBBClient()


class _SdkOpenBBClient:
    """Run one OpenBB request inside a killable, deadline-bound subprocess."""

    def fetch_historical(
        self,
        *,
        symbol: str,
        start_date: str | None,
        end_date: str | None,
        timeout_seconds: float,
    ) -> pd.DataFrame:
        if not math.isfinite(float(timeout_seconds)) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be finite and positive")
        return _run_openbb_worker(
            {
                "symbol": symbol,
                "start_date": start_date,
                "end_date": end_date,
            },
            timeout_seconds=float(timeout_seconds),
        )


def to_yfinance_symbol(stock_code: str) -> str:
    """Map StockPulse US/HK/Shanghai/Shenzhen forms to one Yahoo symbol.

    Beijing Stock Exchange symbols are deliberately rejected because this
    example does not claim verified yfinance coverage for BSE listings.
    """

    code = str(stock_code or "").strip().upper()
    if not code:
        raise ValueError("stock_code is required")

    if code.startswith("HK"):
        digits = code[2:]
        if digits.isdigit():
            if 1 <= len(digits) <= 5:
                return f"{(digits.lstrip('0') or '0').zfill(4)}.HK"
            raise ValueError(f"invalid Hong Kong stock symbol: {stock_code!r}")
    if code.endswith(".HK"):
        digits = code[:-3]
        if digits.isdigit() and 1 <= len(digits) <= 5:
            return f"{(digits.lstrip('0') or '0').zfill(4)}.HK"
        raise ValueError(f"invalid Hong Kong stock symbol: {stock_code!r}")
    if code.isdigit() and 4 <= len(code) <= 5:
        return f"{(code.lstrip('0') or '0').zfill(4)}.HK"

    bse_prefix_digits = code[2:] if code.startswith("BJ") else ""
    bse_dotted_prefix_digits = code[3:] if code.startswith("BJ.") else ""
    bse_suffix_digits = code[:-3] if code.endswith(".BJ") else ""
    if (
        (bse_prefix_digits.isdigit() and len(bse_prefix_digits) == 6)
        or (
            bse_dotted_prefix_digits.isdigit()
            and len(bse_dotted_prefix_digits) == 6
        )
        or (bse_suffix_digits.isdigit() and len(bse_suffix_digits) == 6)
    ):
        raise ValueError(
            f"BSE symbol {stock_code!r} is not supported by this yfinance adapter"
        )

    mainland = code
    explicit_market: str | None = None
    mainland_prefixes = (
        ("SH.", "SS"),
        ("SH", "SS"),
        ("SS.", "SS"),
        ("SS", "SS"),
        ("SZ.", "SZ"),
        ("SZ", "SZ"),
    )
    for prefix, market in mainland_prefixes:
        candidate = code[len(prefix):]
        if code.startswith(prefix) and candidate.isdigit():
            mainland = candidate
            explicit_market = market
            break
    if explicit_market is None and "." in code:
        base, suffix = code.rsplit(".", 1)
        if base.isdigit() and suffix in {"SH", "SS", "SZ"}:
            mainland = base
            explicit_market = "SS" if suffix in {"SH", "SS"} else "SZ"

    if mainland.isdigit() and len(mainland) == 6:
        if mainland.startswith(("92", "43", "81", "82", "83", "87", "88")):
            raise ValueError(
                f"BSE symbol {stock_code!r} is not supported by this yfinance adapter"
            )
        if explicit_market is not None:
            return f"{mainland}.{explicit_market}"
        if mainland.startswith(("51", "52", "56", "58", "600", "601", "603", "605", "688")):
            return f"{mainland}.SS"
        if mainland.startswith(("15", "16", "18", "000", "001", "002", "003", "300", "301")):
            return f"{mainland}.SZ"
        raise ValueError(f"unsupported mainland stock symbol: {stock_code!r}")

    if re.fullmatch(r"[A-Z][A-Z0-9.-]{0,14}", code):
        return code
    raise ValueError(f"unsupported stock symbol: {stock_code!r}")


def _validate_openbb_version(version_text: str) -> None:
    match = re.match(r"^(\d+)\.(\d+)(?:\.|$)", str(version_text or ""))
    if match is None or tuple(map(int, match.groups())) != _SUPPORTED_OPENBB_MINOR:
        raise RuntimeError(
            "Unsupported OpenBB version "
            f"{version_text!r}; install openbb>=4.7,<4.8 for this adapter"
        )


def _installed_openbb_version() -> str:
    try:
        version_text = distribution_version("openbb")
    except PackageNotFoundError as exc:
        raise MissingOpenBBDependencyError(_MISSING_OPENBB_MESSAGE) from exc
    _validate_openbb_version(version_text)
    return version_text


def _call_openbb_historical(
    obb: Any,
    *,
    symbol: str,
    start_date: str | None,
    end_date: str | None,
) -> pd.DataFrame:
    """Perform exactly one supported OpenBB 4.7 historical request."""

    kwargs: dict[str, Any] = {
        "symbol": symbol,
        "provider": "yfinance",
    }
    if start_date:
        kwargs["start_date"] = start_date
    if end_date:
        kwargs["end_date"] = end_date
    result = obb.equity.price.historical(**kwargs)
    return _coerce_openbb_result_to_frame(result)


def _subprocess_group_kwargs() -> dict[str, Any]:
    if os.name == "nt":
        return {"creationflags": getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)}
    return {"start_new_session": True}


def _worker_environment() -> dict[str, str]:
    """Preserve the host import path and OpenBB credentials for the worker."""

    environment = dict(os.environ)
    candidates = [os.getcwd() if not item else item for item in sys.path]
    existing = environment.get("PYTHONPATH")
    if existing:
        candidates.extend(existing.split(os.pathsep))
    environment["PYTHONPATH"] = os.pathsep.join(dict.fromkeys(candidates))
    return environment


def _terminate_subprocess_tree(process: subprocess.Popen[str]) -> None:
    """Terminate and reap a timed-out worker within a fixed cleanup budget."""

    if process.poll() is not None:
        return
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            process.terminate()
    else:
        process.terminate()
    try:
        process.wait(timeout=0.25)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name != "nt":
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            process.kill()
    else:
        process.kill()
    try:
        process.wait(timeout=0.25)
    except subprocess.TimeoutExpired:
        pass


def _run_openbb_worker(
    request: dict[str, Any],
    *,
    timeout_seconds: float,
    command: list[str] | None = None,
) -> pd.DataFrame:
    """Execute one OpenBB call in an isolated process and enforce its deadline."""

    worker_command = command or [
        sys.executable,
        "-c",
        _OPENBB_WORKER_BOOTSTRAP,
        str(Path(__file__).resolve()),
        _OPENBB_WORKER_ARGUMENT,
    ]
    with tempfile.TemporaryDirectory(prefix="stockpulse-openbb-") as temp_dir:
        result_path = Path(temp_dir) / "result.json"
        worker_request = dict(request)
        worker_request["result_path"] = str(result_path)
        process = subprocess.Popen(
            worker_command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            env=_worker_environment(),
            **_subprocess_group_kwargs(),
        )
        try:
            process.communicate(
                json.dumps(worker_request),
                timeout=float(timeout_seconds),
            )
        except subprocess.TimeoutExpired as exc:
            _terminate_subprocess_tree(process)
            raise TimeoutError(
                f"OpenBB yfinance request exceeded {timeout_seconds:g}s adapter timeout"
            ) from exc

        if not result_path.is_file():
            raise RuntimeError(
                f"OpenBB worker exited with code {process.returncode} without a result"
            )
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        if not payload.get("ok"):
            error_type = str(payload.get("error_type") or "RuntimeError")
            message = str(payload.get("message") or "OpenBB worker failed")
            if error_type == "MissingOpenBBDependencyError":
                raise MissingOpenBBDependencyError(message)
            if error_type == "TypeError":
                raise TypeError(message)
            raise RuntimeError(f"OpenBB worker failed ({error_type}): {message}")

        frame_json = payload.get("frame")
        if not isinstance(frame_json, str):
            raise TypeError("OpenBB worker returned an invalid frame payload")
        return pd.read_json(StringIO(frame_json), orient="split")


def _openbb_worker_main() -> int:
    """Child-process protocol entry point; never called by plugin loading."""

    request: dict[str, Any] = {}
    try:
        request = json.loads(sys.stdin.read())
        result_path = Path(str(request["result_path"]))
        _installed_openbb_version()
        obb = _import_openbb()
        frame = _call_openbb_historical(
            obb,
            symbol=str(request["symbol"]),
            start_date=request.get("start_date"),
            end_date=request.get("end_date"),
        )
        payload = {
            "ok": True,
            "frame": frame.to_json(orient="split", date_format="iso"),
        }
    except Exception as exc:  # broad-exception: fallback_recorded - child boundary
        result_path_value = request.get("result_path")
        if not result_path_value:
            return 2
        result_path = Path(str(result_path_value))
        payload = {
            "ok": False,
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    return 0


def _import_openbb() -> Any:
    try:
        from openbb import obb  # type: ignore[import-not-found]
    except ImportError as exc:  # pragma: no cover - exercised via unit test path
        raise MissingOpenBBDependencyError(_MISSING_OPENBB_MESSAGE) from exc
    return obb


def _coerce_openbb_result_to_frame(result: Any) -> pd.DataFrame:
    if isinstance(result, pd.DataFrame):
        return result
    # OpenBB 4.7 exposes OBBject.to_df(); retain to_dataframe() compatibility
    # for real-shaped fixtures and minor SDK presentation differences.
    for method_name in ("to_df", "to_dataframe"):
        converter = getattr(result, method_name, None)
        if callable(converter):
            frame = converter()
            if isinstance(frame, pd.DataFrame):
                return frame
    results = getattr(result, "results", None)
    if results is not None:
        return pd.DataFrame(results)
    raise TypeError(
        f"Unsupported OpenBB historical result type: {type(result)!r}"
    )


def normalize_openbb_daily_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Normalize heterogeneous OpenBB / upstream column names to the host contract.

    Target columns: date, open, high, low, close, volume, amount, pct_chg.
    """

    if frame is None or not isinstance(frame, pd.DataFrame):
        raise TypeError("frame must be a pandas.DataFrame")
    if frame.empty:
        raise RuntimeError("cannot normalize an empty OpenBB frame")

    working = frame.copy()
    if not isinstance(working.index, pd.RangeIndex) and working.index.name in {
        None,
        "date",
        "Date",
        "datetime",
        "timestamp",
    }:
        # Many OpenBB equity historical responses use a DatetimeIndex.
        if "date" not in {str(c).lower() for c in working.columns}:
            working = working.reset_index()

    rename_map: dict[str, str] = {}
    lower_to_actual = {str(col).strip().lower(): col for col in working.columns}
    aliases = {
        "date": ("date", "datetime", "timestamp", "time", "index"),
        "open": ("open", "o", "adj_open", "adj open"),
        "high": ("high", "h", "adj_high", "adj high"),
        "low": ("low", "l", "adj_low", "adj low"),
        "close": ("close", "c", "adj_close", "adj close", "adjclose"),
        "volume": ("volume", "vol", "v"),
        "amount": ("amount", "value", "turnover", "dollar_volume"),
        "pct_chg": (
            "pct_chg",
            "pct_change",
            "percent_change",
            "change_percent",
            "change_pct",
            "returns",
        ),
    }
    for target, candidates in aliases.items():
        for candidate in candidates:
            actual = lower_to_actual.get(candidate)
            if actual is not None and actual not in rename_map:
                rename_map[actual] = target
                break

    working = working.rename(columns=rename_map)
    missing_ohlcv = [
        name
        for name in ("date", "open", "high", "low", "close", "volume")
        if name not in working.columns
    ]
    if missing_ohlcv:
        raise ValueError(
            "OpenBB frame missing required columns after normalization: "
            + ", ".join(missing_ohlcv)
        )

    working["_parsed_timestamp"] = pd.to_datetime(
        working["date"],
        errors="coerce",
        format="mixed",
        utc=True,
    )
    if working["_parsed_timestamp"].isna().any():
        raise ValueError("OpenBB frame contains an invalid required date")

    numeric_columns = ("open", "high", "low", "close", "volume")
    for column in numeric_columns:
        working[column] = pd.to_numeric(working[column], errors="coerce")
        values = working[column].to_numpy(dtype="float64", copy=False)
        if not np.isfinite(values).all():
            raise ValueError(
                f"OpenBB frame contains a non-numeric or non-finite {column} value"
            )

    prices = working.loc[:, ["open", "high", "low", "close"]]
    if (prices <= 0).any(axis=None):
        raise ValueError("OpenBB frame prices must be positive")
    if (
        (working["low"] > working["high"])
        | (working["open"] < working["low"])
        | (working["open"] > working["high"])
        | (working["close"] < working["low"])
        | (working["close"] > working["high"])
    ).any():
        raise ValueError(
            "OpenBB frame violates OHLC bounds: low <= open/close <= high"
        )

    volume_values = working["volume"].to_numpy(dtype="float64", copy=False)
    if (volume_values < 0).any():
        raise ValueError("OpenBB frame volume must be non-negative")
    if not np.equal(volume_values, np.floor(volume_values)).all():
        raise ValueError("OpenBB frame volume must be integer-compatible")
    if (volume_values > np.iinfo(np.int64).max).any():
        raise ValueError("OpenBB frame volume exceeds int64 range")

    if "amount" in working.columns:
        working["amount"] = pd.to_numeric(working["amount"], errors="coerce")
        amount_values = working["amount"].to_numpy(dtype="float64", copy=False)
        if not np.isfinite(amount_values).all() or (amount_values < 0).any():
            raise ValueError("OpenBB frame amount must be finite and non-negative")

    # Stable ascending order, then keep the latest upstream observation for each
    # UTC trading date. Derivations happen only after this duplicate policy.
    working = working.sort_values("_parsed_timestamp", kind="mergesort")
    working["date"] = working["_parsed_timestamp"].dt.strftime("%Y-%m-%d")
    working = working.drop_duplicates(subset=["date"], keep="last")

    working["volume"] = working["volume"].astype("int64")
    if "amount" not in working.columns:
        working["amount"] = working["close"] * working["volume"]
    amount_values = working["amount"].to_numpy(dtype="float64", copy=False)
    if not np.isfinite(amount_values).all() or (amount_values < 0).any():
        raise ValueError("OpenBB frame derived an invalid amount")

    working["pct_chg"] = working["close"].pct_change(fill_method=None) * 100.0
    working.loc[working.index[0], "pct_chg"] = 0.0
    if not np.isfinite(working["pct_chg"].to_numpy(dtype="float64", copy=False)).all():
        raise ValueError("OpenBB frame derived a non-finite percentage change")

    normalized = working.loc[:, list(_REQUIRED_COLUMNS)].copy()
    return normalized.reset_index(drop=True)


def _resolve_window(
    *,
    start_date: str | None,
    end_date: str | None,
    days: int,
) -> tuple[str | None, str | None]:
    if start_date or end_date:
        return start_date, end_date
    if days and days > 0:
        end = date.today()
        start = end - timedelta(days=int(days))
        return start.isoformat(), end.isoformat()
    return start_date, end_date


def create_openbb_provider() -> DataProvider:
    """Factory used by ``DataProviderRegistration`` (no auto-install side effects)."""

    return OpenBBDailyDataProvider()


class Plugin(BasePlugin):
    """Register the OpenBB adapter with a manager-bound provider registry."""

    def onload(self, context: PluginContext) -> None:
        registration = DataProviderRegistration(
            provider_id="openbb-daily-data",
            factory=create_openbb_provider,
            markets=frozenset({"us", "hk", "cn"}),
            capabilities=frozenset({"daily_data"}),
        )
        context.register(
            "data_provider",
            registration.provider_id,
            registration,
            contract_version="1",
            priority=OpenBBDailyDataProvider.priority,
        )


if __name__ == "__main__" and _OPENBB_WORKER_ARGUMENT in sys.argv:
    raise SystemExit(_openbb_worker_main())
