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
from threading import RLock
from typing import Any, Dict, List, Optional, Tuple

from src.utils.sanitize import log_safe_exception

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

# Same-route aliases only. Coarse display tokens must not attach a
# different market's circuit (CN EM ↛ ETF/HK, CN Sina ↛ HK Sina).
# Exact route identity belongs on attempt.circuit_key. Quote-local
# transport, when needed, uses a private non-serialized attribute.
_CIRCUIT_KEY_ATTR = "_field_trust_circuit_key"
_CIRCUIT_KEY_ALIASES: Dict[str, Tuple[str, ...]] = {
    "tencent": ("akshare_tencent",),
    "akshare_qq": ("akshare_tencent",),
    "akshare_tencent": ("tencent",),
}

_NON_OK_PROVIDER_STATUSES = {
    PROVIDER_STATUS_FAILED,
    PROVIDER_STATUS_EMPTY,
    PROVIDER_STATUS_UNAVAILABLE,
}

_FALLBACK_SOURCE_TOKEN = "fallback"


class QuoteAttemptSink:
    """Request-local, concurrency-safe recorder for one fetcher attempt.

    ``_try_fetcher_quote`` keeps its Optional-quote return contract. Callers
    bind a fresh sink per attempt so concurrent requests cannot share state.
    The first ``record`` wins; later writes are ignored.
    """

    __slots__ = ("_lock", "_result")

    def __init__(self) -> None:
        self._lock = RLock()
        self._result: Optional[Dict[str, str]] = None

    def record(
        self,
        provider: Any,
        status: str,
        circuit_key: Optional[str] = None,
    ) -> None:
        token = _source_token(provider)
        if not token:
            return
        normalized = (
            status
            if status
            in {
                PROVIDER_STATUS_OK,
                PROVIDER_STATUS_FAILED,
                PROVIDER_STATUS_EMPTY,
                PROVIDER_STATUS_UNAVAILABLE,
            }
            else PROVIDER_STATUS_UNAVAILABLE
        )
        resolved_circuit = _optional_token(circuit_key)
        with self._lock:
            if self._result is not None:
                return
            result: Dict[str, str] = {"provider": token, "status": normalized}
            if resolved_circuit:
                result["circuit_key"] = resolved_circuit
            self._result = result

    def snapshot(self) -> Optional[Dict[str, str]]:
        with self._lock:
            if self._result is None:
                return None
            return dict(self._result)

    @property
    def provider(self) -> Optional[str]:
        result = self.snapshot()
        return None if result is None else result.get("provider")

    @property
    def status(self) -> Optional[str]:
        result = self.snapshot()
        return None if result is None else result.get("status")


def is_concrete_source_token(token: Optional[str]) -> bool:
    """Return True when *token* is a real provider identity, not fallback."""
    return bool(token) and token != _FALLBACK_SOURCE_TOKEN


def circuit_lookup_keys(
    provider: Any,
    circuit_key: Optional[str] = None,
) -> Tuple[str, ...]:
    """Return exact circuit key first, then same-route aliases only."""
    explicit = _optional_token(circuit_key)
    if explicit:
        return (explicit,)
    token = _source_token(provider)
    if not token:
        return ()
    aliases = _CIRCUIT_KEY_ALIASES.get(token)
    if not aliases:
        return (token,)
    seen = {token}
    keys = [token]
    for alias in aliases:
        if alias not in seen:
            seen.add(alias)
            keys.append(alias)
    return tuple(keys)


