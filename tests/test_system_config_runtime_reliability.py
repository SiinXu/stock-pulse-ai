"""Regression coverage for transactional runtime configuration activation."""

from __future__ import annotations

import errno
import os
import stat
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi import HTTPException

from tests._llm_env_isolation import restore_ambient_llm_env, strip_ambient_llm_env
from tests.litellm_stub import ensure_litellm_stub

ensure_litellm_stub()

from src.config import Config
from src.core.config_manager import ConfigManager
from src.services.system_config_service import (
    ConfigRollbackError,
    ConfigValidationError,
    SystemConfigService,
)
from src.services.task_queue import AnalysisTaskQueue
from api.v1.endpoints import system_config as system_config_api
from api.v1.schemas.system_config import RollbackSystemConfigRequest, UpdateSystemConfigRequest


class SystemConfigRuntimeReliabilityTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._saved_llm_env = strip_ambient_llm_env()
        self._saved_notification_env = {
            key: os.environ[key]
            for key in SystemConfigService._NOTIFICATION_TEST_KEY_MAP
            if key in os.environ
        }
        for key in SystemConfigService._NOTIFICATION_TEST_KEY_MAP:
            os.environ.pop(key, None)
        self._saved_non_llm_env = {
            key: os.environ.get(key)
            for key in ("ENV_FILE", "STOCK_LIST", "SCHEDULE_TIME", "LOG_LEVEL")
        }
        for key in ("STOCK_LIST", "SCHEDULE_TIME", "LOG_LEVEL"):
            os.environ.pop(key, None)
        self._original_queue = AnalysisTaskQueue._instance
        AnalysisTaskQueue._instance = None
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        self.env_path.write_text(
            "\n".join(
                (
                    "STOCK_LIST=600519",
                    "GEMINI_API_KEY=baseline-gemini-secret",
                    "SCHEDULE_TIME=18:00",
                    "LOG_LEVEL=INFO",
                )
            )
            + "\n",
            encoding="utf-8",
        )
        os.environ["ENV_FILE"] = str(self.env_path)
        Config.reset_instance()
        self.manager = ConfigManager(env_path=self.env_path)
        self.service = SystemConfigService(manager=self.manager)

    def tearDown(self) -> None:
        queue = AnalysisTaskQueue._instance
        if queue is not None and queue is not self._original_queue:
            executor = getattr(queue, "_executor", None)
            if executor is not None:
                executor.shutdown(wait=False)
        AnalysisTaskQueue._instance = self._original_queue
        Config.reset_instance()
        for key, value in self._saved_non_llm_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for key in SystemConfigService._NOTIFICATION_TEST_KEY_MAP:
            os.environ.pop(key, None)
        os.environ.update(self._saved_notification_env)
        restore_ambient_llm_env(self._saved_llm_env)
        self.temp_dir.cleanup()

    def test_connectivity_probe_rejects_candidate_before_persist(self) -> None:
        before = self.env_path.read_bytes()
        previous_config = Config.get_instance()
        failed_probe = {
            "success": False,
            "message": "The configured credential was rejected",
            "status": {
                "backend_id": "litellm",
                "health_status": "failed",
                "last_error_code": "authentication_failed",
            },
        }

        with patch.object(
            self.service,
            "test_generation_backend",
            return_value=failed_probe,
        ):
            with self.assertRaises(ConfigValidationError) as raised:
                self.service.update(
                    config_version=self.manager.get_config_version(),
                    items=[{"key": "STOCK_LIST", "value": "300750"}],
                    validate_connectivity=True,
                )

        self.assertEqual(self.env_path.read_bytes(), before)
        self.assertIs(Config.get_instance(), previous_config)
        self.assertEqual(raised.exception.issues[0]["code"], "connectivity_probe_failed")
        self.assertEqual(
            raised.exception.issues[0]["details"]["error_code"],
            "authentication_failed",
        )

    def test_candidate_is_built_before_singleton_is_atomically_published(self) -> None:
        previous_config = Config.get_instance()
        candidate_config = Config(
            stock_list=["300750"],
            gemini_api_key="baseline-gemini-secret",
            gemini_api_keys=["baseline-gemini-secret"],
        )
        observed_singletons = []

        def build_candidate():
            observed_singletons.append(Config.get_instance())
            return candidate_config

        with patch.object(Config, "_load_from_env", side_effect=build_candidate), patch.object(
            self.service,
            "_reload_runtime_singletons",
        ):
            result = self.service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "STOCK_LIST", "value": "300750"}],
            )

        self.assertTrue(result["reload_triggered"])
        self.assertEqual(observed_singletons, [previous_config])
        self.assertIs(Config.get_instance(), candidate_config)
        self.assertEqual(previous_config.stock_list, ["600519"])
        snapshot_path = self.service._runtime_config_transaction.last_good_path
        self.assertTrue(snapshot_path.exists())
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(snapshot_path.stat().st_mode), 0o600)

    def test_secret_snapshot_temp_file_stays_in_env_ignore_namespace(self) -> None:
        snapshot_path = self.service._runtime_config_transaction.last_good_path
        captured_temp_names = []

        def reject_replace(source, _target):
            captured_temp_names.append(Path(source).name)
            raise OSError(errno.EPERM, "replace denied")

        with patch(
            "src.services.system_config_service_parts.runtime_reliability.os.replace",
            side_effect=reject_replace,
        ):
            with self.assertRaises(OSError):
                self.service._runtime_config_transaction._atomic_write_text(
                    snapshot_path,
                    "raw-secret-content",
                )

        self.assertEqual(len(captured_temp_names), 1)
        self.assertRegex(
            captured_temp_names[0],
            r"^\.env\.runtime-config-[0-9a-f]{12}\.tmp$",
        )
        self.assertFalse((snapshot_path.parent / captured_temp_names[0]).exists())

    def test_activation_failure_restores_file_process_env_and_runtime(self) -> None:
        previous_bytes = self.env_path.read_bytes()
        previous_config = Config.get_instance()
        previous_openai_key = os.environ.get("OPENAI_API_KEY")

        with patch.object(
            Config,
            "_load_from_env",
            side_effect=RuntimeError("candidate build failed"),
        ), patch.object(self.service, "_reload_runtime_singletons"):
            with self.assertRaises(ConfigValidationError) as raised:
                self.service.update(
                    config_version=self.manager.get_config_version(),
                    items=[{"key": "OPENAI_API_KEY", "value": "candidate-secret-value"}],
                )

        self.assertEqual(raised.exception.issues[0]["code"], "runtime_activation_failed")
        self.assertEqual(self.env_path.read_bytes(), previous_bytes)
        self.assertIs(Config.get_instance(), previous_config)
        self.assertEqual(os.environ.get("OPENAI_API_KEY"), previous_openai_key)

    def test_activation_and_exact_restoration_when_fchmod_is_unavailable(self) -> None:
        with patch(
            "src.services.system_config_service_parts.runtime_reliability.os.fchmod",
            new=None,
            create=True,
        ), patch.object(self.service, "_reload_runtime_singletons"):
            updated = self.service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "STOCK_LIST", "value": "300750"}],
            )
            activated_bytes = self.env_path.read_bytes()
            activated_config = Config.get_instance()

            with patch.object(
                Config,
                "_load_from_env",
                side_effect=RuntimeError("candidate build failed"),
            ):
                with self.assertRaises(ConfigValidationError) as raised:
                    self.service.update(
                        config_version=updated["config_version"],
                        items=[{"key": "STOCK_LIST", "value": "000001"}],
                    )

        self.assertTrue(updated["reload_triggered"])
        self.assertTrue(self.service._runtime_config_transaction.last_good_path.exists())
        self.assertEqual(raised.exception.issues[0]["code"], "runtime_activation_failed")
        self.assertEqual(self.env_path.read_bytes(), activated_bytes)
        self.assertIs(Config.get_instance(), activated_config)
        self.assertEqual(Config.get_instance().stock_list, ["300750"])

    def test_failed_activation_preserves_existing_rollback_target(self) -> None:
        with patch.object(self.service, "_reload_runtime_singletons"):
            updated = self.service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "STOCK_LIST", "value": "300750"}],
            )

        snapshot_path = self.service._runtime_config_transaction.last_good_path
        rollback_target = snapshot_path.read_bytes()
        with patch.object(
            self.service,
            "_reload_runtime_singletons",
            side_effect=[RuntimeError("runtime reset failed"), None],
        ):
            with self.assertRaises(ConfigValidationError):
                self.service.update(
                    config_version=updated["config_version"],
                    items=[{"key": "STOCK_LIST", "value": "000001"}],
                )

        self.assertEqual(snapshot_path.read_bytes(), rollback_target)
        with patch.object(self.service, "_reload_runtime_singletons"):
            restored = self.service.restore_last_good_config(
                config_version=self.manager.get_config_version(),
                actor="authenticated_admin",
            )

        self.assertTrue(restored["success"])
        self.assertEqual(Config.get_instance().stock_list, ["600519"])

    def test_noop_activation_does_not_replace_existing_rollback_target(self) -> None:
        with patch.object(self.service, "_reload_runtime_singletons"):
            updated = self.service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "STOCK_LIST", "value": "300750"}],
            )
            repeated = self.service.update(
                config_version=updated["config_version"],
                items=[{"key": "STOCK_LIST", "value": "300750"}],
            )
            restored = self.service.restore_last_good_config(
                config_version=repeated["config_version"],
                actor="authenticated_admin",
            )

        self.assertTrue(restored["success"])
        self.assertEqual(Config.get_instance().stock_list, ["600519"])

    def test_one_step_rollback_swaps_between_two_valid_runtime_versions(self) -> None:
        previous_config = Config.get_instance()
        with patch.object(self.service, "_reload_runtime_singletons"):
            updated = self.service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "STOCK_LIST", "value": "300750"}],
            )
            self.assertEqual(Config.get_instance().stock_list, ["300750"])

            restored = self.service.restore_last_good_config(
                config_version=updated["config_version"],
                actor="authenticated_admin",
            )
            self.assertEqual(Config.get_instance().stock_list, ["600519"])
            self.assertEqual(self.manager.read_config_map()["STOCK_LIST"], "600519")
            self.assertIn("STOCK_LIST", restored["updated_keys"])

            redone = self.service.restore_last_good_config(
                config_version=restored["config_version"],
                actor="authenticated_admin",
            )

        self.assertEqual(Config.get_instance().stock_list, ["300750"])
        self.assertEqual(self.manager.read_config_map()["STOCK_LIST"], "300750")
        self.assertIsNot(Config.get_instance(), previous_config)
        self.assertTrue(redone["reload_triggered"])

    def test_rollback_restores_bootstrap_process_override_missing_from_snapshot(self) -> None:
        self.env_path.write_text(
            "GEMINI_API_KEY=baseline-gemini-secret\n",
            encoding="utf-8",
        )
        os.environ["STOCK_LIST"] = "600519"
        Config.reset_instance()

        with patch.object(
            Config,
            "_BOOTSTRAP_RUNTIME_ENV_OVERRIDES_CAPTURED",
            True,
        ), patch.object(
            Config,
            "_BOOTSTRAP_RUNTIME_ENV_OVERRIDES",
            frozenset({"STOCK_LIST"}),
        ), patch.object(
            Config,
            "_BOOTSTRAP_RUNTIME_ENV_PRESENT_KEYS",
            frozenset({"STOCK_LIST"}),
        ):
            service = SystemConfigService(manager=ConfigManager(env_path=self.env_path))
            with patch.object(service, "_reload_runtime_singletons"):
                updated = service.update(
                    config_version=self.manager.get_config_version(),
                    items=[{"key": "STOCK_LIST", "value": "300750"}],
                )
                restored = service.restore_last_good_config(
                    config_version=updated["config_version"],
                    actor="authenticated_admin",
                )

        self.assertTrue(restored["success"])
        self.assertNotIn("STOCK_LIST", self.manager.read_config_map())
        self.assertEqual(os.environ["STOCK_LIST"], "600519")
        self.assertEqual(Config.get_instance().stock_list, ["600519"])

    def test_runtime_cache_recreated_during_publication_uses_candidate_config(self) -> None:
        from src import search_service as search_service_module

        previous_search_service = search_service_module._search_service
        recreated_services = []

        def reset_and_recreate_search_service():
            search_service_module.reset_search_service()
            recreated_services.append(search_service_module.get_search_service())

        try:
            with patch.object(
                self.service,
                "_reload_runtime_singletons",
                side_effect=reset_and_recreate_search_service,
            ):
                self.service.update(
                    config_version=self.manager.get_config_version(),
                    items=[{"key": "NEWS_MAX_AGE_DAYS", "value": "10"}],
                )

            self.assertEqual(Config.get_instance().news_max_age_days, 10)
            self.assertEqual(len(recreated_services), 1)
            self.assertEqual(recreated_services[0].news_max_age_days, 10)
            self.assertIs(
                search_service_module.get_search_service(),
                recreated_services[0],
            )
        finally:
            with search_service_module._search_service_lock:
                search_service_module._search_service = previous_search_service

    def test_rollback_reconciles_runtime_scheduler_for_restored_schedule(self) -> None:
        runtime_scheduler = Mock()
        service = SystemConfigService(
            manager=self.manager,
            runtime_scheduler=runtime_scheduler,
        )

        with patch.object(service, "_reload_runtime_singletons"):
            updated = service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "SCHEDULE_TIME", "value": "19:00"}],
            )
            runtime_scheduler.reset_mock()
            restored = service.restore_last_good_config(
                config_version=updated["config_version"],
                actor="authenticated_admin",
            )

        self.assertTrue(restored["success"])
        self.assertEqual(Config.get_instance().schedule_time, "18:00")
        runtime_scheduler.reconcile_from_config.assert_called_once_with(
            clear_enabled_override=False,
        )

    def test_rollback_cannot_change_admin_authentication_state(self) -> None:
        with patch.object(self.service, "_reload_runtime_singletons"):
            self.service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "STOCK_LIST", "value": "300750"}],
            )

        self.manager.apply_updates(
            updates=[("ADMIN_AUTH_ENABLED", "true")],
            sensitive_keys=set(),
            mask_token="******",
        )

        with self.assertRaises(ConfigValidationError) as raised:
            self.service.restore_last_good_config(
                config_version=self.manager.get_config_version(),
                actor="authenticated_admin",
            )

        self.assertEqual(
            raised.exception.issues[0]["code"],
            "auth_settings_endpoint_required",
        )
        self.assertEqual(self.manager.read_config_map()["ADMIN_AUTH_ENABLED"], "true")

    def test_dedicated_auth_write_becomes_the_next_active_baseline(self) -> None:
        self.service.apply_simple_updates([("ADMIN_AUTH_ENABLED", "true")])
        Config.reset_instance()
        Config.get_instance()

        with patch.object(self.service, "_reload_runtime_singletons"):
            updated = self.service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "STOCK_LIST", "value": "300750"}],
            )
            restored = self.service.restore_last_good_config(
                config_version=updated["config_version"],
                actor="authenticated_admin",
            )

        self.assertTrue(restored["success"])
        self.assertEqual(self.manager.read_config_map()["ADMIN_AUTH_ENABLED"], "true")
        self.assertEqual(self.manager.read_config_map()["STOCK_LIST"], "600519")

    def test_running_queue_task_keeps_its_startup_config_snapshot(self) -> None:
        previous_config = Config.get_instance()
        started = threading.Event()
        release = threading.Event()
        captured = {}

        def analyze_stock(_analysis_service, **_kwargs):
            captured["config"] = Config.get_instance()
            started.set()
            if not release.wait(timeout=5):
                raise RuntimeError("test task was not released")
            captured["stock_list_after_update"] = captured["config"].stock_list
            return {"success": True}

        queue = AnalysisTaskQueue(max_workers=1)
        with patch(
            "src.services.analysis_service.AnalysisService.analyze_stock",
            new=analyze_stock,
        ), patch.object(self.service, "_reload_runtime_singletons"):
            task = queue.submit_task("600519")
            self.assertTrue(started.wait(timeout=5))
            self.service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "STOCK_LIST", "value": "300750"}],
            )
            self.assertIs(captured["config"], previous_config)
            self.assertEqual(Config.get_instance().stock_list, ["300750"])
            release.set()
            queue._futures[task.task_id].result(timeout=5)

        self.assertEqual(captured["stock_list_after_update"], ["600519"])

    def test_audit_log_records_actor_and_keys_without_values(self) -> None:
        secret = "audit-must-not-log-this-secret"
        with self.assertLogs(
            "src.services.system_config_service_parts.runtime_reliability",
            level="INFO",
        ) as captured:
            self.service.update(
                config_version=self.manager.get_config_version(),
                items=[{"key": "GEMINI_API_KEY", "value": secret}],
                reload_now=False,
                actor="authenticated_admin",
            )

        output = "\n".join(captured.output)
        self.assertIn('"actor": "authenticated_admin"', output)
        self.assertIn('"keys": ["GEMINI_API_KEY"]', output)
        self.assertIn('"outcome": "persisted_only"', output)
        self.assertNotIn(secret, output)

    def test_update_api_forwards_optional_connectivity_validation(self) -> None:
        service = Mock()
        service.update.return_value = {
            "success": True,
            "config_version": "version-2",
            "applied_count": 1,
            "skipped_masked_count": 0,
            "reload_triggered": True,
            "updated_keys": ["STOCK_LIST"],
            "warnings": [],
        }
        request = UpdateSystemConfigRequest(
            config_version="version-1",
            validate_connectivity=True,
            connectivity_timeout_seconds=12,
            items=[{"key": "STOCK_LIST", "value": "300750"}],
        )

        with patch.object(
            system_config_api,
            "_config_audit_actor",
            return_value="authenticated_admin",
        ):
            response = system_config_api.update_system_config(
                request=request,
                service=service,
            )

        self.assertTrue(response.success)
        service.update.assert_called_once_with(
            config_version="version-1",
            items=[{"key": "STOCK_LIST", "value": "300750"}],
            mask_token="******",
            reload_now=True,
            validate_connectivity=True,
            connectivity_timeout_seconds=12.0,
            actor="authenticated_admin",
        )

    def test_rollback_api_returns_conflict_when_snapshot_is_unavailable(self) -> None:
        service = Mock()
        service.restore_last_good_config.side_effect = ConfigRollbackError(
            "No last-known-good configuration is available"
        )

        with patch.object(
            system_config_api,
            "_config_audit_actor",
            return_value="local_operator",
        ):
            with self.assertRaises(HTTPException) as raised:
                system_config_api.rollback_system_config(
                    request=RollbackSystemConfigRequest(config_version="version-1"),
                    service=service,
                )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["error"], "rollback_unavailable")


if __name__ == "__main__":
    unittest.main()
