"""Llm Operations methods for the system-config facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.system_config_service import (
        Any,
        Dict,
        List,
        Optional,
        Sequence,
        Set,
        _LLMDiagnostic,
        apply_litellm_generation_params,
        call_litellm_with_param_recovery,
        canonicalize_hermes_base_url,
        canonicalize_hermes_model_ref,
        channel_allows_empty_api_key,
        is_reserved_hermes_name,
        json,
        log_safe_exception,
        logger,
        logging,
        normalize_llm_channel_model,
        open_hermes_no_proxy_client,
        requests,
        resolve_llm_channel_protocol,
        sanitize_exception_chain,
        time,
    )


class _SystemConfigLLMOperationsMethods:
    def discover_llm_channel_models(
        self,
        *,
        name: str,
        provider_id: Optional[str] = None,
        protocol: str,
        base_url: str,
        api_key: str,
        models: Sequence[str] = (),
        timeout_seconds: float = 20.0,
        use_saved_secret: bool = False,
    ) -> Dict[str, Any]:
        """Discover available models through the Provider's Catalog contract."""
        channel_name = name.strip() or "channel"
        provider, protocol, base_url, provider_issue = self._resolve_request_provider(
            provider_id=provider_id,
            protocol=protocol,
            base_url=base_url,
        )
        if provider_issue is not None:
            return self._build_llm_channel_result(
                success=False,
                message="LLM channel configuration is invalid",
                error=provider_issue["message"],
                stage="model_discovery",
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": provider_issue["key"],
                    "issue_code": provider_issue["code"],
                    "reason": provider_issue["code"],
                },
                resolved_protocol=None,
                models=[],
                latency_ms=None,
            )
        resolved_secret, secret_error, redaction_values = self._resolve_hermes_saved_secret(
            channel_name=channel_name,
            protocol=protocol,
            base_url=base_url,
            submitted_api_key=api_key,
            use_saved_secret=use_saved_secret,
            stage="model_discovery",
        )
        if resolved_secret is None:
            return secret_error
        api_key = resolved_secret
        redaction_values.update(self._build_redaction_values(api_key))
        if is_reserved_hermes_name(channel_name):
            secret_error = self._validate_hermes_submitted_secret(
                api_key=api_key,
                use_saved_secret=use_saved_secret,
                stage="model_discovery",
                models=[],
                redaction_values=redaction_values,
            )
            if secret_error is not None:
                return secret_error
            try:
                base_url = canonicalize_hermes_base_url(base_url)
            except ValueError as exc:
                return self._build_llm_channel_result(
                    success=False,
                    message="Hermes Base URL is invalid",
                    error=str(exc),
                    stage="model_discovery",
                    error_code="invalid_config",
                    retryable=False,
                    details={
                        "issue_key": "discover_channel_BASE_URL",
                        "issue_code": "invalid_hermes_url",
                        "reason": "invalid_hermes_url",
                    },
                    resolved_protocol=None,
                    models=[],
                    latency_ms=None,
                    redaction_values=redaction_values,
                )
        existing_models = [str(m).strip() for m in models if str(m).strip()]
        validation_issues, resolved_protocol = self._validate_llm_channel_connection(
            channel_name=channel_name,
            provider=provider,
            provider_id=str(provider_id or ""),
            protocol_value=protocol,
            base_url_value=base_url,
            api_key_value=api_key,
            model_values=existing_models,
            field_prefix="discover_channel",
        )
        if not resolved_protocol and existing_models:
            resolved_protocol = resolve_llm_channel_protocol(
                protocol,
                base_url=base_url,
                models=existing_models,
                channel_name=channel_name,
            )
        errors = [issue for issue in validation_issues if issue["severity"] == "error"]
        if errors:
            return self._build_llm_channel_result(
                success=False,
                message="LLM channel configuration is invalid",
                error=errors[0]["message"],
                stage="model_discovery",
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": errors[0]["key"],
                    "issue_code": errors[0]["code"],
                    "reason": errors[0]["code"],
                },
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=None,
                redaction_values=redaction_values,
            )

        from src.llm.provider_catalog import supports_model_discovery

        if not supports_model_discovery(
            provider_id=str(provider_id or ""),
            protocol=resolved_protocol,
        ):
            return self._build_llm_channel_result(
                success=False,
                message="Model discovery is not supported for this protocol",
                error=(
                    f"LLM channel '{channel_name}' protocol '{resolved_protocol}' "
                    "does not support /models discovery yet"
                ),
                stage="model_discovery",
                error_code="unsupported_protocol",
                retryable=False,
                details={"protocol": resolved_protocol or None},
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=None,
                redaction_values=redaction_values,
            )

        api_keys = [segment.strip() for segment in api_key.split(",") if segment.strip()]
        selected_api_key = api_keys[0] if api_keys else ""
        redaction_values.update(self._build_redaction_values(selected_api_key))
        request_headers = {"Accept": "application/json"}
        if selected_api_key:
            request_headers["Authorization"] = f"Bearer {selected_api_key}"

        try:
            models_url = self._build_llm_models_url(
                base_url,
                protocol=resolved_protocol,
            )
        except ValueError as exc:
            return self._build_llm_channel_result(
                success=False,
                message="LLM channel configuration is invalid",
                error=str(exc),
                stage="model_discovery",
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": "discover_channel_BASE_URL",
                    "issue_code": "invalid_url",
                    "reason": "invalid_url",
                },
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=None,
                redaction_values=redaction_values,
            )

        try:
            started_at = time.perf_counter()
            if is_reserved_hermes_name(channel_name):
                session = requests.Session()
                session.trust_env = False
                try:
                    response = session.get(
                        models_url,
                        headers=request_headers,
                        timeout=max(5.0, float(timeout_seconds)),
                        allow_redirects=False,
                    )
                finally:
                    session.close()
            else:
                response = requests.get(
                    models_url,
                    headers=request_headers,
                    timeout=max(5.0, float(timeout_seconds)),
                    allow_redirects=False,
                )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
        except requests.RequestException as exc:
            log_safe_exception(
                logger,
                "LLM channel model discovery failed",
                exc,
                error_code="llm_channel_model_discovery_failed",
                level=logging.WARNING,
                context={"channel": channel_name},
                redaction_values=redaction_values,
            )
            diagnostic = self._classify_llm_exception(exc)
            return self._build_llm_channel_result(
                success=False,
                message=diagnostic.message,
                error=sanitize_exception_chain(exc, redaction_values=redaction_values),
                stage="model_discovery",
                error_code=diagnostic.error_code,
                retryable=diagnostic.retryable,
                details=self._merge_llm_diagnostic_details({"endpoint": models_url}, diagnostic),
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=None,
                redaction_values=redaction_values,
            )

        if 300 <= response.status_code < 400:
            return self._build_llm_channel_result(
                success=False,
                message="Model discovery request was redirected",
                error="Redirect responses are not allowed for model discovery",
                stage="model_discovery",
                error_code="network_error",
                retryable=False,
                details={"endpoint": models_url, "http_status": response.status_code},
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=latency_ms,
                redaction_values=redaction_values,
            )

        if not response.ok:
            error_text = self._extract_llm_discovery_error(response)
            diagnostic = self._classify_llm_http_error(
                status_code=response.status_code,
                error_text=error_text,
            )
            return self._build_llm_channel_result(
                success=False,
                message=diagnostic.message,
                error=error_text,
                stage="model_discovery",
                error_code=diagnostic.error_code,
                retryable=diagnostic.retryable,
                details=self._merge_llm_diagnostic_details(
                    {"endpoint": models_url, "http_status": response.status_code},
                    diagnostic,
                ),
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=latency_ms,
                redaction_values=redaction_values,
            )

        try:
            payload = response.json()
        except ValueError:
            return self._build_llm_channel_result(
                success=False,
                message="Model discovery returned invalid JSON",
                error="The /models endpoint did not return valid JSON",
                stage="response_parse",
                error_code="format_error",
                retryable=False,
                details={"endpoint": models_url, "http_status": response.status_code, "reason": "non_json"},
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=latency_ms,
                redaction_values=redaction_values,
            )

        models = self._extract_discovered_llm_models(payload)
        if not models:
            return self._build_llm_channel_result(
                success=False,
                message="Model discovery returned no models",
                error="The /models endpoint did not return any model IDs",
                stage="response_parse",
                error_code="empty_response",
                retryable=False,
                details={"endpoint": models_url, "http_status": response.status_code, "reason": "empty_models"},
                resolved_protocol=resolved_protocol or None,
                models=[],
                latency_ms=latency_ms,
                redaction_values=redaction_values,
            )

        return self._build_llm_channel_result(
            success=True,
            message="LLM channel model discovery succeeded",
            error=None,
            stage="model_discovery",
            error_code=None,
            retryable=False,
            details={"endpoint": models_url, "model_count": len(models)},
            resolved_protocol=resolved_protocol or None,
            models=models,
            latency_ms=latency_ms,
            redaction_values=redaction_values,
        )

    def test_llm_channel(
        self,
        *,
        name: str,
        provider_id: Optional[str] = None,
        protocol: str,
        base_url: str,
        api_key: str,
        models: Sequence[str],
        enabled: bool = True,
        timeout_seconds: float = 20.0,
        capability_checks: Sequence[str] = (),
        use_saved_secret: bool = False,
    ) -> Dict[str, Any]:
        """Run a minimal completion call against one channel definition."""
        requested_capabilities = self._normalize_llm_capability_checks(capability_checks)
        raw_models = [str(model).strip() for model in models if str(model).strip()]
        channel_name = name.strip() or "channel"
        provider, protocol, base_url, provider_issue = self._resolve_request_provider(
            provider_id=provider_id,
            protocol=protocol,
            base_url=base_url,
        )
        if provider_issue is not None:
            return self._build_llm_channel_result(
                success=False,
                message="LLM channel configuration is invalid",
                error=provider_issue["message"],
                stage="chat_completion",
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": provider_issue["key"],
                    "issue_code": provider_issue["code"],
                    "reason": provider_issue["code"],
                },
                resolved_protocol=None,
                resolved_model=None,
                latency_ms=None,
                capability_results=self._build_skipped_capability_results(
                    requested_capabilities,
                    "base_test_failed",
                    "Skipped because the base channel test did not pass",
                ),
            )
        resolved_secret, secret_error, redaction_values = self._resolve_hermes_saved_secret(
            channel_name=channel_name,
            protocol=protocol,
            base_url=base_url,
            submitted_api_key=api_key,
            use_saved_secret=use_saved_secret,
            stage="chat_completion",
        )
        if resolved_secret is None:
            result = secret_error
            if requested_capabilities and "capability_results" not in result:
                result["capability_results"] = self._build_skipped_capability_results(
                    requested_capabilities,
                    "base_test_failed",
                    "Skipped because the base channel test did not pass",
                    redaction_values=redaction_values,
                )
            return result
        api_key = resolved_secret
        redaction_values.update(self._build_redaction_values(api_key))
        if is_reserved_hermes_name(channel_name):
            secret_error = self._validate_hermes_submitted_secret(
                api_key=api_key,
                use_saved_secret=use_saved_secret,
                stage="chat_completion",
                capability_checks=requested_capabilities,
                redaction_values=redaction_values,
            )
            if secret_error is not None:
                return secret_error
            try:
                base_url = canonicalize_hermes_base_url(base_url)
            except ValueError as exc:
                return self._build_llm_channel_result(
                    success=False,
                    message="Hermes Base URL is invalid",
                    error=str(exc),
                    stage="chat_completion",
                    error_code="invalid_config",
                    retryable=False,
                    details={
                        "issue_key": "test_channel_BASE_URL",
                        "issue_code": "invalid_hermes_url",
                        "reason": "invalid_hermes_url",
                    },
                    resolved_protocol=None,
                    resolved_model=None,
                    latency_ms=None,
                    capability_results=self._build_skipped_capability_results(
                        requested_capabilities,
                        "base_test_failed",
                        "Skipped because the base channel test did not pass",
                        redaction_values=redaction_values,
                    ),
                    redaction_values=redaction_values,
                )
        validation_issues = self._validate_llm_channel_definition(
            channel_name=channel_name,
            display_name=channel_name,
            provider=provider,
            provider_id=str(provider_id or ""),
            protocol_value=protocol,
            base_url_value=base_url,
            api_key_value=api_key,
            model_values=raw_models,
            enabled=enabled,
            field_prefix="test_channel",
            require_complete=True,
        )
        errors = [issue for issue in validation_issues if issue["severity"] == "error"]
        if errors:
            return self._build_llm_channel_result(
                success=False,
                message="LLM channel configuration is invalid",
                error=errors[0]["message"],
                stage="chat_completion",
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": errors[0]["key"],
                    "issue_code": errors[0]["code"],
                    "reason": errors[0]["code"],
                },
                resolved_protocol=None,
                resolved_model=None,
                latency_ms=None,
                capability_results=self._build_skipped_capability_results(
                    requested_capabilities,
                    "base_test_failed",
                    "Skipped because the base channel test did not pass",
                    redaction_values=redaction_values,
                ),
                redaction_values=redaction_values,
            )

        resolved_protocol = resolve_llm_channel_protocol(protocol, base_url=base_url, models=raw_models, channel_name=name)
        resolved_models = [normalize_llm_channel_model(model, resolved_protocol, base_url) for model in raw_models]
        resolved_model = resolved_models[0]
        if is_reserved_hermes_name(channel_name):
            resolved_model = canonicalize_hermes_model_ref(raw_models[0]).wire_model
        api_keys = [segment.strip() for segment in api_key.split(",") if segment.strip()]
        selected_api_key = api_keys[0] if api_keys else ""
        redaction_values.update(self._build_redaction_values(selected_api_key))

        call_kwargs: Dict[str, Any] = {
            "model": resolved_model,
            "messages": [{"role": "user", "content": "Reply with OK"}],
            "max_tokens": 256,  # Increased to allow MiniMax-M3 thinking process + response
            "timeout": max(5.0, float(timeout_seconds)),
        }
        adapter_api_key = selected_api_key
        if (
            not adapter_api_key
            and resolved_protocol == "openai"
            and channel_allows_empty_api_key(resolved_protocol, base_url)
        ):
            # The OpenAI SDK requires a non-empty constructor value even when a
            # trusted local endpoint does not authenticate requests.
            adapter_api_key = self._LLM_EMPTY_API_KEY_ADAPTER_SENTINEL
        if adapter_api_key:
            call_kwargs["api_key"] = adapter_api_key
        if base_url.strip():
            call_kwargs["api_base"] = base_url.strip()
        call_kwargs = apply_litellm_generation_params(
            call_kwargs,
            resolved_model,
            self._get_runtime_llm_temperature(),
        )

        try:
            import litellm
            from src.agent.llm_adapter import (
                resolve_fallback_litellm_wire_models,
                register_fallback_model_pricing,
            )

            # Register fallback pricing for OpenAI-compatible models to prevent cost calculation errors
            config_model_list = None
            if getattr(self, "_config", None) is not None:
                config_model_list = getattr(self._config, "llm_model_list", None)
            register_fallback_model_pricing(
                resolve_fallback_litellm_wire_models(
                    resolved_model,
                    config_model_list,
                )
            )

            started_at = time.perf_counter()
            if is_reserved_hermes_name(channel_name):
                with open_hermes_no_proxy_client(
                    api_key=selected_api_key,
                    base_url=base_url,
                    timeout=max(5.0, float(timeout_seconds)),
                ) as client:
                    hermes_call_kwargs = dict(call_kwargs)
                    hermes_call_kwargs["stream"] = False
                    hermes_call_kwargs["client"] = client
                    hermes_call_kwargs.pop("api_key", None)
                    hermes_call_kwargs.pop("api_base", None)
                    response = call_litellm_with_param_recovery(
                        lambda kwargs: litellm.completion(**kwargs),
                        model=resolved_model,
                        call_kwargs=hermes_call_kwargs,
                        logger=logger,
                        log_label="[Hermes channel test]",
                    )
            else:
                response = call_litellm_with_param_recovery(
                    lambda kwargs: litellm.completion(**kwargs),
                    model=resolved_model,
                    call_kwargs=call_kwargs,
                    logger=logger,
                    log_label="[LLM channel test]",
                )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            content, parse_error_code, parse_error, parse_reason = self._extract_llm_completion_content(response)
            if parse_error_code:
                message = (
                    "LLM channel returned an empty response"
                    if parse_error_code == "empty_response"
                    else "LLM channel returned an unexpected response format"
                )
                return self._build_llm_channel_result(
                    success=False,
                    message=message,
                    error=parse_error,
                    stage="response_parse",
                    error_code=parse_error_code,
                    retryable=False,
                    details={"response_error": parse_error, "reason": parse_reason},
                    resolved_protocol=resolved_protocol or None,
                    resolved_model=resolved_model,
                    latency_ms=latency_ms,
                    capability_results=self._build_skipped_capability_results(
                        requested_capabilities,
                        "base_test_failed",
                        "Skipped because the base channel test did not pass",
                        redaction_values=redaction_values,
                    ),
                    redaction_values=redaction_values,
                )

            capability_results: Dict[str, Any] = {}
            if requested_capabilities and is_reserved_hermes_name(channel_name):
                capability_results = self._run_hermes_capability_checks(
                    litellm_module=litellm,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    capability_checks=requested_capabilities,
                    redaction_values=redaction_values,
                )
            elif requested_capabilities:
                capability_results = self._run_llm_capability_checks(
                    litellm_module=litellm,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    capability_checks=requested_capabilities,
                    redaction_values=redaction_values,
                )
            return self._build_llm_channel_result(
                success=True,
                message="LLM channel test succeeded",
                error=None,
                stage="chat_completion",
                error_code=None,
                retryable=False,
                details={"response_preview": content[:80]},
                resolved_protocol=resolved_protocol or None,
                resolved_model=resolved_model,
                latency_ms=latency_ms,
                capability_results=capability_results,
                redaction_values=redaction_values,
            )
        except Exception as exc:  # broad-exception: fallback_recorded - return a structured LLM test diagnostic
            log_safe_exception(
                logger,
                "LLM channel test failed",
                exc,
                error_code="llm_channel_test_failed",
                level=logging.WARNING,
                context={"channel": channel_name},
                redaction_values=redaction_values,
            )
            diagnostic = self._classify_llm_exception(exc)
            return self._build_llm_channel_result(
                success=False,
                message=diagnostic.message,
                error=sanitize_exception_chain(exc, redaction_values=redaction_values),
                stage="chat_completion",
                error_code=diagnostic.error_code,
                retryable=diagnostic.retryable,
                details=self._merge_llm_diagnostic_details({"model": resolved_model}, diagnostic),
                resolved_protocol=resolved_protocol or None,
                resolved_model=resolved_model,
                latency_ms=None,
                redaction_values=redaction_values,
                capability_results=self._build_skipped_capability_results(
                    requested_capabilities,
                    "base_test_failed",
                    "Skipped because the base channel test did not pass",
                    redaction_values=redaction_values,
                ),
            )

    @classmethod
    def _normalize_llm_capability_checks(cls, capability_checks: Sequence[str]) -> List[str]:
        requested = {str(check).strip().lower() for check in capability_checks if str(check).strip()}
        return [check for check in cls._LLM_CAPABILITY_ORDER if check in requested]

    @classmethod
    def _build_skipped_capability_results(
        cls,
        capability_checks: Sequence[str],
        reason: str,
        message: str,
        *,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        return {
            capability: cls._build_llm_capability_result(
                capability=capability,
                status="skipped",
                message=message,
                error_code="skipped",
                retryable=False,
                details={"reason": reason},
                redaction_values=redaction_values,
            )
            for capability in capability_checks
        }

    @classmethod
    def _run_hermes_capability_checks(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
        capability_checks: Sequence[str],
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        for capability in capability_checks:
            if capability != "json":
                results[capability] = cls._build_llm_capability_result(
                    capability=capability,
                    status="skipped",
                    message="Hermes Phase 3 does not probe this capability",
                    error_code="not_probed",
                    retryable=False,
                    details={"reason": "not_probed"},
                    redaction_values=redaction_values,
                )
                continue
            try:
                started_at = time.perf_counter()
                with open_hermes_no_proxy_client(
                    api_key=selected_api_key,
                    base_url=base_url,
                    timeout=max(5.0, float(timeout_seconds)),
                ) as client:
                    call_kwargs = cls._build_llm_capability_completion_kwargs(
                        resolved_model=resolved_model,
                        selected_api_key=selected_api_key,
                        base_url=base_url,
                        timeout_seconds=timeout_seconds,
                        messages=[{"role": "user", "content": 'Return exactly this JSON object: {"status":"ok"}'}],
                        max_tokens=64,
                        extra={"response_format": {"type": "json_object"}, "client": client},
                    )
                    call_kwargs.pop("api_key", None)
                    call_kwargs.pop("api_base", None)
                    response = litellm_module.completion(**call_kwargs)
                    content, parse_error_code, parse_error, parse_reason = cls._extract_llm_completion_content(response)
                latency_ms = int((time.perf_counter() - started_at) * 1000)
                if parse_error_code:
                    results[capability] = cls._build_llm_capability_result(
                        capability="json",
                        status="failed",
                        message="JSON capability check returned no parseable content",
                        error_code=parse_error_code,
                        retryable=False,
                        latency_ms=latency_ms,
                        details={"reason": parse_reason, "response_error": parse_error},
                        redaction_values=redaction_values,
                    )
                    continue
                try:
                    payload = json.loads(content)
                except ValueError:
                    payload = None
                if not isinstance(payload, dict) or payload.get("status") != "ok":
                    results[capability] = cls._build_llm_capability_result(
                        capability="json",
                        status="failed",
                        message="JSON capability check returned non-JSON content",
                        error_code="format_error",
                        retryable=False,
                        latency_ms=latency_ms,
                        details={"reason": "non_json", "response_preview": content[:80]},
                        redaction_values=redaction_values,
                    )
                    continue
                results[capability] = cls._build_llm_capability_result(
                    capability="json",
                    status="passed",
                    message="JSON output capability check passed",
                    latency_ms=latency_ms,
                    details={"reason": "json_valid"},
                    redaction_values=redaction_values,
                )
            except Exception as exc:  # broad-exception: optional_metadata - capture a failed Hermes capability probe
                diagnostic = cls._classify_llm_capability_exception(exc, "json")
                results[capability] = cls._build_llm_capability_result_from_diagnostic(
                    "json",
                    diagnostic,
                    cls._sanitize_llm_error_text(exc, redaction_values=redaction_values),
                    redaction_values=redaction_values,
                )
        return results

    @classmethod
    def _run_llm_capability_checks(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
        capability_checks: Sequence[str],
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}
        for capability in capability_checks:
            if capability == "json":
                results[capability] = cls._run_json_capability_check(
                    litellm_module=litellm_module,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                )
            elif capability == "tools":
                results[capability] = cls._run_tools_capability_check(
                    litellm_module=litellm_module,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                )
            elif capability == "stream":
                results[capability] = cls._run_stream_capability_check(
                    litellm_module=litellm_module,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    redaction_values=redaction_values,
                )
            elif capability == "vision":
                results[capability] = cls._run_vision_capability_check(
                    litellm_module=litellm_module,
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                )
        return results

    @classmethod
    def _run_json_capability_check(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        try:
            started_at = time.perf_counter()
            response = litellm_module.completion(
                **cls._build_llm_capability_completion_kwargs(
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    messages=[{"role": "user", "content": 'Return exactly this JSON object: {"status":"ok"}'}],
                    max_tokens=64,
                    extra={"response_format": {"type": "json_object"}},
                )
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            content, parse_error_code, parse_error, parse_reason = cls._extract_llm_completion_content(response)
            if parse_error_code:
                return cls._build_llm_capability_result(
                    capability="json",
                    status="failed",
                    message="JSON capability check returned no parseable content",
                    error_code=parse_error_code,
                    retryable=False,
                    latency_ms=latency_ms,
                    details={"reason": parse_reason, "response_error": parse_error},
                )
            try:
                payload = json.loads(content)
            except ValueError:
                return cls._build_llm_capability_result(
                    capability="json",
                    status="failed",
                    message="JSON capability check returned non-JSON content",
                    error_code="format_error",
                    retryable=False,
                    latency_ms=latency_ms,
                    details={"reason": "non_json", "response_preview": content[:80]},
                )
            if not isinstance(payload, dict) or payload.get("status") != "ok":
                return cls._build_llm_capability_result(
                    capability="json",
                    status="failed",
                    message="JSON capability check returned unexpected JSON",
                    error_code="format_error",
                    retryable=False,
                    latency_ms=latency_ms,
                    details={"reason": "non_json", "response_preview": content[:80]},
                )
            return cls._build_llm_capability_result(
                capability="json",
                status="passed",
                message="JSON output capability check passed",
                latency_ms=latency_ms,
                details={"reason": "json_valid"},
            )
        except Exception as exc:  # broad-exception: optional_metadata - capture a failed JSON capability probe
            diagnostic = cls._classify_llm_capability_exception(exc, "json")
            return cls._build_llm_capability_result_from_diagnostic("json", diagnostic, str(exc))

    @classmethod
    def _run_tools_capability_check(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "dsa_probe_echo",
                    "description": "Return the provided text.",
                    "parameters": {
                        "type": "object",
                        "properties": {"text": {"type": "string"}},
                        "required": ["text"],
                    },
                },
            }
        ]
        try:
            started_at = time.perf_counter()
            response = litellm_module.completion(
                **cls._build_llm_capability_completion_kwargs(
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    messages=[{"role": "user", "content": "Call the dsa_probe_echo tool with text set to ok."}],
                    max_tokens=64,
                    extra={
                        "tools": tools,
                        "tool_choice": {"type": "function", "function": {"name": "dsa_probe_echo"}},
                    },
                )
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            tool_names = cls._extract_llm_tool_call_names(response)
            if "dsa_probe_echo" not in tool_names:
                return cls._build_llm_capability_result(
                    capability="tools",
                    status="failed",
                    message="Tool calling capability check did not return the probe tool call",
                    error_code="capability_unsupported",
                    retryable=False,
                    latency_ms=latency_ms,
                    details={"reason": "tool_calls_missing", "tool_calls": tool_names},
                )
            return cls._build_llm_capability_result(
                capability="tools",
                status="passed",
                message="Tool calling capability check passed",
                latency_ms=latency_ms,
                details={"reason": "tool_call_returned"},
            )
        except Exception as exc:  # broad-exception: optional_metadata - capture a failed tools capability probe
            diagnostic = cls._classify_llm_capability_exception(exc, "tools")
            return cls._build_llm_capability_result_from_diagnostic("tools", diagnostic, str(exc))

    @classmethod
    def _run_stream_capability_check(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        stream = None
        started_at = time.perf_counter()
        try:
            stream = litellm_module.completion(
                **cls._build_llm_capability_completion_kwargs(
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    messages=[{"role": "user", "content": "Reply with OK"}],
                    max_tokens=32,
                    extra={"stream": True},
                )
            )
            for index, chunk in enumerate(stream):
                content = cls._extract_llm_stream_chunk_content(chunk)
                if content:
                    latency_ms = int((time.perf_counter() - started_at) * 1000)
                    return cls._build_llm_capability_result(
                        capability="stream",
                        status="passed",
                        message="Streaming capability check passed",
                        latency_ms=latency_ms,
                        details={"reason": "stream_chunk_received"},
                    )
                if index + 1 >= cls._LLM_STREAM_CHUNK_LIMIT:
                    break
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            return cls._build_llm_capability_result(
                capability="stream",
                status="failed",
                message="Streaming capability check returned no content chunks",
                error_code="empty_response",
                retryable=False,
                latency_ms=latency_ms,
                details={"reason": "stream_no_content"},
            )
        except Exception as exc:  # broad-exception: optional_metadata - capture a failed stream capability probe
            diagnostic = cls._classify_llm_capability_exception(exc, "stream")
            return cls._build_llm_capability_result_from_diagnostic(
                "stream",
                diagnostic,
                sanitize_exception_chain(exc, redaction_values=redaction_values),
                redaction_values=redaction_values,
            )
        finally:
            close_stream = getattr(stream, "close", None)
            if callable(close_stream):
                try:
                    close_stream()
                except Exception as exc:  # broad-exception: cleanup - log stream cleanup failure without masking the result
                    log_safe_exception(
                        logger,
                        "LLM stream capability probe close failed",
                        exc,
                        error_code="llm_stream_capability_probe_close_failed",
                        level=logging.DEBUG,
                        redaction_values=redaction_values,
                    )

    @classmethod
    def _run_vision_capability_check(
        cls,
        *,
        litellm_module: Any,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        try:
            started_at = time.perf_counter()
            response = litellm_module.completion(
                **cls._build_llm_capability_completion_kwargs(
                    resolved_model=resolved_model,
                    selected_api_key=selected_api_key,
                    base_url=base_url,
                    timeout_seconds=timeout_seconds,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "Reply with OK if this image is visible."},
                                {"type": "image_url", "image_url": {"url": cls._LLM_CAPABILITY_PROBE_IMAGE}},
                            ],
                        }
                    ],
                    max_tokens=32,
                )
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            content, parse_error_code, parse_error, parse_reason = cls._extract_llm_completion_content(response)
            if parse_error_code:
                return cls._build_llm_capability_result(
                    capability="vision",
                    status="failed",
                    message="Vision capability check returned no parseable content",
                    error_code=parse_error_code,
                    retryable=False,
                    latency_ms=latency_ms,
                    details={"reason": parse_reason, "response_error": parse_error},
                )
            return cls._build_llm_capability_result(
                capability="vision",
                status="passed",
                message="Vision capability check passed",
                latency_ms=latency_ms,
                details={"reason": "vision_response_received", "response_preview": content[:80]},
            )
        except Exception as exc:  # broad-exception: optional_metadata - capture a failed vision capability probe
            diagnostic = cls._classify_llm_capability_exception(exc, "vision")
            return cls._build_llm_capability_result_from_diagnostic("vision", diagnostic, str(exc))

    @classmethod
    def _build_llm_capability_completion_kwargs(
        cls,
        *,
        resolved_model: str,
        selected_api_key: str,
        base_url: str,
        timeout_seconds: float,
        messages: List[Dict[str, Any]],
        max_tokens: int,
        extra: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        try:
            timeout = float(timeout_seconds)
        except (TypeError, ValueError):
            timeout = 10.0
        call_kwargs: Dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "max_tokens": max_tokens,
            "timeout": min(max(5.0, timeout), 10.0),
        }
        if selected_api_key:
            call_kwargs["api_key"] = selected_api_key
        if base_url.strip():
            call_kwargs["api_base"] = base_url.strip()
        if extra:
            call_kwargs.update(extra)
        call_kwargs = apply_litellm_generation_params(
            call_kwargs,
            resolved_model,
            0.0,
        )
        return call_kwargs

    @classmethod
    def _build_llm_capability_result(
        cls,
        *,
        capability: str,
        status: str,
        message: str,
        error_code: Optional[str] = None,
        retryable: bool = False,
        latency_ms: Optional[int] = None,
        details: Optional[Dict[str, Any]] = None,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        return {
            "status": status,
            "message": cls._sanitize_llm_error_text(message, redaction_values=redaction_values),
            "error_code": error_code,
            "stage": f"capability_{capability}",
            "retryable": retryable,
            "latency_ms": latency_ms,
            "details": cls._sanitize_llm_details(
                {"capability": capability, **(details or {})},
                redaction_values=redaction_values,
            ),
        }

    @classmethod
    def _build_llm_capability_result_from_diagnostic(
        cls,
        capability: str,
        diagnostic: _LLMDiagnostic,
        error: str,
        *,
        redaction_values: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        details = cls._merge_llm_diagnostic_details({"error": error}, diagnostic)
        return cls._build_llm_capability_result(
            capability=capability,
            status="failed",
            message=diagnostic.message,
            error_code=diagnostic.error_code,
            retryable=diagnostic.retryable,
            details=details,
            redaction_values=redaction_values,
        )

    @staticmethod
    def _extract_llm_tool_call_names(response: Any) -> List[str]:
        choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
        if not choices:
            return []
        choice = choices[0]
        message = choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
        if isinstance(message, dict):
            tool_calls = message.get("tool_calls")
        else:
            tool_calls = getattr(message, "tool_calls", None) if message is not None else None
        names: List[str] = []
        for call in tool_calls or []:
            function = call.get("function") if isinstance(call, dict) else getattr(call, "function", None)
            if isinstance(function, dict):
                name = str(function.get("name") or "").strip()
            else:
                name = str(getattr(function, "name", "") or "").strip()
            if name:
                names.append(name)
        return names

    @staticmethod
    def _extract_llm_stream_chunk_content(chunk: Any) -> str:
        choices = chunk.get("choices") if isinstance(chunk, dict) else getattr(chunk, "choices", None)
        if not choices:
            return ""
        choice = choices[0]
        delta = choice.get("delta") if isinstance(choice, dict) else getattr(choice, "delta", None)
        message = choice.get("message") if isinstance(choice, dict) else getattr(choice, "message", None)
        for container in (delta, message):
            if not container:
                continue
            content = container.get("content") if isinstance(container, dict) else getattr(container, "content", None)
            if content:
                return str(content)
        content = choice.get("text") if isinstance(choice, dict) else getattr(choice, "text", None)
        return str(content or "")

    @classmethod
    def _classify_llm_capability_exception(cls, exc: Exception, capability: str) -> _LLMDiagnostic:
        text = str(exc).lower()
        capability_tokens = {
            "json": ("response_format", "json_object", "json mode"),
            "tools": ("tool_choice", "tools", "function calling", "tool call"),
            "stream": ("stream", "streaming"),
            "vision": ("image", "image_url", "vision", "multimodal", "multi-modal"),
        }
        unsupported_markers = (
            "unsupported",
            "not support",
            "not supported",
            "unknown parameter",
            "unrecognized parameter",
            "invalid parameter",
            "unexpected keyword",
            "not allowed",
        )
        has_unsupported_marker = any(marker in text for marker in unsupported_markers)
        has_capability_token = any(token in text for token in capability_tokens.get(capability, ()))
        if has_unsupported_marker and (has_capability_token or capability in text):
            return _LLMDiagnostic(
                "capability_unsupported",
                False,
                f"LLM channel does not support {capability} capability",
                "capability_unsupported",
                {"capability": capability},
            )
        return cls._classify_llm_exception(exc)
