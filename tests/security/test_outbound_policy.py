"""Deterministic security contracts for outbound HTTP targets."""

from __future__ import annotations

import logging
import socket
import threading
from unittest.mock import Mock, patch
from urllib.parse import urlsplit

import pytest
import requests

from src.security import outbound_policy
from src.security.outbound_policy import (
    OutboundPolicyError,
    guard_outbound_urls,
    safe_get,
    safe_post,
    validate_outbound_url,
)
from src.notification_sender.custom_webhook_sender import CustomWebhookSender
from src.patches.eastmoney_patch import _is_eastmoney_request_url


PUBLIC_ADDRINFO = [
    (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))
]
PRIVATE_ADDRINFO = [
    (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 80))
]


def _response(status_code: int = 200, *, location: str = "", url: str = "https://public.example/") -> Mock:
    response = Mock()
    response.status_code = status_code
    response.url = url
    response.headers = {"Location": location} if location else {}
    return response


@pytest.mark.parametrize(
    "url",
    [
        "ftp://example.com/file",
        "file:///etc/passwd",
        "https://user:secret@example.com/path",
        "https://example.com\\@127.0.0.1/",
        "https://public.example%2eattacker.example/path",
        "https://example.com/path\nHost: localhost",
        "https:///missing-host",
    ],
)
def test_rejects_non_http_ambiguous_and_credential_urls(url: str) -> None:
    with pytest.raises(OutboundPolicyError):
        validate_outbound_url(url, resolve_dns=False)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/admin",
        "http://127.1/admin",
        "http://2130706433/admin",
        "http://0177.0.0.1/admin",
        "http://0x7f000001/admin",
        "http://10.0.0.1/admin",
        "http://172.16.0.1/admin",
        "http://192.168.1.1/admin",
        "http://[::1]/admin",
        "http://[::ffff:127.0.0.1]/admin",
        "http://169.254.169.254/latest/meta-data/",
        "http://100.100.100.200/latest/meta-data/",
        "http://[fd00:ec2::254]/latest/meta-data/",
    ],
)
def test_rejects_private_metadata_and_ip_obfuscation(url: str) -> None:
    with pytest.raises(OutboundPolicyError):
        validate_outbound_url(url, resolve_dns=False)


@pytest.mark.parametrize(
    "hostname",
    [
        "localhost",
        "service.localhost",
        "printer.local",
        "metadata.google.internal",
        "instance-data.ec2.internal",
    ],
)
def test_rejects_local_and_metadata_hostnames_without_dns(hostname: str) -> None:
    with pytest.raises(OutboundPolicyError):
        validate_outbound_url(f"http://{hostname}/", resolve_dns=False)


def test_rejects_any_private_answer_from_mixed_dns_results() -> None:
    answers = PUBLIC_ADDRINFO + [
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.8", 443))
    ]
    with patch("src.security.outbound_policy.socket.getaddrinfo", return_value=answers):
        with pytest.raises(OutboundPolicyError, match="private_dns_address"):
            validate_outbound_url("https://mixed.example/path")


def test_dns_failure_is_fail_closed() -> None:
    with patch(
        "src.security.outbound_policy.socket.getaddrinfo",
        side_effect=socket.gaierror("not found"),
    ):
        with pytest.raises(OutboundPolicyError, match="dns_resolution_failed"):
            validate_outbound_url("https://missing.example/path")


def test_actual_resolution_is_checked_against_rebinding() -> None:
    answers = iter((PUBLIC_ADDRINFO, PRIVATE_ADDRINFO))

    def resolver(*_args, **_kwargs):
        return next(answers)

    def connect_twice(url: str, **_kwargs):
        host = urlsplit(url).hostname
        outbound_policy.socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        outbound_policy.socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        raise AssertionError("a private rebound address must not be connected")

    with (
        patch("src.security.outbound_policy.socket.getaddrinfo", side_effect=resolver),
        patch("src.security.outbound_policy.requests.get", side_effect=connect_twice),
    ):
        with pytest.raises(OutboundPolicyError, match="private_dns_address"):
            safe_get("https://rebind.example/data")


def test_sdk_guard_rejects_private_resolution_and_unexpected_proxy_host() -> None:
    with patch(
        "src.security.outbound_policy.socket.getaddrinfo",
        return_value=PRIVATE_ADDRINFO,
    ) as resolver:
        with guard_outbound_urls(("https://model.example/v1",), strict_dns=True):
            with pytest.raises(OutboundPolicyError, match="private_dns_address"):
                outbound_policy.socket.getaddrinfo("model.example", 443)
            with pytest.raises(OutboundPolicyError, match="unexpected_dns_target"):
                outbound_policy.socket.getaddrinfo("proxy.example", 8080)
    resolver.assert_called_once()


