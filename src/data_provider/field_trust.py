# -*- coding: utf-8 -*-
"""Per-field trust metadata for realtime quotes (Issue #1129).

This module records field-level provenance while a quote travels through the
EXISTING multi-provider fallback chain in :mod:`src.data_provider.base`:

- primary attribution comes from the quote's own ``source`` at enrich time;
- supplement attribution is recorded when ``_merge_quote_fields`` fills a
  missing field from a secondary provider;
- conflicts are captured from the existing Issue #185 cross-source
  comparison (:func:`src.data_provider.data_validation.compare_cross_source_quotes`)
  instead of adding a parallel comparison pass;
- provider attempts and circuit-breaker snapshots reuse the existing
  fallback / health concepts; they never silently pick one source as truth.

Design rules:
- The metadata is additive and optional. Consumers must treat an absent or
  partial ``field_trust`` payload as "unknown", never as "trusted".
- Recording must never break the quote path: helpers swallow their own
  errors after logging, because a missing trust payload degrades to
  "unknown" on the read side (fail-closed for trust, fail-open for data).
- Analysis input is a provider-neutral projection (gaps + confidence).
  This module does not compile monitors or alerts (Issue #1133).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FIELD_TRUST_SCHEMA_VERSION = "field_trust_v1"
ANALYSIS_INPUT_SCHEMA_VERSION = "field_trust_analysis_input/1.0"

# Key quote fields covered by field-level trust. Mirrors the core price
# fields plus DataFetcherManager._SUPPLEMENT_FIELDS. Additive only.
TRUST_FIELDS: tuple = (
    # Core price data
    "price",
    "change_pct",
    "change_amount",
    "open_price",
    "high",
    "low",
    "pre_close",
    "volume",
    "amount",
    # Supplementable fields (see DataFetcherManager._SUPPLEMENT_FIELDS)
    "volume_ratio",
    "turnover_rate",
    "pe_ratio",
    "pb_ratio",
    "total_mv",
    "circ_mv",
    "amplitude",
    "iopv",
    "nav",
)

STALENESS_FRESH = "fresh"
STALENESS_STALE = "stale"
STALENESS_UNKNOWN = "unknown"

CONFLICT_CHECK_EVALUATED = "evaluated"
CONFLICT_CHECK_SKIPPED = "skipped"

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"

PROVIDER_STATUS_OK = "ok"
PROVIDER_STATUS_FAILED = "failed"
PROVIDER_STATUS_EMPTY = "empty"
PROVIDER_STATUS_UNAVAILABLE = "unavailable"

PROVIDER_ROLE_PRIMARY = "primary"
PROVIDER_ROLE_SUPPLEMENT = "supplement"
PROVIDER_ROLE_ATTEMPTED = "attempted"


def _source_token(value: Any) -> Optional[str]:
    """Normalize RealtimeSource / str provider identifiers to a plain token."""
    if value is None:
        return None
    token = getattr(value, "value", value)
    try:
        token = str(token).strip()
    except Exception:  # broad-exception: fallback_recorded - unknown provider object stays unattributed
        return None
    return token or None


def _ensure_payload(quote: Any) -> Optional[Dict[str, Any]]:
    """Return the mutable trust payload on *quote*, creating it if needed."""
    if quote is None:
        return None
    payload = getattr(quote, "field_trust", None)
    if not isinstance(payload, dict):
        payload = {
            "schema_version": FIELD_TRUST_SCHEMA_VERSION,
            "fields": {},
            "conflicts": [],
            "conflict_checks": [],
            "provider_attempts": [],
        }
        try:
            setattr(quote, "field_trust", payload)
        except Exception:  # broad-exception: fallback_recorded - frozen quote objects simply carry no trust payload
            return None
    payload.setdefault("schema_version", FIELD_TRUST_SCHEMA_VERSION)
    payload.setdefault("fields", {})
    payload.setdefault("conflicts", [])
    payload.setdefault("conflict_checks", [])
    payload.setdefault("provider_attempts", [])
    return payload


def record_supplement(quote: Any, filled_fields: List[str], secondary: Any) -> None:
    """Attribute *filled_fields* on *quote* to the secondary provider.

    Called by ``DataFetcherManager._merge_quote_fields`` right after fields
    are copied from *secondary* into the primary quote.
    """
    try:
        if not filled_fields:
            return
        payload = _ensure_payload(quote)
        if payload is None:
            return
        source = _source_token(getattr(secondary, "source", None))
        provider_ts = getattr(secondary, "provider_timestamp", None)
        for field_name in filled_fields:
            payload["fields"][str(field_name)] = {
                "source": source,
                "origin": "supplement",
                "provider_timestamp": (
                    str(provider_ts) if provider_ts is not None else None
                ),
            }
        if source:
            record_provider_attempt(
                quote,
                provider=source,
                status=PROVIDER_STATUS_OK,
                role=PROVIDER_ROLE_SUPPLEMENT,
            )
    except Exception as exc:  # broad-exception: fallback_recorded - absent trust metadata reads as unknown, never trusted
        logger.debug("field_trust record_supplement failed: %s", exc)


def record_conflict_check(
    quote: Any,
    *,
    primary_provider: Any,
    secondary_provider: Any,
    status: str,
    reason: Optional[str] = None,
) -> None:
    """Record that a cross-source comparison was (or was not) performed."""
    try:
        payload = _ensure_payload(quote)
        if payload is None:
            return
        entry: Dict[str, Any] = {
            "primary_provider": _source_token(primary_provider),
            "secondary_provider": _source_token(secondary_provider),
            "status": status,
        }
        if reason:
            entry["reason"] = str(reason)[:120]
        payload["conflict_checks"].append(entry)
    except Exception as exc:  # broad-exception: fallback_recorded - absent trust metadata reads as unknown, never trusted
        logger.debug("field_trust record_conflict_check failed: %s", exc)


def record_cross_source_result(
    quote: Any,
    result: Any,
    *,
    primary_provider: Any,
    secondary_provider: Any,
) -> None:
    """Capture divergence findings from an existing ValidationResult.

    *result* is the return value of ``compare_cross_source_quotes``. When
    validation is disabled the comparison never ran, so the check is
    recorded as skipped instead of silently implying agreement.
    """
    try:
        payload = _ensure_payload(quote)
        if payload is None:
            return
        context = getattr(result, "context", None) or {}
        if context.get("enabled") is False or context.get("compared") is False:
            record_conflict_check(
                quote,
                primary_provider=primary_provider,
                secondary_provider=secondary_provider,
                status=CONFLICT_CHECK_SKIPPED,
                reason=(
                    "validation_disabled"
                    if context.get("enabled") is False
                    else "not_compared"
                ),
            )
            return
        record_conflict_check(
            quote,
            primary_provider=primary_provider,
            secondary_provider=secondary_provider,
            status=CONFLICT_CHECK_EVALUATED,
        )
        for issue in getattr(result, "issues", None) or []:
            field_name = getattr(issue, "field", None)
            code = getattr(issue, "code", "") or ""
            if not field_name or "cross_source" not in str(code):
                continue
            detail = getattr(issue, "detail", None) or {}
            payload["conflicts"].append(
                {
                    "field": str(field_name),
                    "severity": _source_token(getattr(issue, "severity", None))
                    or "warn",
                    "relative_difference": detail.get("relative_difference"),
                    "threshold": detail.get("threshold"),
                    "values": detail.get("values") or [],
                }
            )
    except Exception as exc:  # broad-exception: fallback_recorded - absent trust metadata reads as unknown, never trusted
        logger.debug("field_trust record_cross_source_result failed: %s", exc)


def record_provider_attempt(
    quote: Any,
    *,
    provider: Any,
    status: str,
    role: str = PROVIDER_ROLE_ATTEMPTED,
) -> None:
    """Record one provider attempt on the quote's trust payload."""
    try:
        payload = _ensure_payload(quote)
        if payload is None:
            return
        token = _source_token(provider)
        if not token:
            return
        normalized_status = status if status in {
            PROVIDER_STATUS_OK,
            PROVIDER_STATUS_FAILED,
            PROVIDER_STATUS_EMPTY,
            PROVIDER_STATUS_UNAVAILABLE,
        } else PROVIDER_STATUS_UNAVAILABLE
        normalized_role = role if role in {
            PROVIDER_ROLE_PRIMARY,
            PROVIDER_ROLE_SUPPLEMENT,
            PROVIDER_ROLE_ATTEMPTED,
        } else PROVIDER_ROLE_ATTEMPTED
        attempts = payload["provider_attempts"]
        for existing in attempts:
            if (
                existing.get("provider") == token
                and existing.get("status") == normalized_status
                and existing.get("role") == normalized_role
            ):
                return
        attempts.append(
            {
                "provider": token,
                "status": normalized_status,
                "role": normalized_role,
            }
        )
    except Exception as exc:  # broad-exception: fallback_recorded - absent trust metadata reads as unknown, never trusted
        logger.debug("field_trust record_provider_attempt failed: %s", exc)


