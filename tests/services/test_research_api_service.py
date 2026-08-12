# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Unit tests for research API stratified conclusion projection (#1143)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.research_api_service import (
    RESEARCH_CONCLUSION_SCHEMA_VERSION,
    ResearchApiNotFoundError,
    ResearchApiService,
    ResearchApiValidationError,
)

_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "report_strata"
    / "full_strata.json"
)


def _record_with_strata() -> dict:
    strata = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    return {
        "id": 42,
        "query_id": "q-research-1",
        "stock_code": "600519",
        "stock_name": "Kweichow Moutai",
        "report_type": "detailed",
        "created_at": "2026-07-25T16:00:00+08:00",
        "analysis_summary": "Constructive near-term setup with elevated valuation risk.",
        "operation_advice": "Hold and wait for volume confirmation.",
        "action": "hold",
        "action_label": "Hold",
        "trend_prediction": "Range-bound with upside bias.",
        "raw_result": {
            "report_language": "en",
            "confidence_level": "中",
            "operation_advice": "Hold and wait for volume confirmation.",
            "action": "hold",
            "dashboard": {
                "core_conclusion": {
                    "one_sentence": "Hold through the consolidation while volume confirms.",
                    "signal_type": "hold",
                    "time_sensitivity": "days",
                    "position_advice": "Keep core; no chase.",
                },
                "phase_decision": {
                    "confidence_reason": "Quote quality is good but PE is elevated.",
                    "watch_conditions": ["Volume confirms breakout", "Hold 1650"],
                },
                "intelligence": {
                    "risk_alerts": [
                        "Valuation elevated",
                        "Sector rotation risk",
                        "Liquidity thin",
                    ],
                    "positive_catalysts": ["Holiday demand", "Channel restock"],
                },
                "report_strata": strata,
            },
        },
    }


def test_project_standard_includes_strata_and_metadata() -> None:
    service = ResearchApiService(history_service=object())
    payload = service.project_conclusion(_record_with_strata(), mode="standard")

    assert payload["schema_version"] == RESEARCH_CONCLUSION_SCHEMA_VERSION
    assert payload["mode"] == "standard"
    meta = payload["metadata"]
    assert meta["record_id"] == 42
    assert meta["stock_code"] == "600519"
    assert meta["confidence_level"] == "中"
    assert meta["as_of"]  # from strata facts
    assert meta["evidence_counts"]["verified_facts"] >= 1
    assert meta["evidence_counts"]["evidence_refs"] >= 1
    assert "ohlcv:daily:600519" in meta["evidence_refs"]
    conclusion = payload["conclusion"]
    assert conclusion["one_sentence"]
    assert conclusion["gaps"]
    assert conclusion["report_strata"] is not None
    assert "verified_facts" in conclusion["report_strata"]
    assert conclusion["confidence_reason"]
    # compact standard caps risks
    assert len(conclusion["risks"]) <= 3
    # no secret-looking dump fields
    assert "raw_result" not in payload
    assert "api_key" not in json.dumps(payload).lower()


def test_project_brief_omits_strata_but_keeps_gaps() -> None:
    service = ResearchApiService(history_service=object())
    payload = service.project_conclusion(_record_with_strata(), mode="brief")
    assert payload["mode"] == "brief"
    assert payload["conclusion"]["report_strata"] is None
    assert payload["conclusion"]["gaps"]
    assert payload["conclusion"].get("positive_catalysts") is None
    assert len(payload["conclusion"]["risks"]) <= 1


def test_project_research_includes_extended_summary_fields() -> None:
    service = ResearchApiService(history_service=object())
    payload = service.project_conclusion(_record_with_strata(), mode="research")
    assert payload["mode"] == "research"
    assert payload["conclusion"]["analysis_summary"]
    assert payload["conclusion"]["trend_prediction"]
    assert payload["conclusion"]["report_strata"] is not None


def test_get_by_record_id_not_found() -> None:
    class _Hist:
        def get_history_detail_by_id(self, record_id: int):
            return None

    service = ResearchApiService(history_service=_Hist())
    with pytest.raises(ResearchApiNotFoundError):
        service.get_conclusion_by_record_id(99)


def test_invalid_record_id() -> None:
    service = ResearchApiService(history_service=object())
    with pytest.raises(ResearchApiValidationError):
        service.get_conclusion_by_record_id(0)


def test_project_missing_record_id_is_not_found() -> None:
    service = ResearchApiService(history_service=object())
    broken = _record_with_strata()
    broken["id"] = None
    with pytest.raises(ResearchApiNotFoundError):
        service.project_conclusion(broken, mode="standard")


def test_latest_for_stock_uses_list_then_detail() -> None:
    class _Hist:
        def get_history_list(self, **kwargs):
            assert kwargs["stock_code"] == "600519"
            return {"total": 1, "items": [{"id": 42}]}

        def get_history_detail_by_id(self, record_id: int):
            assert record_id == 42
            return _record_with_strata()

    service = ResearchApiService(history_service=_Hist())
    payload = service.get_latest_conclusion_for_stock("600519", mode="standard")
    assert payload["metadata"]["record_id"] == 42
