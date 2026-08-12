# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Read-only runtime projection for the Data Sources Hub.

Builds a sanitized, JSON-serializable view of the live ``DataFetcherManager``
routing chain, process-local provider health, and daily-cache counters.

Rules:
- Observe the manager that actually serves this process; never invent a green
  status from a static catalog.
- Probe failures and missing owners are explicit (``source_state`` / per-provider
  ``health_status``). Availability is never defaulted to true on failure.
- This endpoint does not connect to third-party APIs, write config, or open
  circuits; it only reads process-local registration, availability probes, and
  already-recorded health windows.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.utils.sanitize import log_safe_exception, sanitize_diagnostic_text

logger = logging.getLogger(__name__)

SCHEMA_VERSION = "data_provider_runtime_status_v1"

# Markets shown on the Hub overview. Crypto stays advanced/out of band for v1.
OVERVIEW_MARKETS: tuple[str, ...] = ("cn", "hk", "us")

# Credentialed or specialist feeds treated as optional enhancers in the Hub.
# Keyless scrapers remain baseline providers.
ENHANCER_PROVIDER_IDS = frozenset(
    {
        "tushare",
        "tickflow",
        "finnhub",
        "alphavantage",
        "longbridge",
        "alphasift",
    }
)

# Provider ids whose configuration directory keys live under Data Sources.
# Used only for role hints; runtime identity still comes from the live registry.
CONFIG_DIRECTORY_PROVIDER_IDS = frozenset(
    {"tushare", "tickflow", "pytdx", "alphasift"}
)

ManagerFactory = Callable[[], Any]


class DataProviderRuntimeNotInitialized(RuntimeError):
    """The process has no live DataFetcherManager to project."""

    def __init__(self, error_code: str = "data_runtime_not_initialized") -> None:
        super().__init__(error_code)
        self.error_code = error_code


def build_data_provider_runtime_status(
    *,
    manager: Any | None = None,
    manager_factory: ManagerFactory | None = None,
    clock: Callable[[], datetime] | None = None,
) -> Dict[str, Any]:
    """Return the Hub runtime projection for the live provider owner.

    When ``manager`` is omitted the installed application services are resolved
    first. Construction of a substitute manager is never performed here so the
    projection cannot describe an isolated owner that serves no caller.
    """

    as_of = (clock or (lambda: datetime.now(timezone.utc)))().isoformat()
    try:
        live_manager = (
            manager
            if manager is not None
            else (manager_factory or _resolve_live_manager)()
        )
    except DataProviderRuntimeNotInitialized as exc:
        return _empty_status(
            as_of=as_of,
            source_state="not_initialized",
            error_code=exc.error_code,
            error_message=(
                "Data provider runtime is not initialized in this process. "
                "Open the API/analysis service so the live manager can be observed."
            ),
        )
    except Exception as exc:  # broad-exception: fallback_recorded - expose status probe failure
        log_safe_exception(
            logger,
            "Data provider runtime status resolve failed",
            exc,
            error_code="data_provider_status_resolve_failed",
        )
        return _empty_status(
            as_of=as_of,
            source_state="error",
            error_code="data_provider_status_resolve_failed",
            error_message=sanitize_diagnostic_text(
                str(exc) or "Failed to resolve data provider runtime",
                max_length=240,
            ),
        )

    try:
        return _project_manager(live_manager, as_of=as_of)
    except Exception as exc:  # broad-exception: fallback_recorded - never fabricate healthy
        log_safe_exception(
            logger,
            "Data provider runtime status projection failed",
            exc,
            error_code="data_provider_status_projection_failed",
        )
        return _empty_status(
            as_of=as_of,
            source_state="error",
            error_code="data_provider_status_projection_failed",
            error_message=sanitize_diagnostic_text(
                str(exc) or "Failed to project data provider runtime",
                max_length=240,
            ),
        )


def _empty_status(
    *,
    as_of: str,
    source_state: str,
    error_code: str,
    error_message: str,
) -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of,
        "partial": True,
        "source_state": source_state,
        "error_code": error_code,
        "error_message": error_message,
        "markets": [],
        "providers": [],
        "cache": None,
    }


