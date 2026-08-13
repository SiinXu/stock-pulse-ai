# -*- coding: utf-8 -*-
"""Deterministic, explainable market-regime detection (Issue #220).

Rules only — no black-box classifiers. When inputs conflict or are missing the
service returns ``regime=unknown`` with full evidence so consumers never force a
label. Artifacts retain every evaluated rule for later audit.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Mapping, Optional, Tuple

from src.schemas.market_regime import (
    KNOWN_REGIME_LABELS,
    MARKET_REGIME_CONTEXT_KEY,
    MARKET_REGIME_SCHEMA_VERSION,
    MarketRegimeContext,
    RegimeEvidenceRule,
    RegimeLabel,
    dump_market_regime_model,
)

logger = logging.getLogger(__name__)

MARKET_REGIME_KEY = MARKET_REGIME_CONTEXT_KEY

_STRENGTH_HIGH = 70.0
_STRENGTH_LOW = 30.0
_STRENGTH_MID_LOW = 35.0
_STRENGTH_MID_HIGH = 65.0
_VOLUME_HEAVY_RATIO = 1.5

_BULL_STATUSES = frozenset({"强势多头", "多头排列", "strong_bull", "bull", "bullish"})
_BEAR_STATUSES = frozenset({"强势空头", "空头排列", "strong_bear", "bear", "bearish"})
_CONSOLIDATION_STATUSES = frozenset(
    {
        "盘整",
        "consolidation",
        "弱势多头",
        "弱势空头",
        "weak_bull",
        "weak_bear",
        "neutral",
    }
)
_HEAVY_VOLUME_STATUSES = frozenset(
    {
        "heavy",
        "放量上涨",
        "放量下跌",
        "heavy_volume_up",
        "heavy_volume_down",
    }
)
_HEAVY_UP = frozenset({"放量上涨", "heavy_volume_up"})
_HEAVY_DOWN = frozenset({"放量下跌", "heavy_volume_down"})

_FOCUS_HINTS: Dict[str, Tuple[str, ...]] = {
    "trending_up": (
        "Prioritize trend-following and pullback entries; avoid short-biased theses.",
        "Trail risk with structure; do not fade strength without clear invalidation.",
        "Weight momentum and continuation skills over pure mean-reversion.",
    ),
    "trending_down": (
        "Capital preservation first; avoid catch-the-knife long bias.",
        "Require stronger confirmation before any buy/add framing.",
        "Emphasize breakdown invalidation levels and defensive posture.",
    ),
    "sideways": (
        "Favor range boundaries and mean-reversion edges over breakout chase.",
        "Keep position size modest until a directional break is confirmed.",
        "Highlight support/resistance and time-based invalidation.",
    ),
    "volatile": (
        "Widen risk framing and reduce effective conviction/size language.",
        "Demand multi-signal confirmation; treat single-bar moves as noisy.",
        "Prefer skills tolerant of whipsaw; state uncertainty explicitly.",
    ),
    "unknown": (
        "State regime uncertainty explicitly; do not force a directional thesis.",
        "Present competing scenarios with clear invalidation conditions.",
        "Keep risk framing conservative until evidence converges.",
    ),
}

_RISK_POSTURE = {
    "trending_up": "risk_on",
    "trending_down": "risk_off",
    "sideways": "neutral",
    "volatile": "risk_off",
    "unknown": "unknown",
}


class MarketRegimeService:
    """Build an explainable market-regime context from trend / technical inputs."""

    def __init__(self, config: Any = None) -> None:
        self._config = config

    def is_enabled(self) -> bool:
        if self._config is None:
            return True
        return bool(getattr(self._config, "market_regime_enabled", True))

    def build_from_trend(
        self,
        trend_result: Any,
        *,
        stock_code: Optional[str] = None,
        market: Optional[str] = None,
        override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Detect regime from a ``TrendAnalysisResult`` (or compatible mapping)."""
        if not self.is_enabled():
            return self.build_unavailable(
                stock_code=stock_code,
                market=market,
                reason="market_regime_enabled=false",
            )
        inputs = self._inputs_from_trend(trend_result)
        return self._detect(
            inputs,
            stock_code=stock_code,
            market=market,
            override=self._resolve_override(override),
        )

    def build_from_technical_raw(
        self,
        raw_data: Optional[Mapping[str, Any]],
        *,
        stock_code: Optional[str] = None,
        market: Optional[str] = None,
        override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Detect regime from TechnicalAgent ``raw_data`` fields."""
        if not self.is_enabled():
            return self.build_unavailable(
                stock_code=stock_code,
                market=market,
                reason="market_regime_enabled=false",
            )
        inputs = self._inputs_from_technical_raw(raw_data)
        return self._detect(
            inputs,
            stock_code=stock_code,
            market=market,
            override=self._resolve_override(override),
        )

    def build_from_agent_context(
        self,
        ctx: Any,
        *,
        override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Detect from AgentContext: prefer prebuilt context, then trend, then technical opinion.

        ``unknown`` is not treated as a reusable snapshot. Skill routing runs after
        the technical stage, so a pipeline-seeded unknown artifact must not block
        redetection from ``trend_result`` or the technical opinion.
        """
        if not self.is_enabled():
            stock_code = str(getattr(ctx, "stock_code", "") or "").strip() or None
            return self.build_unavailable(
                stock_code=stock_code,
                reason="market_regime_enabled=false",
            )

        meta = getattr(ctx, "meta", None) or {}
        if isinstance(meta, Mapping):
            existing = meta.get(MARKET_REGIME_CONTEXT_KEY)
            if (
                isinstance(existing, Mapping)
                and existing.get("schema_version") == MARKET_REGIME_SCHEMA_VERSION
                and is_actionable_regime(existing.get("regime"))
            ):
                return dict(existing)

        stock_code = str(getattr(ctx, "stock_code", "") or "").strip() or None
        trend = None
        get_data = getattr(ctx, "get_data", None)
        if callable(get_data):
            trend = get_data("trend_result")
        if trend is None and isinstance(getattr(ctx, "data", None), Mapping):
            trend = ctx.data.get("trend_result")

        from_trend: Optional[Dict[str, Any]] = None
        if trend is not None:
            from_trend = self.build_from_trend(
                trend,
                stock_code=stock_code,
                override=override,
            )
            if is_actionable_regime(from_trend.get("regime")):
                return from_trend

        technical_raw = self._latest_technical_raw(ctx)
        from_technical = self.build_from_technical_raw(
            technical_raw,
            stock_code=stock_code,
            override=override,
        )
        if from_trend is None or is_actionable_regime(from_technical.get("regime")):
            return from_technical
        return from_trend

    def build_unavailable(
        self,
        *,
        stock_code: Optional[str] = None,
        market: Optional[str] = None,
        reason: str = "regime_detection_disabled_or_failed",
    ) -> Dict[str, Any]:
        """Explicit unknown artifact when detection cannot run."""
        model = MarketRegimeContext(
            regime="unknown",
            status="unknown",
            source="unavailable",
            confidence=0.0,
            risk_posture="unknown",
            rules_fired=[],
            evidence=[
                RegimeEvidenceRule(
                    rule_id="unavailable",
                    description="Regime detection did not run",
                    outcome="insufficient_data",
                    inputs={},
                    detail=reason,
                )
            ],
            focus_hints=list(_FOCUS_HINTS["unknown"]),
            missing_inputs=["trend_or_technical_inputs"],
            stock_code=stock_code,
            market=market,
        )
        return dump_market_regime_model(model)

    def _detect(
        self,
        inputs: Dict[str, Any],
        *,
        stock_code: Optional[str],
        market: Optional[str],
        override: Optional[str],
    ) -> Dict[str, Any]:
        evidence: List[RegimeEvidenceRule] = []

        if override:
            evidence.append(
                RegimeEvidenceRule(
                    rule_id="override_applied",
                    description="User/config override takes precedence over automatic rules",
                    outcome="applied",
                    inputs={"override": override},
                    detail="Configured MARKET_REGIME_OVERRIDE",
                )
            )
            model = MarketRegimeContext(
                regime=override,  # type: ignore[arg-type]
                status="ok",
                source="override",
                confidence=1.0,
                risk_posture=_RISK_POSTURE.get(override, "unknown"),  # type: ignore[arg-type]
                rules_fired=["override_applied"],
                evidence=evidence,
                focus_hints=list(_FOCUS_HINTS.get(override, _FOCUS_HINTS["unknown"])),
                missing_inputs=[],
                override=override,
                stock_code=stock_code,
                market=market,
            )
            return dump_market_regime_model(model)

        usable = bool(
            inputs.get("has_trend_status")
            or inputs.get("has_ma_alignment")
            or inputs.get("has_strength")
        )
        if not usable:
            missing = list(
                inputs.get("missing_inputs")
                or ["trend_status", "ma_alignment", "trend_strength"]
            )
            evidence.append(
                RegimeEvidenceRule(
                    rule_id="insufficient_inputs",
                    description="Require trend status, MA alignment, or strength score",
                    outcome="insufficient_data",
                    inputs={
                        "available_keys": sorted(
                            k
                            for k, v in inputs.items()
                            if v is not None and k != "missing_inputs"
                        )
                    },
                    detail="No usable technical inputs for regime rules",
                )
            )
            model = MarketRegimeContext(
                regime="unknown",
                status="unknown",
                source="rules",
                confidence=0.0,
                risk_posture="unknown",
                rules_fired=[],
                evidence=evidence,
                focus_hints=list(_FOCUS_HINTS["unknown"]),
                missing_inputs=missing,
                stock_code=stock_code,
                market=market,
            )
            return dump_market_regime_model(model)

        bull_stack, e_bull = self._eval_bool_rule(
            rule_id="ma_bull_stack",
            description="Bullish MA stack or bullish trend status",
            matched=bool(inputs.get("bull_stack")),
            rule_inputs={
                "trend_status": inputs.get("trend_status"),
                "ma_alignment": inputs.get("ma_alignment"),
            },
        )
        evidence.append(e_bull)

        bear_stack, e_bear = self._eval_bool_rule(
            rule_id="ma_bear_stack",
            description="Bearish MA stack or bearish trend status",
            matched=bool(inputs.get("bear_stack")),
            rule_inputs={
                "trend_status": inputs.get("trend_status"),
                "ma_alignment": inputs.get("ma_alignment"),
            },
        )
        evidence.append(e_bear)

        strength = inputs.get("trend_strength")
        strength_high, e_sh = self._eval_bool_rule(
            rule_id="strength_high",
            description=f"Trend strength >= {_STRENGTH_HIGH}",
            matched=strength is not None and float(strength) >= _STRENGTH_HIGH,
            rule_inputs={"trend_strength": strength, "threshold": _STRENGTH_HIGH},
            insufficient=strength is None,
        )
        evidence.append(e_sh)

        strength_low, e_sl = self._eval_bool_rule(
            rule_id="strength_low",
            description=f"Trend strength <= {_STRENGTH_LOW}",
            matched=strength is not None and float(strength) <= _STRENGTH_LOW,
            rule_inputs={"trend_strength": strength, "threshold": _STRENGTH_LOW},
            insufficient=strength is None,
        )
        evidence.append(e_sl)

        strength_mid, e_sm = self._eval_bool_rule(
            rule_id="strength_mid",
            description=f"Trend strength in [{_STRENGTH_MID_LOW}, {_STRENGTH_MID_HIGH}]",
            matched=(
                strength is not None
                and _STRENGTH_MID_LOW <= float(strength) <= _STRENGTH_MID_HIGH
            ),
            rule_inputs={
                "trend_strength": strength,
                "low": _STRENGTH_MID_LOW,
                "high": _STRENGTH_MID_HIGH,
            },
            insufficient=strength is None,
        )
        evidence.append(e_sm)

        consolidation, e_cons = self._eval_bool_rule(
            rule_id="consolidation_or_weak",
            description="Consolidation / weak / neutral structure without clear stack",
            matched=bool(inputs.get("consolidation")),
            rule_inputs={"trend_status": inputs.get("trend_status")},
        )
        evidence.append(e_cons)

        volume_heavy, e_vh = self._eval_bool_rule(
            rule_id="volume_heavy",
            description="Heavy volume relative to recent average",
            matched=bool(inputs.get("volume_heavy")),
            rule_inputs={
                "volume_status": inputs.get("volume_status"),
                "volume_ratio_5d": inputs.get("volume_ratio_5d"),
            },
            insufficient=(
                inputs.get("volume_status") is None
                and inputs.get("volume_ratio_5d") is None
            ),
        )
        evidence.append(e_vh)

        heavy_up = bool(inputs.get("volume_heavy_up"))
        heavy_down = bool(inputs.get("volume_heavy_down"))

        regime: RegimeLabel = "unknown"
        fired: List[str] = []
        confidence = 0.25
        decision_detail = "No exclusive rule set matched; leaving regime unknown"

        if bull_stack and bear_stack:
            fired = ["ma_bull_stack", "ma_bear_stack", "conflict_bull_bear"]
            evidence.append(
                RegimeEvidenceRule(
                    rule_id="conflict_bull_bear",
                    description="Bull and bear stack cannot both be true",
                    outcome="matched",
                    inputs={"bull_stack": True, "bear_stack": True},
                    detail="Conflicting MA/trend signals",
                )
            )
            decision_detail = "Conflicting bull and bear stacks"
            confidence = 0.15
        elif bull_stack and strength_low:
            fired = ["ma_bull_stack", "strength_low", "conflict_bull_weak"]
            evidence.append(
                RegimeEvidenceRule(
                    rule_id="conflict_bull_weak",
                    description="Bull stack with weak strength is not a clean up-trend",
                    outcome="matched",
                    inputs={"bull_stack": True, "trend_strength": strength},
                    detail="Directional conflict → unknown",
                )
            )
            decision_detail = "Bull structure with weak strength"
            confidence = 0.2
        elif bear_stack and strength_high:
            fired = ["ma_bear_stack", "strength_high", "conflict_bear_strong"]
            evidence.append(
                RegimeEvidenceRule(
                    rule_id="conflict_bear_strong",
                    description="Bear stack with high strength is not a clean down-trend",
                    outcome="matched",
                    inputs={"bear_stack": True, "trend_strength": strength},
                    detail="Directional conflict → unknown",
                )
            )
            decision_detail = "Bear structure with high strength"
            confidence = 0.2
        elif bull_stack and (strength_high or strength is None):
            if heavy_down:
                fired = ["ma_bull_stack", "volume_heavy_down_block"]
                evidence.append(
                    RegimeEvidenceRule(
                        rule_id="volume_heavy_down_block",
                        description="Heavy down-volume blocks clean trending_up label",
                        outcome="matched",
                        inputs={"volume_status": inputs.get("volume_status")},
                        detail="Blocked up-trend classification",
                    )
                )
                regime = "unknown"
                decision_detail = "Bull stack blocked by heavy down-volume"
                confidence = 0.3
            else:
                regime = "trending_up"
                fired = ["ma_bull_stack"]
                if strength_high:
                    fired.append("strength_high")
                confidence = 0.85 if strength_high else 0.65
                decision_detail = "Bull stack with supportive strength"
        elif bear_stack and (strength_low or strength is None):
            if heavy_up:
                fired = ["ma_bear_stack", "volume_heavy_up_block"]
                evidence.append(
                    RegimeEvidenceRule(
                        rule_id="volume_heavy_up_block",
                        description="Heavy up-volume blocks clean trending_down label",
                        outcome="matched",
                        inputs={"volume_status": inputs.get("volume_status")},
                        detail="Blocked down-trend classification",
                    )
                )
                regime = "unknown"
                decision_detail = "Bear stack blocked by heavy up-volume"
                confidence = 0.3
            else:
                regime = "trending_down"
                fired = ["ma_bear_stack"]
                if strength_low:
                    fired.append("strength_low")
                confidence = 0.85 if strength_low else 0.65
                decision_detail = "Bear stack with supportive strength"
        elif volume_heavy and strength_mid and not bull_stack and not bear_stack:
            regime = "volatile"
            fired = ["volume_heavy", "strength_mid"]
            confidence = 0.7
            decision_detail = "Heavy volume without clear directional stack"
        elif consolidation or (strength_mid and not bull_stack and not bear_stack):
            regime = "sideways"
            fired = []
            if consolidation:
                fired.append("consolidation_or_weak")
            if strength_mid:
                fired.append("strength_mid")
            if not fired:
                fired = ["sideways_default_mid"]
            confidence = 0.6 if consolidation else 0.5
            decision_detail = "Range / consolidation structure"
        else:
            evidence.append(
                RegimeEvidenceRule(
                    rule_id="no_exclusive_match",
                    description="No exclusive regime rule set matched",
                    outcome="matched",
                    inputs={
                        "bull_stack": bull_stack,
                        "bear_stack": bear_stack,
                        "strength": strength,
                        "volume_heavy": volume_heavy,
                        "consolidation": consolidation,
                    },
                    detail=decision_detail,
                )
            )

        evidence.append(
            RegimeEvidenceRule(
                rule_id="decision",
                description="Final regime assignment from matched rules",
                outcome="applied",
                inputs={"regime": regime, "rules_fired": list(fired)},
                detail=decision_detail,
            )
        )

        status = "ok" if regime != "unknown" else ("partial" if usable else "unknown")
        model = MarketRegimeContext(
            regime=regime,
            status=status,  # type: ignore[arg-type]
            source="rules",
            confidence=float(confidence),
            risk_posture=_RISK_POSTURE.get(regime, "unknown"),  # type: ignore[arg-type]
            rules_fired=list(fired),
            evidence=evidence,
            focus_hints=list(_FOCUS_HINTS.get(regime, _FOCUS_HINTS["unknown"])),
            missing_inputs=list(inputs.get("missing_inputs") or []),
            stock_code=stock_code,
            market=market,
        )
        return dump_market_regime_model(model)

    def _inputs_from_trend(self, trend_result: Any) -> Dict[str, Any]:
        if trend_result is None:
            return {"missing_inputs": ["trend_result"]}

        if isinstance(trend_result, Mapping):
            payload = dict(trend_result)
            trend_status = self._as_text(
                payload.get("trend_status") or payload.get("trendStatus")
            )
            ma_alignment = self._as_text(payload.get("ma_alignment"))
            strength = self._as_float(
                payload.get("trend_strength")
                if payload.get("trend_strength") is not None
                else payload.get("trend_score")
            )
            volume_status = self._as_text(payload.get("volume_status"))
            volume_ratio = self._as_float(payload.get("volume_ratio_5d"))
        else:
            trend_status_raw = getattr(trend_result, "trend_status", None)
            if hasattr(trend_status_raw, "value"):
                trend_status = self._as_text(trend_status_raw.value)
            else:
                trend_status = self._as_text(trend_status_raw)
            ma_alignment = self._as_text(getattr(trend_result, "ma_alignment", None))
            strength = self._as_float(getattr(trend_result, "trend_strength", None))
            volume_status_raw = getattr(trend_result, "volume_status", None)
            if hasattr(volume_status_raw, "value"):
                volume_status = self._as_text(volume_status_raw.value)
            else:
                volume_status = self._as_text(volume_status_raw)
            volume_ratio = self._as_float(getattr(trend_result, "volume_ratio_5d", None))

        return self._compose_inputs(
            trend_status=trend_status,
            ma_alignment=ma_alignment,
            strength=strength,
            volume_status=volume_status,
            volume_ratio=volume_ratio,
        )

    def _inputs_from_technical_raw(
        self,
        raw_data: Optional[Mapping[str, Any]],
    ) -> Dict[str, Any]:
        if not isinstance(raw_data, Mapping) or not raw_data:
            return {"missing_inputs": ["technical_raw_data"]}

        ma_alignment = self._as_text(raw_data.get("ma_alignment")).lower()
        strength = self._as_float(
            raw_data.get("trend_score")
            if raw_data.get("trend_score") is not None
            else raw_data.get("trend_strength")
        )
        volume_status = self._as_text(raw_data.get("volume_status")).lower()
        trend_status = ma_alignment

        return self._compose_inputs(
            trend_status=trend_status,
            ma_alignment=ma_alignment,
            strength=strength,
            volume_status=volume_status,
            volume_ratio=None,
        )

    def _compose_inputs(
        self,
        *,
        trend_status: str,
        ma_alignment: str,
        strength: Optional[float],
        volume_status: str,
        volume_ratio: Optional[float],
    ) -> Dict[str, Any]:
        status_l = (trend_status or "").strip().lower()
        align_l = (ma_alignment or "").strip().lower()
        vol_l = (volume_status or "").strip().lower()

        bull_stack = (
            status_l in {s.lower() for s in _BULL_STATUSES}
            or align_l == "bullish"
            or "多头排列" in (ma_alignment or "")
            or "强势多头" in (ma_alignment or "")
        )
        bear_stack = (
            status_l in {s.lower() for s in _BEAR_STATUSES}
            or align_l == "bearish"
            or "空头排列" in (ma_alignment or "")
            or "强势空头" in (ma_alignment or "")
        )
        consolidation = (
            status_l in {s.lower() for s in _CONSOLIDATION_STATUSES}
            or align_l == "neutral"
            or "缠绕" in (ma_alignment or "")
            or "趋势不明" in (ma_alignment or "")
        )
        if status_l in {"弱势多头", "weak_bull", "弱势空头", "weak_bear"}:
            bull_stack = False
            bear_stack = False
            consolidation = True

        volume_heavy = (
            vol_l in {s.lower() for s in _HEAVY_VOLUME_STATUSES}
            or vol_l == "heavy"
            or (volume_ratio is not None and volume_ratio >= _VOLUME_HEAVY_RATIO)
        )
        volume_heavy_up = vol_l in {s.lower() for s in _HEAVY_UP} or (
            volume_heavy and "up" in vol_l
        )
        volume_heavy_down = vol_l in {s.lower() for s in _HEAVY_DOWN} or (
            volume_heavy and "down" in vol_l
        )

        missing: List[str] = []
        if not trend_status and not ma_alignment:
            missing.append("trend_status_or_ma_alignment")
        if strength is None:
            missing.append("trend_strength")

        return {
            "trend_status": trend_status or None,
            "ma_alignment": ma_alignment or None,
            "trend_strength": strength,
            "volume_status": volume_status or None,
            "volume_ratio_5d": volume_ratio,
            "bull_stack": bull_stack,
            "bear_stack": bear_stack,
            "consolidation": consolidation,
            "volume_heavy": volume_heavy,
            "volume_heavy_up": volume_heavy_up,
            "volume_heavy_down": volume_heavy_down,
            "has_trend_status": bool(trend_status),
            "has_ma_alignment": bool(ma_alignment),
            "has_strength": strength is not None,
            "missing_inputs": missing,
        }

    def _resolve_override(self, override: Optional[str]) -> Optional[str]:
        candidate = (override or "").strip().lower()
        if not candidate and self._config is not None:
            candidate = str(
                getattr(self._config, "market_regime_override", "") or ""
            ).strip().lower()
        if not candidate:
            return None
        if candidate not in KNOWN_REGIME_LABELS:
            logger.warning(
                "Ignoring invalid MARKET_REGIME_OVERRIDE=%r; valid=%s",
                candidate,
                sorted(KNOWN_REGIME_LABELS),
            )
            return None
        return candidate

    @staticmethod
    def _latest_technical_raw(ctx: Any) -> Optional[Dict[str, Any]]:
        opinions = getattr(ctx, "opinions", None) or []
        for op in opinions:
            if getattr(op, "agent_name", None) != "technical":
                continue
            raw = getattr(op, "raw_data", None)
            if isinstance(raw, Mapping):
                return dict(raw)
        return None

    @staticmethod
    def _eval_bool_rule(
        *,
        rule_id: str,
        description: str,
        matched: bool,
        rule_inputs: Dict[str, Any],
        insufficient: bool = False,
    ) -> Tuple[bool, RegimeEvidenceRule]:
        if insufficient:
            return False, RegimeEvidenceRule(
                rule_id=rule_id,
                description=description,
                outcome="insufficient_data",
                inputs=rule_inputs,
            )
        return matched, RegimeEvidenceRule(
            rule_id=rule_id,
            description=description,
            outcome="matched" if matched else "not_matched",
            inputs=rule_inputs,
        )

    @staticmethod
    def _as_text(value: Any) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @staticmethod
    def _as_float(value: Any) -> Optional[float]:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


def extract_market_regime_context(payload: Any) -> Optional[Dict[str, Any]]:
    """Re-sanitize a stored market_regime_context mapping."""
    if not isinstance(payload, Mapping):
        return None
    nested = payload.get(MARKET_REGIME_CONTEXT_KEY)
    if isinstance(nested, Mapping):
        payload = nested
    if not isinstance(payload, Mapping):
        return None
    if payload.get("schema_version") != MARKET_REGIME_SCHEMA_VERSION:
        return None
    try:
        model = MarketRegimeContext.model_validate(payload)
    except Exception:  # broad-exception: optional_metadata - Invalid stored regime metadata is omitted instead of affecting analysis recovery.
        return None
    return dump_market_regime_model(model)


def is_actionable_regime(regime: Optional[str]) -> bool:
    """True when a regime label should drive skill routing (not unknown/empty)."""
    label = str(regime or "").strip().lower()
    return label in KNOWN_REGIME_LABELS and label != "unknown"
