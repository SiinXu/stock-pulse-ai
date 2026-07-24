# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Validated access to the repository-owned local model catalog."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import urlsplit


LOCAL_MODEL_CATALOG_PATH = Path(__file__).with_name("local_model_catalog.json")

_MODEL_KEYS = {
    "id",
    "section",
    "display_name",
    "capability_summary",
    "capabilities",
    "q4",
    "memory_tier",
    "recommended_ram_gb",
    "license",
    "upstream",
    "install",
    "desktop",
}
_Q4_KEYS = {"quantization", "size_bytes", "source_kind", "source_url", "source_revision"}
_LICENSE_KEYS = {
    "identifier",
    "name",
    "evidence_url",
    "redistribution",
    "standalone_license_file",
}
_UPSTREAM_KEYS = {"primary_url", "huggingface_url", "modelscope_url", "revision"}
_INSTALL_KEYS = {
    "method",
    "status",
    "ollama_tag",
    "planned_ollama_tag",
    "download_url",
    "hosted_by_stockpulse",
    "minimum_runtime_version",
}
_DESKTOP_KEYS = {"recommended", "role", "guidance_en"}
_OLLAMA_TAG_PATTERN = re.compile(
    r"^[a-z0-9]+(?:[._-][a-z0-9]+)*"
    r"(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)?"
    r"(?::[a-z0-9]+(?:[._-][a-z0-9]+)*)?$",
    re.IGNORECASE,
)


class LocalModelCatalogError(ValueError):
    """Raised when the checked-in catalog violates its public contract."""


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise LocalModelCatalogError(message)


def _require_mapping(value: Any, field: str, keys: set[str]) -> Mapping[str, Any]:
    _require(isinstance(value, dict), f"{field} must be an object")
    _require(set(value) == keys, f"{field} fields must be {sorted(keys)}")
    return value


def _require_text(value: Any, field: str) -> str:
    _require(isinstance(value, str) and bool(value.strip()), f"{field} must be a non-empty string")
    return value.strip()


def _require_optional_text(value: Any, field: str) -> Optional[str]:
    if value is None:
        return None
    return _require_text(value, field)


def _require_https_url(value: Any, field: str, *, optional: bool = False) -> Optional[str]:
    text = _require_optional_text(value, field) if optional else _require_text(value, field)
    if text is None:
        return None
    parts = urlsplit(text)
    _require(parts.scheme == "https" and bool(parts.netloc), f"{field} must be an HTTPS URL")
    _require(not parts.username and not parts.password, f"{field} must not contain credentials")
    return text


def _validate_localized_text(value: Any, field: str) -> None:
    localized = _require_mapping(value, field, {"en", "zh"})
    _require_text(localized["en"], f"{field}.en")
    _require_text(localized["zh"], f"{field}.zh")


