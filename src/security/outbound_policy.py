"""Fail-closed policy for user-influenced outbound HTTP requests."""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import threading
import unicodedata
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Dict, Iterable, Iterator, List, Mapping, Optional, Tuple
from urllib.parse import urljoin, urlsplit

import requests

from src.utils.sanitize import sanitize_diagnostic_text

logger = logging.getLogger(__name__)

OUTBOUND_HTTP_ALLOWLIST_ENV = "OUTBOUND_HTTP_ALLOWLIST"
DEFAULT_OUTBOUND_TIMEOUT_SECONDS = 15.0
DEFAULT_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_ALLOWED_SCHEMES = frozenset({"http", "https"})
_REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})
_METADATA_HOSTS = frozenset(
    {
        "instance-data.ec2.internal",
        "metadata.azure.internal",
        "metadata.google.internal",
    }
)
_METADATA_IPS = frozenset(
    {
        ipaddress.ip_address("100.100.100.200"),
        ipaddress.ip_address("169.254.169.254"),
        ipaddress.ip_address("fd00:ec2::254"),
    }
)
_NO_PROXIES = {"http": "", "https": "", "all": ""}
_CROSS_ORIGIN_CREDENTIAL_HEADERS = frozenset(
    {
        "api-key",
        "authorization",
        "cookie",
        "openai-api-key",
        "proxy-authorization",
        "x-access-token",
        "x-api-key",
        "x-auth-token",
    }
)
_DNS_GUARD_LOCK = threading.RLock()
_DNS_GUARD_USERS = 0
_DNS_BASE_GETADDRINFO: Any = socket.getaddrinfo
_DNS_INSTALLED_GETADDRINFO: Any = None


class OutboundPolicyError(requests.RequestException):
    """Raised when an outbound target violates the HTTP safety policy."""

    def __init__(self, reason: str, correlation_id: str):
        self.reason = reason
        self.correlation_id = correlation_id
        super().__init__(f"Outbound request rejected by security policy ({reason})")


@dataclass(frozen=True)
class _AllowlistEntry:
    hostname: str
    port: Optional[int]


@dataclass(frozen=True)
class OutboundTarget:
    """Parsed target metadata that is safe to retain inside the request boundary."""

    scheme: str
    hostname: str
    port: Optional[int]
    allowlisted: bool
    literal_ip: Optional[ipaddress._BaseAddress]

    @property
    def host_type(self) -> str:
        return "ip" if self.literal_ip is not None else "hostname"


@dataclass(frozen=True)
class _DNSGuardContext:
    targets: Tuple[OutboundTarget, ...]
    strict: bool


_DNS_GUARD_CONTEXTS: ContextVar[Tuple[_DNSGuardContext, ...]] = ContextVar(
    "outbound_dns_guard_contexts",
    default=(),
)


def _reject(
    reason: str,
    *,
    scheme: str = "unknown",
    host_type: str = "unknown",
    allowlisted: bool = False,
) -> None:
    safe_scheme = sanitize_diagnostic_text(
        scheme if scheme in _ALLOWED_SCHEMES else "other",
        max_length=16,
    )
    safe_host_type = sanitize_diagnostic_text(
        host_type if host_type in {"hostname", "ip"} else "unknown",
        max_length=16,
    )
    safe_allowlisted = sanitize_diagnostic_text(
        allowlisted,
        max_length=8,
    )
    correlation_id = uuid.uuid4().hex[:16]
    safe_reason = sanitize_diagnostic_text(reason, max_length=64)
    logger.warning(
        "Outbound request rejected event=outbound_request_rejected correlation_id=%s reason=%s "
        "scheme=%s host_type=%s allowlisted=%s",
        correlation_id,
        safe_reason,
        safe_scheme,
        safe_host_type,
        safe_allowlisted,
    )
    raise OutboundPolicyError(reason, correlation_id)


def _reject_target(reason: str, target: OutboundTarget) -> None:
    _reject(
        reason,
        scheme=target.scheme,
        host_type=target.host_type,
        allowlisted=target.allowlisted,
    )


