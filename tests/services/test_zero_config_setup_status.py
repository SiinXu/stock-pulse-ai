"""Setup-status checks for zero-config first success (#796)."""

from __future__ import annotations

import os
from unittest.mock import patch

from src.services.local_runtime_detect import LocalRuntimeDetectResult
from tests.system_config_service_test_support import _SystemConfigServiceTestCaseBase


class ZeroConfigSetupStatusTests(_SystemConfigServiceTestCaseBase):
    def test_empty_config_exposes_data_only_and_local_runtime_checks(self) -> None:
        self._rewrite_env("")
        offline = LocalRuntimeDetectResult(
            available=False,
            reason="unreachable",
            detect_enabled=True,
        )
        with patch.dict(os.environ, {}, clear=True), patch.object(
            type(self.service),
            "_detect_local_runtime_for_setup",
            return_value=offline,
        ):
            status = self.service.get_setup_status()

        keys = {check["key"] for check in status["checks"]}
        self.assertTrue(
            {
                "llm_primary",
                "llm_agent",
                "stock_list",
                "data_only_path",
                "local_runtime",
                "notification",
                "storage",
            }.issubset(keys)
        )
        checks = {check["key"]: check for check in status["checks"]}
        self.assertEqual(checks["data_only_path"]["status"], "optional")
        self.assertEqual(checks["local_runtime"]["status"], "optional")
        self.assertIn("dry-run", checks["llm_primary"]["message"])
        self.assertFalse(status["ready_for_smoke"])
        for check in status["checks"]:
            self.assertTrue(str(check["key"]).strip())
            self.assertIn("message", check)

    def test_detect_on_surfaces_local_runtime_configured_and_llm_guidance(self) -> None:
        self._rewrite_env("STOCK_LIST=600519")
        detected = LocalRuntimeDetectResult(
            available=True,
            backend="ollama",
            base_url="http://127.0.0.1:11434",
            models=["qwen3:8b"],
            suggested_profile={
                "LLM_CHANNELS": "ollama",
                "LITELLM_MODEL": "ollama/qwen3:8b",
                "LLM_OLLAMA_BASE_URL": "http://127.0.0.1:11434",
            },
            reason="ollama_reachable",
            detect_enabled=True,
        )
        with patch.dict(os.environ, {}, clear=True), patch.object(
            type(self.service),
            "_detect_local_runtime_for_setup",
            return_value=detected,
        ):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertEqual(checks["local_runtime"]["status"], "configured")
        self.assertIn("Ollama", checks["local_runtime"]["message"])
        self.assertIn("ollama/qwen3:8b", checks["local_runtime"]["message"])
        self.assertEqual(checks["data_only_path"]["status"], "configured")
        self.assertEqual(checks["llm_primary"]["status"], "needs_action")
        self.assertIn("Ollama", checks["llm_primary"]["message"])

    def test_detect_off_reports_optional_local_runtime(self) -> None:
        self._rewrite_env("LOCAL_RUNTIME_AUTO_DETECT=false", "STOCK_LIST=600519")
        disabled = LocalRuntimeDetectResult(
            available=False,
            reason="detect_disabled",
            detect_enabled=False,
        )
        with patch.dict(os.environ, {}, clear=True), patch.object(
            type(self.service),
            "_detect_local_runtime_for_setup",
            return_value=disabled,
        ):
            status = self.service.get_setup_status()

        checks = {check["key"]: check for check in status["checks"]}
        self.assertEqual(checks["local_runtime"]["status"], "optional")
        self.assertIn("LOCAL_RUNTIME_AUTO_DETECT", checks["local_runtime"]["message"])
