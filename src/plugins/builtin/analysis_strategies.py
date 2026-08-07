# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Built-in analysis strategy plugins wrapping strategies/ YAML definitions.

Each root YAML under ``strategies/`` and each reserved ``strategies/personas/``
YAML becomes one first-class ``analysis_strategy`` plugin. Content stays in the
legacy YAML files for desktop packaging and author editing; the plugin
lifecycle owns enable/disable and catalog publication.
"""

from __future__ import annotations

import logging
from pathlib import Path

from src.agent.skills.base import Skill, load_skill_from_yaml, load_skills_from_directory
from src.plugins.constants import PLUGIN_APPLICATION_VERSION
from src.plugins.manifest import PluginManifest
from src.plugins.plugin import Plugin
from src.plugins.registry import PluginContext
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger(__name__)

# Keep the same on-disk root used by SkillManager's legacy YAML shim.
_BUILTIN_STRATEGY_YAML_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent / "strategies"
)

BUILTIN_ANALYSIS_STRATEGY_PLUGIN_ID_PREFIX = "builtin.analysis-strategy."


def builtin_analysis_strategy_plugin_id(skill_name: str) -> str:
    """Return the stable plugin id for one built-in strategy skill name."""

    return f"{BUILTIN_ANALYSIS_STRATEGY_PLUGIN_ID_PREFIX}{skill_name}"


def is_builtin_analysis_strategy_plugin_id(plugin_id: str) -> bool:
    """Return whether a plugin id is a packaged built-in analysis strategy."""

    return (
        type(plugin_id) is str
        and plugin_id.startswith(BUILTIN_ANALYSIS_STRATEGY_PLUGIN_ID_PREFIX)
        and len(plugin_id) > len(BUILTIN_ANALYSIS_STRATEGY_PLUGIN_ID_PREFIX)
    )


def _skill_yaml_paths(directory: Path) -> list[Path]:
    """Return deterministic YAML paths for the built-in catalog layout."""

    if not directory.is_dir():
        return []
    paths = sorted(directory.glob("*.yaml")) + sorted(directory.glob("*.yml"))
    personas = directory / "personas"
    if personas.is_dir():
        paths.extend(sorted(personas.glob("*.yaml")))
        paths.extend(sorted(personas.glob("*.yml")))
    return paths


class BuiltinAnalysisStrategyPlugin(Plugin):
    """Register one strategies/ YAML definition through analysis_strategy."""

    def __init__(self, yaml_path: Path, *, skill_name: str | None = None) -> None:
        yaml_path = Path(yaml_path)
        if skill_name is None:
            skill = load_skill_from_yaml(yaml_path)
            skill_name = skill.name
        if type(skill_name) is not str or not skill_name.strip():
            raise ValueError("built-in analysis strategy skill name is required")
        skill_name = skill_name.strip()
        super().__init__(
            PluginManifest.model_validate(
                {
                    "id": builtin_analysis_strategy_plugin_id(skill_name),
                    "name": f"Built-in strategy: {skill_name}",
                    "version": "1.0.0",
                    "minAppVersion": PLUGIN_APPLICATION_VERSION,
                    "description": (
                        "First-class plugin packaging for a built-in natural-language "
                        f"analysis strategy defined in {yaml_path.name}."
                    ),
                    "author": "StockPulse contributors",
                    "permissions": [],
                }
            )
        )
        self._yaml_path = yaml_path
        self._skill_name = skill_name
        self._definition: Skill | None = None

    @property
    def yaml_path(self) -> Path:
        """Return the on-disk YAML definition path for this built-in."""

        return self._yaml_path

    @property
    def skill_name(self) -> str:
        """Return the strategy registration name."""

        return self._skill_name

    def onload(self, context: PluginContext) -> None:
        skill = load_skill_from_yaml(self._yaml_path)
        if skill.name != self._skill_name:
            raise ValueError(
                f"built-in strategy YAML name {skill.name!r} does not match "
                f"plugin skill name {self._skill_name!r}"
            )
        # Validation requires a string source; content is detached at register.
        skill.source = "builtin"
        skill.enabled = False
        context.register(
            "analysis_strategy",
            skill.name,
            skill,
            contract_version="1",
            metadata={
                "builtin": True,
                "yaml_path": str(self._yaml_path),
            },
        )
        self._definition = skill

    def onunload(self) -> None:
        self._definition = None


def get_builtin_analysis_strategy_plugins(
    strategies_dir: Path | None = None,
) -> tuple[BuiltinAnalysisStrategyPlugin, ...]:
    """Discover built-in strategy plugins from the strategies/ YAML catalog."""

    directory = (
        Path(strategies_dir) if strategies_dir is not None else _BUILTIN_STRATEGY_YAML_DIR
    )
    if not directory.is_dir():
        logger.warning("Built-in strategy YAML directory not found: %s", directory)
        return ()

    plugins: list[BuiltinAnalysisStrategyPlugin] = []
    seen_names: set[str] = set()
    for yaml_path in _skill_yaml_paths(directory):
        try:
            skill = load_skill_from_yaml(yaml_path)
        except Exception as exc:  # broad-exception: fallback_recorded - isolate bad YAML.
            log_safe_exception(
                logger,
                "Built-in strategy plugin discovery failed",
                exc,
                error_code="builtin_analysis_strategy_yaml_load_failed",
                level=logging.WARNING,
                context={"skill_file": yaml_path.name},
            )
            continue
        if skill.name in seen_names:
            logger.warning(
                "Skipping duplicate built-in strategy name %s from %s",
                skill.name,
                yaml_path,
            )
            continue
        seen_names.add(skill.name)
        plugins.append(
            BuiltinAnalysisStrategyPlugin(yaml_path, skill_name=skill.name)
        )

    logger.info(
        "Discovered %d built-in analysis strategy plugins from %s",
        len(plugins),
        directory,
    )
    return tuple(plugins)


def list_builtin_analysis_strategy_names(
    strategies_dir: Path | None = None,
) -> tuple[str, ...]:
    """Return sorted skill names owned by built-in strategy plugins."""

    directory = (
        Path(strategies_dir) if strategies_dir is not None else _BUILTIN_STRATEGY_YAML_DIR
    )
    try:
        skills = load_skills_from_directory(directory)
    except Exception as exc:  # broad-exception: fallback_recorded - missing/invalid strategy YAML should not break plugin discovery.
        log_safe_exception(
            logger,
            "Built-in strategy name listing failed",
            exc,
            error_code="builtin_analysis_strategy_name_list_failed",
            level=logging.WARNING,
            context={"strategies_dir": str(directory)},
        )
        return ()
    return tuple(sorted({skill.name for skill in skills if skill.name}))


__all__ = [
    "BUILTIN_ANALYSIS_STRATEGY_PLUGIN_ID_PREFIX",
    "BuiltinAnalysisStrategyPlugin",
    "builtin_analysis_strategy_plugin_id",
    "get_builtin_analysis_strategy_plugins",
    "is_builtin_analysis_strategy_plugin_id",
    "list_builtin_analysis_strategy_names",
]