def _normalize_hostname(value: Any) -> str:
    if isinstance(value, bytes):
        value = value.decode("ascii", errors="ignore")
    candidate = unicodedata.normalize("NFKC", str(value or "")).strip().lower().rstrip(".")
    if not candidate:
        return ""
    if "%" in candidate:
        candidate = candidate.split("%", 1)[0]
    if ":" in candidate:
        return candidate
    try:
        return candidate.encode("idna").decode("ascii").lower().rstrip(".")
    except UnicodeError:
        return ""


def _literal_ip(hostname: str) -> Optional[ipaddress._BaseAddress]:
    try:
        return ipaddress.ip_address(hostname)
    except ValueError:
        pass

    if ":" in hostname:
        return None
    try:
        return ipaddress.ip_address(socket.inet_ntoa(socket.inet_aton(hostname)))
    except (OSError, ValueError):
        return None


def _normalize_allowlist_entry(raw_entry: str) -> Optional[_AllowlistEntry]:
    entry = unicodedata.normalize("NFKC", str(raw_entry or "")).strip()
    if (
        not entry
        or "://" in entry
        or any(
            char in "/?#%@\\" or char.isspace() or ord(char) < 32 or ord(char) == 127
            for char in entry
        )
    ):
        return None

    try:
        direct_ip = ipaddress.ip_address(entry)
    except ValueError:
        direct_ip = None
    if direct_ip is not None:
        return _AllowlistEntry(hostname=str(direct_ip), port=None)
    if entry.endswith(":"):
        return None

    try:
        parsed = urlsplit(f"//{entry}")
        hostname = _normalize_hostname(parsed.hostname)
        port = parsed.port
    except ValueError:
        return None
    if not hostname:
        return None
    return _AllowlistEntry(hostname=hostname, port=port)


def _allowlist_entries(allowlist: Optional[Iterable[str]] = None) -> Tuple[_AllowlistEntry, ...]:
    raw_entries: Iterable[str]
    if allowlist is None:
        raw_entries = os.getenv(OUTBOUND_HTTP_ALLOWLIST_ENV, "").split(",")
    else:
        raw_entries = allowlist
    entries = []
    for raw_entry in raw_entries:
        normalized = _normalize_allowlist_entry(raw_entry)
        if normalized is not None:
            entries.append(normalized)
    return tuple(entries)


def _is_allowlisted(
    hostname: str,
    scheme: str,
    port: Optional[int],
    entries: Iterable[_AllowlistEntry],
) -> bool:
    effective_port = port if port is not None else 443 if scheme == "https" else 80
    return any(
        entry.hostname == hostname
        and (entry.port is None or entry.port == effective_port)
        for entry in entries
    )


def _is_metadata_ip(address: ipaddress._BaseAddress) -> bool:
    candidates = [address]
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        candidates.append(mapped)
    return any(candidate in _METADATA_IPS for candidate in candidates)


def _is_hard_blocked_ip(address: ipaddress._BaseAddress) -> bool:
    candidates = [address]
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        candidates.append(mapped)
    return any(
        _is_metadata_ip(candidate)
        or candidate.is_link_local
        or candidate.is_multicast
        or candidate.is_reserved
        or candidate.is_unspecified
        for candidate in candidates
    )


def _is_private_ip(address: ipaddress._BaseAddress) -> bool:
    candidates = [address]
    mapped = getattr(address, "ipv4_mapped", None)
    if mapped is not None:
        candidates.append(mapped)
    return any(
        candidate.is_loopback or candidate.is_private or not candidate.is_global
        for candidate in candidates
    )


