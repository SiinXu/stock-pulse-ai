# -*- coding: utf-8 -*-
"""Optional enhancer construction for the stock analysis pipeline.

Request-scoped MarketHotspot, Search, and SocialSentiment construction is
fail-open. Production callers keep importing ``src.core.pipeline``; this mixin
is rebound onto that facade by ``_bind_stage_methods``.

After bind, every constructor name resolves through facade globals, so
``patch("src.core.pipeline.*")`` stays the public seam for all three services.

``SearchService`` lives in ``src.search_service`` and is imported normally.
``MarketHotspotService`` and ``SocialSentimentService`` are referenced without
an import on purpose: a top-level ``src.services`` import here would add a new
``src.core -> src.services`` reverse edge that the layer-direction ratchet bans
(see ``docs/layer-direction-ratchet.md``). Their facade imports in
``src/core/pipeline.py`` are therefore load-bearing even though flake8 reports
them as unused; ``test_optional_services_constructors_resolve_from_facade_globals``
pins that contract.
"""

import logging

from src.search_service import SearchService
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger("src.core.pipeline")


class _OptionalServicesStageMixin:
    """Construct optional search, social, and hotspot services with fail-open init."""

    def _init_optional_market_hotspot_service(self) -> None:
        """Build MarketHotspotService or leave it disabled after a logged failure."""
        self.market_hotspot_service = None
        try:
            self.market_hotspot_service = MarketHotspotService(  # noqa: F821
                fetcher_manager=self.fetcher_manager,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Market-hotspot initialization failure is safely logged before the optional service is disabled.
            log_safe_exception(
                logger,
                "Market hotspot service initialization failed; continuing without hotspot data",
                exc,
                error_code="pipeline_market_hotspot_service_init_failed",
                level=logging.DEBUG,
            )

    def _init_optional_search_service(self) -> None:
        """Build SearchService or disable search after a logged failure."""
        # Initialize the search service (optional, failure should not block the main analysis process)
        try:
            self.search_service = SearchService(
                bocha_keys=self.config.bocha_api_keys,
                tavily_keys=self.config.tavily_api_keys,
                anspire_keys=self.config.anspire_api_keys,
                brave_keys=self.config.brave_api_keys,
                serpapi_keys=self.config.serpapi_keys,
                minimax_keys=self.config.minimax_api_keys,
                searxng_base_urls=self.config.searxng_base_urls,
                searxng_public_instances_enabled=self.config.searxng_public_instances_enabled,
                searxng_timeout_seconds=getattr(
                    self.config, "searxng_timeout_seconds", None
                ),
                rss_news_feed_urls=getattr(self.config, "rss_news_feed_urls", None),
                rss_news_fetch_timeout_sec=getattr(
                    self.config, "rss_news_fetch_timeout_sec", 8.0
                ),
                news_max_age_days=self.config.news_max_age_days,
                news_strategy_profile=getattr(self.config, "news_strategy_profile", "short"),
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Search initialization failure is safely logged before the optional service is disabled.
            log_safe_exception(
                logger,
                "Search service initialization failed; continuing without search",
                exc,
                error_code="pipeline_search_service_init_failed",
                level=logging.WARNING,
            )
            self.search_service = None

    def _log_optional_search_service_status(self) -> None:
        """Report search availability after construction and config-status logs."""
        if self.search_service is None:
            logger.warning("Search service is unavailable because initialization or a dependency failed")
        elif self.search_service.is_available:
            logger.info("Search service enabled")
        else:
            logger.warning("Search service is unavailable because no search capability is configured")

    def _init_optional_social_sentiment_service(self) -> None:
        """Build SocialSentimentService or disable it after a logged failure."""
        # Initialize social sentiment service (for US stocks, optional)
        try:
            self.social_sentiment_service = SocialSentimentService(  # noqa: F821
                api_key=self.config.social_sentiment_api_key,
                api_url=self.config.social_sentiment_api_url,
            )
            if self.social_sentiment_service.is_available:
                logger.info("Social sentiment service enabled (Reddit/X/Polymarket, US stocks only)")
        except Exception as exc:  # broad-exception: fallback_recorded - Social-sentiment initialization failure is safely logged before the optional service is disabled.
            log_safe_exception(
                logger,
                "Social sentiment service initialization failed; continuing without sentiment data",
                exc,
                error_code="pipeline_social_sentiment_service_init_failed",
                level=logging.WARNING,
            )
            self.social_sentiment_service = None
