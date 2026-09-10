# -*- coding: utf-8 -*-
"""yfinance realtime quote methods: US/index routing and the Stooq fallback.

Method bodies are rebound onto ``YfinanceFetcher`` by the compatibility facade
(ADR-006) so free-name lookups and test patches stay on
``src.data_provider.yfinance_fetcher``. Mirrors the domain split of
``main_indices`` in this package and the realtime owners of
``efinance_parts``, ``tushare_parts``, and ``longbridge_parts``.

No sibling method moves. Symbol conversion and US/JP/KR/TW classifiers are
rebound from ``yfinance_parts.symbols``; the HTTP guard stays on the facade.
The cluster reaches them through ``self`` or facade globals at call time.
"""

from __future__ import annotations

import csv
import logging
from datetime import datetime
from io import StringIO
from typing import Any, Callable, Dict, Optional, Tuple, Type
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from src.security.outbound_policy import OutboundPolicyError
from src.utils.sanitize import log_safe_exception

from .facade_bind import bind_methods_from_class

# Facade free-name anchors for flake8 F821. Rebound methods resolve these from
# ``src.data_provider.yfinance_fetcher`` globals at runtime (ADR-006).
logger = logging.getLogger("src.data_provider.yfinance_fetcher")
RealtimeSource = None  # type: ignore[assignment]
STOCK_NAME_MAP = None  # type: ignore[assignment]
UnifiedRealtimeQuote = None  # type: ignore[assignment]
_yfinance_http_guard = None  # type: ignore[assignment]
get_suffix_market = None  # type: ignore[assignment]
get_us_index_yf_symbol = None  # type: ignore[assignment]
is_meaningful_stock_name = None  # type: ignore[assignment]

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")