def _inspect_target(
    raw_url: str,
    *,
    allowlist: Optional[Iterable[str]] = None,
) -> OutboundTarget:
    value = str(raw_url or "")
    if not value or any(
        char == "\\" or char.isspace() or ord(char) < 32 or ord(char) == 127
        for char in value
    ):
        _reject("invalid_url")

    try:
        parsed = urlsplit(value)
        scheme = parsed.scheme.lower()
        parsed_hostname = str(parsed.hostname or "")
        if "%" in parsed_hostname:
            _reject("invalid_url", scheme=scheme)
        hostname = _normalize_hostname(parsed_hostname)
        port = parsed.port
    except ValueError:
        _reject("invalid_url")

    if scheme not in _ALLOWED_SCHEMES:
        _reject("scheme_not_allowed", scheme=scheme)
    if not parsed.netloc or not hostname:
        _reject("host_missing", scheme=scheme)
    if parsed.username is not None or parsed.password is not None or "@" in parsed.netloc:
        _reject("credentials_not_allowed", scheme=scheme)

    literal_ip = _literal_ip(hostname)
    normalized_host = str(literal_ip) if literal_ip is not None else hostname
    entries = _allowlist_entries(allowlist)
    target = OutboundTarget(
        scheme=scheme,
        hostname=normalized_host,
        port=port,
        allowlisted=_is_allowlisted(normalized_host, scheme, port, entries),
        literal_ip=literal_ip,
    )

    if hostname in _METADATA_HOSTS or hostname.endswith(".metadata.google.internal"):
        _reject_target("metadata_host_blocked", target)
    if hostname == "localhost" or hostname.endswith(".localhost") or hostname.endswith(".local"):
        if not target.allowlisted:
            _reject_target("local_host_blocked", target)
    if literal_ip is not None:
        if _is_hard_blocked_ip(literal_ip):
            _reject_target("restricted_ip_blocked", target)
        if _is_private_ip(literal_ip) and not target.allowlisted:
            _reject_target("private_ip_blocked", target)
    return target


def _validate_addrinfos(addr_infos: Iterable[Any], target: OutboundTarget) -> None:
    usable_addresses: List[ipaddress._BaseAddress] = []
    for info in addr_infos or []:
        try:
            raw_address = str(info[4][0]).split("%", 1)[0]
            address = ipaddress.ip_address(raw_address)
        except (IndexError, TypeError, ValueError):
            continue
        usable_addresses.append(address)
        if _is_hard_blocked_ip(address):
            _reject_target("restricted_dns_address", target)
        if _is_private_ip(address) and not target.allowlisted:
            _reject_target("private_dns_address", target)
    if not usable_addresses:
        _reject_target("dns_no_usable_address", target)


def validate_outbound_url(
    raw_url: str,
    *,
    allowlist: Optional[Iterable[str]] = None,
    resolve_dns: bool = True,
) -> OutboundTarget:
    """Validate an HTTP(S) URL and, by default, all current DNS answers."""

    target = _inspect_target(raw_url, allowlist=allowlist)
    if not resolve_dns or target.literal_ip is not None:
        return target
    try:
        addr_infos = socket.getaddrinfo(
            target.hostname,
            target.port,
            type=socket.SOCK_STREAM,
        )
    except OutboundPolicyError:
        raise
    except OSError:
        _reject_target("dns_resolution_failed", target)
    _validate_addrinfos(addr_infos, target)
    return target


def _effective_port(target: OutboundTarget) -> int:
    if target.port is not None:
        return target.port
    return 443 if target.scheme == "https" else 80


def _normalized_dns_port(port: Any) -> Optional[int]:
    try:
        return int(port)
    except (TypeError, ValueError):
        return {"http": 80, "https": 443}.get(str(port or "").strip().lower())


def _matching_dns_target(
    host: Any,
    port: Any,
    context: _DNSGuardContext,
) -> Optional[OutboundTarget]:
    normalized_host = _normalize_hostname(host)
    literal = _literal_ip(normalized_host)
    if literal is not None:
        normalized_host = str(literal)
    host_targets = tuple(
        target for target in context.targets if target.hostname == normalized_host
    )
    dns_port = _normalized_dns_port(port)
    if dns_port is None:
        return host_targets[0] if len(host_targets) == 1 else None
    return next(
        (target for target in host_targets if _effective_port(target) == dns_port),
        None,
    )


def _resolve_with_dns_guard(
    resolver: Any,
    host: Any,
    port: Any,
    *args: Any,
    **kwargs: Any,
) -> Any:
    contexts = _DNS_GUARD_CONTEXTS.get()
    context = contexts[-1] if contexts else None
    matching_target = (
        _matching_dns_target(host, port, context)
        if context is not None
        else None
    )
    if context is not None and matching_target is None and context.strict:
        _reject("unexpected_dns_target")

    try:
        addr_infos = resolver(host, port, *args, **kwargs)
    except OutboundPolicyError:
        raise
    except OSError:
        if matching_target is not None:
            _reject_target("dns_resolution_failed", matching_target)
        raise
    if matching_target is not None:
        _validate_addrinfos(addr_infos, matching_target)
    return addr_infos


