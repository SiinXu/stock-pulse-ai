"""Local Ollama model lifecycle and zero-config activation services."""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Set
from urllib.parse import urlsplit, urlunsplit

import requests

from src.llm.model_ref import decode_model_ref
from src.services.system_config_service import SystemConfigService
from src.services.task_queue import AnalysisTaskQueue, TaskInfo, TaskStatus


OLLAMA_DEFAULT_BASE_URL = "http://127.0.0.1:11434"
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
LOCAL_MODEL_MAX_ID_LENGTH = 128
LocalModelAssignment = Literal["auto", "primary", "agent"]


class LocalModelError(Exception):
    """Base error for stable local-model service failures."""

    error_code = "local_model_error"


class LocalModelValidationError(LocalModelError):
    """Raised when a model identifier or requested operation is invalid."""

    error_code = "invalid_local_model"


class LocalModelNotAllowedError(LocalModelError):
    """Raised when a model is not pullable from the authoritative catalog."""

    error_code = "local_model_not_pullable"


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
    hostname = parsed.hostname.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return urlunsplit((parsed.scheme.lower(), netloc, "", "", ""))


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


@dataclass(frozen=True)
class OllamaPullProgress:
    """One normalized Ollama pull progress event."""

    percent: Optional[int]
    status: str


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
                stream=stream,
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
            content = response.content
            if len(content) > OLLAMA_MAX_JSON_BYTES:
                raise LocalModelRuntimeRequestError("The local model response is too large")
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
        timeout_seconds: float = OLLAMA_PULL_TIMEOUT_SECONDS,
    ) -> None:
        """Pull one validated model and emit bounded normalized progress events."""
        model_id = normalize_local_model_id(model_id)
        response = self._request(
            "POST",
            "/api/pull",
            json_body={"name": model_id, "stream": True},
            stream=True,
        )
        deadline = time.monotonic() + max(1.0, float(timeout_seconds))
        saw_terminal_success = False
        try:
            for raw_line in response.iter_lines():
                if time.monotonic() > deadline:
                    raise LocalModelRuntimeRequestError("The local model download timed out")
                if not raw_line:
                    continue
                if len(raw_line) > OLLAMA_MAX_EVENT_BYTES:
                    raise LocalModelRuntimeRequestError("The local model progress event is too large")
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

    @staticmethod
    def _split_csv(value: Any) -> List[str]:
        return [item.strip() for item in str(value or "").split(",") if item.strip()]

    @classmethod
    def _append_csv(cls, value: Any, additions: Sequence[str]) -> str:
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
        if str(values.get("LITELLM_MODEL") or "").strip():
            return True
        generation_backend = str(values.get("GENERATION_BACKEND") or "").strip().lower()
        if generation_backend and generation_backend != "litellm":
            return True

        has_yaml = bool(str(values.get("LITELLM_CONFIG") or "").strip())
        has_channels = False
        for channel in cls._split_csv(values.get("LLM_CHANNELS")):
            prefix = f"LLM_{channel.upper()}"
            enabled = str(values.get(f"{prefix}_ENABLED") or "true").strip().lower()
            if enabled not in {"false", "0", "no", "off"} and cls._split_csv(
                values.get(f"{prefix}_MODELS")
            ):
                has_channels = True
                break
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
    def _is_assigned(values: Mapping[str, str], key: str, model_id: str) -> bool:
        return LocalModelService._runtime_route(values.get(key)) == f"ollama/{model_id}"

    def _base_url(self, values: Mapping[str, str]) -> str:
        return normalize_ollama_base_url(values.get("LLM_OLLAMA_BASE_URL"))

    def _allowed_model_ids(self) -> Set[str]:
        allowed: Set[str] = set()
        for candidate in self._pullable_model_ids():
            allowed.add(normalize_local_model_id(candidate))
        return allowed

    def _require_pullable(self, model_id: Any) -> str:
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
        normalized = self._require_pullable(model_id)
        if assignment not in {"auto", "primary", "agent"}:
            raise LocalModelValidationError("Invalid local model assignment")

        config_version, values = self._config_snapshot()
        current_channels = values.get("LLM_CHANNELS", "")
        current_models = values.get("LLM_OLLAMA_MODELS", "")
        route = f"ollama/{normalized}"
        updates: List[Dict[str, str]] = [
            {"key": "LLM_CHANNELS", "value": self._append_csv(current_channels, ["ollama"])},
            {"key": "LLM_OLLAMA_PROVIDER", "value": "ollama"},
            {"key": "LLM_OLLAMA_PROTOCOL", "value": "ollama"},
            {"key": "LLM_OLLAMA_BASE_URL", "value": self._base_url(values)},
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
        elif assignment == "agent":
            updates.append({"key": "AGENT_LITELLM_MODEL", "value": route})

        requested_mode = str(values.get("LLM_CONFIG_MODE") or "auto").strip().lower() or "auto"
        had_channels = bool(self._split_csv(current_channels))
        has_legacy = any(str(values.get(key) or "").strip() for key in self._LEGACY_PRIMARY_KEYS)
        if (
            not selected_primary
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

    def unregister_model(self, model_id: Any) -> Dict[str, Any]:
        """Remove a non-active model from the Ollama connection configuration."""
        normalized = self._require_pullable(model_id)
        config_version, values = self._config_snapshot()
        if self._is_assigned(values, "LITELLM_MODEL", normalized) or self._is_assigned(
            values, "AGENT_LITELLM_MODEL", normalized
        ):
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
        result = self._system_config_service.update(
            config_version=config_version,
            items=updates,
            reload_now=True,
            validate_connectivity=False,
            actor="local_model_center",
        )
        return {**result, **self.get_configuration(), "model_id": normalized}

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
        for task in self._task_queue.list_pending_tasks():
            if task.report_type == LOCAL_MODEL_PULL_TASK_KIND and task.stock_code == model_id:
                return task
        return None

    def start_pull(self, model_id: Any) -> TaskInfo:
        """Submit one allowlisted pull to the shared background task queue."""
        normalized = self._require_pullable(model_id)
        with self._task_lock:
            pending = self._pending_pull(normalized)
            if pending is not None:
                return pending

            _config_version, values = self._config_snapshot()
            client = self._client_factory(self._base_url(values))
            # Fail before accepting a task so the UI can immediately offer the
            # manual command instead of polling a predictably failed worker.
            client.list_installed_models()
            task_id = uuid.uuid4().hex

            def run_pull() -> Dict[str, Any]:
                def update(progress: OllamaPullProgress) -> None:
                    self._task_queue.update_task_progress(
                        task_id,
                        progress.percent if progress.percent is not None else 1,
                        "Downloading local model",
                        message_code="local_model.pull.progress",
                        message_params={"model_id": normalized, "status": progress.status},
                    )

                client.pull_model(normalized, on_progress=update)
                activation = self.configure_model(normalized, assignment="auto")
                return {
                    "model_id": normalized,
                    "activated": True,
                    "selected_primary": bool(activation.get("selected_primary")),
                }

            return self._task_queue.submit_background_task(
                run_pull,
                stock_code=normalized,
                stock_name=normalized,
                report_type=LOCAL_MODEL_PULL_TASK_KIND,
                message="Local model download queued",
                task_id=task_id,
                trace_id=task_id,
                failure_error_code="local_model_pull_failed",
            )

    def get_pull(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Return a caller-safe pull task snapshot."""
        task = self._task_queue.get_task(str(task_id or ""))
        if task is None or task.report_type != LOCAL_MODEL_PULL_TASK_KIND:
            return None
        result = task.result if task.status == TaskStatus.COMPLETED and isinstance(task.result, dict) else None
        return {
            "task_id": task.task_id,
            "status": task.status.value if isinstance(task.status, TaskStatus) else str(task.status),
            "progress": task.progress,
            "model_id": task.stock_code,
            "error": task.public_error(),
            "result": result,
        }

    def delete_model(self, model_id: Any) -> Dict[str, Any]:
        """Delete one non-active catalog model and remove its saved registration."""
        normalized = self._require_pullable(model_id)
        _config_version, values = self._config_snapshot()
        if self._is_assigned(values, "LITELLM_MODEL", normalized) or self._is_assigned(
            values, "AGENT_LITELLM_MODEL", normalized
        ):
            raise LocalModelInUseError("Change the active model assignment before deleting it")
        self._client_factory(self._base_url(values)).delete_model(normalized)
        result = self.unregister_model(normalized)
        return {**result, "deleted": True, "model_id": normalized}
