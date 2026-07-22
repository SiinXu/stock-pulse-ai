# -*- coding: utf-8 -*-
"""AlphaSift service methods extracted from the public facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.alphasift_service import (
        Any,
        Config,
        DSA_ALPHASIFT_HOTSPOT_DETAIL_FALLBACK_CODE,
        DSA_ALPHASIFT_HOTSPOT_DETAIL_PREFETCH_FAILED_CODE,
        DSA_ALPHASIFT_HOTSPOT_DETAIL_SOURCE_ERROR_CODE,
        DSA_ALPHASIFT_HOTSPOT_DETAIL_STALE_CACHE_CODE,
        DSA_ALPHASIFT_HOTSPOT_DIRECT_FALLBACK_FAILED_CODE,
        DSA_ALPHASIFT_HOTSPOT_DIRECT_FALLBACK_USED_CODE,
        DSA_ALPHASIFT_HOTSPOT_PREFETCH_DETAIL_COUNT,
        DSA_ALPHASIFT_HOTSPOT_REFRESH_FAILED_CODE,
        DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE,
        DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_MESSAGE,
        Dict,
        DsaEastMoneyHotspotProvider,
        HTTPException,
        Request,
        _alphasift_hotspot_cache_path,
        _alphasift_hotspot_history_path,
        _alphasift_runtime_env,
        _attach_cached_hotspot_details,
        _build_hotspot_event_routes_from_search,
        _call_alphasift_screen,
        _classify_hotspot_source_errors,
        _empty_alphasift_hotspot_payload,
        _enrich_candidates_with_dsa,
        _enrich_hotspot_rows_from_provider,
        _ensure_alphasift_available_for_use,
        _ensure_alphasift_enabled,
        _ensure_alphasift_install_access,
        _ensure_hotspot_detail_compat_fields,
        _ensure_supported_market,
        _ensure_supported_strategy,
        _env_text,
        _get_adapter_callable,
        _get_alphasift_source_health_snapshot,
        _get_alphasift_status_snapshot,
        _get_dsa_adapter,
        _has_degraded_eastmoney_hotspot_failure,
        _hotspot_route_has_external_event,
        _hotspot_rows_are_thin,
        _hotspot_topic_from_row,
        _import_alphasift_hotspot,
        _install_alphasift,
        _is_default_alphasift_install_spec,
        _list_strategies,
        _list_text_values,
        _load_alphasift_hotspot_cache,
        _load_alphasift_hotspot_detail_cache,
        _log_unexpected_alphasift_exception,
        _merge_provider_hotspot_route_fallback,
        _normalize_alphasift_hotspot_detail,
        _normalize_candidates,
        _public_diagnostic_codes,
        _remove_non_finite_json_values,
        _resolve_hotspot_provider,
        _sanitize_public_alphasift_diagnostics,
        _should_return_eastmoney_hotspot_unavailable,
        _to_plain,
        _topic_log_context,
        _write_alphasift_hotspot_cache,
        _write_alphasift_hotspot_detail_cache,
        log_safe_exception,
        logger,
        logging,
    )


class AlphaSiftService:
    """Coordinate AlphaSift calls with DSA-owned runtime capabilities."""

    def __init__(self, config: Config):
        self.config = config

    def status(self) -> Dict[str, Any]:
        adapter_status, available, diagnostics = _get_alphasift_status_snapshot()
        payload = {
            "enabled": bool(self.config.alphasift_enabled),
            "available": available,
            "install_spec_is_default": _is_default_alphasift_install_spec(self.config.alphasift_install_spec),
            "contract_version": adapter_status.get("contract_version"),
            "version": adapter_status.get("version"),
            "strategy_count": adapter_status.get("strategy_count"),
        }
        source_health = _get_alphasift_source_health_snapshot()
        if source_health:
            payload["source_health"] = source_health
        if diagnostics:
            payload["diagnostics"] = diagnostics
        return _sanitize_public_alphasift_diagnostics(payload)

    def strategies(self) -> Dict[str, Any]:
        _ensure_alphasift_enabled(self.config)
        _ensure_alphasift_available_for_use()
        strategies = _list_strategies()
        return {
            "enabled": True,
            "strategies": strategies,
            "strategy_count": len(strategies),
        }

    def install(self, *, request: Request) -> Dict[str, Any]:
        _ensure_alphasift_install_access(request)
        _ensure_alphasift_enabled(self.config)
        return _install_alphasift(self.config)

    def hotspots(
        self,
        *,
        provider: str = "",
        top: int = 12,
        refresh: bool = False,
        include_details: bool = False,
    ) -> Dict[str, Any]:
        _ensure_alphasift_enabled(self.config)
        _ensure_alphasift_available_for_use()
        provider_name, provider_arg = _resolve_hotspot_provider(provider)
        top_count = max(1, min(int(top or 12), 50))
        if not refresh:
            cached = _load_alphasift_hotspot_cache(provider=provider_name, top=top_count)
            if cached is not None:
                return _attach_cached_hotspot_details(cached, provider=provider_name, top=top_count) if include_details else cached
            return _empty_alphasift_hotspot_payload(
                provider=provider_name,
                message="No cached AlphaSift hotspot snapshot. Click refresh to fetch live hotspots.",
            )

        hotspot_module = _import_alphasift_hotspot()
        discover_hotspots = _get_adapter_callable(
            hotspot_module,
            "discover_hotspots",
            "discover_hotspots() is not callable.",
        )

        try:
            with _alphasift_runtime_env(self.config):
                raw = discover_hotspots(
                    provider=provider_arg,
                    top=top_count,
                    history_path=_alphasift_hotspot_history_path(),
                    fallback_cache_path=_alphasift_hotspot_cache_path(),
                )
        except HTTPException:
            raise
        except Exception as exc:  # broad-exception: optional_metadata - Live hotspot data may degrade to cache or a classified unavailable payload.
            cached = _load_alphasift_hotspot_cache(provider=provider_name, top=top_count)
            if cached is not None:
                errors = list(cached.get("source_errors") or [])
                errors.append(DSA_ALPHASIFT_HOTSPOT_REFRESH_FAILED_CODE)
                cached["source_errors"] = errors
                cached["fallback_used"] = True
                cached["cache_used"] = True
                log_safe_exception(
                    logger,
                    "AlphaSift hotspot live refresh failed; serving cache",
                    exc,
                    error_code=DSA_ALPHASIFT_HOTSPOT_REFRESH_FAILED_CODE,
                    level=logging.WARNING,
                )
                fallback_payload = (
                    _attach_cached_hotspot_details(cached, provider=provider_name, top=top_count)
                    if include_details
                    else cached
                )
                return _sanitize_public_alphasift_diagnostics(fallback_payload)
            if not _should_return_eastmoney_hotspot_unavailable(provider_arg, exc):
                diagnostics = _log_unexpected_alphasift_exception("hotspot_refresh", exc)
                raise HTTPException(
                    status_code=424,
                    detail={
                        "error": DSA_ALPHASIFT_HOTSPOT_REFRESH_FAILED_CODE,
                        "message": "AlphaSift 热点刷新失败，请稍后重试。",
                        "diagnostics": diagnostics,
                    },
                ) from exc
            log_safe_exception(
                logger,
                "AlphaSift hotspot live refresh failed without cache",
                exc,
                error_code=DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE,
                level=logging.WARNING,
            )
            return _empty_alphasift_hotspot_payload(
                provider=provider_name,
                provider_used=type(provider_arg).__name__,
                source_errors=[DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE],
                message=DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_MESSAGE,
            )

        items = _remove_non_finite_json_values(_to_plain(raw))
        if not isinstance(items, list):
            items = []
        selected = items[:top_count]
        raw_source_errors = _list_text_values(getattr(raw, "source_errors", []))
        direct_hotspot_fallback_used = False
        if isinstance(provider_arg, DsaEastMoneyHotspotProvider) and _hotspot_rows_are_thin(selected, top=top_count):
            try:
                direct_hotspots = provider_arg.hotspot_rows(top=top_count)
            except Exception as exc:  # broad-exception: fallback_recorded - Keep the contract rows when direct enrichment fails.
                log_safe_exception(
                    logger,
                    "AlphaSift direct hotspot fallback failed",
                    exc,
                    error_code=DSA_ALPHASIFT_HOTSPOT_DIRECT_FALLBACK_FAILED_CODE,
                    level=logging.WARNING,
                )
                direct_hotspots = []
                raw_source_errors.append(DSA_ALPHASIFT_HOTSPOT_DIRECT_FALLBACK_FAILED_CODE)
            if len(direct_hotspots) > len(selected):
                selected = direct_hotspots
                direct_hotspot_fallback_used = True
                raw_source_errors.append(DSA_ALPHASIFT_HOTSPOT_DIRECT_FALLBACK_USED_CODE)
        if isinstance(provider_arg, DsaEastMoneyHotspotProvider) and selected:
            selected = _enrich_hotspot_rows_from_provider(selected, provider_arg, top=top_count)
        if not selected and raw_source_errors:
            cached = _load_alphasift_hotspot_cache(provider=provider_name, top=top_count)
            if cached is not None:
                errors = list(cached.get("source_errors") or [])
                errors.extend(_classify_hotspot_source_errors(
                    raw_source_errors,
                    eastmoney=isinstance(provider_arg, DsaEastMoneyHotspotProvider),
                ))
                cached["source_errors"] = errors
                cached["fallback_used"] = True
                cached["cache_used"] = True
                fallback_payload = (
                    _attach_cached_hotspot_details(cached, provider=provider_name, top=top_count)
                    if include_details
                    else cached
                )
                return _sanitize_public_alphasift_diagnostics(fallback_payload)
            if _has_degraded_eastmoney_hotspot_failure(provider_arg, raw_source_errors):
                return _empty_alphasift_hotspot_payload(
                    provider=provider_name,
                    provider_used=str(getattr(raw, "provider_used", "") or type(provider_arg).__name__),
                    source_errors=[DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_CODE],
                    message=DSA_ALPHASIFT_HOTSPOT_UNAVAILABLE_MESSAGE,
                )
        source_errors = _classify_hotspot_source_errors(
            raw_source_errors,
            eastmoney=isinstance(provider_arg, DsaEastMoneyHotspotProvider),
        )

        payload = {
            "enabled": True,
            "provider": provider_name,
            "provider_used": "dsa_eastmoney_board_change" if direct_hotspot_fallback_used else str(getattr(raw, "provider_used", "")),
            "fallback_used": direct_hotspot_fallback_used or bool(getattr(raw, "fallback_used", False)),
            "cache_used": False,
            "cached_at": None,
            "source_errors": source_errors,
            "stale": bool(getattr(raw, "stale", False)),
            "stale_age_hours": getattr(raw, "stale_age_hours", None),
            "hotspots": selected,
            "hotspot_count": len(selected),
        }
        if selected and include_details:
            payload = self._prefetch_hotspot_details(payload, provider=provider_name, refresh=False)
        if selected:
            _write_alphasift_hotspot_cache(payload)
        return _sanitize_public_alphasift_diagnostics(payload)

    def _prefetch_hotspot_details(self, payload: Dict[str, Any], *, provider: str, refresh: bool) -> Dict[str, Any]:
        rows = payload.get("hotspots")
        if not isinstance(rows, list) or not rows:
            return payload
        details = dict(payload.get("details") if isinstance(payload.get("details"), dict) else {})
        source_errors = _list_text_values(payload.get("source_errors"))
        for row in rows[:DSA_ALPHASIFT_HOTSPOT_PREFETCH_DETAIL_COUNT]:
            topic = _hotspot_topic_from_row(row)
            if not topic or (topic in details and not refresh):
                continue
            try:
                details[topic] = self.hotspot_detail(topic=topic, provider=provider, refresh=refresh)
            except HTTPException as exc:
                source_errors.append(DSA_ALPHASIFT_HOTSPOT_DETAIL_PREFETCH_FAILED_CODE)
                log_safe_exception(
                    logger,
                    "AlphaSift hotspot detail prefetch failed with an HTTP error",
                    exc,
                    error_code=DSA_ALPHASIFT_HOTSPOT_DETAIL_PREFETCH_FAILED_CODE,
                    level=logging.WARNING,
                    context=_topic_log_context(topic, provider=provider),
                )
            except Exception as exc:  # broad-exception: fallback_recorded - Keep the hotspot list when optional detail prefetch fails.
                source_errors.append(DSA_ALPHASIFT_HOTSPOT_DETAIL_PREFETCH_FAILED_CODE)
                log_safe_exception(
                    logger,
                    "AlphaSift hotspot detail prefetch failed",
                    exc,
                    error_code=DSA_ALPHASIFT_HOTSPOT_DETAIL_PREFETCH_FAILED_CODE,
                    level=logging.WARNING,
                    context=_topic_log_context(topic, provider=provider),
                )
        attached = dict(payload)
        if details:
            attached["details"] = _remove_non_finite_json_values(details)
        if source_errors:
            attached["source_errors"] = source_errors
        return _sanitize_public_alphasift_diagnostics(attached)

    def hotspot_detail(self, *, topic: str, provider: str = "", refresh: bool = False) -> Dict[str, Any]:
        _ensure_alphasift_enabled(self.config)
        _ensure_alphasift_available_for_use()
        topic_text = _env_text(topic)
        if not topic_text:
            raise HTTPException(
                status_code=400,
                detail={"error": "alphasift_hotspot_topic_required", "message": "热点题材名称不能为空。"},
            )
        provider_name, provider_arg = _resolve_hotspot_provider(provider)
        if not isinstance(provider_arg, DsaEastMoneyHotspotProvider):
            provider_arg = DsaEastMoneyHotspotProvider()
        cached = None if refresh else _load_alphasift_hotspot_detail_cache(provider=provider_name, topic=topic_text)
        if cached is not None:
            return cached
        normalized: Dict[str, Any] = {}
        hotspot_helper_failed = False
        try:
            try:
                hotspot_module = _import_alphasift_hotspot()
                get_hotspot_detail = getattr(hotspot_module, "get_hotspot_detail", None)
            except Exception:  # broad-exception: optional_metadata - The optional contract helper may fall back to provider detail.
                get_hotspot_detail = None
            with _alphasift_runtime_env(self.config):
                if callable(get_hotspot_detail) and type(provider_arg) is DsaEastMoneyHotspotProvider:
                    try:
                        detail = get_hotspot_detail(
                            topic_text,
                            provider=provider_arg,
                            top_stocks=30,
                            history_path=_alphasift_hotspot_history_path(),
                            fallback_cache_path=_alphasift_hotspot_cache_path(),
                        )
                        normalized = _normalize_alphasift_hotspot_detail(
                            detail,
                            provider=provider_name,
                            requested_topic=topic_text,
                        )
                        normalized = _merge_provider_hotspot_route_fallback(
                            normalized,
                            provider=provider_arg,
                            topic=topic_text,
                        )
                    except Exception as exc:  # broad-exception: fallback_recorded - Fall back to provider-owned hotspot detail.
                        hotspot_helper_failed = True
                        log_safe_exception(
                            logger,
                            "AlphaSift contract hotspot detail fallback to provider",
                            exc,
                            error_code=DSA_ALPHASIFT_HOTSPOT_DETAIL_FALLBACK_CODE,
                            level=logging.WARNING,
                            context=_topic_log_context(
                                topic_text,
                                provider=provider_name,
                            ),
                        )
                else:
                    normalized = provider_arg.hotspot_detail(topic_text)
                if not normalized:
                    normalized = provider_arg.hotspot_detail(topic_text)
        except Exception as exc:  # broad-exception: fallback_recorded - Serve stale cache or return the classified source failure.
            log_safe_exception(
                logger,
                "AlphaSift hotspot detail fetch failed",
                exc,
                error_code=DSA_ALPHASIFT_HOTSPOT_DETAIL_SOURCE_ERROR_CODE,
                level=logging.WARNING,
                context=_topic_log_context(topic_text, provider=provider_name),
            )
            stale_cached = _load_alphasift_hotspot_detail_cache(
                provider=provider_name,
                topic=topic_text,
                allow_stale=True,
            )
            if stale_cached is not None:
                source_errors = _list_text_values(stale_cached.get("source_errors"))
                source_errors.append(DSA_ALPHASIFT_HOTSPOT_DETAIL_STALE_CACHE_CODE)
                stale_cached["source_errors"] = source_errors
                stale_cached["fallback_used"] = True
                return _sanitize_public_alphasift_diagnostics(stale_cached)
            raise HTTPException(
                status_code=424,
                detail={
                    "error": "alphasift_hotspot_detail_failed",
                    "message": "AlphaSift 热点详情获取失败，请稍后重试。",
                },
            ) from exc
        if hotspot_helper_failed:
            source_errors = _list_text_values(normalized.get("source_errors"))
            source_errors.append(DSA_ALPHASIFT_HOTSPOT_DETAIL_FALLBACK_CODE)
            normalized["source_errors"] = source_errors
            normalized["fallback_used"] = True
            normalized["provider"] = provider_name
        if not _hotspot_route_has_external_event(normalized.get("route")):
            search_routes = _build_hotspot_event_routes_from_search(topic_text, self.config)
            if search_routes:
                route = normalized.get("route")
                normalized["route"] = search_routes + (route if isinstance(route, list) else [])
        normalized = _ensure_hotspot_detail_compat_fields(normalized)
        normalized["enabled"] = True
        normalized["provider"] = provider_name
        normalized["source_errors"] = _public_diagnostic_codes(
            normalized.get("source_errors"),
            fallback_code=DSA_ALPHASIFT_HOTSPOT_DETAIL_SOURCE_ERROR_CODE,
        )
        cleaned = _sanitize_public_alphasift_diagnostics(_remove_non_finite_json_values(normalized))
        _write_alphasift_hotspot_detail_cache(provider=provider_name, topic=topic_text, payload=cleaned)
        return cleaned

    def screen(self, *, strategy: str, market: str, max_results: int) -> Dict[str, Any]:
        _ensure_alphasift_enabled(self.config)
        _ensure_alphasift_available_for_use()
        _ensure_supported_market(market)
        _ensure_supported_strategy(strategy)

        adapter = _get_dsa_adapter()
        screen = _get_adapter_callable(adapter, "screen", "screen() 不可调用。")
        try:
            raw = _call_alphasift_screen(screen, strategy, market, max_results, self.config)
        except ValueError as exc:
            log_safe_exception(
                logger,
                "AlphaSift screen request was rejected by the adapter",
                exc,
                error_code="alphasift_screen_rejected",
                level=logging.WARNING,
            )
            raise HTTPException(
                status_code=400,
                detail={"error": "alphasift_screen_rejected", "message": "AlphaSift 拒绝了当前选股参数。"},
            ) from exc
        except (TypeError, KeyError) as exc:
            log_safe_exception(
                logger,
                "AlphaSift screen received invalid adapter input",
                exc,
                error_code="alphasift_invalid_input",
                level=logging.WARNING,
            )
            raise HTTPException(
                status_code=422,
                detail={"error": "alphasift_invalid_input", "message": "AlphaSift 选股参数无效。"},
            ) from exc
        except HTTPException:
            raise
        except Exception as exc:  # broad-exception: fallback_recorded - Map unexpected adapter failures to the stable API error.
            log_safe_exception(
                logger,
                "AlphaSift screen execution failed",
                exc,
                error_code="alphasift_screen_failed",
                level=logging.WARNING,
            )
            raise HTTPException(
                status_code=424,
                detail={"error": "alphasift_screen_failed", "message": "AlphaSift 选股运行失败，请稍后重试。"},
            ) from exc

        raw_data = _to_plain(raw)
        if not isinstance(raw_data, dict):
            raw_data = {"candidates": raw_data}
        raw_data = _sanitize_public_alphasift_diagnostics(_remove_non_finite_json_values(raw_data))

        candidates = _normalize_candidates(raw_data)
        selected = candidates[:max_results]
        selected, dsa_enrichment = _enrich_candidates_with_dsa(selected)
        return _sanitize_public_alphasift_diagnostics({
            "enabled": True,
            "candidates": selected,
            "candidate_count": len(selected),
            "run_id": raw_data.get("run_id"),
            "strategy": raw_data.get("strategy") or strategy,
            "market": raw_data.get("market") or market,
            "snapshot_count": raw_data.get("snapshot_count"),
            "snapshot_source": raw_data.get("snapshot_source") or "",
            "after_filter_count": raw_data.get("after_filter_count"),
            "llm_ranked": raw_data.get("llm_ranked"),
            "llm_market_view": raw_data.get("llm_market_view") or "",
            "llm_selection_logic": raw_data.get("llm_selection_logic") or "",
            "llm_portfolio_risk": raw_data.get("llm_portfolio_risk") or "",
            "llm_coverage": raw_data.get("llm_coverage"),
            "llm_parse_errors": _list_text_values(raw_data.get("llm_parse_errors")),
            "warnings": _list_text_values(raw_data.get("warnings")),
            "source_errors": _list_text_values(raw_data.get("source_errors")),
            "dsa_enrichment": dsa_enrichment,
            "deep_analysis_requested": raw_data.get("deep_analysis_requested"),
            "post_analyzers": raw_data.get("post_analyzers") or [],
            "daily_enriched": raw_data.get("daily_enriched"),
            "daily_enrich_count": raw_data.get("daily_enrich_count"),
            "risk_enabled": raw_data.get("risk_enabled"),
            "portfolio_diversity_enabled": raw_data.get("portfolio_diversity_enabled"),
            "portfolio_concentration_notes": raw_data.get("portfolio_concentration_notes") or [],
        })
