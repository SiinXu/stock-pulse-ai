# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Strict PredictionRecord contract for agent forecast verification (Issue #1101).

This module is **A1 only**: types and validation for structured, machine-checkable
forecast claims. It does not extract claims from free text, persist rows, fetch
actuals, or score outcomes (A2–A10 under Epic #1107).

Product rules (Epic #1107):
- Research / quality-ops framing only — not a guaranteed-returns product surface.
- Non-structured prose must not become a verifiable claim.
- When structured fields cannot yield a claim, emit ``no_verifiable_claim`` and
  skip scoring later; never invent a claim or fabricate a hit.
- Numeric fields reject NaN and ±Infinity (``allow_inf_nan=False``).
"""

from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

PREDICTION_RECORD_SCHEMA_VERSION = "prediction-record-v1"

# Trading-day horizons used by later resolvers. Absolute expiry uses resolve_after.
PREDICTION_HORIZON_TOKENS = frozenset({"1d", "3d", "5d", "10d", "20d"})
PredictionHorizon = Literal["1d", "3d", "5d", "10d", "20d"]

PredictionStatus = Literal[
    "pending",
    "resolving",
    "resolved",
    "expired",
    "error",
    "no_verifiable_claim",
]

# Statuses that may enter the verification / scoring pipeline later.
VERIFIABLE_PIPELINE_STATUSES = frozenset(
    {"pending", "resolving", "resolved", "expired", "error"}
)

ClaimType = Literal[
    "direction",
    "return_bucket",
    "level_break",
    "vol_regime",
    "custom",
]

DirectionValue = Literal["up", "down", "sideways"]
LevelBreakSide = Literal["above", "below"]
LevelBreakReference = Literal["absolute_price", "pct_from_as_of_close"]
VolRegimeValue = Literal["low", "normal", "high", "elevated"]
CustomOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in_range"]

NoVerifiableReason = Literal[
    "unparseable_output",
    "prose_only",
    "missing_structured_fields",
    "empty_decision",
    "unsupported_shape",
]

# Machine token for custom expected labels (not free-form sentences).
_CUSTOM_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_.:%+\-]{1,64}$")

_MAX_CLAIMS = 32
_MAX_SKILL_IDS = 64


class _StrictModel(BaseModel):
    """Shared strict base: no extra fields, strict types, no NaN/±Inf."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )


def _require_aware_utc(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None:
        raise ValueError(f"{field_name} must be timezone-aware (UTC preferred)")
    return value.astimezone(timezone.utc)


class DirectionPayload(_StrictModel):
    """Machine-checkable directional claim relative to as_of close."""

    direction: DirectionValue


class ReturnBucketPayload(_StrictModel):
    """Expected simple return range in percent vs as_of close.

    Bounds are finite percentages. Default interval is ``[low_pct, high_pct)``
    when inclusive flags are left at defaults.
    """

    low_pct: float
    high_pct: float
    inclusive_low: bool = True
    inclusive_high: bool = False
    bucket_id: Optional[str] = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _ordered_bounds(self) -> "ReturnBucketPayload":
        if self.low_pct >= self.high_pct:
            raise ValueError("return_bucket low_pct must be strictly less than high_pct")
        return self


class LevelBreakPayload(_StrictModel):
    """Price or percent level expected to be broken within the horizon."""

    side: LevelBreakSide
    level: float
    reference: LevelBreakReference = "absolute_price"


class VolRegimePayload(_StrictModel):
    """Expected realized-volatility regime label (resolver-defined metric)."""

    regime: VolRegimeValue


class CustomClaimPayload(_StrictModel):
    """Structured custom check only — not free-form prose.

    ``expected`` must be a finite number, a short machine token, or (for
    ``in_range``) a pair of finite bounds via ``expected`` + ``expected_high``.
    Narrative strings are rejected so they cannot become fake verifiable claims.
    """

    metric: str = Field(min_length=1, max_length=128)
    operator: CustomOperator
    expected: Union[float, str]
    expected_high: Optional[float] = None
    unit: Optional[str] = Field(default=None, min_length=1, max_length=32)

    @field_validator("expected")
    @classmethod
    def _expected_machine_value(cls, value: Union[float, str]) -> Union[float, str]:
        if isinstance(value, str):
            if not _CUSTOM_TOKEN_PATTERN.fullmatch(value):
                raise ValueError(
                    "custom expected string must be a machine token "
                    "(1..64 of [A-Za-z0-9_.:%+-]), not prose"
                )
            return value
        return value

    @model_validator(mode="after")
    def _in_range_bounds(self) -> "CustomClaimPayload":
        if self.operator == "in_range":
            if not isinstance(self.expected, float):
                raise ValueError(
                    "custom in_range expected must be a finite float low bound"
                )
            if self.expected_high is None:
                raise ValueError("custom in_range requires expected_high")
            if self.expected >= self.expected_high:
                raise ValueError("custom in_range expected must be < expected_high")
        elif self.expected_high is not None:
            raise ValueError("expected_high is only valid when operator is in_range")
        return self


_PAYLOAD_BY_TYPE = {
    "direction": DirectionPayload,
    "return_bucket": ReturnBucketPayload,
    "level_break": LevelBreakPayload,
    "vol_regime": VolRegimePayload,
    "custom": CustomClaimPayload,
}


class PredictionClaim(_StrictModel):
    """One typed, machine-checkable claim inside a PredictionRecord."""

    claim_id: str = Field(min_length=1, max_length=128)
    type: ClaimType
    confidence: float = Field(ge=0.0, le=1.0)
    payload: Union[
        DirectionPayload,
        ReturnBucketPayload,
        LevelBreakPayload,
        VolRegimePayload,
        CustomClaimPayload,
    ]

    @model_validator(mode="before")
    @classmethod
    def _coerce_payload_for_type(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        claim_type = data.get("type")
        payload = data.get("payload")
        payload_cls = _PAYLOAD_BY_TYPE.get(claim_type) if isinstance(claim_type, str) else None
        if payload_cls is None:
            return data
        if isinstance(payload, payload_cls):
            return data
        if isinstance(payload, dict):
            coerced = dict(data)
            coerced["payload"] = payload_cls.model_validate(payload)
            return coerced
        return data

    @model_validator(mode="after")
    def _payload_matches_type(self) -> "PredictionClaim":
        expected = _PAYLOAD_BY_TYPE[self.type]
        if not isinstance(self.payload, expected):
            raise ValueError(
                f"claim type {self.type!r} requires payload of type {expected.__name__}"
            )
        return self


class PredictionModelMeta(_StrictModel):
    """Optional provenance for model / soul / skill / config versions."""

    mode: Optional[str] = Field(default=None, min_length=1, max_length=64)
    soul_version: Optional[str] = Field(default=None, min_length=1, max_length=128)
    skill_ids: List[str] = Field(default_factory=list, max_length=_MAX_SKILL_IDS)
    model_version: Optional[str] = Field(default=None, min_length=1, max_length=128)
    config_version: Optional[str] = Field(default=None, min_length=1, max_length=128)
    model_id: Optional[str] = Field(default=None, min_length=1, max_length=128)

    @field_validator("skill_ids")
    @classmethod
    def _skill_ids_non_empty_tokens(cls, values: List[str]) -> List[str]:
        cleaned: List[str] = []
        for item in values:
            token = item.strip()
            if not token or len(token) > 128:
                raise ValueError("skill_ids entries must contain 1..128 characters")
            if token not in cleaned:
                cleaned.append(token)
        return cleaned


class PredictionRecord(_StrictModel):
    """Structured forecast record ready for later horizon resolution.

    Verifiable pipeline entry requires one or more typed ``claims``. When the
    upstream decision cannot yield machine-checkable structure, use
    :func:`build_no_verifiable_claim_record` instead of inventing claims.
    """

    schema_version: Literal["prediction-record-v1"] = PREDICTION_RECORD_SCHEMA_VERSION
    prediction_id: str = Field(min_length=1, max_length=128)
    run_id: str = Field(min_length=1, max_length=128)
    symbol: str = Field(min_length=1, max_length=32)
    market: Optional[str] = Field(default=None, min_length=1, max_length=16)
    created_at: datetime
    as_of: date
    horizon: PredictionHorizon
    resolve_after: datetime
    claims: List[PredictionClaim] = Field(default_factory=list, max_length=_MAX_CLAIMS)
    status: PredictionStatus
    source_decision_id: Optional[str] = Field(
        default=None, min_length=1, max_length=128
    )
    model_meta: PredictionModelMeta = Field(default_factory=PredictionModelMeta)
    no_verifiable_reason: Optional[NoVerifiableReason] = None
    notes: Optional[str] = Field(
        default=None,
        max_length=500,
        description=(
            "Human-readable research note only; never scored as a claim. "
            "Must not be used to invent verifiable content."
        ),
    )

    @field_validator("created_at", "resolve_after", mode="before")
    @classmethod
    def _parse_aware_datetime(cls, value: Any) -> Any:
        """Accept datetime or ISO-8601 strings from JSON persistence dumps."""
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            text = value.strip()
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            return datetime.fromisoformat(text)
        return value

    @field_validator("as_of", mode="before")
    @classmethod
    def _parse_as_of_date(cls, value: Any) -> Any:
        """Accept date or ISO date strings from JSON persistence dumps."""
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return date.fromisoformat(value.strip()[:10])
        return value

    @field_validator("created_at", "resolve_after")
    @classmethod
    def _utc_aware(cls, value: datetime, info: ValidationInfo) -> datetime:
        return _require_aware_utc(value, info.field_name or "datetime")

    @field_validator(
        "symbol", "market", "run_id", "prediction_id", "source_decision_id"
    )
    @classmethod
    def _no_internal_whitespace(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if any(ch.isspace() for ch in value):
            raise ValueError("identifiers must not contain whitespace")
        return value

    @model_validator(mode="after")
    def _status_claim_invariants(self) -> "PredictionRecord":
        claim_ids = [c.claim_id for c in self.claims]
        if len(claim_ids) != len(set(claim_ids)):
            raise ValueError("claim_id values must be unique within a PredictionRecord")

        if self.status == "no_verifiable_claim":
            if self.claims:
                raise ValueError(
                    "no_verifiable_claim records must not carry claims "
                    "(do not invent verifiable claims from prose)"
                )
            if self.no_verifiable_reason is None:
                raise ValueError(
                    "no_verifiable_claim requires no_verifiable_reason"
                )
            return self

        # Verifiable pipeline statuses require at least one typed claim.
        if self.status in {"pending", "resolving", "resolved"} and not self.claims:
            raise ValueError(
                f"status {self.status!r} requires at least one typed claim; "
                "use status=no_verifiable_claim when structured extraction fails"
            )
        if self.no_verifiable_reason is not None:
            raise ValueError(
                "no_verifiable_reason is only valid when status is no_verifiable_claim"
            )
        return self

    def is_verifiable(self) -> bool:
        """Return True when this record may enter claim scoring later."""
        return self.status != "no_verifiable_claim" and bool(self.claims)

    def to_persistence_dict(self) -> Dict[str, Any]:
        """JSON-ready dict for A3 persistence (no ORM coupling here)."""
        return self.model_dump(mode="json")


def build_no_verifiable_claim_record(
    *,
    prediction_id: str,
    run_id: str,
    symbol: str,
    created_at: datetime,
    as_of: date,
    horizon: PredictionHorizon = "1d",
    resolve_after: Optional[datetime] = None,
    reason: NoVerifiableReason = "unparseable_output",
    market: Optional[str] = None,
    source_decision_id: Optional[str] = None,
    model_meta: Optional[PredictionModelMeta] = None,
    notes: Optional[str] = None,
) -> PredictionRecord:
    """Build an explicit non-scoring record when structure cannot be extracted.

    This is the only supported path for unparseable / prose-only outputs.
    Callers must not synthesize directional or bucket claims from narrative text.

    Naive ``created_at`` / ``resolve_after`` values are treated as UTC so the
    helper stays usable for offline fixtures without inventing claim content.
    """
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)

    if resolve_after is None:
        resolve_after = created_at
    elif resolve_after.tzinfo is None:
        resolve_after = resolve_after.replace(tzinfo=timezone.utc)
    else:
        resolve_after = resolve_after.astimezone(timezone.utc)

    return PredictionRecord(
        prediction_id=prediction_id,
        run_id=run_id,
        symbol=symbol,
        market=market,
        created_at=created_at,
        as_of=as_of,
        horizon=horizon,
        resolve_after=resolve_after,
        claims=[],
        status="no_verifiable_claim",
        source_decision_id=source_decision_id,
        model_meta=model_meta or PredictionModelMeta(),
        no_verifiable_reason=reason,
        notes=notes,
    )


def validate_prediction_record(payload: Any) -> PredictionRecord:
    """Validate an arbitrary payload into a PredictionRecord (strict)."""
    return PredictionRecord.model_validate(payload)


def try_validate_prediction_record(
    payload: Any,
) -> tuple[Optional[PredictionRecord], Optional[str]]:
    """Validate without raising; return (record, None) or (None, error)."""
    try:
        return validate_prediction_record(payload), None
    except Exception as exc:  # noqa: BLE001 — surface validation text only
        return None, str(exc)


ClaimPayload = Union[
    DirectionPayload,
    ReturnBucketPayload,
    LevelBreakPayload,
    VolRegimePayload,
    CustomClaimPayload,
]

__all__ = [
    "PREDICTION_HORIZON_TOKENS",
    "PREDICTION_RECORD_SCHEMA_VERSION",
    "VERIFIABLE_PIPELINE_STATUSES",
    "ClaimPayload",
    "ClaimType",
    "CustomClaimPayload",
    "CustomOperator",
    "DirectionPayload",
    "DirectionValue",
    "LevelBreakPayload",
    "LevelBreakReference",
    "LevelBreakSide",
    "NoVerifiableReason",
    "PredictionClaim",
    "PredictionHorizon",
    "PredictionModelMeta",
    "PredictionRecord",
    "PredictionStatus",
    "ReturnBucketPayload",
    "VolRegimePayload",
    "VolRegimeValue",
    "build_no_verifiable_claim_record",
    "try_validate_prediction_record",
    "validate_prediction_record",
]
