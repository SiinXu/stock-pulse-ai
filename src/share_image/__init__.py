# -*- coding: utf-8 -*-
"""Decision-first HTML posters for Markdown stock and market reports.

The notification pipeline currently owns a Markdown string, rather than the
original Pydantic/dataclass payload.  This package therefore extracts only the
stable, renderer-generated Markdown contract and turns it into a compact share
card.  Missing fields are hidden; no price, score, signal, or market statistic
is inferred.

Public import path is unchanged: ``from src.share_image import ...`` and
``from src import share_image`` continue to resolve to this package.
"""

from __future__ import annotations

from .formatting import (
    PROJECT_URL,
    PROJECT_REPOSITORY,
    PROJECT_DISPLAY_NAME,
    _MARKET_RE,
    _MARKET_SCOPE_RE,
    _DASHBOARD_RE,
    _HEADING_RE,
    _QUOTE_RE,
    _DATE_RE,
    _MARKET_REGION_REF_RE,
    _SUFFIXED_NUMERIC_CODE_PATTERN,
    _CODE_RE,
    _NUMERIC_CODE_RE,
    _NA_VALUES,
    _POSTER_TEXT,
    _POSTER_LABELS,
    _MARKET_LABEL_PATTERNS,
    _asset_path,
    _asset_data_uri,
    _plain,
    _clean_value,
    _compact_text,
    _nested_mapping,
    _poster_language,
    _poster_text,
    _poster_label,
    _metric_value,
    _merge_metrics,
    _merge_compact_list,
    _market_light_overlay_allowed,
    _normalize_index_name,
    _normalize_ranking_name,
    _merge_index_cards,
    _merge_sector_rankings,
    _number_text,
    _compact_turnover,
    _signed_percent,
    _price_tokens,
    _compact_sniper_value,
    _compact_position,
    _escape,
    _opposite_color,
    _marker_color,
    _positive_color_from_change,
    _ranking_change_tone,
    _tone_for_action,
    _tone_for_score,
    _tone_for_trend,
    _stock_positive_tone,
)

from .parsing import (
    Table,
    MarketSegment,
    _extract_sections,
    _section,
    _parse_tables,
    _table_map,
    _find_table,
    _mapped_value,
    _has_meaningful_section,
    _meaningful_market_subsection_count,
    _labeled_value,
    _labeled_line,
    _list_after_label,
    _section_items,
    _sentences,
    _extract_date,
    _market_label,
    _market_region_hint,
    _market_label_for_region,
    _stock_heading_entry,
    _stock_headings,
    _is_market_review_title,
    _has_market_scope,
    _market_segments,
)

from .model import (
    ShareImageBranding,
    StockPoster,
    MarketPoster,
    _stock_data,
    _stock_data_from_payload,
    _market_title,
    _parsed_breadth_metrics,
    _parse_index_bullets,
    _direction_items,
    _market_fund_metrics,
    _market_data,
    _market_data_from_payload,
    _should_keep_market_fallback,
)

from .render import (
    _metric_cards,
    _list_html,
    _section_html,
    _render_markdown_fragment,
    _stock_body,
    _market_body,
    _generic_body,
    _market_region_for_segment,
    _multi_market_body,
    _safe_web_url,
    _xiaohongshu_card,
    _footer,
    build_share_image_html,
)

__all__ = [
    "PROJECT_REPOSITORY",
    "PROJECT_DISPLAY_NAME",
    "PROJECT_URL",
    "ShareImageBranding",
    "build_share_image_html",
]
