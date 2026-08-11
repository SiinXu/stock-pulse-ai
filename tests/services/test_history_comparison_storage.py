from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta
from typing import Any, Optional
from unittest.mock import patch

from src.config import Config
from src.services.history_comparison_service import (
    BASELINE_INCOMPARABLE,
    BASELINE_MISSING_BASE,
    BASELINE_MISSING_HISTORY,
    BASELINE_MISSING_TARGET,
    BASELINE_OK,
    DIRECTION_DOWN,
    DIRECTION_UP,
    compare_analyses,
    get_latest_delta,
)
from src.storage import AnalysisHistory, DatabaseManager


def _raw_payload(
    *,
    score: Any = 50,
    operation_advice: str = "Hold",
    key_points: Optional[list[str]] = None,
    risks: Optional[list[str]] = None,
    dimension_score: Any = 50,
    stop_loss: Any = 100.0,
) -> str:
    return json.dumps(
        {
            "operation_advice": operation_advice,
            "action": "buy" if operation_advice == "Buy" else "hold",
            "sentiment_score": score,
            "key_points": key_points or [],
            "risk_warning": risks or [],
            "dashboard": {
                "data_perspective": {
                    "trend_status": {"trend_score": dimension_score},
                },
                "battle_plan": {
                    "sniper_points": {"stop_loss": stop_loss},
                },
            },
        },
        allow_nan=True,
    )


