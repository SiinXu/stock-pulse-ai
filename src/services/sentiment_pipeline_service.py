# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Deterministic sentiment scoring from already-fetched news/event evidence.

This pipeline does not call ungoverned external APIs. It only scores artifacts
already produced by SearchService intelligence search, the local intelligence
pool, or optional pre-fetched text that the analysis pipeline already owns.
Output is evidence for AnalysisContextPack, not a trading conclusion.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from src.schemas.sentiment_snapshot import (
    SENTIMENT_DISCLAIMER,
    SENTIMENT_SNAPSHOT_SCHEMA_VERSION,
    SentimentEvidenceItem,
    SentimentFreshness,
    SentimentLabel,
    SentimentReasonCode,
    SentimentSnapshot,
    SentimentSourceSummary,
)

logger = logging.getLogger(__name__)

DEFAULT_WINDOW_DAYS = 7
MAX_EVIDENCE_ITEMS = 12
_FRESH_HOURS = 36
_AGING_DAYS = 7

_BULLISH_TERMS: Tuple[Tuple[str, float], ...] = (
    ("strong buy", 1.0),
    ("upgrade", 0.85),
    ("outperform", 0.8),
    ("beat expectations", 0.85),
    ("record high", 0.75),
    ("surge", 0.7),
    ("rally", 0.65),
    ("bullish", 0.7),
    ("growth", 0.45),
    ("profit", 0.4),
    ("breakthrough", 0.55),
    ("raise guidance", 0.8),
    ("买入", 0.75),
    ("增持", 0.8),
    ("上调", 0.75),
    ("超预期", 0.85),
    ("利好", 0.7),
    ("高增", 0.65),
    ("大涨", 0.7),
    ("突破", 0.55),
    ("创新高", 0.75),
    ("扭亏", 0.6),
    ("回购", 0.55),
    ("中标", 0.5),
)

_BEARISH_TERMS: Tuple[Tuple[str, float], ...] = (
    ("strong sell", 1.0),
    ("downgrade", 0.85),
    ("underperform", 0.8),
    ("miss expectations", 0.85),
    ("profit warning", 0.9),
    ("plunge", 0.75),
    ("slump", 0.7),
    ("bearish", 0.7),
    ("lawsuit", 0.55),
    ("investigation", 0.55),
    ("fraud", 0.85),
    ("default", 0.8),
    ("sell", 0.55),
    ("卖出", 0.75),
    ("减持", 0.8),
    ("下调", 0.75),
    ("低于预期", 0.85),
    ("利空", 0.7),
    ("大跌", 0.7),
    ("暴跌", 0.8),
    ("亏损", 0.65),
    ("预亏", 0.8),
    ("立案", 0.75),
    ("调查", 0.55),
    ("处罚", 0.7),
    ("违规", 0.65),
    ("退市", 0.9),
    ("造假", 0.85),
)

_DIMENSION_WEIGHTS: Mapping[str, float] = {
    "latest_news": 1.0,
    "announcements": 1.05,
    "risk_check": 1.1,
    "earnings": 0.95,
    "market_analysis": 0.85,
    "industry": 0.7,
    "event": 1.0,
    "local_intel": 0.8,
    "social": 0.55,
    "news_text": 0.6,
}

_EVENT_DIMENSIONS = frozenset({"risk_check", "announcements", "event"})


