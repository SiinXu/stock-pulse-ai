# -*- coding: utf-8 -*-
"""Market-overview data fetch orchestration.

Issue #1085 step 6 extracts the four ``data_manager`` fetch helpers that
``src.market.blocks`` (step 5) named as still living in
``src.market.analyzer``. LLM generation and snapshots remain on the analyzer.

This module must not import ``MarketAnalyzer``; every function receives
``owner`` and reaches ``data_manager``, ``region``, and ``_log_context``
through it, so class-level and instance-level overrides stay effective.
``overview`` is typed ``Any`` for the same reason, matching
``src.market.degradation`` and ``src.market.blocks``.
"""

from __future__ import annotations

import logging
from typing import Any, List

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger("src.market.analyzer")

# ``MarketIndex`` is defined on ``src.market.analyzer``; importing it here would
# be circular. The analyzer injects the real class after import, mirroring how
# the data_provider parts packages anchor facade-only names.
MarketIndex = None  # type: ignore[assignment,misc]

__all__ = (
    "get_main_indices",
    "get_market_statistics",
    "get_sector_rankings",
    "get_concept_rankings",
)


def get_main_indices(owner: Any) -> List[Any]:
    """获取主要指数实时行情"""
    indices = []

    try:
        logger.info("[大盘] %s action=get_main_indices status=start", owner._log_context())

        # Use DataFetcherManager to get index data (switch by region)
        data_list = owner.data_manager.get_main_indices(region=owner.region)

        if data_list:
            for item in data_list:
                index = MarketIndex(
                    code=item['code'],
                    name=item['name'],
                    current=item['current'],
                    change=item['change'],
                    change_pct=item['change_pct'],
                    open=item['open'],
                    high=item['high'],
                    low=item['low'],
                    prev_close=item['prev_close'],
                    volume=item['volume'],
                    amount=item['amount'],
                    amplitude=item['amplitude']
                )
                indices.append(index)

        if not indices:
            logger.warning("[大盘] %s action=get_main_indices status=empty", owner._log_context())
        else:
            logger.info(
                "[大盘] %s action=get_main_indices status=success count=%d",
                owner._log_context(),
                len(indices),
            )

    except Exception as e:  # broad-exception: fallback_recorded - index failure is logged before partial fallback
        log_safe_exception(
            logger,
            "Market review index fetch failed",
            e,
            error_code="market_review_index_fetch_failed",
            level=logging.ERROR,
            context={"region": owner.region},
        )

    return indices


def get_market_statistics(owner: Any, overview: Any):
    """获取市场涨跌统计"""
    try:
        logger.info("[大盘] %s action=get_market_stats status=start", owner._log_context())

        stats = owner.data_manager.get_market_stats(purpose=f"market_review:{owner.region}")

        if stats:
            overview.up_count = stats.get('up_count', 0)
            overview.down_count = stats.get('down_count', 0)
            overview.flat_count = stats.get('flat_count', 0)
            overview.limit_up_count = stats.get('limit_up_count', 0)
            overview.limit_down_count = stats.get('limit_down_count', 0)
            overview.total_amount = stats.get('total_amount', 0.0)

            logger.info(
                "[大盘] %s action=get_market_stats status=success up=%s down=%s flat=%s "
                "limit_up=%s limit_down=%s amount=%.0f亿",
                owner._log_context(),
                overview.up_count,
                overview.down_count,
                overview.flat_count,
                overview.limit_up_count,
                overview.limit_down_count,
                overview.total_amount,
            )
        else:
            logger.warning("[大盘] %s action=get_market_stats status=empty", owner._log_context())

    except Exception as e:  # broad-exception: fallback_recorded - statistics failure is logged before fallback
        log_safe_exception(
            logger,
            "Market review statistics fetch failed",
            e,
            error_code="market_review_statistics_fetch_failed",
            level=logging.ERROR,
            context={"region": owner.region},
        )


def get_sector_rankings(owner: Any, overview: Any):
    """获取板块涨跌榜"""
    try:
        logger.info("[大盘] %s action=get_sector_rankings status=start", owner._log_context())

        top_sectors, bottom_sectors = owner.data_manager.get_sector_rankings(5)

        if top_sectors or bottom_sectors:
            overview.top_sectors = top_sectors
            overview.bottom_sectors = bottom_sectors

            logger.info(
                "[大盘] %s action=get_sector_rankings status=success top=%s bottom=%s",
                owner._log_context(),
                [s['name'] for s in overview.top_sectors],
                [s['name'] for s in overview.bottom_sectors],
            )
        else:
            logger.warning("[大盘] %s action=get_sector_rankings status=empty", owner._log_context())

    except Exception as e:  # broad-exception: fallback_recorded - sector failure is logged before fallback
        log_safe_exception(
            logger,
            "Market review sector ranking fetch failed",
            e,
            error_code="market_review_sector_ranking_fetch_failed",
            level=logging.ERROR,
            context={"region": owner.region},
        )


def get_concept_rankings(owner: Any, overview: Any):
    """获取概念/题材涨跌榜（fail-open）。"""
    try:
        logger.info("[大盘] %s action=get_concept_rankings status=start", owner._log_context())

        top_concepts, bottom_concepts = owner.data_manager.get_concept_rankings(5)

        if top_concepts or bottom_concepts:
            overview.top_concepts = top_concepts
            overview.bottom_concepts = bottom_concepts

            logger.info(
                "[大盘] %s action=get_concept_rankings status=success top=%s bottom=%s",
                owner._log_context(),
                [s.get('name') for s in overview.top_concepts],
                [s.get('name') for s in overview.bottom_concepts],
            )
        else:
            logger.warning("[大盘] %s action=get_concept_rankings status=empty", owner._log_context())

    except Exception as e:  # broad-exception: fallback_recorded - concept failure is logged before fallback
        log_safe_exception(
            logger,
            "Market review concept ranking fetch failed",
            e,
            error_code="market_review_concept_ranking_fetch_failed",
            level=logging.WARNING,
            context={"region": owner.region},
        )