class HistoryComparisonStorageTestCase(unittest.TestCase):
    """Exercise delta identity and ordering against real SQLite storage."""

    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._original_env = {
            key: os.environ.get(key)
            for key in (
                "ENV_FILE",
                "DATABASE_PATH",
            )
        }
        env_path = os.path.join(self._temp_dir.name, ".env")
        with open(env_path, "w", encoding="utf-8") as env_file:
            env_file.write("STOCK_LIST=600519,AAPL\n")
        os.environ["ENV_FILE"] = env_path
        os.environ["DATABASE_PATH"] = os.path.join(
            self._temp_dir.name,
            "history-comparison.db",
        )
        Config._instance = None
        DatabaseManager.reset_instance()
        self.db = DatabaseManager.get_instance()

    def tearDown(self) -> None:
        DatabaseManager.reset_instance()
        Config._instance = None
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._temp_dir.cleanup()

    def _insert(
        self,
        *,
        code: str = "600519",
        query_id: Optional[str] = "query",
        report_type: Optional[str] = "simple",
        created_at: Optional[datetime] = None,
        score: int = 50,
        operation_advice: str = "Hold",
        raw_result: Optional[str] = None,
        stop_loss: Optional[float] = None,
    ) -> int:
        with self.db.session_scope() as session:
            row = AnalysisHistory(
                query_id=query_id,
                code=code,
                name=code,
                report_type=report_type,
                sentiment_score=score,
                operation_advice=operation_advice,
                trend_prediction="Bullish",
                raw_result=(
                    raw_result
                    if raw_result is not None
                    else _raw_payload(score=score, operation_advice=operation_advice)
                ),
                stop_loss=stop_loss,
                created_at=created_at or datetime.now(),
            )
            session.add(row)
            session.flush()
            return int(row.id)

    @staticmethod
    def _score_change(delta: Any) -> Any:
        return next(
            item for item in delta.score_changes if item.field == "sentiment_score"
        )

    def test_duplicate_query_id_never_collapses_two_versions(self) -> None:
        base_id = self._insert(
            query_id="duplicate",
            created_at=datetime(2026, 1, 1, 9, 0),
            score=20,
        )
        target_id = self._insert(
            query_id="duplicate",
            created_at=datetime(2026, 1, 2, 9, 0),
            score=45,
        )

        delta = get_latest_delta("600519", "simple")

        self.assertEqual(delta.base_record_id, base_id)
        self.assertEqual(delta.target_record_id, target_id)
        self.assertEqual(delta.base_query_id, "duplicate")
        self.assertEqual(delta.target_query_id, "duplicate")
        self.assertEqual(self._score_change(delta).delta, 25.0)

    def test_batch_query_id_is_scoped_by_stock_code(self) -> None:
        base_id = self._insert(
            code="600519",
            query_id="batch",
            created_at=datetime(2026, 2, 1, 9, 0),
            score=10,
        )
        target_id = self._insert(
            code="600519",
            query_id="batch",
            created_at=datetime(2026, 2, 2, 9, 0),
            score=30,
        )
        self._insert(
            code="AAPL",
            query_id="batch",
            created_at=datetime(2026, 2, 3, 9, 0),
            score=99,
        )

        delta = get_latest_delta("600519", "simple")

        self.assertEqual((delta.base_record_id, delta.target_record_id), (base_id, target_id))
        self.assertEqual(self._score_change(delta).delta, 20.0)

    def test_retried_and_recovered_rows_keep_distinct_versions(self) -> None:
        self._insert(
            query_id="retry-chain",
            created_at=datetime(2026, 3, 1, 9, 0),
            score=10,
        )
        retry_id = self._insert(
            query_id="retry-chain",
            created_at=datetime(2026, 3, 1, 9, 1),
            score=20,
        )
        recovered_id = self._insert(
            query_id="retry-chain",
            created_at=datetime(2026, 3, 1, 9, 2),
            score=35,
        )

        delta = get_latest_delta("600519", "simple")

        self.assertEqual(
            (delta.base_record_id, delta.target_record_id),
            (retry_id, recovered_id),
        )
        self.assertEqual(self._score_change(delta).delta, 15.0)

    def test_timestamp_tie_uses_primary_key_as_descending_tiebreaker(self) -> None:
        tied_at = datetime(2026, 4, 1, 9, 0)
        base_id = self._insert(created_at=tied_at, score=60)
        target_id = self._insert(created_at=tied_at, score=40)

        rows = self.db.get_analysis_history(
            code="600519",
            report_type="simple",
            days=None,
            limit=2,
        )
        delta = get_latest_delta("600519", "simple")

        self.assertEqual([row.id for row in rows], [target_id, base_id])
        self.assertEqual((delta.base_record_id, delta.target_record_id), (base_id, target_id))
        self.assertEqual(self._score_change(delta).direction, DIRECTION_DOWN)

    def test_batch_history_is_bounded_per_code_and_filters_window(self) -> None:
        self._insert(
            code="600519",
            created_at=datetime(2026, 7, 31, 9, 0),
            score=10,
        )
        first_a = self._insert(
            code="600519",
            created_at=datetime(2026, 8, 1, 9, 0),
            score=20,
        )
        second_a = self._insert(
            code="600519",
            created_at=datetime(2026, 8, 2, 9, 0),
            score=30,
        )
        first_us = self._insert(
            code="AAPL",
            created_at=datetime(2026, 8, 1, 8, 0),
            score=40,
        )

        rows = self.db.get_analysis_history_batch(
            codes=["600519", "AAPL"],
            created_at_from=datetime(2026, 8, 1, 0, 0),
            limit_per_code=2,
        )
        ids_by_code = {
            code: [row.id for row in rows if row.code == code]
            for code in ("600519", "AAPL")
        }

        self.assertEqual(ids_by_code["600519"], [second_a, first_a])
        self.assertEqual(ids_by_code["AAPL"], [first_us])

    def test_latest_delta_has_no_hidden_365_day_cutoff(self) -> None:
        base_id = self._insert(
            created_at=datetime.now() - timedelta(days=800),
            score=15,
        )
        target_id = self._insert(created_at=datetime.now(), score=25)

        delta = get_latest_delta("600519", "simple")

        self.assertTrue(delta.has_baseline)
        self.assertEqual(delta.baseline_status, BASELINE_OK)
        self.assertEqual((delta.base_record_id, delta.target_record_id), (base_id, target_id))

    def test_exact_primary_key_lookup_same_record_and_missing_rows(self) -> None:
        base_id = self._insert(query_id="same-correlation", score=10)
        target_id = self._insert(query_id="same-correlation", score=30)

        exact = compare_analyses("600519", base_id, target_id)
        same = compare_analyses("600519", base_id, base_id)
        missing_base = compare_analyses("600519", 999_991, target_id)
        missing_target = compare_analyses("600519", base_id, 999_992)

        self.assertEqual(self._score_change(exact).delta, 20.0)
        self.assertTrue(same.has_baseline)
        self.assertFalse(same.has_material_changes)
        self.assertEqual(same.base_record_id, same.target_record_id)
        self.assertEqual(missing_base.baseline_status, BASELINE_MISSING_BASE)
        self.assertEqual(missing_target.baseline_status, BASELINE_MISSING_TARGET)

    def test_deleted_record_is_reported_as_missing_not_no_change(self) -> None:
        base_id = self._insert(score=10)
        target_id = self._insert(score=20)
        self.assertEqual(self.db.delete_analysis_history_records([base_id]), 1)

        delta = compare_analyses("600519", base_id, target_id)

        self.assertFalse(delta.has_baseline)
        self.assertEqual(delta.baseline_status, BASELINE_MISSING_BASE)

    def test_report_type_boundary_filters_latest_and_rejects_cross_type(self) -> None:
        simple_base = self._insert(
            report_type="simple",
            created_at=datetime(2026, 5, 1, 9, 0),
            score=10,
        )
        simple_target = self._insert(
            report_type="simple",
            created_at=datetime(2026, 5, 2, 9, 0),
            score=20,
        )
        full_newest = self._insert(
            report_type="full",
            created_at=datetime(2026, 5, 3, 9, 0),
            score=99,
        )

        latest_simple = get_latest_delta("600519", "simple")
        cross_type = compare_analyses("600519", simple_target, full_newest)

        self.assertEqual(
            (latest_simple.base_record_id, latest_simple.target_record_id),
            (simple_base, simple_target),
        )
        self.assertEqual(cross_type.baseline_status, BASELINE_INCOMPARABLE)
        self.assertIn("report_type", cross_type.baseline_reason or "")

    def test_batch_record_from_another_stock_is_incomparable_by_primary_key(self) -> None:
        base_id = self._insert(code="600519", query_id="batch", score=10)
        other_stock_id = self._insert(code="AAPL", query_id="batch", score=20)

        delta = compare_analyses("600519", base_id, other_stock_id)

        self.assertEqual(delta.baseline_status, BASELINE_INCOMPARABLE)
        self.assertIn("stock_code", delta.baseline_reason or "")

    def test_concurrent_insert_after_latest_selection_does_not_redirect_pair(self) -> None:
        base_id = self._insert(created_at=datetime(2026, 6, 1, 9, 0), score=10)
        target_id = self._insert(created_at=datetime(2026, 6, 2, 9, 0), score=20)
        original_get = self.db.get_analysis_history
        calls = 0

        def _select_then_insert(**kwargs: Any) -> list[AnalysisHistory]:
            nonlocal calls
            calls += 1
            selected = original_get(**kwargs)
            self._insert(created_at=datetime(2026, 6, 3, 9, 0), score=90)
            return selected

        with patch.object(self.db, "get_analysis_history", side_effect=_select_then_insert):
            delta = get_latest_delta("600519", "simple")

        self.assertEqual(calls, 1)
        self.assertEqual((delta.base_record_id, delta.target_record_id), (base_id, target_id))
        self.assertEqual(self._score_change(delta).delta, 10.0)

    def test_concurrent_delete_after_latest_selection_uses_selected_values(self) -> None:
        base_id = self._insert(created_at=datetime(2026, 7, 1, 9, 0), score=25)
        target_id = self._insert(created_at=datetime(2026, 7, 2, 9, 0), score=50)
        original_get = self.db.get_analysis_history
        calls = 0

        def _select_then_delete(**kwargs: Any) -> list[AnalysisHistory]:
            nonlocal calls
            calls += 1
            selected = original_get(**kwargs)
            self.db.delete_analysis_history_records([base_id, target_id])
            return selected

        with patch.object(self.db, "get_analysis_history", side_effect=_select_then_delete):
            delta = get_latest_delta("600519", "simple")

        self.assertEqual(calls, 1)
        self.assertEqual((delta.base_record_id, delta.target_record_id), (base_id, target_id))
        self.assertEqual(self._score_change(delta).delta, 25.0)

    def test_strict_json_round_trip_at_real_storage_boundary(self) -> None:
        base_id = self._insert(
            score=10,
            raw_result=_raw_payload(
                score=10,
                key_points=["base evidence"],
                risks=["base risk"],
                dimension_score=0,
                stop_loss=100.0,
            ),
        )
        target_id = self._insert(
            score=20,
            raw_result=_raw_payload(
                score=20,
                operation_advice="Buy",
                key_points=["target evidence"],
                risks=["target risk"],
                dimension_score=float("inf"),
                stop_loss=float("nan"),
            ),
        )

        payload = compare_analyses("600519", base_id, target_id).to_dict()
        encoded = json.dumps(payload, allow_nan=False)

        self.assertEqual(json.loads(encoded), payload)
        self.assertTrue(payload["conclusion_changes"])
        self.assertTrue(payload["score_changes"])
        self.assertTrue(payload["evidence_changes"])
        self.assertTrue(payload["risk_changes"])

    def test_malformed_raw_history_still_compares_persisted_columns(self) -> None:
        base_id = self._insert(
            query_id=None,
            score=5,
            operation_advice="Hold",
            raw_result="{malformed",
        )
        target_id = self._insert(
            query_id=None,
            score=15,
            operation_advice="Buy",
            raw_result="not-json",
        )

        delta = compare_analyses("600519", base_id, target_id)

        self.assertTrue(delta.has_baseline)
        self.assertEqual(self._score_change(delta).direction, DIRECTION_UP)
        self.assertIsNone(delta.base_query_id)
        self.assertIsNone(delta.target_query_id)

    def test_real_storage_distinguishes_no_baseline_from_no_change(self) -> None:
        empty = get_latest_delta("600519", "simple")
        only_id = self._insert(score=50)
        only = get_latest_delta("600519", "simple")
        same_id = self._insert(score=50)
        no_change = get_latest_delta("600519", "simple")

        self.assertEqual(empty.baseline_status, BASELINE_MISSING_HISTORY)
        self.assertEqual(only.baseline_status, BASELINE_MISSING_HISTORY)
        self.assertEqual(only.target_record_id, only_id)
        self.assertTrue(no_change.has_baseline)
        self.assertEqual(no_change.baseline_status, BASELINE_OK)
        self.assertFalse(no_change.has_material_changes)
        self.assertEqual((no_change.base_record_id, no_change.target_record_id), (only_id, same_id))


if __name__ == "__main__":
    unittest.main()
