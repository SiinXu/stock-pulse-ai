"""Llm Validation methods for the system-config facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.system_config_service import (
        ANSPIRE_LLM_MODEL_DEFAULT,
        Any,
        Config,
        Dict,
        HERMES_DEFAULT_BASE_URL,
        HERMES_DEFAULT_MODEL,
        HERMES_DEFAULT_PROTOCOL,
        List,
        ModelAssignmentValidator,
        Optional,
        SUPPORTED_LLM_CHANNEL_PROTOCOLS,
        Sequence,
        Set,
        SystemConfigService,
        Tuple,
        _LLMDiagnostic,
        build_connection_contract_values,
        build_hermes_redaction_values,
        canonicalize_llm_channel_protocol,
        get_connection_field_schema,
        get_unknown_connection_contract_fields,
        is_feishu_app_bot_env_configured,
        is_feishu_static_env_configured,
        is_reserved_hermes_name,
        llm_channel_map,
        parse_env_bool,
        parse_hermes_channel,
        re,
        requests,
        resolve_llm_channel_protocol,
        sanitize_diagnostic_text,
        strip_leading_think_wrapper,
        urlparse,
        urlunparse,
        validate_connection_contract_values,
    )


class _SystemConfigLLMValidationMethods:
    @staticmethod
    def _is_safe_base_url(value: str) -> bool:
        """Block link-local and cloud metadata addresses to prevent SSRF.

        Allows localhost / private-LAN addresses (e.g. Ollama on 192.168.x.x)
        but blocks 169.254.x.x (AWS/Azure/GCP/Alibaba instance-metadata service)
        and other known metadata hostnames.
        """
        import ipaddress

        try:
            parsed = urlparse(value)
            raw_host = parsed.hostname or ""
        except ValueError:
            return False
        if not raw_host:
            return True
        host = SystemConfigService._normalize_hostname_for_security(raw_host)
        if not host:
            return False
        # Known cloud metadata hostnames
        _BLOCKED_HOSTS = frozenset({
            "169.254.169.254",
            "metadata.google.internal",
            "100.100.100.200",
        })
        if host in _BLOCKED_HOSTS:
            return False
        if SystemConfigService._is_noncanonical_ipv4_numeric_host(host):
            return False
        # Numeric IPs: block link-local range (169.254.0.0/16), including IPv4-mapped IPv6.
        try:
            addr = ipaddress.ip_address(host)
            candidate_addrs = [addr]
            mapped_addr = getattr(addr, "ipv4_mapped", None)
            if mapped_addr is not None:
                candidate_addrs.append(mapped_addr)
            for candidate_addr in candidate_addrs:
                if str(candidate_addr) in _BLOCKED_HOSTS or candidate_addr.is_link_local:
                    return False
        except ValueError:
            pass  # hostname, not an IP — already checked against blocklist above
        return True

    @staticmethod
    def _build_llm_models_url(base_url: str, protocol: str = "openai") -> str:
        """Convert a Connection base URL into its model discovery endpoint."""
        if not SystemConfigService._is_valid_llm_base_url(base_url):
            raise ValueError("LLM channel base URL must be a valid absolute URL")
        if not SystemConfigService._is_safe_base_url(base_url):
            raise ValueError("LLM channel base URL points to a restricted address")

        parsed = urlparse(base_url)
        normalized = (parsed.path or "").rstrip("/")
        if str(protocol or "").strip().lower() == "ollama":
            if normalized.endswith("/api/tags"):
                models_path = normalized
            else:
                for suffix in (
                    "/v1/chat/completions",
                    "/v1/completions",
                    "/chat/completions",
                    "/completions",
                    "/v1",
                    "/api",
                ):
                    if normalized.endswith(suffix):
                        normalized = normalized[: -len(suffix)]
                        break
                models_path = f"{normalized}/api/tags" if normalized else "/api/tags"
        else:
            for suffix in ("/chat/completions", "/completions"):
                if normalized.endswith(suffix):
                    normalized = normalized[: -len(suffix)]
                    break
            if normalized.endswith("/models"):
                models_path = normalized or "/models"
            else:
                models_path = f"{normalized}/models" if normalized else "/models"
        models_url = urlunparse(parsed._replace(path=models_path, params="", query="", fragment=""))
        if not SystemConfigService._is_valid_llm_base_url(models_url):
            raise ValueError("LLM channel models URL must be a valid absolute URL")
        if not SystemConfigService._is_safe_base_url(models_url):
            raise ValueError("LLM channel models URL points to a restricted address")
        return models_url

    @staticmethod
    def _get_runtime_llm_temperature() -> float:
        """Return the current configured LLM temperature for ad-hoc channel tests."""
        config = Config._load_from_env()
        try:
            return float(getattr(config, "llm_temperature", 0.7))
        except (TypeError, ValueError):
            return 0.7

    @classmethod
    def _build_llm_channel_result(
        cls,
        *,
        success: bool,
        message: str,
        error: Optional[str],
        stage: Optional[str],
        error_code: Optional[str],
        retryable: Optional[bool],
        details: Optional[Dict[str, Any]] = None,
        resolved_protocol: Optional[str] = None,
        resolved_model: Optional[str] = None,
        models: Optional[List[str]] = None,
        latency_ms: Optional[int] = None,
        capability_results: Optional[Dict[str, Any]] = None,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "success": success,
            "message": cls._sanitize_llm_error_text(message, redaction_values=redaction_values),
            "error": cls._sanitize_llm_error_text(error, redaction_values=redaction_values) if error else None,
            "stage": stage,
            "error_code": error_code,
            "retryable": retryable,
            "details": cls._sanitize_llm_details(details, redaction_values=redaction_values),
            "resolved_protocol": cls._sanitize_llm_error_text(
                resolved_protocol,
                redaction_values=redaction_values,
            ) if resolved_protocol is not None else None,
            "latency_ms": latency_ms,
        }
        if resolved_model is not None or models is None:
            payload["resolved_model"] = cls._sanitize_llm_error_text(
                resolved_model,
                redaction_values=redaction_values,
            ) if resolved_model is not None else resolved_model
        if models is not None:
            payload["models"] = cls._sanitize_llm_value(models, redaction_values=redaction_values)
        if capability_results is not None:
            payload["capability_results"] = cls._sanitize_llm_value(capability_results, redaction_values=redaction_values)
        return payload

    @staticmethod
    def _merge_llm_diagnostic_details(
        base_details: Optional[Dict[str, Any]],
        diagnostic: _LLMDiagnostic,
    ) -> Dict[str, Any]:
        details: Dict[str, Any] = dict(base_details or {})
        if diagnostic.reason:
            details.setdefault("reason", diagnostic.reason)
        details.update(diagnostic.details)
        return details

    @staticmethod
    def _build_redaction_values(*values: Any) -> Set[str]:
        return build_hermes_redaction_values(*values)

    @staticmethod
    def _comma_flexible_secret_pattern(secret: str) -> Optional[re.Pattern[str]]:
        normalized = re.sub(r"(?i)^\s*authorization\s*[:=]\s*", "", str(secret or "").strip())
        normalized = re.sub(r"(?i)^\s*bearer\s+", "", normalized)
        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        if len(parts) <= 1:
            return None
        return re.compile(
            r"(?i)(?:authorization\s*[:=]\s*)?(?:bearer\s+)?"
            + r"\s*,\s*".join(re.escape(part) for part in parts)
        )

    @classmethod
    def _sanitize_llm_error_text(cls, text: Any, *, redaction_values: Optional[Set[str]] = None) -> str:
        if text is None:
            return ""
        sanitized = str(text).strip()
        if not sanitized:
            return ""
        for secret in sorted((redaction_values or set()), key=len, reverse=True):
            pattern = cls._comma_flexible_secret_pattern(secret)
            if pattern is not None:
                sanitized = pattern.sub("[REDACTED]", sanitized)
        for secret in sorted((redaction_values or set()), key=len, reverse=True):
            if secret:
                sanitized = sanitized.replace(secret, "[REDACTED]")

        patterns = [
            (r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?([^\s,;]+)", r"\1[REDACTED]"),
            (r"(?i)(api[_-]?key\s*[:=]\s*)([^\s,;]+)", r"\1[REDACTED]"),
            (r"(?i)(cookie\s*[:=]\s*)([^\s,;]+)", r"\1[REDACTED]"),
            (r"(?i)bearer\s+[a-z0-9._\-]+", "Bearer [REDACTED]"),
            (r"(?i)sk-[a-z0-9_\-]+", "[REDACTED]"),
        ]
        for pattern, replacement in patterns:
            sanitized = re.sub(pattern, replacement, sanitized)
        return sanitize_diagnostic_text(sanitized, max_length=300)

    @classmethod
    def _sanitize_llm_details(
        cls,
        details: Optional[Dict[str, Any]],
        *,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        if not details:
            return {}
        sanitized = cls._sanitize_llm_value(details, redaction_values=redaction_values)
        return sanitized if isinstance(sanitized, dict) else {}

    @classmethod
    def _sanitize_llm_value(cls, value: Any, *, redaction_values: Optional[Set[str]] = None) -> Any:
        if isinstance(value, str):
            return cls._sanitize_llm_error_text(value, redaction_values=redaction_values)
        if isinstance(value, dict):
            return {
                cls._sanitize_llm_error_text(key, redaction_values=redaction_values): cls._sanitize_llm_value(
                    item,
                    redaction_values=redaction_values,
                )
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                cls._sanitize_llm_value(item, redaction_values=redaction_values)
                for item in value
            ]
        if isinstance(value, tuple):
            return [
                cls._sanitize_llm_value(item, redaction_values=redaction_values)
                for item in value
            ]
        return value

    @staticmethod
    def _classify_llm_http_error(status_code: int, error_text: str) -> _LLMDiagnostic:
        lowered = (error_text or "").lower()
        if SystemConfigService._has_model_access_denied_signal(error_text or ""):
            return _LLMDiagnostic(
                "model_not_found",
                False,
                "Configured model is not available for this channel",
                "model_access_denied",
            )
        if "model" in lowered and any(token in lowered for token in ("not found", "does not exist", "unknown")):
            return _LLMDiagnostic(
                "model_not_found",
                False,
                "Configured model could not be found on this channel",
                "model_not_found",
            )
        if status_code == 402 or any(token in lowered for token in ("billing", "balance", "insufficient balance")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or billing limits",
                "insufficient_balance",
            )
        if any(token in lowered for token in ("quota", "insufficient_quota", "quota exceeded")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or rate limiting",
                "quota_exceeded",
            )
        if status_code == 429 or any(token in lowered for token in ("rate limit", "too many requests", "rpm", "tpm")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or rate limiting",
                "rate_limit",
            )
        if SystemConfigService._has_transport_blocked_signal(error_text or ""):
            return _LLMDiagnostic(
                "network_error",
                True,
                "LLM request failed before a valid response was returned",
                "network_error",
            )
        if SystemConfigService._has_request_blocked_signal(error_text or ""):
            return _LLMDiagnostic(
                "request_blocked",
                False,
                "LLM request was blocked by provider or gateway policy",
                "provider_blocked",
            )
        if status_code in {401, 403} or any(token in lowered for token in ("unauthorized", "forbidden", "invalid api key", "authentication")):
            return _LLMDiagnostic("auth", False, "LLM authentication failed", "api_key_rejected")
        if status_code == 404:
            return _LLMDiagnostic(
                "network_error",
                False,
                "LLM model discovery endpoint could not be found",
                "endpoint_not_found",
            )
        if any(token in lowered for token in ("timeout", "timed out")):
            return _LLMDiagnostic("timeout", True, "LLM request timed out", "timeout")
        return _LLMDiagnostic(
            "network_error",
            status_code >= 500,
            "LLM request failed before a valid response was returned",
            "http_error",
        )

    @staticmethod
    def _has_model_not_found_signal(text: str) -> bool:
        lowered = text.lower()

        model_candidates = [
            re.search(r"model\s+not\s+found\s*[:：]?\s*[`\"']?\s*([a-z0-9._/-]{2,})", lowered),
            re.search(r"model\s*[`\"']?\s*([a-z0-9._/-]{2,})\s*[`\"']?\s+does\s+not\s+exist", lowered),
            re.search(r"model\s+does\s+not\s+exist\s*[:：]?\s*[`\"']?\s*([a-z0-9._/-]{2,})", lowered),
            re.search(r"unknown\s+model\s*[:：]?\s*[`\"']?\s*([a-z0-9._/-]{2,})", lowered),
            re.search(r"no\s+such\s+model\s*[:：]?\s*[`\"']?\s*([a-z0-9._/-]{2,})", lowered),
        ]

        for match in model_candidates:
            if not match:
                continue
            model_id = match.group(1).strip()
            if model_id and not model_id.startswith("/") and "http" not in model_id:
                return True

        return False

    @staticmethod
    def _has_model_access_denied_signal(text: str) -> bool:
        lowered = text.lower()
        if "model" not in lowered:
            return False

        # Best-effort classifier for observed provider messages. Keep it gated by
        # an explicit "model" mention plus access/disabled/unavailable signals so
        # unrelated provider-specific failures continue to use the fallback path.
        access_denied_tokens = (
            "not authorized",
            "not allowed",
            "access denied",
            "permission denied",
            "model disabled",
            "model is disabled",
            "disabled model",
            "model has been disabled",
            "model not enabled",
            "model not available",
            "model is not available",
        )
        return any(token in lowered for token in access_denied_tokens)

    @staticmethod
    def _has_request_blocked_signal(text: str) -> bool:
        lowered = text.lower()
        if SystemConfigService._has_transport_blocked_signal(lowered):
            return False
        blocked_tokens = (
            "your request was blocked",
            "the request was blocked",
            "request blocked by policy",
            "blocked by policy",
            "blocked due to policy",
            "moderation_blocked",
            "policy_blocked",
            "请求被拦截",
        )
        return any(token in lowered for token in blocked_tokens)

    @staticmethod
    def _has_transport_blocked_signal(text: str) -> bool:
        lowered = text.lower()
        transport_tokens = (
            "connection blocked",
            "connection request was blocked",
            "network blocked",
            "blocked by network policy",
            "blocked by firewall",
            "firewall blocked",
        )
        return any(token in lowered for token in transport_tokens)

    @staticmethod
    def _has_provider_prefix_mismatch_signal(text: str) -> bool:
        lowered = text.lower()
        mismatch_tokens = (
            "provider prefix",
            "llm provider not provided",
            "invalid provider",
            "unknown provider",
            "custom_llm_provider",
            "not a valid llm provider",
        )
        return any(token in lowered for token in mismatch_tokens)

    @staticmethod
    def _classify_llm_exception(exc: Exception) -> _LLMDiagnostic:
        exc_name = type(exc).__name__.lower()
        text = str(exc).lower()
        if isinstance(exc, TimeoutError) or "timeout" in exc_name or "timed out" in text:
            return _LLMDiagnostic("timeout", True, "LLM request timed out", "timeout")
        if any(token in text for token in ("billing", "balance", "insufficient balance")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or billing limits",
                "insufficient_balance",
            )
        if any(token in text for token in ("quota", "insufficient_quota", "quota exceeded")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or rate limiting",
                "quota_exceeded",
            )
        if "ratelimit" in exc_name or any(token in text for token in ("rate limit", "too many requests", "rpm", "tpm")):
            return _LLMDiagnostic(
                "quota",
                True,
                "LLM request was rejected by quota or rate limiting",
                "rate_limit",
            )
        if SystemConfigService._has_provider_prefix_mismatch_signal(text):
            return _LLMDiagnostic(
                "model_not_found",
                False,
                "Configured model prefix does not match this channel",
                "provider_prefix_mismatch",
            )
        if SystemConfigService._has_model_access_denied_signal(str(exc)):
            return _LLMDiagnostic(
                "model_not_found",
                False,
                "Configured model is not available for this channel",
                "model_access_denied",
            )
        if SystemConfigService._has_request_blocked_signal(str(exc)):
            return _LLMDiagnostic(
                "request_blocked",
                False,
                "LLM request was blocked by provider or gateway policy",
                "provider_blocked",
            )
        if any(token in exc_name for token in ("auth", "permission")) or any(token in text for token in ("unauthorized", "forbidden", "invalid api key", "authentication")):
            return _LLMDiagnostic("auth", False, "LLM authentication failed", "api_key_rejected")
        if ("notfound" in exc_name or "model" in text) and (
            "not found" in text or "does not exist" in text or "unknown model" in text
        ) and SystemConfigService._has_model_not_found_signal(text):
            return _LLMDiagnostic(
                "model_not_found",
                False,
                "Configured model could not be found on this channel",
                "model_not_found",
            )
        if "dns" in text or "name resolution" in text or "temporary failure in name resolution" in text:
            return _LLMDiagnostic("network_error", True, "LLM request failed before a valid response was returned", "dns_error")
        if "refused" in text or "connection refused" in text:
            return _LLMDiagnostic("network_error", True, "LLM request failed before a valid response was returned", "connection_refused")
        if "ssl" in text or "tls" in text or "certificate" in text:
            return _LLMDiagnostic("network_error", True, "LLM request failed before a valid response was returned", "tls_error")
        if any(token in exc_name for token in ("connection", "network")) or any(
            token in text for token in ("connection", "network", "firewall")
        ):
            return _LLMDiagnostic("network_error", True, "LLM request failed before a valid response was returned", "network_error")
        return _LLMDiagnostic("network_error", False, "LLM channel test failed", "unknown_error")

    @staticmethod
    def _extract_llm_completion_content(response: Any) -> Tuple[str, Optional[str], Optional[str], Optional[str]]:
        def _field(obj: Any, key: str) -> Any:
            if isinstance(obj, dict):
                return obj.get(key)
            return getattr(obj, key, None)

        def _text_from_blocks(blocks: Any) -> str:
            if not isinstance(blocks, list):
                return ""
            text_parts: List[str] = []
            for block in blocks:
                if isinstance(block, str):
                    text_parts.append(block)
                    continue
                block_type = str(_field(block, "type") or "").strip().lower()
                if block_type and block_type not in {"text", "output_text"}:
                    continue
                text = _field(block, "text")
                if text is None:
                    text = _field(block, "content")
                if isinstance(text, str) and text:
                    text_parts.append(text)
            return strip_leading_think_wrapper("".join(text_parts))

        if response is None:
            return "", "empty_response", "Completion returned no response object", "null_response"

        choices = _field(response, "choices")
        if not choices:
            return "", "format_error", "Completion response did not include choices", "malformed_choices"

        choice = choices[0]
        message = _field(choice, "message")
        content_blocks = _field(choice, "content_blocks")
        if content_blocks is None and message is not None:
            content_blocks = _field(message, "content_blocks")
        if content_blocks is not None:
            content = _text_from_blocks(content_blocks)
            if content:
                return content, None, None, None

        if message is None:
            return "", "format_error", "Completion response did not include a message object", "malformed_choices"
        if isinstance(message, dict):
            has_content = "content" in message
        else:
            has_content = hasattr(message, "content")
        if not has_content:
            return "", "format_error", "Completion message did not include a content field", "malformed_choices"
        raw_content = _field(message, "content")
        if raw_content is None:
            return "", "empty_response", "Completion returned null message content", "null_content"
        content = (
            _text_from_blocks(raw_content)
            if isinstance(raw_content, list)
            else strip_leading_think_wrapper(str(raw_content))
        )
        if not content:
            return "", "empty_response", "Completion returned an empty message content", "empty_content"
        return content, None, None, None

    @staticmethod
    def _extract_llm_discovery_error(response: requests.Response) -> str:
        """Extract a concise error message from a failed model discovery response."""
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if isinstance(payload, dict):
            error_payload = payload.get("error")
            if isinstance(error_payload, dict):
                message = str(
                    error_payload.get("message")
                    or error_payload.get("code")
                    or ""
                ).strip()
                if message:
                    return message

            message = str(payload.get("message") or payload.get("detail") or "").strip()
            if message:
                return message

        text = response.text.strip()
        if text:
            return text[:200]
        return f"HTTP {response.status_code}"

    @staticmethod
    def _extract_discovered_llm_models(payload: Any) -> List[str]:
        """Normalize common `/models` response shapes into a unique model ID list."""
        raw_models: List[Any] = []
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                raw_models = payload["data"]
            elif isinstance(payload.get("models"), list):
                raw_models = payload["models"]
        elif isinstance(payload, list):
            raw_models = payload

        models: List[str] = []
        seen: Set[str] = set()
        for entry in raw_models:
            if isinstance(entry, str):
                model_id = entry.strip()
            elif isinstance(entry, dict):
                model_id = str(
                    entry.get("id") or entry.get("model") or entry.get("name") or ""
                ).strip()
            else:
                model_id = ""

            if not model_id or model_id in seen:
                continue

            seen.add(model_id)
            models.append(model_id)

        return models

    @staticmethod
    def _validate_cross_field(
        effective_map: Dict[str, str],
        updated_keys: Set[str],
        previous_effective_map: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        """Validate dependencies across multiple keys."""
        issues: List[Dict[str, Any]] = []

        token_value = (effective_map.get("TELEGRAM_BOT_TOKEN") or "").strip()
        chat_id_value = (effective_map.get("TELEGRAM_CHAT_ID") or "").strip()
        if token_value and not chat_id_value and (
            "TELEGRAM_BOT_TOKEN" in updated_keys or "TELEGRAM_CHAT_ID" in updated_keys
        ):
            issues.append(
                {
                    "key": "TELEGRAM_CHAT_ID",
                    "code": "missing_dependency",
                    "message": "TELEGRAM_CHAT_ID is required when TELEGRAM_BOT_TOKEN is set",
                    "severity": "error",
                    "expected": "non-empty TELEGRAM_CHAT_ID",
                    "actual": chat_id_value,
                }
            )

        feishu_relevant_keys = {
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "FEISHU_WEBHOOK_URL",
            "FEISHU_WEBHOOK_SECRET",
            "FEISHU_WEBHOOK_KEYWORD",
            "FEISHU_STREAM_ENABLED",
            "FEISHU_FOLDER_TOKEN",
            "FEISHU_CHAT_ID",
        }
        has_feishu_app_id = bool((effective_map.get("FEISHU_APP_ID") or "").strip())
        has_feishu_app_secret = bool((effective_map.get("FEISHU_APP_SECRET") or "").strip())
        has_feishu_app_credentials_complete = has_feishu_app_id and has_feishu_app_secret
        has_feishu_app_credentials = has_feishu_app_id or has_feishu_app_secret
        has_feishu_folder_token = bool((effective_map.get("FEISHU_FOLDER_TOKEN") or "").strip())
        has_feishu_full_cloud_doc_credentials = (
            has_feishu_app_credentials_complete
            and has_feishu_folder_token
        )
        # Match runtime semantics: Config.from_env only enables stream mode
        # when the value is exactly "true" (case-insensitive).
        feishu_stream_enabled = (
            (effective_map.get("FEISHU_STREAM_ENABLED") or "false")
            .strip()
            .lower()
            == "true"
        )
        has_feishu_stream_route = feishu_stream_enabled and has_feishu_app_credentials_complete
        has_feishu_app_bot_route = is_feishu_app_bot_env_configured(effective_map)
        if (
            has_feishu_app_credentials
            and not has_feishu_full_cloud_doc_credentials
            and not is_feishu_static_env_configured(effective_map)
            and not has_feishu_stream_route
            and not has_feishu_app_bot_route
            and (updated_keys & feishu_relevant_keys)
        ):
            issues.append(
                {
                    "key": "FEISHU_CHAT_ID",
                    "code": "feishu_mode_mismatch",
                    "message": (
                        "仅配置 FEISHU_APP_ID / FEISHU_APP_SECRET 不会开启飞书静态通知；"
                        "App Bot 主动推送需要同时配置 FEISHU_CHAT_ID，"
                        "Webhook 推送请填写 FEISHU_WEBHOOK_URL；"
                        "事件订阅请使用 FEISHU_STREAM_ENABLED=true 并完成应用发布与权限配置。"
                    ),
                    "severity": "warning",
                    "expected": (
                        "static notification: FEISHU_WEBHOOK_URL or "
                        "FEISHU_APP_ID + FEISHU_APP_SECRET + FEISHU_CHAT_ID; "
                        "event subscription: FEISHU_STREAM_ENABLED=true"
                    ),
                    "actual": "app credentials without notification target",
                }
            )

        issues.extend(
            SystemConfigService._validate_llm_channel_map(
                effective_map=effective_map,
                updated_keys=updated_keys,
            )
        )
        issues.extend(
            SystemConfigService._validate_llm_runtime_selection(
                effective_map=effective_map,
                updated_keys=updated_keys,
                previous_effective_map=previous_effective_map,
            )
        )

        if parse_env_bool(effective_map.get("NOTIFICATION_DAILY_DIGEST_ENABLED"), default=False):
            issues.append(
                {
                    "key": "NOTIFICATION_DAILY_DIGEST_ENABLED",
                    "code": "reserved_notification_daily_digest",
                    "message": (
                        "NOTIFICATION_DAILY_DIGEST_ENABLED is reserved; "
                        "the current P4 implementation does not send daily digests."
                    ),
                    "severity": "warning",
                    "expected": "reserved flag only",
                    "actual": effective_map.get("NOTIFICATION_DAILY_DIGEST_ENABLED", ""),
                }
            )

        return issues

    @staticmethod
    def _validate_llm_channel_map(effective_map: Dict[str, str], updated_keys: Set[str]) -> List[Dict[str, Any]]:
        """Validate channel-style LLM configuration stored in `.env`."""
        issues: List[Dict[str, Any]] = []
        if SystemConfigService._uses_litellm_yaml(effective_map):
            return issues

        raw_channels = (effective_map.get("LLM_CHANNELS") or "").strip()
        if not raw_channels:
            return issues

        normalized_names: List[str] = []
        seen_names: Set[str] = set()
        for raw_name in raw_channels.split(","):
            name = raw_name.strip()
            if not name:
                continue
            if not re.fullmatch(r"[A-Za-z0-9_]+", name):
                issues.append(
                    {
                        "key": "LLM_CHANNELS",
                        "code": "invalid_channel_name",
                        "message": f"LLM channel name '{name}' may only contain letters, numbers, and underscores",
                        "severity": "error",
                        "expected": "letters/numbers/underscores",
                        "actual": name,
                    }
                )
                continue

            normalized_upper = name.upper()
            if normalized_upper in seen_names:
                issues.append(
                    {
                        "key": "LLM_CHANNELS",
                        "code": "duplicate_channel_name",
                        "message": f"LLM channel '{name}' is declared more than once",
                        "severity": "error",
                        "expected": "unique channel names",
                        "actual": raw_channels,
                    }
                )
                continue

            seen_names.add(normalized_upper)
            normalized_names.append(name)

        # Strict completeness gating applies only to channels this update
        # actually touches (or a changed channel list); historical incomplete
        # channels must not block saving unrelated settings.
        llm_channels_touched = "LLM_CHANNELS" in updated_keys
        for name in normalized_names:
            prefix = f"LLM_{name.upper()}"
            touched = llm_channels_touched or any(
                updated_key.startswith(f"{prefix}_") for updated_key in updated_keys
            )
            provider, provider_id, provider_is_explicit = (
                SystemConfigService._resolve_connection_provider(effective_map, name)
            )
            if provider_is_explicit and provider is None and touched:
                provider_value = (effective_map.get(f"{prefix}_PROVIDER") or "").strip()
                issues.append(
                    {
                        "key": f"{prefix}_PROVIDER",
                        "code": "invalid_provider",
                        "message": (
                            f"LLM connection '{name}' references an unknown model provider"
                        ),
                        "severity": "error",
                        "expected": "provider id from the model provider catalog",
                        "actual": provider_value,
                    }
                )
            submitted_protocol = (effective_map.get(f"{prefix}_PROTOCOL") or "").strip()
            protocol_value, base_url_value = (
                SystemConfigService._resolve_connection_transport(
                    effective_map,
                    name,
                )
            )
            if (
                touched
                and submitted_protocol
                and provider_is_explicit
                and provider is not None
                and not provider["is_custom"]
                and canonicalize_llm_channel_protocol(submitted_protocol)
                != canonicalize_llm_channel_protocol(str(provider["protocol"]))
            ):
                issues.append(
                    {
                        "key": f"{prefix}_PROTOCOL",
                        "code": "provider_protocol_mismatch",
                        "message": (
                            f"LLM connection '{name}' protocol must match its Provider"
                        ),
                        "severity": "error",
                        "expected": str(provider["protocol"]),
                        "actual": submitted_protocol,
                    }
                )
            api_key_value = (
                (effective_map.get(f"{prefix}_API_KEYS") or "").strip()
                or (effective_map.get(f"{prefix}_API_KEY") or "").strip()
            )
            api_keys_value = (effective_map.get(f"{prefix}_API_KEYS") or "").strip()
            if name.lower() == "anspire" and not api_key_value:
                api_key_value = (effective_map.get("ANSPIRE_API_KEYS") or "").strip()
            models_value = [
                model.strip()
                for model in (effective_map.get(f"{prefix}_MODELS") or "").split(",")
                if model.strip()
            ]
            if name.lower() == "anspire" and not models_value:
                models_value = [
                    (
                        effective_map.get("ANSPIRE_LLM_MODEL")
                        or ANSPIRE_LLM_MODEL_DEFAULT
                    ).strip()
                ]
            enabled_raw = effective_map.get(f"{prefix}_ENABLED")
            if name.lower() == "anspire" and not (enabled_raw or "").strip():
                enabled_raw = effective_map.get("ANSPIRE_LLM_ENABLED")
            enabled = parse_env_bool(enabled_raw, default=True)
            if is_reserved_hermes_name(name):
                if touched:
                    result = parse_hermes_channel(
                        enabled=enabled,
                        protocol=protocol_value or HERMES_DEFAULT_PROTOCOL,
                        base_url=base_url_value or HERMES_DEFAULT_BASE_URL,
                        api_key=(effective_map.get(f"{prefix}_API_KEY") or "").strip(),
                        api_keys_raw=(effective_map.get(f"{prefix}_API_KEYS") or "").strip(),
                        extra_headers_raw=(effective_map.get(f"{prefix}_EXTRA_HEADERS") or "").strip(),
                        models=models_value or [HERMES_DEFAULT_MODEL],
                    )
                    for issue in result.issues:
                        issues.append(
                            {
                                "key": issue.field,
                                "code": issue.code,
                                "message": issue.message,
                                "severity": issue.severity,
                                "expected": "valid reserved Hermes channel",
                                "actual": "",
                            }
                        )
                continue
            validation_provider = provider
            if (
                not provider_is_explicit
                and provider is not None
                and provider.get("is_custom")
            ):
                # Legacy Connections had no Provider identity. Preserve the
                # established model-route inference only when it resolves to a
                # local runtime contract (for example ollama/model); explicit
                # Custom selections still require their own Base URL.
                inferred_protocol = resolve_llm_channel_protocol(
                    protocol_value,
                    base_url=base_url_value,
                    models=models_value or None,
                    channel_name=name,
                )
                from src.llm.provider_catalog import get_provider

                inferred_provider = get_provider(inferred_protocol)
                if inferred_provider is not None and inferred_provider.get("is_local"):
                    validation_provider = inferred_provider
            display_name_key = f"{prefix}_DISPLAY_NAME"
            # Legacy Connection payloads predate DISPLAY_NAME. Preserve their
            # identity label only when the key is absent; an explicit empty
            # value must still reach the authoritative required-field contract.
            display_name = (
                name
                if display_name_key not in effective_map
                else (effective_map.get(display_name_key) or "").strip()
            )
            issues.extend(
                SystemConfigService._validate_llm_channel_definition(
                    channel_name=name,
                    display_name=display_name,
                    provider=validation_provider,
                    provider_id=provider_id,
                    protocol_value=protocol_value,
                    base_url_value=base_url_value,
                    api_key_value=api_key_value,
                    api_keys_value=api_keys_value,
                    model_values=models_value,
                    extra_headers_value=(effective_map.get(f"{prefix}_EXTRA_HEADERS") or "").strip(),
                    enabled=enabled,
                    field_prefix=prefix,
                    require_complete=enabled and touched,
                )
            )

        return issues

    @staticmethod
    def _collect_llm_channel_models_from_map(effective_map: Dict[str, str]) -> List[str]:
        return llm_channel_map.collect_llm_channel_models_from_map(effective_map)

    @staticmethod
    def _collect_hermes_channel_models_from_map(effective_map: Dict[str, str]) -> List[str]:
        return llm_channel_map.collect_hermes_channel_models_from_map(effective_map)

    @staticmethod
    def _collect_non_hermes_channel_models_from_map(effective_map: Dict[str, str]) -> List[str]:
        return llm_channel_map.collect_non_hermes_channel_models_from_map(effective_map)

    @staticmethod
    def _collect_mixed_hermes_routes_from_map(effective_map: Dict[str, str]) -> Set[str]:
        return llm_channel_map.collect_mixed_hermes_routes_from_map(effective_map)

    @staticmethod
    def _matches_route_set(model: str, routes: Set[str]) -> bool:
        return llm_channel_map.matches_route_set(model, routes)

    @staticmethod
    def _matches_exact_route(model: str, routes: Set[str]) -> bool:
        return llm_channel_map.matches_exact_route(model, routes)

    @staticmethod
    def _uses_litellm_yaml(effective_map: Dict[str, str]) -> bool:
        return llm_channel_map.uses_litellm_yaml(effective_map)

    @staticmethod
    def _collect_yaml_models_from_map(effective_map: Dict[str, str]) -> List[str]:
        return llm_channel_map.collect_yaml_models_from_map(effective_map)

    @staticmethod
    def _has_legacy_key_for_provider(provider: str, effective_map: Dict[str, str]) -> bool:
        return llm_channel_map.has_legacy_key_for_provider(provider, effective_map)

    @staticmethod
    def _has_runtime_source_for_model(model: str, effective_map: Dict[str, str]) -> bool:
        return llm_channel_map.has_runtime_source_for_model(model, effective_map)

    @staticmethod
    def _collect_llm_route_references(
        effective_map: Dict[str, str],
        known_routes: Set[str],
    ) -> Dict[str, List[Dict[str, str]]]:
        return ModelAssignmentValidator.collect_llm_route_references(effective_map, known_routes)

    @staticmethod
    def _collect_llm_route_connection_ids(
        effective_map: Dict[str, str],
    ) -> Dict[str, List[str]]:
        return ModelAssignmentValidator.collect_llm_route_connection_ids(effective_map)

    @staticmethod
    def _collect_llm_channel_model_refs_from_map(
        effective_map: Dict[str, str],
    ) -> List[str]:
        return ModelAssignmentValidator.collect_llm_channel_model_refs_from_map(effective_map)

    @staticmethod
    def _collect_model_ref_assignment_issues(
        effective_map: Dict[str, str],
        updated_keys: Set[str],
    ) -> List[Dict[str, Any]]:
        return ModelAssignmentValidator.collect_model_ref_assignment_issues(effective_map, updated_keys)

    @staticmethod
    def _model_removal_issue_key(
        connection_ids: Sequence[str],
        updated_keys: Set[str],
    ) -> str:
        return ModelAssignmentValidator.model_removal_issue_key(connection_ids, updated_keys)

    @staticmethod
    def _collect_removed_model_in_use_issues(
        effective_map: Dict[str, str],
        previous_effective_map: Optional[Dict[str, str]],
        updated_keys: Set[str],
    ) -> List[Dict[str, Any]]:
        return ModelAssignmentValidator.collect_removed_model_in_use_issues(
            effective_map,
            previous_effective_map,
            updated_keys,
        )

    @staticmethod
    def _validate_llm_runtime_selection(
        effective_map: Dict[str, str],
        updated_keys: Optional[Set[str]] = None,
        previous_effective_map: Optional[Dict[str, str]] = None,
    ) -> List[Dict[str, Any]]:
        return ModelAssignmentValidator.validate_llm_runtime_selection(
            effective_map,
            updated_keys,
            previous_effective_map,
        )

    @staticmethod
    def _unknown_connection_contract_issues(
        *,
        schema: Sequence[Dict[str, Any]],
        values: Dict[str, str],
        field_prefix: str,
        field_keys: Optional[Sequence[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Build stable validation issues for unsupported field conditions."""
        fields_by_key = {
            str(field.get("key") or ""): field
            for field in schema
        }
        issues: List[Dict[str, Any]] = []
        for field_key in get_unknown_connection_contract_fields(
            schema,
            values,
            field_keys=field_keys,
        ):
            field = fields_by_key.get(field_key, {})
            env_suffix = str(field.get("env_suffix") or "").strip()
            issue_key = (
                field_key
                if field_prefix == "test_channel"
                else f"{field_prefix}_{env_suffix}" if env_suffix else field_prefix
            )
            issues.append(
                {
                    "key": issue_key,
                    "code": "unknown_contract_condition",
                    "message": (
                        f"LLM channel field '{field_key}' uses an unsupported "
                        "contract condition"
                    ),
                    "severity": "error",
                    "expected": "supported condition operator",
                    "actual": "unknown",
                }
            )
        return issues

    @staticmethod
    def _validate_llm_channel_definition(
        *,
        channel_name: str,
        display_name: str = "",
        provider: Optional[Dict[str, Any]] = None,
        provider_id: str = "",
        protocol_value: str,
        base_url_value: str,
        api_key_value: str,
        api_keys_value: str = "",
        model_values: Sequence[str],
        extra_headers_value: str = "",
        enabled: bool,
        field_prefix: str,
        require_complete: bool,
    ) -> List[Dict[str, Any]]:
        """Validate one normalized LLM channel definition."""
        if require_complete:
            issues, resolved_protocol = SystemConfigService._validate_llm_channel_connection(
                channel_name=channel_name,
                provider=provider,
                provider_id=provider_id,
                protocol_value=protocol_value,
                base_url_value=base_url_value,
                api_key_value=api_key_value,
                api_keys_value=api_keys_value,
                model_values=model_values,
                extra_headers_value=extra_headers_value,
                enabled=enabled,
                field_prefix=field_prefix,
            )
        else:
            issues = []
            resolved_protocol = resolve_llm_channel_protocol(
                protocol_value,
                base_url=base_url_value,
                models=list(model_values) if model_values else None,
                channel_name=channel_name,
            )
        models_key = f"{field_prefix}_MODELS" if field_prefix != "test_channel" else "models"
        contract_values = build_connection_contract_values(
            connection_name=channel_name,
            display_name=display_name,
            provider_id=provider_id,
            provider=provider,
            protocol=resolved_protocol,
            base_url=base_url_value,
            api_key=api_key_value,
            api_keys=api_keys_value,
            models=model_values,
            extra_headers=extra_headers_value,
            enabled=enabled,
        )
        connection_schema = get_connection_field_schema()
        missing_fields = validate_connection_contract_values(
            connection_schema,
            contract_values,
        )
        issues.extend(
            SystemConfigService._unknown_connection_contract_issues(
                schema=connection_schema,
                values=contract_values,
                field_prefix=field_prefix,
                field_keys=(
                    (
                        "connection_name",
                        "display_name",
                        "provider_id",
                        "api_keys",
                        "models",
                        "extra_headers",
                        "enabled",
                    )
                    if require_complete
                    else None
                ),
            )
        )

        if "display_name" in missing_fields:
            display_name_key = (
                f"{field_prefix}_DISPLAY_NAME"
                if field_prefix != "test_channel"
                else "display_name"
            )
            issues.append(
                {
                    "key": display_name_key,
                    "code": "field_required",
                    "message": f"LLM channel '{channel_name}' requires a display name",
                    "severity": "error",
                    "expected": "non-empty value",
                    "actual": "",
                }
            )

        # Disabled drafts may omit fields required only while enabled, but
        # unconditional identity requirements and schema diagnostics still apply.
        if not require_complete:
            return issues

        if "models" in missing_fields:
            issues.append(
                {
                    "key": models_key,
                    "code": "missing_models",
                    "message": f"LLM channel '{channel_name}' requires at least one model",
                    "severity": "error",
                    "expected": "comma-separated model list",
                    "actual": "",
                }
            )
        elif not resolved_protocol:
            unresolved = [model for model in model_values if "/" not in model]
            if unresolved:
                issues.append(
                    {
                        "key": models_key,
                        "code": "missing_protocol",
                        "message": (
                            f"LLM channel '{channel_name}' uses bare model names. "
                            "Set PROTOCOL or add provider/model prefixes."
                        ),
                        "severity": "error",
                        "expected": "protocol or provider/model",
                        "actual": ", ".join(unresolved[:3]),
                    }
                )

        return issues

    @staticmethod
    def _validate_llm_channel_connection(
        *,
        channel_name: str,
        provider: Optional[Dict[str, Any]] = None,
        provider_id: str = "",
        protocol_value: str,
        base_url_value: str,
        api_key_value: str,
        api_keys_value: str = "",
        model_values: Sequence[str] = (),
        extra_headers_value: str = "",
        enabled: bool = True,
        field_prefix: str,
    ) -> Tuple[List[Dict[str, Any]], str]:
        """Validate connection-level fields shared by test and discovery flows."""
        issues: List[Dict[str, Any]] = []
        protocol_key = f"{field_prefix}_PROTOCOL" if field_prefix != "test_channel" else "protocol"
        base_url_key = f"{field_prefix}_BASE_URL" if field_prefix != "test_channel" else "base_url"
        api_key_key = f"{field_prefix}_API_KEY" if field_prefix != "test_channel" else "api_key"

        normalized_protocol = canonicalize_llm_channel_protocol(protocol_value)
        if normalized_protocol and normalized_protocol not in SUPPORTED_LLM_CHANNEL_PROTOCOLS:
            issues.append(
                {
                    "key": protocol_key,
                    "code": "invalid_protocol",
                    "message": (
                        f"Unsupported LLM channel protocol '{protocol_value}'. "
                        f"Supported: {', '.join(SUPPORTED_LLM_CHANNEL_PROTOCOLS)}"
                    ),
                    "severity": "error",
                    "expected": ",".join(SUPPORTED_LLM_CHANNEL_PROTOCOLS),
                    "actual": protocol_value,
                }
            )

        if base_url_value and not SystemConfigService._is_valid_llm_base_url(base_url_value):
            issues.append(
                {
                    "key": base_url_key,
                    "code": "invalid_url",
                    "message": "LLM channel base URL must be a valid absolute URL",
                    "severity": "error",
                    "expected": "http(s)://host",
                    "actual": base_url_value,
                }
            )
        elif base_url_value and not SystemConfigService._is_safe_base_url(base_url_value):
            issues.append(
                {
                    "key": base_url_key,
                    "code": "ssrf_blocked",
                    "message": "LLM channel base URL points to a restricted address (cloud metadata services are not allowed)",
                    "severity": "error",
                    "expected": "publicly reachable or local LLM endpoint",
                    "actual": base_url_value,
                }
            )

        resolved_protocol = resolve_llm_channel_protocol(
            protocol_value,
            base_url=base_url_value,
            models=list(model_values) if model_values else None,
            channel_name=channel_name,
        )
        # Parsed segments make comma-only credentials empty before contract
        # evaluation. Requirement decisions themselves stay in the shared schema.
        parsed_api_key = ",".join(
            segment.strip() for segment in api_key_value.split(",") if segment.strip()
        )
        contract_values = build_connection_contract_values(
            connection_name=channel_name,
            display_name=channel_name,
            provider_id=provider_id,
            provider=provider,
            protocol=resolved_protocol,
            base_url=base_url_value,
            api_key=parsed_api_key,
            api_keys=api_keys_value,
            models=model_values,
            extra_headers=extra_headers_value,
            enabled=enabled,
        )
        connection_schema = get_connection_field_schema()
        missing_fields = validate_connection_contract_values(
            connection_schema,
            contract_values,
            field_keys=("protocol", "base_url", "api_key"),
        )
        issues.extend(
            SystemConfigService._unknown_connection_contract_issues(
                schema=connection_schema,
                values=contract_values,
                field_prefix=field_prefix,
                field_keys=("protocol", "base_url", "api_key"),
            )
        )
        if "protocol" in missing_fields:
            issues.append(
                {
                    "key": protocol_key,
                    "code": "missing_protocol",
                    "message": f"LLM channel '{channel_name}' requires a protocol",
                    "severity": "error",
                    "expected": "supported protocol",
                    "actual": "",
                }
            )
        if "base_url" in missing_fields:
            issues.append(
                {
                    "key": base_url_key,
                    "code": "missing_base_url",
                    "message": f"LLM channel '{channel_name}' requires a base URL",
                    "severity": "error",
                    "expected": "http(s)://host/v1",
                    "actual": "",
                }
            )
        if "api_key" in missing_fields:
            issues.append(
                {
                    "key": api_key_key,
                    "code": "missing_api_key",
                    "message": f"LLM channel '{channel_name}' requires an API key",
                    "severity": "error",
                    "expected": "non-empty API key",
                    "actual": api_key_value,
                }
            )
        return issues, resolved_protocol
