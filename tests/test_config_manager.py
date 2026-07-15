# -*- coding: utf-8 -*-
"""Unit tests for structured `.env` line preservation in ConfigManager."""

import errno
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import src.core.config_manager as config_manager_module
from src.core.config_manager import ConfigManager, ConfigVersionConflictError


class ConfigManagerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.original_env_file = os.environ.get("ENV_FILE")
        self.temp_dir = tempfile.TemporaryDirectory()
        self.env_path = Path(self.temp_dir.name) / ".env"
        os.environ["ENV_FILE"] = str(self.env_path)
        self.manager = ConfigManager(env_path=self.env_path)

    def tearDown(self) -> None:
        if self.original_env_file is None:
            os.environ.pop("ENV_FILE", None)
        else:
            os.environ["ENV_FILE"] = self.original_env_file
        self.temp_dir.cleanup()

    def test_apply_updates_preserves_comments_blank_lines_and_raw_lines(self) -> None:
        self.env_path.write_text(
            "\n".join(
                [
                    "# Core settings",
                    "STOCK_LIST=600519,000001",
                    "",
                    "export SHOULD_STAY_UNCHANGED",
                    "# Secrets",
                    "GEMINI_API_KEY=secret-key",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        self.manager.apply_updates(
            updates=[("STOCK_LIST", "600519,300750")],
            sensitive_keys=set(),
            mask_token="******",
        )

        env_content = self.env_path.read_text(encoding="utf-8")
        self.assertIn("# Core settings\n", env_content)
        self.assertIn("\n\nexport SHOULD_STAY_UNCHANGED\n", env_content)
        self.assertIn("# Secrets\nGEMINI_API_KEY=secret-key\n", env_content)
        self.assertIn("STOCK_LIST=600519,300750\n", env_content)

    def test_apply_updates_rejects_stale_version_inside_write_lock(self) -> None:
        self.env_path.write_text("STOCK_LIST=600519\n", encoding="utf-8")
        stale_version = self.manager.get_config_version()
        self.manager.apply_updates(
            updates=[("STOCK_LIST", "300750")],
            sensitive_keys=set(),
            mask_token="******",
            expected_version=stale_version,
        )

        with self.assertRaises(ConfigVersionConflictError) as context:
            self.manager.apply_updates(
                updates=[("STOCK_LIST", "AAPL")],
                sensitive_keys=set(),
                mask_token="******",
                expected_version=stale_version,
            )

        self.assertEqual(context.exception.current_version, self.manager.get_config_version())
        self.assertEqual(self.manager.read_config_map()["STOCK_LIST"], "300750")

    def test_managers_for_same_path_share_the_atomic_write_lock(self) -> None:
        second_manager = ConfigManager(env_path=self.env_path)
        other_manager = ConfigManager(env_path=self.env_path.parent / "other.env")

        self.assertIs(self.manager._lock, second_manager._lock)
        self.assertIsNot(self.manager._lock, other_manager._lock)

    @unittest.skipIf(config_manager_module.fcntl is None, "requires POSIX flock")
    def test_expected_version_is_checked_under_cross_process_lock(self) -> None:
        self.env_path.write_text("STOCK_LIST=600519\n", encoding="utf-8")
        expected_version = self.manager.get_config_version()
        ready_path = Path(self.temp_dir.name) / "child-ready"
        result_path = Path(self.temp_dir.name) / "child-result"
        script = """
import sys
from pathlib import Path
from src.core.config_manager import ConfigManager, ConfigVersionConflictError

manager = ConfigManager(env_path=Path(sys.argv[1]))
Path(sys.argv[3]).write_text("ready", encoding="utf-8")
try:
    manager.apply_updates(
        updates=[("STOCK_LIST", "AAPL")],
        sensitive_keys=set(),
        mask_token="******",
        expected_version=sys.argv[2],
    )
except ConfigVersionConflictError:
    outcome = "conflict"
else:
    outcome = "success"
Path(sys.argv[4]).write_text(outcome, encoding="utf-8")
"""
        process = None
        try:
            with self.manager._exclusive_file_lock():
                process = subprocess.Popen(
                    [
                        sys.executable,
                        "-c",
                        script,
                        str(self.env_path),
                        expected_version,
                        str(ready_path),
                        str(result_path),
                    ],
                    cwd=Path(__file__).resolve().parents[1],
                )
                deadline = time.monotonic() + 5
                while not ready_path.exists() and time.monotonic() < deadline:
                    if process.poll() is not None:
                        self.fail(f"child exited before locking: {process.returncode}")
                    time.sleep(0.01)
                self.assertTrue(ready_path.exists())
                time.sleep(0.1)
                self.assertFalse(result_path.exists())
                self.manager._atomic_upsert({"STOCK_LIST": "300750"})

            self.assertEqual(process.wait(timeout=5), 0)
            self.assertEqual(result_path.read_text(encoding="utf-8"), "conflict")
            self.assertEqual(self.manager.read_config_map()["STOCK_LIST"], "300750")
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=5)

    def test_apply_updates_only_rewrites_last_duplicate_assignment(self) -> None:
        self.env_path.write_text(
            "\n".join(
                [
                    "STOCK_LIST=600519",
                    "# Keep the legacy duplicate for audit history",
                    "STOCK_LIST=000001",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        self.manager.apply_updates(
            updates=[("STOCK_LIST", "300750")],
            sensitive_keys=set(),
            mask_token="******",
        )

        env_lines = self.env_path.read_text(encoding="utf-8").splitlines()
        self.assertEqual(env_lines[0], "STOCK_LIST=600519")
        self.assertEqual(env_lines[1], "# Keep the legacy duplicate for audit history")
        self.assertEqual(env_lines[2], "STOCK_LIST=300750")

    def test_apply_updates_falls_back_to_in_place_rewrite(self) -> None:
        self.env_path.write_text("STOCK_LIST=600519\n", encoding="utf-8")

        with patch("src.core.config_manager.os.replace", side_effect=OSError(errno.EXDEV, "cross-device")):
            self.manager.apply_updates(
                updates=[("STOCK_LIST", "000001")],
                sensitive_keys=set(),
                mask_token="******",
            )

        self.assertEqual(self.env_path.read_text(encoding="utf-8"), "STOCK_LIST=000001\n")

    def test_custom_webhook_template_placeholders_are_escaped_for_compose(self) -> None:
        template = '{"title":$title_json,"content":$content_json,"raw":$content,"name":"$OTHER"}'

        self.manager.apply_updates(
            updates=[("CUSTOM_WEBHOOK_BODY_TEMPLATE", template)],
            sensitive_keys=set(),
            mask_token="******",
        )

        env_content = self.env_path.read_text(encoding="utf-8")
        self.assertIn(
            'CUSTOM_WEBHOOK_BODY_TEMPLATE={"title":$$title_json,"content":$$content_json,'
            '"raw":$$content,"name":"$OTHER"}',
            env_content,
        )
        self.assertEqual(
            self.manager.read_config_map()["CUSTOM_WEBHOOK_BODY_TEMPLATE"],
            template,
        )

    def test_custom_webhook_template_braced_placeholders_are_escaped_for_compose(self) -> None:
        template = '{"title":${title_json},"content":${content_json},"name":"${OTHER}"}'

        self.manager.apply_updates(
            updates=[("CUSTOM_WEBHOOK_BODY_TEMPLATE", template)],
            sensitive_keys=set(),
            mask_token="******",
        )

        env_content = self.env_path.read_text(encoding="utf-8")
        self.assertIn(
            'CUSTOM_WEBHOOK_BODY_TEMPLATE={"title":$${title_json},'
            '"content":$${content_json},"name":"${OTHER}"}',
            env_content,
        )
        self.assertEqual(
            self.manager.read_config_map()["CUSTOM_WEBHOOK_BODY_TEMPLATE"],
            template,
        )

    def test_custom_webhook_template_canonicalizes_unescaped_existing_value(self) -> None:
        self.env_path.write_text(
            'CUSTOM_WEBHOOK_BODY_TEMPLATE={"content":$content_json}\n',
            encoding="utf-8",
        )

        self.manager.apply_updates(
            updates=[("CUSTOM_WEBHOOK_BODY_TEMPLATE", '{"content":$content_json}')],
            sensitive_keys=set(),
            mask_token="******",
        )

        self.assertEqual(
            self.env_path.read_text(encoding="utf-8"),
            'CUSTOM_WEBHOOK_BODY_TEMPLATE={"content":$$content_json}\n',
        )

    def test_custom_webhook_template_does_not_double_escape_existing_value(self) -> None:
        self.env_path.write_text(
            'CUSTOM_WEBHOOK_BODY_TEMPLATE={"content":$$content_json}\n',
            encoding="utf-8",
        )

        self.manager.apply_updates(
            updates=[("CUSTOM_WEBHOOK_BODY_TEMPLATE", '{"content":$content_json}')],
            sensitive_keys=set(),
            mask_token="******",
        )

        self.assertEqual(
            self.env_path.read_text(encoding="utf-8"),
            'CUSTOM_WEBHOOK_BODY_TEMPLATE={"content":$$content_json}\n',
        )
        self.assertEqual(
            self.manager.read_config_map()["CUSTOM_WEBHOOK_BODY_TEMPLATE"],
            '{"content":$content_json}',
        )

    def test_custom_webhook_template_plain_json_is_not_changed(self) -> None:
        template = '{"content":"plain json string"}'

        self.manager.apply_updates(
            updates=[("CUSTOM_WEBHOOK_BODY_TEMPLATE", template)],
            sensitive_keys=set(),
            mask_token="******",
        )

        self.assertEqual(
            self.env_path.read_text(encoding="utf-8"),
            f"CUSTOM_WEBHOOK_BODY_TEMPLATE={template}\n",
        )

    def test_non_template_settings_keep_dotenv_interpolation_semantics(self) -> None:
        self.env_path.write_text(
            "\n".join(
                [
                    "API_PORT=8000",
                    "WEBUI_PORT=${API_PORT}",
                    'CUSTOM_WEBHOOK_BODY_TEMPLATE={"content":$${content_json}}',
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        config_map = self.manager.read_config_map()

        self.assertEqual(config_map["API_PORT"], "8000")
        self.assertEqual(config_map["WEBUI_PORT"], "8000")
        self.assertEqual(
            config_map["CUSTOM_WEBHOOK_BODY_TEMPLATE"],
            '{"content":${content_json}}',
        )

        self.manager.apply_updates(
            updates=[("WEBUI_PORT", config_map["WEBUI_PORT"])],
            sensitive_keys=set(),
            mask_token="******",
        )

        self.assertIn(
            "WEBUI_PORT=${API_PORT}\n",
            self.env_path.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
