# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Default-off, fail-soft collection of layered memory observations (#1118).

When ``LAYERED_MEMORY_COLLECTION_ENABLED`` is false or missing, this module
returns without initializing a repository. Storage failures are logged and
never abort analysis. There is no production prompt injection and no user CRUD.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
import math
from typing import Any, Mapping, Optional

from src.agent.memory_governance import LayeredMemoryPolicy, PrincipalMemoryLifecycle
from src.agent.memory_layers import MemoryObservation
from src.agent.protocols import normalize_decision_signal
from src.repositories.layered_memory_repo import (
    DurableLayeredMemoryStore,
    LayeredMemoryRepository,
)
from src.schemas.approvals import LOCAL_ADMIN_OWNER
from src.schemas.layered_memory_persist import admit_layered_observation_mapping
from src.schemas.memory_provenance import PROVENANCE_SOURCE_SYSTEM_RESOLVE
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

LAYERED_MEMORY_OPERATOR_PRINCIPAL = LOCAL_ADMIN_OWNER


def is_layered_memory_collection_enabled(config: Any = None) -> bool:
    return (
        config is not None
        and getattr(config, "layered_memory_collection_enabled", None) is True
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _finite_price(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(price) or price <= 0.0:
        return None
    return price


def _observation_from_admitted_mapping(admitted: Mapping[str, Any]) -> MemoryObservation:
    """Build the agent-layer observation from a schema-admitted mapping."""
    return MemoryObservation(
        principal_id=admitted["principal_id"],
        analysis_history_id=admitted["analysis_history_id"],
        stock_code=admitted["stock_code"],
        observed_at=admitted["observed_at"],
        expires_at=admitted.get("expires_at"),
        signal=admitted["signal"],
        sentiment_score=admitted["sentiment_score"],
        price_at_analysis=admitted["price_at_analysis"],
        outcome_id=admitted.get("outcome_id"),
        outcome_horizon_days=admitted.get("outcome_horizon_days"),
        evaluated_at=admitted.get("evaluated_at"),
        was_correct=admitted.get("was_correct"),
        provenance_source=admitted.get("provenance_source"),
        actor_id=admitted.get("actor_id"),
    )


def _finite_score(value: Any) -> Optional[float]:
    if isinstance(value, bool) or value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(score) or not 0.0 <= score <= 100.0:
        return None
    return score


class LayeredMemoryCollectionService:
    def __init__(
        self,
        repository: Optional[LayeredMemoryRepository] = None,
        *,
        config: Any = None,
    ) -> None:
        self._repository = repository
        self._config = config

    def _get_repository(self) -> LayeredMemoryRepository:
        if self._repository is None:
            self._repository = LayeredMemoryRepository()
        return self._repository

    def _lifecycle(self, config: Any) -> PrincipalMemoryLifecycle:
        return PrincipalMemoryLifecycle(
            policy=LayeredMemoryPolicy.from_config(config),
            store=DurableLayeredMemoryStore(self._get_repository()),
        )

    def collect_observation(
        self,
        payload: Mapping[str, Any],
        *,
        config: Any = None,
        now: Optional[str] = None,
    ) -> Optional[MemoryObservation]:
        cfg = config if config is not None else self._config
        if not is_layered_memory_collection_enabled(cfg):
            return None
        try:
            admitted, _stamp = admit_layered_observation_mapping(
                payload,
                provenance_source=PROVENANCE_SOURCE_SYSTEM_RESOLVE,
                actor_id=None,
            )
            observation = _observation_from_admitted_mapping(admitted)
            lifecycle = self._lifecycle(cfg)
            if not lifecycle.has_consent(observation.principal_id):
                return None
            return lifecycle.put(observation, now=now)
        except Exception as exc:  # broad-exception: fallback_recorded - layered collect must never fail analysis
            log_safe_exception(
                logger,
                "layered_memory_collect_failed",
                exc,
                error_code="layered_memory_collect_failed",
                context={
                    "principal_id": payload.get("principal_id")
                    if isinstance(payload, Mapping)
                    else None,
                    "analysis_history_id": payload.get("analysis_history_id")
                    if isinstance(payload, Mapping)
                    else None,
                },
            )
            return None

    def collect_from_analysis_result(
        self,
        *,
        result: Any,
        analysis_history_id: int,
        config: Any = None,
        now: Optional[str] = None,
        principal_id: str = LAYERED_MEMORY_OPERATOR_PRINCIPAL,
    ) -> Optional[MemoryObservation]:
        cfg = config if config is not None else self._config
        if not is_layered_memory_collection_enabled(cfg):
            return None
        try:
            stock_code = str(getattr(result, "code", "") or "").strip()
            price = _finite_price(getattr(result, "current_price", None))
            score = _finite_score(getattr(result, "sentiment_score", None))
            if (
                type(analysis_history_id) is not int
                or analysis_history_id <= 0
                or not stock_code
                or price is None
                or score is None
            ):
                return None
            payload = {
                "principal_id": principal_id,
                "analysis_history_id": analysis_history_id,
                "stock_code": stock_code,
                "observed_at": now or _utc_now_iso(),
                "expires_at": None,
                "signal": normalize_decision_signal(getattr(result, "decision_type", None)),
                "sentiment_score": score,
                "price_at_analysis": price,
            }
            return self.collect_observation(payload, config=cfg, now=now)
        except Exception as exc:  # broad-exception: fallback_recorded - result projection must never fail analysis
            log_safe_exception(
                logger,
                "layered_memory_collect_from_result_failed",
                exc,
                error_code="layered_memory_collect_from_result_failed",
                context={"analysis_history_id": analysis_history_id},
            )
            return None


def try_collect_layered_memory_observation(
    *,
    result: Any,
    analysis_history_id: int,
    config: Any = None,
    now: Optional[str] = None,
) -> Optional[MemoryObservation]:
    if not is_layered_memory_collection_enabled(config):
        return None
    try:
        return LayeredMemoryCollectionService(config=config).collect_from_analysis_result(
            result=result,
            analysis_history_id=analysis_history_id,
            config=config,
            now=now,
        )
    except Exception as exc:  # broad-exception: fallback_recorded - helper must never alter analysis control flow
        log_safe_exception(
            logger,
            "layered_memory_collect_helper_failed",
            exc,
            error_code="layered_memory_collect_helper_failed",
            context={"analysis_history_id": analysis_history_id},
        )
        return None


__all__ = [
    "LAYERED_MEMORY_OPERATOR_PRINCIPAL",
    "LayeredMemoryCollectionService",
    "is_layered_memory_collection_enabled",
    "try_collect_layered_memory_observation",
]
