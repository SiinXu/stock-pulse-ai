# -*- coding: utf-8 -*-
"""Market-review news retrieval and persisted-intelligence merge.

Issue #1085 step 7. Pure news formatters already live in
``src.market.formatters`` (step 4) and the markdown block builder in
``src.market.blocks`` (step 5); this module owns the retrieval and merge
orchestration that stayed behind.

This module must not import ``MarketAnalyzer``; every function receives
``owner`` and reaches ``search_service``, ``config``, ``profile``, ``region``,
``_log_context``, ``_get_review_language``, and ``_get_news_field`` through it,
so class-level and instance-level overrides stay effective.

``IntelligenceService`` is imported here (the original analyzer module-level
binding) and resolved through the owner's defining module at call time so
``patch("src.market.analyzer.IntelligenceService")`` still applies. Duck-typed
owners without that name fall back to this module's binding.
"""

from __future__ import annotations

import logging
import sys
from typing import Any, Dict, List

from src.services.intelligence_service import IntelligenceService
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger("src.market.analyzer")

__all__ = (
    "search_market_news",
    "normalize_news_item",
    "merge_persisted_market_intelligence",
)


def _resolve_intelligence_service(owner: Any) -> Any:
    """Use the owner's module binding, else this module's real import."""
    module = sys.modules.get(getattr(type(owner), "__module__", "") or "")
    if module is None:
        return IntelligenceService
    return getattr(module, "IntelligenceService", IntelligenceService)


def search_market_news(owner: Any) -> List[Dict]:
    """
    搜索市场新闻
    
    Returns:
        新闻列表
    """
    if not owner.search_service:
        logger.warning(
            "[大盘] %s action=search_market_news status=skipped reason=no_search_service",
            owner._log_context(),
        )
        return []

    all_news = []

    # Use different news search terms based on region.
    search_queries = owner.profile.news_queries
    review_language = owner._get_review_language()
    market_names = {
        "cn": "大盘" if review_language == "zh" else "A-share market",
        "us": "美股市场" if review_language == "zh" else "US market",
        "hk": "港股市场" if review_language == "zh" else "HK market",
        "jp": "日本股市" if review_language == "zh" else "Japan stock market",
        "kr": "韩国股市" if review_language == "zh" else "Korea stock market",
    }

    try:
        logger.info("[大盘] %s action=search_market_news status=start", owner._log_context())

        # Set search context name based on region to avoid interpreting US stock searches as A-shares context
        market_name = market_names.get(owner.region, "大盘")
        for query in search_queries:
            response = owner.search_service.search_stock_news(
                stock_code="market",
                stock_name=market_name,
                max_results=3,
                focus_keywords=query.split()
            )
            if response and response.results:
                all_news.extend(response.results)
                logger.info(
                    "[大盘] %s action=search_market_news status=query_success count=%d",
                    owner._log_context(),
                    len(response.results),
                )

        logger.info(
            "[大盘] %s action=search_market_news status=success count=%d",
            owner._log_context(),
            len(all_news),
        )

    except Exception as e:  # broad-exception: fallback_recorded - news failure is logged before fallback
        log_safe_exception(
            logger,
            "Market review news search failed",
            e,
            error_code="market_review_news_search_failed",
            level=logging.ERROR,
            context={"region": owner.region},
        )

    return all_news


def normalize_news_item(owner: Any, item: Any) -> Dict[str, str]:
    return {
        "title": owner._compact_news_text(owner._get_news_field(item, "title"), limit=120),
        "snippet": owner._compact_news_text(owner._get_news_field(item, "snippet"), limit=260),
        "source": owner._compact_news_text(owner._get_news_field(item, "source"), limit=80),
        "published_date": owner._compact_news_text(owner._get_news_field(item, "published_date"), limit=40),
        "url": owner._compact_news_text(owner._get_news_field(item, "url"), limit=240),
    }


def merge_persisted_market_intelligence(owner: Any, news: List) -> List:
    """Merge local persisted market intelligence and search news with bounded prompt/payload slot preservation."""
    search_news = list(news or [])
    merged_local = []
    seen_urls = {
        owner._get_news_field(item, "url")
        for item in search_news
        if owner._get_news_field(item, "url")
    }
    try:
        service_cls = _resolve_intelligence_service(owner)
        service = service_cls(config=owner.config)
        service.refresh_auto_sources()
        payload = service.list_items(
            scope_type="market",
            market=owner.region,
            published_days=max(1, int(owner.config.get_effective_news_window_days() or 1)),
            page=1,
            page_size=6,
        )
        for item in payload.get("items", []):
            if not isinstance(item, dict):
                continue
            url = str(item.get("url") or "")
            if url and url in seen_urls:
                continue
            seen_urls.add(url)
            merged_local.append({
                "title": item.get("title") or "未命名资讯",
                "snippet": item.get("summary") or "",
                "source": item.get("source") or item.get("source_name") or "local-intel",
                "published_date": item.get("published_at") or "",
                "url": "" if url.startswith("no-url:intel:") else url,
            })
    except Exception as exc:  # broad-exception: fallback_recorded - local intelligence failure is logged
        log_safe_exception(
            logger,
            "Market review local intelligence load failed",
            exc,
            error_code="market_review_local_intelligence_load_failed",
            level=logging.DEBUG,
            context={"region": owner.region},
        )
    merged_news = []
    merged_local_index = 0
    merged_search_index = 0
    while merged_local_index < len(merged_local) or merged_search_index < len(search_news):
        if merged_local_index < len(merged_local):
            merged_news.append(merged_local[merged_local_index])
            merged_local_index += 1
        if merged_search_index < len(search_news):
            merged_news.append(search_news[merged_search_index])
            merged_search_index += 1
    return merged_news
