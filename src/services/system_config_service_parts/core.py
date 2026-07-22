"""Core methods for the system-config facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.system_config_service import (
        Any,
        Callable,
        Config,
        ConfigConflictService,
        ConfigManager,
        ConfigValidationError,
        Dict,
        EffectiveConfigResolver,
        GenerationBackendStatusService,
        List,
        Optional,
        Sequence,
        Set,
        SystemConfigService,
        Tuple,
        _RuntimeConfigTransaction,
        build_schema_response,
        canonicalize_hermes_base_url,
        get_category_definitions,
        get_field_definition,
        get_registered_field_keys,
        get_runtime_config,
        is_masked_secret_placeholder,
        is_reserved_hermes_name,
        llm_channel_map,
        log_safe_exception,
        logger,
        logging,
        normalize_llm_channel_model,
        os,
        parse_env_bool,
        sanitize_exception_chain,
    )


class _SystemConfigCoreMethods:
    def __init__(
        self,
        manager: Optional[ConfigManager] = None,
        runtime_scheduler: Optional[Any] = None,
        runtime_config_provider: Optional[Callable[[], Config]] = None,
    ):
        self._manager = manager or ConfigManager()
        self._conflict = ConfigConflictService(self._manager)
        self._runtime_scheduler = runtime_scheduler
        # Keep the provider rather than a Config object so Config.reset_instance()
        # is reflected on the next read.
        self._runtime_config_provider = runtime_config_provider or get_runtime_config
        self._runtime_config_transaction = _RuntimeConfigTransaction(
            manager=self._manager,
            reload_runtime_singletons=lambda: self._reload_runtime_singletons(),
        )

    def get_schema(self) -> Dict[str, Any]:
        """Return grouped schema metadata for UI rendering."""
        return build_schema_response()

    @staticmethod
    def _reload_runtime_singletons() -> None:
        """Reset runtime singleton services after config reload."""
        from src.agent.tools.data_tools import reset_fetcher_manager
        from src.search_service import reset_search_service

        reset_fetcher_manager()
        reset_search_service()

    @classmethod
    def _build_display_config_map(cls, raw_config_map: Dict[str, str]) -> Dict[str, str]:
        return EffectiveConfigResolver.build_display_config_map(raw_config_map)

    @classmethod
    def _build_runtime_display_config_map(cls, saved_config_map: Dict[str, str]) -> Dict[str, str]:
        return EffectiveConfigResolver.build_runtime_display_config_map(saved_config_map)

    def get_config(self, include_schema: bool = True, mask_token: str = "******") -> Dict[str, Any]:
        """Return display config values with mask metadata for server-masked fields."""
        saved_config_map = self._build_display_config_map(self._manager.read_config_map())
        runtime_config_map = self._build_runtime_display_config_map(saved_config_map)
        config_map = {
            **runtime_config_map,
            **saved_config_map,
        }
        configured_notification_channels = self._detect_configured_notification_channels()
        registered_keys = set(get_registered_field_keys())
        all_keys = set(config_map.keys()) | registered_keys
        if include_schema:
            all_keys = EffectiveConfigResolver.get_schema_config_keys(config_map, registered_keys)

        category_orders = {
            item["category"]: item["display_order"]
            for item in get_category_definitions()
        }

        schema_by_key: Dict[str, Dict[str, Any]] = {
            key: get_field_definition(key, config_map.get(key, ""))
            for key in all_keys
        }

        items: List[Dict[str, Any]] = []
        for key in all_keys:
            raw_value_exists = key in saved_config_map
            raw_value = config_map.get(key, "")
            field_schema = schema_by_key[key]
            display_value = EffectiveConfigResolver.resolve_display_value(
                raw_value, field_schema, raw_value_exists
            )
            is_masked = False
            if field_schema.get("is_sensitive", False) and display_value:
                display_value = mask_token
                is_masked = True
            item: Dict[str, Any] = {
                "key": key,
                "value": display_value,
                "raw_value_exists": raw_value_exists,
                "is_masked": is_masked,
            }
            if include_schema:
                item["schema"] = field_schema
            items.append(item)

        items.sort(
            key=lambda item: (
                category_orders.get(schema_by_key[item["key"]].get("category", "uncategorized"), 999),
                schema_by_key[item["key"]].get("display_order", 9999),
                item["key"],
            )
        )

        return {
            "config_version": self._manager.get_config_version(),
            "mask_token": mask_token,
            "items": items,
            "configured_notification_channels": configured_notification_channels,
            "updated_at": self._manager.get_updated_at(),
        }

    def _detect_configured_notification_channels(self) -> List[str]:
        """Return channels from the live runtime Config without exposing credentials."""
        from src.notification import NotificationService

        config = self._runtime_config_provider()
        return [
            channel.value
            for channel in NotificationService.detect_configured_channels(config)
        ]

    def validate(self, items: Sequence[Dict[str, str]], mask_token: str = "******") -> Dict[str, Any]:
        """Validate submitted items without writing to `.env`."""
        issues = self._collect_issues(items=items, mask_token=mask_token)
        valid = not any(issue["severity"] == "error" for issue in issues)
        return {
            "valid": valid,
            "issues": issues,
        }

    def test_notification_channel(
        self,
        *,
        channel: str,
        items: Sequence[Dict[str, str]],
        mask_token: str = "******",
        title: str = "StockPulse 通知测试",
        content: str = "这是一条来自 StockPulse Web 设置页的通知测试消息。",
        timeout_seconds: float = 20.0,
    ) -> Dict[str, Any]:
        """Send one real notification test without persisting submitted values."""
        normalized_channel = (channel or "").strip().lower()
        if normalized_channel not in self._NOTIFICATION_TEST_CHANNELS:
            raise ValueError(f"Unsupported notification channel: {channel}")

        effective_map = self._build_notification_test_effective_map(
            items=items,
            mask_token=mask_token,
        )
        missing = self._get_missing_notification_test_keys(normalized_channel, effective_map)
        if missing:
            return self._build_notification_test_result(
                success=False,
                message=f"通知渠道配置不完整，缺少: {', '.join(missing)}",
                error_code="config_missing",
                stage="config_validation",
                retryable=False,
                latency_ms=None,
                attempts=[],
            )
        invalid_message = self._get_invalid_notification_test_config_message(
            normalized_channel,
            effective_map,
        )
        if invalid_message:
            return self._build_notification_test_result(
                success=False,
                message=invalid_message,
                error_code="config_invalid",
                stage="config_validation",
                retryable=False,
                latency_ms=None,
                attempts=[],
            )

        config = self._build_notification_config(effective_map)
        try:
            return self._dispatch_notification_test(
                channel=normalized_channel,
                config=config,
                effective_map=effective_map,
                title=title.strip(),
                content=content.strip(),
                timeout_seconds=float(timeout_seconds),
            )
        except Exception as exc:  # broad-exception: fallback_recorded - return a sanitized notification test result
            redaction_values = [
                value
                for key, value in effective_map.items()
                if get_field_definition(key, value_hint=str(value)).get("is_sensitive")
            ]
            safe_error = sanitize_exception_chain(
                exc,
                redaction_values=redaction_values,
            )
            log_safe_exception(
                logger,
                "Notification channel test failed",
                exc,
                error_code="notification_channel_test_failed",
                level=logging.WARNING,
                context={"channel": normalized_channel},
                redaction_values=redaction_values,
            )
            error_code, retryable = self._classify_notification_exception(exc)
            return self._build_notification_test_result(
                success=False,
                message=safe_error,
                error_code=error_code,
                stage="notification_send",
                retryable=retryable,
                latency_ms=None,
                attempts=[
                    {
                        "channel": normalized_channel,
                        "success": False,
                        "message": safe_error,
                        "target": self._resolve_notification_test_target(normalized_channel, effective_map),
                        "error_code": error_code,
                        "stage": "notification_send",
                        "retryable": retryable,
                        "latency_ms": None,
                    }
                ],
            )

    def get_setup_status(self) -> Dict[str, Any]:
        """Return read-only first-run setup status without mutating runtime state."""
        effective_map = self._build_setup_effective_config_map()
        llm_check = self._build_setup_primary_llm_check(effective_map)
        agent_check = self._build_setup_agent_llm_check(effective_map, llm_check)
        checks = [
            llm_check,
            agent_check,
            self._build_setup_stock_list_check(effective_map),
            self._build_setup_notification_check(effective_map),
            self._build_setup_storage_check(effective_map),
        ]

        required_missing = [
            check["key"]
            for check in checks
            if check["required"] and check["status"] == "needs_action"
        ]
        smoke_blocking_missing = [
            check["key"]
            for check in checks
            if check["key"] in {"llm_primary", "stock_list"}
            and check["status"] == "needs_action"
        ]
        return {
            "is_complete": not required_missing,
            "ready_for_smoke": not smoke_blocking_missing,
            "required_missing_keys": required_missing,
            "next_step_key": required_missing[0] if required_missing else None,
            "checks": checks,
        }

    def get_llm_config_mode_status(self) -> Dict[str, Any]:
        """Return which model config source is requested vs effective."""
        saved_config_map = self._build_display_config_map(self._manager.read_config_map())
        runtime_config_map = self._build_runtime_display_config_map(saved_config_map)
        effective_map = {**runtime_config_map, **saved_config_map}
        return self._resolve_llm_config_mode_status(effective_map)

    def get_available_models(
        self, items: Optional[Sequence[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """Return the model routes declared by currently-enabled sources.

        Each entry pairs the canonical backend route (what LITELLM_MODEL etc.
        must store) with a display name and its owning connection/provider, so
        Web model selectors let users pick a display name while the system keeps
        the exact route. The route set is authoritative (matches validation);
        connection/provider are best-effort grouping metadata.
        """
        saved_config_map = self._build_display_config_map(self._manager.read_config_map())
        runtime_config_map = self._build_runtime_display_config_map(saved_config_map)
        effective_map = {**runtime_config_map, **saved_config_map}
        if items:
            for item in items:
                key = str(item.get("key", "")).strip().upper()
                if key:
                    effective_map[key] = str(item.get("value", ""))

        yaml_routes = SystemConfigService._collect_yaml_models_from_map(effective_map)

        # Resolve a connection to its authoritative catalog provider so selectors
        # can group models by provider without a second frontend list.
        from src.llm.model_ref import canonicalize_connection_id, encode_model_ref
        from src.llm.provider_catalog import get_provider_catalog

        provider_label_by_id = {
            str(entry["id"]).lower(): str(entry["label"]) for entry in get_provider_catalog()
        }

        def _resolve_provider(connection_name: str) -> Tuple[str, str]:
            _provider, pid, _explicit = self._resolve_connection_provider(
                effective_map,
                connection_name,
            )
            if pid not in provider_label_by_id:
                pid = "custom"
            return pid, provider_label_by_id.get(pid, pid)

        # YAML aliases do not expose a Connection identity. Preserve their route
        # contract and mark the route itself as the legacy-compatible model_ref.
        if yaml_routes:
            return {
                "models": [
                    {
                        "model_ref": route,
                        "route": route,
                        "display": route,
                        "connection": None,
                        "connection_id": None,
                        "connection_name": None,
                        "provider": None,
                        "provider_id": None,
                        "provider_label": None,
                        "available": True,
                    }
                    for route in dict.fromkeys(yaml_routes)
                ]
            }

        models: List[Dict[str, Any]] = []
        for raw_name in (effective_map.get("LLM_CHANNELS") or "").split(","):
            name = raw_name.strip()
            if not name:
                continue
            connection_id = canonicalize_connection_id(name)
            prefix = f"LLM_{name.upper()}"
            enabled_raw = effective_map.get(f"{prefix}_ENABLED")
            if name.lower() == "anspire" and not (enabled_raw or "").strip():
                enabled_raw = effective_map.get("ANSPIRE_LLM_ENABLED")
            if not parse_env_bool(enabled_raw, default=True):
                continue
            protocol, base_url = self._resolve_connection_transport(
                effective_map,
                name,
            )
            protocol = protocol or "openai"
            provider_id, provider_label = _resolve_provider(name)
            connection_name = (
                effective_map.get(f"{prefix}_DISPLAY_NAME") or name
            ).strip()
            seen_routes: Set[str] = set()
            for raw_model in (effective_map.get(f"{prefix}_MODELS") or "").split(","):
                model = raw_model.strip()
                if not model:
                    continue
                route = normalize_llm_channel_model(model, protocol, base_url)
                if not route or route in seen_routes:
                    continue
                seen_routes.add(route)
                models.append({
                    "model_ref": encode_model_ref(connection_id, route),
                    "route": route,
                    "display": model,
                    "connection": connection_id,
                    "connection_id": connection_id,
                    "connection_name": connection_name,
                    # `provider` stays the protocol for back-compat; provider_id/label
                    # are the authoritative Catalog Provider for display/grouping.
                    "provider": protocol,
                    "provider_id": provider_id,
                    "provider_label": provider_label,
                    "available": True,
                })
        return {"models": models}

    @staticmethod
    def _resolve_connection_provider(
        effective_map: Dict[str, str],
        connection_name: str,
    ) -> Tuple[Optional[Dict[str, Any]], str, bool]:
        return llm_channel_map.resolve_connection_provider(effective_map, connection_name)

    @staticmethod
    def _resolve_connection_transport(
        effective_map: Dict[str, str],
        connection_name: str,
    ) -> Tuple[str, str]:
        return llm_channel_map.resolve_connection_transport(effective_map, connection_name)

    @staticmethod
    def _resolve_request_provider(
        *,
        provider_id: Optional[str],
        protocol: str,
        base_url: str,
    ) -> Tuple[Optional[Dict[str, Any]], str, str, Optional[Dict[str, Any]]]:
        """Apply explicit Catalog identity to an unsaved Connection request."""
        normalized_provider_id = str(provider_id or "").strip().lower()
        if not normalized_provider_id:
            return None, protocol, base_url, None

        from src.llm.provider_catalog import get_provider

        provider = get_provider(normalized_provider_id)
        if provider is None:
            return None, protocol, base_url, {
                "key": "provider_id",
                "code": "invalid_provider",
                "message": "The model connection references an unknown Provider",
                "severity": "error",
                "expected": "provider id from the model provider catalog",
                "actual": normalized_provider_id,
            }

        if not provider["is_custom"]:
            protocol = str(provider["protocol"])
            if not base_url.strip():
                base_url = str(provider["default_base_url"])
        return provider, protocol, base_url, None

    _LEGACY_LLM_PROVIDER_KEYS = (
        "OPENAI_API_KEY", "OPENAI_API_KEYS", "ANTHROPIC_API_KEY", "ANTHROPIC_API_KEYS",
        "GEMINI_API_KEY", "GEMINI_API_KEYS", "DEEPSEEK_API_KEY", "DEEPSEEK_API_KEYS",
        "AIHUBMIX_KEY",
    )

    @classmethod
    def _resolve_llm_config_mode_status(cls, effective_map: Dict[str, str]) -> Dict[str, Any]:
        requested = (effective_map.get("LLM_CONFIG_MODE") or "").strip().lower() or "auto"
        if requested not in ("auto", "channels", "yaml", "legacy"):
            requested = "auto"
        has_yaml = bool((effective_map.get("LITELLM_CONFIG") or "").strip())
        has_channels = bool((effective_map.get("LLM_CHANNELS") or "").strip())
        has_legacy = any((effective_map.get(k) or "").strip() for k in cls._LEGACY_LLM_PROVIDER_KEYS)
        detected = [
            name for name, present in (("yaml", has_yaml), ("channels", has_channels), ("legacy", has_legacy))
            if present
        ]

        issues: List[Dict[str, Any]] = []
        if requested == "auto":
            effective = next((cand for cand in ("yaml", "channels", "legacy") if cand in detected), None)
        else:
            effective = requested
            if requested not in detected:
                issues.append({
                    "key": "LLM_CONFIG_MODE",
                    "code": "forced_mode_no_config",
                    "severity": "warning",
                    "message": f"LLM_CONFIG_MODE={requested} is active but no {requested} configuration was found.",
                    "expected": f"configured {requested} source",
                    "actual": ",".join(detected) or "none",
                })

        overridden = [source for source in detected if source != effective]
        return {
            "requested_mode": requested,
            "effective_mode": effective,
            "detected_sources": detected,
            "overridden_sources": overridden,
            "issues": issues,
        }

    # (channel, protocol, base_url_key, api_key_fields, model_field, default_base_url, default_model)
    _LEGACY_CHANNEL_SPECS = (
        ("openai", "openai", "OPENAI_BASE_URL", ("OPENAI_API_KEYS", "OPENAI_API_KEY"), "OPENAI_MODEL", "", "gpt-5.5"),
        ("anthropic", "anthropic", None, ("ANTHROPIC_API_KEYS", "ANTHROPIC_API_KEY"), "ANTHROPIC_MODEL", "", "claude-sonnet-4-6"),
        ("gemini", "gemini", None, ("GEMINI_API_KEYS", "GEMINI_API_KEY"), "GEMINI_MODEL", "", "gemini-3.1-pro-preview"),
        ("deepseek", "deepseek", None, ("DEEPSEEK_API_KEYS", "DEEPSEEK_API_KEY"), None, "", "deepseek-chat"),
        ("aihubmix", "openai", None, ("AIHUBMIX_KEY",), None, "https://aihubmix.com/v1", "gpt-5.5"),
    )

    @classmethod
    def _build_legacy_channels_migration(
        cls, raw_map: Dict[str, str]
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """Turn detected legacy provider keys into channel update items."""
        items: List[Dict[str, str]] = []
        channels: List[Dict[str, str]] = []
        for name, protocol, base_url_key, api_key_fields, model_field, default_base_url, default_model in cls._LEGACY_CHANNEL_SPECS:
            api_key = ""
            for field_name in api_key_fields:
                api_key = (raw_map.get(field_name) or "").strip()
                if api_key:
                    break
            if not api_key:
                continue
            prefix = f"LLM_{name.upper()}"
            base_url = ((raw_map.get(base_url_key) if base_url_key else "") or "").strip() or default_base_url
            model = ((raw_map.get(model_field) if model_field else "") or "").strip() or default_model
            items.append({"key": f"{prefix}_PROVIDER", "value": name})
            items.append({"key": f"{prefix}_PROTOCOL", "value": protocol})
            if base_url:
                items.append({"key": f"{prefix}_BASE_URL", "value": base_url})
            items.append({"key": f"{prefix}_API_KEY", "value": api_key})
            items.append({"key": f"{prefix}_MODELS", "value": model})
            items.append({"key": f"{prefix}_ENABLED", "value": "true"})
            channels.append({"name": name, "protocol": protocol, "base_url": base_url, "model": model})
        if channels:
            items.insert(0, {"key": "LLM_CHANNELS", "value": ",".join(entry["name"] for entry in channels)})
            items.append({"key": "LLM_CONFIG_MODE", "value": "channels"})
        return items, channels

    def preview_legacy_channels_migration(self) -> Dict[str, Any]:
        """Return a redacted preview of the Legacy -> Channels migration."""
        raw_map = {str(key).upper(): value for key, value in self._manager.read_config_map().items()}
        _items, channels = self._build_legacy_channels_migration(raw_map)
        return {"channels": channels}

    def apply_legacy_channels_migration(
        self,
        config_version: str,
        mask_token: str = "******",
        validate_connectivity: bool = False,
        connectivity_timeout_seconds: float = 20.0,
        actor: str = "system_config_service",
    ) -> Dict[str, Any]:
        """Copy detected legacy provider config into channels and switch mode."""
        raw_map = {str(key).upper(): value for key, value in self._manager.read_config_map().items()}
        items, channels = self._build_legacy_channels_migration(raw_map)
        if not channels:
            raise ConfigValidationError(issues=[{
                "key": "LLM_CHANNELS",
                "code": "no_legacy_config",
                "severity": "error",
                "message": "No legacy provider configuration was found to migrate.",
                "expected": "at least one legacy provider key",
                "actual": "none",
            }])
        return self.update(
            config_version=config_version,
            items=items,
            mask_token=mask_token,
            validate_connectivity=validate_connectivity,
            connectivity_timeout_seconds=connectivity_timeout_seconds,
            actor=actor,
        )

    def get_generation_backend_status(self) -> Dict[str, Any]:
        """Return cheap generation backend status for saved/runtime config only."""
        effective_map = self._build_generation_backend_base_map()
        service = GenerationBackendStatusService(
            effective_map=effective_map,
            validation_issues=self._collect_generation_backend_issues_from_map(effective_map),
        )
        return service.get_status()

    def preview_generation_backend_status(
        self,
        *,
        items: Sequence[Dict[str, str]],
        mask_token: str = "******",
    ) -> Dict[str, Any]:
        """Return cheap generation backend status for unsaved settings draft."""
        issues = self._collect_generation_backend_issues(items=items, mask_token=mask_token)
        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            raise ConfigValidationError(issues=errors)
        effective_map = self._build_generation_backend_effective_map(
            items=items,
            mask_token=mask_token,
        )
        service = GenerationBackendStatusService(
            effective_map=effective_map,
            validation_issues=issues,
        )
        return service.get_status()

    def test_generation_backend(
        self,
        *,
        backend_id: Optional[str] = None,
        mode: str = "json",
        items: Sequence[Dict[str, str]] = (),
        mask_token: str = "******",
        timeout_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Run an explicit generation backend smoke test without persisting config."""
        issues = self._collect_generation_backend_issues(items=items, mask_token=mask_token)
        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            raise ConfigValidationError(issues=errors)
        effective_map = self._build_generation_backend_effective_map(
            items=items,
            mask_token=mask_token,
        )
        service = GenerationBackendStatusService(
            effective_map=effective_map,
            validation_issues=issues,
        )
        return service.smoke_test(
            backend_id=backend_id,
            mode=mode,
            timeout_seconds=timeout_seconds,
        )

    def export_env(self) -> Dict[str, Any]:
        """Return the raw active `.env` content for backup."""
        if self._manager.env_path.exists():
            content = self._manager.env_path.read_text(encoding="utf-8")
        else:
            content = ""

        return {
            "content": content,
            "config_version": self._manager.get_config_version(),
            "updated_at": self._manager.get_updated_at(),
        }

    def export_desktop_env(self) -> Dict[str, Any]:
        """Return the raw active `.env` content for desktop backup compatibility."""
        return self.export_env()

    def import_env(
        self,
        *,
        config_version: str,
        content: str,
        reload_now: bool = True,
        validate_connectivity: bool = False,
        connectivity_timeout_seconds: float = 20.0,
        actor: str = "system_config_service",
    ) -> Dict[str, Any]:
        """Merge imported `.env` assignments into the active config."""
        self._conflict.guard_version(config_version)

        updates = self._parse_imported_env_content(content)
        return self.update(
            config_version=config_version,
            items=updates,
            mask_token="__DSA_IMPORT_LITERAL_MASK__",
            reload_now=reload_now,
            validate_connectivity=validate_connectivity,
            connectivity_timeout_seconds=connectivity_timeout_seconds,
            actor=actor,
        )

    def import_desktop_env(
        self,
        *,
        config_version: str,
        content: str,
        reload_now: bool = True,
    ) -> Dict[str, Any]:
        """Merge imported `.env` assignments for desktop backup compatibility."""
        return self.import_env(
            config_version=config_version,
            content=content,
            reload_now=reload_now,
        )

    def _resolve_hermes_saved_secret(
        self,
        *,
        channel_name: str,
        protocol: str,
        base_url: str,
        submitted_api_key: str,
        use_saved_secret: bool,
        stage: str,
    ) -> Tuple[Optional[str], Dict[str, Any], Set[str]]:
        """Resolve a saved Hermes key only when the submitted endpoint is unchanged."""

        redaction_values = self._build_redaction_values(submitted_api_key)
        if not use_saved_secret:
            return submitted_api_key, {}, redaction_values

        if not is_reserved_hermes_name(channel_name):
            return None, self._build_llm_channel_result(
                success=False,
                message="Saved secret scope mismatch",
                error="Saved Hermes secret can only be used with the reserved hermes channel",
                stage=stage,
                error_code="saved_secret_scope_mismatch",
                retryable=False,
                details={"reason": "channel_identity_mismatch"},
                resolved_protocol=None,
                models=[] if stage == "model_discovery" else None,
                latency_ms=None,
                redaction_values=redaction_values,
            ), redaction_values

        saved_map = self._manager.read_config_map()
        saved_key = (saved_map.get("LLM_HERMES_API_KEY") or "").strip()
        if not saved_key or is_masked_secret_placeholder(saved_key):
            error_code = (
                "runtime_secret_not_reusable"
                if is_masked_secret_placeholder(saved_key) or (os.environ.get("LLM_HERMES_API_KEY") or "").strip()
                else "missing_saved_secret"
            )
            return None, self._build_llm_channel_result(
                success=False,
                message=(
                    "Runtime Hermes secret is not reusable"
                    if error_code == "runtime_secret_not_reusable"
                    else "Missing saved Hermes secret"
                ),
                error=(
                    "Runtime-injected LLM_HERMES_API_KEY cannot be reused from the settings test flow"
                    if error_code == "runtime_secret_not_reusable"
                    else "No saved LLM_HERMES_API_KEY is available for this endpoint"
                ),
                stage=stage,
                error_code=error_code,
                retryable=False,
                details={"reason": error_code},
                resolved_protocol=None,
                models=[] if stage == "model_discovery" else None,
                latency_ms=None,
                redaction_values=redaction_values,
            ), redaction_values

        redaction_values.update(self._build_redaction_values(saved_key))
        saved_protocol = (saved_map.get("LLM_HERMES_PROTOCOL") or "openai").strip()
        saved_base_url = (saved_map.get("LLM_HERMES_BASE_URL") or "").strip()
        try:
            submitted_protocol = (protocol or "openai").strip().lower() or "openai"
            saved_protocol_canonical = (saved_protocol or "openai").strip().lower() or "openai"
            submitted_base = canonicalize_hermes_base_url(base_url)
            saved_base = canonicalize_hermes_base_url(saved_base_url)
        except ValueError as exc:
            return None, self._build_llm_channel_result(
                success=False,
                message="Saved secret scope mismatch",
                error=str(exc),
                stage=stage,
                error_code="saved_secret_scope_mismatch",
                retryable=False,
                details={"reason": "invalid_hermes_endpoint"},
                resolved_protocol=None,
                models=[] if stage == "model_discovery" else None,
                latency_ms=None,
                redaction_values=redaction_values,
            ), redaction_values

        if submitted_protocol != saved_protocol_canonical or submitted_base != saved_base:
            return None, self._build_llm_channel_result(
                success=False,
                message="Saved secret scope mismatch",
                error="Hermes endpoint changed; re-enter LLM_HERMES_API_KEY before testing",
                stage=stage,
                error_code="saved_secret_scope_mismatch",
                retryable=False,
                details={
                    "reason": "endpoint_mismatch",
                    "submitted_base_url": submitted_base,
                    "saved_base_url": saved_base,
                },
                resolved_protocol=submitted_protocol,
                models=[] if stage == "model_discovery" else None,
                latency_ms=None,
                redaction_values=redaction_values,
            ), redaction_values

        return saved_key, {}, redaction_values

    def _validate_hermes_submitted_secret(
        self,
        *,
        api_key: str,
        use_saved_secret: bool,
        stage: str,
        models: Optional[List[str]] = None,
        capability_checks: Sequence[str] = (),
        redaction_values: Optional[Set[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Reject Hermes secret shapes that must not reach an outbound request."""

        secret = (api_key or "").strip()
        redactions = set(redaction_values or set())
        redactions.update(self._build_redaction_values(secret))
        if is_masked_secret_placeholder(secret):
            return self._build_llm_channel_result(
                success=False,
                message="Runtime Hermes secret is not reusable",
                error=(
                    "Runtime-injected Hermes secret is masked and cannot be reused by "
                    "test/discovery. Re-enter the key or save it to .env."
                ),
                stage=stage,
                error_code="runtime_secret_not_reusable",
                retryable=False,
                details={"reason": "runtime_secret_not_reusable"},
                resolved_protocol=None,
                models=models if stage == "model_discovery" else None,
                latency_ms=None,
                capability_results=(
                    self._build_skipped_capability_results(
                        capability_checks,
                        "base_test_failed",
                        "Skipped because the base channel test did not pass",
                        redaction_values=redactions,
                    )
                    if capability_checks
                    else None
                ),
                redaction_values=redactions,
            )
        if "," in secret:
            return self._build_llm_channel_result(
                success=False,
                message="Hermes API key is invalid",
                error="Hermes Phase 3 only supports a single LLM_HERMES_API_KEY",
                stage=stage,
                error_code="invalid_config",
                retryable=False,
                details={
                    "issue_key": "LLM_HERMES_API_KEY",
                    "issue_code": "multiple_api_keys",
                    "reason": "multiple_api_keys",
                },
                resolved_protocol=None,
                models=models if stage == "model_discovery" else None,
                latency_ms=None,
                capability_results=(
                    self._build_skipped_capability_results(
                        capability_checks,
                        "base_test_failed",
                        "Skipped because the base channel test did not pass",
                        redaction_values=redactions,
                    )
                    if capability_checks
                    else None
                ),
                redaction_values=redactions,
            )
        return None
