# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned fundamental context aggregation rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. Cache key/prune/inflight stays in ``fundamental_cache_methods``;
capital-flow, dragon-tiger, and board fetches stay on the facade and are
still invoked through rebound ``get_fundamental_context``. These descriptors
own source-chain normalization, block builders, CN/offshore aggregation, and
the failed/validation-rejected payloads. ``DataFetcherManager`` remains the
public import and patch surface.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
)

import numpy as np
import pandas as pd

from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
DataFetcherManager = None  # type: ignore[assignment,misc]
normalize_stock_code = None  # type: ignore[assignment,misc]
_market_tag = None  # type: ignore[assignment,misc]
_is_etf_code = None  # type: ignore[assignment,misc]

logger = logging.getLogger("src.data_provider.base")

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _FundamentalContextMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    @staticmethod
    def _normalize_source_chain(
        entries: Any,
        provider: str,
        result: str,
        duration_ms: int,
    ) -> List[Dict[str, Any]]:
        """Normalize free-form source chain entries to structured dict list."""
        if entries is None:
            return [{"provider": provider, "result": result, "duration_ms": duration_ms}]

        normalized: List[Dict[str, Any]] = []
        if not isinstance(entries, (list, tuple)):
            entries = [entries]

        for item in entries:
            if isinstance(item, dict):
                normalized.append({
                    "provider": str(item.get("provider") or provider),
                    "result": str(item.get("result") or result),
                    "duration_ms": int(item.get("duration_ms", duration_ms)),
                })
                continue

            if item is None:
                continue

            provider_name = str(item)
            normalized.append({
                "provider": provider_name,
                "result": result,
                "duration_ms": duration_ms,
            })

        if not normalized:
            return [{"provider": provider, "result": result, "duration_ms": duration_ms}]

        return normalized

    @staticmethod
    def _block_status(payload: Dict[str, Any], available: bool = True) -> str:
        if not available:
            return "not_supported"
        if not payload:
            return "partial"
        return "ok"

    @staticmethod
    def _build_fundamental_block(
        status: str,
        payload: Optional[Dict[str, Any]] = None,
        source_chain: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "coverage": {"status": status},
            "source_chain": source_chain or [],
            "errors": errors or [],
            "data": payload or {},
        }

    @staticmethod
    def _has_meaningful_payload(payload: Any) -> bool:
        if payload is None:
            return False
        if isinstance(payload, str):
            normalized = payload.strip().lower()
            return normalized not in ("", "-", "nan", "none", "null", "n/a", "na")
        if isinstance(payload, dict):
            return any(DataFetcherManager._has_meaningful_payload(v) for v in payload.values())
        if isinstance(payload, pd.DataFrame):
            if payload.empty:
                return False
            return any(
                DataFetcherManager._has_meaningful_payload(v)
                for v in payload.to_numpy().flat
            )
        if isinstance(payload, (pd.Series, pd.Index)):
            return any(DataFetcherManager._has_meaningful_payload(v) for v in payload.tolist())
        if isinstance(payload, np.ndarray):
            if payload.ndim == 0:
                payload = payload.item()
            else:
                return any(
                    DataFetcherManager._has_meaningful_payload(v)
                    for v in payload.flat
                )
        if isinstance(payload, (list, tuple, set)):
            return any(DataFetcherManager._has_meaningful_payload(v) for v in payload)
        if DataFetcherManager._try_scalar_isna(payload, "fundamental_payload") is True:
            return False
        return True

    @staticmethod
    def _infer_block_status(payload: Any, fallback_status: str) -> str:
        if DataFetcherManager._has_meaningful_payload(payload):
            return "ok"
        if fallback_status in ("failed", "partial", "not_supported"):
            return fallback_status
        return "partial"

    @staticmethod
    def _should_cache_fundamental_context(context: Any) -> bool:
        if not isinstance(context, dict):
            return False
        status = str(context.get("status", "")).strip().lower()
        if status == "ok":
            return True
        if status == "failed":
            return False
        for block in (
            "valuation",
            "growth",
            "earnings",
            "institution",
            "capital_flow",
            "dragon_tiger",
            "boards",
        ):
            payload = context.get(block, {})
            if isinstance(payload, dict) and DataFetcherManager._has_meaningful_payload(payload.get("data")):
                return True
        return False

    def _build_market_not_supported(self, market: str, reason: str) -> Dict[str, Any]:
        blocks = {
            "valuation": self._build_fundamental_block(
                "partial" if market == "etf" else "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "growth": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "earnings": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "institution": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "capital_flow": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "dragon_tiger": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
            "boards": self._build_fundamental_block(
                "not_supported",
                {},
                [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                [reason],
            ),
        }
        return {
            "market": market,
            "status": "partial" if market == "etf" else "not_supported",
            "coverage": {
                block: blocks[block]["status"] for block in blocks
            },
            "source_chain": [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
            "errors": [reason],
            **blocks,
        }

    def _build_offshore_fundamental_context(
        self,
        stock_code: str,
        market: str,
        budget_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """HK/US fundamental aggregation via yfinance.

        Mirrors :meth:`get_fundamental_context` but skips A-share-specific
        blocks (capital_flow, dragon_tiger, sector rankings). belong_boards is
        sourced from yfinance ``info.sector`` / ``info.industry``.

        Cache, retry and fail-open semantics intentionally match the CN path so
        upstream callers see the same shape regardless of market.
        """
        config = self._get_fundamental_config()
        stage_timeout = float(
            budget_seconds if budget_seconds is not None else config.fundamental_stage_timeout_seconds
        )
        stage_timeout = max(0.0, stage_timeout)
        fetch_timeout = float(config.fundamental_fetch_timeout_seconds)
        fetch_timeout = max(0.0, fetch_timeout)

        def _load() -> Dict[str, Any]:
            result_ctx: Dict[str, Any] = {
                "market": market,
                "provider": "yfinance",
                "as_of": datetime.now(timezone.utc).isoformat(),
                "data_quality": "unavailable",
                "missing_fields": [],
                "valuation": {},
                "growth": {},
                "earnings": {},
                "institution": {},
                "capital_flow": {},
                "dragon_tiger": {},
                "boards": {},
                "belong_boards": [],
                "coverage": {},
                "source_chain": [],
                "errors": [],
            }
            start_ts = time.time()

            # Valuation: reuse realtime quote payload — yfinance returns pe/pb in the
            # same shape as AkShare, so the existing block formatter still works.
            valuation_timeout = min(fetch_timeout, stage_timeout) if stage_timeout > 0 else 0
            if valuation_timeout > 0:
                quote_payload, valuation_err, valuation_ms = self._run_with_retry(
                    lambda: self.get_realtime_quote(stock_code),
                    valuation_timeout,
                    "fundamental_valuation",
                )
            else:
                quote_payload, valuation_err, valuation_ms = None, "fundamental stage timeout", 0
            valuation_payload = {
                "pe_ratio": getattr(quote_payload, "pe_ratio", None) if quote_payload else None,
                "pb_ratio": getattr(quote_payload, "pb_ratio", None) if quote_payload else None,
                "total_mv": getattr(quote_payload, "total_mv", None) if quote_payload else None,
                "circ_mv": getattr(quote_payload, "circ_mv", None) if quote_payload else None,
            }
            valuation_status = self._infer_block_status(
                valuation_payload,
                "partial" if quote_payload is not None else "not_supported",
            )
            if valuation_status == "partial" and valuation_err and not self._has_meaningful_payload(valuation_payload):
                valuation_status = "failed"
            result_ctx["valuation"] = self._build_fundamental_block(
                valuation_status,
                valuation_payload,
                self._normalize_source_chain(
                    [{"provider": "realtime_quote", "result": valuation_status, "duration_ms": valuation_ms}],
                    "realtime_quote",
                    valuation_status,
                    valuation_ms,
                ),
                [valuation_err] if valuation_err else [],
            )

            # Fundamental bundle via yfinance.
            bundle_timeout = min(fetch_timeout, max(stage_timeout - (time.time() - start_ts), 0.0))
            if bundle_timeout <= 0:
                bundle_payload, bundle_err, bundle_ms = {}, "fundamental stage timeout", 0
            else:
                bundle_payload, bundle_err, bundle_ms = self._run_with_retry(
                    lambda: self._yfinance_fundamental_adapter.get_fundamental_bundle(stock_code),
                    bundle_timeout,
                    "fundamental_bundle_yfinance",
                )
            if not isinstance(bundle_payload, dict):
                bundle_payload = {}

            bundle_chain = self._normalize_source_chain(
                bundle_payload.get("source_chain", []),
                "fundamental_bundle_yfinance",
                str(bundle_payload.get("status", "not_supported")),
                bundle_ms,
            )
            adapter_errors = list(bundle_payload.get("errors", []))
            if bundle_err:
                adapter_errors.append(bundle_err)

            growth_payload = bundle_payload.get("growth", {}) if isinstance(bundle_payload.get("growth"), dict) else {}
            earnings_payload = bundle_payload.get("earnings", {}) if isinstance(bundle_payload.get("earnings"), dict) else {}
            belong_boards = bundle_payload.get("belong_boards") if isinstance(bundle_payload.get("belong_boards"), list) else []

            growth_status = self._infer_block_status(growth_payload, str(bundle_payload.get("status", "not_supported")))
            earnings_status = self._infer_block_status(earnings_payload, str(bundle_payload.get("status", "not_supported")))

            result_ctx["growth"] = self._build_fundamental_block(
                growth_status,
                growth_payload,
                bundle_chain,
                list(adapter_errors),
            )
            result_ctx["earnings"] = self._build_fundamental_block(
                earnings_status,
                earnings_payload,
                bundle_chain,
                list(adapter_errors),
            )

            # capital_flow / dragon_tiger / boards: no offshore data feed today -> not_supported.
            for block in ("capital_flow", "dragon_tiger", "boards"):
                result_ctx[block] = self._build_fundamental_block(
                    "not_supported",
                    {},
                    [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                    ["not supported for offshore market"],
                )

            # institution: tw (Taiwan stocks) has a free official institutional investors (institutional net buy/sell)
            # feed (TWSE T86 / TPEx OpenAPI); every other offshore market keeps not_supported.
            # tw-only + strictly additive + fail-open: any error or no-data -> not_supported,
            # which never interrupts the main analysis. Raw net figures only — no derived
            # signal / score / schema (per the v2 scope confirmed on issue #1777).
            tw_record = None
            if market == "tw":
                fetcher = getattr(self, "_tw_institutional_fetcher", None)
                if fetcher is None:
                    # Wiring (import + construct) is a one-time op; a failure here is a
                    # programming / deploy bug, so log it LOUD (error). Still fail-open
                    # (never interrupt the main analysis — a hard requirement of #1777).
                    try:
                        from src.data_provider.tw_institutional_fetcher import TwInstitutionalFetcher

                        fetcher = TwInstitutionalFetcher()
                        self._tw_institutional_fetcher = fetcher
                    except Exception as exc:  # broad-exception: fallback_recorded - wiring failure is logged then fail-open
                        log_safe_exception(
                            logger,
                            "Taiwan institutional data fetcher initialization failed",
                            exc,
                            error_code="tw_institutional_fetcher_initialization_failed",
                            level=logging.ERROR,
                            context={"symbol": stock_code},
                        )
                        fetcher = None
                # fetch_timeout == 0 disables per-fetch fundamental fetches (same as valuation /
                # bundle above, which gate on fetch_timeout); honour that for institution too so
                # the FUNDAMENTAL_FETCH_TIMEOUT_SECONDS=0 config semantic is not bypassed.
                if fetcher is not None and fetch_timeout > 0:
                    # The tw institution block is a WHOLE-MARKET download (~4-5s), far slower
                    # than the per-symbol quote/bundle fetches, and it is the LAST offshore
                    # block. When enabled, give it the full REMAINING stage budget rather than
                    # the ~3s per-fetch cap that starves it and makes the first/only stock of a
                    # run coin-flip between ok and not_supported. Bounded by the stage deadline
                    # via _run_with_retry, so it fails open (never blocks).
                    inst_timeout = max(stage_timeout - (time.time() - start_ts), 0.0)
                    if inst_timeout > 0:
                        tw_record, inst_err, _inst_ms = self._run_with_retry(
                            lambda: fetcher.get_institutional_net(stock_code),
                            inst_timeout,
                            "fundamental_tw_institution",
                        )
                        if inst_err:
                            logger.warning(
                                "Taiwan institutional data fetch failed or timed out symbol=%s",
                                stock_code,
                            )
                    else:
                        tw_record = None
            # status 'ok' only when the record carries all core net figures (a genuine 0 is
            # kept — 0 is not None); None / missing core field / fetch failure -> not_supported.
            _tw_core = ("foreign_net", "trust_net", "dealer_net", "total_net")
            if tw_record is not None and all(tw_record.get(key) is not None for key in _tw_core):
                institution_status = "ok"
                result_ctx["institution"] = self._build_fundamental_block(
                    "ok",
                    {
                        "foreign_net": tw_record.get("foreign_net"),
                        "trust_net": tw_record.get("trust_net"),
                        "dealer_net": tw_record.get("dealer_net"),
                        "total_net": tw_record.get("total_net"),
                        "unit": tw_record.get("unit"),
                        "date": tw_record.get("date"),
                        "source": tw_record.get("source"),
                    },
                    [{"provider": tw_record.get("source", "tw-institutional"), "result": "ok", "duration_ms": 0}],
                    [],
                )
            else:
                institution_status = "not_supported"
                result_ctx["institution"] = self._build_fundamental_block(
                    "not_supported",
                    {},
                    [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                    ["not supported for offshore market"],
                )

            result_ctx["belong_boards"] = belong_boards

            block_statuses = {
                "valuation": result_ctx["valuation"].get("status", "not_supported"),
                "growth": growth_status,
                "earnings": earnings_status,
                "institution": institution_status,
                "capital_flow": "not_supported",
                "dragon_tiger": "not_supported",
                "boards": "not_supported",
            }
            result_ctx["coverage"] = block_statuses
            for block in ("valuation", "growth", "earnings", "institution", "capital_flow", "dragon_tiger", "boards"):
                result_ctx["errors"].extend(result_ctx[block].get("errors", []))
                result_ctx["source_chain"].extend(result_ctx[block].get("source_chain", []))

            active_statuses = {"valuation": valuation_status, "growth": growth_status, "earnings": earnings_status}
            # tw institution (when present) counts toward the OVERALL status so a report that
            # only has institutional investors data still surfaces fundamentals (consumers key off the top-level
            # status). missing_fields stays the original three blocks, so offshore markets
            # without institution data are byte-identical (institution is not_supported there).
            status_values = list(active_statuses.values())
            if institution_status == "ok":
                status_values.append("ok")
            if all(value == "not_supported" for value in status_values):
                result_ctx["status"] = "not_supported"
                result_ctx["data_quality"] = "unavailable"
            elif "failed" in status_values or "partial" in status_values:
                result_ctx["status"] = "partial"
                result_ctx["data_quality"] = "partial"
            else:
                result_ctx["status"] = "ok"
                result_ctx["data_quality"] = "ok"
            result_ctx["missing_fields"] = [
                block for block, status in active_statuses.items() if status != "ok"
            ]

            result_ctx["elapsed_ms"] = int((time.time() - start_ts) * 1000)
            return result_ctx

        return self._get_or_load_fundamental_context(
            stock_code,
            stage_timeout,
            _load,
            market=market,
            config=config,
        )

    def build_failed_fundamental_context(self, stock_code: str, reason: str) -> Dict[str, Any]:
        """Build a consistent failed-context payload for caller-side fallback."""
        market = _market_tag(stock_code)
        block_names = (
            "valuation",
            "growth",
            "earnings",
            "institution",
            "capital_flow",
            "dragon_tiger",
            "boards",
        )
        blocks = {
            block: self._build_fundamental_block(
                "failed",
                {},
                [{"provider": "fundamental_pipeline", "result": "failed", "duration_ms": 0}],
                [reason],
            )
            for block in block_names
        }
        return {
            "market": market,
            "status": "failed",
            "coverage": {block: "failed" for block in block_names},
            "source_chain": [{"provider": "fundamental_pipeline", "result": "failed", "duration_ms": 0}],
            "errors": [reason],
            **blocks,
        }

    def build_validation_rejected_fundamental_context(
        self,
        stock_code: str,
        rejection: Any,
    ) -> Dict[str, Any]:
        """Build a typed upper-layer policy outcome without claiming provider failure."""
        market = _market_tag(stock_code)
        reason_codes = [
            sanitize_diagnostic_text(code, max_length=96)
            for code in getattr(rejection, "reason_codes", ())
            if sanitize_diagnostic_text(code, max_length=96)
        ][:24]
        evidence = getattr(rejection, "evidence", None)
        evidence_list = [dict(evidence)] if isinstance(evidence, dict) else []
        source_chain = [
            {
                "provider": "data_validation",
                "result": "rejected",
                "duration_ms": 0,
            }
        ]
        block_names = (
            "valuation",
            "growth",
            "earnings",
            "institution",
            "capital_flow",
            "dragon_tiger",
            "boards",
        )
        blocks = {
            block: self._build_fundamental_block(
                "validation_rejected",
                {},
                source_chain,
                reason_codes or ["data_validation_rejected"],
            )
            for block in block_names
        }
        return {
            "market": market,
            "status": "validation_rejected",
            "data_quality": "rejected",
            "coverage": {block: "validation_rejected" for block in block_names},
            "source_chain": source_chain,
            "errors": reason_codes or ["data_validation_rejected"],
            "validation_rejection": {
                "outcome": "rejected",
                "reason_codes": reason_codes,
            },
            "data_quality_evidence": evidence_list,
            **blocks,
        }

    def get_fundamental_context(
        self,
        stock_code: str,
        budget_seconds: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Aggregate fundamental blocks with fail-open semantics.
        """
        config = self._get_fundamental_config()
        if not config.enable_fundamental_pipeline:
            return self._build_market_not_supported(
                market=_market_tag(stock_code),
                reason="fundamental pipeline disabled",
            )

        stock_code = normalize_stock_code(stock_code)
        market = _market_tag(stock_code)
        is_etf = _is_etf_code(stock_code)
        if market == "crypto":
            return self._build_market_not_supported(
                market="crypto",
                reason="equity fundamentals do not apply to crypto assets",
            )
        if market in {"us", "hk", "jp", "kr", "tw"}:
            return self._build_offshore_fundamental_context(
                stock_code,
                market=market,
                budget_seconds=budget_seconds,
            )

        stage_timeout = float(
            budget_seconds if budget_seconds is not None else config.fundamental_stage_timeout_seconds
        )
        stage_timeout = max(0.0, stage_timeout)
        fetch_timeout = float(config.fundamental_fetch_timeout_seconds)
        fetch_timeout = max(0.0, fetch_timeout)

        def _load() -> Dict[str, Any]:
            remaining_seconds = stage_timeout
            result_ctx: Dict[str, Any] = {
                "market": market,
                "valuation": {},
                "growth": {},
                "earnings": {},
                "institution": {},
                "capital_flow": {},
                "dragon_tiger": {},
                "boards": {},
                "coverage": {},
                "source_chain": [],
                "errors": [],
            }

            start_ts = time.time()

            def _consume_budget(consumed_ms: int) -> None:
                nonlocal remaining_seconds
                remaining_seconds = max(0.0, remaining_seconds - consumed_ms / 1000.0)

            valuation_timeout = min(fetch_timeout, remaining_seconds)
            if valuation_timeout > 0:
                quote_payload, valuation_err, valuation_ms = self._run_with_retry(
                    lambda: self.get_realtime_quote(stock_code),
                    valuation_timeout,
                    "fundamental_valuation",
                )
                _consume_budget(valuation_ms)
            else:
                quote_payload, valuation_err, valuation_ms = None, "fundamental stage timeout", 0

            valuation_payload = {
                "pe_ratio": getattr(quote_payload, "pe_ratio", None) if quote_payload else None,
                "pb_ratio": getattr(quote_payload, "pb_ratio", None) if quote_payload else None,
                "total_mv": getattr(quote_payload, "total_mv", None) if quote_payload else None,
                "circ_mv": getattr(quote_payload, "circ_mv", None) if quote_payload else None,
            }
            valuation_status = self._infer_block_status(
                valuation_payload,
                "partial" if quote_payload is not None else "not_supported",
            )
            if valuation_status == "partial" and valuation_err and not self._has_meaningful_payload(valuation_payload):
                valuation_status = "failed"
            result_ctx["valuation"] = self._build_fundamental_block(
                valuation_status,
                valuation_payload,
                self._normalize_source_chain(
                    [{"provider": "realtime_quote", "result": valuation_status, "duration_ms": valuation_ms}],
                    "realtime_quote",
                    valuation_status,
                    valuation_ms,
                ),
                [valuation_err] if valuation_err else [],
            )

            # growth / earnings / institution (one AkShare call)
            if remaining_seconds <= 0:
                bundle_status = "failed"
                bundle_payload: Dict[str, Any] = {}
                bundle_errors = ["fundamental stage timeout"]
                bundle_ms = 0
            else:
                bundle_timeout = min(fetch_timeout, remaining_seconds)
                bundle_payload, bundle_err_msg, bundle_ms = self._run_with_retry(
                    lambda: self._fundamental_adapter.get_fundamental_bundle(stock_code),
                    bundle_timeout,
                    "fundamental_bundle",
                )
                _consume_budget(bundle_ms)
                if not isinstance(bundle_payload, dict):
                    bundle_status = "failed"
                    bundle_payload = {}
                    bundle_errors = ["fundamental_bundle failed"]
                    if bundle_err_msg:
                        bundle_errors.append(bundle_err_msg)
                else:
                    bundle_status = str(bundle_payload.get("status", "not_supported"))
                    bundle_errors = [bundle_err_msg] if bundle_err_msg else []

            bundle_chain = self._normalize_source_chain(
                bundle_payload.get("source_chain", []),
                "fundamental_bundle",
                bundle_status,
                bundle_ms,
            ) if isinstance(bundle_payload, dict) else self._normalize_source_chain(
                None,
                "fundamental_bundle",
                bundle_status,
                bundle_ms,
            )
            growth_payload = bundle_payload.get("growth", {}) if isinstance(bundle_payload, dict) else {}
            earnings_payload = bundle_payload.get("earnings", {}) if isinstance(bundle_payload, dict) else {}
            institution_payload = bundle_payload.get("institution", {}) if isinstance(bundle_payload, dict) else {}
            if not isinstance(growth_payload, dict):
                growth_payload = {}
            else:
                growth_payload = dict(growth_payload)
            if not isinstance(earnings_payload, dict):
                earnings_payload = {}
            else:
                earnings_payload = dict(earnings_payload)
            if not isinstance(institution_payload, dict):
                institution_payload = {}
            else:
                institution_payload = dict(institution_payload)

            # Derive TTM dividend yield from already-fetched quote price; avoid extra quote calls.
            earnings_extra_errors: List[str] = []
            dividend_payload = earnings_payload.get("dividend")
            if isinstance(dividend_payload, dict):
                dividend_payload = dict(dividend_payload)
                ttm_cash_raw = dividend_payload.get("ttm_cash_dividend_per_share")
                ttm_cash = None
                if ttm_cash_raw is not None:
                    try:
                        ttm_cash = float(ttm_cash_raw)
                    except (TypeError, ValueError):
                        earnings_extra_errors.append("invalid_ttm_cash_dividend_per_share")
                if isinstance(quote_payload, dict):
                    latest_price_raw = quote_payload.get("price")
                else:
                    latest_price_raw = getattr(quote_payload, "price", None) if quote_payload else None
                latest_price = None
                if latest_price_raw is not None:
                    try:
                        latest_price = float(latest_price_raw)
                    except (TypeError, ValueError):
                        latest_price = None
                ttm_yield = None
                if ttm_cash is not None:
                    if latest_price is not None and latest_price > 0:
                        ttm_yield = round(ttm_cash / latest_price * 100.0, 4)
                    else:
                        earnings_extra_errors.append("invalid_price_for_ttm_dividend_yield")

                dividend_payload["ttm_dividend_yield_pct"] = ttm_yield
                if ttm_yield is not None:
                    dividend_payload["yield_formula"] = "ttm_cash_dividend_per_share / latest_price * 100"
                earnings_payload["dividend"] = dividend_payload

            adapter_errors = list(bundle_payload.get("errors", [])) if isinstance(bundle_payload, dict) else []
            adapter_errors.extend(bundle_errors)
            growth_errors = list(adapter_errors)
            earnings_errors = list(adapter_errors)
            earnings_errors.extend(earnings_extra_errors)
            institution_errors = list(adapter_errors)

            growth_status = self._infer_block_status(growth_payload, bundle_status)
            earnings_status = self._infer_block_status(earnings_payload, bundle_status)
            institution_status = self._infer_block_status(institution_payload, bundle_status)

            result_ctx["growth"] = self._build_fundamental_block(
                growth_status,
                growth_payload,
                bundle_chain,
                growth_errors,
            )
            result_ctx["earnings"] = self._build_fundamental_block(
                earnings_status,
                earnings_payload,
                bundle_chain,
                earnings_errors,
            )
            result_ctx["institution"] = self._build_fundamental_block(
                institution_status,
                institution_payload,
                bundle_chain,
                institution_errors,
            )

            # capital flow
            if is_etf:
                result_ctx["capital_flow"] = self._build_fundamental_block(
                    "not_supported",
                    {},
                    [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                    ["etf not fully supported"],
                )
                result_ctx["dragon_tiger"] = self._build_fundamental_block(
                    "not_supported",
                    {},
                    [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                    ["etf not fully supported"],
                )
                result_ctx["boards"] = self._build_fundamental_block(
                    "not_supported",
                    {},
                    [{"provider": "fundamental_pipeline", "result": "not_supported", "duration_ms": 0}],
                    ["etf not fully supported"],
                )
                result_ctx["status"] = "partial"
            else:
                capital_flow_budget = min(fetch_timeout, remaining_seconds)
                capital_flow_start = time.time()
                result_ctx["capital_flow"] = self.get_capital_flow_context(
                    stock_code,
                    budget_seconds=capital_flow_budget,
                )
                _consume_budget(int((time.time() - capital_flow_start) * 1000))

                dragon_tiger_budget = min(fetch_timeout, remaining_seconds)
                dragon_tiger_start = time.time()
                result_ctx["dragon_tiger"] = self.get_dragon_tiger_context(
                    stock_code,
                    budget_seconds=dragon_tiger_budget,
                )
                _consume_budget(int((time.time() - dragon_tiger_start) * 1000))

                result_ctx["boards"] = self.get_board_context(
                    stock_code,
                    budget_seconds=min(fetch_timeout, remaining_seconds),
                )

            block_statuses = {
                "valuation": result_ctx["valuation"].get("status", "not_supported"),
                "growth": result_ctx["growth"].get("status", "not_supported"),
                "earnings": result_ctx["earnings"].get("status", "not_supported"),
                "institution": result_ctx["institution"].get("status", "not_supported"),
                "capital_flow": result_ctx["capital_flow"].get("status", "not_supported"),
                "dragon_tiger": result_ctx["dragon_tiger"].get("status", "not_supported"),
                "boards": result_ctx["boards"].get("status", "not_supported"),
            }
            result_ctx["coverage"] = block_statuses
            for block in (
                "valuation",
                "growth",
                "earnings",
                "institution",
                "capital_flow",
                "dragon_tiger",
                "boards",
            ):
                result_ctx["errors"].extend(result_ctx[block].get("errors", []))
                result_ctx["source_chain"].extend(result_ctx[block].get("source_chain", []))

            if is_etf:
                # Keep ETF downgrade semantics for overall status even when valuation is available.
                result_ctx["status"] = (
                    "not_supported" if all(value == "not_supported" for value in block_statuses.values()) else "partial"
                )
            elif all(value == "not_supported" for value in block_statuses.values()):
                result_ctx["status"] = "not_supported"
            elif "failed" in block_statuses.values() or "partial" in block_statuses.values():
                result_ctx["status"] = "partial"
            else:
                result_ctx["status"] = "ok"

            result_ctx["elapsed_ms"] = int((time.time() - start_ts) * 1000)
            return result_ctx

        return self._get_or_load_fundamental_context(
            stock_code,
            stage_timeout,
            _load,
            market=market,
            config=config,
        )


EXPECTED_FUNDAMENTAL_CONTEXT_METHOD_NAMES = (
    "_normalize_source_chain",
    "_block_status",
    "_build_fundamental_block",
    "_has_meaningful_payload",
    "_infer_block_status",
    "_should_cache_fundamental_context",
    "_build_market_not_supported",
    "_build_offshore_fundamental_context",
    "build_failed_fundamental_context",
    "build_validation_rejected_fundamental_context",
    "get_fundamental_context",
)


def bind_fundamental_context_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind fundamental-context descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_FundamentalContextMethods).items():
        if name.startswith("__") or _descriptor_function(descriptor) is None:
            continue
        setattr(
            target_class,
            name,
            _clone_facade_descriptor(
                descriptor,
                global_namespace,
                owner_qualname=target_class.__qualname__,
            ),
        )
        bound_names.append(name)
    return tuple(bound_names)


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
