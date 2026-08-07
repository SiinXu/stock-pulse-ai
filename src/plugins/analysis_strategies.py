# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Exact-owner catalog adapter for plugin-provided analysis strategies."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from src.agent.skills.base import Skill

from .registry import ExtensionContract, ExtensionRegistration


_SKILL_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _valid_text(value: object, *, required: bool = False) -> bool:
    return type(value) is str and (not required or bool(value.strip()))


def _valid_string_list(value: object) -> bool:
    return (
        type(value) is list
        and all(type(item) is str and bool(item.strip()) for item in value)
        and len(value) == len(set(value))
    )


def validate_analysis_strategy_definition(implementation: object) -> bool:
    """Return whether an object is a complete declarative ``Skill`` definition."""

    if type(implementation) is not Skill:
        return False
    if (
        type(implementation.name) is not str
        or len(implementation.name) > 128
        or _SKILL_NAME_PATTERN.fullmatch(implementation.name) is None
        or not _valid_text(implementation.display_name, required=True)
        or not _valid_text(implementation.description, required=True)
        or not _valid_text(implementation.instructions, required=True)
        or not _valid_text(implementation.category, required=True)
        or not _valid_text(implementation.source)
        or not _valid_text(implementation.entrypoint)
        or not _valid_text(implementation.bundle_dir)
        or not _valid_text(implementation.subagent_type)
        or not _valid_text(implementation.preferred_model)
        or implementation.execution_context not in {"inline", "fork"}
        or type(implementation.default_priority) is not int
        or any(
            type(value) is not bool
            for value in (
                implementation.enabled,
                implementation.disable_model_invocation,
                implementation.user_invocable,
                implementation.default_active,
                implementation.default_router,
            )
        )
        or type(implementation.core_rules) is not list
        or any(
            type(rule) is not int or not 1 <= rule <= 7
            for rule in implementation.core_rules
        )
        or len(implementation.core_rules) != len(set(implementation.core_rules))
        or not _valid_string_list(implementation.required_tools)
        or not _valid_string_list(implementation.allowed_tools)
        or not _valid_string_list(implementation.aliases)
        or not _valid_string_list(implementation.market_regimes)
    ):
        return False
    return True


@dataclass(frozen=True, slots=True)
class AnalysisStrategyDefinition:
    """Detached immutable form of one validated plugin ``Skill``."""

    name: str
    display_name: str
    description: str
    instructions: str
    category: str
    core_rules: tuple[int, ...]
    required_tools: tuple[str, ...]
    allowed_tools: tuple[str, ...]
    aliases: tuple[str, ...]
    disable_model_invocation: bool
    user_invocable: bool
    default_active: bool
    default_router: bool
    default_priority: int
    market_regimes: tuple[str, ...]
    execution_context: str
    subagent_type: str
    preferred_model: str

    @classmethod
    def from_skill(cls, skill: Skill) -> "AnalysisStrategyDefinition":
        """Validate and detach a mutable plugin-owned ``Skill`` instance."""

        if not validate_analysis_strategy_definition(skill):
            raise TypeError("analysis strategy definition is invalid")
        return cls(
            name=skill.name,
            display_name=skill.display_name,
            description=skill.description,
            instructions=skill.instructions,
            category=skill.category,
            core_rules=tuple(skill.core_rules),
            required_tools=tuple(skill.required_tools),
            allowed_tools=tuple(skill.allowed_tools),
            aliases=tuple(skill.aliases),
            disable_model_invocation=skill.disable_model_invocation,
            user_invocable=skill.user_invocable,
            default_active=skill.default_active,
            default_router=skill.default_router,
            default_priority=skill.default_priority,
            market_regimes=tuple(skill.market_regimes),
            execution_context=skill.execution_context,
            subagent_type=skill.subagent_type,
            preferred_model=skill.preferred_model,
        )

    def to_skill(self, *, plugin_id: str) -> Skill:
        """Create an isolated runtime ``Skill`` with pinned plugin provenance.

        External plugins always pin ``source`` to ``plugin:<manifest-id>`` so
        they cannot impersonate built-in or custom-directory definitions.
        Packaged built-in analysis strategies (``builtin.analysis-strategy.*``)
        keep ``source="builtin"`` so default-prompt and catalog parity with the
        pre-plugin YAML path is preserved.
        """

        # Prefix owned by src.plugins.builtin.analysis_strategies; inlined here
        # to avoid an import cycle through the builtin package during adapter use.
        if (
            type(plugin_id) is str
            and plugin_id.startswith("builtin.analysis-strategy.")
            and len(plugin_id) > len("builtin.analysis-strategy.")
        ):
            source = "builtin"
        else:
            source = f"plugin:{plugin_id}"

        return Skill(
            name=self.name,
            display_name=self.display_name,
            description=self.description,
            instructions=self.instructions,
            category=self.category,
            core_rules=list(self.core_rules),
            required_tools=list(self.required_tools),
            allowed_tools=list(self.allowed_tools),
            aliases=list(self.aliases),
            enabled=False,
            source=source,
            entrypoint="",
            bundle_dir="",
            disable_model_invocation=self.disable_model_invocation,
            user_invocable=self.user_invocable,
            default_active=self.default_active,
            default_router=self.default_router,
            default_priority=self.default_priority,
            market_regimes=list(self.market_regimes),
            execution_context=self.execution_context,
            subagent_type=self.subagent_type,
            preferred_model=self.preferred_model,
        )