def _activate_dns_guard() -> None:
    global _DNS_BASE_GETADDRINFO, _DNS_GUARD_USERS, _DNS_INSTALLED_GETADDRINFO
    with _DNS_GUARD_LOCK:
        if _DNS_GUARD_USERS == 0:
            _DNS_BASE_GETADDRINFO = socket.getaddrinfo
            resolver = _DNS_BASE_GETADDRINFO

            def guarded_getaddrinfo(
                host: Any,
                port: Any,
                *args: Any,
                **kwargs: Any,
            ) -> Any:
                return _resolve_with_dns_guard(
                    resolver,
                    host,
                    port,
                    *args,
                    **kwargs,
                )

            _DNS_INSTALLED_GETADDRINFO = guarded_getaddrinfo
            socket.getaddrinfo = guarded_getaddrinfo
        _DNS_GUARD_USERS += 1


def _deactivate_dns_guard() -> None:
    global _DNS_GUARD_USERS, _DNS_INSTALLED_GETADDRINFO
    with _DNS_GUARD_LOCK:
        _DNS_GUARD_USERS -= 1
        if _DNS_GUARD_USERS == 0:
            if socket.getaddrinfo is _DNS_INSTALLED_GETADDRINFO:
                socket.getaddrinfo = _DNS_BASE_GETADDRINFO
            _DNS_INSTALLED_GETADDRINFO = None


@contextmanager
def _dns_guard(
    targets: Tuple[OutboundTarget, ...],
    *,
    strict: bool,
) -> Iterator[None]:
    context = _DNSGuardContext(targets=targets, strict=strict)
    token = _DNS_GUARD_CONTEXTS.set((*_DNS_GUARD_CONTEXTS.get(), context))
    try:
        _activate_dns_guard()
    except BaseException:  # broad-exception: cleanup - Restore context if guard installation cannot complete.
        _DNS_GUARD_CONTEXTS.reset(token)
        raise
    try:
        yield
    finally:
        _DNS_GUARD_CONTEXTS.reset(token)
        _deactivate_dns_guard()


@contextmanager
def guard_outbound_urls(
    raw_urls: Iterable[str],
    *,
    allowlist: Optional[Iterable[str]] = None,
    strict_dns: bool = True,
) -> Iterator[None]:
    """Guard DNS performed by an SDK that owns its HTTP transport."""

    targets = tuple(
        _inspect_target(raw_url, allowlist=allowlist)
        for raw_url in dict.fromkeys(str(value or "").strip() for value in raw_urls)
        if raw_url
    )
    if not targets:
        yield
        return

    with _dns_guard(targets, strict=strict_dns):
        yield


@contextmanager
def _guard_actual_dns(target: OutboundTarget) -> Iterator[None]:
    with _dns_guard((target,), strict=True):
        yield


def _origin(target: OutboundTarget) -> Tuple[str, str, int]:
    return target.scheme, target.hostname, _effective_port(target)


def _strip_cross_origin_credentials(kwargs: Dict[str, Any]) -> None:
    headers = dict(kwargs.get("headers") or {})
    for key in list(headers):
        if str(key).lower() in _CROSS_ORIGIN_CREDENTIAL_HEADERS:
            headers.pop(key, None)
    if headers or "headers" in kwargs:
        kwargs["headers"] = headers
    for key in ("auth", "cert", "cookies"):
        kwargs.pop(key, None)


def _redirect_request(
    method: str,
    kwargs: Mapping[str, Any],
    status_code: int,
    *,
    cross_origin: bool,
) -> Tuple[str, Dict[str, Any]]:
    next_method = method
    next_kwargs = dict(kwargs)
    if status_code == 303 and method != "HEAD":
        next_method = "GET"
    elif status_code == 302 and method != "HEAD":
        next_method = "GET"
    elif status_code == 301 and method == "POST":
        next_method = "GET"

    if next_method == "GET" and method != "GET":
        for key in ("data", "files", "json"):
            next_kwargs.pop(key, None)
        headers = dict(next_kwargs.get("headers") or {})
        for key in list(headers):
            if str(key).lower() in {"content-length", "content-type", "transfer-encoding"}:
                headers.pop(key, None)
        if headers or "headers" in next_kwargs:
            next_kwargs["headers"] = headers

    next_kwargs.pop("params", None)
    if cross_origin:
        _strip_cross_origin_credentials(next_kwargs)
    return next_method, next_kwargs