def test_sdk_guard_matches_allowlist_by_host_and_port() -> None:
    urls = (
        "https://private.example:8443/v1",
        "https://private.example:9443/v1",
    )
    with patch(
        "src.security.outbound_policy.socket.getaddrinfo",
        return_value=PRIVATE_ADDRINFO,
    ):
        with guard_outbound_urls(
            urls,
            allowlist=("private.example:8443",),
            strict_dns=True,
        ):
            outbound_policy.socket.getaddrinfo("private.example", 8443)
            with pytest.raises(OutboundPolicyError, match="private_dns_address"):
                outbound_policy.socket.getaddrinfo("private.example", 9443)


def test_dns_guards_do_not_serialize_independent_threads() -> None:
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()
    errors = []

    def hold_first_guard() -> None:
        try:
            with guard_outbound_urls(("https://first.example/v1",)):
                first_entered.set()
                if not release_first.wait(timeout=5):
                    errors.append("first guard timed out")
        except Exception as exc:  # broad-exception: fallback_recorded - Thread failures are asserted by the parent.
            errors.append(str(exc))

    def enter_second_guard() -> None:
        try:
            if not first_entered.wait(timeout=5):
                errors.append("first guard did not start")
                return
            with guard_outbound_urls(("https://second.example/v1",)):
                second_entered.set()
        except Exception as exc:  # broad-exception: fallback_recorded - Thread failures are asserted by the parent.
            errors.append(str(exc))

    first = threading.Thread(target=hold_first_guard)
    second = threading.Thread(target=enter_second_guard)
    first.start()
    second.start()
    try:
        assert second_entered.wait(timeout=2)
    finally:
        release_first.set()
        first.join(timeout=5)
        second.join(timeout=5)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []


def test_strict_guard_does_not_apply_to_unrelated_threads() -> None:
    result = []

    def resolve_unrelated_host() -> None:
        result.extend(outbound_policy.socket.getaddrinfo("unrelated.example", 443))

    with patch(
        "src.security.outbound_policy.socket.getaddrinfo",
        return_value=PUBLIC_ADDRINFO,
    ) as resolver:
        with guard_outbound_urls(("https://model.example/v1",), strict_dns=True):
            thread = threading.Thread(target=resolve_unrelated_host)
            thread.start()
            thread.join(timeout=5)

    assert not thread.is_alive()
    assert result == PUBLIC_ADDRINFO
    resolver.assert_called_once_with("unrelated.example", 443)


def test_redirect_to_loopback_is_rejected_before_second_request() -> None:
    first = _response(
        302,
        location="http://2130706433/admin",
        url="https://public.example/start",
    )
    with patch("src.security.outbound_policy.requests.get", return_value=first) as request_get:
        with pytest.raises(OutboundPolicyError, match="private_ip_blocked"):
            safe_get("https://public.example/start")
    assert request_get.call_count == 1
    first.close.assert_called_once()


def test_redirect_to_private_dns_target_cannot_reach_local_service() -> None:
    connected_hosts = []

    def resolver(host: str, *_args, **_kwargs):
        return PRIVATE_ADDRINFO if host == "internal.example" else PUBLIC_ADDRINFO

    def request_get(url: str, **_kwargs):
        host = urlsplit(url).hostname
        outbound_policy.socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        connected_hosts.append(host)
        if host == "public.example":
            return _response(302, location="https://internal.example/admin", url=url)
        raise AssertionError("the private target must be rejected before connection")

    with (
        patch("src.security.outbound_policy.socket.getaddrinfo", side_effect=resolver),
        patch("src.security.outbound_policy.requests.get", side_effect=request_get),
    ):
        with pytest.raises(OutboundPolicyError, match="private_dns_address"):
            safe_get("https://public.example/start")
    assert connected_hosts == ["public.example"]


def test_cross_origin_redirect_removes_request_credentials() -> None:
    first = _response(302, location="https://other.example/next")
    second = _response(200, url="https://other.example/next")
    with patch(
        "src.security.outbound_policy.requests.post",
        side_effect=[first],
    ) as request_post, patch(
        "src.security.outbound_policy.requests.get",
        return_value=second,
    ) as request_get:
        result = safe_post(
            "https://public.example/start",
            headers={
                "Authorization": "Bearer secret",
                "Cookie": "sid=secret",
                "X-API-Key": "provider-secret",
                "api-key": "azure-secret",
                "OpenAI-Api-Key": "openai-secret",
                "X-Auth-Token": "auth-secret",
                "X-Access-Token": "access-secret",
                "X-Test": "ok",
            },
            auth=("user", "secret"),
            json={"value": 1},
        )

    assert result is second
    assert request_post.call_count == 1
    redirected_kwargs = request_get.call_args.kwargs
    assert redirected_kwargs["headers"] == {"X-Test": "ok"}
    assert "auth" not in redirected_kwargs
    assert "json" not in redirected_kwargs


