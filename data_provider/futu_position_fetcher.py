# -*- coding: utf-8 -*-
"""Futu OpenD real-position adapter for portfolio import.

OpenD is a local TCP gateway (not HTTP). Connections use the admin-configured
``FUTU_OPEND_HOST`` / ``FUTU_OPEND_PORT`` directly via the Futu SDK, following
the same local-runtime precedent as Pytdx: the operator chooses a loopback or
trusted LAN address; the outbound HTTP allowlist does not apply to this path.

Unreachable OpenD raises :class:`FutuPositionFetchError` with an actionable
message. Callers must treat that as a soft failure for the import action only;
it must never block unrelated analysis or other data providers.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import math
import os
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, Iterable, List, Optional, Sequence

from data_provider.base import canonical_stock_code
from data_provider.us_index_mapping import is_us_stock_code
from src.services.stock_code_utils import normalize_code
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

DEFAULT_OPEND_HOST = "127.0.0.1"
DEFAULT_OPEND_PORT = 11111
_SUPPORTED_ACCOUNT_ROLES = frozenset({"NORMAL", "MASTER"})
_SUPPORTED_MARKETS = frozenset({"SH", "SZ", "HK", "US"})
_UNKNOWN_SECURITY_TYPES = frozenset({"", "N/A", "NAN", "NONE", "UNKNOWN"})
_BASIC_INFO_BATCH_SIZE = 100
_CURRENCY_BY_MARKET = {
    "SH": "CNY",
    "SZ": "CNY",
    "HK": "HKD",
    "US": "USD",
}


class FutuPositionFetchError(RuntimeError):
    """Raised when Futu OpenD positions cannot be loaded safely."""


@dataclass(frozen=True)
class FutuPosition:
    """One normalized LONG stock position from a REAL Futu account."""

    futu_acc_id: int
    futu_code: str
    symbol: str
    market: str
    quantity: float
    cost_price: float
    currency: str


@dataclass(frozen=True)
class _Account:
    acc_id: int
    security_firm: Any


@dataclass(frozen=True)
class _FutuApi:
    OpenQuoteContext: Any
    OpenSecTradeContext: Any
    Market: Any
    RET_OK: Any
    SecurityFirm: Any
    SecurityType: Any
    TrdEnv: Any
    TrdMarket: Any


def _load_futu_api() -> _FutuApi:
    try:
        from futu import (
            Market,
            OpenQuoteContext,
            OpenSecTradeContext,
            RET_OK,
            SecurityFirm,
            SecurityType,
            TrdEnv,
            TrdMarket,
        )
    except ImportError as exc:
        raise FutuPositionFetchError(
            "Futu OpenAPI SDK is unavailable; install project requirements "
            "(futu-api) before importing Futu positions"
        ) from exc
    except Exception as exc:  # broad-exception: SDK import initializes file logger
        raise FutuPositionFetchError(
            f"Futu OpenAPI SDK initialization failed: {exc}"
        ) from exc

    return _FutuApi(
        OpenQuoteContext=OpenQuoteContext,
        OpenSecTradeContext=OpenSecTradeContext,
        Market=Market,
        RET_OK=RET_OK,
        SecurityFirm=SecurityFirm,
        SecurityType=SecurityType,
        TrdEnv=TrdEnv,
        TrdMarket=TrdMarket,
    )


def _enum_text(value: Any) -> str:
    if value is None:
        return ""
    name = getattr(value, "name", None)
    return str(name if name is not None else value).strip().upper()


def _rows(data: Any, operation: str) -> Iterable[Any]:
    iterrows = getattr(data, "iterrows", None)
    if not callable(iterrows):
        raise FutuPositionFetchError(f"{operation} returned non-tabular data")
    return (row for _, row in iterrows())


def _close(context: Any) -> None:
    if context is None:
        return
    try:
        context.close()
    except Exception as exc:  # broad-exception: close must not mask primary result
        log_safe_exception(
            logger,
            "Futu OpenD context close failed",
            exc,
            error_code="futu_context_close_failed",
            level=logging.DEBUG,
        )


def _connection_settings() -> tuple[str, int]:
    host = (os.getenv("FUTU_OPEND_HOST") or DEFAULT_OPEND_HOST).strip()
    raw_port = (os.getenv("FUTU_OPEND_PORT") or str(DEFAULT_OPEND_PORT)).strip()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise FutuPositionFetchError("FUTU_OPEND_PORT must be a valid port") from exc
    if not host or not 1 <= port <= 65535:
        raise FutuPositionFetchError("Futu OpenD host or port is invalid")

    address_text = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        address = ipaddress.ip_address(address_text)
    except ValueError:
        address = None
    if address is not None and address.version != 4:
        raise FutuPositionFetchError(
            "The bundled Futu SDK requires an IPv4 OpenD address; "
            "set FUTU_OPEND_HOST to IPv4 or an IPv4-resolving hostname"
        )
    return host, port


def _configured_account_id() -> Optional[int]:
    raw_account_id = (os.getenv("FUTU_ACC_ID") or "").strip()
    if not raw_account_id:
        return None
    try:
        account_id = int(raw_account_id)
    except ValueError as exc:
        raise FutuPositionFetchError("FUTU_ACC_ID must be a positive integer") from exc
    if account_id <= 0:
        raise FutuPositionFetchError("FUTU_ACC_ID must be a positive integer")
    return account_id


def _configured_security_firm(api: _FutuApi) -> Any:
    firm_name = (os.getenv("FUTU_SECURITY_FIRM") or "NONE").strip().upper()
    firm = getattr(api.SecurityFirm, firm_name, None)
    if firm is None:
        raise FutuPositionFetchError(f"Unsupported FUTU_SECURITY_FIRM: {firm_name}")
    return firm


def _discover_accounts(api: _FutuApi, host: str, port: int) -> List[_Account]:
    requested_id = _configured_account_id()
    default_firm = _configured_security_firm(api)
    context = None
    accounts: List[_Account] = []
    seen_ids: set[int] = set()
    try:
        context = api.OpenSecTradeContext(
            host=host,
            port=port,
            filter_trdmarket=api.TrdMarket.NONE,
            security_firm=default_firm,
        )
        ret, data = context.get_acc_list()
        if ret != api.RET_OK:
            raise FutuPositionFetchError(f"Futu real-account query failed: {data}")
        for row in _rows(data, "Futu account query"):
            if _enum_text(row.get("trd_env")) != "REAL":
                continue
            if _enum_text(row.get("acc_status")) != "ACTIVE":
                continue
            if _enum_text(row.get("acc_role")) not in _SUPPORTED_ACCOUNT_ROLES:
                continue
            raw_id = row.get("acc_id")
            try:
                account_id = int(raw_id)
                exact_integer = isinstance(raw_id, str) or bool(raw_id == account_id)
            except (TypeError, ValueError, OverflowError) as exc:
                raise FutuPositionFetchError("Futu returned an invalid account ID") from exc
            if isinstance(raw_id, bool) or not exact_integer or account_id <= 0:
                raise FutuPositionFetchError("Futu returned an invalid account ID")
            if account_id in seen_ids:
                continue
            returned_firm = getattr(
                api.SecurityFirm,
                _enum_text(row.get("security_firm")),
                default_firm,
            )
            seen_ids.add(account_id)
            accounts.append(_Account(account_id, returned_firm))
    except FutuPositionFetchError:
        raise
    except Exception as exc:  # broad-exception: translate SDK/network to typed boundary
        raise FutuPositionFetchError(
            "Futu OpenD is unreachable or rejected the account query; "
            f"verify OpenD is running at the configured host/port ({exc})"
        ) from exc
    finally:
        _close(context)

    if requested_id is not None:
        accounts = [account for account in accounts if account.acc_id == requested_id]
        if not accounts:
            raise FutuPositionFetchError(
                "FUTU_ACC_ID did not match an ACTIVE REAL securities account"
            )
    if not accounts:
        raise FutuPositionFetchError(
            "No ACTIVE REAL Futu NORMAL or MASTER securities account was found"
        )
    return accounts


def _is_cn_b_share(code: str) -> bool:
    market, separator, symbol = code.partition(".")
    if not separator or not (symbol.isdigit() and len(symbol) == 6):
        return False
    return (market == "SH" and symbol.startswith("900")) or (
        market == "SZ" and symbol.startswith("200")
    )


def _analysis_symbol(futu_code: str) -> Optional[str]:
    market, separator, symbol = futu_code.partition(".")
    if not separator or not symbol:
        return None
    if market == "US":
        return symbol if is_us_stock_code(symbol) else None
    normalized = normalize_code(futu_code)
    if normalized is None:
        return None
    if market == "HK":
        return f"HK{normalized}"
    if market in {"SH", "SZ"}:
        return normalized
    return None


def _parse_positive_float(value: Any, *, field: str) -> Optional[float]:
    try:
        if isinstance(value, bool):
            raise TypeError("boolean")
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number <= 0:
        return None
    return number


@dataclass
class _RawLongPosition:
    futu_acc_id: int
    futu_code: str
    quantity: float
    cost_price: float


def _load_raw_long_positions(
    api: _FutuApi,
    host: str,
    port: int,
    accounts: Sequence[_Account],
) -> List[_RawLongPosition]:
    positions: List[_RawLongPosition] = []
    skipped_short = 0
    skipped_unknown = 0
    for account in accounts:
        context = None
        try:
            context = api.OpenSecTradeContext(
                host=host,
                port=port,
                filter_trdmarket=api.TrdMarket.NONE,
                security_firm=account.security_firm,
            )
            ret, data = context.position_list_query(
                trd_env=api.TrdEnv.REAL,
                acc_id=account.acc_id,
                refresh_cache=True,
            )
            if ret != api.RET_OK:
                raise FutuPositionFetchError(f"Futu real-position query failed: {data}")
            for row in _rows(data, "Futu position query"):
                side = _enum_text(row.get("position_side"))
                if side == "SHORT":
                    skipped_short += 1
                    continue
                if side != "LONG":
                    skipped_unknown += 1
                    continue

                quantity = _parse_positive_float(row.get("qty"), field="qty")
                if quantity is None:
                    raw_qty = row.get("qty")
                    try:
                        if isinstance(raw_qty, bool):
                            raise TypeError("boolean quantity")
                        qty_value = float(raw_qty)
                    except (TypeError, ValueError) as exc:
                        raise FutuPositionFetchError(
                            "Futu returned an invalid position quantity"
                        ) from exc
                    if not math.isfinite(qty_value):
                        raise FutuPositionFetchError(
                            "Futu returned an invalid position quantity"
                        )
                    if qty_value == 0:
                        continue
                    continue

                raw_code = row.get("code")
                if not isinstance(raw_code, str):
                    raise FutuPositionFetchError(
                        "Futu returned an invalid non-zero position code"
                    )
                code = raw_code.strip().upper()
                market, separator, symbol = code.partition(".")
                if not separator or not market or not symbol:
                    raise FutuPositionFetchError(
                        f"Futu returned an invalid non-zero position code: {code or '<empty>'}"
                    )

                cost_price = _parse_positive_float(
                    row.get("cost_price"), field="cost_price"
                )
                if cost_price is None:
                    cost_price = _parse_positive_float(
                        row.get("nominal_price"), field="nominal_price"
                    )
                if cost_price is None:
                    logger.warning(
                        "Skipping Futu position %s: missing positive cost/nominal price",
                        code,
                    )
                    continue

                positions.append(
                    _RawLongPosition(
                        futu_acc_id=account.acc_id,
                        futu_code=code,
                        quantity=quantity,
                        cost_price=cost_price,
                    )
                )
        except FutuPositionFetchError:
            raise
        except Exception as exc:  # broad-exception: translate SDK/network to typed boundary
            raise FutuPositionFetchError(
                "Futu OpenD is unreachable or rejected the position query; "
                f"verify OpenD is running and logged in ({exc})"
            ) from exc
        finally:
            _close(context)

    if skipped_short:
        logger.info("Skipped %d Futu short position(s)", skipped_short)
    if skipped_unknown:
        logger.warning(
            "Skipped %d Futu position(s) without LONG direction", skipped_unknown
        )
    return positions


def _confirm_stock_codes(
    api: _FutuApi,
    host: str,
    port: int,
    position_codes: Sequence[str],
) -> set[str]:
    if not position_codes:
        return set()

    grouped: dict[str, List[str]] = {}
    unsupported: List[str] = []
    for code in position_codes:
        market = code.split(".", 1)[0]
        if market not in _SUPPORTED_MARKETS or _is_cn_b_share(code):
            unsupported.append(code)
            continue
        grouped.setdefault(market, []).append(code)

    confirmed_stocks: set[str] = set()
    classified_codes: set[str] = set()
    context = None
    try:
        if grouped:
            context = api.OpenQuoteContext(host=host, port=port)
        for market_name, codes in grouped.items():
            market = getattr(api.Market, market_name, None)
            if market is None:
                unsupported.extend(codes)
                continue
            for start in range(0, len(codes), _BASIC_INFO_BATCH_SIZE):
                batch = codes[start : start + _BASIC_INFO_BATCH_SIZE]
                ret, data = context.get_stock_basicinfo(
                    market,
                    stock_type=api.SecurityType.STOCK,
                    code_list=batch,
                )
                if ret != api.RET_OK:
                    raise FutuPositionFetchError(
                        f"Futu security-type query failed for {market_name}: {data}"
                    )
                for row in _rows(data, "Futu security-type query"):
                    code = str(row.get("code", "") or "").strip().upper()
                    if not code:
                        continue
                    stock_type = _enum_text(row.get("stock_type"))
                    if stock_type in _UNKNOWN_SECURITY_TYPES:
                        continue
                    classified_codes.add(code)
                    if stock_type == "STOCK":
                        confirmed_stocks.add(code)
    except FutuPositionFetchError:
        raise
    except Exception as exc:  # broad-exception: translate SDK/network to typed boundary
        raise FutuPositionFetchError(
            f"Futu security-type query failed: {exc}"
        ) from exc
    finally:
        _close(context)

    missing = [
        code
        for codes in grouped.values()
        for code in codes
        if code not in classified_codes
    ]
    if missing:
        raise FutuPositionFetchError(
            "Futu did not return a definitive security type for: " + ", ".join(missing)
        )
    if unsupported:
        logger.warning(
            "Skipped %d unsupported Futu holding(s): %s",
            len(unsupported),
            ", ".join(unsupported),
        )
    return confirmed_stocks


def fetch_futu_positions(*, api: Optional[_FutuApi] = None) -> List[FutuPosition]:
    """Fetch LONG stock positions from configured REAL Futu accounts.

    Returns an empty list when OpenD is reachable but no eligible stocks are held.
    Raises :class:`FutuPositionFetchError` when the gateway is unreachable or
    configuration/query results are untrustworthy.
    """
    resolved_api = api or _load_futu_api()
    host, port = _connection_settings()
    accounts = _discover_accounts(resolved_api, host, port)
    raw_positions = _load_raw_long_positions(resolved_api, host, port, accounts)
    codes = [item.futu_code for item in raw_positions]
    confirmed = _confirm_stock_codes(resolved_api, host, port, codes)

    results: List[FutuPosition] = []
    seen_keys: set[str] = set()
    for item in raw_positions:
        if item.futu_code not in confirmed:
            continue
        market = item.futu_code.split(".", 1)[0]
        candidate = _analysis_symbol(item.futu_code)
        if candidate is None:
            raise FutuPositionFetchError(
                f"Futu returned a STOCK code inconsistent with its market: {item.futu_code}"
            )
        symbol = canonical_stock_code(candidate) or candidate
        if not symbol:
            raise FutuPositionFetchError(
                f"Futu returned a STOCK code that cannot be normalized: {item.futu_code}"
            )
        merge_key = f"{item.futu_acc_id}:{symbol}"
        if merge_key in seen_keys:
            continue
        seen_keys.add(merge_key)
        results.append(
            FutuPosition(
                futu_acc_id=item.futu_acc_id,
                futu_code=item.futu_code,
                symbol=symbol,
                market=market,
                quantity=item.quantity,
                cost_price=item.cost_price,
                currency=_CURRENCY_BY_MARKET.get(market, "USD"),
            )
        )

    logger.info(
        "Loaded %d stock position(s) from %d Futu real account(s)",
        len(results),
        len(accounts),
    )
    return results


def positions_to_import_records(
    positions: Sequence[FutuPosition],
    *,
    as_of: Optional[date] = None,
) -> List[Dict[str, Any]]:
    """Map Futu positions into portfolio import trade records (synthetic buys)."""
    trade_date = as_of or date.today()
    records: List[Dict[str, Any]] = []
    for index, position in enumerate(positions):
        trade_uid = (
            f"futu:{position.futu_acc_id}:{position.symbol}:"
            f"{position.quantity:.8f}:{position.cost_price:.8f}"
        )
        record: Dict[str, Any] = {
            "trade_date": trade_date,
            "symbol": position.symbol,
            "side": "buy",
            "quantity": float(position.quantity),
            "price": float(position.cost_price),
            "fee": 0.0,
            "tax": 0.0,
            "trade_uid": trade_uid,
            "currency": position.currency,
            "market": {
                "SH": "cn",
                "SZ": "cn",
                "HK": "hk",
                "US": "us",
            }.get(position.market),
            "note": f"futu_import:{position.futu_code}",
            "_source_line_number": index + 1,
        }
        record["dedup_hash"] = _build_dedup_hash(record)
        records.append(record)
    return records


def _build_dedup_hash(record: Dict[str, Any]) -> str:
    payload = "|".join(
        [
            str(record.get("trade_date") or ""),
            str(record.get("symbol") or ""),
            str(record.get("side") or ""),
            f"{float(record.get('quantity', 0.0)):.8f}",
            f"{float(record.get('price', 0.0)):.8f}",
            f"{float(record.get('fee', 0.0)):.8f}",
            f"{float(record.get('tax', 0.0)):.8f}",
            str(record.get("currency") or ""),
            str(record.get("trade_uid") or ""),
            str(record.get("_source_line_number") or ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
