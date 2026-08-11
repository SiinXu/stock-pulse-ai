# -*- coding: utf-8 -*-
"""Unit tests for report version compare service (T18 / #188)."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from src.config import Config
from src.services.report_version_compare_service import (
    SEVERITY_MAJOR,
    SEVERITY_MINOR,
    SEVERITY_MODERATE,
    SEVERITY_NONE,
    ReportVersionCompareError,
    ReportVersionCompareService,
)
from src.storage import DatabaseManager
from src.storage_parts.schema import AnalysisHistory
from tests.fixtures.report_version_compare.analysis_delta_fixture import (
    CONCLUSION_REVERSAL_DELTA,
    NO_BASELINE_DELTA,
    fixture_compare_analyses_factory,
)


def _insert_history(
    db: DatabaseManager,
    *,
    code: str = "600519",
    name: str = "贵州茅台",
    query_id: str = "q1",
    report_type: Optional[str] = "detailed",
    action: str = "buy",
    sentiment_score: Any = 75,
    model_used: str = "gpt-test",
    report_language: Any = "zh",
    operation_advice: str = "买入",
    trend_prediction: str = "上行",
    analysis_summary: str = "summary-a",
    created_at: Optional[datetime] = None,
    extra_raw: Optional[Dict[str, Any]] = None,
    context_snapshot: Optional[Dict[str, Any]] = None,
) -> int:
    raw = {
        "model_used": model_used,
        "action": action,
        "operation_advice": operation_advice,
        "analysis_summary": analysis_summary,
        "trend_prediction": trend_prediction,
    }
    if report_language is not None:
        raw["report_language"] = report_language
    if extra_raw:
        raw.update(extra_raw)

    persisted_context = (
        {
            "routing": {"provider": "test-provider", "model": model_used},
            "config_profile": "test-profile",
            "config_version": "v1",
        }
        if context_snapshot is None
        else context_snapshot
    )

    def _write(session):
        row = AnalysisHistory(
            query_id=query_id,
            code=code,
            name=name,
            report_type=report_type,
            sentiment_score=sentiment_score,
            operation_advice=operation_advice,
            trend_prediction=trend_prediction,
            analysis_summary=analysis_summary,
            raw_result=json.dumps(raw, ensure_ascii=False),
            news_content=None,
            context_snapshot=json.dumps(persisted_context, ensure_ascii=False),
            created_at=created_at or datetime.now(),
        )
        session.add(row)
        session.flush()
        return int(row.id)

    return db._run_write_transaction("test_insert_history", _write)


class ReportVersionCompareServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "rvc.db"
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "GEMINI_API_KEY=test",
                    "ADMIN_AUTH_ENABLED=false",
                    f"DATABASE_PATH={self.db_path}",
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        os.environ["DATABASE_PATH"] = str(self.db_path)
        Config.reset_instance()
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def test_list_runs_returns_fingerprint_and_model(self) -> None:
        run_id = _insert_history(self.db, model_used="model-a")
        service = ReportVersionCompareService(self.db)
        result = service.list_runs("600519", page=1, limit=20)
        self.assertGreaterEqual(result["total"], 1)
        item = next(i for i in result["items"] if i["run_id"] == str(run_id))
        self.assertEqual(item["model_used"], "model-a")
        self.assertTrue(item["config_fingerprint"])
        self.assertTrue(item["config_complete"])
        self.assertIn("model_used", item["config_components"])
        self.assertEqual(item["config_components"]["model_used"], "model-a")

    def test_compare_engine_pending_without_t17(self) -> None:
        base_id = _insert_history(
            self.db,
            query_id="base",
            action="buy",
            sentiment_score=80,
            model_used="model-a",
            created_at=datetime.now() - timedelta(days=1),
        )
        target_id = _insert_history(
            self.db,
            query_id="target",
            action="sell",
            sentiment_score=20,
            model_used="model-b",
            analysis_summary="summary-b",
            created_at=datetime.now(),
            extra_raw={"report_language": "en"},
        )
        from unittest.mock import patch

        # Simulate T17 not merged: adapter has no compare_analyses.
        with patch(
            "src.services.report_version_compare_adapter.resolve_compare_analyses",
            return_value=None,
        ):
            service = ReportVersionCompareService(self.db, compare_fn=None)
            result = service.compare_runs("600519", str(base_id), str(target_id))

        self.assertEqual(result["status"], "engine_pending")
        self.assertEqual(result["engine_status"], "engine_pending")
        self.assertIsNone(result["delta"])
        self.assertTrue(result["config_diff"]["has_differences"])
        action_diff = next(d for d in result["field_diffs"] if d["field"] == "action")
        self.assertTrue(action_diff["changed"])
        self.assertEqual(action_diff["severity"], SEVERITY_MAJOR)

    def test_compare_with_fixture_t17_delta(self) -> None:
        base_id = _insert_history(self.db, query_id="base", action="buy", sentiment_score=80)
        target_id = _insert_history(self.db, query_id="target", action="sell", sentiment_score=25)
        compare_fn = fixture_compare_analyses_factory(CONCLUSION_REVERSAL_DELTA)
        service = ReportVersionCompareService(self.db, compare_fn=compare_fn)
        result = service.compare_runs("600519", str(base_id), str(target_id))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["engine_status"], "ok")
        self.assertIsNotNone(result["delta"])
        assert result["delta"] is not None
        self.assertTrue(result["delta"]["has_baseline"])
        self.assertEqual(result["delta"]["base_record_id"], base_id)
        self.assertEqual(result["delta"]["target_record_id"], target_id)
        self.assertEqual(len(result["delta"]["conclusion_changes"]), 1)

    def test_no_baseline_is_not_no_change(self) -> None:
        base_id = _insert_history(self.db, query_id="base", action="hold", sentiment_score=50)
        target_id = _insert_history(self.db, query_id="target", action="hold", sentiment_score=50)
        compare_fn = fixture_compare_analyses_factory(NO_BASELINE_DELTA)
        service = ReportVersionCompareService(self.db, compare_fn=compare_fn)
        result = service.compare_runs("600519", str(base_id), str(target_id))
        self.assertEqual(result["status"], "no_baseline")
        self.assertIsNotNone(result["delta"])
        assert result["delta"] is not None
        self.assertFalse(result["delta"]["has_baseline"])
        # Field diffs may show none/minor, but status must remain no_baseline
        action_diff = next(d for d in result["field_diffs"] if d["field"] == "action")
        self.assertFalse(action_diff["changed"])
        self.assertEqual(action_diff["severity"], SEVERITY_NONE)

    def test_same_run_ids_rejected(self) -> None:
        run_id = _insert_history(self.db)
        service = ReportVersionCompareService(self.db)
        with self.assertRaises(ReportVersionCompareError) as ctx:
            service.compare_runs("600519", str(run_id), str(run_id))
        self.assertEqual(ctx.exception.code, "same_run_ids")

    def test_score_minor_severity(self) -> None:
        service = ReportVersionCompareService(self.db)
        severity = service._grade_field_severity("sentiment_score", 70, 72)
        self.assertEqual(severity, SEVERITY_MINOR)
        severity_major = service._grade_field_severity("action", "buy", "sell")
        self.assertEqual(severity_major, SEVERITY_MAJOR)
        severity_mod = service._grade_field_severity("action", "hold", "buy")
        self.assertEqual(severity_mod, SEVERITY_MODERATE)

    def test_market_review_filter_is_applied_before_count_and_pagination(self) -> None:
        eligible_old = _insert_history(
            self.db,
            query_id="eligible-old",
            created_at=datetime.now() - timedelta(days=3),
        )
        _insert_history(
            self.db,
            query_id="eligible-new",
            created_at=datetime.now() - timedelta(days=2),
        )
        eligible_without_type = _insert_history(
            self.db,
            query_id="eligible-without-type",
            report_type=None,
            created_at=datetime.now() - timedelta(days=1),
        )
        _insert_history(
            self.db,
            query_id="market-newest",
            report_type="market_review",
            created_at=datetime.now(),
        )

        service = ReportVersionCompareService(self.db)
        first_page = service.list_runs("600519", page=1, limit=1)
        second_page = service.list_runs("600519", page=2, limit=1)
        third_page = service.list_runs("600519", page=3, limit=1)

        self.assertEqual(first_page["total"], 3)
        self.assertEqual(second_page["total"], 3)
        self.assertEqual(third_page["total"], 3)
        returned = {
            first_page["items"][0]["run_id"],
            second_page["items"][0]["run_id"],
            third_page["items"][0]["run_id"],
        }
        self.assertIn(str(eligible_old), returned)
        self.assertIn(str(eligible_without_type), returned)
        self.assertTrue(
            all(item["report_type"] != "market_review" for item in first_page["items"])
        )

    def test_non_finite_and_out_of_range_scores_are_strict_json_safe(self) -> None:
        run_ids = [
            _insert_history(self.db, query_id="nan", sentiment_score=float("nan")),
            _insert_history(self.db, query_id="pos-inf", sentiment_score=float("inf")),
            _insert_history(self.db, query_id="neg-inf", sentiment_score=float("-inf")),
            _insert_history(self.db, query_id="out-of-range", sentiment_score=101),
        ]

        result = ReportVersionCompareService(self.db).list_runs("600519", limit=20)
        json.dumps(result, allow_nan=False)
        scores = {
            item["run_id"]: item["sentiment_score"]
            for item in result["items"]
            if item["run_id"] in {str(run_id) for run_id in run_ids}
        }
        self.assertEqual(set(scores), {str(run_id) for run_id in run_ids})
        self.assertTrue(all(score is None for score in scores.values()))

    def test_merged_engine_uses_primary_ids_when_query_id_is_shared(self) -> None:
        shared_query_id = "shared-query"
        base_id = _insert_history(
            self.db,
            query_id=shared_query_id,
            action="buy",
            sentiment_score=80,
            created_at=datetime.now() - timedelta(days=1),
        )
        target_id = _insert_history(
            self.db,
            query_id=shared_query_id,
            action="sell",
            sentiment_score=20,
            created_at=datetime.now(),
        )

        result = ReportVersionCompareService(self.db).compare_runs(
            "600519", str(base_id), str(target_id)
        )

        self.assertEqual(result["status"], "ok")
        delta = result["delta"]
        self.assertEqual(delta["base_record_id"], base_id)
        self.assertEqual(delta["target_record_id"], target_id)
        self.assertEqual(delta["base_query_id"], shared_query_id)
        self.assertEqual(delta["target_query_id"], shared_query_id)
        self.assertTrue(delta["has_material_changes"])
        json.dumps(result, allow_nan=False)

    def test_incomplete_config_is_unknown_not_identical(self) -> None:
        base_id = _insert_history(self.db, query_id="base", context_snapshot={})
        target_id = _insert_history(self.db, query_id="target", context_snapshot={})

        result = ReportVersionCompareService(self.db).compare_runs(
            "600519", str(base_id), str(target_id)
        )

        self.assertIsNone(result["base_run"]["config_fingerprint"])
        self.assertFalse(result["base_run"]["config_complete"])
        self.assertEqual(result["config_diff"]["comparison_status"], "unknown")
        self.assertFalse(result["config_diff"]["identical"])

    def test_missing_invalid_or_non_string_language_keeps_config_unknown(self) -> None:
        service = ReportVersionCompareService(self.db)

        persisted_languages = (
            None,
            "not-a-language",
            1,
            {"unexpected": "language"},
        )
        for index, persisted_language in enumerate(persisted_languages, start=1):
            with self.subTest(persisted_language=persisted_language):
                run_id = _insert_history(
                    self.db,
                    query_id=f"language-provenance-{index}",
                    report_language=persisted_language,
                )

                result = service.list_runs("600519", limit=20)
                item = next(
                    run for run in result["items"] if run["run_id"] == str(run_id)
                )

                self.assertEqual(item["report_language"], "zh")
                self.assertEqual(item["config_components"]["report_language"], "")
                self.assertFalse(item["config_complete"])
                self.assertIn("report_language", item["config_missing_keys"])
                self.assertIsNone(item["config_fingerprint"])


if __name__ == "__main__":
    unittest.main()
