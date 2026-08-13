# -*- coding: utf-8 -*-
"""
SkillRouter — rule-based skill selection.

Selects which trading skills to apply based on:
1. User-explicit request (highest priority)
2. Market regime detection from technical data in ``AgentContext``
3. Centralised default fallback
"""

from __future__ import annotations

import logging
from typing import List, Optional

from src.agent.protocols import AgentContext
from src.agent.skills.defaults import (
    get_default_router_skill_ids,
    get_regime_skill_ids,
)
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


class SkillRouter:
    """Select applicable skills for a given analysis context."""

    def __init__(self, *, skill_manager=None, config=None) -> None:
        self._skill_manager = skill_manager
        self._config = config

    def select_skills(
        self,
        ctx: AgentContext,
        max_count: int = 3,
    ) -> List[str]:
        requested_skills = ctx.meta.get("skills_requested") or ctx.meta.get("strategies_requested", [])
        if requested_skills:
            logger.info("[SkillRouter] user-requested skills: %s", requested_skills)
            return requested_skills[:max_count]

        routing_mode = self._get_routing_mode(self._config)
        if routing_mode == "manual":
            selected = self._get_manual_skills(
                max_count=max_count,
                config=self._config,
                skill_manager=self._skill_manager,
            )
            logger.info("[SkillRouter] manual mode — using skills: %s", selected)
            return selected

        available_skills = self._get_available_skills(self._skill_manager)
        skill_catalog = available_skills or None
        available_ids = {skill.name for skill in available_skills}
        regime = self._detect_regime(ctx)
        if regime:
            selected = get_regime_skill_ids(
                regime,
                skill_catalog,
                max_count=max_count,
                available_skill_ids=available_ids or None,
            )
            if selected:
                logger.info("[SkillRouter] regime=%s -> skills: %s", regime, selected)
                return selected

        default_skills = get_default_router_skill_ids(
            skill_catalog,
            max_count=max_count,
            available_skill_ids=available_ids or None,
        )
        logger.info("[SkillRouter] using default skills: %s", default_skills)
        return default_skills

    def select_strategies(
        self,
        ctx: AgentContext,
        max_count: int = 3,
    ) -> List[str]:
        """Compatibility wrapper for legacy strategy-based callers."""
        return self.select_skills(ctx, max_count=max_count)

    def _detect_regime(self, ctx: AgentContext) -> Optional[str]:
        """Return an actionable regime label, or None when unknown/unavailable.

        Uses the shared explainable MarketRegimeService so routing and analysis
        share the same rule evidence. ``unknown`` never forces a skill route.
        ``sector_hot`` remains a soft meta hint for skill tags when present.
        """
        try:
            from src.services.market_regime_service import (
                MARKET_REGIME_CONTEXT_KEY,
                MarketRegimeService,
                is_actionable_regime,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - Router must still function if regime import fails.
            log_safe_exception(
                logger,
                "Market regime service unavailable for skill routing",
                exc,
                error_code="agent_regime_service_import_failed",
                level=logging.WARNING,
            )
            if ctx.meta.get("sector_hot"):
                return "sector_hot"
            return None

        try:
            service = MarketRegimeService(config=self._config)
            regime_context = service.build_from_agent_context(ctx)
            if isinstance(regime_context, dict):
                ctx.meta[MARKET_REGIME_CONTEXT_KEY] = regime_context
                regime = str(regime_context.get("regime") or "").strip().lower()
                if is_actionable_regime(regime):
                    return regime
        except Exception as exc:  # broad-exception: fallback_recorded - Regime detection must not break routing.
            log_safe_exception(
                logger,
                "Market regime detection failed during skill routing",
                exc,
                error_code="agent_regime_detect_failed",
                level=logging.WARNING,
            )

        if ctx.meta.get("sector_hot"):
            return "sector_hot"
        return None

    @staticmethod
    def _get_routing_mode(config=None) -> str:
        try:
            if config is None:
                from src.application_services import get_application_services

                config = get_application_services().config
            return getattr(config, "agent_skill_routing", "auto")
        except Exception as exc:  # broad-exception: fallback_recorded - Config lookup failures are logged before automatic routing is selected.
            log_safe_exception(
                logger,
                "Failed to get routing mode; using automatic routing",
                exc,
                error_code="agent_skill_routing_mode_failed",
                level=logging.WARNING,
            )
            return "auto"

    @staticmethod
    def _get_available_ids(skill_manager=None) -> set:
        return {
            skill.name
            for skill in SkillRouter._get_available_skills(skill_manager)
        }

    @staticmethod
    def _get_available_skills(skill_manager=None) -> list:
        try:
            if skill_manager is not None:
                return list(skill_manager.list_skills())
            from src.agent.factory import get_skill_manager

            sm = get_skill_manager()
            return list(sm.list_skills())
        except Exception as exc:  # broad-exception: fallback_recorded - Catalog lookup failures are logged before the optional router returns no skills.
            log_safe_exception(
                logger,
                "Failed to get available skills",
                exc,
                error_code="agent_available_skills_lookup_failed",
                level=logging.WARNING,
            )
            return []

    @classmethod
    def _get_manual_skills(
        cls,
        max_count: int,
        *,
        config=None,
        skill_manager=None,
    ) -> List[str]:
        configured: List[str] = []
        try:
            if config is None:
                from src.application_services import get_application_services

                config = get_application_services().config
            configured = [
                skill_id
                for skill_id in getattr(config, "agent_skills", []) or []
                if isinstance(skill_id, str) and skill_id
            ]
        except Exception as exc:  # broad-exception: fallback_recorded - Manual config failures are logged before central defaults are resolved.
            log_safe_exception(
                logger,
                "Failed to get manual skills config",
                exc,
                error_code="agent_manual_skill_config_failed",
                level=logging.WARNING,
            )
            configured = []

        available_skills = cls._get_available_skills(skill_manager)
        skill_catalog = available_skills or None
        available = {skill.name for skill in available_skills}
        selected = [skill_id for skill_id in configured if skill_id in available][:max_count]
        if selected:
            return selected

        return get_default_router_skill_ids(
            skill_catalog,
            max_count=max_count,
            available_skill_ids=available or None,
        )


StrategyRouter = SkillRouter
_DEFAULT_STRATEGIES = tuple(get_default_router_skill_ids())
_DEFAULT_SKILLS = _DEFAULT_STRATEGIES
