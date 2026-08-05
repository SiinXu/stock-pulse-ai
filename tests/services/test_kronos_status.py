"""Deterministic Kronos status diagnostics (no torch / network)."""

from __future__ import annotations

from types import SimpleNamespace

from src.services.kronos_forecast_service import (
    KRONOS_INSTALL_COMMAND,
    build_kronos_status_report,
)


def _config(*, enabled=False, size="mini", weights_dir=None):
    return SimpleNamespace(
        kronos_enabled=enabled,
        kronos_model_size=size,
        kronos_weights_dir=weights_dir,
    )


def test_status_disabled_has_actionable_next_step() -> None:
    report = build_kronos_status_report(
        _config(enabled=False),
        dependency_probe=lambda _name: False,
        packaged_desktop=False,
    )

    assert report.enabled is False
    assert report.ready is False
    assert report.reason == "disabled"
    assert report.dependencies_installed is False
    assert "KRONOS_ENABLED" in report.next_step
    assert "requirements-kronos" in report.next_step
    assert report.install_supported is True
    assert report.packaged_desktop is False


def test_status_reports_missing_dependencies_with_install_command(tmp_path) -> None:
    report = build_kronos_status_report(
        _config(enabled=True, weights_dir=str(tmp_path)),
        dependency_probe=lambda name: name != "torch",
        packaged_desktop=False,
    )

    assert report.ready is False
    assert report.reason == "dependencies_missing"
    assert report.dependencies_installed is False
    assert any(not item.available and item.name == "torch" for item in report.dependencies)
    assert KRONOS_INSTALL_COMMAND in report.message
    assert "requirements-kronos" in report.next_step


def test_status_reports_weights_missing(tmp_path) -> None:
    missing = tmp_path / "does-not-exist"
    report = build_kronos_status_report(
        _config(enabled=True, weights_dir=str(missing)),
        dependency_probe=lambda _name: True,
        packaged_desktop=False,
    )

    assert report.ready is False
    assert report.reason == "weights_dir_missing"
    assert report.weights_present is False
    assert "download_kronos_weights.py" in report.message
    assert report.download_size_hint is not None


def test_status_ready_when_weights_valid(tmp_path) -> None:
    from tests.plugins.test_kronos_agent_tool import _write_ready_weights

    root = _write_ready_weights(tmp_path)
    report = build_kronos_status_report(
        _config(enabled=True, weights_dir=str(root)),
        dependency_probe=lambda _name: True,
        packaged_desktop=False,
    )

    assert report.ready is True
    assert report.reason == "ready"
    assert report.weights_present is True
    assert report.weights_total_bytes is not None
    assert report.weights_total_bytes > 0
    assert report.model_dir is not None
    assert report.tokenizer_dir is not None
    assert "restart" in report.next_step.lower() or "register" in report.next_step.lower()


def test_packaged_desktop_never_reports_install_supported(tmp_path) -> None:
    from tests.plugins.test_kronos_agent_tool import _write_ready_weights

    root = _write_ready_weights(tmp_path)
    report = build_kronos_status_report(
        _config(enabled=True, weights_dir=str(root)),
        dependency_probe=lambda _name: True,
        packaged_desktop=True,
    )

    assert report.packaged_desktop is True
    assert report.install_supported is False
    assert report.ready is False
    assert report.reason == "packaged_desktop_unsupported"
    assert "desktop" in report.next_step.lower()
