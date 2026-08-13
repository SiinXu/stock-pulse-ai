# -*- coding: utf-8 -*-
"""Single config resolve path: value parity + source observability (#1070).

Hard contract: resolved *values* must match the frozen pre-#1070 algorithm for
every (env, file, default, prefer, bootstrap, webui-priority) combination used
by runtime. Source is additive metadata and must not alter values.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from typing import Optional

from src.config import Config
from src.core.config import (
    ConfigSource,
    WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS,
    dump_resolved,
    resolve,
    resolve_config_value,
    resolve_registered,
)
from src.core.config.registry import get_registered_field_keys
from src.core.config_registry import get_field_definition


def _legacy_resolve_env_value(
    key: str,
    *,
    env_value: Optional[str],
    file_value: Optional[str],
    default: Optional[str] = None,
    prefer_env_file: bool = False,
    has_bootstrap_override: bool = False,
    webui_file_priority: bool = False,
) -> Optional[str]:
    """Frozen pre-#1070 value algorithm (must stay byte-equivalent forever)."""
    should_prefer_file = prefer_env_file or webui_file_priority
    if should_prefer_file and file_value is not None:
        if env_value is not None and has_bootstrap_override:
            return env_value
        return file_value
    if env_value is not None:
        return env_value
    if file_value is not None:
        return file_value
    return default


class TestResolveConfigValueParity(unittest.TestCase):
    def test_precedence_matrix_matches_legacy(self) -> None:
        cases = [
            (None, None, None, False, False, False),
            (None, None, "d", False, False, False),
            ("e", None, "d", False, False, False),
            (None, "f", "d", False, False, False),
            ("e", "f", "d", False, False, False),
            ("e", "f", "d", True, False, False),
            ("e", "f", "d", True, True, False),
            ("e", "f", "d", False, True, True),
            ("e", "f", "d", False, False, True),
            (None, "f", "d", False, False, True),
            ("e", None, "d", False, False, True),
            ("", "f", "d", True, False, False),
            ("e", "", "d", True, False, False),
        ]
        for env_v, file_v, default, prefer, bootstrap, webui in cases:
            with self.subTest(env=env_v, file=file_v, prefer=prefer, bootstrap=bootstrap, webui=webui):
                legacy = _legacy_resolve_env_value(
                    "K",
                    env_value=env_v,
                    file_value=file_v,
                    default=default,
                    prefer_env_file=prefer,
                    has_bootstrap_override=bootstrap,
                    webui_file_priority=webui,
                )
                resolved = resolve_config_value(
                    "K",
                    env_value=env_v,
                    file_value=file_v,
                    default=default,
                    prefer_env_file=prefer,
                    has_bootstrap_override=bootstrap,
                    webui_file_priority=webui,
                )
                self.assertEqual(resolved.value, legacy)

    def test_source_labels_match_winning_branch(self) -> None:
        self.assertEqual(
            resolve_config_value("K", env_value=None, file_value=None, default="d").source,
            ConfigSource.DEFAULT,
        )
        self.assertEqual(
            resolve_config_value("K", env_value="e", file_value=None, default="d").source,
            ConfigSource.ENV,
        )
        self.assertEqual(
            resolve_config_value("K", env_value=None, file_value="f", default="d").source,
            ConfigSource.PERSISTED,
        )
        self.assertEqual(
            resolve_config_value(
                "K", env_value="e", file_value="f", prefer_env_file=True, has_bootstrap_override=False
            ).source,
            ConfigSource.PERSISTED,
        )
        self.assertEqual(
            resolve_config_value(
                "K", env_value="e", file_value="f", prefer_env_file=True, has_bootstrap_override=True
            ).source,
            ConfigSource.ENV,
        )


