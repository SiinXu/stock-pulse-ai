# -*- coding: utf-8 -*-
"""Per-field trust metadata for realtime quotes (Issue #1129).

This module records field-level provenance while a quote travels through the
EXISTING multi-provider fallback chain in :mod:`data_provider.base`:

- primary attribution comes from the quote's own ``source`` at enrich time;
- supplement attribution is recorded when ``_merge_quote_fields`` fills a
  missing field from a secondary provider;
- conflicts are captured from the existing Issue #185 cross-source
  comparison (:func:`data_provider.data_validation.compare_cross_source_quotes`)
  instead of adding a parallel comparison pass.

Design rules:
- The metadata is additive and optional. Consumers must treat an absent or
  partial ``field_trust`` payload as "unknown", never as "trusted".
- Recording must never break the quote path: helpers swallow their own
  errors after logging, because a missing trust payload degrades to
  "unknown" on the read side (fail-closed for trust, fail-open for data).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FIELD_TRUST_SCHEMA_VERSION = "field_trust_v1"

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
        }
        try:
            setattr(quote, "field_trust", payload)
        except Exception:  # broad-exception: fallback_recorded - frozen quote objects simply carry no trust payload
            return None
    payload.setdefault("schema_version", FIELD_TRUST_SCHEMA_VERSION)
    payload.setdefault("fields", {})
    payload.setdefault("conflicts", [])
    payload.setdefault("conflict_checks", [])
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


def finalize(quote: Any) -> None:
    """Complete field attribution once quote-level staleness is normalized.

    Called at the end of ``DataFetcherManager._enrich_realtime_quote``, which
    is the single exit point of every successful realtime-quote path.

    - Fields without a supplement record are attributed to the primary
      source and inherit the quote-level staleness verdict.
    - Supplement fields keep their own provider; their staleness is
      "unknown" because supplement timestamps are not TTL-normalized.
    - Conflicted fields are flagged so read-side consumers can degrade.
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
    except Exception as exc:  # broad-exception: fallback_recorded - absent trust metadata reads as unknown, never trusted
        logger.debug("field_trust finalize failed: %s", exc)
