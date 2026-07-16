# -*- coding: utf-8 -*-
"""Static contracts for modules and data bundled in desktop backends."""

from __future__ import annotations

import unittest
from pathlib import Path


class DesktopPackagingAssetsTestCase(unittest.TestCase):
    """Keep Windows and macOS PyInstaller package-data rules aligned."""

    repo_root = Path(__file__).resolve().parent.parent

    def test_orjson_is_declared_bundled_and_probed(self) -> None:
        requirements = (self.repo_root / "requirements.txt").read_text(encoding="utf-8")
        main = (self.repo_root / "main.py").read_text(encoding="utf-8")
        macos_script = (self.repo_root / "scripts" / "build-backend-macos.sh").read_text(
            encoding="utf-8"
        )
        windows_script = (self.repo_root / "scripts" / "build-backend.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("orjson>=3.10,<4", requirements)
        self.assertIn('"orjson"', macos_script)
        self.assertIn("'orjson'", windows_script)
        self.assertIn('DSA_PACKAGED_IMPORT_PROBE="${module}"', macos_script)
        self.assertIn("$env:DSA_PACKAGED_IMPORT_PROBE = $module", windows_script)
        self.assertIn('importlib.import_module(_packaged_import_probe)', main)

    def test_scripts_collect_and_verify_akshare_calendar_data(self) -> None:
        macos_script = (self.repo_root / "scripts" / "build-backend-macos.sh").read_text(
            encoding="utf-8"
        )
        windows_script = (self.repo_root / "scripts" / "build-backend.ps1").read_text(
            encoding="utf-8"
        )

        self.assertIn("--collect-data akshare", macos_script)
        self.assertIn("'--collect-data', 'akshare'", windows_script)
        self.assertIn("_internal/akshare/file_fold/calendar.json", macos_script)
        self.assertIn("_internal\\akshare\\file_fold\\calendar.json", windows_script)

    def test_migration_package_is_bundled_and_probed_on_both_platforms(self) -> None:
        macos_script = (self.repo_root / "scripts" / "build-backend-macos.sh").read_text(
            encoding="utf-8"
        )
        windows_script = (self.repo_root / "scripts" / "build-backend.ps1").read_text(
            encoding="utf-8"
        )

        for module in ("src.migrations", "src.migrations.registry", "src.migrations.versions"):
            self.assertIn(f'"{module}"', macos_script)
            self.assertIn(f"'{module}'", windows_script)

        self.assertIn(
            "for module in alphasift.dsa_adapter orjson src.migrations.registry",
            macos_script,
        )
        self.assertIn(
            "@('alphasift.dsa_adapter', 'orjson', 'src.migrations.registry')",
            windows_script,
        )
        self.assertNotIn(
            "assert TARGET_VERSION == '202607160001_migration_runner_registry'",
            macos_script,
        )
        self.assertNotIn(
            "assert TARGET_VERSION == '202607160001_migration_runner_registry'",
            windows_script,
        )
        self.assertIn(
            'src/migrations/versions/*.py:src/migrations/versions',
            macos_script,
        )
        self.assertIn(
            'src/migrations/versions/*.py;src/migrations/versions',
            windows_script,
        )
        self.assertIn("Verifying packaged migration source", macos_script)
        self.assertIn("Verifying packaged migration source", windows_script)
        self.assertIn("-name 'v*.py'", macos_script)
        self.assertIn("-Filter 'v*.py'", windows_script)


if __name__ == "__main__":
    unittest.main()
