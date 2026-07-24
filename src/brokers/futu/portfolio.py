"""Read live stock positions from Futu OpenD without trading operations."""

from __future__ import annotations

import ipaddress
import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

from data_provider.us_index_mapping import is_us_stock_code
from src.services.stock_code_utils import normalize_code
from src.services.stock_list_parser import normalize_stock_codes
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

DEFAULT_OPEND_HOST = "127.0.0.1"
DEFAULT_OPEND_PORT = 11111
_SUPPORTED_ACCOUNT_ROLES = frozenset({"NORMAL", "MASTER"})
_SUPPORTED_MARKETS = frozenset({"SH", "SZ", "HK", "US"})
_UNKNOWN_SECURITY_TYPES = frozenset({"", "N/A", "NAN", "NONE", "UNKNOWN"})
_BASIC_INFO_BATCH_SIZE = 100


class FutuPortfolioError(RuntimeError):
    """Raised when a trustworthy Futu analysis scope cannot be produced."""


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
        raise FutuPortfolioError(
            "Futu OpenAPI SDK is unavailable; install the project requirements "
            "before using --portfolio futu"
        ) from exc
    except Exception as exc:  # broad-exception: cleanup - Translate SDK initialization failures to the typed broker boundary.
        raise FutuPortfolioError(f"Futu OpenAPI SDK initialization failed: {exc}") from exc

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
        raise FutuPortfolioError(f"{operation} returned non-tabular data")
    return (row for _, row in iterrows())


