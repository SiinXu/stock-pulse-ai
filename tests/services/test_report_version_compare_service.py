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
    report_type: str = "detailed",
    action: str = "buy",
    sentiment_score: int = 75,
    model_used: str = "gpt-test",
    report_language: str = "zh",
    operation_advice: str = "买入",
    trend_prediction: str = "上行",
    analysis_summary: str = "summary-a",
    created_at: Optional[datetime] = None,
    extra_raw: Optional[Dict[str, Any]] = None,
    context_snapshot: Optional[Dict[str, Any]] = None,
) -> int:
    raw = {
        "model_used": model_used,
        "report_language": report_language,
        "action": action,
        "operation_advice": operation_advice,
        "analysis_summary": analysis_summary,
        "trend_prediction": trend_prediction,
    }
    if extra_raw:
        raw.update(extra_raw)

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
            context_snapshot=json.dumps(context_snapshot or {}, ensure_ascii=False),
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
        self.assertEqual(result["delta"]["base_run_id"], str(base_id))
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


if __name__ == "__main__":
    unittest.main()
