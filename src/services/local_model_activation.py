from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Iterable, Mapping

from src.model_pack.errors import ModelPackError
from src.model_pack.manifest import MODEL_ID_PATTERN
from src.model_pack.ollama_http import (
    DEFAULT_OLLAMA_BASE_URL,
    normalize_ollama_native_base_url,
)
if TYPE_CHECKING:
    from src.services.system_config_service import SystemConfigService


def _append_csv(existing: str, additions: Iterable[str], *, casefold: bool = False) -> str:
    values = []
    seen = set()
    for raw_value in (*str(existing or "").split(","), *tuple(additions)):
        value = str(raw_value or "").strip()
        identity = value.casefold() if casefold else value
        if not value or identity in seen:
            continue
        seen.add(identity)
        values.append(value)
    return ",".join(values)


class LocalModelActivationService:
    """Activate imported or downloaded Ollama models through system config."""

    def __init__(
        self,
        system_config_service: "SystemConfigService",
        *,
        reload_now: bool = True,
    ) -> None:
        self._service = system_config_service
        self._reload_now = reload_now

    def activate(self, model_id: str) -> Dict[str, Any]:
        normalized_id = str(model_id or "").strip()
        if not MODEL_ID_PATTERN.fullmatch(normalized_id):
            raise ModelPackError(
                "invalid_model_id",
                "The imported model id is invalid. Rebuild the Model Pack.",
            )

        current = self._service.get_config(include_schema=False)
        values: Mapping[str, str] = {
            str(item.get("key") or ""): str(item.get("value") or "")
            for item in current.get("items", [])
            if isinstance(item, dict)
        }
        channels = _append_csv(values.get("LLM_CHANNELS", ""), ["ollama"], casefold=True)
        models = _append_csv(values.get("LLM_OLLAMA_MODELS", ""), [normalized_id])
        configured_base_url = values.get("LLM_OLLAMA_BASE_URL", "") or DEFAULT_OLLAMA_BASE_URL
        native_base_url = normalize_ollama_native_base_url(configured_base_url)

        result = self._service.update(
            config_version=str(current.get("config_version") or ""),
            items=[
                {"key": "LLM_CHANNELS", "value": channels},
                {"key": "LLM_OLLAMA_PROVIDER", "value": "ollama"},
                {"key": "LLM_OLLAMA_PROTOCOL", "value": "ollama"},
                {"key": "LLM_OLLAMA_BASE_URL", "value": native_base_url},
                {"key": "LLM_OLLAMA_MODELS", "value": models},
                {"key": "LLM_OLLAMA_ENABLED", "value": "true"},
            ],
            reload_now=self._reload_now,
            actor="local_model_activation",
        )
        return {
            "channels": channels,
            "models": models,
            "config_version": result.get("config_version"),
            "reload_triggered": bool(result.get("reload_triggered")),
        }


__all__ = ["LocalModelActivationService"]
