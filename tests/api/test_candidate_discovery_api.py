# -*- coding: utf-8 -*-
"""API contracts for bounded candidate discovery (#177 / #325)."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from api.v1.endpoints import candidate_discovery as endpoint
from src.services.candidate_discovery_service import DiscoveryValidationError
from src.services.task_queue import TaskStatus as QueueTaskStatus


class CandidateDiscoveryApiTests(unittest.TestCase):
    def test_run_candidate_discovery_returns_service_payload(self) -> None:
        config = SimpleNamespace()
        request = endpoint.CandidateDiscoveryRequest(
            query="银行",
            universe="watchlist",
            max_results=3,
            max_provider_calls=5,
        )
        payload = {
            "pack_version": "candidate_discovery/1.0",
            "run_id": "run-1",
            "status": "ok",
            "query": "银行",
            "universe": "watchlist",
            "market": "cn",
            "page": 1,
            "page_size": 50,
            "max_results": 3,
            "candidate_count": 1,
            "candidates": [
                {
                    "rank": 1,
                    "code": "000001.SZ",
                    "name": "平安银行",
                    "score": 42.0,
                    "reason": "matched bank keyword",
                    "reason_codes": ["keyword_match"],
                }
            ],
            "criteria": {"keywords": ["银行"], "markets": ["CN"], "exclude_st": True},
            "warnings": [],
            "research_disclaimer": "Research screening only. Not investment advice or trade instructions.",
            "universe_contract": {"source": "watchlist", "resolved_count": 1, "evaluated_count": 1},
            "cost_contract": {
                "provider_calls": 1,
                "max_provider_calls": 5,
                "bounded": True,
                "llm_calls": 0,
            },
        }
        with patch.object(endpoint.CandidateDiscoveryService, "discover", return_value=payload) as discover_mock:
            result = endpoint.run_candidate_discovery(request, config=config)

        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["candidates"][0]["code"], "000001.SZ")
        discover_mock.assert_called_once()
        kwargs = discover_mock.call_args.kwargs
        self.assertEqual(kwargs["universe"], "watchlist")
        self.assertEqual(kwargs["max_results"], 3)
        self.assertEqual(kwargs["max_provider_calls"], 5)

    def test_run_candidate_discovery_maps_validation_error(self) -> None:
        config = SimpleNamespace()
        request = endpoint.CandidateDiscoveryRequest(universe="watchlist")
        with patch.object(
            endpoint.CandidateDiscoveryService,
            "discover",
            side_effect=DiscoveryValidationError("bad universe"),
        ):
            with self.assertRaises(Exception) as caught:
                endpoint.run_candidate_discovery(request, config=config)
        self.assertEqual(caught.exception.status_code, 400)
        self.assertEqual(caught.exception.detail["error"], "candidate_discovery_invalid_request")

    def test_start_task_submits_background_work(self) -> None:
        config = SimpleNamespace()
        fake_queue = MagicMock()
        fake_queue.submit_background_task.return_value = SimpleNamespace(
            task_id="disc-1",
            trace_id="disc-1",
            status=QueueTaskStatus.PENDING,
            message="Candidate discovery task submitted",
            message_code="task.discovery.queued",
            message_params={},
        )
        request = endpoint.CandidateDiscoveryRequest(
            query="银行",
            universe="index",
            page=1,
            page_size=20,
            max_results=5,
            max_provider_calls=10,
        )
        with (
            patch("api.v1.endpoints.candidate_discovery.get_task_queue", return_value=fake_queue),
            patch("api.v1.endpoints.candidate_discovery.uuid.uuid4", return_value=SimpleNamespace(hex="disc-1")),
        ):
            accepted = endpoint.start_candidate_discovery_task(request, config=config)

        self.assertEqual(accepted.task_id, "disc-1")
        self.assertEqual(accepted.universe, "index")
        self.assertEqual(accepted.max_results, 5)
        self.assertEqual(accepted.max_provider_calls, 10)
        fake_queue.submit_background_task.assert_called_once()
        kwargs = fake_queue.submit_background_task.call_args.kwargs
        self.assertEqual(kwargs["report_type"], "candidate_discovery")
        self.assertEqual(kwargs["task_id"], "disc-1")

    def test_get_task_rejects_non_discovery_report_type(self) -> None:
        fake_queue = MagicMock()
        fake_queue.get_task.return_value = SimpleNamespace(
            task_id="other-1",
            report_type="alphasift_screen",
            status=QueueTaskStatus.COMPLETED,
            result={},
        )
        with patch("api.v1.endpoints.candidate_discovery.get_task_queue", return_value=fake_queue):
            with self.assertRaises(Exception) as caught:
                endpoint.get_candidate_discovery_task("other-1")
        self.assertEqual(caught.exception.status_code, 404)

    def test_cancel_task_calls_queue_cancel(self) -> None:
        task = SimpleNamespace(
            task_id="disc-2",
            trace_id="disc-2",
            report_type="candidate_discovery",
            status=QueueTaskStatus.PROCESSING,
            progress=40,
            message="running",
            message_code="task.status",
            message_params={},
        )
        fake_queue = MagicMock()
        fake_queue.get_task.return_value = task
        fake_queue.cancel.return_value = SimpleNamespace(
            task_id="disc-2",
            status=QueueTaskStatus.CANCEL_REQUESTED,
            progress=40,
            message="Cancel requested",
            message_code="task.cancel_requested",
            message_params={},
        )
        with patch("api.v1.endpoints.candidate_discovery.get_task_queue", return_value=fake_queue):
            payload = endpoint.cancel_candidate_discovery_task("disc-2")
        fake_queue.cancel.assert_called_once_with("disc-2")
        self.assertEqual(payload.status, "cancel_requested")


if __name__ == "__main__":
    unittest.main()