def _close(context: Any) -> None:
    if context is None:
        return
    try:
        context.close()
    except Exception as exc:  # broad-exception: cleanup - Context close failure cannot replace the primary query outcome.
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
        raise FutuPortfolioError("FUTU_OPEND_PORT must be a valid port") from exc
    if not host or not 1 <= port <= 65535:
        raise FutuPortfolioError("Futu OpenD host or port is invalid")

    address_text = host[1:-1] if host.startswith("[") and host.endswith("]") else host
    try:
        address = ipaddress.ip_address(address_text)
    except ValueError:
        address = None
    if address is not None and address.version != 4:
        raise FutuPortfolioError(
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
        raise FutuPortfolioError("FUTU_ACC_ID must be a positive integer") from exc
    if account_id <= 0:
        raise FutuPortfolioError("FUTU_ACC_ID must be a positive integer")
    return account_id


def _configured_security_firm(api: _FutuApi) -> Any:
    firm_name = (os.getenv("FUTU_SECURITY_FIRM") or "NONE").strip().upper()
    firm = getattr(api.SecurityFirm, firm_name, None)
    if firm is None:
        raise FutuPortfolioError(f"Unsupported FUTU_SECURITY_FIRM: {firm_name}")
    return firm


def _discover_accounts(api: _FutuApi, host: str, port: int) -> List[_Account]:
    requested_id = _configured_account_id()
    default_firm = _configured_security_firm(api)
    context = None
    accounts: List[_Account] = []
    seen_ids = set()
    try:
        context = api.OpenSecTradeContext(
            host=host,
            port=port,
            filter_trdmarket=api.TrdMarket.NONE,
            security_firm=default_firm,
        )
        ret, data = context.get_acc_list()
        if ret != api.RET_OK:
            raise FutuPortfolioError(f"Futu real-account query failed: {data}")
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
                raise FutuPortfolioError("Futu returned an invalid account ID") from exc
            if isinstance(raw_id, bool) or not exact_integer or account_id <= 0:
                raise FutuPortfolioError("Futu returned an invalid account ID")
            if account_id in seen_ids:
                continue
            returned_firm = getattr(
                api.SecurityFirm,
                _enum_text(row.get("security_firm")),
                default_firm,
            )
            seen_ids.add(account_id)
            accounts.append(_Account(account_id, returned_firm))
    except FutuPortfolioError:
        raise
    except Exception as exc:  # broad-exception: cleanup - Translate SDK/network failures to the typed broker boundary.
        raise FutuPortfolioError(f"Futu real-account query failed: {exc}") from exc
    finally:
        _close(context)

    if requested_id is not None:
        accounts = [account for account in accounts if account.acc_id == requested_id]
        if not accounts:
            raise FutuPortfolioError(
                "FUTU_ACC_ID did not match an ACTIVE REAL securities account"
            )
    if not accounts:
        raise FutuPortfolioError(
            "No ACTIVE REAL Futu NORMAL or MASTER securities account was found"
        )
    return accounts


def _load_position_codes(
    api: _FutuApi,
    host: str,
    port: int,
    accounts: Iterable[_Account],
) -> List[str]:
    codes: List[str] = []
    seen_codes = set()
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
                raise FutuPortfolioError(f"Futu real-position query failed: {data}")
            for row in _rows(data, "Futu position query"):
                side = _enum_text(row.get("position_side"))
                if side == "SHORT":
                    skipped_short += 1
                    continue
                if side != "LONG":
                    skipped_unknown += 1
                    continue

                raw_quantity = row.get("qty")
                try:
                    if isinstance(raw_quantity, bool):
                        raise TypeError("boolean quantity")
                    quantity = float(raw_quantity)
                except (TypeError, ValueError) as exc:
                    raise FutuPortfolioError("Futu returned an invalid position quantity") from exc
                if not math.isfinite(quantity):
                    raise FutuPortfolioError("Futu returned an invalid position quantity")
                if quantity == 0:
                    continue

                raw_code = row.get("code")
                if not isinstance(raw_code, str):
                    raise FutuPortfolioError("Futu returned an invalid non-zero position code")
                code = raw_code.strip().upper()
                market, separator, symbol = code.partition(".")
                if not separator or not market or not symbol:
                    raise FutuPortfolioError(
                        f"Futu returned an invalid non-zero position code: {code or '<empty>'}"
                    )
                if code not in seen_codes:
                    seen_codes.add(code)
                    codes.append(code)
        except FutuPortfolioError:
            raise
        except Exception as exc:  # broad-exception: cleanup - Translate SDK/network failures to the typed broker boundary.
            raise FutuPortfolioError(f"Futu real-position query failed: {exc}") from exc
        finally:
            _close(context)

    if skipped_short:
        logger.info("Skipped %d Futu short position(s)", skipped_short)
    if skipped_unknown:
        logger.warning("Skipped %d Futu position(s) without LONG direction", skipped_unknown)
    return codes


def _is_cn_b_share(code: str) -> bool:
    market, separator, symbol = code.partition(".")
    if not separator or not (symbol.isdigit() and len(symbol) == 6):
        return False
    return (market == "SH" and symbol.startswith("900")) or (
        market == "SZ" and symbol.startswith("200")
    )


def _analysis_candidate(futu_code: str) -> Optional[str]:
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


def _filter_and_normalize_stocks(
    api: _FutuApi,
    host: str,
    port: int,
    position_codes: List[str],
) -> List[str]:
    if not position_codes:
        return []

    grouped: dict[str, List[str]] = {}
    unsupported: List[str] = []
    for code in position_codes:
        market = code.split(".", 1)[0]
        if market not in _SUPPORTED_MARKETS or _is_cn_b_share(code):
            unsupported.append(code)
            continue
        grouped.setdefault(market, []).append(code)

    confirmed_stocks = set()
    classified_codes = set()
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
                    raise FutuPortfolioError(
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
    except FutuPortfolioError:
        raise
    except Exception as exc:  # broad-exception: cleanup - Translate SDK/network failures to the typed broker boundary.
        raise FutuPortfolioError(f"Futu security-type query failed: {exc}") from exc
    finally:
        _close(context)

    missing = [
        code
        for codes in grouped.values()
        for code in codes
        if code not in classified_codes
    ]
    if missing:
        raise FutuPortfolioError(
            "Futu did not return a definitive security type for: " + ", ".join(missing)
        )
    if unsupported:
        logger.warning(
            "Skipped %d unsupported Futu holding(s): %s",
            len(unsupported),
            ", ".join(unsupported),
        )

    candidates = []
    for code in position_codes:
        if code not in confirmed_stocks:
            continue
        candidate = _analysis_candidate(code)
        if candidate is None:
            raise FutuPortfolioError(
                f"Futu returned a STOCK code inconsistent with its market: {code}"
            )
        candidates.append(candidate)
    try:
        return normalize_stock_codes(candidates, reject_invalid=True)
    except ValueError as exc:
        raise FutuPortfolioError(
            "A confirmed Futu stock code cannot be normalized for analysis"
        ) from exc


def load_futu_stock_codes() -> List[str]:
    """Return normalized codes from non-zero LONG stocks in selected REAL accounts."""
    api = _load_futu_api()
    host, port = _connection_settings()
    accounts = _discover_accounts(api, host, port)
    positions = _load_position_codes(api, host, port, accounts)
    stock_codes = _filter_and_normalize_stocks(api, host, port, positions)
    logger.info(
        "Loaded %d stock(s) from %d Futu real account(s)",
        len(stock_codes),
        len(accounts),
    )
    return stock_codes
