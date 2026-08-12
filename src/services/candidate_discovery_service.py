# -*- coding: utf-8 -*-
"""Bounded AI candidate discovery for Research Discover (#177 / #325).

Design constraints:
- Universe is explicit and hard-capped (watchlist / portfolio / index page / codes).
- Market data goes through DataFetcherManager (data_provider governance).
- No unbounded full-market quote scans: pagination + provider-call budget + cancel hook.
- Results include deterministic selection reasons and cost/universe contracts.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Set

from src.data.stock_index_loader import find_existing_stock_index_path
from src.services.stock_code_utils import canonicalize_analysis_stock_code
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

DISCOVERY_PACK_VERSION = "candidate_discovery/1.0"

DEFAULT_MAX_RESULTS = 10
MAX_RESULTS_HARD_CAP = 30
DEFAULT_PAGE = 1
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
MAX_UNIVERSE_EVALUATED = 200
DEFAULT_MAX_PROVIDER_CALLS = 20
MAX_PROVIDER_CALLS_HARD_CAP = 50
MAX_QUERY_LENGTH = 500
MAX_EXPLICIT_CODES = 100
MAX_KEYWORDS = 12
MAX_LLM_CALLS = 2
MAX_REASON_LENGTH = 280

UNIVERSE_WATCHLIST = "watchlist"
UNIVERSE_PORTFOLIO = "portfolio"
UNIVERSE_INDEX = "index"
UNIVERSE_CODES = "codes"
SUPPORTED_UNIVERSES = frozenset(
    {UNIVERSE_WATCHLIST, UNIVERSE_PORTFOLIO, UNIVERSE_INDEX, UNIVERSE_CODES}
)
SUPPORTED_MARKETS = frozenset({"CN", "HK", "US", "BSE", "JP", "KR"})

CancelCheck = Callable[[], bool]
QuoteFetcher = Callable[[str], Optional[Mapping[str, Any]]]
LlmCall = Callable[[str], str]


class DiscoveryCancelled(Exception):
    """Raised when the caller requests cancellation mid-run."""


class DiscoveryValidationError(ValueError):
    """Raised for invalid discovery request parameters."""


@dataclass(frozen=True)
class IndexSymbol:
    """One stock-index row used as a local universe entry."""

    code: str
    display_code: str
    name: str
    market: str
    kind: str = "stock"
    active: bool = True
    aliases: tuple[str, ...] = ()
    search_blob: str = ""


@dataclass
class DiscoveryCriteria:
    """Normalized structured criteria after NL/rule parsing."""

    markets: List[str] = field(default_factory=list)
    keywords: List[str] = field(default_factory=list)
    min_change_pct: Optional[float] = None
    max_change_pct: Optional[float] = None
    min_amount: Optional[float] = None
    exclude_st: bool = True
    raw_query: str = ""


@dataclass
class ScoredCandidate:
    code: str
    name: str
    market: str
    score: float
    reason: str
    reason_codes: tuple[str, ...]
    price: Optional[float] = None
    change_pct: Optional[float] = None
    amount: Optional[float] = None
    industry: str = ""
    factor_scores: Dict[str, float] = field(default_factory=dict)
    llm_thesis: str = ""
    provider: str = ""


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))


def _optional_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _bounded_text(value: Any, limit: int, *, fallback: str = "") -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _normalize_markets(raw: Any) -> List[str]:
    if raw is None:
        return []
    values: Iterable[Any]
    if isinstance(raw, str):
        values = re.split(r"[\s,;/|]+", raw)
    elif isinstance(raw, (list, tuple, set)):
        values = raw
    else:
        return []
    ordered: List[str] = []
    seen: Set[str] = set()
    for item in values:
        market = str(item or "").strip().upper()
        if market in {"A", "A-SHARE", "ASHARE", "CN_EQUITY", "CHINA"}:
            market = "CN"
        if market not in SUPPORTED_MARKETS or market in seen:
            continue
        seen.add(market)
        ordered.append(market)
    return ordered


def _normalize_keywords(raw: Any) -> List[str]:
    if raw is None:
        return []
    values: Iterable[Any]
    if isinstance(raw, str):
        values = re.split(r"[\s,;/|，、]+", raw)
    elif isinstance(raw, (list, tuple, set)):
        values = raw
    else:
        return []
    ordered: List[str] = []
    seen: Set[str] = set()
    for item in values:
        token = str(item or "").strip().lower()
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
        if len(ordered) >= MAX_KEYWORDS:
            break
    return ordered


def parse_natural_language_query(query: str) -> DiscoveryCriteria:
    """Rule-based NL → criteria. Offline-safe; no network/LLM required."""
    text = _bounded_text(query, MAX_QUERY_LENGTH)
    lower = text.lower()
    markets: List[str] = []
    if re.search(r"\b(a股|a-share|ashare|沪深|上证|深证|cn)\b", lower) or "a股" in text or "沪深" in text:
        markets.append("CN")
    if re.search(r"\b(港股|hk|hong\s*kong)\b", lower) or "港股" in text:
        markets.append("HK")
    if re.search(r"\b(美股|us|nasdaq|nyse)\b", lower) or "美股" in text:
        markets.append("US")
    if re.search(r"\b(北交所|bse)\b", lower) or "北交所" in text:
        markets.append("BSE")

    min_change: Optional[float] = None
    max_change: Optional[float] = None
    gain = re.search(r"(?:涨幅|上涨|change(?:_pct)?)\s*[>≥>=]\s*(-?\d+(?:\.\d+)?)", text, re.I)
    if gain:
        min_change = float(gain.group(1))
    loss = re.search(r"(?:跌幅|下跌)\s*[>≥>=]\s*(-?\d+(?:\.\d+)?)", text)
    if loss:
        max_change = -abs(float(loss.group(1)))
    upper = re.search(r"(?:涨幅|change(?:_pct)?)\s*[<≤<=]\s*(-?\d+(?:\.\d+)?)", text, re.I)
    if upper:
        max_change = float(upper.group(1))

    min_amount: Optional[float] = None
    amount_match = re.search(
        r"(?:成交额|amount)\s*[>≥>=]\s*(\d+(?:\.\d+)?)\s*(亿|万|w|e)?",
        text,
        re.I,
    )
    if amount_match:
        amount = float(amount_match.group(1))
        unit = (amount_match.group(2) or "").lower()
        if unit in {"亿", "e"}:
            amount *= 100_000_000
        elif unit in {"万", "w"}:
            amount *= 10_000
        min_amount = amount

    exclude_st = not bool(re.search(r"\b(包含st|include\s*st|含st)\b", lower) or "包含ST" in text)

    scrubbed = text
    for pattern in (
        r"(?:涨幅|下跌|跌幅|change(?:_pct)?|成交额|amount)\s*[<>≤≥>=<=]+\s*-?\d+(?:\.\d+)?\s*(?:亿|万|w|e|%)?",
        r"\b(a股|a-share|ashare|港股|美股|hk|us|cn|nasdaq|nyse|北交所|bse|沪深|上证|深证)\b",
        r"包含st|include\s*st|含st|排除st|exclude\s*st",
        r"低波动|高股息|蓝筹|成长|动量|热门|强势|放量|缩量",
    ):
        scrubbed = re.sub(pattern, " ", scrubbed, flags=re.I)
    keywords = _normalize_keywords(scrubbed)

    if not keywords:
        for token, mapped in (
            (r"银行|bank", "银行"),
            (r"白酒|liquor", "白酒"),
            (r"新能源|ev|光伏|锂电", "新能源"),
            (r"半导体|芯片|chip", "半导体"),
            (r"医药|biotech|pharma", "医药"),
            (r"券商|证券", "证券"),
            (r"地产|地产股|real\s*estate", "地产"),
            (r"消费|consumer", "消费"),
            (r"科技|tech", "科技"),
        ):
            if re.search(token, text, re.I):
                keywords.append(mapped)

    return DiscoveryCriteria(
        markets=_normalize_markets(markets),
        keywords=keywords[:MAX_KEYWORDS],
        min_change_pct=min_change,
        max_change_pct=max_change,
        min_amount=min_amount,
        exclude_st=exclude_st,
        raw_query=text,
    )


def merge_criteria(
    *,
    query: str = "",
    criteria: Optional[Mapping[str, Any]] = None,
) -> DiscoveryCriteria:
    """Merge explicit criteria over NL-derived defaults."""
    parsed = parse_natural_language_query(query)
    payload = dict(criteria or {})
    markets = _normalize_markets(payload.get("markets")) or parsed.markets
    keywords = _normalize_keywords(payload.get("keywords")) or parsed.keywords
    min_change = _optional_float(payload.get("min_change_pct"))
    if min_change is None:
        min_change = parsed.min_change_pct
    max_change = _optional_float(payload.get("max_change_pct"))
    if max_change is None:
        max_change = parsed.max_change_pct
    min_amount = _optional_float(payload.get("min_amount"))
    if min_amount is None:
        min_amount = parsed.min_amount
    exclude_st = payload.get("exclude_st")
    if exclude_st is None:
        exclude_st = parsed.exclude_st
    else:
        exclude_st = bool(exclude_st)
    return DiscoveryCriteria(
        markets=markets,
        keywords=keywords,
        min_change_pct=min_change,
        max_change_pct=max_change,
        min_amount=min_amount,
        exclude_st=bool(exclude_st),
        raw_query=_bounded_text(query, MAX_QUERY_LENGTH),
    )


def _is_st_name(name: str) -> bool:
    upper = str(name or "").upper()
    return "ST" in upper or "退" in str(name or "")


def _build_search_blob(name: str, aliases: Sequence[str], display_code: str, code: str) -> str:
    parts = [name, display_code, code, *aliases]
    return " ".join(str(part or "") for part in parts).lower()


def load_stock_index_symbols() -> List[IndexSymbol]:
    """Load local stock-index symbols (no network)."""
    path = find_existing_stock_index_path()
    if path is None:
        return []
    try:
        raw_items = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        log_safe_exception(
            logger,
            "Candidate discovery stock index load failed",
            exc,
            error_code="candidate_discovery_index_load_failed",
            level=logging.WARNING,
        )
        return []
    if not isinstance(raw_items, list):
        return []

    symbols: List[IndexSymbol] = []
    for item in raw_items:
        if not isinstance(item, list) or len(item) < 3:
            continue
        canonical = str(item[0] or "").strip()
        display = str(item[1] or "").strip() or canonical
        name = str(item[2] or "").strip()
        if not canonical or not name:
            continue
        aliases_raw = item[5] if len(item) > 5 else []
        aliases: List[str] = []
        if isinstance(aliases_raw, list):
            aliases = [str(alias).strip() for alias in aliases_raw if str(alias or "").strip()]
        market = str(item[6] if len(item) > 6 else "CN").strip().upper() or "CN"
        kind = str(item[7] if len(item) > 7 else "stock").strip().lower() or "stock"
        active = True if len(item) <= 8 else bool(item[8])
        if not active or kind not in {"", "stock", "equity"}:
            continue
        code = canonicalize_analysis_stock_code(canonical) or canonical
        symbols.append(
            IndexSymbol(
                code=code,
                display_code=display,
                name=name,
                market=market if market in SUPPORTED_MARKETS else "CN",
                kind=kind or "stock",
                active=active,
                aliases=tuple(aliases),
                search_blob=_build_search_blob(name, aliases, display, code),
            )
        )
    return symbols


def _default_quote_fetcher(stock_code: str) -> Optional[Mapping[str, Any]]:
    try:
        from data_provider.base import DataFetcherManager

        quote = DataFetcherManager().get_realtime_quote(stock_code, log_final_failure=False)
        if quote is None:
            return None
        if isinstance(quote, Mapping):
            return quote
        return {
            "code": getattr(quote, "code", stock_code),
            "name": getattr(quote, "name", None),
            "price": getattr(quote, "price", None),
            "change_pct": getattr(quote, "change_pct", None),
            "amount": getattr(quote, "amount", None),
            "volume": getattr(quote, "volume", None),
            "source": getattr(quote, "source", None) or getattr(quote, "provider", None),
        }
    except Exception as exc:  # broad-exception: fallback_recorded - one symbol must not fail the run
        log_safe_exception(
            logger,
            "Candidate discovery quote fetch failed",
            exc,
            error_code="candidate_discovery_quote_failed",
            level=logging.DEBUG,
            context={"stock_code": stock_code},
        )
        return None


def _quote_field(quote: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in quote and quote[name] is not None:
            return quote[name]
    return None


class CandidateDiscoveryService:
    """Run one bounded discovery pass with explicit cost/universe contracts."""

    def __init__(
        self,
        *,
        config_provider: Optional[Callable[[], Any]] = None,
        index_loader: Optional[Callable[[], Sequence[IndexSymbol]]] = None,
        quote_fetcher: Optional[QuoteFetcher] = None,
        portfolio_loader: Optional[Callable[[Optional[int]], Sequence[str]]] = None,
        watchlist_loader: Optional[Callable[[], Sequence[str]]] = None,
        llm_call: Optional[LlmCall] = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        self._config_provider = config_provider
        self._index_loader = index_loader or load_stock_index_symbols
        self._quote_fetcher = quote_fetcher or _default_quote_fetcher
        self._portfolio_loader = portfolio_loader
        self._watchlist_loader = watchlist_loader
        self._llm_call = llm_call
        self._clock = clock or time.time

    def discover(
        self,
        *,
        query: str = "",
        criteria: Optional[Mapping[str, Any]] = None,
        universe: str = UNIVERSE_WATCHLIST,
        page: int = DEFAULT_PAGE,
        page_size: int = DEFAULT_PAGE_SIZE,
        max_results: int = DEFAULT_MAX_RESULTS,
        max_provider_calls: int = DEFAULT_MAX_PROVIDER_CALLS,
        codes: Optional[Sequence[str]] = None,
        markets: Optional[Sequence[str]] = None,
        account_id: Optional[int] = None,
        use_llm: bool = False,
        language: str = "en",
        cancel_check: Optional[CancelCheck] = None,
    ) -> Dict[str, Any]:
        started = self._clock()
        universe_name = str(universe or UNIVERSE_WATCHLIST).strip().lower()
        if universe_name not in SUPPORTED_UNIVERSES:
            raise DiscoveryValidationError(
                f"Unsupported universe '{universe}'. Supported: {sorted(SUPPORTED_UNIVERSES)}"
            )

        page_n = _clamp_int(page, default=DEFAULT_PAGE, minimum=1, maximum=10_000)
        page_size_n = _clamp_int(page_size, default=DEFAULT_PAGE_SIZE, minimum=1, maximum=MAX_PAGE_SIZE)
        max_results_n = _clamp_int(
            max_results, default=DEFAULT_MAX_RESULTS, minimum=1, maximum=MAX_RESULTS_HARD_CAP
        )
        max_provider_calls_n = _clamp_int(
            max_provider_calls,
            default=DEFAULT_MAX_PROVIDER_CALLS,
            minimum=0,
            maximum=MAX_PROVIDER_CALLS_HARD_CAP,
        )

        merged = merge_criteria(query=query, criteria=criteria)
        if markets:
            merged = DiscoveryCriteria(
                markets=_normalize_markets(markets) or merged.markets,
                keywords=merged.keywords,
                min_change_pct=merged.min_change_pct,
                max_change_pct=merged.max_change_pct,
                min_amount=merged.min_amount,
                exclude_st=merged.exclude_st,
                raw_query=merged.raw_query,
            )

        self._raise_if_cancelled(cancel_check)

        index_symbols = list(self._index_loader())
        index_by_code = {item.code.upper(): item for item in index_symbols}
        for item in index_symbols:
            index_by_code.setdefault(item.display_code.upper(), item)

        universe_codes, universe_meta = self._resolve_universe_codes(
            universe_name=universe_name,
            page=page_n,
            page_size=page_size_n,
            codes=codes,
            index_symbols=index_symbols,
            account_id=account_id,
        )
        self._raise_if_cancelled(cancel_check)

        filtered_symbols = self._filter_universe(
            universe_codes=universe_codes,
            index_by_code=index_by_code,
            criteria=merged,
        )
        evaluated = filtered_symbols[:MAX_UNIVERSE_EVALUATED]
        truncated_eval = len(filtered_symbols) > MAX_UNIVERSE_EVALUATED

        provider_calls = 0
        provider_hits = 0
        provider_errors = 0
        scored: List[ScoredCandidate] = []
        for symbol in evaluated:
            self._raise_if_cancelled(cancel_check)
            quote: Optional[Mapping[str, Any]] = None
            if provider_calls < max_provider_calls_n:
                provider_calls += 1
                quote = self._quote_fetcher(symbol.code)
                if quote is None:
                    provider_errors += 1
                else:
                    provider_hits += 1
            candidate = self._score_symbol(symbol, quote=quote, criteria=merged, language=language)
            if candidate is None:
                continue
            scored.append(candidate)

        scored.sort(key=lambda item: (-item.score, item.code))
        shortlist = scored[:max_results_n]

        llm_calls = 0
        llm_explained = 0
        if use_llm and shortlist and self._llm_call is not None:
            self._raise_if_cancelled(cancel_check)
            shortlist, llm_calls, llm_explained = self._maybe_explain_with_llm(
                shortlist, language=language, criteria=merged
            )

        elapsed_ms = int(max(0.0, (self._clock() - started) * 1000))
        candidates_payload = [
            self._candidate_to_dict(item, rank=index)
            for index, item in enumerate(shortlist, start=1)
        ]
        status = "ok" if candidates_payload else "empty"
        if provider_calls > 0 and provider_hits == 0 and max_provider_calls_n > 0:
            status = "degraded" if candidates_payload else "degraded_empty"

        empty_reason = None
        empty_message = None
        if not candidates_payload:
            if not universe_codes:
                empty_reason = "empty_universe"
                empty_message = "The selected universe has no symbols for this page."
            elif not filtered_symbols:
                empty_reason = "no_criteria_match"
                empty_message = "No symbols matched the current natural-language or structured criteria."
            elif provider_calls > 0 and provider_hits == 0:
                empty_reason = "provider_unavailable"
                empty_message = (
                    "data_provider returned no usable quotes within the call budget. "
                    "Retry later or widen the universe page."
                )
            else:
                empty_reason = "no_ranked_candidates"
                empty_message = "Symbols were evaluated but none passed ranking filters."

        return {
            "pack_version": DISCOVERY_PACK_VERSION,
            "run_id": uuid.uuid4().hex,
            "status": status,
            "query": merged.raw_query,
            "universe": universe_name,
            "market": (merged.markets[0].lower() if merged.markets else "cn"),
            "page": page_n,
            "page_size": page_size_n,
            "max_results": max_results_n,
            "candidate_count": len(candidates_payload),
            "candidates": candidates_payload,
            "criteria": {
                "markets": merged.markets,
                "keywords": merged.keywords,
                "min_change_pct": merged.min_change_pct,
                "max_change_pct": merged.max_change_pct,
                "min_amount": merged.min_amount,
                "exclude_st": merged.exclude_st,
            },
            "empty_reason": empty_reason,
            "empty_message": empty_message,
            "warnings": self._build_warnings(
                truncated_eval=truncated_eval,
                provider_errors=provider_errors,
                provider_calls=provider_calls,
                max_provider_calls=max_provider_calls_n,
            ),
            "research_disclaimer": (
                "Research screening only. Not investment advice or trade instructions."
            ),
            "universe_contract": {
                **universe_meta,
                "resolved_count": len(universe_codes),
                "after_filter_count": len(filtered_symbols),
                "evaluated_count": len(evaluated),
                "hard_cap_evaluated": MAX_UNIVERSE_EVALUATED,
                "truncated_evaluated": truncated_eval,
            },
            "cost_contract": {
                "provider_calls": provider_calls,
                "provider_hits": provider_hits,
                "provider_errors": provider_errors,
                "max_provider_calls": max_provider_calls_n,
                "llm_calls": llm_calls,
                "llm_explained": llm_explained,
                "max_llm_calls": MAX_LLM_CALLS if use_llm else 0,
                "elapsed_ms": elapsed_ms,
                "analysis_runs_triggered": 0,
                "database_writes": 0,
                "bounded": True,
                "interruptible": cancel_check is not None,
            },
        }

    def _config(self) -> Any:
        if self._config_provider is not None:
            return self._config_provider()
        try:
            from src.application_services import get_application_services

            return get_application_services().config
        except Exception as exc:  # broad-exception: fallback_recorded - config optional
            log_safe_exception(
                logger,
                "Candidate discovery config load failed",
                exc,
                error_code="candidate_discovery_config_failed",
                level=logging.DEBUG,
            )
            return None

    def _resolve_universe_codes(
        self,
        *,
        universe_name: str,
        page: int,
        page_size: int,
        codes: Optional[Sequence[str]],
        index_symbols: Sequence[IndexSymbol],
        account_id: Optional[int],
    ) -> tuple[List[str], Dict[str, Any]]:
        if universe_name == UNIVERSE_CODES:
            ordered = self._canonicalize_codes(codes or [])
            truncated = len(ordered) > MAX_EXPLICIT_CODES
            if truncated:
                ordered = ordered[:MAX_EXPLICIT_CODES]
            return ordered, {
                "source": UNIVERSE_CODES,
                "total_available": len(ordered),
                "page": 1,
                "page_size": len(ordered),
                "truncated": truncated,
            }

        if universe_name == UNIVERSE_INDEX:
            total = len(index_symbols)
            start = (page - 1) * page_size
            end = start + page_size
            page_items = index_symbols[start:end]
            return [item.code for item in page_items], {
                "source": UNIVERSE_INDEX,
                "total_available": total,
                "page": page,
                "page_size": page_size,
                "truncated": end < total,
                "has_more": end < total,
            }

        if universe_name == UNIVERSE_PORTFOLIO:
            raw = self._load_portfolio_codes(account_id=account_id)
            ordered = self._canonicalize_codes(raw)
            page_slice, meta = self._paginate(ordered, page=page, page_size=page_size)
            meta["source"] = UNIVERSE_PORTFOLIO
            return page_slice, meta

        raw = self._load_watchlist_codes()
        ordered = self._canonicalize_codes(raw)
        page_slice, meta = self._paginate(ordered, page=page, page_size=page_size)
        meta["source"] = UNIVERSE_WATCHLIST
        return page_slice, meta

    def _paginate(
        self, codes: Sequence[str], *, page: int, page_size: int
    ) -> tuple[List[str], Dict[str, Any]]:
        total = len(codes)
        start = (page - 1) * page_size
        end = start + page_size
        return list(codes[start:end]), {
            "total_available": total,
            "page": page,
            "page_size": page_size,
            "truncated": end < total,
            "has_more": end < total,
        }

    def _canonicalize_codes(self, codes: Sequence[Any]) -> List[str]:
        ordered: List[str] = []
        seen: Set[str] = set()
        for raw in codes:
            canonical = canonicalize_analysis_stock_code(str(raw or "").strip())
            if not canonical:
                continue
            key = canonical.upper()
            if key in seen:
                continue
            seen.add(key)
            ordered.append(canonical)
        return ordered

    def _load_watchlist_codes(self) -> List[str]:
        if self._watchlist_loader is not None:
            return [str(code) for code in self._watchlist_loader()]
        config = self._config()
        raw = getattr(config, "stock_list", None) if config is not None else None
        if isinstance(raw, str):
            try:
                from src.utils.stock_list import split_stock_list

                return list(split_stock_list(raw))
            except Exception as exc:  # broad-exception: fallback_recorded
                log_safe_exception(
                    logger,
                    "Candidate discovery watchlist parse failed",
                    exc,
                    error_code="candidate_discovery_watchlist_parse_failed",
                    level=logging.DEBUG,
                )
                return []
        if isinstance(raw, (list, tuple)):
            return [str(item) for item in raw]
        return []

    def _load_portfolio_codes(self, *, account_id: Optional[int]) -> List[str]:
        if self._portfolio_loader is not None:
            return [str(code) for code in self._portfolio_loader(account_id)]
        try:
            from src.repositories.portfolio_repo import PortfolioRepository

            rows = PortfolioRepository().list_cached_positions(
                account_id=account_id, cost_method="fifo"
            )
        except Exception as exc:  # broad-exception: fallback_recorded
            log_safe_exception(
                logger,
                "Candidate discovery portfolio load failed",
                exc,
                error_code="candidate_discovery_portfolio_failed",
                level=logging.WARNING,
            )
            return []
        codes: List[str] = []
        for row in rows or []:
            if isinstance(row, Mapping):
                codes.append(str(row.get("symbol") or row.get("code") or ""))
            else:
                codes.append(str(getattr(row, "symbol", "") or getattr(row, "code", "") or ""))
        return codes

    def _filter_universe(
        self,
        *,
        universe_codes: Sequence[str],
        index_by_code: Mapping[str, IndexSymbol],
        criteria: DiscoveryCriteria,
    ) -> List[IndexSymbol]:
        symbols: List[IndexSymbol] = []
        for code in universe_codes:
            item = index_by_code.get(str(code).upper())
            if item is None:
                name = str(code)
                item = IndexSymbol(
                    code=str(code),
                    display_code=str(code),
                    name=name,
                    market="CN",
                    search_blob=name.lower(),
                )
            if criteria.markets and item.market not in criteria.markets:
                continue
            if criteria.exclude_st and _is_st_name(item.name):
                continue
            if criteria.keywords:
                blob = item.search_blob
                if not any(keyword in blob for keyword in criteria.keywords):
                    continue
            symbols.append(item)
        return symbols

    def _score_symbol(
        self,
        symbol: IndexSymbol,
        *,
        quote: Optional[Mapping[str, Any]],
        criteria: DiscoveryCriteria,
        language: str,
    ) -> Optional[ScoredCandidate]:
        price = _optional_float(_quote_field(quote or {}, "price", "current_price", "close"))
        change_pct = _optional_float(
            _quote_field(quote or {}, "change_pct", "change_percent", "pct_chg")
        )
        amount = _optional_float(_quote_field(quote or {}, "amount", "turnover", "total_amount"))
        provider = str(_quote_field(quote or {}, "source", "provider") or "")
        quote_name = str(_quote_field(quote or {}, "name", "stock_name") or "").strip()
        name = quote_name or symbol.name

        if criteria.min_change_pct is not None:
            if change_pct is None:
                if quote is not None:
                    return None
            elif change_pct < criteria.min_change_pct:
                return None
        if criteria.max_change_pct is not None and change_pct is not None:
            if change_pct > criteria.max_change_pct:
                return None
        if criteria.min_amount is not None and amount is not None:
            if amount < criteria.min_amount:
                return None
        if criteria.min_amount is not None and amount is None and quote is not None:
            return None

        score = 0.0
        reason_codes: List[str] = []
        factors: Dict[str, float] = {}

        if criteria.keywords:
            hits = sum(1 for keyword in criteria.keywords if keyword in symbol.search_blob)
            if hits:
                keyword_score = min(40.0, hits * 12.0)
                score += keyword_score
                factors["keyword_match"] = keyword_score
                reason_codes.append("keyword_match")

        if change_pct is not None:
            momentum = max(-20.0, min(20.0, change_pct))
            momentum_score = 20.0 + momentum
            score += momentum_score
            factors["momentum"] = round(momentum_score, 2)
            reason_codes.append("momentum")

        if amount is not None and amount > 0:
            liquidity = min(25.0, max(0.0, (amount / 50_000_000.0) * 5.0))
            score += liquidity
            factors["liquidity"] = round(liquidity, 2)
            reason_codes.append("liquidity")

        if quote is None:
            score += 5.0
            factors["metadata_only"] = 5.0
            reason_codes.append("metadata_only")
        else:
            score += 10.0
            factors["quote_available"] = 10.0
            reason_codes.append("quote_available")

        if not reason_codes:
            reason_codes.append("universe_member")
            score += 1.0

        reason = self._format_reason(
            language=language,
            symbol=symbol,
            name=name,
            reason_codes=reason_codes,
            change_pct=change_pct,
            keywords=criteria.keywords,
            query=criteria.raw_query,
        )
        return ScoredCandidate(
            code=symbol.code,
            name=name,
            market=symbol.market,
            score=round(score, 2),
            reason=reason,
            reason_codes=tuple(dict.fromkeys(reason_codes)),
            price=price,
            change_pct=change_pct,
            amount=amount,
            industry="",
            factor_scores=factors,
            provider=provider,
        )

    def _format_reason(
        self,
        *,
        language: str,
        symbol: IndexSymbol,
        name: str,
        reason_codes: Sequence[str],
        change_pct: Optional[float],
        keywords: Sequence[str],
        query: str,
    ) -> str:
        zh = str(language or "").lower().startswith("zh")
        parts: List[str] = []
        if "keyword_match" in reason_codes and keywords:
            joined = "、".join(keywords[:4]) if zh else ", ".join(keywords[:4])
            parts.append(f"名称/别名匹配关键词 {joined}" if zh else f"Name/alias matched keywords {joined}")
        if "momentum" in reason_codes and change_pct is not None:
            parts.append(
                f"日内涨跌幅 {change_pct:+.2f}%" if zh else f"Session change {change_pct:+.2f}%"
            )
        if "liquidity" in reason_codes:
            parts.append("成交额提供流动性支持" if zh else "Turnover supports liquidity")
        if "metadata_only" in reason_codes:
            parts.append(
                "本页仅用本地指数元数据入选（未取到行情）"
                if zh
                else "Selected from local index metadata (no quote in budget)"
            )
        if "quote_available" in reason_codes and "momentum" not in reason_codes:
            parts.append("已通过 data_provider 取得实时行情" if zh else "Realtime quote via data_provider")
        if not parts:
            if query:
                parts.append(
                    f"属于所选宇宙且与查询相关：{query[:40]}"
                    if zh
                    else f"In selected universe and related to query: {query[:40]}"
                )
            else:
                parts.append(
                    f"属于 {symbol.market} 宇宙分页结果"
                    if zh
                    else f"Member of {symbol.market} universe page"
                )
        prefix = f"{name}（{symbol.display_code}）" if zh else f"{name} ({symbol.display_code})"
        return _bounded_text(f"{prefix}: " + "；".join(parts), MAX_REASON_LENGTH)

    def _maybe_explain_with_llm(
        self,
        shortlist: Sequence[ScoredCandidate],
        *,
        language: str,
        criteria: DiscoveryCriteria,
    ) -> tuple[List[ScoredCandidate], int, int]:
        if self._llm_call is None or not shortlist:
            return list(shortlist), 0, 0
        zh = str(language or "").lower().startswith("zh")
        lines = []
        for item in shortlist[:MAX_RESULTS_HARD_CAP]:
            lines.append(
                f"- {item.code} {item.name}: score={item.score}, change={item.change_pct}, reason={item.reason}"
            )
        prompt = (
            "你是股票研究筛选助手。根据候选列表，为每只股票写一句不超过 40 字的入选理由。"
            "只输出 JSON 对象，键为股票代码，值为理由字符串。不要给出买卖建议。\n"
            f"查询: {criteria.raw_query}\n候选:\n" + "\n".join(lines)
            if zh
            else (
                "You are a research screening assistant. For each candidate write one selection "
                "reason under 40 words. Output a JSON object mapping stock code to reason string. "
                "Do not give trade instructions.\n"
                f"Query: {criteria.raw_query}\nCandidates:\n" + "\n".join(lines)
            )
        )
        try:
            raw = self._llm_call(prompt)
            payload = self._extract_json_object(raw)
        except Exception as exc:  # broad-exception: fallback_recorded - keep deterministic reasons
            log_safe_exception(
                logger,
                "Candidate discovery LLM explain failed",
                exc,
                error_code="candidate_discovery_llm_explain_failed",
                level=logging.INFO,
            )
            return list(shortlist), 1, 0

        explained = 0
        updated: List[ScoredCandidate] = []
        for item in shortlist:
            thesis = _bounded_text(payload.get(item.code) or payload.get(item.code.upper()), 120)
            if thesis:
                explained += 1
                updated.append(
                    ScoredCandidate(
                        code=item.code,
                        name=item.name,
                        market=item.market,
                        score=item.score,
                        reason=item.reason,
                        reason_codes=item.reason_codes,
                        price=item.price,
                        change_pct=item.change_pct,
                        amount=item.amount,
                        industry=item.industry,
                        factor_scores=dict(item.factor_scores),
                        llm_thesis=thesis,
                        provider=item.provider,
                    )
                )
            else:
                updated.append(item)
        return updated, 1, explained

    @staticmethod
    def _extract_json_object(raw: str) -> Dict[str, Any]:
        text = str(raw or "").strip()
        if not text:
            return {}
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", text, re.S)
            if not match:
                return {}
            try:
                data = json.loads(match.group(0))
                return data if isinstance(data, dict) else {}
            except json.JSONDecodeError:
                return {}

    @staticmethod
    def _candidate_to_dict(item: ScoredCandidate, *, rank: int) -> Dict[str, Any]:
        return {
            "rank": rank,
            "code": item.code,
            "name": item.name,
            "score": item.score,
            "reason": item.reason,
            "reason_codes": list(item.reason_codes),
            "risk_level": "research",
            "price": item.price,
            "change_pct": item.change_pct,
            "amount": item.amount,
            "industry": item.industry or item.market,
            "factor_scores": item.factor_scores,
            "llm_thesis": item.llm_thesis or None,
            "market": item.market,
            "provider": item.provider or None,
            "selection_source": "candidate_discovery",
        }

    @staticmethod
    def _build_warnings(
        *,
        truncated_eval: bool,
        provider_errors: int,
        provider_calls: int,
        max_provider_calls: int,
    ) -> List[str]:
        warnings: List[str] = []
        if truncated_eval:
            warnings.append(
                f"Evaluated universe truncated to {MAX_UNIVERSE_EVALUATED} symbols for this run."
            )
        if max_provider_calls == 0:
            warnings.append("Provider calls disabled; ranking uses local metadata only.")
        elif provider_calls >= max_provider_calls:
            warnings.append(
                f"Provider call budget reached ({max_provider_calls}); remaining symbols use metadata only."
            )
        if provider_errors:
            warnings.append(f"{provider_errors} quote fetches returned no data.")
        return warnings

    @staticmethod
    def _raise_if_cancelled(cancel_check: Optional[CancelCheck]) -> None:
        if cancel_check is None:
            return
        try:
            cancelled = bool(cancel_check())
        except Exception as exc:  # broad-exception: fallback_recorded - cancel probe must not crash run
            log_safe_exception(
                logger,
                "Candidate discovery cancel check failed",
                exc,
                error_code="candidate_discovery_cancel_check_failed",
                level=logging.DEBUG,
            )
            return
        if cancelled:
            raise DiscoveryCancelled("Discovery run cancelled")
