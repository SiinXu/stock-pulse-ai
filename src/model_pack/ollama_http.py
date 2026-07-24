from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Optional
from urllib.parse import urlsplit, urlunsplit

import requests

from src.model_pack.errors import ModelPackError
from src.model_pack.models import InspectedModelPack
from src.security.outbound_policy import OutboundPolicyError, safe_request


DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_IMPORT_TIMEOUT_SECONDS = 30 * 60
MAX_OLLAMA_RESPONSE_BYTES = 1024 * 1024


def normalize_ollama_native_base_url(raw_url: str) -> str:
    """Normalize a configured OpenAI-compatible Ollama URL to its native API root."""

    candidate = str(raw_url or "").strip() or DEFAULT_OLLAMA_BASE_URL
    if any(character.isspace() or character == "\\" for character in candidate):
        raise ModelPackError(
            "invalid_ollama_configuration",
            "LLM_OLLAMA_BASE_URL is invalid. Fix it in Settings and try again.",
        )
    try:
        parsed = urlsplit(candidate)
        port = parsed.port
    except ValueError as exc:
        raise ModelPackError(
            "invalid_ollama_configuration",
            "LLM_OLLAMA_BASE_URL is invalid. Fix it in Settings and try again.",
        ) from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ModelPackError(
            "invalid_ollama_configuration",
            "LLM_OLLAMA_BASE_URL is invalid. Fix it in Settings and try again.",
        )
    path = parsed.path.rstrip("/")
    if path == "/v1":
        path = ""
    elif path:
        raise ModelPackError(
            "invalid_ollama_configuration",
            (
                "LLM_OLLAMA_BASE_URL must point to the Ollama server root or /v1. "
                "Fix it in Settings and try again."
            ),
        )
    host = parsed.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    netloc = f"{host}:{port}" if port is not None else host
    return urlunsplit((parsed.scheme, netloc, path, "", "")).rstrip("/")


def _actionable_request_error(exc: BaseException) -> ModelPackError:
    if isinstance(exc, OutboundPolicyError):
        return ModelPackError(
            "ollama_access_blocked",
            (
                "StockPulse cannot reach the configured Ollama server under the outbound "
                "security policy. Add its exact host and port to OUTBOUND_HTTP_ALLOWLIST, "
                "then try again."
            ),
        )
    return ModelPackError(
        "ollama_unavailable",
        (
            "Ollama is not reachable. Start Ollama, verify LLM_OLLAMA_BASE_URL, "
            "and try the import again."
        ),
    )


