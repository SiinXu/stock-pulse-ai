"""API contract tests for GET /api/v1/system/config/kronos/status."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from api.v1.endpoints import system_config


def test_get_kronos_status_returns_response_model() -> None:
    fake_config = SimpleNamespace(
        kronos_enabled=False,
        kronos_model_size="mini",
        kronos_weights_dir=None,
    )
    with (
        patch("src.config.get_config", return_value=fake_config),
        patch(
            "src.services.kronos_forecast_service._dependency_available",
            return_value=False,
        ),
        patch(
            "src.services.kronos_forecast_service.is_packaged_desktop_runtime",
            return_value=False,
        ),
    ):
        response = system_config.get_kronos_status()

    payload = response.model_dump()
    assert payload["enabled"] is False
    assert payload["ready"] is False
    assert payload["reason"] == "disabled"
    assert payload["model_size"] == "mini"
    assert isinstance(payload["dependencies"], list)
    assert payload["next_step"]
    assert payload["install_supported"] is True
    assert payload["packaged_desktop"] is False