def test_requests_disable_environment_proxies_and_library_redirects() -> None:
    response = _response(200)
    with patch("src.security.outbound_policy.requests.get", return_value=response) as request_get:
        assert safe_get("https://public.example/data") is response
    assert request_get.call_args.kwargs["allow_redirects"] is False
    assert request_get.call_args.kwargs["proxies"] == {"http": "", "https": "", "all": ""}
    assert request_get.call_args.kwargs["stream"] is True
    assert request_get.call_args.kwargs["timeout"] == 15.0


def test_allowlist_permits_exact_private_self_host_but_not_metadata(monkeypatch) -> None:
    monkeypatch.setenv("OUTBOUND_HTTP_ALLOWLIST", "localhost:8080,private.example")
    validate_outbound_url("http://localhost:8080/health", resolve_dns=False)
    with patch("src.security.outbound_policy.socket.getaddrinfo", return_value=[
        (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("10.0.0.9", 8080))
    ]):
        validate_outbound_url("http://private.example:8080/health")

    with pytest.raises(OutboundPolicyError):
        validate_outbound_url("http://localhost:9090/health", resolve_dns=False)
    monkeypatch.setenv("OUTBOUND_HTTP_ALLOWLIST", "169.254.169.254,metadata.google.internal")
    with pytest.raises(OutboundPolicyError):
        validate_outbound_url("http://169.254.169.254/latest/meta-data/", resolve_dns=False)
    with pytest.raises(OutboundPolicyError):
        validate_outbound_url("http://metadata.google.internal/", resolve_dns=False)


def test_allowlist_port_matches_the_url_effective_default_port(monkeypatch) -> None:
    monkeypatch.setenv("OUTBOUND_HTTP_ALLOWLIST", "localhost:80")
    validate_outbound_url("http://localhost/health", resolve_dns=False)
    with pytest.raises(OutboundPolicyError, match="local_host_blocked"):
        validate_outbound_url("https://localhost/health", resolve_dns=False)

    monkeypatch.setenv("OUTBOUND_HTTP_ALLOWLIST", "localhost:443")
    validate_outbound_url("https://localhost/health", resolve_dns=False)


def test_invalid_allowlist_entries_cannot_broaden_to_a_host_only_match(monkeypatch) -> None:
    monkeypatch.setenv(
        "OUTBOUND_HTTP_ALLOWLIST",
        "localhost:,localhost%2eattacker.example,localhost\uff052eattacker.example,local host",
    )
    with pytest.raises(OutboundPolicyError, match="local_host_blocked"):
        validate_outbound_url("http://localhost:8080/health", resolve_dns=False)


def test_rejection_log_does_not_include_url_credentials_or_query(caplog) -> None:
    secret = "OUTBOUND_SECRET_CANARY"
    caplog.set_level(logging.WARNING, logger="src.security.outbound_policy")
    with pytest.raises(OutboundPolicyError):
        validate_outbound_url(
            f"https://user:{secret}@example.com/path?api_key={secret}",
            resolve_dns=False,
        )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert "event=outbound_request_rejected" in rendered
    assert "correlation_id=" in rendered
    assert "reason=credentials_not_allowed" in rendered
    assert secret not in rendered
    assert "example.com" not in rendered
    assert "api_key" not in rendered


def test_real_response_body_is_bounded_without_logging_content() -> None:
    response = requests.Response()
    response.status_code = 200
    response.headers = {}
    response.raw = Mock()
    response.raw.stream.return_value = [b"1234", b"5678"]

    with patch("src.security.outbound_policy.requests.get", return_value=response):
        with pytest.raises(OutboundPolicyError, match="response_too_large"):
            safe_get("https://public.example/data", max_response_bytes=7)


def test_custom_webhook_cannot_reach_loopback_service() -> None:
    config = Mock(
        custom_webhook_urls=["http://127.0.0.1:9000/hook"],
        custom_webhook_bearer_token=None,
        custom_webhook_body_template=None,
        webhook_verify_ssl=True,
    )
    sender = CustomWebhookSender(config)

    with patch("src.security.outbound_policy.requests.post") as request_post:
        assert sender.send_to_custom("test") is False
    request_post.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "https://fund.eastmoney.com/data",
        "https://api.push2.eastmoney.com/data",
        "https://push2his.eastmoney.com./data",
    ],
)
def test_eastmoney_patch_matches_only_owned_hosts(url: str) -> None:
    assert _is_eastmoney_request_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://fund.eastmoney.com.attacker.example/data",
        "https://attacker.example/?next=push2.eastmoney.com",
        "https://fund.eastmoney.com@attacker.example/data",
        "https://attacker.example/fund.eastmoney.com/data",
    ],
)
def test_eastmoney_patch_rejects_domain_substring_confusion(url: str) -> None:
    assert _is_eastmoney_request_url(url) is False
