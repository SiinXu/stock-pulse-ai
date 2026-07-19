# -*- coding: utf-8 -*-
"""Single authority for validating LLM model assignments against configured routes.

Task assignments (``LITELLM_MODEL``, ``AGENT_LITELLM_MODEL``, ``VISION_MODEL``,
``LITELLM_FALLBACK_MODELS``) must resolve to an enabled, unambiguous Connection
route. This module owns that decision — malformed/unknown ModelRefs, ambiguous
legacy routes, routes removed while still referenced, and Phase 3 Hermes/mixed
constraints — reading the available routes from
:mod:`src.services.config.llm_channel_map`.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from src.config import (
    _uses_direct_env_provider,
    normalize_agent_litellm_model,
)
from src.services.config.llm_channel_map import (
    collect_hermes_channel_models_from_map,
    collect_llm_channel_models_from_map,
    collect_mixed_hermes_routes_from_map,
    collect_yaml_models_from_map,
    has_runtime_source_for_model,
    matches_exact_route,
    matches_route_set,
)


def _split_csv(value: str) -> List[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


class ModelAssignmentValidator:
    """Validate model-route assignments and legacy/ModelRef migration hazards."""

    @staticmethod
    def collect_llm_route_references(
        effective_map: Dict[str, str],
        known_routes: Set[str],
    ) -> Dict[str, List[Dict[str, str]]]:
        """Collect explicit task assignments by exact model route."""
        from src.llm.model_ref import normalize_model_ref

        references: Dict[str, List[Dict[str, str]]] = {}

        def add(route: str, task: str, key: str) -> None:
            normalized = normalize_model_ref(route)
            if not normalized:
                return
            entry = {"task": task, "key": key}
            route_references = references.setdefault(normalized, [])
            if entry not in route_references:
                route_references.append(entry)

        add(effective_map.get("LITELLM_MODEL", ""), "report", "LITELLM_MODEL")
        raw_agent_model = (effective_map.get("AGENT_LITELLM_MODEL") or "").strip()
        if raw_agent_model:
            add(
                normalize_agent_litellm_model(
                    raw_agent_model,
                    configured_models=known_routes,
                ),
                "agent",
                "AGENT_LITELLM_MODEL",
            )
        add(effective_map.get("VISION_MODEL", ""), "vision", "VISION_MODEL")
        for fallback in _split_csv(
            effective_map.get("LITELLM_FALLBACK_MODELS") or ""
        ):
            add(fallback, "fallback", "LITELLM_FALLBACK_MODELS")
        return references

    @staticmethod
    def collect_llm_route_connection_ids(
        effective_map: Dict[str, str],
    ) -> Dict[str, List[str]]:
        """Map each enabled channel route to its owning Connection ids."""
        from src.llm.model_ref import canonicalize_connection_id

        owners: Dict[str, List[str]] = {}
        for raw_name in (effective_map.get("LLM_CHANNELS") or "").split(","):
            connection_id = canonicalize_connection_id(raw_name)
            if not connection_id:
                continue
            connection_map = dict(effective_map)
            connection_map["LLM_CHANNELS"] = connection_id
            for route in collect_llm_channel_models_from_map(connection_map):
                route_owners = owners.setdefault(route, [])
                if connection_id not in route_owners:
                    route_owners.append(connection_id)
        return owners

    @staticmethod
    def collect_llm_channel_model_refs_from_map(
        effective_map: Dict[str, str],
    ) -> List[str]:
        """Collect connection-aware aliases for all enabled channel models."""
        from src.llm.model_ref import encode_model_ref

        refs: List[str] = []
        for route, connection_ids in (
            ModelAssignmentValidator.collect_llm_route_connection_ids(effective_map).items()
        ):
            refs.extend(
                encode_model_ref(connection_id, route)
                for connection_id in connection_ids
            )
        return refs

    @staticmethod
    def collect_model_ref_assignment_issues(
        effective_map: Dict[str, str],
        updated_keys: Set[str],
    ) -> List[Dict[str, Any]]:
        """Validate ModelRefs and require confirmation for ambiguous legacy routes."""
        from src.llm.model_ref import (
            decode_model_ref,
            encode_model_ref,
            is_model_ref,
            normalize_model_ref,
        )

        owners = ModelAssignmentValidator.collect_llm_route_connection_ids(effective_map)
        known_routes = set(owners)
        assignments: List[Tuple[str, str]] = [
            ("LITELLM_MODEL", (effective_map.get("LITELLM_MODEL") or "").strip()),
            (
                "AGENT_LITELLM_MODEL",
                normalize_agent_litellm_model(
                    (effective_map.get("AGENT_LITELLM_MODEL") or "").strip(),
                    configured_models=known_routes,
                ),
            ),
            ("VISION_MODEL", (effective_map.get("VISION_MODEL") or "").strip()),
        ]
        assignments.extend(
            ("LITELLM_FALLBACK_MODELS", value)
            for value in _split_csv(
                effective_map.get("LITELLM_FALLBACK_MODELS") or ""
            )
        )

        valid_refs = set(
            ModelAssignmentValidator.collect_llm_channel_model_refs_from_map(effective_map)
        )
        issues: List[Dict[str, Any]] = []
        seen: Set[Tuple[str, str, str]] = set()
        for key, value in assignments:
            if not value:
                continue
            if is_model_ref(value):
                normalized_value = normalize_model_ref(value)
                try:
                    decoded = decode_model_ref(value)
                except ValueError:
                    decoded = None
                    code = "invalid_model_ref"
                else:
                    code = "unknown_model_ref" if normalized_value not in valid_refs else ""
                if code and (key, value, code) not in seen:
                    seen.add((key, value, code))
                    issues.append({
                        "key": key,
                        "code": code,
                        "message": (
                            "The selected model reference is malformed"
                            if code == "invalid_model_ref"
                            else "The selected model reference no longer resolves to an enabled Connection"
                        ),
                        "severity": "error" if key in updated_keys else "warning",
                        "expected": "enabled connection-aware model_ref",
                        "actual": value,
                        "details": {
                            "model_ref": value,
                            "connection_id": decoded.connection_id if decoded else None,
                            "route": decoded.runtime_route if decoded else None,
                        },
                    })
                continue

            connection_ids = owners.get(value, [])
            if len(connection_ids) < 2 or (key, value, "ambiguous_model_route") in seen:
                continue
            seen.add((key, value, "ambiguous_model_route"))
            issues.append({
                "key": key,
                "code": "ambiguous_model_route",
                "message": (
                    f"Model route '{value}' exists on multiple Connections. "
                    "Choose the intended Connection before saving this assignment."
                ),
                "severity": "error" if key in updated_keys else "warning",
                "expected": "connection-aware model_ref",
                "actual": value,
                "details": {
                    "route": value,
                    "connection_ids": connection_ids,
                    "model_refs": [
                        encode_model_ref(connection_id, value)
                        for connection_id in connection_ids
                    ],
                },
            })
        return issues

    @staticmethod
    def model_removal_issue_key(
        connection_ids: Sequence[str],
        updated_keys: Set[str],
    ) -> str:
        """Choose the submitted Connection field that removed a model route."""
        for suffix in ("MODELS", "ENABLED"):
            for connection_id in connection_ids:
                key = f"LLM_{connection_id.upper()}_{suffix}"
                if key in updated_keys:
                    return key
        if "LITELLM_CONFIG" in updated_keys:
            return "LITELLM_CONFIG"
        return "LLM_CHANNELS"

    @staticmethod
    def collect_removed_model_in_use_issues(
        effective_map: Dict[str, str],
        previous_effective_map: Optional[Dict[str, str]],
        updated_keys: Set[str],
    ) -> List[Dict[str, Any]]:
        """Reject routes removed by this draft while task assignments still use them."""
        if previous_effective_map is None or not updated_keys:
            return []

        from src.llm.model_ref import decode_model_ref, encode_model_ref

        previous_models = (
            collect_yaml_models_from_map(previous_effective_map)
            or collect_llm_channel_models_from_map(previous_effective_map)
        )
        current_models = (
            collect_yaml_models_from_map(effective_map)
            or collect_llm_channel_models_from_map(effective_map)
        )
        current_model_set = set(current_models)
        previous_connection_owners = (
            ModelAssignmentValidator.collect_llm_route_connection_ids(previous_effective_map)
        )
        current_connection_owners = (
            ModelAssignmentValidator.collect_llm_route_connection_ids(effective_map)
        )
        previous_model_refs = {
            encode_model_ref(connection_id, route)
            for route, connection_ids in previous_connection_owners.items()
            for connection_id in connection_ids
        }
        current_model_refs = {
            encode_model_ref(connection_id, route)
            for route, connection_ids in current_connection_owners.items()
            for connection_id in connection_ids
        }
        removed_models = [
            route for route in previous_models if route not in current_model_set
        ]

        known_routes = set(previous_models) | current_model_set
        references = ModelAssignmentValidator.collect_llm_route_references(
            effective_map,
            known_routes,
        )
        issues: List[Dict[str, Any]] = []
        for model_ref in sorted(previous_model_refs - current_model_refs):
            referenced_by = references.get(model_ref, [])
            if not referenced_by:
                continue
            decoded = decode_model_ref(model_ref)
            if decoded is None:
                continue
            issues.append({
                "key": ModelAssignmentValidator.model_removal_issue_key(
                    [decoded.connection_id],
                    updated_keys,
                ),
                "code": "model_in_use",
                "message": (
                    "The selected Connection model is still assigned to one or more tasks. "
                    "Replace or clear those assignments in the same update before removing it."
                ),
                "severity": "error",
                "expected": "all task references replaced or cleared atomically",
                "actual": model_ref,
                "details": {
                    "model_ref": model_ref,
                    "route": decoded.runtime_route,
                    "connection_ids": [decoded.connection_id],
                    "referenced_by": referenced_by,
                },
            })

        # A legacy route that used to have multiple owners is ambiguous even if
        # one owner remains after this update. Require the assignment itself to be
        # migrated to a ModelRef instead of silently selecting the survivor.
        for route, previous_connection_ids in previous_connection_owners.items():
            current_connection_ids = current_connection_owners.get(route, [])
            if (
                len(previous_connection_ids) < 2
                or set(current_connection_ids) == set(previous_connection_ids)
                or not references.get(route)
            ):
                continue
            for reference in references[route]:
                issues.append({
                    "key": reference["key"],
                    "code": "ambiguous_model_route",
                    "message": (
                        f"Legacy model route '{route}' was shared by multiple Connections. "
                        "Choose a specific Connection before changing either source."
                    ),
                    "severity": "error",
                    "expected": "connection-aware model_ref",
                    "actual": route,
                    "details": {
                        "route": route,
                        "connection_ids": previous_connection_ids,
                        "model_refs": [
                            encode_model_ref(connection_id, route)
                            for connection_id in previous_connection_ids
                        ],
                        "referenced_by": references[route],
                    },
                })

        for route in removed_models:
            referenced_by = references.get(route, [])
            if not referenced_by:
                continue
            connection_ids = previous_connection_owners.get(route, [])
            issues.append(
                {
                    "key": ModelAssignmentValidator.model_removal_issue_key(
                        connection_ids,
                        updated_keys,
                    ),
                    "code": "model_in_use",
                    "message": (
                        f"Model route '{route}' is still assigned to one or more tasks. "
                        "Replace or clear those assignments in the same update before removing it."
                    ),
                    "severity": "error",
                    "expected": "all task references replaced or cleared atomically",
                    "actual": route,
                    "details": {
                        "route": route,
                        "connection_ids": connection_ids,
                        "referenced_by": referenced_by,
                    },
                }
            )
        return issues

    @staticmethod
    def validate_llm_runtime_selection(
        effective_map: Dict[str, str],
        updated_keys: Optional[Set[str]] = None,
        previous_effective_map: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Validate selected primary/fallback/vision models against configured channels."""
        from src.llm.model_ref import normalize_model_ref

        removal_issues = ModelAssignmentValidator.collect_removed_model_in_use_issues(
            effective_map=effective_map,
            previous_effective_map=previous_effective_map,
            updated_keys=updated_keys or set(),
        )
        issues: List[Dict[str, Any]] = list(removal_issues)
        issues.extend(
            ModelAssignmentValidator.collect_model_ref_assignment_issues(
                effective_map,
                updated_keys or set(),
            )
        )
        removed_routes_in_use = {
            issue["details"]["route"] for issue in removal_issues
        }

        # Vision references normally degrade to warnings so historical breakage
        # never blocks unrelated saves; but when this very update reshapes the
        # channel map (delete/disable/model-list changes), removing the Vision
        # model's declared source must block like other task references.
        channel_shape_touched = False
        if updated_keys:
            if "LLM_CHANNELS" in updated_keys:
                channel_shape_touched = True
            else:
                declared_channel_prefixes = tuple(
                    f"LLM_{name.strip().upper()}_"
                    for name in (effective_map.get("LLM_CHANNELS") or "").split(",")
                    if name.strip()
                )
                channel_shape_touched = bool(declared_channel_prefixes) and any(
                    key.startswith(declared_channel_prefixes) for key in updated_keys
                )
        vision_reference_severity = "error" if channel_shape_touched else "warning"

        available_models = (
            collect_yaml_models_from_map(effective_map)
            or collect_llm_channel_models_from_map(effective_map)
        )
        available_model_set = set(available_models)
        if not collect_yaml_models_from_map(effective_map):
            available_model_set.update(
                ModelAssignmentValidator.collect_llm_channel_model_refs_from_map(effective_map)
            )
        hermes_route_set = set(collect_hermes_channel_models_from_map(effective_map))
        mixed_hermes_routes = collect_mixed_hermes_routes_from_map(effective_map)
        if not available_model_set:
            raw_channels = (effective_map.get("LLM_CHANNELS") or "").strip()
            if not raw_channels:
                return issues

            configured_agent_model_raw = (effective_map.get("AGENT_LITELLM_MODEL") or "").strip()
            configured_agent_model = normalize_agent_litellm_model(
                configured_agent_model_raw,
                configured_models=available_model_set,
            )
            primary_model = normalize_model_ref(effective_map.get("LITELLM_MODEL") or "")
            if (
                primary_model
                and primary_model not in removed_routes_in_use
                and not has_runtime_source_for_model(primary_model, effective_map)
            ):
                issues.append(
                    {
                        "key": "LITELLM_MODEL",
                        "code": "missing_runtime_source",
                        "message": (
                            "A primary model is selected, but no usable runtime source was found. "
                            "Enable at least one channel with available models, or provide the "
                            "matching provider API key so the model can be resolved."
                        ),
                        "severity": "error",
                        "expected": "enabled channel model or matching legacy API key",
                        "actual": primary_model,
                    }
                )

            if (
                configured_agent_model_raw
                and configured_agent_model
                and configured_agent_model not in removed_routes_in_use
                and not has_runtime_source_for_model(
                    configured_agent_model,
                    effective_map,
                )
            ):
                issues.append(
                    {
                        "key": "AGENT_LITELLM_MODEL",
                        "code": "missing_runtime_source",
                        "message": (
                            "An Agent primary model is selected, but no usable runtime source was found. "
                            "Enable at least one channel with available models, or provide the "
                            "matching provider API key so the model can be resolved."
                        ),
                        "severity": "error",
                        "expected": "enabled channel model or matching legacy API key",
                        "actual": configured_agent_model,
                    }
                )
            elif (
                configured_agent_model_raw
                and configured_agent_model
                and matches_route_set(configured_agent_model, hermes_route_set)
                and not matches_route_set(configured_agent_model, mixed_hermes_routes)
            ):
                issues.append(
                    {
                        "key": "AGENT_LITELLM_MODEL",
                        "code": "explicit_agent_model_no_safe_deployment",
                        "message": (
                            "Hermes-only routes are not valid Agent models in Phase 3. "
                            "Choose a route with at least one non-Hermes deployment."
                        ),
                        "severity": "error",
                        "expected": "Agent-safe route with non-Hermes deployment",
                        "actual": configured_agent_model,
                    }
                )

            fallback_models = [
                normalize_model_ref(model)
                for model in (effective_map.get("LITELLM_FALLBACK_MODELS") or "").split(",")
                if model.strip()
            ]
            invalid_fallbacks = [
                model for model in fallback_models
                if model not in removed_routes_in_use
                if not has_runtime_source_for_model(model, effective_map)
            ]
            if invalid_fallbacks:
                issues.append(
                    {
                        "key": "LITELLM_FALLBACK_MODELS",
                        "code": "missing_runtime_source",
                        "message": (
                            "Some fallback models do not have an enabled channel "
                            "or matching API key available"
                        ),
                        "severity": "error",
                        "expected": "enabled channel models or matching legacy API keys",
                        "actual": ", ".join(invalid_fallbacks[:3]),
                    }
                )

            vision_model = normalize_model_ref(effective_map.get("VISION_MODEL") or "")
            if vision_model and matches_route_set(vision_model, hermes_route_set):
                issues.append(
                    {
                        "key": "VISION_MODEL",
                        "code": "hermes_vision_unsupported",
                        "message": (
                            "Hermes routes are not valid Vision models in Phase 3. "
                            "Choose a pure non-Hermes Vision-capable route."
                        ),
                        "severity": "error",
                        "expected": "pure non-Hermes Vision route",
                        "actual": vision_model,
                    }
                )
            elif (
                vision_model
                and vision_model not in removed_routes_in_use
                and not has_runtime_source_for_model(vision_model, effective_map)
            ):
                issues.append(
                    {
                        "key": "VISION_MODEL",
                        "code": "missing_runtime_source",
                        "message": (
                            "A Vision model is selected, but there is no enabled channel "
                            "or matching API key available for it"
                        ),
                        "severity": vision_reference_severity,
                        "expected": "enabled channel model or matching legacy API key",
                        "actual": vision_model,
                    }
                )

            return issues

        primary_model = normalize_model_ref(effective_map.get("LITELLM_MODEL") or "")
        if matches_route_set(primary_model, mixed_hermes_routes):
            issues.append(
                {
                    "key": "LITELLM_MODEL",
                    "code": "mixed_hermes_route_unsupported",
                    "message": (
                        "Mixed Hermes/non-Hermes generation routes are not supported in Phase 3. "
                        "Choose a pure Hermes or pure non-Hermes route."
                    ),
                    "severity": "error",
                    "expected": "pure generation route",
                    "actual": primary_model,
                }
            )
        if (
            primary_model
            and primary_model not in removed_routes_in_use
            and not matches_exact_route(primary_model, available_model_set)
            and not _uses_direct_env_provider(primary_model)
        ):
            issues.append(
                {
                    "key": "LITELLM_MODEL",
                    "code": "unknown_model",
                    "message": (
                        "The selected primary model is not declared by the current enabled channels "
                        "or advanced model routing config. "
                        f"Available models: {', '.join(available_models[:6])}"
                    ),
                    "severity": "error",
                    "expected": "one configured channel model",
                    "actual": primary_model,
                }
            )

        configured_agent_model_raw = (effective_map.get("AGENT_LITELLM_MODEL") or "").strip()
        configured_agent_model = normalize_agent_litellm_model(
            configured_agent_model_raw,
            configured_models=available_model_set,
        )
        if (
            configured_agent_model_raw
            and configured_agent_model
            and configured_agent_model not in removed_routes_in_use
            and not matches_exact_route(configured_agent_model, available_model_set)
            and not _uses_direct_env_provider(configured_agent_model)
        ):
            issues.append(
                {
                    "key": "AGENT_LITELLM_MODEL",
                    "code": "unknown_model",
                    "message": (
                        "The selected Agent primary model is not declared by the current enabled channels "
                        "or advanced model routing config. "
                        f"Available models: {', '.join(available_models[:6])}"
                    ),
                    "severity": "error",
                    "expected": "one configured channel model",
                    "actual": configured_agent_model,
                }
            )
        elif (
                configured_agent_model_raw
                and configured_agent_model
                and matches_route_set(configured_agent_model, hermes_route_set)
                and not matches_route_set(configured_agent_model, mixed_hermes_routes)
            ):
            issues.append(
                {
                    "key": "AGENT_LITELLM_MODEL",
                    "code": "explicit_agent_model_no_safe_deployment",
                    "message": (
                        "Hermes-only routes are not valid Agent models in Phase 3. "
                        "Choose a route with at least one non-Hermes deployment."
                    ),
                    "severity": "error",
                    "expected": "Agent-safe route with non-Hermes deployment",
                    "actual": configured_agent_model,
                }
            )

        fallback_models = [
            normalize_model_ref(model)
            for model in (effective_map.get("LITELLM_FALLBACK_MODELS") or "").split(",")
            if model.strip()
        ]
        mixed_fallbacks = [
            model for model in fallback_models
            if matches_route_set(model, mixed_hermes_routes)
        ]
        if mixed_fallbacks:
            issues.append(
                {
                    "key": "LITELLM_FALLBACK_MODELS",
                    "code": "mixed_hermes_route_unsupported",
                    "message": (
                        "Mixed Hermes/non-Hermes generation routes are not supported as fallback models in Phase 3."
                    ),
                    "severity": "error",
                    "expected": "pure generation fallback routes",
                    "actual": ", ".join(mixed_fallbacks[:3]),
                }
            )
        invalid_fallbacks = [
            model for model in fallback_models
            if model not in removed_routes_in_use
            if not matches_exact_route(model, available_model_set)
            and not _uses_direct_env_provider(model)
        ]
        if invalid_fallbacks:
            issues.append(
                {
                    "key": "LITELLM_FALLBACK_MODELS",
                    "code": "unknown_model",
                    "message": (
                        "Fallback models include entries that are not declared by the current enabled channels "
                        "or advanced model routing config"
                    ),
                    "severity": "error",
                    "expected": ",".join(available_models[:6]),
                    "actual": ", ".join(invalid_fallbacks[:3]),
                }
            )

        vision_model = normalize_model_ref(effective_map.get("VISION_MODEL") or "")
        if vision_model and matches_route_set(vision_model, hermes_route_set):
            issues.append(
                {
                    "key": "VISION_MODEL",
                    "code": "hermes_vision_unsupported",
                    "message": (
                        "Hermes routes are not valid Vision models in Phase 3. "
                        "Choose a pure non-Hermes Vision-capable route."
                    ),
                    "severity": "error",
                    "expected": "pure non-Hermes Vision route",
                    "actual": vision_model,
                }
            )
        elif (
            vision_model
            and vision_model not in removed_routes_in_use
            and not matches_exact_route(vision_model, available_model_set)
            and not _uses_direct_env_provider(vision_model)
        ):
            issues.append(
                {
                    "key": "VISION_MODEL",
                    "code": "unknown_model",
                    "message": (
                        "The selected Vision model is not declared by the current enabled channels "
                        "or advanced model routing config"
                    ),
                    "severity": vision_reference_severity,
                    "expected": ",".join(available_models[:6]),
                    "actual": vision_model,
                }
            )

        return issues
