"""Stable local-model error types and identifier normalization.

Consumers import ``src.services.local_model_service``, not this module.
"""

from __future__ import annotations

import re
from typing import Any

from src.model_pack.manifest import MAX_MODEL_ID_LENGTH


LOCAL_MODEL_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*"
    r"(?::[A-Za-z0-9][A-Za-z0-9._-]*)?$"
)
LOCAL_MODEL_MAX_ID_LENGTH = MAX_MODEL_ID_LENGTH


class LocalModelError(Exception):
    """Base error for stable local-model service failures."""

    error_code = "local_model_error"


class LocalModelValidationError(LocalModelError):
    """Raised when a model identifier or requested operation is invalid."""

    error_code = "invalid_local_model"


class LocalModelNotAllowedError(LocalModelError):
    """Raised when a model is not pullable from the authoritative catalog."""

    error_code = "local_model_not_pullable"


class LocalModelNotInstalledError(LocalModelError):
    """Raised when assignment targets a catalog model absent from Ollama."""

    error_code = "local_model_not_installed"


class LocalModelRuntimeUnavailableError(LocalModelError):
    """Raised when the configured Ollama runtime cannot be reached."""

    error_code = "local_model_runtime_unavailable"


class LocalModelRuntimeRequestError(LocalModelError):
    """Raised when Ollama rejects or malforms a lifecycle request."""

    error_code = "local_model_runtime_request_failed"


class LocalModelInUseError(LocalModelError):
    """Raised when deletion would invalidate an active model assignment."""

    error_code = "local_model_in_use"


def normalize_local_model_id(value: Any) -> str:
    """Return a safe Ollama model identifier or raise a stable validation error."""
    model_id = str(value or "").strip()
    if (
        not model_id
        or len(model_id) > LOCAL_MODEL_MAX_ID_LENGTH
        or LOCAL_MODEL_ID_PATTERN.fullmatch(model_id) is None
    ):
        raise LocalModelValidationError("Invalid local model identifier")
    return model_id
