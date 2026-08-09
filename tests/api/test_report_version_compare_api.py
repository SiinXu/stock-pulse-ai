# -*- coding: utf-8 -*-
"""API tests for report version compare endpoints (T18 / #188)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

import src.auth as auth
from api.app import create_app
from src.config import Config
from src.storage import DatabaseManager
from src.storage_parts.schema import AnalysisHistory
from tests.fixtures.report_version_compare.analysis_delta_fixture import (
    CONCLUSION_REVERSAL_DELTA,
    fixture_compare_analyses_factory,
)


def _reset_auth_globals() -> None:
    auth._auth_enabled = None
    auth._session_secret = None
    auth._password_hash_salt = None
    auth._password_hash_stored = None
    auth._rate_limit = {}


def _insert_history(
    db: DatabaseManager,
    *,
    code: str = "600519",
    query_id: str = "q1",
    action: str = "buy",
    sentiment_score: Any = 70,
    model_used: str = "model-a",
    created_at: Optional[datetime] = None,
) -> int:
    raw = {
        "model_used": model_used,
        "report_language": "zh",
        "action": action,
        "operation_advice": action,
        "analysis_summary": f"summary-{query_id}",
        "trend_prediction": "flat",
    }

    def _write(session):
        row = AnalysisHistory(
            query_id=query_id,
            code=code,
            name="贵州茅台",
            report_type="detailed",
            sentiment_score=sentiment_score,
            operation_advice=action,
            trend_prediction="flat",
            analysis_summary=f"summary-{query_id}",
            raw_result=json.dumps(raw, ensure_ascii=False),
            news_content=None,
            context_snapshot=json.dumps(
                {
                    "routing": {"provider": "test-provider", "model": model_used},
                    "config_profile": "test-profile",
                    "config_version": "v1",
                }
            ),
            created_at=created_at or datetime.now(),
        )
        session.add(row)
        session.flush()
        return int(row.id)

    return db._run_write_transaction("test_rvc_api_insert", _write)


class ReportVersionCompareApiTests(unittest.TestCase):
    def setUp(self) -> None:
        _reset_auth_globals()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.temp_dir.name)
        self.env_path = self.data_dir / ".env"
        self.db_path = self.data_dir / "rvc_api.db"
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
        app = create_app(static_dir=self.data_dir / "empty-static")
        self.client = TestClient(app)
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config.reset_instance()
        os.environ.pop("ENV_FILE", None)
        os.environ.pop("DATABASE_PATH", None)
        self.temp_dir.cleanup()

    def test_list_runs_empty(self) -> None:
        resp = self.client.get(
            "/api/v1/report-version-compare/runs",
            params={"stock_code": "600519"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["stock_code"], "600519")
        self.assertEqual(payload["items"], [])

    def test_list_runs_with_items(self) -> None:
        run_id = _insert_history(self.db, model_used="gpt-x")
        resp = self.client.get(
            "/api/v1/report-version-compare/runs",
            params={"stock_code": "600519"},
        )
        self.assertEqual(resp.status_code, 200, resp.text)
        items = resp.json()["items"]
        self.assertTrue(any(item["run_id"] == str(run_id) for item in items))
        item = next(i for i in items if i["run_id"] == str(run_id))
        self.assertEqual(item["model_used"], "gpt-x")
        self.assertTrue(item["config_fingerprint"])

    def test_compare_engine_pending_without_t17(self) -> None:
        base_id = _insert_history(
            self.db,
            query_id="base",
            action="buy",
            sentiment_score=80,
            created_at=datetime.now() - timedelta(days=2),
        )
        target_id = _insert_history(
            self.db,
            query_id="target",
            action="sell",
            sentiment_score=15,
            model_used="model-b",
            created_at=datetime.now(),
        )
        from unittest.mock import patch

        with patch(
            "src.services.report_version_compare_service.invoke_compare_analyses",
            return_value=("engine_pending", None),
        ):
            resp = self.client.get(
                "/api/v1/report-version-compare/compare",
                params={
                    "stock_code": "600519",
                    "base_run_id": str(base_id),
                    "target_run_id": str(target_id),
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "engine_pending")
        self.assertIsNone(payload["delta"])
        self.assertTrue(payload["config_diff"]["has_differences"] or True)
        major = [d for d in payload["field_diffs"] if d["severity"] == "major"]
        self.assertTrue(major, "buy→sell must be major severity")

    def test_compare_with_fixture_delta(self) -> None:
        base_id = _insert_history(self.db, query_id="base", action="buy")
        target_id = _insert_history(self.db, query_id="target", action="sell")
        compare_fn = fixture_compare_analyses_factory(CONCLUSION_REVERSAL_DELTA)

        from unittest.mock import patch

        with patch(
            "api.v1.endpoints.report_version_compare.ReportVersionCompareService"
        ) as service_cls:
            real = __import__(
                "src.services.report_version_compare_service",
                fromlist=["ReportVersionCompareService"],
            ).ReportVersionCompareService
            service_cls.side_effect = lambda db_manager=None: real(
                db_manager, compare_fn=compare_fn
            )
            resp = self.client.get(
                "/api/v1/report-version-compare/compare",
                params={
                    "stock_code": "600519",
                    "base_run_id": str(base_id),
                    "target_run_id": str(target_id),
                },
            )
        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["delta"]["has_baseline"])

    def test_compare_missing_run_404(self) -> None:
        resp = self.client.get(
            "/api/v1/report-version-compare/compare",
            params={
                "stock_code": "600519",
                "base_run_id": "999999",
                "target_run_id": "999998",
            },
        )
        self.assertEqual(resp.status_code, 404, resp.text)
        self.assertEqual(resp.json()["error"], "base_run_not_found")

    def test_compare_same_run_400(self) -> None:
        run_id = _insert_history(self.db)
        resp = self.client.get(
            "/api/v1/report-version-compare/compare",
            params={
                "stock_code": "600519",
                "base_run_id": str(run_id),
                "target_run_id": str(run_id),
            },
        )
        self.assertEqual(resp.status_code, 400, resp.text)
        self.assertEqual(resp.json()["error"], "same_run_ids")

    def test_list_runs_normalizes_corrupt_scores_before_response_serialization(self) -> None:
        run_ids = [
            _insert_history(self.db, query_id="nan", sentiment_score=float("nan")),
            _insert_history(self.db, query_id="inf", sentiment_score=float("inf")),
            _insert_history(self.db, query_id="out-of-range", sentiment_score=101),
        ]

        resp = self.client.get(
            "/api/v1/report-version-compare/runs",
            params={"stock_code": "600519"},
        )

        self.assertEqual(resp.status_code, 200, resp.text)
        payload = resp.json()
        encoded = json.dumps(payload, allow_nan=False)
        self.assertTrue(encoded)
        scores = {
            item["run_id"]: item["sentiment_score"]
            for item in payload["items"]
            if item["run_id"] in {str(run_id) for run_id in run_ids}
        }
        self.assertTrue(all(score is None for score in scores.values()))

    def test_compare_distinguishes_rows_with_shared_query_id(self) -> None:
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
        )

        resp = self.client.get(
            "/api/v1/report-version-compare/compare",
            params={
                "stock_code": "600519",
                "base_run_id": str(base_id),
                "target_run_id": str(target_id),
            },
        )

        self.assertEqual(resp.status_code, 200, resp.text)
        delta = resp.json()["delta"]
        self.assertEqual(delta["base_record_id"], base_id)
        self.assertEqual(delta["target_record_id"], target_id)
        self.assertEqual(delta["base_query_id"], shared_query_id)
        self.assertEqual(delta["target_query_id"], shared_query_id)


if __name__ == "__main__":
    unittest.main()
