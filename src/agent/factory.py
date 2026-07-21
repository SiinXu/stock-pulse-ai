# -*- coding: utf-8 -*-
"""Backward-compatible facade for agent assembly.

Executor and registry assembly live in :mod:`src.agent.runtime_assembly` so
the native runtime can depend on that leaf without reaching back into this
factory. Existing imports, patch points, and cache-reset hooks remain available
from this module.
"""

import sys
from types import ModuleType
from typing import List, Optional

from src.agent import runtime_assembly as _runtime_assembly
from src.config import Config


def build_agent_runtime(
    config: Optional[Config] = None,
    skills: Optional[List[str]] = None,
):
    """Return the default runtime adapter behind the vendor-neutral contract.

    Thin assembly seam (AR-PY-01): always returns the native adapter and
    does not change any default execution behaviour. It intentionally has no
    experimental runtime selector; the PydanticAI executable POC is constructed
    directly only by tests and evidence harnesses. Existing callers of
    ``build_agent_executor`` are unaffected.
    """
    from src.agent.runtime.native_adapter import NativeRuntimeAdapter

    return NativeRuntimeAdapter(config=config, skills=skills)


_FORWARDED_ASSEMBLY_NAMES = frozenset(
    {
        "SkillPromptState",
        "_SENTINEL",
        "_SKILL_MANAGER_CUSTOM_DIR",
        "_SKILL_MANAGER_PROTOTYPE",
        "_TOOL_REGISTRY",
        "_build_orchestrator",
        "_coerce_config_int",
        "_normalize_skill_ids",
        "_resolve_selected_skill_ids",
        "_should_use_legacy_default_prompt",
        "build_agent_executor",
        "build_executor",
        "get_skill_manager",
        "get_tool_registry",
        "resolve_skill_prompt_state",
    }
)
__all__ = tuple(
    sorted(
        {"build_agent_runtime"}
        | {name for name in _FORWARDED_ASSEMBLY_NAMES if not name.startswith("_")}
    )
)


class _FactoryFacadeModule(ModuleType):
    """Keep legacy module writes and patches attached to leaf-owned state."""

    def __getattr__(self, name: str):
        """Read a legacy assembly symbol from the leaf module."""
        if name in _FORWARDED_ASSEMBLY_NAMES:
            return getattr(_runtime_assembly, name)
        raise AttributeError(f"module {self.__name__!r} has no attribute {name!r}")

    def __setattr__(self, name: str, value) -> None:
        """Write a legacy assembly symbol through to the leaf module."""
        if name in _FORWARDED_ASSEMBLY_NAMES:
            setattr(_runtime_assembly, name, value)
            return
        super().__setattr__(name, value)

    def __delattr__(self, name: str) -> None:
        """Delete a legacy assembly symbol from the leaf module."""
        if name in _FORWARDED_ASSEMBLY_NAMES:
            delattr(_runtime_assembly, name)
            return
        super().__delattr__(name)


sys.modules[__name__].__class__ = _FactoryFacadeModule