class OllamaHttpModelPackExecutor:
    """Create a validated Model Pack through Ollama's native HTTP API."""

    def __init__(
        self,
        *,
        base_url_provider: Callable[[], str],
        requester: Callable[..., Any] = safe_request,
        allowlist_provider: Optional[Callable[[], Optional[Iterable[str]]]] = None,
        timeout_seconds: float = DEFAULT_OLLAMA_IMPORT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url_provider = base_url_provider
        self._requester = requester
        self._allowlist_provider = allowlist_provider
        self._timeout_seconds = max(1.0, float(timeout_seconds))

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        if self._allowlist_provider is not None:
            allowlist = self._allowlist_provider()
            if allowlist is not None:
                kwargs["allowlist"] = tuple(allowlist)
        kwargs.setdefault("allow_redirects", False)
        kwargs.setdefault("max_response_bytes", MAX_OLLAMA_RESPONSE_BYTES)
        kwargs.setdefault("timeout", self._timeout_seconds)
        try:
            return self._requester(method, url, **kwargs)
        except ModelPackError:
            raise
        except (OutboundPolicyError, requests.RequestException, OSError) as exc:
            raise _actionable_request_error(exc) from exc

    @staticmethod
    def _close_response(response: Any) -> None:
        close = getattr(response, "close", None)
        if callable(close):
            close()

    @staticmethod
    def _require_status(
        response: Any,
        *,
        accepted: Iterable[int],
        operation: str,
    ) -> None:
        try:
            status_code = int(response.status_code)
        except (AttributeError, TypeError, ValueError):
            status_code = 0
        if status_code in set(accepted):
            return
        if status_code in {502, 503, 504} or status_code == 0:
            raise ModelPackError(
                "ollama_unavailable",
                (
                    "Ollama is not ready for model import. Start or restart Ollama "
                    "and try again."
                ),
            )
        raise ModelPackError(
            "ollama_create_failed",
            (
                f"Ollama rejected the {operation} step. "
                "Check Ollama compatibility and rebuild or re-download the Model Pack."
            ),
            details={"http_status": status_code, "operation": operation},
        )

    def _ensure_blob(
        self,
        *,
        base_url: str,
        gguf_path: Path,
        digest: str,
    ) -> None:
        blob_url = f"{base_url}/api/blobs/sha256:{digest}"
        head_response = self._request("HEAD", blob_url)
        try:
            status_code = int(head_response.status_code)
        except (AttributeError, TypeError, ValueError):
            status_code = 0
        try:
            if status_code == 200:
                return
            if status_code != 404:
                self._require_status(
                    head_response,
                    accepted={200, 404},
                    operation="blob check",
                )
        finally:
            self._close_response(head_response)
        try:
            with gguf_path.open("rb") as file_obj:
                response = self._request(
                    "POST",
                    blob_url,
                    data=file_obj,
                    headers={
                        "Content-Type": "application/octet-stream",
                        "Content-Length": str(gguf_path.stat().st_size),
                    },
                )
        except ModelPackError:
            raise
        except OSError as exc:
            raise ModelPackError(
                "file_read_failed",
                "Could not read the validated GGUF file. Check disk access and try again.",
            ) from exc
        try:
            self._require_status(response, accepted={200, 201}, operation="GGUF upload")
        finally:
            self._close_response(response)

    @staticmethod
    def _create_payload(inspected: InspectedModelPack) -> Dict[str, Any]:
        manifest = inspected.manifest
        digest = manifest.file_for_role("gguf").sha256
        try:
            license_text = inspected.license_path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ModelPackError(
                "invalid_license_file",
                "The declared license must be readable UTF-8 text. Rebuild the Model Pack.",
            ) from exc
        payload: Dict[str, Any] = {
            "model": manifest.model_id,
            "files": {manifest.gguf_file: f"sha256:{digest}"},
            "license": license_text,
            "stream": False,
        }
        if inspected.modelfile.parameters:
            payload["parameters"] = dict(inspected.modelfile.parameters)
        if inspected.modelfile.template is not None:
            payload["template"] = inspected.modelfile.template
        if inspected.modelfile.system is not None:
            payload["system"] = inspected.modelfile.system
        return payload

    def create(
        self,
        inspected: InspectedModelPack,
        *,
        on_progress: Optional[Callable[[int, str], None]] = None,
    ) -> None:
        base_url = normalize_ollama_native_base_url(self._base_url_provider())
        digest = inspected.manifest.file_for_role("gguf").sha256
        if on_progress is not None:
            on_progress(45, "Uploading the verified GGUF data to Ollama")
        self._ensure_blob(
            base_url=base_url,
            gguf_path=inspected.gguf_path,
            digest=digest,
        )
        if on_progress is not None:
            on_progress(75, "Creating the Ollama model")
        response = self._request(
            "POST",
            f"{base_url}/api/create",
            json=self._create_payload(inspected),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        try:
            self._require_status(response, accepted={200, 201}, operation="model creation")
            try:
                body = response.json()
            except (AttributeError, json.JSONDecodeError, ValueError) as exc:
                raise ModelPackError(
                    "ollama_create_failed",
                    (
                        "Ollama returned an unreadable create response. "
                        "Update or restart Ollama and try again."
                    ),
                ) from exc
        finally:
            self._close_response(response)
        if not isinstance(body, dict) or body.get("status") != "success":
            raise ModelPackError(
                "ollama_create_failed",
                (
                    "Ollama did not finish creating the model. "
                    "Check Ollama logs and try the import again."
                ),
            )
        if on_progress is not None:
            on_progress(90, "Activating the imported model")


__all__ = [
    "DEFAULT_OLLAMA_BASE_URL",
    "OllamaHttpModelPackExecutor",
    "normalize_ollama_native_base_url",
]
