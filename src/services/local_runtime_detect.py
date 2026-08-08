"""Fast, loopback-only local runtime detection for zero-config first success.

Detection is intentionally observational: it never mutates configuration, never
blocks startup, and treats every probe failure as log-only. Non-loopback hosts
are refused even when present in the effective config map.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence
from urllib.parse import urlsplit

import requests

from src.llm.provider_catalog import get_provider
from src.security.http_bind import is_local_only_bind
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

_OLLAMA_PROVIDER = get_provider("ollama")
if _OLLAMA_PROVIDER is None:  # pragma: no cover - checked-in catalog invariant
    raise RuntimeError("The Ollama provider is missing from the provider catalog")

DEFAULT_OLLAMA_LOOPBACK_BASE_URL = str(_OLLAMA_PROVIDER["default_base_url"]).rstrip("/")
DEFAULT_DETECT_TIMEOUT_SECONDS = 0.35
MAX_DETECT_RESPONSE_BYTES = 256 * 1024
MAX_SUGGESTED_MODELS = 8

Requester = Callable[..., Any]


@dataclass(frozen=True)
class LocalRuntimeDetectResult:
    """Immutable snapshot of one local-runtime detect attempt."""

    available: bool
    backend: Optional[str] = None
    base_url: Optional[str] = None
    models: List[str] = field(default_factory=list)
    suggested_profile: Dict[str, str] = field(default_factory=dict)
    reason: str = "not_probed"
    detect_enabled: bool = True

    def to_public_dict(self) -> Dict[str, Any]:
        """Project a JSON-serializable, non-secret detect payload."""
        return {
            "available": bool(self.available),
            "backend": self.backend,
            "base_url": self.base_url,
            "models": list(self.models),
            "suggested_profile": dict(self.suggested_profile),
            "reason": self.reason,
            "detect_enabled": bool(self.detect_enabled),
        }


def _parse_timeout_seconds(raw: Any, *, default: float = DEFAULT_DETECT_TIMEOUT_SECONDS) -> float:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    # Keep probes fast; clamp so misconfiguration cannot stall setup/startup.
    return max(0.05, min(value, 2.0))


def parse_local_runtime_auto_detect_enabled(raw: Any, *, default: bool = True) -> bool:
    """Parse LOCAL_RUNTIME_AUTO_DETECT; empty/missing keeps the beginner default (on)."""
    if raw is None:
        return default
    text = str(raw).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _candidate_base_urls(effective_map: Optional[Mapping[str, str]] = None) -> List[str]:
    """Build ordered loopback-only probe targets from config hints + default."""
    candidates: List[str] = []
    seen: set[str] = set()

    def _add(raw: Any) -> None:
        text = str(raw or "").strip().rstrip("/")
        if not text or text in seen:
            return
        seen.add(text)
        candidates.append(text)

    if effective_map:
        _add(effective_map.get("LLM_OLLAMA_BASE_URL"))
        _add(effective_map.get("OLLAMA_API_BASE"))
    _add(DEFAULT_OLLAMA_LOOPBACK_BASE_URL)
    return candidates


def _is_loopback_http_base_url(raw_url: str) -> bool:
    """Return True only for plain http(s) loopback roots without userinfo/query."""
    candidate = str(raw_url or "").strip()
    if not candidate or any(ch.isspace() or ch == "\\" or ord(ch) < 32 for ch in candidate):
        return False
    try:
        parsed = urlsplit(candidate)
    except ValueError:
        return False
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        return False
    path = (parsed.path or "").rstrip("/")
    if path and path != "/v1":
        return False
    return is_local_only_bind(parsed.hostname)


def _normalize_loopback_native_base_url(raw_url: str) -> Optional[str]:
    """Normalize a loopback Ollama root (strip trailing /v1) or return None."""
    if not _is_loopback_http_base_url(raw_url):
        return None
    parsed = urlsplit(str(raw_url).strip())
    path = (parsed.path or "").rstrip("/")
    if path == "/v1":
        path = ""
    hostname = (parsed.hostname or "").lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    port = parsed.port
    scheme = parsed.scheme.lower()
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    netloc = f"{hostname}:{port}" if port is not None else hostname
    return f"{scheme}://{netloc}{path}".rstrip("/")


def _extract_model_names(payload: Any) -> List[str]:
    """Extract Ollama model names from a /api/tags JSON body."""
    if not isinstance(payload, Mapping):
        return []
    models_raw = payload.get("models")
    if not isinstance(models_raw, list):
        return []
    names: List[str] = []
    seen: set[str] = set()
    for item in models_raw:
        if not isinstance(item, Mapping):
            continue
        name = str(item.get("name") or item.get("model") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
        if len(names) >= MAX_SUGGESTED_MODELS:
            break
    return names


def _build_suggested_profile(*, base_url: str, models: Sequence[str]) -> Dict[str, str]:
    """Non-secret profile fields for a local-zero-cost first-run path."""
    profile: Dict[str, str] = {
        "LLM_CHANNELS": "ollama",
        "LLM_OLLAMA_PROVIDER": "ollama",
        "LLM_OLLAMA_PROTOCOL": "ollama",
        "LLM_OLLAMA_BASE_URL": base_url,
        "LLM_OLLAMA_ENABLED": "true",
        "GENERATION_BACKEND": "litellm",
    }
    if models:
        primary = models[0]
        profile["LLM_OLLAMA_MODELS"] = ",".join(models)
        profile["LITELLM_MODEL"] = (
            primary if primary.startswith("ollama/") else f"ollama/{primary}"
        )
    return profile


def _default_requester(
    method: str,
    url: str,
    *,
    timeout: float,
    **_kwargs: Any,
) -> requests.Response:
    session = requests.Session()
    session.trust_env = False
    try:
        return session.request(
            method,
            url,
            timeout=timeout,
            allow_redirects=False,
            stream=True,
            headers={"Accept": "application/json"},
        )
    finally:
        session.close()


def _read_bounded_json(response: requests.Response, *, max_bytes: int) -> Any:
    chunks: List[bytes] = []
    total = 0
    for chunk in response.iter_content(chunk_size=4096):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_bytes:
            raise ValueError("local_runtime_detect_response_too_large")
        chunks.append(chunk)
    raw = b"".join(chunks)
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def detect_local_runtime(
    *,
    enabled: bool = True,
    timeout_seconds: float = DEFAULT_DETECT_TIMEOUT_SECONDS,
    effective_map: Optional[Mapping[str, str]] = None,
    requester: Optional[Requester] = None,
) -> LocalRuntimeDetectResult:
    """Probe loopback Ollama quickly; failures never raise to callers.

    Args:
        enabled: When False, skip probes and return a disabled snapshot.
        timeout_seconds: Per-request timeout (clamped to a tight band).
        effective_map: Optional config map used only for loopback base-url hints.
        requester: Optional injectable HTTP callable for deterministic tests.
    """
    if not enabled:
        return LocalRuntimeDetectResult(
            available=False,
            reason="detect_disabled",
            detect_enabled=False,
        )

    timeout = _parse_timeout_seconds(timeout_seconds)
    http = requester or _default_requester
    last_reason = "unreachable"

    for raw_url in _candidate_base_urls(effective_map):
        base_url = _normalize_loopback_native_base_url(raw_url)
        if base_url is None:
            last_reason = "non_loopback_skipped"
            logger.debug(
                "Local runtime detect skipped non-loopback candidate url_host_redacted=1"
            )
            continue

        tags_url = f"{base_url}/api/tags"
        response: Optional[requests.Response] = None
        try:
            response = http("GET", tags_url, timeout=timeout)
            status = int(getattr(response, "status_code", 0) or 0)
            if status != 200:
                last_reason = f"http_{status}" if status else "http_error"
                continue
            payload = _read_bounded_json(response, max_bytes=MAX_DETECT_RESPONSE_BYTES)
            models = _extract_model_names(payload)
            return LocalRuntimeDetectResult(
                available=True,
                backend="ollama",
                base_url=base_url,
                models=models,
                suggested_profile=_build_suggested_profile(base_url=base_url, models=models),
                reason="ollama_reachable",
                detect_enabled=True,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - detect is log-only and must never block setup/startup
            last_reason = "probe_failed"
            log_safe_exception(
                logger,
                "Local runtime detect probe failed",
                exc,
                error_code="local_runtime_detect_probe_failed",
                level=logging.DEBUG,
                context={"backend": "ollama"},
            )
        finally:
            if response is not None:
                try:
                    response.close()
                except Exception:  # broad-exception: cleanup - best-effort response close after probe
                    pass

    return LocalRuntimeDetectResult(
        available=False,
        reason=last_reason,
        detect_enabled=True,
    )


def detect_local_runtime_from_config_map(
    effective_map: Optional[Mapping[str, str]] = None,
    *,
    requester: Optional[Requester] = None,
) -> LocalRuntimeDetectResult:
    """Convenience entry that honors LOCAL_RUNTIME_AUTO_DETECT* config keys."""
    values = effective_map or {}
    enabled = parse_local_runtime_auto_detect_enabled(
        values.get("LOCAL_RUNTIME_AUTO_DETECT"),
        default=True,
    )
    timeout_raw = values.get("LOCAL_RUNTIME_DETECT_TIMEOUT_SECONDS")
    timeout = _parse_timeout_seconds(
        timeout_raw if timeout_raw not in (None, "") else DEFAULT_DETECT_TIMEOUT_SECONDS
    )
    return detect_local_runtime(
        enabled=enabled,
        timeout_seconds=timeout,
        effective_map=values,
        requester=requester,
    )
