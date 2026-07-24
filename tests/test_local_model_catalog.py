# -*- coding: utf-8 -*-
# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Contracts for the repository-owned local model catalog."""

from __future__ import annotations

from copy import deepcopy

import pytest

from src.llm.local_model_catalog import (
    LocalModelCatalogError,
    get_desktop_local_model_presets,
    get_local_model_catalog,
    validate_local_model_catalog,
)


EXPECTED_IDS = [
    "qwen3-4b",
    "qwen3-8b",
    "gemma4-12b",
    "deepseek-r1-8b",
    "dianjin-r1-7b",
    "fin-r1-7b",
    "xuanyuan-6b-chat",
]


def test_catalog_keeps_the_fixed_general_and_finance_selection() -> None:
    catalog = get_local_model_catalog()

    assert [model["id"] for model in catalog["models"]] == EXPECTED_IDS
    assert [model["section"] for model in catalog["models"]].count("general") == 4
    assert [model["section"] for model in catalog["models"]].count("finance") == 3


def test_catalog_returns_caller_immune_data() -> None:
    first = get_local_model_catalog()
    first["models"][0]["display_name"]["en"] = "mutated"
    first["models"].append({"id": "injected"})

    second = get_local_model_catalog()
    assert second["models"][0]["display_name"]["en"] == "Qwen3 4B"
    assert [model["id"] for model in second["models"]] == EXPECTED_IDS


def test_desktop_projection_contains_only_available_general_ollama_tags() -> None:
    presets = get_desktop_local_model_presets()

    assert [preset["id"] for preset in presets] == [
        "qwen3:4b",
        "qwen3:8b",
        "gemma4:12b",
        "deepseek-r1:8b",
    ]
    assert [preset["approxSizeGb"] for preset in presets] == [2.5, 5.2, 7.6, 5.2]
    assert [preset["minRamGb"] for preset in presets] == [8, 16, 24, 16]


def test_finance_distribution_matches_license_and_artifact_evidence() -> None:
    models = {model["id"]: model for model in get_local_model_catalog()["models"]}

    assert models["dianjin-r1-7b"]["install"]["status"] == "conversion_required"
    assert models["fin-r1-7b"]["install"]["planned_ollama_tag"] == "stockpulse/fin-r1-7b:q4_k_m"
    assert models["xuanyuan-6b-chat"]["license"]["redistribution"] == "guided_only"
    assert models["xuanyuan-6b-chat"]["install"]["method"] == "guided_import"
    assert all(not model["install"]["hosted_by_stockpulse"] for model in models.values())


def test_catalog_rejects_a_non_pullable_desktop_recommendation() -> None:
    invalid = deepcopy(get_local_model_catalog())
    finance = next(model for model in invalid["models"] if model["section"] == "finance")
    finance["desktop"]["recommended"] = True
    finance["desktop"]["role"] = "default"

    with pytest.raises(LocalModelCatalogError, match="desktop presets must be general"):
        validate_local_model_catalog(invalid)
