# -*- coding: utf-8 -*-
"""Tests for the AlphaSift screening endpoints."""

from __future__ import annotations

import os
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import ANY, MagicMock, patch
import threading

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

try:
    import litellm  # noqa: F401
except ModuleNotFoundError:
    sys.modules["litellm"] = MagicMock()

from api.v1.endpoints import alphasift as alphasift_endpoint
from src.config import Config, DEFAULT_ALPHASIFT_INSTALL_SPEC
from src.security.outbound_policy import OutboundPolicyError
from src.services import alphasift_service
from src.services.task_queue import TaskInfo, TaskStatus as QueueTaskStatus

DEFAULT_ALPHASIFT_TEST_SPEC = DEFAULT_ALPHASIFT_INSTALL_SPEC
PUBLIC_DIAGNOSTIC_SECRET = (
    "Authorization: Bearer sk-alphasift-secret-marker "
    "https://user:password@example.invalid/private"
)


def _alphasift_unavailable() -> HTTPException:
    return HTTPException(
        status_code=424,
        detail={"error": "alphasift_unavailable", "message": "AlphaSift is unavailable"},
    )


def _raise_alphasift_unavailable() -> None:
    raise _alphasift_unavailable()


def _make_adapter_module(
    *,
    screen=None,
    list_strategies=None,
    get_status=None,
) -> SimpleNamespace:
    return SimpleNamespace(
        screen=screen or MagicMock(return_value=[]),
        list_strategies=list_strategies or (lambda: [{"id": "dual_low", "name": "双低选股", "description": "", "category": "价值"}]),
        get_status=get_status or (lambda: {"supported_markets": ["cn"], "contract_version": "1", "version": "0.2.0", "strategy_count": 1}),
    )


def _missing_alphasift_module_diagnostics() -> Dict[str, str]:
    return {
        "reason": "missing_module",
        "stage": "import_adapter",
        "error_type": "ModuleNotFoundError",
        "module": "alphasift.dsa_adapter",
    }

class _AlphaSiftApiTestCaseBase(unittest.TestCase):
    def setUp(self) -> None:
        Config.reset_instance()
        self.env_patch = patch.dict(os.environ, {"ALPHASIFT_DATA_DIR": ""}, clear=False)
        self.env_patch.start()

    def tearDown(self) -> None:
        self.env_patch.stop()
        Config.reset_instance()

    def _config(self, *, enabled: bool, install_spec: str = DEFAULT_ALPHASIFT_TEST_SPEC) -> Config:
        return Config(alphasift_enabled=enabled, alphasift_install_spec=install_spec)

    @staticmethod
    def _request(cookies=None) -> SimpleNamespace:
        return SimpleNamespace(cookies=cookies or {})

    def _screen(self, config: Config, *, mock_enrichment: bool = True, **kwargs):
        if not mock_enrichment:
            return alphasift_endpoint.alphasift_screen(
                alphasift_endpoint.AlphaSiftScreenRequest(**kwargs),
                http_request=self._request(),
                config=config,
            )
        with patch(
            "src.services.alphasift_service._enrich_candidates_with_dsa",
            side_effect=lambda candidates: (
                candidates,
                {
                    "enabled": True,
                    "max_candidates": 3,
                    "requested_count": min(len(candidates), 3),
                    "enriched_count": 0,
                    "warnings": [],
                },
            ),
        ):
            return alphasift_endpoint.alphasift_screen(
                alphasift_endpoint.AlphaSiftScreenRequest(**kwargs),
                http_request=self._request(),
                config=config,
            )

    def _strategies(self, config: Config):
        return alphasift_endpoint.alphasift_strategies(request=self._request(), config=config)

    def _hotspots(self, config: Config, **kwargs):
        return alphasift_endpoint.alphasift_hotspots(config=config, **kwargs)

    def _hotspot_detail(self, config: Config, **kwargs):
        if os.environ.get("ALPHASIFT_DATA_DIR"):
            return alphasift_endpoint.alphasift_hotspot_detail(config=config, **kwargs)
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.dict(os.environ, {"ALPHASIFT_DATA_DIR": str(Path(tmpdir) / "alphasift")}, clear=False):
                return alphasift_endpoint.alphasift_hotspot_detail(config=config, **kwargs)

    def assert_public_payload_is_private(self, payload: Any) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, default=str)
        self.assertNotIn("sk-alphasift-secret-marker", serialized)
        self.assertNotIn("user:password@example.invalid", serialized)
