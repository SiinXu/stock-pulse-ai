# -*- coding: utf-8 -*-
"""Validation tests for backend packaging scripts."""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_windows_backend_build_script_collects_alphasift_adapter() -> None:
    script = _read_text(REPO_ROOT / "scripts" / "build-backend.ps1")
    main_py = _read_text(REPO_ROOT / "main.py")

    assert "Checking AlphaSift adapter availability" in script
    assert "import alphasift.dsa_adapter" in script
    assert "--collect-all" in script
    assert "alphasift.dsa_adapter" in script
    assert "hiddenImports" in script
    assert "Verifying packaged runtime imports" in script
    assert "DSA_PACKAGED_IMPORT_PROBE" in script
    assert "Start-Process -FilePath $packagedEntry -Wait -PassThru" in script
    assert "$probeProcess.ExitCode" in script
    assert "& $packagedEntry" not in script
    assert "Packaged backend cannot import $module" in script
    assert "DSA_PACKAGED_IMPORT_PROBE" in main_py
    assert "importlib.import_module(_packaged_import_probe)" in main_py


def test_windows_backend_build_script_collects_and_probes_migration_registry() -> None:
    script = _read_text(REPO_ROOT / "scripts" / "build-backend.ps1")
    main_py = _read_text(REPO_ROOT / "main.py")

    assert "Checking migration registry availability" in script
    assert "from src.migrations.registry import TARGET_VERSION, get_migrations" in script
    assert "'src.migrations'" in script
    assert "'src.migrations.registry'" in script
    assert "'src.migrations.versions'" in script
    assert "@('alphasift.dsa_adapter', 'orjson', 'src.migrations.registry')" in script
    assert "src/migrations/versions/*.py;src/migrations/versions" in script
    assert "Verifying packaged migration source" in script
    assert 'if _packaged_import_probe == "src.migrations.registry"' in main_py
    assert "target={target_version}" in main_py


def test_macos_backend_build_script_collects_alphasift_adapter() -> None:
    script = _read_text(REPO_ROOT / "scripts" / "build-backend-macos.sh")
    main_py = _read_text(REPO_ROOT / "main.py")

    assert "Checking AlphaSift adapter availability..." in script
    assert "import alphasift.dsa_adapter" in script
    assert "--collect-all" in script
    assert "cmd+=(\"--collect-all\" \"alphasift\")" in script
    assert "packaged_entry=\"${packaged_root}/stock_analysis\"" in script
    assert "--help" in script
    assert 'DSA_PACKAGED_IMPORT_PROBE="${module}"' in script
    assert "dsa-packaged-import.log" in script
    assert "PathFinder.find_spec(" not in script
    assert "zipfile" not in script
    assert 'normalized.startswith("alphasift/dsa_adapter.")' not in script
    assert "DSA_PACKAGED_IMPORT_PROBE" in main_py
    assert "importlib.import_module(_packaged_import_probe)" in main_py


def test_macos_backend_build_script_collects_and_probes_migration_registry() -> None:
    script = _read_text(REPO_ROOT / "scripts" / "build-backend-macos.sh")
    main_py = _read_text(REPO_ROOT / "main.py")

    assert "Checking migration registry availability..." in script
    assert "from src.migrations.registry import TARGET_VERSION, get_migrations" in script
    assert '"src.migrations"' in script
    assert '"src.migrations.registry"' in script
    assert '"src.migrations.versions"' in script
    assert "for module in alphasift.dsa_adapter orjson src.migrations.registry" in script
    assert "src/migrations/versions/*.py:src/migrations/versions" in script
    assert "Verifying packaged migration source" in script
    assert 'if _packaged_import_probe == "src.migrations.registry"' in main_py
    assert "target={target_version}" in main_py


def test_docker_smoke_imports_and_validates_migration_registry() -> None:
    workflow = _read_text(REPO_ROOT / ".github" / "workflows" / "ci.yml")

    assert "from src.migrations.registry import TARGET_VERSION, get_migrations" in workflow
    assert "migration_ids = [migration.id for migration in get_migrations()]" in workflow
    assert "assert migration_ids and migration_ids[-1] == TARGET_VERSION" in workflow
    assert "migrations target {TARGET_VERSION}" in workflow
    assert "assert TARGET_VERSION == '202607160001_migration_runner_registry'" not in workflow


def test_backend_gate_uses_an_isolated_temporary_database() -> None:
    script = _read_text(REPO_ROOT / "scripts" / "ci_gate.sh")

    assert 'test_data_dir="$(mktemp -d)"' in script
    assert 'DATABASE_PATH="${test_data_dir}/stockpulse-ci.sqlite"' in script
    assert 'rm -rf "${test_data_dir}"' in script
    assert 'python -m pytest -m "not network"' in script