def _resolve_live_manager() -> Any:
    """Return the process-serving DataFetcherManager or raise explicitly."""

    from src.application_services import get_installed_application_services

    services = get_installed_application_services()
    manager = None if services is None else services.data_fetcher_manager
    if manager is None and services is not None:
        # Accessing plugin_manager may complete composition-root auto-bind of
        # the manager that analysis and stock services already share.
        try:
            _ = services.plugin_manager
        except Exception as exc:  # broad-exception: fallback_recorded - try agent manager next
            log_safe_exception(
                logger,
                "Application plugin manager access failed during data status resolve",
                exc,
                error_code="data_provider_status_plugin_manager_failed",
                level=logging.DEBUG,
            )
        manager = services.data_fetcher_manager
    if manager is None:
        from src.agent.tools.data_tools import active_fetcher_manager

        manager = active_fetcher_manager()
    if manager is None:
        raise DataProviderRuntimeNotInitialized("data_runtime_not_initialized")
    return manager


def _project_manager(manager: Any, *, as_of: str) -> Dict[str, Any]:
    fetchers = list(manager._get_fetchers_snapshot())
    name_to_id = _provider_name_to_id(manager, fetchers)
    health_by_key = _health_index(manager)
    providers: List[Dict[str, Any]] = []
    for fetcher in fetchers:
        providers.append(
            _project_provider(
                manager,
                fetcher=fetcher,
                provider_id=name_to_id.get(fetcher.name, _slug_provider_name(fetcher.name)),
                health_by_key=health_by_key,
            )
        )

    markets = [
        _project_market_chain(
            manager,
            market=market,
            fetchers=fetchers,
            name_to_id=name_to_id,
            health_by_key=health_by_key,
        )
        for market in OVERVIEW_MARKETS
    ]

    # Annotate primary/fallback membership after chains are known.
    primary_for: Dict[str, List[str]] = {}
    fallback_for: Dict[str, List[str]] = {}
    for chain in markets:
        chain_key = f"{chain['data_type']}:{chain['market']}"
        primary_id = chain.get("primary_provider_id")
        if primary_id:
            primary_for.setdefault(primary_id, []).append(chain_key)
        for fallback_id in chain.get("fallback_provider_ids") or []:
            fallback_for.setdefault(fallback_id, []).append(chain_key)
    for entry in providers:
        pid = entry["provider_id"]
        entry["is_primary_for"] = sorted(primary_for.get(pid, []))
        entry["is_fallback_for"] = sorted(fallback_for.get(pid, []))

    providers.sort(
        key=lambda item: (
            0 if item.get("role") == "baseline" else 1 if item.get("role") == "enhancer" else 2,
            item.get("static_priority") is None,
            item.get("static_priority") if item.get("static_priority") is not None else 0,
            item["provider_id"],
        )
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of,
        "partial": False,
        "source_state": "ok",
        "error_code": None,
        "error_message": None,
        "markets": markets,
        "providers": providers,
        "cache": _project_cache(manager),
    }