@dataclass(frozen=True, slots=True)
class RegisteredAnalysisStrategy:
    """Immutable plugin provenance plus its detached definition."""

    plugin_id: str
    definition: AnalysisStrategyDefinition


@dataclass(frozen=True, slots=True)
class AnalysisStrategyCatalogSnapshot:
    """One stable root-local generation of enabled plugin strategies."""

    catalog_token: object
    generation: int
    registrations: tuple[RegisteredAnalysisStrategy, ...]


@dataclass(frozen=True, slots=True)
class _OwnedAnalysisStrategy:
    implementation: Skill
    definition: AnalysisStrategyDefinition


class AnalysisStrategyRegistry:
    """Own detached plugin definitions and reject declarative catalog collisions."""

    def __init__(self, reserved_names: Callable[[], Iterable[str]]) -> None:
        if not callable(reserved_names):
            raise TypeError("reserved analysis strategy names provider must be callable")
        self._reserved_names_provider = reserved_names
        self._entries: dict[str, _OwnedAnalysisStrategy] = {}
        self._catalog_token = object()
        self._generation = 0
        self._lock = threading.RLock()

    def _reserved_names(self) -> frozenset[str]:
        values = self._reserved_names_provider()
        if isinstance(values, str):
            raise TypeError("reserved analysis strategy names must be an iterable")
        names = frozenset(values)
        if any(
            type(name) is not str
            or len(name) > 128
            or _SKILL_NAME_PATTERN.fullmatch(name) is None
            for name in names
        ):
            raise TypeError("reserved analysis strategy names are invalid")
        return names

    @property
    def generation(self) -> int:
        """Return the monotonic native catalog generation."""

        with self._lock:
            return self._generation

    def contains(self, registration_id: str) -> bool:
        """Return whether a plugin or declarative definition owns this name."""

        reserved = self._reserved_names()
        with self._lock:
            return registration_id in reserved or registration_id in self._entries

    def register(self, registration_id: str, implementation: object) -> None:
        """Store a detached definition after repeating collision preflight."""

        if type(implementation) is not Skill or implementation.name != registration_id:
            raise TypeError("analysis strategy registration identity is invalid")
        definition = AnalysisStrategyDefinition.from_skill(implementation)
        reserved = self._reserved_names()
        with self._lock:
            if registration_id in reserved or registration_id in self._entries:
                raise ValueError("analysis strategy registration already exists")
            self._entries[registration_id] = _OwnedAnalysisStrategy(
                implementation=implementation,
                definition=definition,
            )
            self._generation += 1

    def unregister(self, registration_id: str, implementation: object) -> None:
        """Remove only the exact mutable object accepted for this registration."""

        with self._lock:
            owner = self._entries.get(registration_id)
            if owner is None or owner.implementation is not implementation:
                return
            del self._entries[registration_id]
            self._generation += 1

    def snapshot(
        self,
        registrations: Iterable[ExtensionRegistration],
    ) -> AnalysisStrategyCatalogSnapshot:
        """Resolve unified registrations against the exact native owners."""

        with self._lock:
            active: list[RegisteredAnalysisStrategy] = []
            for registration in registrations:
                if registration.extension_point != "analysis_strategy":
                    continue
                owner = self._entries.get(registration.registration_id)
                if (
                    owner is None
                    or owner.implementation is not registration.implementation
                ):
                    continue
                active.append(
                    RegisteredAnalysisStrategy(
                        plugin_id=registration.plugin_id,
                        definition=owner.definition,
                    )
                )
            return AnalysisStrategyCatalogSnapshot(
                catalog_token=self._catalog_token,
                generation=self._generation,
                registrations=tuple(active),
            )


def build_analysis_strategy_extension_contract(
    registry: AnalysisStrategyRegistry,
) -> ExtensionContract:
    """Bind the Analysis Strategy point to one root-owned native catalog."""

    if not isinstance(registry, AnalysisStrategyRegistry):
        raise TypeError("analysis strategy registry is invalid")
    return ExtensionContract(
        identity_resolver=lambda implementation: implementation.name,
        validator=validate_analysis_strategy_definition,
        backend=registry,
    )