def _dispatch_request(
    method: str,
    url: str,
    kwargs: Dict[str, Any],
    transport: Any,
) -> requests.Response:
    request_transport = transport if transport is not None else requests
    request_callable = getattr(request_transport, method.lower(), None)
    if request_callable is None:
        return request_transport.request(method, url, **kwargs)
    return request_callable(url, **kwargs)


def _buffer_bounded_response(response: requests.Response, max_response_bytes: int) -> None:
    content_length = response.headers.get("Content-Length")
    if content_length:
        try:
            if int(content_length) > max_response_bytes:
                response.close()
                _reject("response_too_large")
        except ValueError:
            pass

    existing_content = getattr(response, "_content", False)
    if existing_content is not False:
        if len(existing_content or b"") > max_response_bytes:
            response.close()
            _reject("response_too_large")
        return
    if getattr(response, "raw", None) is None:
        # Synthetic responses used by callers and tests may not own a raw stream.
        response._content = b""
        response._content_consumed = True
        return

    chunks = []
    total = 0
    for chunk in response.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > max_response_bytes:
            response.close()
            _reject("response_too_large")
        chunks.append(chunk)
    response._content = b"".join(chunks)
    response._content_consumed = True


def safe_request(
    method: str,
    url: str,
    *,
    allow_redirects: bool = True,
    max_redirects: int = 5,
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    allowlist: Optional[Iterable[str]] = None,
    transport: Any = None,
    **kwargs: Any,
) -> requests.Response:
    """Issue a proxy-free request with DNS and per-redirect target checks."""

    current_method = str(method or "GET").upper()
    current_url = str(url or "")
    current_kwargs = dict(kwargs)
    current_kwargs.pop("allow_redirects", None)
    current_kwargs.setdefault("timeout", DEFAULT_OUTBOUND_TIMEOUT_SECONDS)
    current_kwargs["proxies"] = dict(_NO_PROXIES)
    redirects_followed = 0

    while True:
        target = _inspect_target(current_url, allowlist=allowlist)
        request_kwargs = dict(current_kwargs)
        caller_streams_response = bool(request_kwargs.get("stream", False))
        if not caller_streams_response:
            request_kwargs["stream"] = True
        request_kwargs["allow_redirects"] = False
        with _guard_actual_dns(target):
            response = _dispatch_request(
                current_method,
                current_url,
                request_kwargs,
                transport,
            )

        try:
            status_code = int(response.status_code)
        except (AttributeError, TypeError, ValueError):
            status_code = 0
        if not allow_redirects or status_code not in _REDIRECT_STATUS_CODES:
            if not caller_streams_response and isinstance(response, requests.Response):
                _buffer_bounded_response(response, max(1, int(max_response_bytes)))
            return response

        location = str(getattr(response, "headers", {}).get("Location") or "").strip()
        if not location:
            response.close()
            _reject_target("redirect_missing_location", target)
        if redirects_followed >= max(0, int(max_redirects)):
            response.close()
            _reject_target("redirect_limit_exceeded", target)

        response_url = str(getattr(response, "url", "") or current_url)
        next_url = urljoin(response_url, location)
        try:
            next_target = _inspect_target(next_url, allowlist=allowlist)
        except OutboundPolicyError:
            response.close()
            raise
        response.close()

        current_method, current_kwargs = _redirect_request(
            current_method,
            current_kwargs,
            status_code,
            cross_origin=_origin(target) != _origin(next_target),
        )
        current_url = next_url
        redirects_followed += 1


def safe_get(url: str, **kwargs: Any) -> requests.Response:
    return safe_request("GET", url, **kwargs)


def safe_post(url: str, **kwargs: Any) -> requests.Response:
    return safe_request("POST", url, **kwargs)


def safe_patch(url: str, **kwargs: Any) -> requests.Response:
    return safe_request("PATCH", url, **kwargs)