def attach_failed_sources(quote: Any, failed_sources: Optional[List[Any]]) -> None:
    """Attribute whole-source fallback failures already tracked by the manager."""
    try:
        for source in failed_sources or []:
            record_provider_attempt(
                quote,
                provider=source,
                status=PROVIDER_STATUS_FAILED,
                role=PROVIDER_ROLE_ATTEMPTED,
            )
    except Exception as exc:  # broad-exception: fallback_recorded - absent trust metadata reads as unknown, never trusted
        logger.debug("field_trust attach_failed_sources failed: %s", exc)


def _circuit_snapshots() -> Dict[str, Dict[str, Any]]:
    try:
        from src.data_provider.realtime_types import get_realtime_circuit_breaker

        snapshot = get_realtime_circuit_breaker().get_snapshot()
        return snapshot if isinstance(snapshot, dict) else {}
    except Exception:  # broad-exception: fallback_recorded - circuit health is optional enrichment
        return {}


def build_provider_health(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Project provider-neutral health rows from attempts + circuit snapshots."""
    circuits = _circuit_snapshots()
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for attempt in payload.get("provider_attempts") or []:
        if not isinstance(attempt, dict):
            continue
        provider = _source_token(attempt.get("provider"))
        if not provider:
            continue
        seen.add(provider)
        circuit = circuits.get(provider) or {}
        rows.append(
            {
                "provider": provider,
                "status": attempt.get("status") or PROVIDER_STATUS_UNAVAILABLE,
                "role": attempt.get("role") or PROVIDER_ROLE_ATTEMPTED,
                "circuit_state": circuit.get("state"),
                "available": circuit.get("available"),
                "health_score": circuit.get("health_score"),
            }
        )
    return rows


def build_analysis_input(payload: Dict[str, Any], quote: Any = None) -> Dict[str, Any]:
    """Provider-neutral gap + confidence projection for analysis consumers.

    High confidence is reserved for fresh, attributed, conflict-free fields.
    Conflicts, staleness, missing metadata, skipped comparisons, and preferred
    provider failures are gaps — they never collapse to a silent winner.
    """
    gaps: List[Dict[str, Any]] = []
    fields = payload.get("fields") if isinstance(payload.get("fields"), dict) else {}
    conflicts = [
        entry
        for entry in (payload.get("conflicts") or [])
        if isinstance(entry, dict) and entry.get("field")
    ]
    conflicted = {str(entry.get("field")) for entry in conflicts}
    for conflict in conflicts:
        gaps.append(
            {
                "code": "conflict",
                "field": str(conflict["field"]),
                "detail": "providers disagreed; no source was chosen as truth",
            }
        )

    for field_name, raw in fields.items():
        if not isinstance(raw, dict):
            gaps.append(
                {
                    "code": "unattributed",
                    "field": str(field_name),
                    "detail": "field present without a trust entry",
                }
            )
            continue
        if raw.get("source") is None:
            gaps.append(
                {
                    "code": "unattributed",
                    "field": str(field_name),
                    "detail": "field has no provider attribution",
                }
            )
        staleness = raw.get("staleness")
        if staleness == STALENESS_STALE or raw.get("is_stale") is True:
            gaps.append(
                {
                    "code": "stale",
                    "field": str(field_name),
                    "detail": "provider timestamp exceeded the realtime TTL",
                }
            )
        elif staleness != STALENESS_FRESH:
            gaps.append(
                {
                    "code": "unknown_staleness",
                    "field": str(field_name),
                    "detail": "staleness could not be proven; do not treat as fresh",
                }
            )
        if field_name in conflicted:
            continue

    missing_fields = list(getattr(quote, "missing_fields", None) or [])
    for field_name in missing_fields:
        gaps.append(
            {
                "code": "missing",
                "field": str(field_name),
                "detail": "quote reported this field as missing",
            }
        )

    for check in payload.get("conflict_checks") or []:
        if not isinstance(check, dict):
            continue
        if check.get("status") == CONFLICT_CHECK_SKIPPED:
            gaps.append(
                {
                    "code": "conflict_check_skipped",
                    "field": None,
                    "detail": str(check.get("reason") or "comparison did not run"),
                }
            )

    failed_attempts = [
        attempt
        for attempt in (payload.get("provider_attempts") or [])
        if isinstance(attempt, dict)
        and attempt.get("status") in {PROVIDER_STATUS_FAILED, PROVIDER_STATUS_EMPTY}
    ]
    for attempt in failed_attempts:
        gaps.append(
            {
                "code": "provider_failed",
                "field": None,
                "detail": "{provider}:{status}".format(
                    provider=attempt.get("provider") or "unknown",
                    status=attempt.get("status"),
                ),
            }
        )

    if not fields:
        gaps.append(
            {
                "code": "no_attributable_fields",
                "field": None,
                "detail": "no covered quote fields were attributable",
            }
        )

    codes = {str(gap.get("code")) for gap in gaps}
    if codes.intersection(
        {"conflict", "stale", "provider_failed", "no_attributable_fields", "unattributed"}
    ):
        confidence = CONFIDENCE_LOW
    elif codes:
        confidence = CONFIDENCE_MEDIUM
    else:
        confidence = CONFIDENCE_HIGH

    return {
        "schema_version": ANALYSIS_INPUT_SCHEMA_VERSION,
        "confidence": confidence,
        "gaps": gaps,
        "conflict_count": len(conflicts),
        "failed_provider_count": len(failed_attempts),
    }


def project_analysis_input(quote: Any) -> Dict[str, Any]:
    """Return the analysis-input projection, treating missing metadata as a gap."""
    payload = getattr(quote, "field_trust", None) if quote is not None else None
    if not isinstance(payload, dict):
        return {
            "schema_version": ANALYSIS_INPUT_SCHEMA_VERSION,
            "confidence": CONFIDENCE_LOW,
            "gaps": [
                {
                    "code": "metadata_absent",
                    "field": None,
                    "detail": "quote carried no field-level trust metadata",
                }
            ],
            "conflict_count": 0,
            "failed_provider_count": 0,
        }
    analysis = payload.get("analysis_input")
    if isinstance(analysis, dict) and analysis.get("confidence"):
        return analysis
    return build_analysis_input(payload, quote)


def finalize(quote: Any) -> None:
    """Complete field attribution once quote-level staleness is normalized.

    Called at the end of ``DataFetcherManager._enrich_realtime_quote``, which
    is the single exit point of every successful realtime-quote path.

    - Fields without a supplement record are attributed to the primary
      source and inherit the quote-level staleness verdict.
    - Supplement fields keep their own provider; their staleness is
      "unknown" because supplement timestamps are not TTL-normalized.
    - Conflicted fields are flagged so read-side consumers can degrade.
    - Analysis input (gaps + confidence) is attached so analysis consumers
      receive the same verdict the API/Web panel shows.
    """
    try:
        payload = _ensure_payload(quote)
        if payload is None:
            return
        primary_source = _source_token(getattr(quote, "source", None))
        provider_ts = getattr(quote, "provider_timestamp", None)
        stale_seconds = getattr(quote, "stale_seconds", None)
        is_stale = getattr(quote, "is_stale", None)
        if is_stale is True:
            primary_staleness = STALENESS_STALE
        elif is_stale is False:
            primary_staleness = STALENESS_FRESH
        else:
            primary_staleness = STALENESS_UNKNOWN

        if primary_source:
            record_provider_attempt(
                quote,
                provider=primary_source,
                status=PROVIDER_STATUS_OK,
                role=PROVIDER_ROLE_PRIMARY,
            )
        fallback_from = getattr(quote, "fallback_from", None)
        if fallback_from:
            record_provider_attempt(
                quote,
                provider=fallback_from,
                status=PROVIDER_STATUS_FAILED,
                role=PROVIDER_ROLE_ATTEMPTED,
            )

        conflicted_fields = {
            str(entry.get("field"))
            for entry in payload.get("conflicts", [])
            if entry.get("field")
        }

        fields = payload["fields"]
        for field_name in TRUST_FIELDS:
            value = getattr(quote, field_name, None)
            entry = fields.get(field_name)
            if entry is None:
                if value is None:
                    continue
                entry = {
                    "source": primary_source,
                    "origin": "primary",
                    "provider_timestamp": provider_ts,
                }
                fields[field_name] = entry
            if entry.get("origin") == "primary":
                entry["stale_seconds"] = stale_seconds
                entry["is_stale"] = is_stale
                entry["staleness"] = primary_staleness
            else:
                # Supplement timestamps are provider-raw and not TTL-checked:
                # surface them as unknown rather than implying freshness.
                entry.setdefault("stale_seconds", None)
                entry.setdefault("is_stale", None)
                entry.setdefault("staleness", STALENESS_UNKNOWN)
            entry["conflict"] = field_name in conflicted_fields

        payload["provider_health"] = build_provider_health(payload)
        payload["analysis_input"] = build_analysis_input(payload, quote)
    except Exception as exc:  # broad-exception: fallback_recorded - absent trust metadata reads as unknown, never trusted
        logger.debug("field_trust finalize failed: %s", exc)