class SentimentPipelineService:
    """Build a versioned sentiment snapshot from governed news/event inputs."""

    def __init__(
        self,
        *,
        window_days: int = DEFAULT_WINDOW_DAYS,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.window_days = max(1, min(90, int(window_days or DEFAULT_WINDOW_DAYS)))
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def build_unavailable(
        self,
        *,
        stock_code: str,
        stock_name: Optional[str] = None,
        market: Optional[str] = None,
        reason_code: SentimentReasonCode = "news_source_unavailable",
        gaps: Optional[Sequence[str]] = None,
        sources: Optional[Sequence[SentimentSourceSummary]] = None,
    ) -> SentimentSnapshot:
        as_of = self._now_iso()
        return SentimentSnapshot(
            stock_code=self._safe_text(stock_code, fallback="UNKNOWN", max_len=32),
            stock_name=self._safe_optional_text(stock_name, max_len=120),
            market=self._safe_optional_text(market, max_len=32),
            as_of=as_of,
            window_days=self.window_days,
            status="unavailable",
            degraded=True,
            reason_code=reason_code,
            score=None,
            label="unclear",
            confidence=None,
            confidence_basis=self._basis_for_reason(reason_code),
            freshness="unknown",
            sources=list(sources or []),
            evidence=[],
            gaps=list(gaps or [reason_code]),
            item_count=0,
            disclaimer=SENTIMENT_DISCLAIMER,
        )

    def build_from_intel_results(
        self,
        *,
        stock_code: str,
        stock_name: Optional[str] = None,
        market: Optional[str] = None,
        intel_results: Optional[Mapping[str, Any]] = None,
        remote_search_available: bool = True,
        local_intel_items: Optional[Sequence[Mapping[str, Any]]] = None,
        news_context: Optional[str] = None,
    ) -> SentimentSnapshot:
        """Score structured intelligence search results and optional local items."""
        try:
            return self._build_from_intel_results(
                stock_code=stock_code,
                stock_name=stock_name,
                market=market,
                intel_results=intel_results,
                remote_search_available=remote_search_available,
                local_intel_items=local_intel_items,
                news_context=news_context,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - scoring must never fail analysis
            logger.warning(
                "Sentiment pipeline scoring failed for %s: %s",
                stock_code,
                type(exc).__name__,
            )
            return self.build_unavailable(
                stock_code=stock_code,
                stock_name=stock_name,
                market=market,
                reason_code="scoring_failed",
                gaps=["scoring_failed"],
            )

    def _build_from_intel_results(
        self,
        *,
        stock_code: str,
        stock_name: Optional[str],
        market: Optional[str],
        intel_results: Optional[Mapping[str, Any]],
        remote_search_available: bool,
        local_intel_items: Optional[Sequence[Mapping[str, Any]]],
        news_context: Optional[str],
    ) -> SentimentSnapshot:
        code = self._safe_text(stock_code, fallback="UNKNOWN", max_len=32)
        stock_name = self._safe_optional_text(stock_name, max_len=120)
        market = self._safe_optional_text(market, max_len=32)
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)

        raw_items: List[Dict[str, Any]] = []
        source_rows: List[SentimentSourceSummary] = []
        gaps: List[str] = []

        remote_count = 0
        remote_providers: List[str] = []
        if intel_results:
            for dimension, response in intel_results.items():
                results = getattr(response, "results", None)
                success = bool(getattr(response, "success", False))
                provider = str(getattr(response, "provider", "") or "").strip() or None
                if provider and provider not in remote_providers:
                    remote_providers.append(provider)
                if not success:
                    gaps.append(f"dimension_failed:{dimension}")
                    continue
                if not results:
                    continue
                for item in results:
                    mapped = self._from_search_result(
                        item,
                        dimension=str(dimension),
                        provider=provider,
                    )
                    if mapped is not None:
                        raw_items.append(mapped)
                        remote_count += 1

        if remote_count > 0:
            newest_remote = self._newest_as_of(raw_items)
            source_rows.append(
                SentimentSourceSummary(
                    source_id="news_search",
                    source_type="news",
                    status="available",
                    item_count=remote_count,
                    provider=",".join(remote_providers[:4]) if remote_providers else None,
                    as_of=newest_remote,
                    as_of_status="present" if newest_remote else "missing",
                )
            )
        elif remote_search_available:
            source_rows.append(
                SentimentSourceSummary(
                    source_id="news_search",
                    source_type="news",
                    status="unavailable",
                    item_count=0,
                    as_of_status="missing",
                )
            )
            gaps.append("news_search_empty")
        else:
            source_rows.append(
                SentimentSourceSummary(
                    source_id="news_search",
                    source_type="news",
                    status="unavailable",
                    item_count=0,
                    as_of_status="missing",
                )
            )
            gaps.append("news_source_unavailable")

        local_count = 0
        for item in local_intel_items or ():
            if not isinstance(item, Mapping):
                continue
            mapped = self._from_local_intel_item(item)
            if mapped is not None:
                raw_items.append(mapped)
                local_count += 1
        if local_count > 0:
            local_as_of = self._newest_as_of(
                [item for item in raw_items if item.get("source_type") == "local_intel"]
            )
            source_rows.append(
                SentimentSourceSummary(
                    source_id="local_intel",
                    source_type="local_intel",
                    status="available",
                    item_count=local_count,
                    as_of=local_as_of,
                    as_of_status="present" if local_as_of else "missing",
                )
            )
        elif local_intel_items is not None:
            source_rows.append(
                SentimentSourceSummary(
                    source_id="local_intel",
                    source_type="local_intel",
                    status="unavailable",
                    item_count=0,
                    as_of_status="missing",
                )
            )

        text_blob = (news_context or "").strip()
        if not raw_items and text_blob:
            mapped = self._from_free_text(text_blob)
            if mapped is not None:
                raw_items.append(mapped)
                source_rows.append(
                    SentimentSourceSummary(
                        source_id="news_text_fallback",
                        source_type="news",
                        status="partial",
                        item_count=1,
                        as_of_status="missing",
                    )
                )
                gaps.append("structured_items_missing_used_text_fallback")

        if not raw_items:
            reason: SentimentReasonCode = (
                "news_source_unavailable"
                if not remote_search_available and local_count == 0
                else "no_data"
            )
            return self.build_unavailable(
                stock_code=code,
                stock_name=stock_name,
                market=market,
                reason_code=reason,
                gaps=gaps or [reason],
                sources=source_rows,
            )

        scored = [self._score_item(item, now=now) for item in raw_items]
        scored = [item for item in scored if item is not None]
        if not scored:
            return self.build_unavailable(
                stock_code=code,
                stock_name=stock_name,
                market=market,
                reason_code="low_signal",
                gaps=gaps + ["no_scorable_terms"],
                sources=source_rows,
            )

        total_weight = sum(item["weight"] for item in scored)
        if total_weight <= 0:
            return self.build_unavailable(
                stock_code=code,
                stock_name=stock_name,
                market=market,
                reason_code="low_signal",
                gaps=gaps + ["zero_weight"],
                sources=source_rows,
            )

        weighted_polarity = (
            sum(item["polarity"] * item["weight"] for item in scored) / total_weight
        )
        score = int(round(50.0 + weighted_polarity * 50.0))
        score = max(0, min(100, score))
        label = self._label_from_score(score, scored)

        dated = [item for item in scored if item.get("published_at") is not None]
        freshness_as_of = None
        if dated:
            newest = max(dated, key=lambda item: item["published_at"])
            freshness_as_of = self._iso(newest["published_at"])
        freshness = self._freshness(dated, now=now)

        abs_signal = abs(weighted_polarity)
        date_coverage = len(dated) / max(1, len(scored))
        volume_factor = min(1.0, len(scored) / 6.0)
        confidence = round(
            min(
                0.95,
                0.25
                + 0.35 * abs_signal
                + 0.2 * date_coverage
                + 0.2 * volume_factor,
            ),
            3,
        )

        reason_code: SentimentReasonCode = "ok"
        status = "available"
        degraded = False
        if freshness in {"stale", "unknown"} and date_coverage < 0.5:
            reason_code = (
                "unknown_freshness" if freshness == "unknown" else "stale_evidence"
            )
            status = "degraded"
            degraded = True
        if abs_signal < 0.08 and confidence < 0.45:
            reason_code = "low_signal"
            status = "degraded"
            degraded = True
        if gaps or any(row.status != "available" for row in source_rows):
            if reason_code == "ok":
                reason_code = "partial_coverage"
            status = "degraded"
            degraded = True

        evidence = self._select_evidence(scored, limit=MAX_EVIDENCE_ITEMS)
        confidence_basis = (
            f"items={len(scored)}; dated={len(dated)}; "
            f"abs_polarity={abs_signal:.2f}; freshness={freshness}"
        )[:240]

        return SentimentSnapshot(
            schema_version=SENTIMENT_SNAPSHOT_SCHEMA_VERSION,
            role="evidence",
            stock_code=code,
            stock_name=stock_name,
            market=market,
            as_of=self._iso(now),
            window_days=self.window_days,
            status=status,  # type: ignore[arg-type]
            degraded=degraded,
            reason_code=reason_code,
            score=score,
            label=label,
            confidence=confidence,
            confidence_basis=confidence_basis,
            freshness=freshness,
            freshness_as_of=freshness_as_of,
            sources=source_rows,
            evidence=evidence,
            gaps=list(dict.fromkeys(gaps))[:12],
            item_count=len(scored),
            method="news_lexicon_v1",
            disclaimer=SENTIMENT_DISCLAIMER,
        )

    def build_from_news_context(
        self,
        *,
        stock_code: str,
        stock_name: Optional[str] = None,
        market: Optional[str] = None,
        news_context: Optional[str] = None,
        remote_search_available: bool = True,
        news_result_count: Optional[int] = None,
    ) -> SentimentSnapshot:
        """Convenience path when only formatted news text is available."""
        if not (news_context or "").strip():
            reason: SentimentReasonCode = (
                "news_source_unavailable"
                if not remote_search_available
                else "no_data"
            )
            sources = [
                SentimentSourceSummary(
                    source_id="news_search",
                    source_type="news",
                    status="unavailable",
                    item_count=int(news_result_count or 0),
                    as_of_status="missing",
                )
            ]
            return self.build_unavailable(
                stock_code=stock_code,
                stock_name=stock_name,
                market=market,
                reason_code=reason,
                gaps=[reason],
                sources=sources,
            )
        return self.build_from_intel_results(
            stock_code=stock_code,
            stock_name=stock_name,
            market=market,
            intel_results=None,
            remote_search_available=remote_search_available,
            news_context=news_context,
        )

    @staticmethod
    def snapshot_to_context_value(snapshot: SentimentSnapshot) -> Dict[str, Any]:
        """Low-risk projection for AnalysisContextPack item values."""
        payload = snapshot.to_public_dict()
        evidence = list(payload.get("evidence") or [])[:8]
        payload["evidence"] = evidence
        return payload

    def _from_search_result(
        self,
        item: Any,
        *,
        dimension: str,
        provider: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        title = str(getattr(item, "title", "") or "").strip()
        snippet = str(getattr(item, "snippet", "") or "").strip()
        text = " ".join(part for part in (title, snippet) if part).strip()
        if len(text) < 4:
            return None
        source_label = str(getattr(item, "source", "") or "").strip() or "news"
        url = str(getattr(item, "url", "") or "").strip() or None
        published = self._parse_datetime(getattr(item, "published_date", None))
        source_type = "event" if dimension in _EVENT_DIMENSIONS else "news"
        return {
            "text": text,
            "title": title or text[:120],
            "snippet": (snippet or title)[:400],
            "source_type": source_type,
            "source_id": self._slug(source_label)[:80] or "news",
            "dimension": dimension,
            "provider": provider,
            "link": url,
            "published_at": published,
        }

    def _from_local_intel_item(self, item: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        title = str(item.get("title") or "").strip()
        summary = str(item.get("summary") or "").strip()
        text = " ".join(part for part in (title, summary) if part).strip()
        if len(text) < 4:
            return None
        source_label = str(
            item.get("source") or item.get("source_name") or "local-intel"
        ).strip()
        url = str(item.get("url") or "").strip() or None
        if url and url.startswith("no-url:intel:"):
            url = None
        published = self._parse_datetime(
            item.get("published_at") or item.get("published_date")
        )
        return {
            "text": text,
            "title": title or text[:120],
            "snippet": (summary or title)[:400],
            "source_type": "local_intel",
            "source_id": self._slug(source_label)[:80] or "local_intel",
            "dimension": "local_intel",
            "provider": "intelligence_service",
            "link": url,
            "published_at": published,
        }

    def _from_free_text(self, text: str) -> Optional[Dict[str, Any]]:
        cleaned = re.sub(r"\s+", " ", text).strip()
        if len(cleaned) < 8:
            return None
        return {
            "text": cleaned[:2000],
            "title": cleaned[:120],
            "snippet": cleaned[:400],
            "source_type": "news",
            "source_id": "news_text_fallback",
            "dimension": "news_text",
            "provider": None,
            "link": None,
            "published_at": None,
        }

    def _score_item(
        self,
        item: Mapping[str, Any],
        *,
        now: datetime,
    ) -> Optional[Dict[str, Any]]:
        text = str(item.get("text") or "")
        if not text:
            return None
        polarity, hit_count = self._lexicon_polarity(text)
        if hit_count <= 0:
            polarity = 0.0
        dimension = str(item.get("dimension") or "latest_news")
        dim_weight = float(_DIMENSION_WEIGHTS.get(dimension, 0.75))
        recency_weight = self._recency_weight(item.get("published_at"), now=now)
        signal_weight = 1.0 if hit_count > 0 else 0.15
        weight = dim_weight * recency_weight * signal_weight
        item_confidence = min(
            0.95,
            0.2 + 0.15 * min(hit_count, 4) + 0.35 * recency_weight + 0.15 * dim_weight,
        )
        return {
            **dict(item),
            "polarity": max(-1.0, min(1.0, polarity)),
            "weight": weight,
            "hit_count": hit_count,
            "confidence": round(item_confidence, 3),
        }

    def _lexicon_polarity(self, text: str) -> Tuple[float, int]:
        lowered = text.lower()
        bull = 0.0
        bear = 0.0
        hits = 0
        for term, weight in _BULLISH_TERMS:
            count = self._term_count(lowered, text, term)
            if count:
                bull += weight * count
                hits += count
        for term, weight in _BEARISH_TERMS:
            count = self._term_count(lowered, text, term)
            if count:
                bear += weight * count
                hits += count
        total = bull + bear
        if total <= 0:
            return 0.0, 0
        return (bull - bear) / total, hits

    @staticmethod
    def _term_count(lowered: str, original: str, term: str) -> int:
        if not term:
            return 0
        if re.search(r"[\u4e00-\u9fff]", term):
            return original.count(term)
        return len(re.findall(re.escape(term.lower()), lowered))

    def _recency_weight(self, published_at: Any, *, now: datetime) -> float:
        if not isinstance(published_at, datetime):
            return 0.45
        published = published_at
        if published.tzinfo is None:
            published = published.replace(tzinfo=timezone.utc)
        age = now - published
        if age <= timedelta(hours=_FRESH_HOURS):
            return 1.0
        if age <= timedelta(days=self.window_days):
            return 0.75
        if age <= timedelta(days=max(self.window_days * 2, _AGING_DAYS * 2)):
            return 0.4
        return 0.2

    def _freshness(
        self,
        dated_items: Sequence[Mapping[str, Any]],
        *,
        now: datetime,
    ) -> SentimentFreshness:
        if not dated_items:
            return "unknown"
        newest = max(
            item["published_at"]
            for item in dated_items
            if isinstance(item.get("published_at"), datetime)
        )
        if newest.tzinfo is None:
            newest = newest.replace(tzinfo=timezone.utc)
        age = now - newest
        if age <= timedelta(hours=_FRESH_HOURS):
            return "fresh"
        if age <= timedelta(days=max(self.window_days, _AGING_DAYS)):
            return "aging"
        return "stale"

    def _select_evidence(
        self,
        scored: Sequence[Mapping[str, Any]],
        *,
        limit: int,
    ) -> List[SentimentEvidenceItem]:
        ranked = sorted(
            scored,
            key=lambda item: (
                abs(float(item.get("polarity") or 0.0))
                * float(item.get("weight") or 0.0),
                float(item.get("confidence") or 0.0),
            ),
            reverse=True,
        )
        evidence: List[SentimentEvidenceItem] = []
        seen: set[str] = set()
        for item in ranked:
            snippet = str(item.get("snippet") or item.get("title") or "").strip()
            if not snippet:
                continue
            key = snippet[:120]
            if key in seen:
                continue
            seen.add(key)
            published = item.get("published_at")
            as_of = self._iso(published) if isinstance(published, datetime) else None
            evidence_id = self._evidence_id(
                source_id=str(item.get("source_id") or "news"),
                snippet=snippet,
                as_of=as_of,
            )
            evidence.append(
                SentimentEvidenceItem(
                    evidence_id=evidence_id,
                    source_type=item.get("source_type") or "news",  # type: ignore[arg-type]
                    source_id=str(item.get("source_id") or "news")[:80],
                    dimension=str(item.get("dimension") or "")[:64] or None,
                    snippet=snippet[:400],
                    as_of=as_of,
                    as_of_status="present" if as_of else "missing",
                    confidence=item.get("confidence"),
                    polarity=item.get("polarity"),
                    link=str(item["link"])[:400] if item.get("link") else None,
                    provider=str(item["provider"])[:80] if item.get("provider") else None,
                )
            )
            if len(evidence) >= limit:
                break
        return evidence

    @staticmethod
    def _label_from_score(
        score: int,
        scored: Sequence[Mapping[str, Any]],
    ) -> SentimentLabel:
        polarities = [float(item.get("polarity") or 0.0) for item in scored]
        if not polarities:
            return "unclear"
        positive = sum(1 for value in polarities if value > 0.15)
        negative = sum(1 for value in polarities if value < -0.15)
        if (
            positive
            and negative
            and min(positive, negative) / max(positive, negative) > 0.55
        ):
            return "mixed"
        if score >= 62:
            return "bullish"
        if score <= 38:
            return "bearish"
        if abs(score - 50) <= 6 and max(abs(v) for v in polarities) < 0.12:
            return "unclear"
        return "neutral"

    @staticmethod
    def _basis_for_reason(reason_code: str) -> str:
        mapping = {
            "news_source_unavailable": "news_source_unavailable",
            "no_data": "no_scorable_news_or_events",
            "scoring_failed": "scoring_pipeline_error",
            "low_signal": "weak_or_conflicting_lexicon_signal",
            "stale_evidence": "evidence_outside_freshness_window",
            "unknown_freshness": "missing_publish_timestamps",
            "partial_coverage": "partial_source_coverage",
            "ok": "news_lexicon_aggregate",
        }
        return mapping.get(reason_code, reason_code)[:240]

    @staticmethod
    def _newest_as_of(items: Iterable[Mapping[str, Any]]) -> Optional[str]:
        dated = [
            item["published_at"]
            for item in items
            if isinstance(item.get("published_at"), datetime)
        ]
        if not dated:
            return None
        newest = max(dated)
        return SentimentPipelineService._iso(newest)

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        text = str(value).strip()
        if not text:
            return None
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
                try:
                    parsed = datetime.strptime(text[:16], fmt)
                    return parsed.replace(tzinfo=timezone.utc)
                except ValueError:
                    continue
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed

    @staticmethod
    def _iso(value: datetime) -> str:
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def _now_iso(self) -> str:
        now = self._clock()
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        return self._iso(now)

    @staticmethod
    def _safe_text(value: Any, *, fallback: str = "", max_len: int = 120) -> str:
        if not isinstance(value, str):
            return fallback
        cleaned = value.strip()
        if not cleaned:
            return fallback
        return cleaned[:max_len]

    @classmethod
    def _safe_optional_text(cls, value: Any, *, max_len: int = 120) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        if not cleaned:
            return None
        return cleaned[:max_len]

    @staticmethod
    def _slug(value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9._-]+", "_", (value or "").strip().lower())
        return cleaned.strip("._-") or "source"

    @staticmethod
    def _evidence_id(*, source_id: str, snippet: str, as_of: Optional[str]) -> str:
        digest = hashlib.sha1(
            f"{source_id}|{as_of or ''}|{snippet[:160]}".encode("utf-8")
        ).hexdigest()[:16]
        return f"sent-{digest}"
