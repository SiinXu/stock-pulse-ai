# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Map structured decision / dashboard fields to PredictionRecord drafts (Issue #1108).

A2 under Epic #1107. Depends on the A1 PredictionRecord contract
(``src.schemas.prediction_record``) and the A6 ``resolve_after`` helper.

Product rules:
- Only **typed structured fields** become claims. Prose (analysis_summary,
  short_term_outlook, free-form operation_advice text, trend_prediction copy,
  markdown) is never regex-parsed into a verifiable claim.
- Missing required structure → ``status=no_verifiable_claim`` with an explicit
  reason, never invented direction/default claims.
- Extraction failures are recorded and never fail the user-visible analysis.
- Feature-flagged via ``PREDICTION_EXTRACT_ENABLED`` (default off).
"""

from __future__ import annotations

import logging
import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from src.schemas.prediction_record import (
    PREDICTION_HORIZON_TOKENS,
    DirectionPayload,
    LevelBreakPayload,
    NoVerifiableReason,
    PredictionClaim,
    PredictionHorizon,
    PredictionModelMeta,
    PredictionRecord,
    ReturnBucketPayload,
    VolRegimePayload,
    build_no_verifiable_claim_record,
    validate_prediction_record,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

PREDICTION_EXTRACTOR_VERSION = "prediction-extractor-v1"
DEFAULT_DECISION_HORIZON: PredictionHorizon = "5d"

# Strict enum maps only — no phrase / prose matching.
_DECISION_TYPE_DIRECTION = {
    "buy": "up",
    "hold": "sideways",
    "sell": "down",
}
_ACTION_DIRECTION = {
    "buy": "up",
    "add": "up",
    "hold": "sideways",
    "watch": "sideways",
    "reduce": "down",
    "sell": "down",
    # avoid / alert are not clear price-direction forecasts
}

_CONFIDENCE_LEVEL_MAP = {
    "高": 0.8,
    "high": 0.8,
    "中": 0.6,
    "medium": 0.6,
    "mid": 0.6,
    "低": 0.4,
    "low": 0.4,
}

# Free-text surfaces that must never be parsed into claims.
_PROSE_FIELD_NAMES = frozenset(
    {
        "analysis_summary",
        "short_term_outlook",
        "medium_term_outlook",
        "trend_prediction",
        "operation_advice",
        "buy_reason",
        "key_points",
        "risk_warning",
        "trend_analysis",
        "technical_analysis",
        "news_summary",
        "market_sentiment",
        "fundamental_analysis",
        "one_sentence",
        "reasoning",
        "final_response_text",
        "raw_response",
    }
)

ExtractionSource = Union[Mapping[str, Any], Any]


@dataclass(frozen=True)
class PredictionExtractionResult:
    """Outcome of one extraction attempt (never raises to analysis callers)."""

    record: Optional[PredictionRecord]
    verifiable: bool
    reason: Optional[str] = None
    error: Optional[str] = None
    extractor_version: str = PREDICTION_EXTRACTOR_VERSION

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "verifiable": self.verifiable,
            "extractor_version": self.extractor_version,
        }
        if self.record is not None:
            payload["record"] = self.record.to_persistence_dict()
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.error is not None:
            payload["error"] = self.error
        return payload


def is_prediction_extract_enabled(config: Any = None) -> bool:
    """Return whether config-gated prediction extraction is on (default off)."""
    if config is None:
        try:
            from src.config import Config

            config = Config.get_instance()
        except Exception:  # broad-exception: optional_metadata - config unavailable; treat extract gate as off
            return False
    return bool(getattr(config, "prediction_extract_enabled", False))


def extract_prediction_record(
    source: ExtractionSource,
    *,
    run_id: Optional[str] = None,
    created_at: Optional[datetime] = None,
    as_of: Optional[date] = None,
    mode: Optional[str] = None,
    soul_version: Optional[str] = None,
    skill_ids: Optional[Sequence[str]] = None,
    model_id: Optional[str] = None,
    model_version: Optional[str] = None,
    source_decision_id: Optional[str] = None,
    prediction_id: Optional[str] = None,
    default_horizon: PredictionHorizon = DEFAULT_DECISION_HORIZON,
) -> PredictionExtractionResult:
    """Extract a PredictionRecord draft from structured decision fields only.

    Never parses marketing prose into claims. Callers should treat this as pure
    and side-effect free; persistence is owned by later issues.
    """
    try:
        return _extract_prediction_record_impl(
            source,
            run_id=run_id,
            created_at=created_at,
            as_of=as_of,
            mode=mode,
            soul_version=soul_version,
            skill_ids=skill_ids,
            model_id=model_id,
            model_version=model_version,
            source_decision_id=source_decision_id,
            prediction_id=prediction_id,
            default_horizon=default_horizon,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - never fail analysis
        log_safe_exception(
            logger,
            "Prediction extraction failed",
            exc,
            error_code="prediction_extraction_failed",
            level=logging.WARNING,
        )
        return PredictionExtractionResult(
            record=None,
            verifiable=False,
            reason="extraction_exception",
            error=str(exc) or exc.__class__.__name__,
        )


def maybe_extract_prediction_on_finalize(
    source: ExtractionSource,
    *,
    config: Any = None,
    run_id: Optional[str] = None,
    created_at: Optional[datetime] = None,
    as_of: Optional[date] = None,
    mode: Optional[str] = None,
    soul_version: Optional[str] = None,
    skill_ids: Optional[Sequence[str]] = None,
    model_id: Optional[str] = None,
    model_version: Optional[str] = None,
    source_decision_id: Optional[str] = None,
) -> Optional[PredictionExtractionResult]:
    """Feature-flagged finalize hook; returns None when disabled.

    Failures are swallowed into a non-verifiable result and never raised.
    """
    if not is_prediction_extract_enabled(config):
        return None
    return extract_prediction_record(
        source,
        run_id=run_id,
        created_at=created_at,
        as_of=as_of,
        mode=mode,
        soul_version=soul_version,
        skill_ids=skill_ids,
        model_id=model_id,
        model_version=model_version,
        source_decision_id=source_decision_id,
    )


def _extract_prediction_record_impl(
    source: ExtractionSource,
    *,
    run_id: Optional[str],
    created_at: Optional[datetime],
    as_of: Optional[date],
    mode: Optional[str],
    soul_version: Optional[str],
    skill_ids: Optional[Sequence[str]],
    model_id: Optional[str],
    model_version: Optional[str],
    source_decision_id: Optional[str],
    prediction_id: Optional[str],
    default_horizon: PredictionHorizon,
) -> PredictionExtractionResult:
    payload = _coerce_source_mapping(source)
    if not payload:
        return _unverifiable(
            reason="empty_decision",
            run_id=run_id,
            created_at=created_at,
            as_of=as_of,
            mode=mode,
            soul_version=soul_version,
            skill_ids=skill_ids,
            model_id=model_id,
            model_version=model_version,
            source_decision_id=source_decision_id,
            prediction_id=prediction_id,
            symbol="UNKNOWN",
            market=None,
            default_horizon=default_horizon,
        )

    symbol = _extract_symbol(payload, source)
    market = _extract_market(payload, symbol)
    created = _normalize_created_at(created_at)
    as_of_date = as_of or created.date()
    run = _clean_id(run_id) or _clean_id(payload.get("run_id")) or _clean_id(
        payload.get("query_id")
    ) or f"run-{uuid.uuid4().hex[:16]}"
    pred_id = _clean_id(prediction_id) or f"pred-{uuid.uuid4().hex}"
    decision_id = _clean_id(source_decision_id) or _clean_id(
        payload.get("source_decision_id")
    ) or _clean_id(payload.get("decision_id"))

    model_meta = _build_model_meta(
        payload,
        mode=mode,
        soul_version=soul_version,
        skill_ids=skill_ids,
        model_id=model_id,
        model_version=model_version,
    )

    if not symbol:
        record = build_no_verifiable_claim_record(
            prediction_id=pred_id,
            run_id=run,
            symbol="UNKNOWN",
            created_at=created,
            as_of=as_of_date,
            horizon=default_horizon,
            resolve_after=created,
            reason="missing_structured_fields",
            market=market,
            source_decision_id=decision_id,
            model_meta=model_meta,
            notes="missing_symbol",
        )
        return PredictionExtractionResult(
            record=record,
            verifiable=False,
            reason="missing_structured_fields",
        )

    horizon = _extract_horizon(payload, default=default_horizon)
    claims, claim_errors = _extract_claims(payload)

    if not claims:
        reason = _no_claim_reason(payload, claim_errors)
        resolve_after, resolve_meta, resolve_error = _compute_resolve_after(
            market=market,
            created_at=created,
            horizon=horizon,
            stock_code=symbol,
        )
        notes_parts = []
        if claim_errors:
            notes_parts.append("claim_errors=" + ";".join(claim_errors[:8]))
        if resolve_error:
            notes_parts.append(f"resolve_after={resolve_error}")
        if resolve_meta:
            notes_parts.append("resolve_meta_present")
        record = build_no_verifiable_claim_record(
            prediction_id=pred_id,
            run_id=run,
            symbol=symbol,
            created_at=created,
            as_of=as_of_date,
            horizon=horizon,
            resolve_after=resolve_after or created,
            reason=reason,
            market=market,
            source_decision_id=decision_id,
            model_meta=model_meta,
            notes="; ".join(notes_parts) if notes_parts else None,
        )
        return PredictionExtractionResult(
            record=record,
            verifiable=False,
            reason=reason,
            error="; ".join(claim_errors) if claim_errors else None,
        )

    resolve_after, resolve_meta, resolve_error = _compute_resolve_after(
        market=market,
        created_at=created,
        horizon=horizon,
        stock_code=symbol,
    )

    status = "pending"
    notes: Optional[str] = None
    if resolve_after is None:
        # Keep typed claims but do not invent a due time (A6 fail-closed).
        status = "error"
        resolve_after = created
        notes = f"resolve_after_unavailable:{resolve_error or 'unknown'}"

    if resolve_meta:
        # Attach calendar provenance under model_meta via config_version notes path
        # without inventing new schema fields (A1 forbids extra keys on the record).
        existing_notes = notes
        cal_note = f"resolve_calendar_approx={bool(resolve_meta.get('calendar_approx'))}"
        notes = f"{existing_notes}; {cal_note}" if existing_notes else cal_note

    record = validate_prediction_record(
        {
            "prediction_id": pred_id,
            "run_id": run,
            "symbol": symbol,
            "market": market,
            "created_at": created,
            "as_of": as_of_date,
            "horizon": horizon,
            "resolve_after": resolve_after,
            "claims": [c.model_dump(mode="python") for c in claims],
            "status": status,
            "source_decision_id": decision_id,
            "model_meta": model_meta.model_dump(mode="python"),
            "notes": notes,
        }
    )
    ready = record.is_verifiable() and record.status == "pending"
    return PredictionExtractionResult(
        record=record,
        verifiable=ready,
        reason=None if ready else "resolve_after_unavailable",
        error=resolve_error,
    )


def _unverifiable(
    *,
    reason: NoVerifiableReason,
    run_id: Optional[str],
    created_at: Optional[datetime],
    as_of: Optional[date],
    mode: Optional[str],
    soul_version: Optional[str],
    skill_ids: Optional[Sequence[str]],
    model_id: Optional[str],
    model_version: Optional[str],
    source_decision_id: Optional[str],
    prediction_id: Optional[str],
    symbol: str,
    market: Optional[str],
    default_horizon: PredictionHorizon,
) -> PredictionExtractionResult:
    created = _normalize_created_at(created_at)
    record = build_no_verifiable_claim_record(
        prediction_id=_clean_id(prediction_id) or f"pred-{uuid.uuid4().hex}",
        run_id=_clean_id(run_id) or f"run-{uuid.uuid4().hex[:16]}",
        symbol=symbol,
        created_at=created,
        as_of=as_of or created.date(),
        horizon=default_horizon,
        resolve_after=created,
        reason=reason,
        market=market,
        source_decision_id=_clean_id(source_decision_id),
        model_meta=_build_model_meta(
            {},
            mode=mode,
            soul_version=soul_version,
            skill_ids=skill_ids,
            model_id=model_id,
            model_version=model_version,
        ),
    )
    return PredictionExtractionResult(
        record=record,
        verifiable=False,
        reason=reason,
    )


def _coerce_source_mapping(source: ExtractionSource) -> Dict[str, Any]:
    if source is None:
        return {}
    if isinstance(source, Mapping):
        return dict(source)

    # Duck-typed AnalysisResult / similar objects.
    out: Dict[str, Any] = {}
    for key in (
        "code",
        "stock_code",
        "symbol",
        "name",
        "stock_name",
        "market",
        "decision_type",
        "action",
        "confidence_level",
        "confidence",
        "sentiment_score",
        "trend_prediction",
        "operation_advice",
        "analysis_summary",
        "short_term_outlook",
        "medium_term_outlook",
        "buy_reason",
        "key_points",
        "risk_warning",
        "dashboard",
        "query_id",
        "run_id",
        "model_used",
        "prediction_claims",
        "claims",
        "forecast",
        "horizon",
        "return_bucket",
        "level_break",
        "vol_regime",
        "soul_version",
        "skill_ids",
        "mode",
        "source_decision_id",
        "decision_id",
        "raw_response",
    ):
        if hasattr(source, key):
            value = getattr(source, key)
            if value is not None:
                out[key] = value
    # Prefer to_dict when present for nested dashboard fidelity.
    to_dict = getattr(source, "to_dict", None)
    if callable(to_dict):
        try:
            dumped = to_dict()
            if isinstance(dumped, Mapping):
                for key, value in dumped.items():
                    out.setdefault(key, value)
        except Exception:  # broad-exception: optional_metadata - to_dict optional for duck-typed sources
            pass
    return out


def _normalize_symbol_token(raw: Any) -> Optional[str]:
    """Return a whitespace-free symbol token without importing data_provider."""
    text = str(raw or "").strip()
    if not text or any(ch.isspace() for ch in text):
        return None
    # Prefer provider normalizer when available; never hard-fail extraction.
    try:
        from data_provider.base import normalize_stock_code

        normalized = normalize_stock_code(text)
        if normalized:
            return str(normalized).strip().upper()
    except Exception:  # broad-exception: optional_metadata - symbol normalizer optional
        pass
    return text.upper()


def _extract_symbol(payload: Mapping[str, Any], source: ExtractionSource) -> Optional[str]:
    for key in ("symbol", "stock_code", "code"):
        token = _normalize_symbol_token(payload.get(key))
        if token:
            return token
    if not isinstance(source, Mapping) and hasattr(source, "code"):
        return _normalize_symbol_token(getattr(source, "code"))
    return None


def _extract_market(payload: Mapping[str, Any], symbol: Optional[str]) -> Optional[str]:
    raw = payload.get("market")
    if isinstance(raw, str) and raw.strip():
        return raw.strip().lower()
    if not symbol:
        return None
    # Lightweight inference first so extraction stays import-light for pure unit tests.
    inferred = _infer_market_from_symbol(symbol)
    if inferred:
        return inferred
    try:
        from src.core.trading_calendar import get_market_for_stock

        market = get_market_for_stock(symbol)
        if market and market != "crypto":
            return market
    except Exception:  # broad-exception: optional_metadata - market calendar optional for draft
        return None
    return None


def _infer_market_from_symbol(symbol: str) -> Optional[str]:
    """Best-effort market tag without importing data_provider."""
    text = str(symbol or "").strip().upper()
    if not text:
        return None
    if text.endswith(".HK") or text.startswith("HK"):
        return "hk"
    if text.endswith((".SS", ".SZ", ".SH")):
        return "cn"
    if text.isdigit() and len(text) == 6:
        return "cn"
    if text.isdigit() and len(text) in {4, 5}:
        # Common HK numeric form without prefix; ambiguous but used in agent payloads.
        return "hk"
    if text.isalpha() and 1 <= len(text) <= 5:
        return "us"
    return None


def _normalize_created_at(value: Optional[datetime]) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.now(timezone.utc)


def _clean_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or any(ch.isspace() for ch in text):
        return None
    if len(text) > 128:
        return text[:128]
    return text


def _build_model_meta(
    payload: Mapping[str, Any],
    *,
    mode: Optional[str],
    soul_version: Optional[str],
    skill_ids: Optional[Sequence[str]],
    model_id: Optional[str],
    model_version: Optional[str],
) -> PredictionModelMeta:
    nested = payload.get("model_meta")
    nested_map = dict(nested) if isinstance(nested, Mapping) else {}

    mode_val = _optional_str(mode) or _optional_str(payload.get("mode")) or _optional_str(
        nested_map.get("mode")
    )
    soul = (
        _optional_str(soul_version)
        or _optional_str(payload.get("soul_version"))
        or _optional_str(nested_map.get("soul_version"))
    )
    model = (
        _optional_str(model_id)
        or _optional_str(payload.get("model_used"))
        or _optional_str(payload.get("model_id"))
        or _optional_str(nested_map.get("model_id"))
    )
    mver = (
        _optional_str(model_version)
        or _optional_str(payload.get("model_version"))
        or _optional_str(nested_map.get("model_version"))
    )
    skills = _normalize_skill_ids(
        skill_ids
        if skill_ids is not None
        else payload.get("skill_ids")
        if payload.get("skill_ids") is not None
        else nested_map.get("skill_ids")
    )
    data: Dict[str, Any] = {}
    if mode_val:
        data["mode"] = mode_val
    if soul:
        data["soul_version"] = soul
    if skills:
        data["skill_ids"] = skills
    if model:
        data["model_id"] = model
    if mver:
        data["model_version"] = mver
    data["config_version"] = PREDICTION_EXTRACTOR_VERSION
    return PredictionModelMeta.model_validate(data)


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_skill_ids(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        items = list(value)
    else:
        return []
    cleaned: List[str] = []
    for item in items:
        token = str(item or "").strip()
        if not token or len(token) > 128:
            continue
        if token not in cleaned:
            cleaned.append(token)
        if len(cleaned) >= 64:
            break
    return cleaned


def _extract_horizon(
    payload: Mapping[str, Any],
    *,
    default: PredictionHorizon,
) -> PredictionHorizon:
    for candidate in (
        payload.get("horizon"),
        (payload.get("forecast") or {}).get("horizon")
        if isinstance(payload.get("forecast"), Mapping)
        else None,
        (payload.get("dashboard") or {}).get("horizon")
        if isinstance(payload.get("dashboard"), Mapping)
        else None,
    ):
        if candidate is None:
            continue
        text = str(candidate).strip().lower()
        if text in PREDICTION_HORIZON_TOKENS:
            return text  # type: ignore[return-value]
    return default


def _extract_claims(
    payload: Mapping[str, Any],
) -> tuple[List[PredictionClaim], List[str]]:
    """Build claims strictly from structured fields; collect skip reasons."""
    claims: List[PredictionClaim] = []
    errors: List[str] = []
    seen_ids: set[str] = set()

    # 1) Explicit structured claim lists (preferred when agents emit them).
    for raw_list, origin in (
        (payload.get("prediction_claims"), "prediction_claims"),
        (payload.get("claims"), "claims"),
        (
            (payload.get("forecast") or {}).get("claims")
            if isinstance(payload.get("forecast"), Mapping)
            else None,
            "forecast.claims",
        ),
        (
            (payload.get("dashboard") or {}).get("prediction_claims")
            if isinstance(payload.get("dashboard"), Mapping)
            else None,
            "dashboard.prediction_claims",
        ),
    ):
        if not isinstance(raw_list, list):
            continue
        for index, item in enumerate(raw_list):
            claim, err = _validate_explicit_claim(item, origin=origin, index=index)
            if claim is None:
                if err:
                    errors.append(err)
                continue
            if claim.claim_id in seen_ids:
                errors.append(f"{origin}[{index}]:duplicate_claim_id")
                continue
            seen_ids.add(claim.claim_id)
            claims.append(claim)

    confidence = _extract_confidence(payload)

    # 2) Direction from strict enums only (never from operation_advice prose).
    if not any(c.type == "direction" for c in claims):
        direction = _extract_direction_from_enums(payload)
        if direction is not None:
            claim_id = "direction-0"
            if claim_id not in seen_ids:
                claims.append(
                    PredictionClaim.model_validate(
                        {
                            "claim_id": claim_id,
                            "type": "direction",
                            "confidence": confidence,
                            "payload": DirectionPayload(direction=direction),
                        }
                    )
                )
                seen_ids.add(claim_id)

    # 3) Explicit structured return_bucket / level_break / vol_regime objects.
    for field_name, builder in (
        ("return_bucket", _claim_from_return_bucket),
        ("level_break", _claim_from_level_break),
        ("vol_regime", _claim_from_vol_regime),
    ):
        raw = payload.get(field_name)
        if raw is None and isinstance(payload.get("dashboard"), Mapping):
            raw = payload["dashboard"].get(field_name)
        if raw is None and isinstance(payload.get("forecast"), Mapping):
            raw = payload["forecast"].get(field_name)
        if raw is None:
            continue
        claim, err = builder(raw, confidence=confidence, claim_id=f"{field_name}-0")
        if claim is None:
            if err:
                errors.append(err)
            continue
        if claim.claim_id in seen_ids:
            continue
        # Skip if same type already present from explicit list
        if any(c.type == claim.type for c in claims):
            continue
        seen_ids.add(claim.claim_id)
        claims.append(claim)

    return claims, errors


def _validate_explicit_claim(
    item: Any,
    *,
    origin: str,
    index: int,
) -> tuple[Optional[PredictionClaim], Optional[str]]:
    if not isinstance(item, Mapping):
        return None, f"{origin}[{index}]:not_object"
    try:
        data = dict(item)
        if "claim_id" not in data or not str(data.get("claim_id") or "").strip():
            data["claim_id"] = f"{origin.replace('.', '-')}-{index}"
        claim = PredictionClaim.model_validate(data)
        return claim, None
    except Exception as exc:  # broad-exception: optional_metadata - invalid claim objects are skipped with reason
        return None, f"{origin}[{index}]:{exc}"


def _extract_direction_from_enums(payload: Mapping[str, Any]) -> Optional[str]:
    """Map only exact structured enums; never parse free-text advice."""
    action_raw = payload.get("action")
    if action_raw is None and isinstance(payload.get("dashboard"), Mapping):
        action_raw = payload["dashboard"].get("action")
    action_key = _strict_token(action_raw)
    if action_key in _ACTION_DIRECTION:
        return _ACTION_DIRECTION[action_key]

    decision_raw = payload.get("decision_type")
    if decision_raw is None and isinstance(payload.get("dashboard"), Mapping):
        decision_raw = payload["dashboard"].get("decision_type")
    decision_key = _strict_token(decision_raw)
    if decision_key in _DECISION_TYPE_DIRECTION:
        return _DECISION_TYPE_DIRECTION[decision_key]

    return None


def _strict_token(value: Any) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, str):
        # Reject numeric / object inputs — they are not decision enums.
        if hasattr(value, "value") and isinstance(getattr(value, "value"), str):
            text = str(value.value).strip().lower()
        else:
            return None
    else:
        text = value.strip().lower()
    if not text or any(ch.isspace() for ch in text):
        # Multi-word free text is not a structured enum.
        return None
    # Reject values that look like sentences / Chinese prose phrases.
    if len(text) > 32:
        return None
    return text


def _extract_confidence(payload: Mapping[str, Any]) -> float:
    for key in ("confidence", "confidence_level"):
        raw = payload.get(key)
        if raw is None and isinstance(payload.get("dashboard"), Mapping):
            raw = payload["dashboard"].get(key)
        conf = _coerce_confidence(raw)
        if conf is not None:
            return conf
    return 0.5


def _coerce_confidence(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return None
        if 0.0 <= number <= 1.0:
            return number
        if 0.0 <= number <= 100.0:
            return max(0.0, min(1.0, number / 100.0))
        return None
    if isinstance(value, str):
        key = value.strip().lower()
        if key in _CONFIDENCE_LEVEL_MAP:
            return _CONFIDENCE_LEVEL_MAP[key]
        # Also try original for Chinese keys stored as-is
        if value.strip() in _CONFIDENCE_LEVEL_MAP:
            return _CONFIDENCE_LEVEL_MAP[value.strip()]
        try:
            return _coerce_confidence(float(value.strip()))
        except ValueError:
            return None
    return None


def _claim_from_return_bucket(
    raw: Any,
    *,
    confidence: float,
    claim_id: str,
) -> tuple[Optional[PredictionClaim], Optional[str]]:
    if not isinstance(raw, Mapping):
        return None, "return_bucket:not_object"
    try:
        payload = ReturnBucketPayload.model_validate(raw)
        claim = PredictionClaim.model_validate(
            {
                "claim_id": claim_id,
                "type": "return_bucket",
                "confidence": confidence,
                "payload": payload,
            }
        )
        return claim, None
    except Exception as exc:  # broad-exception: optional_metadata - invalid return_bucket skipped with reason
        return None, f"return_bucket:{exc}"


def _claim_from_level_break(
    raw: Any,
    *,
    confidence: float,
    claim_id: str,
) -> tuple[Optional[PredictionClaim], Optional[str]]:
    if not isinstance(raw, Mapping):
        return None, "level_break:not_object"
    try:
        payload = LevelBreakPayload.model_validate(raw)
        claim = PredictionClaim.model_validate(
            {
                "claim_id": claim_id,
                "type": "level_break",
                "confidence": confidence,
                "payload": payload,
            }
        )
        return claim, None
    except Exception as exc:  # broad-exception: optional_metadata - invalid level_break skipped with reason
        return None, f"level_break:{exc}"


def _claim_from_vol_regime(
    raw: Any,
    *,
    confidence: float,
    claim_id: str,
) -> tuple[Optional[PredictionClaim], Optional[str]]:
    if isinstance(raw, str):
        raw = {"regime": raw}
    if not isinstance(raw, Mapping):
        return None, "vol_regime:not_object"
    try:
        payload = VolRegimePayload.model_validate(raw)
        claim = PredictionClaim.model_validate(
            {
                "claim_id": claim_id,
                "type": "vol_regime",
                "confidence": confidence,
                "payload": payload,
            }
        )
        return claim, None
    except Exception as exc:  # broad-exception: optional_metadata - invalid vol_regime skipped with reason
        return None, f"vol_regime:{exc}"


def _no_claim_reason(
    payload: Mapping[str, Any],
    claim_errors: Sequence[str],
) -> NoVerifiableReason:
    if _has_prose_content(payload) and not _has_structured_signal_fields(payload):
        return "prose_only"
    if claim_errors and _has_structured_signal_fields(payload):
        return "unparseable_output"
    if _has_structured_signal_fields(payload):
        return "missing_structured_fields"
    if not payload:
        return "empty_decision"
    if _has_prose_content(payload):
        return "prose_only"
    return "missing_structured_fields"


def _has_prose_content(payload: Mapping[str, Any]) -> bool:
    for key in _PROSE_FIELD_NAMES:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return True
    dashboard = payload.get("dashboard")
    if isinstance(dashboard, Mapping):
        core = dashboard.get("core_conclusion")
        if isinstance(core, Mapping):
            one = core.get("one_sentence")
            if isinstance(one, str) and one.strip():
                return True
    return False


def _has_structured_signal_fields(payload: Mapping[str, Any]) -> bool:
    if _strict_token(payload.get("decision_type")) in _DECISION_TYPE_DIRECTION:
        return True
    if _strict_token(payload.get("action")) in _ACTION_DIRECTION:
        return True
    for key in ("prediction_claims", "claims", "return_bucket", "level_break", "vol_regime"):
        if payload.get(key) not in (None, "", [], {}):
            return True
    forecast = payload.get("forecast")
    if isinstance(forecast, Mapping) and forecast:
        return True
    dashboard = payload.get("dashboard")
    if isinstance(dashboard, Mapping):
        if _strict_token(dashboard.get("decision_type")) in _DECISION_TYPE_DIRECTION:
            return True
        if _strict_token(dashboard.get("action")) in _ACTION_DIRECTION:
            return True
        if dashboard.get("prediction_claims") not in (None, "", [], {}):
            return True
    return False


def _compute_resolve_after(
    *,
    market: Optional[str],
    created_at: datetime,
    horizon: PredictionHorizon,
    stock_code: Optional[str],
) -> tuple[Optional[datetime], Optional[Dict[str, Any]], Optional[str]]:
    """Compute resolve_after via A6 helper; fail closed without fabricating."""
    if not market:
        return None, None, "market_required"

    try:
        from src.core.prediction_resolve_after import (
            ResolveAfterError,
            compute_resolve_after,
        )
    except Exception as exc:  # broad-exception: optional_metadata - resolve_after helper may be absent until A6 merges
        return None, None, f"resolve_after_module_unavailable:{exc.__class__.__name__}"

    try:
        result = compute_resolve_after(
            market,
            created_at,
            horizon,
            stock_code=stock_code,
        )
        return result.resolve_after, result.to_dict(), None
    except ResolveAfterError as exc:
        return None, getattr(exc, "meta", None), f"{exc.error_code}:{exc}"
    except Exception as exc:  # broad-exception: fallback_recorded - calendar resolve failures fail closed without fabricating due times
        log_safe_exception(
            logger,
            "Prediction resolve_after computation failed",
            exc,
            error_code="prediction_extract_resolve_after_failed",
            level=logging.WARNING,
            context={"market": market, "horizon": horizon},
        )
        return None, None, f"resolve_after_exception:{exc.__class__.__name__}"


__all__ = [
    "DEFAULT_DECISION_HORIZON",
    "PREDICTION_EXTRACTOR_VERSION",
    "PredictionExtractionResult",
    "extract_prediction_record",
    "is_prediction_extract_enabled",
    "maybe_extract_prediction_on_finalize",
]
