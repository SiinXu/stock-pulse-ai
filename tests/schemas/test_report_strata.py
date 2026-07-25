# -*- coding: utf-8 -*-
"""Unit tests and fixture coverage for report strata (Issue #616)."""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from src.schemas.report_schema import AnalysisReportSchema, Dashboard
from src.schemas.report_strata import (
    REPORT_STRATA_SCHEMA_VERSION,
    DataGapOrConflict,
    FrameworkAlignment,
    ReportStrata,
    VerifiedFact,
    default_disclaimer,
    empty_report_strata,
    ensure_report_strata,
    extract_report_strata_payload,
    normalize_report_strata,
    resolve_report_strata,
)


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "report_strata"


def _load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


class TestReportStrataSchema(unittest.TestCase):
    def test_empty_report_strata_has_six_contract_fields(self) -> None:
        strata = empty_report_strata("en")
        data = strata.to_public_dict()
        self.assertEqual(data["schema_version"], REPORT_STRATA_SCHEMA_VERSION)
        self.assertEqual(data["verified_facts"], [])
        self.assertEqual(data["missing_or_conflicts"], [])
        self.assertEqual(data["model_inference"], [])
        self.assertEqual(data["risks_counter_evidence"], [])
        self.assertEqual(data["framework_alignment"]["status"], "not_configured")
        self.assertIn("not configured", data["framework_alignment"]["summary"].lower())
        self.assertTrue(data["disclaimer"])
        self.assertIn("Not investment advice", data["disclaimer"])

    def test_disclaimer_always_present_after_normalize(self) -> None:
        strata = normalize_report_strata(
            {
                "verified_facts": [],
                "model_inference": ["x"],
                "disclaimer": "   ",
            },
            language="en",
        )
        self.assertIsNotNone(strata)
        assert strata is not None
        self.assertEqual(strata.disclaimer, default_disclaimer("en"))

    def test_framework_defaults_to_not_configured(self) -> None:
        strata = ensure_report_strata(None, language="zh")
        self.assertEqual(strata.framework_alignment.status, "not_configured")
        self.assertIn("未配置", strata.framework_alignment.summary)

    def test_inference_not_merged_into_facts(self) -> None:
        strata = ReportStrata(
            verified_facts=[
                VerifiedFact(
                    statement="Close was 10.0",
                    source_id="ohlcv",
                    as_of="2026-07-25T15:00:00+08:00",
                )
            ],
            model_inference=["Price may rise next week."],
            risks_counter_evidence=["Downside if support fails."],
            framework_alignment=FrameworkAlignment(status="not_configured"),
            disclaimer=default_disclaimer("en"),
        )
        statements = {fact.statement for fact in strata.verified_facts}
        self.assertNotIn("Price may rise next week.", statements)
        self.assertEqual(len(strata.model_inference), 1)
        self.assertEqual(len(strata.verified_facts), 1)

    def test_historical_without_strata_still_validates(self) -> None:
        payload = _load_fixture("historical_without_strata.json")
        schema = AnalysisReportSchema.model_validate(payload)
        self.assertIsNone(schema.report_strata)
        self.assertIsNotNone(schema.dashboard)
        assert schema.dashboard is not None
        self.assertIsNone(schema.dashboard.report_strata)
        self.assertIsNone(normalize_report_strata(None))
        self.assertIsNone(resolve_report_strata(payload))

    def test_new_report_with_dashboard_strata_parses(self) -> None:
        payload = _load_fixture("new_report_with_strata.json")
        schema = AnalysisReportSchema.model_validate(payload)
        self.assertIsNotNone(schema.dashboard)
        assert schema.dashboard is not None
        self.assertIsNotNone(schema.dashboard.report_strata)
        strata = resolve_report_strata(payload)
        self.assertIsNotNone(strata)
        assert strata is not None
        self.assertEqual(len(strata.verified_facts), 1)
        self.assertTrue(strata.disclaimer)

    def test_full_fixture_round_trip(self) -> None:
        payload = _load_fixture("full_strata.json")
        strata = ReportStrata.model_validate(payload)
        self.assertEqual(len(strata.verified_facts), 2)
        self.assertEqual(strata.missing_or_conflicts[0].kind, "conflict")
        self.assertEqual(strata.framework_alignment.status, "partial")
        restored = ReportStrata.model_validate(strata.to_public_dict())
        self.assertEqual(restored.model_dump(), strata.model_dump())

    def test_empty_sources_fixture(self) -> None:
        payload = _load_fixture("empty_sources.json")
        strata = normalize_report_strata(payload, language="en")
        self.assertIsNotNone(strata)
        assert strata is not None
        for fact in strata.verified_facts:
            self.assertTrue(fact.statement)
            self.assertTrue(fact.source_id is None or fact.source_id == "")
        self.assertTrue(
            any(gap.kind == "missing" for gap in strata.missing_or_conflicts)
        )

    def test_source_conflicts_fixture(self) -> None:
        payload = _load_fixture("source_conflicts.json")
        strata = ReportStrata.model_validate(payload)
        conflict_items = [
            item for item in strata.missing_or_conflicts if item.kind == "conflict"
        ]
        self.assertGreaterEqual(len(conflict_items), 2)
        for item in conflict_items:
            self.assertGreaterEqual(len(item.source_ids), 1)
        self.assertEqual(strata.framework_alignment.status, "conflict")

    def test_missing_timestamps_fixture(self) -> None:
        payload = _load_fixture("missing_timestamps.json")
        strata = ReportStrata.model_validate(payload)
        self.assertTrue(any(fact.as_of is None for fact in strata.verified_facts))
        self.assertTrue(
            any(
                "timestamp" in gap.description.lower()
                or "as-of" in gap.description.lower()
                for gap in strata.missing_or_conflicts
            )
        )

    def test_extract_prefers_dashboard_nested_payload(self) -> None:
        nested = {
            "report_strata": {"model_inference": ["top-level"]},
            "dashboard": {
                "report_strata": {
                    "model_inference": ["dashboard-level"],
                    "disclaimer": default_disclaimer("en"),
                }
            },
        }
        raw = extract_report_strata_payload(nested)
        self.assertEqual(raw.get("model_inference"), ["dashboard-level"])
        resolved = resolve_report_strata(nested, language="en")
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.model_inference, ["dashboard-level"])

    def test_dashboard_model_accepts_report_strata(self) -> None:
        dashboard = Dashboard.model_validate(
            {
                "core_conclusion": {"one_sentence": "hold"},
                "report_strata": empty_report_strata("zh").to_public_dict(),
            }
        )
        self.assertIsNotNone(dashboard.report_strata)
        assert dashboard.report_strata is not None
        self.assertEqual(
            dashboard.report_strata.schema_version, REPORT_STRATA_SCHEMA_VERSION
        )

    def test_gap_kind_validation(self) -> None:
        gap = DataGapOrConflict(
            kind="conflict",
            description="A vs B mismatch",
            source_ids=["a", "b"],
        )
        self.assertEqual(gap.kind, "conflict")
        with self.assertRaises(Exception):
            DataGapOrConflict(kind="unknown", description="x")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