class _RealtimeMethods:
    """Source descriptors rebound onto ``YfinanceFetcher``."""

    def _get_us_stock_quote_from_stooq(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        使用 Stooq 为美股实时行情提供免密钥兜底。

        Stooq 提供的是最新交易日行情，精度不如分时实时接口，但在 Yahoo / yfinance
        被限流时，至少能为 Web UI 提供可用价格；若可获取到昨收价，则同时提供涨跌幅等衍生指标。
        """
        symbol = stock_code.strip().upper()
        stooq_symbol = f"{symbol.lower()}.us"
        url = f"https://stooq.com/q/l/?s={stooq_symbol}"
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; StockPulse/1.0; +https://github.com/SiinXu/stock-pulse-ai)",
                "Accept": "text/plain,text/csv,*/*",
            },
        )

        try:
            with _yfinance_http_guard():
                with urlopen(request, timeout=15) as response:
                    payload = response.read().decode("utf-8", "ignore").strip()
        except (HTTPError, URLError, TimeoutError, OutboundPolicyError) as exc:
            log_safe_exception(
                logger,
                "Stooq realtime quote request failed",
                exc,
                error_code="stooq_realtime_quote_request_failed",
                level=logging.WARNING,
                context={"symbol": symbol},
            )
            return None

        if not payload or payload.upper().startswith("NO DATA"):
            logger.warning(f"[Stooq] 无法获取 {symbol} 的行情数据")
            return None

        def _fetch_prev_close() -> Optional[float]:
            history_url = f"https://stooq.com/q/d/l/?s={stooq_symbol}&i=d"
            history_request = Request(
                history_url,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; StockPulse/1.0; +https://github.com/SiinXu/stock-pulse-ai)",
                    "Accept": "text/plain,text/csv,*/*",
                },
            )
            try:
                with _yfinance_http_guard():
                    with urlopen(history_request, timeout=15) as response:
                        history_payload = response.read().decode("utf-8", "ignore").strip()
            except (HTTPError, URLError, TimeoutError, OutboundPolicyError) as exc:
                log_safe_exception(
                    logger,
                    "Stooq daily history request failed",
                    exc,
                    error_code="stooq_daily_history_request_failed",
                    level=logging.DEBUG,
                    context={"symbol": symbol},
                )
                return None

            if not history_payload or history_payload.upper().startswith("NO DATA"):
                return None

            try:
                reader = csv.reader(StringIO(history_payload))
                header = next(reader, None)
                if not header:
                    return None

                header_tokens = [cell.strip().lower() for cell in header]
                has_header = "close" in header_tokens and "date" in header_tokens
                if not has_header:
                    return None

                date_index = header_tokens.index("date")
                close_index = header_tokens.index("close")

                daily_rows: list[tuple[datetime, float]] = []
                for row in reader:
                    if not row:
                        continue
                    date_text = row[date_index].strip() if len(row) > date_index else ""
                    close_text = row[close_index].strip() if len(row) > close_index else ""
                    if not date_text or not close_text:
                        continue
                    try:
                        dt = datetime.strptime(date_text, "%Y-%m-%d")
                        close_val = float(close_text)
                    except Exception:
                        continue
                    daily_rows.append((dt, close_val))

                if len(daily_rows) < 2:
                    return None

                daily_rows.sort(key=lambda item: item[0])
                return daily_rows[-2][1]
            except Exception:
                return None

        try:
            reader = csv.reader(StringIO(payload))
            first_row = next(reader, None)
            if first_row is None:
                raise ValueError(f"unexpected Stooq payload: {payload}")

            normalized_first_row = [cell.strip() for cell in first_row]
            header_tokens = {cell.lower() for cell in normalized_first_row if cell}
            has_header = 'open' in header_tokens and 'close' in header_tokens
            row = next(reader, None) if has_header else first_row
            if row is None:
                raise ValueError(f"unexpected Stooq payload: {payload}")

            normalized_row = [cell.strip() for cell in row]
            while normalized_row and normalized_row[-1] == '':
                normalized_row.pop()

            if len(normalized_row) >= 8:
                open_index, high_index, low_index, price_index, volume_index = 3, 4, 5, 6, 7
            elif len(normalized_row) >= 7:
                open_index, high_index, low_index, price_index, volume_index = 2, 3, 4, 5, 6
            else:
                raise ValueError(f"unexpected Stooq payload: {payload}")

            open_price = float(normalized_row[open_index])
            high = float(normalized_row[high_index])
            low = float(normalized_row[low_index])
            price = float(normalized_row[price_index])
            volume = int(float(normalized_row[volume_index]))

            prev_close = _fetch_prev_close()
            change_amount = None
            change_pct = None
            amplitude = None
            if prev_close is not None and prev_close > 0:
                change_amount = price - prev_close
                change_pct = (change_amount / prev_close) * 100
                amplitude = ((high - low) / prev_close) * 100

            quote = UnifiedRealtimeQuote(
                code=symbol,
                name=STOCK_NAME_MAP.get(symbol, ''),
                source=RealtimeSource.STOOQ,
                price=price,
                change_pct=round(change_pct, 2) if change_pct is not None else None,
                change_amount=round(change_amount, 4) if change_amount is not None else None,
                volume=volume,
                amount=None,
                volume_ratio=None,
                turnover_rate=None,
                amplitude=round(amplitude, 2) if amplitude is not None else None,
                open_price=open_price,
                high=high,
                low=low,
                pre_close=prev_close,
                pe_ratio=None,
                pb_ratio=None,
                total_mv=None,
                circ_mv=None,
            )
            logger.info(f"[Stooq] 获取美股 {symbol} 兜底行情成功: 价格={price}")
            return quote
        except Exception as exc:
            log_safe_exception(
                logger,
                "Stooq realtime quote parsing failed",
                exc,
                error_code="stooq_realtime_quote_parsing_failed",
                level=logging.WARNING,
                context={"symbol": symbol},
            )
            return None

    def _get_us_index_realtime_quote(
        self,
        user_code: str,
        yf_symbol: str,
        index_name: str,
    ) -> Optional[UnifiedRealtimeQuote]:
        """
        Get realtime quote for US index (e.g. SPX -> ^GSPC).

        Args:
            user_code: User input code (e.g. SPX)
            yf_symbol: Yahoo Finance symbol (e.g. ^GSPC)
            index_name: Chinese name for the index

        Returns:
            UnifiedRealtimeQuote or None
        """
        import yfinance as yf

        try:
            with _yfinance_http_guard():
                logger.debug(f"[Yfinance] 获取美股指数 {user_code} ({yf_symbol}) 实时行情")
                ticker = yf.Ticker(yf_symbol)

                try:
                    info = ticker.fast_info
                    if info is None:
                        raise ValueError("fast_info is None")
                    price = getattr(info, 'lastPrice', None) or getattr(info, 'last_price', None)
                    prev_close = getattr(info, 'previousClose', None) or getattr(info, 'previous_close', None)
                    open_price = getattr(info, 'open', None)
                    high = getattr(info, 'dayHigh', None) or getattr(info, 'day_high', None)
                    low = getattr(info, 'dayLow', None) or getattr(info, 'day_low', None)
                    volume = getattr(info, 'lastVolume', None) or getattr(info, 'last_volume', None)
                except Exception:  # broad-exception: fallback_recorded - Debug log precedes the history fallback.
                    logger.debug("[Yfinance] fast_info 失败，尝试 history 方法")
                    hist = ticker.history(period='2d')
                    if hist.empty:
                        logger.warning(f"[Yfinance] 无法获取 {yf_symbol} 的数据")
                        return None
                    today = hist.iloc[-1]
                    prev = hist.iloc[-2] if len(hist) > 1 else today
                    price = float(today['Close'])
                    prev_close = float(prev['Close'])
                    open_price = float(today['Open'])
                    high = float(today['High'])
                    low = float(today['Low'])
                    volume = int(today['Volume'])

                change_amount = None
                change_pct = None
                if price is not None and prev_close is not None and prev_close > 0:
                    change_amount = price - prev_close
                    change_pct = (change_amount / prev_close) * 100

                amplitude = None
                if high is not None and low is not None and prev_close is not None and prev_close > 0:
                    amplitude = ((high - low) / prev_close) * 100

                try:
                    ticker_info = ticker.info or {}
                except Exception:  # broad-exception: optional_metadata - ticker.info is supplementary to the already-fetched quote.
                    ticker_info = {}
                missing_fields = [
                    field
                    for field, value in {
                        "price": price,
                        "prev_close": prev_close,
                        "volume": volume,
                        "amount": None,
                        "pe_ratio": None,
                        "pb_ratio": None,
                    }.items()
                    if value is None
                ]

                quote = UnifiedRealtimeQuote(
                    code=user_code,
                    name=index_name or user_code,
                    source=RealtimeSource.FALLBACK,
                    market="us",
                    currency=str(ticker_info.get("currency") or "").upper() or None,
                    data_quality="partial" if missing_fields else "ok",
                    missing_fields=missing_fields or None,
                    price=price,
                    change_pct=round(change_pct, 2) if change_pct is not None else None,
                    change_amount=round(change_amount, 4) if change_amount is not None else None,
                    volume=volume,
                    amount=None,
                    volume_ratio=None,
                    turnover_rate=None,
                    amplitude=round(amplitude, 2) if amplitude is not None else None,
                    open_price=open_price,
                    high=high,
                    low=low,
                    pre_close=prev_close,
                    pe_ratio=None,
                    pb_ratio=None,
                    total_mv=None,
                    circ_mv=None,
                )
                logger.info(f"[Yfinance] 获取美股指数 {user_code} 实时行情成功: 价格={price}")
                return quote
        except Exception as e:  # broad-exception: fallback_recorded - Safe diagnostics preserve the None index-quote fallback.
            log_safe_exception(
                logger,
                "Yfinance US index realtime quote failed",
                e,
                error_code="yfinance_us_index_realtime_quote_failed",
                level=logging.WARNING,
                context={"index_code": user_code, "symbol": yf_symbol},
            )
            return None

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        """
        获取美股/美股指数实时行情数据

        支持美股股票（AAPL、TSLA）和美股指数（SPX、DJI 等）。
        数据来源：yfinance Ticker.info

        Args:
            stock_code: 美股代码或指数代码，如 'AMD', 'AAPL', 'SPX', 'DJI'

        Returns:
            UnifiedRealtimeQuote 对象，获取失败返回 None
        """
        import yfinance as yf

        # U.S. stocks indices: use mapping (SPX -> ^GSPC)
        yf_symbol, index_name = get_us_index_yf_symbol(stock_code)
        if yf_symbol:
            quote = self._get_us_index_realtime_quote(
                user_code=stock_code.strip().upper(),
                yf_symbol=yf_symbol,
                index_name=index_name,
            )
            if quote is not None and quote.source is RealtimeSource.FALLBACK:
                quote.source = RealtimeSource.YFINANCE
            return quote

        # Handles US stocks or JP/KR/TW suffix-only stocks
        if not (
            self._is_us_stock(stock_code)
            or self._is_jp_kr_suffix_stock(stock_code)
            or self._is_tw_suffix_stock(stock_code)
        ):
            logger.debug(f"[Yfinance] {stock_code} 不是美股或日韩 suffix 代码，跳过")
            return None

        try:
            with _yfinance_http_guard():
                symbol = self._convert_stock_code(stock_code)
                is_us_symbol = self._is_us_stock(symbol)
                suffix_market = get_suffix_market(symbol)
                logger.debug(f"[Yfinance] 获取 {symbol} 实时行情")

                ticker = yf.Ticker(symbol)

                # Attempt to fetch fast_info (faster, but fewer fields)
                try:
                    info = ticker.fast_info
                    if info is None:
                        raise ValueError("fast_info is None")

                    price = getattr(info, 'lastPrice', None) or getattr(info, 'last_price', None)
                    prev_close = getattr(info, 'previousClose', None) or getattr(info, 'previous_close', None)
                    open_price = getattr(info, 'open', None)
                    high = getattr(info, 'dayHigh', None) or getattr(info, 'day_high', None)
                    low = getattr(info, 'dayLow', None) or getattr(info, 'day_low', None)
                    volume = getattr(info, 'lastVolume', None) or getattr(info, 'last_volume', None)
                    market_cap = getattr(info, 'marketCap', None) or getattr(info, 'market_cap', None)

                except Exception:  # broad-exception: fallback_recorded - Debug log precedes the history fallback.
                    # Fallback to the history method to get the latest data
                    logger.debug("[Yfinance] fast_info 失败，尝试 history 方法")
                    hist = ticker.history(period='2d')
                    if hist.empty:
                        if is_us_symbol:
                            logger.warning(f"[Yfinance] 无法获取 {symbol} 的数据，尝试 Stooq 兜底")
                            return self._get_us_stock_quote_from_stooq(symbol)
                        logger.warning(f"[Yfinance] 无法获取 {symbol} 的数据")
                        return None

                    today = hist.iloc[-1]
                    prev = hist.iloc[-2] if len(hist) > 1 else today

                    price = float(today['Close'])
                    prev_close = float(prev['Close'])
                    open_price = float(today['Open'])
                    high = float(today['High'])
                    low = float(today['Low'])
                    volume = int(today['Volume'])
                    market_cap = None

                # Calculate Percentage Change
                change_amount = None
                change_pct = None
                if price is not None and prev_close is not None and prev_close > 0:
                    change_amount = price - prev_close
                    change_pct = (change_amount / prev_close) * 100

                # Calculate Amplitude
                amplitude = None
                if high is not None and low is not None and prev_close is not None and prev_close > 0:
                    amplitude = ((high - low) / prev_close) * 100

                # Get stock name and provider metadata
                try:
                    ticker_info = ticker.info or {}
                except Exception:  # broad-exception: optional_metadata - ticker.info is supplementary to the already-fetched quote.
                    ticker_info = {}
                try:
                    info_name = ticker_info.get('shortName', '') or ticker_info.get('longName', '') or ''
                    name = info_name if is_meaningful_stock_name(info_name, symbol) else STOCK_NAME_MAP.get(symbol, '')
                except Exception:  # broad-exception: optional_metadata - stock name is optional display metadata.
                    name = STOCK_NAME_MAP.get(symbol, '')

                # Reuse the ticker_info fetched above for valuation; no extra request.
                # Imported locally (module still has no module-level dependency on the
                # fundamental adapter) to keep the module import block unchanged.
                from .yfinance_fundamental_adapter import _safe_float
                pe_ratio = _safe_float(ticker_info.get('trailingPE'))
                pb_ratio = _safe_float(ticker_info.get('priceToBook'))

                missing_fields = [
                    field
                    for field, value in {
                        "price": price,
                        "prev_close": prev_close,
                        "volume": volume,
                        "amount": None,
                        "pe_ratio": pe_ratio,
                        "pb_ratio": pb_ratio,
                    }.items()
                    if value is None
                ]
                quote = UnifiedRealtimeQuote(
                    code=symbol,
                    name=name,
                    source=RealtimeSource.YFINANCE,
                    market=suffix_market or ("us" if is_us_symbol else None),
                    currency=str(ticker_info.get("currency") or "").upper() or None,
                    data_quality="partial" if missing_fields else "ok",
                    missing_fields=missing_fields or None,
                    price=price,
                    change_pct=round(change_pct, 2) if change_pct is not None else None,
                    change_amount=round(change_amount, 4) if change_amount is not None else None,
                    volume=volume,
                    amount=None,  # yfinance does not directly provide trading value
                    volume_ratio=None,
                    turnover_rate=None,
                    amplitude=round(amplitude, 2) if amplitude is not None else None,
                    open_price=open_price,
                    high=high,
                    low=low,
                    pre_close=prev_close,
                    pe_ratio=pe_ratio,
                    pb_ratio=pb_ratio,
                    total_mv=market_cap,
                    circ_mv=None,
                )

                logger.info(f"[Yfinance] 获取 {symbol} 实时行情成功: 价格={price}")
                return quote

        except Exception as e:  # broad-exception: fallback_recorded - failure is logged, then degraded to Stooq (US) or None
            is_us = self._is_us_stock(stock_code)
            log_safe_exception(
                logger,
                "Yfinance US realtime quote failed; trying Stooq fallback"
                if is_us
                else "Yfinance realtime quote failed",
                e,
                error_code="yfinance_us_realtime_quote_failed"
                if is_us
                else "yfinance_realtime_quote_failed",
                level=logging.WARNING,
                context={"symbol": stock_code},
            )
            if is_us:
                return self._get_us_stock_quote_from_stooq(stock_code)
            return None


EXPECTED_REALTIME_METHOD_NAMES: Tuple[str, ...] = (
    "_get_us_stock_quote_from_stooq",
    "_get_us_index_realtime_quote",
    "get_realtime_quote",
)


def bind_realtime_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind realtime-quote descriptors without changing the fetcher API."""

    return bind_methods_from_class(
        _RealtimeMethods,
        target_class,
        global_namespace,
        expected_names=EXPECTED_REALTIME_METHOD_NAMES,
    )


def _install_facade_reload_hook(hook: Callable[[], None]) -> None:
    """Register the loaded facade assembly callback for owner reloads."""

    global _FACADE_RELOAD_HOOK
    _FACADE_RELOAD_HOOK = hook


def _rebind_loaded_facade() -> None:
    """Refresh a registered facade after this owner module is reloaded."""

    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