def _validate_model(model: Any, index: int, seen_ids: set[str], seen_tags: set[str]) -> None:
    field = f"models[{index}]"
    entry = _require_mapping(model, field, _MODEL_KEYS)
    model_id = _require_text(entry["id"], f"{field}.id")
    _require(model_id not in seen_ids, f"duplicate model id: {model_id}")
    seen_ids.add(model_id)

    section = _require_text(entry["section"], f"{field}.section")
    _require(section in {"general", "finance"}, f"{field}.section is unsupported")
    _validate_localized_text(entry["display_name"], f"{field}.display_name")
    _validate_localized_text(entry["capability_summary"], f"{field}.capability_summary")

    capabilities = entry["capabilities"]
    _require(isinstance(capabilities, list) and bool(capabilities), f"{field}.capabilities must be non-empty")
    normalized_capabilities = [_require_text(item, f"{field}.capabilities") for item in capabilities]
    _require(len(normalized_capabilities) == len(set(normalized_capabilities)), f"{field}.capabilities has duplicates")

    q4 = _require_mapping(entry["q4"], f"{field}.q4", _Q4_KEYS)
    _require(q4["quantization"] == "Q4_K_M", f"{field}.q4.quantization must be Q4_K_M")
    _require(
        isinstance(q4["size_bytes"], int) and not isinstance(q4["size_bytes"], bool) and q4["size_bytes"] > 0,
        f"{field}.q4.size_bytes must be a positive integer",
    )
    _require(
        q4["source_kind"] in {"official_ollama", "community_gguf"},
        f"{field}.q4.source_kind is unsupported",
    )
    _require_https_url(q4["source_url"], f"{field}.q4.source_url")
    _require_text(q4["source_revision"], f"{field}.q4.source_revision")

    _require(entry["memory_tier"] in {"light", "standard", "high"}, f"{field}.memory_tier is unsupported")
    _require(
        isinstance(entry["recommended_ram_gb"], int)
        and not isinstance(entry["recommended_ram_gb"], bool)
        and entry["recommended_ram_gb"] > 0,
        f"{field}.recommended_ram_gb must be a positive integer",
    )

    license_data = _require_mapping(entry["license"], f"{field}.license", _LICENSE_KEYS)
    _require_text(license_data["identifier"], f"{field}.license.identifier")
    _require_text(license_data["name"], f"{field}.license.name")
    _require_https_url(license_data["evidence_url"], f"{field}.license.evidence_url")
    _require(
        license_data["redistribution"] in {"allowed_with_notice", "guided_only"},
        f"{field}.license.redistribution is unsupported",
    )
    _require(
        isinstance(license_data["standalone_license_file"], bool),
        f"{field}.license.standalone_license_file must be boolean",
    )

    upstream = _require_mapping(entry["upstream"], f"{field}.upstream", _UPSTREAM_KEYS)
    _require_https_url(upstream["primary_url"], f"{field}.upstream.primary_url")
    _require_https_url(upstream["huggingface_url"], f"{field}.upstream.huggingface_url", optional=True)
    _require_https_url(upstream["modelscope_url"], f"{field}.upstream.modelscope_url", optional=True)
    _require_text(upstream["revision"], f"{field}.upstream.revision")

    install = _require_mapping(entry["install"], f"{field}.install", _INSTALL_KEYS)
    _require(
        install["method"] in {"ollama_pull", "planned_ollama_package", "guided_import"},
        f"{field}.install.method is unsupported",
    )
    _require(
        install["status"] in {"available", "conversion_required", "license_review_required"},
        f"{field}.install.status is unsupported",
    )
    ollama_tag = _require_optional_text(install["ollama_tag"], f"{field}.install.ollama_tag")
    planned_tag = _require_optional_text(install["planned_ollama_tag"], f"{field}.install.planned_ollama_tag")
    for tag_field, tag in (("ollama_tag", ollama_tag), ("planned_ollama_tag", planned_tag)):
        if tag is not None:
            _require(bool(_OLLAMA_TAG_PATTERN.fullmatch(tag)), f"{field}.install.{tag_field} is invalid")
    if ollama_tag is not None:
        _require(ollama_tag not in seen_tags, f"duplicate Ollama tag: {ollama_tag}")
        seen_tags.add(ollama_tag)
    _require_https_url(install["download_url"], f"{field}.install.download_url")
    _require(isinstance(install["hosted_by_stockpulse"], bool), f"{field}.install.hosted_by_stockpulse must be boolean")
    _require_optional_text(install["minimum_runtime_version"], f"{field}.install.minimum_runtime_version")

    if install["method"] == "ollama_pull":
        _require(
            install["status"] == "available" and ollama_tag is not None,
            f"{field} must have an available Ollama tag",
        )
    if install["method"] == "planned_ollama_package":
        _require(
            install["status"] == "conversion_required" and ollama_tag is None and planned_tag is not None,
            f"{field} planned package state is inconsistent",
        )
    if install["method"] == "guided_import":
        _require(
            install["status"] == "license_review_required" and ollama_tag is None,
            f"{field} guided import state is inconsistent",
        )
    if install["hosted_by_stockpulse"]:
        _require(
            license_data["redistribution"] == "allowed_with_notice",
            f"{field} cannot be StockPulse-hosted under its current license conclusion",
        )

    desktop = _require_mapping(entry["desktop"], f"{field}.desktop", _DESKTOP_KEYS)
    _require(isinstance(desktop["recommended"], bool), f"{field}.desktop.recommended must be boolean")
    role = _require_optional_text(desktop["role"], f"{field}.desktop.role")
    _require_text(desktop["guidance_en"], f"{field}.desktop.guidance_en")
    if desktop["recommended"]:
        _require(section == "general", f"{field} desktop presets must be general models")
        _require(
            install["method"] == "ollama_pull" and ollama_tag is not None,
            f"{field} desktop preset is not pullable",
        )
        _require(
            role in {"lightweight", "default", "high_performance", "reasoning"},
            f"{field}.desktop.role is unsupported",
        )
    else:
        _require(role is None, f"{field}.desktop.role must be null when not recommended")


def validate_local_model_catalog(catalog: Any) -> None:
    """Raise when a catalog value violates the cross-client contract."""
    _require(isinstance(catalog, dict), "catalog root must be an object")
    _require(set(catalog) == {"schema_version", "verified_at", "models"}, "catalog root fields are invalid")
    _require(catalog["schema_version"] == 1, "unsupported local model catalog schema_version")
    verified_at = _require_text(catalog["verified_at"], "verified_at")
    try:
        date.fromisoformat(verified_at)
    except ValueError as exc:
        raise LocalModelCatalogError("verified_at must be an ISO date") from exc
    models = catalog["models"]
    _require(isinstance(models, list) and bool(models), "models must be a non-empty list")
    seen_ids: set[str] = set()
    seen_tags: set[str] = set()
    for index, model in enumerate(models):
        _validate_model(model, index, seen_ids, seen_tags)


def get_local_model_catalog(path: Optional[Path] = None) -> Dict[str, Any]:
    """Read, validate, and return a caller-immune local model catalog."""
    catalog_path = Path(path) if path is not None else LOCAL_MODEL_CATALOG_PATH
    try:
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalModelCatalogError(f"failed to read local model catalog: {exc}") from exc
    validate_local_model_catalog(catalog)
    return deepcopy(catalog)


def get_desktop_local_model_presets() -> List[Dict[str, Any]]:
    """Project the pullable desktop recommendations from the shared catalog."""
    presets: List[Dict[str, Any]] = []
    for model in get_local_model_catalog()["models"]:
        if not model["desktop"]["recommended"]:
            continue
        presets.append(
            {
                "id": model["install"]["ollama_tag"],
                "label": model["display_name"]["en"],
                "approxSizeGb": round(model["q4"]["size_bytes"] / 1_000_000_000, 1),
                "minRamGb": model["recommended_ram_gb"],
                "guidance": model["desktop"]["guidance_en"],
            }
        )
    return presets
