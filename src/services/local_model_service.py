"""Local Ollama model lifecycle and zero-config activation services."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Set
from urllib.parse import urlsplit, urlunsplit

import requests

from src.llm.model_ref import decode_model_ref
from src.llm.provider_catalog import get_provider
from src.services.system_config_service import (
    ConfigConflictError,
    ConfigValidationError,
    SystemConfigService,
)
from src.services.task_queue import AnalysisTaskQueue, TaskInfo
from src.task_execution import TaskCommand, TaskRunContext, TaskStatusEnum
from src.utils.sanitize import log_safe_exception


_OLLAMA_PROVIDER = get_provider("ollama")
if _OLLAMA_PROVIDER is None:  # pragma: no cover - checked-in provider catalog invariant
    raise RuntimeError("The Ollama provider is missing from the provider catalog")
OLLAMA_DEFAULT_BASE_URL = str(_OLLAMA_PROVIDER["default_base_url"])
OLLAMA_CONNECT_TIMEOUT_SECONDS = 5.0
OLLAMA_READ_TIMEOUT_SECONDS = 30.0
OLLAMA_PULL_TIMEOUT_SECONDS = 30.0 * 60.0
OLLAMA_MAX_JSON_BYTES = 4 * 1024 * 1024
OLLAMA_MAX_EVENT_BYTES = 64 * 1024
LOCAL_MODEL_PULL_TASK_KIND = "local_model_pull"
LOCAL_MODEL_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]*(?:/[A-Za-z0-9][A-Za-z0-9._-]*)*"
    r"(?::[A-Za-z0-9][A-Za-z0-9._-]*)?$"
)
LOCAL_MODEL_RUNTIME_IDENTITY_PATTERN = re.compile(r"^[0-9a-f]{64}$")
LOCAL_MODEL_MAX_ID_LENGTH = 128
LOCAL_MODEL_REGISTRATION_RECOVERY_TTL_SECONDS = 5.0 * 60.0
LocalModelAssignment = Literal["auto", "primary", "agent"]


logger = logging.getLogger(__name__)


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


def normalize_ollama_base_url(value: Any) -> str:
    """Normalize a server-controlled Ollama URL to its HTTP origin."""
    candidate = str(value or "").strip() or OLLAMA_DEFAULT_BASE_URL
    if any(char.isspace() or char == "\\" or ord(char) < 32 for char in candidate):
        raise LocalModelValidationError("Invalid configured Ollama Base URL")
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise LocalModelValidationError("Invalid configured Ollama Base URL") from exc
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise LocalModelValidationError("Invalid configured Ollama Base URL")
    scheme = parsed.scheme.lower()
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    hostname = parsed.hostname.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return urlunsplit((scheme, netloc, "", "", ""))


def get_ollama_runtime_identity(value: Any) -> str:
    """Return an opaque identity for one normalized server-controlled runtime."""
    normalized = normalize_ollama_base_url(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def get_pullable_local_model_ids() -> Set[str]:
    """Project pullable Ollama tags from the authoritative checked-in catalog."""
    from src.llm.local_model_catalog import get_local_model_catalog

    pullable: Set[str] = set()
    for entry in get_local_model_catalog()["models"]:
        install = entry["install"]
        if install["method"] != "ollama_pull" or install["status"] != "available":
            continue
        pullable.add(normalize_local_model_id(install["ollama_tag"]))
    return pullable


def _read_bounded_response_body(response: requests.Response, max_bytes: int) -> bytes:
    """Read a streamed response without allowing an unbounded in-memory body."""
    chunks: List[bytes] = []
    received = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        value = chunk.encode("utf-8") if isinstance(chunk, str) else bytes(chunk)
        received += len(value)
        if received > max_bytes:
            raise LocalModelRuntimeRequestError("The local model response is too large")
        chunks.append(value)
    return b"".join(chunks)


def _iter_bounded_response_lines(
    response: requests.Response,
    max_event_bytes: int,
    *,
    should_continue: Optional[Callable[[], bool]] = None,
) -> Iterable[bytes]:
    """Yield NDJSON lines while bounding both complete events and partial buffers."""
    buffer = bytearray()
    for chunk in response.iter_content(chunk_size=max_event_bytes):
        if should_continue is not None and not should_continue():
            return
        if not chunk:
            continue
        value = chunk.encode("utf-8") if isinstance(chunk, str) else bytes(chunk)
        buffer.extend(value)
        newline_index = buffer.find(b"\n")
        while newline_index >= 0:
            line = bytes(buffer[:newline_index])
            del buffer[: newline_index + 1]
            if len(line) > max_event_bytes:
                raise LocalModelRuntimeRequestError(
                    "The local model progress event is too large"
                )
            if should_continue is not None and not should_continue():
                return
            yield line
            newline_index = buffer.find(b"\n")
        if len(buffer) > max_event_bytes:
            raise LocalModelRuntimeRequestError(
                "The local model progress event is too large"
            )
    if buffer:
        if len(buffer) > max_event_bytes:
            raise LocalModelRuntimeRequestError(
                "The local model progress event is too large"
            )
        if should_continue is None or should_continue():
            yield bytes(buffer)


@dataclass(frozen=True)
class OllamaPullProgress:
    """One normalized Ollama pull progress event."""

    percent: Optional[int]
    status: str


@dataclass(frozen=True)
class _LocalModelRegistrationRecovery:
    """One short-lived rollback capability issued by a successful unregister."""

    model_id: str
    config_version: str
    runtime_identity: str
    previous_channels: tuple[str, ...]
    previous_models: tuple[str, ...]
    registration_changed: bool
    expires_at: float


class OllamaRuntimeClient:
    """Minimal no-proxy client for a server-configured Ollama runtime."""

    def __init__(
        self,
        base_url: str,
        *,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.base_url = normalize_ollama_base_url(base_url)
        if session is None:
            session = requests.Session()
            session.trust_env = False
        self._session = session

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[Mapping[str, Any]] = None,
        stream: bool = False,
        timeout: tuple[float, float] = (
            OLLAMA_CONNECT_TIMEOUT_SECONDS,
            OLLAMA_READ_TIMEOUT_SECONDS,
        ),
    ) -> requests.Response:
        try:
            response = self._session.request(
                method,
                self._url(path),
                json=dict(json_body) if json_body is not None else None,
                headers={"Accept": "application/x-ndjson" if stream else "application/json"},
                allow_redirects=False,
                # Always stream transport bodies so every caller can enforce a
                # strict byte bound before buffering or parsing the response.
                stream=True,
                timeout=timeout,
            )
        except requests.RequestException as exc:
            raise LocalModelRuntimeUnavailableError(
                "The configured local model runtime is unavailable"
            ) from exc
        if 300 <= response.status_code < 400:
            response.close()
            raise LocalModelRuntimeRequestError("Local model redirects are not allowed")
        if not response.ok:
            response.close()
            raise LocalModelRuntimeRequestError("The local model runtime rejected the request")
        return response

    def list_installed_models(self) -> List[str]:
        """Return validated model names reported by Ollama."""
        response = self._request("GET", "/api/tags")
        try:
            try:
                content = _read_bounded_response_body(response, OLLAMA_MAX_JSON_BYTES)
            except requests.RequestException as exc:
                raise LocalModelRuntimeUnavailableError(
                    "The configured local model runtime is unavailable"
                ) from exc
            try:
                payload = json.loads(content.decode("utf-8")) if content else {}
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise LocalModelRuntimeRequestError(
                    "The local model runtime returned an invalid response"
                ) from exc
        finally:
            response.close()

        entries = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(entries, list):
            raise LocalModelRuntimeRequestError("The local model runtime returned an invalid response")
        installed: Set[str] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            candidate = entry.get("name") or entry.get("model")
            try:
                installed.add(normalize_local_model_id(candidate))
            except LocalModelValidationError:
                continue
        return sorted(installed)

    def pull_model(
        self,
        model_id: str,
        *,
        on_progress: Callable[[OllamaPullProgress], None],
        is_cancel_requested: Optional[Callable[[], bool]] = None,
        timeout_seconds: float = OLLAMA_PULL_TIMEOUT_SECONDS,
    ) -> None:
        """Pull one validated model and emit bounded normalized progress events."""
        model_id = normalize_local_model_id(model_id)
        deadline = time.monotonic() + max(1.0, float(timeout_seconds))

        def should_continue() -> bool:
            if is_cancel_requested is not None and is_cancel_requested():
                return False
            if time.monotonic() > deadline:
                raise LocalModelRuntimeRequestError("The local model download timed out")
            return True

        if not should_continue():
            return
        response = self._request(
            "POST",
            "/api/pull",
            json_body={"name": model_id, "stream": True},
            stream=True,
        )
        saw_terminal_success = False
        try:
            for raw_line in _iter_bounded_response_lines(
                response,
                OLLAMA_MAX_EVENT_BYTES,
                should_continue=should_continue,
            ):
                if not raw_line:
                    continue
                try:
                    event = json.loads(raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise LocalModelRuntimeRequestError(
                        "The local model runtime returned invalid progress"
                    ) from exc
                if not isinstance(event, dict):
                    raise LocalModelRuntimeRequestError(
                        "The local model runtime returned invalid progress"
                    )
                if event.get("error"):
                    raise LocalModelRuntimeRequestError("The local model download failed")
                status = str(event.get("status") or "").strip()
                total = event.get("total")
                completed = event.get("completed")
                percent: Optional[int] = None
                if isinstance(total, (int, float)) and total > 0 and isinstance(completed, (int, float)):
                    percent = max(0, min(99, round((completed / total) * 100)))
                if status == "success":
                    saw_terminal_success = True
                    percent = 99
                on_progress(OllamaPullProgress(percent=percent, status=status))
        except requests.RequestException as exc:
            raise LocalModelRuntimeUnavailableError(
                "The configured local model runtime is unavailable"
            ) from exc
        finally:
            response.close()
        if not should_continue():
            return
        if not saw_terminal_success:
            raise LocalModelRuntimeRequestError("The local model download ended unexpectedly")

    def delete_model(self, model_id: str) -> None:
        """Delete one validated model from Ollama."""
        model_id = normalize_local_model_id(model_id)
        response = self._request(
            "DELETE",
            "/api/delete",
            json_body={"name": model_id},
        )
        response.close()


class LocalModelService:
    """Coordinate catalog allowlisting, runtime tasks, and saved configuration."""

    _LEGACY_PRIMARY_KEYS = (
        "OPENAI_API_KEY",
        "OPENAI_API_KEYS",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_API_KEYS",
        "GEMINI_API_KEY",
        "GEMINI_API_KEYS",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_API_KEYS",
        "AIHUBMIX_KEY",
    )

    def __init__(
        self,
        *,
        system_config_service: SystemConfigService,
        task_queue: AnalysisTaskQueue,
        pullable_model_ids: Callable[[], Iterable[str]],
        client_factory: Callable[[str], OllamaRuntimeClient] = OllamaRuntimeClient,
    ) -> None:
        self._system_config_service = system_config_service
        self._task_queue = task_queue
        self._pullable_model_ids = pullable_model_ids
        self._client_factory = client_factory
        self._task_lock = threading.RLock()
        self._operation_lock = threading.RLock()
        self._registration_recoveries: Dict[str, _LocalModelRegistrationRecovery] = {}
        self._revoked_registration_recoveries: Dict[
            str, _LocalModelRegistrationRecovery
        ] = {}

    @staticmethod
    def _split_csv(value: Any) -> List[str]:
        """Split one comma-separated configuration value into ordered entries."""
        return [item.strip() for item in str(value or "").split(",") if item.strip()]

    @classmethod
    def _append_csv(cls, value: Any, additions: Sequence[str]) -> str:
        """Append entries case-insensitively while preserving the original order."""
        ordered: List[str] = []
        seen: Set[str] = set()
        for item in [*cls._split_csv(value), *additions]:
            identity = item.lower()
            if identity in seen:
                continue
            seen.add(identity)
            ordered.append(item)
        return ",".join(ordered)

    @staticmethod
    def _runtime_route(value: Any) -> str:
        """Resolve a ModelRef to its runtime route while preserving legacy values."""
        raw = str(value or "").strip()
        try:
            decoded = decode_model_ref(raw)
        except ValueError:
            return raw
        return decoded.runtime_route if decoded is not None else raw

    def _config_snapshot(self) -> tuple[str, Dict[str, str]]:
        payload = self._system_config_service.get_config(include_schema=False)
        values = {
            str(item.get("key") or "").upper(): str(item.get("value") or "")
            for item in payload.get("items", [])
            if isinstance(item, dict)
        }
        return str(payload.get("config_version") or ""), values

    @classmethod
    def _has_existing_primary(cls, values: Mapping[str, str]) -> bool:
        """Return whether the effective configuration already has a primary route."""
        if str(values.get("LITELLM_MODEL") or "").strip():
            return True
        generation_backend = str(values.get("GENERATION_BACKEND") or "").strip().lower()
        if generation_backend and generation_backend != "litellm":
            return True

        has_yaml = bool(str(values.get("LITELLM_CONFIG") or "").strip())
        has_channels = cls._has_routable_channels(values)
        has_legacy = any(
            str(values.get(key) or "").strip() for key in cls._LEGACY_PRIMARY_KEYS
        )
        requested_mode = str(values.get("LLM_CONFIG_MODE") or "auto").strip().lower() or "auto"
        if requested_mode == "yaml":
            return has_yaml
        if requested_mode == "channels":
            return has_channels
        if requested_mode == "legacy":
            return has_legacy
        # Auto mode follows the runtime's YAML > Channels > legacy precedence.
        return has_yaml or has_channels or has_legacy

    @staticmethod
    def _has_routable_channels(values: Mapping[str, str]) -> bool:
        """Reuse setup validation to distinguish declared channels from usable routes."""
        return bool(
            SystemConfigService._collect_setup_channel_models(dict(values))
        )

    @staticmethod
    def _is_assigned(values: Mapping[str, str], key: str, model_id: str) -> bool:
        return LocalModelService._runtime_route(values.get(key)) == f"ollama/{model_id}"

    def _base_url(self, values: Mapping[str, str]) -> str:
        """Resolve the normalized server-owned Ollama origin from a snapshot."""
        return normalize_ollama_base_url(values.get("LLM_OLLAMA_BASE_URL"))

    def _require_expected_runtime_snapshot(
        self,
        *,
        config_version: str,
        values: Mapping[str, str],
        expected_config_version: Any,
        expected_runtime_identity: Any,
    ) -> str:
        """Validate opaque caller observations without accepting a request target."""
        expected_version = str(expected_config_version or "").strip()
        if not expected_version or expected_version != config_version:
            raise ConfigConflictError(current_version=config_version)
        configured_base_url = self._base_url(values)
        expected_identity = str(expected_runtime_identity or "").strip()
        configured_identity = get_ollama_runtime_identity(configured_base_url)
        if (
            LOCAL_MODEL_RUNTIME_IDENTITY_PATTERN.fullmatch(expected_identity) is None
            or not secrets.compare_digest(expected_identity, configured_identity)
        ):
            raise ConfigConflictError(current_version=config_version)
        return configured_base_url

    def _prune_registration_recoveries(self) -> None:
        """Discard expired Desktop rollback capabilities and deletion reservations."""
        now = time.monotonic()
        self._registration_recoveries = {
            token: recovery
            for token, recovery in self._registration_recoveries.items()
            if recovery.expires_at > now
        }
        self._revoked_registration_recoveries = {
            token: recovery
            for token, recovery in self._revoked_registration_recoveries.items()
            if recovery.expires_at > now
        }

    def _require_no_pending_unregistration(self, model_id: str) -> None:
        """Keep one model unregistered until its Desktop weight mutation resolves."""
        self._prune_registration_recoveries()
        if any(
            recovery.model_id.lower() == model_id.lower()
            for recovery in self._registration_recoveries.values()
        ):
            raise LocalModelInUseError(
                "Wait for the active model deletion before registering it again"
            )

    def _consume_registration_recovery(
        self,
        model_id: str,
        recovery_token: Any,
        *,
        allow_revoked: bool = False,
    ) -> tuple[str, _LocalModelRegistrationRecovery]:
        """Consume one matching recovery before any fallible completion work."""
        token = str(recovery_token or "").strip()
        if not token or len(token) > 128:
            raise LocalModelValidationError(
                "A valid registration recovery token is required"
            )
        self._prune_registration_recoveries()
        revoked = self._revoked_registration_recoveries.get(token)
        if (
            allow_revoked
            and revoked is not None
            and revoked.model_id.lower() == model_id.lower()
        ):
            return token, revoked
        recovery = self._registration_recoveries.get(token)
        if recovery is None or recovery.model_id.lower() != model_id.lower():
            raise LocalModelValidationError(
                "The registration recovery token is invalid or expired"
        )
        del self._registration_recoveries[token]
        return token, recovery

    def _validate_registration_recovery_configuration(
        self,
        recovery: _LocalModelRegistrationRecovery,
    ) -> tuple[str, Dict[str, str]]:
        """Require the exact post-unregister configuration owned by a recovery."""
        current_version, values = self._config_snapshot()
        if current_version != recovery.config_version:
            raise ConfigConflictError(current_version=current_version)
        current_runtime_identity = get_ollama_runtime_identity(self._base_url(values))
        if not secrets.compare_digest(
            current_runtime_identity,
            recovery.runtime_identity,
        ):
            raise ConfigConflictError(current_version=current_version)

        current_models = self._split_csv(values.get("LLM_OLLAMA_MODELS"))
        expected_models = [
            item
            for item in recovery.previous_models
            if item.lower() != recovery.model_id.lower()
        ]
        expected_channels = list(recovery.previous_channels)
        if not expected_models:
            expected_channels = [
                item for item in expected_channels if item.lower() != "ollama"
            ]
        if (
            [item.lower() for item in current_models]
            != [item.lower() for item in expected_models]
            or [item.lower() for item in self._split_csv(values.get("LLM_CHANNELS"))]
            != [item.lower() for item in expected_channels]
        ):
            raise LocalModelValidationError(
                "The registration recovery no longer matches configuration"
            )
        return current_version, values

    def _allowed_model_ids(self) -> Set[str]:
        """Return the normalized catalog allowlist for lifecycle operations."""
        allowed: Set[str] = set()
        for candidate in self._pullable_model_ids():
            allowed.add(normalize_local_model_id(candidate))
        return allowed

    def _require_pullable(self, model_id: Any) -> str:
        """Validate one model and require membership in the catalog allowlist."""
        normalized = normalize_local_model_id(model_id)
        if normalized not in self._allowed_model_ids():
            raise LocalModelNotAllowedError(
                "The selected model is not pullable from the authoritative catalog"
            )
        return normalized

    def get_configuration(self) -> Dict[str, Any]:
        """Return caller-safe local model assignment state."""
        config_version, values = self._config_snapshot()
        return {
            "config_version": config_version,
            "registered_models": self._split_csv(values.get("LLM_OLLAMA_MODELS")),
            "primary_model": str(values.get("LITELLM_MODEL") or "").strip(),
            "agent_model": str(values.get("AGENT_LITELLM_MODEL") or "").strip(),
        }

    def configure_model(
        self,
        model_id: Any,
        *,
        assignment: LocalModelAssignment = "auto",
    ) -> Dict[str, Any]:
        """Register one model and optionally assign it without stealing an existing default."""
        with self._operation_lock:
            normalized = self._require_pullable(model_id)
            return self._register_installed_model(normalized, assignment=assignment)

    def activate_desktop_model(
        self,
        model_id: Any,
        *,
        expected_config_version: Any,
        expected_runtime_identity: Any,
    ) -> Dict[str, Any]:
        """Activate a Desktop pull only when its runtime snapshot is still current."""
        with self._operation_lock:
            normalized = self._require_pullable(model_id)
            config_version, values = self._config_snapshot()
            base_url = self._require_expected_runtime_snapshot(
                config_version=config_version,
                values=values,
                expected_config_version=expected_config_version,
                expected_runtime_identity=expected_runtime_identity,
            )
            return self._register_installed_model_from_snapshot(
                normalized,
                assignment="auto",
                config_version=config_version,
                values=values,
                base_url=base_url,
            )

    def _register_installed_model(
        self,
        normalized: str,
        *,
        assignment: LocalModelAssignment,
    ) -> Dict[str, Any]:
        self._require_no_pending_unregistration(normalized)
        if assignment not in {"auto", "primary", "agent"}:
            raise LocalModelValidationError("Invalid local model assignment")

        config_version, values = self._config_snapshot()
        base_url = self._base_url(values)
        return self._register_installed_model_from_snapshot(
            normalized,
            assignment=assignment,
            config_version=config_version,
            values=values,
            base_url=base_url,
        )

    def _register_installed_model_from_snapshot(
        self,
        normalized: str,
        *,
        assignment: LocalModelAssignment,
        config_version: str,
        values: Mapping[str, str],
        base_url: str,
    ) -> Dict[str, Any]:
        if assignment not in {"auto", "primary", "agent"}:
            raise LocalModelValidationError("Invalid local model assignment")
        installed = {
            item.lower()
            for item in self._client_factory(base_url).list_installed_models()
        }
        if normalized.lower() not in installed:
            raise LocalModelNotInstalledError(
                "The selected local model is not installed in the configured runtime"
            )
        return self._configure_model_from_snapshot(
            normalized,
            assignment=assignment,
            config_version=config_version,
            values=values,
            base_url=base_url,
        )

    def _configure_model_from_snapshot(
        self,
        normalized: str,
        *,
        assignment: LocalModelAssignment,
        config_version: str,
        values: Mapping[str, str],
        base_url: str,
    ) -> Dict[str, Any]:
        """Activate a verified model against one immutable runtime/config snapshot."""
        with self._operation_lock:
            return self._configure_model_from_snapshot_locked(
                normalized,
                assignment=assignment,
                config_version=config_version,
                values=values,
                base_url=base_url,
            )

    def _configure_model_from_snapshot_locked(
        self,
        normalized: str,
        *,
        assignment: LocalModelAssignment,
        config_version: str,
        values: Mapping[str, str],
        base_url: str,
    ) -> Dict[str, Any]:
        self._require_no_pending_unregistration(normalized)
        current_channels = values.get("LLM_CHANNELS", "")
        current_models = values.get("LLM_OLLAMA_MODELS", "")
        route = f"ollama/{normalized}"
        updates: List[Dict[str, str]] = [
            {"key": "LLM_CHANNELS", "value": self._append_csv(current_channels, ["ollama"])},
            {"key": "LLM_OLLAMA_PROVIDER", "value": "ollama"},
            {"key": "LLM_OLLAMA_PROTOCOL", "value": "ollama"},
            {"key": "LLM_OLLAMA_BASE_URL", "value": base_url},
            {"key": "LLM_OLLAMA_MODELS", "value": self._append_csv(current_models, [normalized])},
            {"key": "LLM_OLLAMA_ENABLED", "value": "true"},
        ]

        selected_primary = assignment == "primary" or (
            assignment == "auto" and not self._has_existing_primary(values)
        )
        if selected_primary:
            updates.extend(
                [
                    {"key": "LLM_CONFIG_MODE", "value": "channels"},
                    {"key": "GENERATION_BACKEND", "value": "litellm"},
                    {"key": "LITELLM_MODEL", "value": route},
                ]
            )
        requested_mode = str(values.get("LLM_CONFIG_MODE") or "auto").strip().lower() or "auto"
        had_channels = self._has_routable_channels(values)
        has_yaml = bool(str(values.get("LITELLM_CONFIG") or "").strip())
        has_legacy = any(str(values.get(key) or "").strip() for key in self._LEGACY_PRIMARY_KEYS)
        if assignment == "agent":
            incompatible_agent_source = (
                requested_mode in {"legacy", "yaml"}
                or (requested_mode == "auto" and has_yaml)
                or (requested_mode == "auto" and not had_channels and has_legacy)
            )
            if incompatible_agent_source:
                raise LocalModelValidationError(
                    "The active configuration source cannot route an Ollama Agent model"
                )
            updates.extend(
                [
                    {"key": "AGENT_GENERATION_BACKEND", "value": "litellm"},
                    {"key": "AGENT_LITELLM_MODEL", "value": route},
                ]
            )
        if (
            not selected_primary
            and assignment != "agent"
            and requested_mode == "auto"
            and not had_channels
            and has_legacy
        ):
            # Adding the first channel would otherwise make auto mode silently
            # supersede an existing legacy primary model.
            updates.append({"key": "LLM_CONFIG_MODE", "value": "legacy"})

        result = self._system_config_service.update(
            config_version=config_version,
            items=updates,
            reload_now=True,
            validate_connectivity=False,
            actor="local_model_center",
        )
        configuration = self.get_configuration()
        return {
            **result,
            **configuration,
            "model_id": normalized,
            "selected_primary": selected_primary,
            "selected_agent": assignment == "agent",
        }

    def unregister_model(
        self,
        model_id: Any,
        *,
        expected_config_version: Any,
        expected_runtime_identity: Any,
    ) -> Dict[str, Any]:
        """Remove a non-active model from the Ollama connection configuration."""
        with self._task_lock, self._operation_lock:
            normalized = self._require_pullable(model_id)
            self._require_no_pending_unregistration(normalized)
            if self._pending_pull(normalized) is not None:
                raise LocalModelInUseError(
                    "Wait for the active model download before deleting it"
                )
            config_version, values = self._config_snapshot()
            base_url = self._require_expected_runtime_snapshot(
                config_version=config_version,
                values=values,
                expected_config_version=expected_config_version,
                expected_runtime_identity=expected_runtime_identity,
            )
            current_models = self._split_csv(values.get("LLM_OLLAMA_MODELS"))
            registration_changed = any(
                item.lower() == normalized.lower() for item in current_models
            )
            result = self._unregister_model_from_snapshot(
                normalized,
                config_version=config_version,
                values=values,
            )
            now = time.monotonic()
            self._prune_registration_recoveries()
            recovery_token = secrets.token_urlsafe(32)
            self._registration_recoveries[recovery_token] = (
                _LocalModelRegistrationRecovery(
                    model_id=normalized,
                    config_version=str(result.get("config_version") or ""),
                    runtime_identity=get_ollama_runtime_identity(base_url),
                    previous_channels=tuple(
                        self._split_csv(values.get("LLM_CHANNELS"))
                    ),
                    previous_models=tuple(current_models),
                    registration_changed=registration_changed,
                    expires_at=now + LOCAL_MODEL_REGISTRATION_RECOVERY_TTL_SECONDS,
                )
            )
            return {**result, "recovery_token": recovery_token}

    def finalize_unregistration(
        self,
        model_id: Any,
        *,
        recovery_token: Any,
    ) -> Dict[str, Any]:
        """Revoke a rollback capability after Desktop confirms weight deletion."""
        with self._operation_lock:
            normalized = self._require_pullable(model_id)
            token, recovery = self._consume_registration_recovery(
                normalized,
                recovery_token,
                allow_revoked=True,
            )
            self._revoked_registration_recoveries[token] = recovery
            self._validate_registration_recovery_configuration(recovery)
            return {
                **self.get_configuration(),
                "success": True,
                "model_id": normalized,
                "deleted": True,
            }

    def restore_registration(
        self,
        model_id: Any,
        *,
        recovery_token: Any,
    ) -> Dict[str, Any]:
        """Restore one exact Desktop snapshot without probing a stopped runtime."""
        with self._operation_lock:
            normalized = self._require_pullable(model_id)
            _token, recovery = self._consume_registration_recovery(
                normalized,
                recovery_token,
            )
            current_version, _values = self._validate_registration_recovery_configuration(
                recovery
            )
            if not recovery.registration_changed:
                return {
                    **self.get_configuration(),
                    "success": True,
                    "model_id": normalized,
                    "deleted": False,
                }
            result = self._system_config_service.update(
                config_version=current_version,
                items=[
                    {
                        "key": "LLM_CHANNELS",
                        "value": ",".join(recovery.previous_channels),
                    },
                    {
                        "key": "LLM_OLLAMA_MODELS",
                        "value": ",".join(recovery.previous_models),
                    },
                ],
                reload_now=True,
                validate_connectivity=False,
                actor="local_model_registration_restore",
            )
            return {
                **result,
                **self.get_configuration(),
                "model_id": normalized,
            }

    def _unregister_model_from_snapshot(
        self,
        normalized: str,
        *,
        config_version: str,
        values: Mapping[str, str],
    ) -> Dict[str, Any]:
        """Remove one model using the exact configuration snapshot already validated."""
        if self._is_model_referenced(values, normalized):
            raise LocalModelInUseError("Change the active model assignment before deleting it")

        current_models = self._split_csv(values.get("LLM_OLLAMA_MODELS"))
        remaining_models = [item for item in current_models if item.lower() != normalized.lower()]
        if len(remaining_models) == len(current_models):
            return {**self.get_configuration(), "success": True, "model_id": normalized}

        updates = [{"key": "LLM_OLLAMA_MODELS", "value": ",".join(remaining_models)}]
        if not remaining_models:
            remaining_channels = [
                item for item in self._split_csv(values.get("LLM_CHANNELS"))
                if item.lower() != "ollama"
            ]
            updates.append({"key": "LLM_CHANNELS", "value": ",".join(remaining_channels)})
        validation = self._system_config_service.validate(items=updates)
        errors = [
            issue
            for issue in validation["issues"]
            if issue.get("severity") == "error"
        ]
        if any(issue.get("code") == "model_in_use" for issue in errors):
            raise LocalModelInUseError(
                "Change every active model assignment before deleting it"
            )
        if errors:
            raise ConfigValidationError(issues=errors)
        result = self._system_config_service.update(
            config_version=config_version,
            items=updates,
            reload_now=True,
            validate_connectivity=False,
            actor="local_model_center",
        )
        return {**result, **self.get_configuration(), "model_id": normalized}

    @classmethod
    def _is_model_referenced(
        cls,
        values: Mapping[str, str],
        model_id: str,
    ) -> bool:
        """Protect explicit task routes and the effective implicit channel primary."""
        route = f"ollama/{model_id}".lower()
        for key in ("LITELLM_MODEL", "AGENT_LITELLM_MODEL", "VISION_MODEL"):
            if cls._runtime_route(values.get(key)).lower() == route:
                return True
        if any(
            cls._runtime_route(candidate).lower() == route
            for candidate in cls._split_csv(values.get("LITELLM_FALLBACK_MODELS"))
        ):
            return True

        if str(values.get("LITELLM_MODEL") or "").strip():
            return False
        mode = str(values.get("LLM_CONFIG_MODE") or "auto").strip().lower() or "auto"
        if mode not in {"auto", "channels"}:
            return False
        if mode == "auto" and str(values.get("LITELLM_CONFIG") or "").strip():
            return False
        for channel in cls._split_csv(values.get("LLM_CHANNELS")):
            prefix = f"LLM_{channel.upper()}"
            enabled = str(values.get(f"{prefix}_ENABLED") or "true").strip().lower()
            if enabled in {"false", "0", "no", "off"}:
                continue
            models = cls._split_csv(values.get(f"{prefix}_MODELS"))
            if not models:
                continue
            return channel.lower() == "ollama" and models[0].lower() == model_id.lower()
        return False

    def get_runtime_status(self) -> Dict[str, Any]:
        """Return installed models or a stable unavailable state without raw diagnostics."""
        _config_version, values = self._config_snapshot()
        try:
            installed = self._client_factory(self._base_url(values)).list_installed_models()
        except LocalModelError:
            return {
                "runtime": "ollama",
                "status": "unavailable",
                "installed_models": [],
                "manual_pull_supported": True,
            }
        return {
            "runtime": "ollama",
            "status": "running",
            "installed_models": installed,
            "manual_pull_supported": False,
        }

    def _pending_pull(self, model_id: str) -> Optional[TaskInfo]:
        """Return the active canonical pull task for one model, when present."""
        for task in self._task_queue.list_pending_tasks():
            if task.report_type == LOCAL_MODEL_PULL_TASK_KIND and task.stock_code == model_id:
                return task
        return None

    def start_pull(self, model_id: Any) -> TaskInfo:
        """Submit one allowlisted pull to the shared background task queue."""
        normalized = self._require_pullable(model_id)
        with self._task_lock, self._operation_lock:
            self._require_no_pending_unregistration(normalized)
            pending = self._pending_pull(normalized)
            if pending is not None:
                return pending

            config_version, values = self._config_snapshot()
            base_url = self._base_url(values)
            # Fail before accepting a task so the UI can immediately offer the
            # manual command instead of polling a predictably failed worker.
            self._client_factory(base_url).list_installed_models()
            def run_pull(context: TaskRunContext) -> Dict[str, Any]:
                client = self._client_factory(base_url)

                def update(progress: OllamaPullProgress) -> None:
                    context.update_progress(
                        progress.percent if progress.percent is not None else 1,
                        "Downloading local model",
                    )

                client.pull_model(
                    normalized,
                    on_progress=update,
                    is_cancel_requested=context.is_cancel_requested,
                )
                if context.is_cancel_requested():
                    return {
                        "model_id": normalized,
                        "activated": False,
                        "selected_primary": False,
                    }
                try:
                    activation = self._configure_model_from_snapshot(
                        normalized,
                        assignment="auto",
                        config_version=config_version,
                        values=values,
                        base_url=base_url,
                    )
                except Exception as exc:  # broad-exception: fallback_recorded - download already succeeded
                    log_safe_exception(
                        logger,
                        "Local model activation failed after download",
                        exc,
                        error_code="local_model_activation_failed",
                        context={"model_id": normalized},
                    )
                    return {
                        "model_id": normalized,
                        "activated": False,
                        "selected_primary": False,
                    }
                return {
                    "model_id": normalized,
                    "activated": True,
                    "selected_primary": bool(activation.get("selected_primary")),
                }

            command = TaskCommand(
                kind=LOCAL_MODEL_PULL_TASK_KIND,
                run=run_pull,
                metadata={
                    "stock_code": normalized,
                    "stock_name": normalized,
                    "report_type": LOCAL_MODEL_PULL_TASK_KIND,
                    "message": "Local model download queued",
                },
                failure_error_code="local_model_pull_failed",
            )
            task_id = self._task_queue.submit(command)
            task = self._task_queue.get_task(task_id)
            if task is None:  # pragma: no cover - queue adapter invariant
                raise RuntimeError("Accepted local model pull task is unavailable")
            return task

    def get_pull(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Return a caller-safe pull task snapshot."""
        task = self._task_queue.get_task(str(task_id or ""))
        if task is None or task.report_type != LOCAL_MODEL_PULL_TASK_KIND:
            return None
        result = (
            task.result
            if task.status == TaskStatusEnum.COMPLETED and isinstance(task.result, dict)
            else None
        )
        return {
            "task_id": task.task_id,
            "status": (
                task.status.value
                if isinstance(task.status, TaskStatusEnum)
                else str(task.status)
            ),
            "progress": task.progress,
            "model_id": task.stock_code,
            "error": task.public_error(),
            "result": result,
        }

    def delete_model(self, model_id: Any) -> Dict[str, Any]:
        """Validate and unregister one catalog model before deleting its weights."""
        with self._task_lock, self._operation_lock:
            return self._delete_model(model_id)

    def _delete_model(self, model_id: Any) -> Dict[str, Any]:
        """Apply the server-side unregister/delete transaction for one model."""
        normalized = self._require_pullable(model_id)
        self._require_no_pending_unregistration(normalized)
        if self._pending_pull(normalized) is not None:
            raise LocalModelInUseError(
                "Wait for the active model download before deleting it"
            )
        config_version, previous_values = self._config_snapshot()
        base_url = self._base_url(previous_values)
        previous_channels = self._split_csv(previous_values.get("LLM_CHANNELS"))
        previous_models = self._split_csv(previous_values.get("LLM_OLLAMA_MODELS"))
        was_registered = any(
            item.lower() == normalized.lower()
            for item in previous_models
        )
        remaining_models = [
            item for item in previous_models if item.lower() != normalized.lower()
        ]
        remaining_channels = list(previous_channels)
        if not remaining_models:
            remaining_channels = [
                item for item in previous_channels if item.lower() != "ollama"
            ]
        result = self._unregister_model_from_snapshot(
            normalized,
            config_version=config_version,
            values=previous_values,
        )
        client = self._client_factory(base_url)
        try:
            client.delete_model(normalized)
        except Exception as exc:  # broad-exception: fallback_recorded - recover config after runtime failure
            log_safe_exception(
                logger,
                "Local model deletion failed",
                exc,
                error_code="local_model_delete_failed",
                context={"model_id": normalized},
            )
            weights_remain = True
            try:
                installed = client.list_installed_models()
                weights_remain = any(
                    item.lower() == normalized.lower() for item in installed
                )
            except Exception as probe_exc:  # broad-exception: fallback_recorded - restore conservatively
                log_safe_exception(
                    logger,
                    "Could not confirm local model state after deletion failure",
                    probe_exc,
                    error_code="local_model_delete_probe_failed",
                    context={"model_id": normalized},
                )

            if not weights_remain:
                return {**result, "deleted": True, "model_id": normalized}

            if was_registered and weights_remain:
                current_version, current_values = self._config_snapshot()
                current_channels = self._split_csv(current_values.get("LLM_CHANNELS"))
                current_models = self._split_csv(current_values.get("LLM_OLLAMA_MODELS"))
                same_runtime = False
                try:
                    same_runtime = self._base_url(current_values) == base_url
                except LocalModelError:
                    pass
                related_config_unchanged = (
                    [item.lower() for item in current_channels]
                    == [item.lower() for item in remaining_channels]
                    and [item.lower() for item in current_models]
                    == [item.lower() for item in remaining_models]
                )
                if same_runtime and related_config_unchanged:
                    try:
                        self._system_config_service.update(
                            config_version=current_version,
                            items=[
                                {
                                    "key": "LLM_CHANNELS",
                                    "value": ",".join(previous_channels),
                                },
                                {
                                    "key": "LLM_OLLAMA_MODELS",
                                    "value": ",".join(previous_models),
                                },
                            ],
                            reload_now=True,
                            validate_connectivity=False,
                            actor="local_model_delete_rollback",
                        )
                    except Exception as rollback_exc:  # broad-exception: fallback_recorded - preserve original boundary
                        log_safe_exception(
                            logger,
                            "Local model registration recovery failed",
                            rollback_exc,
                            error_code="local_model_delete_rollback_failed",
                            context={"model_id": normalized},
                        )
                        raise LocalModelRuntimeRequestError(
                            "Local model deletion failed and registration recovery was rejected"
                        ) from rollback_exc
                else:
                    logger.warning(
                        "Skipped local model registration recovery because related configuration changed",
                        extra={"error_code": "local_model_delete_rollback_conflict"},
                    )
            raise
        return {**result, "deleted": True, "model_id": normalized}