class TestConfigFacadeParity(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.env_path = Path(self._temp.name) / ".env"
        self.env_path.write_text(
            "STOCK_LIST=600519,000001\nSCHEDULE_ENABLED=true\nSCHEDULE_TIME=09:30\nDEBUG=false\nMAX_WORKERS=2\n",
            encoding="utf-8",
        )
        self._saved = {
            key: os.environ[key]
            for key in ("ENV_FILE", "STOCK_LIST", "SCHEDULE_ENABLED", "SCHEDULE_TIME", "DEBUG", "MAX_WORKERS")
            if key in os.environ
        }
        for key in (
            "STOCK_LIST", "SCHEDULE_ENABLED", "SCHEDULE_TIME", "DEBUG", "MAX_WORKERS",
            "RUN_IMMEDIATELY", "SCHEDULE_TIMES", "SCHEDULE_RUN_IMMEDIATELY",
        ):
            os.environ.pop(key, None)
        os.environ["ENV_FILE"] = str(self.env_path)
        Config.reset_instance()

    def tearDown(self) -> None:
        Config.reset_instance()
        for key in (
            "STOCK_LIST", "SCHEDULE_ENABLED", "SCHEDULE_TIME", "DEBUG", "MAX_WORKERS",
            "RUN_IMMEDIATELY", "SCHEDULE_TIMES", "SCHEDULE_RUN_IMMEDIATELY", "ENV_FILE",
        ):
            os.environ.pop(key, None)
        os.environ.update(self._saved)
        self._temp.cleanup()

    def test_webui_priority_keys_match_shared_constant(self) -> None:
        self.assertEqual(set(Config._WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS), set(WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS))

    def test_resolve_env_value_equals_resolve_with_source_value(self) -> None:
        for key in sorted(WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS | {"DEBUG", "MAX_WORKERS", "MISSING_KEY"}):
            with self.subTest(key=key):
                via_legacy = Config._resolve_env_value(key, prefer_env_file=True)
                via_source = Config.resolve_with_source(key, prefer_env_file=True)
                self.assertEqual(via_legacy, via_source.value)
                self.assertIsInstance(via_source.source, ConfigSource)

    def test_public_resolve_matches_config_facade(self) -> None:
        Config._capture_bootstrap_runtime_env_overrides()
        for key in ("STOCK_LIST", "SCHEDULE_ENABLED", "SCHEDULE_TIME", "DEBUG"):
            with self.subTest(key=key):
                facade = Config.resolve_with_source(key, prefer_env_file=True)
                public = resolve(
                    key,
                    prefer_env_file=True,
                    env_path=self.env_path,
                    bootstrap_overrides=set(Config._BOOTSTRAP_RUNTIME_ENV_OVERRIDES),
                )
                self.assertEqual(public.value, facade.value)

    def test_persisted_wins_without_bootstrap_override(self) -> None:
        os.environ["STOCK_LIST"] = "600519,000001"
        Config.reset_instance()
        Config._capture_bootstrap_runtime_env_overrides()
        resolved = Config.resolve_with_source("STOCK_LIST", prefer_env_file=True)
        self.assertEqual(resolved.value, "600519,000001")
        self.assertEqual(resolved.source, ConfigSource.PERSISTED)

    def test_bootstrap_process_override_wins(self) -> None:
        os.environ["STOCK_LIST"] = "AAPL,TSLA"
        Config.reset_instance()
        Config._capture_bootstrap_runtime_env_overrides()
        resolved = Config.resolve_with_source("STOCK_LIST", prefer_env_file=True)
        self.assertEqual(resolved.value, "AAPL,TSLA")
        self.assertEqual(resolved.source, ConfigSource.ENV)


class TestRegisteredKeysValueParity(unittest.TestCase):
    def test_empty_sources_all_registered_keys_match_legacy(self) -> None:
        keys = get_registered_field_keys()
        self.assertGreaterEqual(len(keys), 300)
        for key in keys:
            legacy = _legacy_resolve_env_value(
                key, env_value=None, file_value=None, default=None,
                webui_file_priority=key in WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS,
            )
            resolved = resolve_config_value(
                key, env_value=None, file_value=None, default=None,
                webui_file_priority=key in WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS,
            )
            self.assertEqual(resolved.value, legacy)
            self.assertEqual(resolved.source, ConfigSource.DEFAULT)

    def test_fixture_map_parity_for_all_registered_keys(self) -> None:
        file_map = {
            "STOCK_LIST": "600519",
            "SCHEDULE_ENABLED": "true",
            "DEBUG": "1",
            "MAX_WORKERS": "4",
            "GENERATION_BACKEND": "litellm",
            "KRONOS_ENABLED": "false",
        }
        env_map = {"STOCK_LIST": "AAPL", "DEBUG": "1", "LITELLM_MODEL": "openai/gpt-test"}
        bootstrap = {"STOCK_LIST"}
        for key in get_registered_field_keys():
            env_v = env_map.get(key)
            file_v = file_map.get(key)
            webui = key in WEBUI_RUNTIME_ENV_FILE_PRIORITY_KEYS
            legacy = _legacy_resolve_env_value(
                key, env_value=env_v, file_value=file_v, default=None,
                prefer_env_file=webui, has_bootstrap_override=key in bootstrap,
                webui_file_priority=webui,
            )
            resolved = resolve_config_value(
                key, env_value=env_v, file_value=file_v, default=None,
                prefer_env_file=webui, has_bootstrap_override=key in bootstrap,
                webui_file_priority=webui,
            )
            self.assertEqual(resolved.value, legacy, msg=f"value drift for {key}")

    def test_resolve_registered_uses_registry_default_only_when_present(self) -> None:
        default = get_field_definition("STOCK_LIST").get("default_value")
        self.assertIsInstance(default, str)
        resolved = resolve_registered(
            "STOCK_LIST", environ={}, file_values={}, bootstrap_overrides=set()
        )
        self.assertEqual(resolved.value, default)
        self.assertEqual(resolved.source, ConfigSource.DEFAULT)

    def test_resolve_registered_does_not_invent_unregistered_defaults(self) -> None:
        resolved = resolve_registered(
            "TOTALLY_UNREGISTERED_KEY_FOR_1070",
            environ={}, file_values={}, bootstrap_overrides=set(),
        )
        self.assertIsNone(resolved.value)
        self.assertEqual(resolved.source, ConfigSource.DEFAULT)

    def test_dump_resolved_covers_registered_keys_only_by_default(self) -> None:
        rows = dump_resolved(environ={}, file_values={}, bootstrap_overrides=set())
        self.assertEqual({row.key for row in rows}, set(get_registered_field_keys()))
        for row in rows:
            self.assertIn(row.source, ConfigSource)


class TestCriticalFeatureFlagReadPath(unittest.TestCase):
    def setUp(self) -> None:
        self._temp = tempfile.TemporaryDirectory()
        self.env_path = Path(self._temp.name) / ".env"
        self.env_path.write_text(
            "SCHEDULE_ENABLED=true\nKRONOS_ENABLED=false\nDEBUG=false\nSTOCK_LIST=600519,300750\n",
            encoding="utf-8",
        )
        self._saved = {
            key: os.environ[key]
            for key in ("ENV_FILE", "SCHEDULE_ENABLED", "KRONOS_ENABLED", "DEBUG", "STOCK_LIST")
            if key in os.environ
        }
        for key in (
            "SCHEDULE_ENABLED", "KRONOS_ENABLED", "DEBUG", "STOCK_LIST",
            "RUN_IMMEDIATELY", "SCHEDULE_TIME", "SCHEDULE_TIMES", "SCHEDULE_RUN_IMMEDIATELY",
        ):
            os.environ.pop(key, None)
        os.environ["ENV_FILE"] = str(self.env_path)
        Config.reset_instance()
        Config._capture_bootstrap_runtime_env_overrides()

    def tearDown(self) -> None:
        Config.reset_instance()
        for key in (
            "ENV_FILE", "SCHEDULE_ENABLED", "KRONOS_ENABLED", "DEBUG", "STOCK_LIST",
            "RUN_IMMEDIATELY", "SCHEDULE_TIME", "SCHEDULE_TIMES", "SCHEDULE_RUN_IMMEDIATELY",
        ):
            os.environ.pop(key, None)
        os.environ.update(self._saved)
        self._temp.cleanup()

    def test_critical_keys_go_through_resolve_with_source(self) -> None:
        for key in ("SCHEDULE_ENABLED", "STOCK_LIST", "DEBUG", "KRONOS_ENABLED"):
            with self.subTest(key=key):
                via_facade = Config.resolve_with_source(key, prefer_env_file=True)
                via_resolve = resolve(
                    key, prefer_env_file=True, env_path=self.env_path,
                    bootstrap_overrides=set(Config._BOOTSTRAP_RUNTIME_ENV_OVERRIDES),
                )
                via_name = Config._resolve_env_value(key, prefer_env_file=True)
                self.assertEqual(via_facade.value, via_resolve.value)
                self.assertEqual(via_facade.value, via_name)
                self.assertIsNotNone(via_facade.value)
                self.assertIn(via_facade.source, (ConfigSource.ENV, ConfigSource.PERSISTED))


if __name__ == "__main__":
    unittest.main()