def _provider_name_to_id(manager: Any, fetchers: Sequence[Any]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    builtin = getattr(manager, "_BUILTIN_DATA_PROVIDER_IDS", None) or {}
    if isinstance(builtin, dict):
        for name, provider_id in builtin.items():
            mapping[str(name)] = str(provider_id)
    for fetcher in fetchers:
        registration = manager._provider_plugin_registration(fetcher)
        if registration is not None:
            mapping[str(fetcher.name)] = str(registration.provider_id)
        elif fetcher.name not in mapping:
            mapping[str(fetcher.name)] = _slug_provider_name(fetcher.name)
    return mapping


def _slug_provider_name(name: str) -> str:
    cleaned = "".join(
        ch.lower() if ch.isalnum() else "_"
        for ch in str(name or "").removesuffix("Fetcher")
    ).strip("_")
    return cleaned or "unknown"


def _health_index(manager: Any) -> Dict[str, Dict[str, Any]]:
    try:
        report = manager.get_daily_provider_health_report()
    except Exception as exc:  # broad-exception: fallback_recorded - health optional
        log_safe_exception(
            logger,
            "Daily provider health report unavailable",
            exc,
            error_code="data_provider_health_report_unavailable",
            level=logging.DEBUG,
        )
        return {}
    indexed: Dict[str, Dict[str, Any]] = {}
    for item in report.get("providers") or []:
        market = str(item.get("market") or "")
        provider_name = str(item.get("provider") or "")
        if not market or not provider_name:
            continue
        indexed[f"daily_data:{market}:{provider_name}"] = item
    return indexed


def _project_provider(
    manager: Any,
    *,
    fetcher: Any,
    provider_id: str,
    health_by_key: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    registration = manager._provider_plugin_registration(fetcher)
    markets = sorted(
        registration.markets
        if registration is not None
        else (getattr(manager, "_DAILY_MARKET_FETCHER_SUPPORT", {}) or {}).get(
            fetcher.name, ()
        )
        or ()
    )
    capabilities = sorted(
        registration.capabilities
        if registration is not None
        else ("daily_data",)
    )
    role = _role_for(provider_id)
    static_priority = manager._provider_priority(fetcher)

    availability_probe = _probe_availability(manager, fetcher)
    configured = _configured_state(fetcher, provider_id=provider_id, role=role)

    # Aggregate process-local health across overview markets for this provider.
    market_health = [
        health_by_key[key]
        for key in (
            f"daily_data:{market}:{fetcher.name}" for market in OVERVIEW_MARKETS
        )
        if key in health_by_key
    ]
    health_status, health_score, circuit_state, sample_count = _aggregate_health(
        market_health,
        available=availability_probe["available"],
        configured=configured,
        probe_failed=availability_probe["probe_failed"],
        probe_error=availability_probe["error_message"],
    )

    last_success = _max_epoch([item.get("last_success_time") for item in market_health])
    last_failure = _max_epoch([item.get("last_failure_time") for item in market_health])
    failure_reason = availability_probe["error_message"]
    if failure_reason is None and health_status in {"degraded", "unavailable", "circuit_open"}:
        failure_reason = _health_failure_reason(market_health, health_status)

    return {
        "provider_id": provider_id,
        "display_name": sanitize_diagnostic_text(
            str(getattr(fetcher, "name", provider_id)),
            max_length=120,
        ),
        "role": role,
        "markets": list(markets),
        "capabilities": list(capabilities),
        "configured": configured,
        "available": availability_probe["available"],
        "health_status": health_status,
        "health_score": health_score,
        "circuit_state": circuit_state,
        "sample_count": sample_count,
        "static_priority": static_priority,
        "last_success_at": _epoch_to_iso(last_success),
        "last_failure_at": _epoch_to_iso(last_failure),
        "failure_reason": failure_reason,
        "is_primary_for": [],
        "is_fallback_for": [],
        "config_directory": provider_id in CONFIG_DIRECTORY_PROVIDER_IDS,
    }


def _project_market_chain(
    manager: Any,
    *,
    market: str,
    fetchers: Sequence[Any],
    name_to_id: Dict[str, str],
    health_by_key: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    market_fetchers = manager._filter_daily_fetchers_for_market(list(fetchers), market)
    # Filter capability/availability with the Hub probe so probe exceptions become
    # explicit failed rows rather than aborting the whole projection. The manager
    # helper can raise when tests (or future probes) surface hard failures.
    capability_fetchers = []
    for fetcher in market_fetchers:
        declared = True
        try:
            declared = bool(manager._provider_supports_capability(fetcher, "daily_data"))
        except Exception:  # broad-exception: fallback_recorded - treat as unsupported
            declared = False
        if not declared:
            continue
        probe = _probe_availability(manager, fetcher)
        if probe["probe_failed"] or probe["available"] is False:
            continue
        capability_fetchers.append(fetcher)
    ordered = manager._order_daily_fetchers(capability_fetchers, market)
    ordered_ids = [
        name_to_id.get(fetcher.name, _slug_provider_name(fetcher.name))
        for fetcher in ordered
    ]

    primary_id: Optional[str] = None
    primary_reason: Optional[str] = None
    for fetcher, provider_id in zip(ordered, ordered_ids):
        probe = _probe_availability(manager, fetcher)
        health = health_by_key.get(f"daily_data:{market}:{fetcher.name}")
        circuit_open = bool(health and health.get("state") == "open" and not health.get("available", True))
        if probe["probe_failed"]:
            continue
        if probe["available"] is False:
            continue
        if circuit_open:
            continue
        # Prefer a provider with observed success when peers share the slot.
        if primary_id is None:
            primary_id = provider_id
            if health and int(health.get("sample_count") or 0) > 0:
                primary_reason = "first_eligible_with_health"
            else:
                primary_reason = "first_eligible_unobserved"
            # Keep first eligible; do not skip to later providers without evidence.
            break

    if primary_id is None and ordered_ids:
        # Chain exists but every entry is unavailable or probe-failed.
        primary_reason = "no_eligible_provider"
    elif not ordered_ids:
        primary_reason = "no_registered_provider"

    fallback_ids = [pid for pid in ordered_ids if pid != primary_id]

    quality = "unknown"
    if not ordered_ids:
        quality = "unavailable"
    elif primary_id is None:
        quality = "unavailable"
    elif primary_reason == "first_eligible_with_health":
        health = None
        for fetcher, provider_id in zip(ordered, ordered_ids):
            if provider_id == primary_id:
                health = health_by_key.get(f"daily_data:{market}:{fetcher.name}")
                break
        if health is not None:
            score = float(health.get("health_score") or 0.0)
            error_rate = float(health.get("error_rate") or 0.0)
            if health.get("state") == "open" or score < 40.0 or error_rate >= 0.5:
                quality = "degraded"
            else:
                quality = "ok"
        else:
            quality = "unknown"
    else:
        quality = "unknown"

    return {
        "market": market,
        "data_type": "daily_data",
        "ordered_provider_ids": ordered_ids,
        "primary_provider_id": primary_id,
        "fallback_provider_ids": fallback_ids,
        "primary_selection": primary_reason,
        "quality": quality,
        "as_of": None,
    }


def _project_cache(manager: Any) -> Dict[str, Any]:
    try:
        stats = manager.get_daily_cache_stats()
        fetch_mode = manager._get_daily_data_cache().fetch_mode.value
    except Exception as exc:  # broad-exception: fallback_recorded - cache optional
        log_safe_exception(
            logger,
            "Daily cache stats unavailable",
            exc,
            error_code="data_provider_cache_stats_unavailable",
            level=logging.DEBUG,
        )
        return {
            "enabled": None,
            "fetch_mode": None,
            "hits": None,
            "misses": None,
            "stale_hits": None,
            "writes": None,
            "quality": "unknown",
            "note": "cache_stats_unavailable",
        }

    hits = int(stats.get("hits") or 0)
    misses = int(stats.get("misses") or 0)
    stale_hits = int(stats.get("stale_hits") or 0)
    writes = int(stats.get("writes") or 0)
    if fetch_mode == "local_only":
        quality = "local_only"
    elif stale_hits > 0 and stale_hits >= hits:
        quality = "stale"
    elif hits > 0 or writes > 0:
        quality = "active"
    elif misses > 0:
        quality = "cold"
    else:
        quality = "idle"

    return {
        "enabled": True,
        "fetch_mode": fetch_mode,
        "hits": hits,
        "misses": misses,
        "stale_hits": stale_hits,
        "writes": writes,
        "quality": quality,
        "note": None,
    }


def _role_for(provider_id: str) -> str:
    if provider_id in ENHANCER_PROVIDER_IDS:
        return "enhancer"
    if provider_id == "pytdx":
        return "specialist"
    return "baseline"


def _configured_state(
    fetcher: Any,
    *,
    provider_id: str,
    role: str,
) -> Optional[bool]:
    """Return credential/config presence without revealing secret values.

    Keyless baselines return ``None`` (not applicable). Enhancers/specialists
    use public availability or known credential attributes only.
    """

    if role == "baseline":
        return None

    if provider_id == "tushare":
        return bool(getattr(fetcher, "_api", None) is not None)
    if provider_id == "tickflow":
        return bool(str(getattr(fetcher, "api_key", "") or "").strip())
    if provider_id in {"finnhub", "alphavantage"}:
        return bool(str(getattr(fetcher, "_api_key", "") or "").strip())
    if provider_id == "longbridge":
        # Longbridge may use several credential shapes; availability is the
        # honest configured signal when present.
        probe = getattr(fetcher, "is_available", None)
        if callable(probe):
            try:
                return bool(probe())
            except Exception:  # broad-exception: fallback_recorded - treat as unconfigured
                return False
        return None
    if provider_id == "pytdx":
        host = str(getattr(fetcher, "host", "") or "").strip()
        servers = getattr(fetcher, "servers", None)
        return bool(host) or bool(servers)
    return None


def _probe_availability(manager: Any, fetcher: Any) -> Dict[str, Any]:
    try:
        available = bool(manager._is_fetcher_available(fetcher, capability="daily_data"))
        return {
            "available": available,
            "probe_failed": False,
            "error_message": None if available else "provider_availability_probe_false",
        }
    except Exception as exc:  # broad-exception: fallback_recorded - never invent available
        log_safe_exception(
            logger,
            "Data provider availability probe failed during status projection",
            exc,
            error_code="data_provider_availability_probe_failed",
            level=logging.DEBUG,
            context={"provider": getattr(fetcher, "name", "unknown")},
        )
        return {
            "available": False,
            "probe_failed": True,
            "error_message": sanitize_diagnostic_text(
                str(exc) or "availability_probe_failed",
                max_length=200,
            ),
        }


def _aggregate_health(
    market_health: Sequence[Dict[str, Any]],
    *,
    available: Optional[bool],
    configured: Optional[bool],
    probe_failed: bool,
    probe_error: Optional[str],
) -> tuple[str, Optional[float], Optional[str], int]:
    if probe_failed:
        return "failed", None, None, 0
    if configured is False:
        return "not_configured", None, None, 0
    if available is False:
        # Prefer circuit_open when health proves it.
        for item in market_health:
            if item.get("state") == "open":
                return "circuit_open", _safe_float(item.get("health_score")), "open", int(
                    item.get("sample_count") or 0
                )
        return "unavailable", None, None, 0

    if not market_health:
        # Registered and available, but no observed samples yet — not healthy.
        return "unknown", None, None, 0

    sample_count = sum(int(item.get("sample_count") or 0) for item in market_health)
    if sample_count <= 0:
        return "unknown", None, None, 0

    # Prefer the worst circuit state across markets.
    states = [str(item.get("state") or "closed") for item in market_health]
    if "open" in states:
        circuit_state = "open"
    elif "half_open" in states:
        circuit_state = "half_open"
    else:
        circuit_state = "closed"

    scores = [
        float(item["health_score"])
        for item in market_health
        if item.get("health_score") is not None
    ]
    health_score = min(scores) if scores else None
    error_rates = [
        float(item["error_rate"])
        for item in market_health
        if item.get("error_rate") is not None
    ]
    max_error_rate = max(error_rates) if error_rates else 0.0

    if circuit_state == "open":
        return "circuit_open", health_score, circuit_state, sample_count
    if circuit_state == "half_open":
        return "degraded", health_score, circuit_state, sample_count
    if health_score is not None and health_score < 50.0:
        return "degraded", health_score, circuit_state, sample_count
    if max_error_rate >= 0.35:
        return "degraded", health_score, circuit_state, sample_count
    return "healthy", health_score, circuit_state, sample_count


def _health_failure_reason(
    market_health: Sequence[Dict[str, Any]],
    health_status: str,
) -> Optional[str]:
    if health_status == "circuit_open":
        for item in market_health:
            remaining = item.get("cooldown_remaining_seconds")
            if remaining:
                return sanitize_diagnostic_text(
                    f"circuit_open cooldown_remaining_seconds={remaining}",
                    max_length=160,
                )
        return "circuit_open"
    if health_status == "degraded":
        for item in market_health:
            score = item.get("health_score")
            error_rate = item.get("error_rate")
            if score is not None or error_rate is not None:
                return sanitize_diagnostic_text(
                    f"degraded health_score={score} error_rate={error_rate}",
                    max_length=160,
                )
        return "degraded"
    if health_status == "unavailable":
        return "provider_unavailable"
    return None


def _max_epoch(values: Sequence[Any]) -> Optional[float]:
    numbers: List[float] = []
    for value in values:
        if value is None:
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            numbers.append(number)
    return max(numbers) if numbers else None


def _epoch_to_iso(value: Optional[float]) -> Optional[str]:
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(float(value), tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