def resolve_circuit_snapshot(
    provider: Any,
    circuits: Optional[Dict[str, Any]] = None,
    circuit_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Find a circuit snapshot without renaming the public provider token."""
    if not isinstance(circuits, dict):
        circuits = {}
    for key in circuit_lookup_keys(provider, circuit_key=circuit_key):
        snapshot = circuits.get(key)
        if isinstance(snapshot, dict) and snapshot:
            return snapshot
    return {}


def derive_circuit_key(
    provider: Any,
    *,
    stock_code: Optional[str] = None,
    source: Optional[str] = None,
    market: Optional[str] = None,
    quote: Any = None,
    circuit_key: Optional[str] = None,
) -> Optional[str]:
    """Return the exact circuit-breaker identity for one attempt.

    Public provider tokens stay coarse (``akshare_em``, ``akshare_sina``).
    Circuit keys distinguish CN / ETF / HK routes of the same token.
    An explicit attempt key or private quote-local identity always wins.
    """
    explicit = _optional_token(circuit_key) or quote_circuit_key(quote)
    if explicit:
        return explicit

    token = _source_token(provider)
    code = stock_code or getattr(quote, "code", None)
    market_token = _optional_token(market) or _optional_token(
        getattr(quote, "market", None)
    )
    route_source = _optional_token(source)

    if not market_token and code:
        try:
            from src.data_provider.symbol_normalization import (
                _is_etf_code,
                _market_tag,
            )

            if _is_etf_code(str(code)):
                market_token = "etf"
            else:
                market_token = _market_tag(str(code))
        except Exception as exc:  # broad-exception: fallback_recorded - market inference is optional for circuit identity
            log_safe_exception(
                logger,
                "Field-trust circuit market inference failed",
                exc,
                error_code="field_trust_circuit_market_failed",
                level=logging.DEBUG,
            )
            market_token = None

    if token in {"tencent", "akshare_qq", "akshare_tencent"}:
        return "akshare_tencent"
    if token == "akshare_etf" or (
        token in {"akshare_em", "akshare"} and market_token == "etf"
    ):
        return "akshare_etf"
    if token == "akshare_hk_em":
        return "akshare_hk_em"
    if token == "akshare_hk_sina":
        return "akshare_hk_sina"

    akshare_tokens = {"akshare", "akshare_em", "akshare_sina", "akshare_hk"}
    is_hk = (
        market_token == "hk"
        or token == "akshare_hk"
        or route_source == "hk"
    )
    if is_hk and token in akshare_tokens:
        if token == "akshare_sina" or route_source == "sina":
            return "akshare_hk_sina"
        return "akshare_hk_em"

    if token == "akshare_sina":
        return "akshare_sina"
    if token == "akshare_em":
        return "akshare_em"
    return token


def _source_token(value: Any) -> Optional[str]:
    """Normalize RealtimeSource / str provider identifiers to a plain token."""
    if value is None:
        return None
    token = getattr(value, "value", value)
    try:
        token = str(token).strip()
    except Exception as exc:  # broad-exception: fallback_recorded - unknown provider object stays unattributed
        log_safe_exception(
            logger,
            "Field-trust source token unavailable",
            exc,
            error_code="field_trust_source_token_failed",
            level=logging.DEBUG,
        )
        return None
    return token or None


def _optional_token(value: Any) -> Optional[str]:
    """Return a stripped token or None when *value* is empty."""
    return _source_token(value)


def quote_circuit_key(quote: Any) -> Optional[str]:
    """Read quote-local circuit identity without treating it as public payload."""
    if quote is None:
        return None
    return _optional_token(getattr(quote, _CIRCUIT_KEY_ATTR, None))


def set_quote_circuit_key(quote: Any, circuit_key: Optional[str]) -> None:
    """Attach exact circuit identity as a private, non-serialized quote attribute."""
    token = _optional_token(circuit_key)
    if quote is None or not token:
        return
    try:
        setattr(quote, _CIRCUIT_KEY_ATTR, token)
    except Exception as exc:  # broad-exception: fallback_recorded - quote identity stays on attempts
        log_safe_exception(
            logger,
            "Field-trust circuit key attach failed",
            exc,
            error_code="field_trust_circuit_key_attach_failed",
            level=logging.DEBUG,
        )


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
        except Exception as exc:  # broad-exception: fallback_recorded - frozen quote objects simply carry no trust payload
            log_safe_exception(
                logger,
                "Field-trust payload attach failed",
                exc,
                error_code="field_trust_payload_attach_failed",
                level=logging.DEBUG,
            )
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
                circuit_key=quote_circuit_key(secondary),
                stock_code=getattr(quote, "code", None),
                market=getattr(quote, "market", None),
            )
    except Exception as exc:  # broad-exception: fallback_recorded - absent trust metadata reads as unknown, never trusted
        log_safe_exception(
            logger,
            "Field-trust supplement recording failed",
            exc,
            error_code="field_trust_supplement_record_failed",
            level=logging.DEBUG,
        )


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
        log_safe_exception(
            logger,
            "Field-trust conflict-check recording failed",
            exc,
            error_code="field_trust_conflict_check_record_failed",
            level=logging.DEBUG,
        )


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
        log_safe_exception(
            logger,
            "Field-trust cross-source recording failed",
            exc,
            error_code="field_trust_cross_source_record_failed",
            level=logging.DEBUG,
        )


def record_provider_attempt(
    quote: Any,
    *,
    provider: Any,
    status: str,
    role: str = PROVIDER_ROLE_ATTEMPTED,
    circuit_key: Optional[str] = None,
    stock_code: Optional[str] = None,
    source: Optional[str] = None,
    market: Optional[str] = None,
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
        resolved_circuit = derive_circuit_key(
            token,
            stock_code=stock_code or getattr(quote, "code", None),
            source=source,
            market=market or getattr(quote, "market", None),
            quote=quote,
            circuit_key=circuit_key,
        )
        attempts = payload["provider_attempts"]
        for existing in attempts:
            if (
                existing.get("provider") == token
                and existing.get("status") == normalized_status
                and existing.get("role") == normalized_role
                and existing.get("circuit_key") == resolved_circuit
            ):
                return
        entry: Dict[str, Any] = {
            "provider": token,
            "status": normalized_status,
            "role": normalized_role,
        }
        if resolved_circuit:
            entry["circuit_key"] = resolved_circuit
        attempts.append(entry)
    except Exception as exc:  # broad-exception: fallback_recorded - absent trust metadata reads as unknown, never trusted
        log_safe_exception(
            logger,
            "Field-trust provider-attempt recording failed",
            exc,
            error_code="field_trust_provider_attempt_record_failed",
            level=logging.DEBUG,
        )


def attach_failed_sources(
    quote: Any,
    failed_sources: Optional[List[Any]],
    *,
    stock_code: Optional[str] = None,
) -> None:
    """Attribute whole-source fallback failures already tracked by the manager."""
    try:
        for source in failed_sources or []:
            record_provider_attempt(
                quote,
                provider=source,
                status=PROVIDER_STATUS_FAILED,
                role=PROVIDER_ROLE_ATTEMPTED,
                stock_code=stock_code or getattr(quote, "code", None),
            )
    except Exception as exc:  # broad-exception: fallback_recorded - absent trust metadata reads as unknown, never trusted
        log_safe_exception(
            logger,
            "Field-trust failed-source attachment failed",
            exc,
            error_code="field_trust_failed_sources_attach_failed",
            level=logging.DEBUG,
        )


def _circuit_snapshots() -> Dict[str, Dict[str, Any]]:
    try:
        from src.data_provider.realtime_types import get_realtime_circuit_breaker

        snapshot = get_realtime_circuit_breaker().get_snapshot()
        return snapshot if isinstance(snapshot, dict) else {}
    except Exception as exc:  # broad-exception: fallback_recorded - circuit health is optional enrichment
        log_safe_exception(
            logger,
            "Field-trust circuit snapshot unavailable",
            exc,
            error_code="field_trust_circuit_snapshot_failed",
            level=logging.DEBUG,
        )
        return {}


def resolve_source_token(*candidates: Any) -> Optional[str]:
    """Return the first normalized provider token among *candidates*."""
    for candidate in candidates:
        token = _source_token(candidate)
        if token:
            return token
    return None


def record_comparison_failure(
    quote: Any,
    *,
    primary_provider: Any,
    secondary_provider: Any,
) -> None:
    """Record that a comparison attempted to run and failed closed for trust."""
    record_conflict_check(
        quote,
        primary_provider=primary_provider,
        secondary_provider=secondary_provider,
        status=CONFLICT_CHECK_SKIPPED,
        reason="comparison_failed",
    )


def observe_cross_source_quotes(
    primary: Any,
    secondary: Any,
    *,
    stock_code: str,
    market: Optional[str] = None,
    primary_candidates: tuple = (),
    secondary_candidates: tuple = (),
    asset_type: Any = None,
) -> None:
    """Run the existing comparison and record evaluated, skipped, or failed checks.

    Comparison exceptions are recorded as ``comparison_failed`` skips so an
    unevaluated pair cannot read as agreement or high confidence.
    """
    primary_provider = resolve_source_token(*primary_candidates) or "primary"
    secondary_provider = resolve_source_token(*secondary_candidates)
    try:
        from src.data_provider.data_validation import compare_cross_source_quotes

        result = compare_cross_source_quotes(
            primary,
            secondary,
            primary_provider=str(primary_provider),
            secondary_provider=str(secondary_provider or "secondary"),
            market=market,
            stock_code=stock_code,
            asset_type=asset_type,
        )
        record_cross_source_result(
            primary,
            result,
            primary_provider=primary_provider,
            secondary_provider=secondary_provider,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - failed comparison is recorded, not treated as agreement
        log_safe_exception(
            logger,
            "Cross-source quote comparison failed",
            exc,
            error_code="data_validation_cross_source_failed",
            level=logging.DEBUG,
            context={"symbol": stock_code, "provider": str(secondary_provider or "")},
        )
        record_comparison_failure(
            primary,
            primary_provider=primary_provider,
            secondary_provider=secondary_provider,
        )


def build_provider_health(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Project provider-neutral health rows from attempts + circuit snapshots."""
    circuits = _circuit_snapshots()
    rows: List[Dict[str, Any]] = []
    for attempt in payload.get("provider_attempts") or []:
        if not isinstance(attempt, dict):
            continue
        provider = _source_token(attempt.get("provider"))
        if not provider:
            continue
        circuit_key = _optional_token(attempt.get("circuit_key"))
        circuit = resolve_circuit_snapshot(
            provider,
            circuits,
            circuit_key=circuit_key,
        )
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
        and attempt.get("status") in _NON_OK_PROVIDER_STATUSES
    ]
    seen_provider_gap_keys = set()
    for attempt in failed_attempts:
        status = attempt.get("status")
        gap_code = (
            "provider_unavailable"
            if status == PROVIDER_STATUS_UNAVAILABLE
            else "provider_failed"
        )
        detail = "{provider}:{status}".format(
            provider=attempt.get("provider") or "unknown",
            status=status,
        )
        seen_provider_gap_keys.add(detail)
        gaps.append(
            {
                "code": gap_code,
                "field": None,
                "detail": detail,
            }
        )

    health_rows = payload.get("provider_health")
    if not isinstance(health_rows, list):
        health_rows = build_provider_health(payload)
    for row in health_rows:
        if not isinstance(row, dict):
            continue
        provider = row.get("provider") or "unknown"
        if row.get("available") is False:
            detail = "{provider}:circuit_unavailable".format(provider=provider)
            if detail not in seen_provider_gap_keys:
                seen_provider_gap_keys.add(detail)
                gaps.append(
                    {
                        "code": "provider_unavailable",
                        "field": None,
                        "detail": detail,
                    }
                )
            continue
        status = row.get("status")
        if status in _NON_OK_PROVIDER_STATUSES:
            detail = "{provider}:{status}".format(provider=provider, status=status)
            if detail not in seen_provider_gap_keys:
                seen_provider_gap_keys.add(detail)
                gaps.append(
                    {
                        "code": (
                            "provider_unavailable"
                            if status == PROVIDER_STATUS_UNAVAILABLE
                            else "provider_failed"
                        ),
                        "field": None,
                        "detail": detail,
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
        {
            "conflict",
            "stale",
            "provider_failed",
            "provider_unavailable",
            "no_attributable_fields",
            "unattributed",
        }
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
                circuit_key=quote_circuit_key(quote),
                stock_code=getattr(quote, "code", None),
                market=getattr(quote, "market", None),
            )
        fallback_from = getattr(quote, "fallback_from", None)
        if fallback_from:
            record_provider_attempt(
                quote,
                provider=fallback_from,
                status=PROVIDER_STATUS_FAILED,
                role=PROVIDER_ROLE_ATTEMPTED,
                stock_code=getattr(quote, "code", None),
                market=getattr(quote, "market", None),
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
        log_safe_exception(
            logger,
            "Field-trust finalization failed",
            exc,
            error_code="field_trust_finalize_failed",
            level=logging.DEBUG,
        )
