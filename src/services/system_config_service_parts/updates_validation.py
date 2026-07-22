"""Updates Validation methods for the system-config facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.system_config_service import (
        Any,
        Config,
        ConfigImportError,
        ConfigRollbackError,
        ConfigValidationError,
        ConfigVersionMismatchError,
        Dict,
        LITELLM_BACKEND_ID,
        List,
        Optional,
        Sequence,
        Set,
        SystemConfigService,
        Tuple,
        _LastGoodConfigUnavailableError,
        _RuntimeConfigActivationError,
        _build_auth_rollback_issue,
        _build_connectivity_failure_issue,
        _log_config_audit,
        canonicalize_llm_channel_protocol,
        evaluate_config_conditions,
        get_contract_field_definitions,
        get_field_definition,
        io,
        is_masked_secret_placeholder,
        json,
        log_safe_exception,
        logger,
        normalize_backend_id,
        normalize_news_strategy_profile,
        re,
        resolve_gotify_message_endpoint,
        resolve_news_window_days,
        resolve_ntfy_endpoint,
        setup_env,
        urlparse,
        validate_notification_timezone,
    )


class _SystemConfigUpdateMethods:
    def update(
        self,
        config_version: str,
        items: Sequence[Dict[str, str]],
        mask_token: str = "******",
        reload_now: bool = True,
        validate_connectivity: bool = False,
        connectivity_timeout_seconds: float = 20.0,
        actor: str = "system_config_service",
    ) -> Dict[str, Any]:
        """Validate, persist, and transactionally activate configuration updates."""
        submitted_keys = {item["key"].upper() for item in items}
        self._conflict.guard_version(config_version)

        issues = self._collect_issues(items=items, mask_token=mask_token)
        errors = [issue for issue in issues if issue["severity"] == "error"]
        if errors:
            _log_config_audit(
                actor=actor,
                operation="update",
                outcome="rejected_validation",
                keys=submitted_keys,
                config_version=config_version,
            )
            raise ConfigValidationError(issues=errors)

        if validate_connectivity:
            probe_result = self.test_generation_backend(
                items=items,
                mask_token=mask_token,
                timeout_seconds=connectivity_timeout_seconds,
            )
            if not probe_result.get("success", False):
                _log_config_audit(
                    actor=actor,
                    operation="update",
                    outcome="rejected_connectivity",
                    keys=submitted_keys,
                    config_version=config_version,
                )
                raise ConfigValidationError(
                    issues=[_build_connectivity_failure_issue(probe_result)]
                )

        with self._runtime_config_transaction.lock:
            previous_map = self._manager.read_config_map()
            updates: List[Tuple[str, str]] = []
            sensitive_keys: Set[str] = set()
            for item in items:
                key = item["key"].upper()
                value = item["value"]
                field_schema = get_field_definition(key, value)
                normalized_value = self._normalize_value_for_storage(value, field_schema)
                updates.append((key, normalized_value))
                if bool(field_schema.get("is_sensitive", False)):
                    sensitive_keys.add(key)

            redaction_values = tuple(
                value for key, value in updates if key in sensitive_keys
            )
            try:
                updated_keys, skipped_masked_keys, new_version = self._manager.apply_updates(
                    updates=updates,
                    sensitive_keys=sensitive_keys,
                    mask_token=mask_token,
                    expected_version=config_version,
                )
            except ConfigVersionMismatchError as exc:
                _log_config_audit(
                    actor=actor,
                    operation="update",
                    outcome="version_conflict",
                    keys=submitted_keys,
                    config_version=exc.current_version,
                )
                raise self._conflict.as_conflict(exc) from exc

            warnings: List[str] = []
            reload_triggered = False
            if reload_now:
                try:
                    warnings.extend(
                        self._runtime_config_transaction.activate_persisted_candidate(
                            redaction_values=redaction_values,
                        )
                    )
                    reload_triggered = True
                except _RuntimeConfigActivationError as exc:
                    log_safe_exception(
                        logger,
                        "Configuration activation failed",
                        exc,
                        error_code="configuration_activation_failed",
                        redaction_values=redaction_values,
                        context={
                            "rollback_succeeded": exc.rollback_succeeded,
                            "updated_keys": sorted(updated_keys),
                        },
                    )
                    _log_config_audit(
                        actor=actor,
                        operation="update",
                        outcome=(
                            "rolled_back_activation_failure"
                            if exc.rollback_succeeded
                            else "rollback_failed"
                        ),
                        keys=submitted_keys,
                        config_version=self._manager.get_config_version(),
                    )
                    if not exc.rollback_succeeded:
                        raise RuntimeError(
                            "Configuration activation and restoration failed"
                        ) from exc
                    raise ConfigValidationError(issues=[{
                        "key": "RUNTIME_CONFIG",
                        "code": "runtime_activation_failed",
                        "severity": "error",
                        "message": (
                            "The candidate configuration could not be activated; "
                            "the previous runtime configuration was restored."
                        ),
                        "expected": "loadable runtime configuration",
                        "actual": "activation failed",
                        "details": {
                            "rollback_succeeded": True,
                            "current_config_version": self._manager.get_config_version(),
                        },
                    }]) from exc

            warnings.extend(
                self._build_explainability_warnings(
                    submitted_keys=submitted_keys,
                    reload_now=reload_now,
                )
            )
            update_map = dict(updates)
            warnings.extend(
                self._build_runtime_model_cleanup_warnings(
                    previous_map=previous_map,
                    updates=update_map,
                )
            )
            warnings.extend(
                self._build_hermes_unsupported_key_cleanup_warnings(
                    previous_map=previous_map,
                    updates=update_map,
                )
            )
            if self._runtime_scheduler is not None and submitted_keys & {
                "SCHEDULE_ENABLED",
                "SCHEDULE_TIME",
                "SCHEDULE_TIMES",
            }:
                try:
                    self._runtime_scheduler.reconcile_from_config(
                        clear_enabled_override="SCHEDULE_ENABLED" in submitted_keys,
                    )
                except Exception as exc:  # pragma: no cover; broad-exception: fallback_recorded - report scheduler failure
                    log_safe_exception(
                        logger,
                        "Runtime scheduler reconciliation failed",
                        exc,
                        error_code="runtime_scheduler_reconcile_failed",
                        redaction_values=redaction_values,
                    )
                    warnings.append("Configuration updated but runtime scheduler reconcile failed")

            _log_config_audit(
                actor=actor,
                operation="update",
                outcome="activated" if reload_triggered else "persisted_only",
                keys=updated_keys,
                config_version=new_version,
            )
            return {
                "success": True,
                "config_version": new_version,
                "applied_count": len(updated_keys),
                "skipped_masked_count": len(skipped_masked_keys),
                "reload_triggered": reload_triggered,
                "updated_keys": updated_keys,
                "warnings": warnings,
            }

    def restore_last_good_config(
        self,
        *,
        config_version: str,
        actor: str = "system_config_service",
    ) -> Dict[str, Any]:
        """Restore the previous active config without crossing the auth boundary."""
        with self._runtime_config_transaction.lock:
            self._conflict.guard_version(config_version)
            try:
                target_snapshot = self._runtime_config_transaction.read_last_good_snapshot()
            except _LastGoodConfigUnavailableError as exc:
                _log_config_audit(
                    actor=actor,
                    operation="rollback",
                    outcome="unavailable",
                    keys=(),
                    config_version=config_version,
                )
                raise ConfigRollbackError(str(exc)) from exc

            current_map = self._manager.read_config_map()
            target_map = self._runtime_config_transaction.snapshot_config_map(
                target_snapshot
            )
            auth_issue = _build_auth_rollback_issue(
                current_map=current_map,
                target_map=target_map,
            )
            if auth_issue is not None:
                _log_config_audit(
                    actor=actor,
                    operation="rollback",
                    outcome="rejected_auth_boundary",
                    keys=("ADMIN_AUTH_ENABLED",),
                    config_version=config_version,
                )
                raise ConfigValidationError(issues=[auth_issue])

            try:
                new_version, changed_keys, warnings = (
                    self._runtime_config_transaction.rollback_to_last_good(
                        target_snapshot=target_snapshot,
                    )
                )
            except _RuntimeConfigActivationError as exc:
                log_safe_exception(
                    logger,
                    "Configuration rollback activation failed",
                    exc,
                    error_code="configuration_rollback_activation_failed",
                    context={"rollback_succeeded": exc.rollback_succeeded},
                )
                _log_config_audit(
                    actor=actor,
                    operation="rollback",
                    outcome=(
                        "restored_current_after_failure"
                        if exc.rollback_succeeded
                        else "rollback_failed"
                    ),
                    keys=(),
                    config_version=self._manager.get_config_version(),
                )
                raise RuntimeError("Last-known-good configuration activation failed") from exc

            if self._runtime_scheduler is not None and set(changed_keys) & {
                "SCHEDULE_ENABLED",
                "SCHEDULE_TIME",
                "SCHEDULE_TIMES",
            }:
                try:
                    self._runtime_scheduler.reconcile_from_config(
                        clear_enabled_override="SCHEDULE_ENABLED" in changed_keys,
                    )
                except Exception as exc:  # broad-exception: fallback_recorded - report rollback scheduler failure
                    log_safe_exception(
                        logger,
                        "Runtime scheduler rollback reconciliation failed",
                        exc,
                        error_code="runtime_scheduler_rollback_reconcile_failed",
                    )
                    warnings.append(
                        "Configuration rolled back but runtime scheduler reconcile failed"
                    )

            warnings.append("The previous last-known-good configuration was restored.")
            _log_config_audit(
                actor=actor,
                operation="rollback",
                outcome="activated",
                keys=changed_keys,
                config_version=new_version,
            )
            return {
                "success": True,
                "config_version": new_version,
                "applied_count": len(changed_keys),
                "skipped_masked_count": 0,
                "reload_triggered": True,
                "updated_keys": changed_keys,
                "warnings": warnings,
            }

    def _build_explainability_warnings(
        self,
        *,
        submitted_keys: Set[str],
        reload_now: bool,
    ) -> List[str]:
        """Append user-facing runtime explainability warnings for key settings."""
        warnings: List[str] = []
        if not submitted_keys:
            return warnings

        current_map = self._manager.read_config_map()

        if submitted_keys & {"NEWS_MAX_AGE_DAYS", "NEWS_STRATEGY_PROFILE"}:
            raw_profile = current_map.get("NEWS_STRATEGY_PROFILE", "short")
            profile = normalize_news_strategy_profile(raw_profile)
            try:
                max_age = max(1, int(current_map.get("NEWS_MAX_AGE_DAYS", "3") or "3"))
            except (TypeError, ValueError):
                max_age = 3
            effective_days = resolve_news_window_days(
                news_max_age_days=max_age,
                news_strategy_profile=profile,
            )
            warnings.append(
                (
                    "新闻窗口已按策略计算："
                    f"NEWS_STRATEGY_PROFILE={profile}, "
                    f"NEWS_MAX_AGE_DAYS={max_age}, "
                    f"effective_days={effective_days} "
                    "(effective_days=min(profile_days, NEWS_MAX_AGE_DAYS))."
                )
            )

        if "MAX_WORKERS" in submitted_keys:
            try:
                max_workers = max(1, int(current_map.get("MAX_WORKERS", "3") or "3"))
            except (TypeError, ValueError):
                max_workers = 3
            if reload_now:
                warnings.append(
                    (
                        f"MAX_WORKERS={max_workers} 已保存。任务队列空闲时会自动应用；"
                        "若当前存在运行中任务，将在队列空闲后生效。"
                    )
                )
            else:
                warnings.append(
                    (
                        f"MAX_WORKERS={max_workers} 已写入 .env，但本次未触发运行时重载"
                        "（reload_now=false）；重载后才会应用。"
                    )
                )

        startup_only_run_keys = submitted_keys & {
            "RUN_IMMEDIATELY",
        }
        if startup_only_run_keys:
            warnings.append(
                (
                    f"{', '.join(sorted(startup_only_run_keys))} 已写入 .env。"
                    "它属于启动期单次运行配置：当前已运行的 WebUI/API 进程不会因为本次保存立即触发分析；"
                    "请重启当前进程后，在非 schedule 模式下按新值生效。"
                )
            )

        startup_only_schedule_keys = submitted_keys & {
            "SCHEDULE_RUN_IMMEDIATELY",
        }
        if startup_only_schedule_keys:
            warnings.append(
                (
                    f"{', '.join(sorted(startup_only_schedule_keys))} 已写入 .env。"
                    "这些属于启动期调度模式配置：当前已运行的 WebUI/API 进程不会因为本次保存启动、"
                    "停止或重建 scheduler；请重启当前进程，并以 schedule 模式重新启动后生效。"
                )
            )

        if "SCHEDULE_ENABLED" in submitted_keys:
            schedule_enabled = (current_map.get("SCHEDULE_ENABLED", "false") or "false").strip().lower()
            warnings.append(
                (
                    f"SCHEDULE_ENABLED={schedule_enabled} 已写入 .env。"
                    "如果当前进程是 WebUI/API/Desktop 长运行进程，runtime scheduler 会按新配置启停；"
                    "CLI schedule 模式仍按启动参数和配置运行。"
                )
            )

        if "SCHEDULE_TIMES" in submitted_keys:
            schedule_times = (current_map.get("SCHEDULE_TIMES", "") or "").strip()
            schedule_time = (current_map.get("SCHEDULE_TIME", "") or "").strip() or "18:00"
            effective = schedule_times or schedule_time
            warnings.append(
                (
                    f"SCHEDULE_TIMES={effective} 已写入 .env。"
                    "有效时间点会去重、排序；为空时继续使用 SCHEDULE_TIME。"
                    "如果当前进程存在 runtime scheduler，会按新时间重建 daily jobs。"
                )
            )

        if "SCHEDULE_TIME" in submitted_keys:
            schedule_time = (current_map.get("SCHEDULE_TIME", "") or "").strip() or "18:00"
            warnings.append(
                (
                    f"SCHEDULE_TIME={schedule_time} 已写入 .env。"
                    "如果当前进程已经以 schedule 模式运行，scheduler 会在下一轮检查中自动重建 daily job；"
                    "如果当前进程未以 schedule 模式运行，本次保存不会启动 scheduler。"
                )
            )

        startup_only_bind_keys = submitted_keys & {
            "WEBUI_HOST",
            "WEBUI_PORT",
        }
        if startup_only_bind_keys:
            warnings.append(
                (
                    f"{', '.join(sorted(startup_only_bind_keys))} 已写入 .env。"
                    "这些属于启动期监听配置：当前已运行的 WebUI/API 进程不会因为本次保存重新绑定监听地址或端口；"
                    "请重启当前进程、Docker 容器或服务管理器后生效。"
                )
            )

        return warnings

    @staticmethod
    def _build_runtime_model_cleanup_warnings(
        *,
        previous_map: Dict[str, str],
        updates: Dict[str, str],
    ) -> List[str]:
        """Explain when save payload clears stale runtime model references."""
        runtime_labels = {
            "LITELLM_MODEL": "主要模型",
            "AGENT_LITELLM_MODEL": "Agent 主要模型",
            "VISION_MODEL": "Vision 模型",
        }
        cleared_labels: List[str] = []
        for key, label in runtime_labels.items():
            if previous_map.get(key, "").strip() and key in updates and not updates[key].strip():
                cleared_labels.append(label)

        removed_fallbacks: List[str] = []
        if "LITELLM_FALLBACK_MODELS" in updates:
            previous_fallbacks = [
                item.strip()
                for item in previous_map.get("LITELLM_FALLBACK_MODELS", "").split(",")
                if item.strip()
            ]
            next_fallbacks = {
                item.strip()
                for item in updates["LITELLM_FALLBACK_MODELS"].split(",")
                if item.strip()
            }
            removed_fallbacks = [item for item in previous_fallbacks if item not in next_fallbacks]

        if not cleared_labels and not removed_fallbacks:
            return []

        cleaned_targets = list(cleared_labels)
        if removed_fallbacks:
            cleaned_targets.append("备用模型中的失效项")

        cleaned_text = " / ".join(cleaned_targets)
        warning = (
            f"检测到已同步清理失效的运行时模型引用：{cleaned_text}。"
            "如需恢复，请先补回对应连接的模型列表后重新选择；"
            "也可用桌面端导出备份或手动 .env 还原之前的 LLM_* / "
            "LITELLM_MODEL / AGENT_LITELLM_MODEL / VISION_MODEL / LLM_TEMPERATURE。"
        )
        return [warning]

    @staticmethod
    def _build_hermes_unsupported_key_cleanup_warnings(
        *,
        previous_map: Dict[str, str],
        updates: Dict[str, str],
    ) -> List[str]:
        """Explain when Hermes save clears unsupported Phase 3 key/header fields."""
        unsupported_labels = {
            "LLM_HERMES_API_KEYS": "LLM_HERMES_API_KEYS",
            "LLM_HERMES_EXTRA_HEADERS": "LLM_HERMES_EXTRA_HEADERS",
        }
        cleared = [
            label
            for key, label in unsupported_labels.items()
            if previous_map.get(key, "").strip() and key in updates and not updates[key].strip()
        ]
        if not cleared:
            return []

        return [
            (
                "检测到已清理 Hermes Phase 3 不支持的配置项："
                f"{', '.join(cleared)}。"
                "Hermes reserved channel 只支持单个 LLM_HERMES_API_KEY，不支持多 Key 或额外 Header；"
                "如需恢复旧值，请从 .env 备份、Git 历史或桌面端导出备份手动还原，"
                "但非空 LLM_HERMES_API_KEYS / LLM_HERMES_EXTRA_HEADERS 仍会被后端校验拒绝。"
            )
        ]

    def apply_simple_updates(
        self,
        updates: Sequence[Tuple[str, str]],
        mask_token: str = "******",
    ) -> None:
        """Apply raw key updates without validation (internal service use only)."""
        with self._runtime_config_transaction.lock:
            self._manager.apply_updates(
                updates=updates,
                sensitive_keys=set(),
                mask_token=mask_token,
            )
            self._runtime_config_transaction.mark_persisted_config_active()

    @staticmethod
    def _parse_imported_env_content(content: str) -> List[Dict[str, str]]:
        """Parse raw `.env` text into update items without expanding app templates."""
        normalized_content = content.replace("\ufeff", "")
        if not normalized_content.strip():
            raise ConfigImportError("未识别到有效 .env 配置")

        from dotenv import dotenv_values

        parsed = dotenv_values(stream=io.StringIO(normalized_content), interpolate=False)
        updates: List[Dict[str, str]] = []
        for key, value in parsed.items():
            if key is None:
                continue
            updates.append(
                {
                    "key": str(key).upper(),
                    "value": "" if value is None else str(value),
                }
            )

        if not updates:
            raise ConfigImportError("未识别到有效 .env 配置")

        return updates

    def _collect_issues(
        self,
        items: Sequence[Dict[str, str]],
        mask_token: str,
        *,
        require_explicit_runtime_secrets: bool = False,
    ) -> List[Dict[str, Any]]:
        """Collect field-level and cross-field validation issues."""
        saved_config_map = self._manager.read_config_map()
        display_config_map = self._build_display_config_map(saved_config_map)
        runtime_config_map = self._build_runtime_display_config_map(display_config_map)
        effective_map = {
            **runtime_config_map,
            **display_config_map,
        }
        previous_effective_map = dict(effective_map)
        issues: List[Dict[str, Any]] = []
        updated_map: Dict[str, str] = {}
        submitted_map: Dict[str, str] = {}

        for item in items:
            raw_key = item["key"]
            key = raw_key.upper()
            value = item["value"]
            if self._ENV_KEY_PATTERN.fullmatch(raw_key) is None:
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_key",
                        "severity": "error",
                        "message": "Configuration keys must use canonical environment-variable syntax.",
                        "expected": "[A-Za-z_][A-Za-z0-9_]*",
                        "actual": "invalid format",
                    }
                )
                continue
            submitted_map[key] = value
            field_schema = get_field_definition(key, value)
            if key == "ADMIN_AUTH_ENABLED":
                current_enabled = (saved_config_map.get(key) or "").strip().lower() in {
                    "true",
                    "1",
                    "yes",
                }
                requested_enabled = value.strip().lower() in {"true", "1", "yes"}
                if requested_enabled != current_enabled:
                    issues.append(
                        {
                            "key": key,
                            "code": "auth_settings_endpoint_required",
                            "severity": "error",
                            "message": (
                                "ADMIN_AUTH_ENABLED can only be changed through "
                                "/api/v1/auth/settings with current-password verification."
                            ),
                            "expected": "unchanged value or dedicated auth settings endpoint",
                            "actual": value,
                        }
                    )
            is_sensitive = bool(field_schema.get("is_sensitive", False))
            submitted_is_masked = is_sensitive and (
                value == mask_token or is_masked_secret_placeholder(value)
            )
            if submitted_is_masked:
                saved_secret = (saved_config_map.get(key) or "").strip()
                dynamic_match = self._WEB_SETTINGS_LLM_CHANNEL_SUPPORT_KEY_RE.fullmatch(key)
                is_connection_scoped = bool(
                    dynamic_match
                    and dynamic_match.group(2) in self._CONNECTION_SECRET_SCOPE_SUFFIXES
                )
                if saved_secret:
                    if not is_connection_scoped and is_masked_secret_placeholder(saved_secret):
                        issues.append(
                            {
                                "key": key,
                                "code": "saved_secret_scope_mismatch",
                                "severity": "error",
                                "message": f"{key} contains a saved mask placeholder and must be replaced.",
                                "expected": "fresh literal secret or explicit clear",
                                "actual": "masked",
                                "details": {"reason": "invalid_saved_secret_placeholder"},
                            }
                        )
                    # Keep the effective saved value. Connection-scoped identity
                    # changes are checked after all draft fields are applied.
                    continue

                runtime_secret = (runtime_config_map.get(key) or "").strip()
                if runtime_secret:
                    code = "runtime_secret_not_reusable"
                    detail_reason = code
                elif dynamic_match:
                    code = "saved_secret_scope_mismatch"
                    detail_reason = "missing_scoped_saved_secret"
                else:
                    code = "missing_saved_secret"
                    detail_reason = code
                details: Dict[str, Any] = {"reason": detail_reason}
                if dynamic_match:
                    details["connection"] = dynamic_match.group(1).lower()
                issues.append(
                    {
                        "key": key,
                        "code": code,
                        "severity": "error",
                        "message": (
                            f"{key} is injected at runtime and cannot be reused by a Settings draft."
                            if runtime_secret
                            else f"{key} has no saved value for this mask token."
                        ),
                        "expected": "fresh literal secret or explicit clear",
                        "actual": "masked",
                        "details": details,
                    }
                )
                continue

            updated_map[key] = value
            effective_map[key] = value
            issues.extend(self._validate_value(key=key, value=value, field_schema=field_schema))

        issues.extend(
            self._collect_connection_secret_scope_issues(
                saved_map=display_config_map,
                runtime_map=runtime_config_map,
                effective_map=effective_map,
                submitted_map=submitted_map,
                mask_token=mask_token,
                require_explicit_runtime_secrets=(
                    require_explicit_runtime_secrets
                    and self._generation_backend_uses_litellm(effective_map)
                ),
            )
        )
        issues.extend(
            self._validate_cross_field(
                effective_map=effective_map,
                updated_keys=set(updated_map.keys()),
                previous_effective_map=previous_effective_map,
            )
        )
        issues.extend(self._validate_field_contracts(effective_map))
        return issues

    @classmethod
    def _connection_secret_scope_identity(
        cls,
        config_map: Dict[str, str],
        connection_name: str,
    ) -> Dict[str, str]:
        """Return the endpoint identity to which a Connection secret is bound."""
        _provider, provider_id, _is_explicit = cls._resolve_connection_provider(
            config_map,
            connection_name,
        )
        protocol, base_url = cls._resolve_connection_transport(
            config_map,
            connection_name,
        )
        return {
            "provider": provider_id.strip().lower(),
            "protocol": canonicalize_llm_channel_protocol(protocol),
            "base_url": base_url.strip().rstrip("/"),
        }

    @classmethod
    def _collect_connection_secret_scope_issues(
        cls,
        *,
        saved_map: Dict[str, str],
        runtime_map: Dict[str, str],
        effective_map: Dict[str, str],
        submitted_map: Dict[str, str],
        mask_token: str,
        require_explicit_runtime_secrets: bool = False,
    ) -> List[Dict[str, Any]]:
        """Reject secrets whose saved/runtime scope cannot authorize a draft."""
        saved_connections: Set[str] = set()
        for key, value in saved_map.items():
            match = cls._WEB_SETTINGS_LLM_CHANNEL_SUPPORT_KEY_RE.fullmatch(key)
            if (
                match
                and match.group(2) in cls._CONNECTION_SECRET_SCOPE_SUFFIXES
                and str(value or "").strip()
            ):
                saved_connections.add(match.group(1))
        effective_connections = {
            name.strip().upper()
            for name in cls._split_csv(effective_map.get("LLM_CHANNELS") or "")
        }
        issues: List[Dict[str, Any]] = []
        for connection_name in sorted(saved_connections):
            saved_identity = cls._connection_secret_scope_identity(
                saved_map,
                connection_name,
            )
            effective_identity = cls._connection_secret_scope_identity(
                effective_map,
                connection_name,
            )
            changed_fields = [
                field
                for field in ("provider", "protocol", "base_url")
                if saved_identity[field] != effective_identity[field]
            ]
            prefix = f"LLM_{connection_name}"
            for suffix in cls._CONNECTION_SECRET_SCOPE_SUFFIXES:
                key = f"{prefix}_{suffix}"
                saved_secret = (saved_map.get(key) or "").strip()
                if not saved_secret:
                    continue
                submitted = submitted_map.get(key)
                submitted_is_masked = submitted is not None and (
                    submitted == mask_token or is_masked_secret_placeholder(submitted)
                )
                if submitted is not None and not submitted_is_masked:
                    continue
                saved_is_masked = is_masked_secret_placeholder(saved_secret)
                if not saved_is_masked and not changed_fields:
                    continue
                issues.append(
                    {
                        "key": key,
                        "code": "saved_secret_scope_mismatch",
                        "severity": "error",
                        "message": (
                            f"{key} contains a saved mask placeholder and must be replaced."
                            if saved_is_masked
                            else (
                                f"{key} is bound to the saved Connection endpoint. "
                                "Re-enter or clear it before changing Provider, protocol, or Base URL."
                            )
                        ),
                        "expected": "fresh literal secret or explicit clear",
                        "actual": "masked" if submitted_is_masked else "omitted",
                        "details": {
                            "reason": (
                                "invalid_saved_secret_placeholder"
                                if saved_is_masked
                                else "connection_identity_changed"
                            ),
                            "connection": connection_name.lower(),
                            "changed_fields": changed_fields,
                        },
                    }
                )

        for connection_name in sorted(effective_connections):
            prefix = f"LLM_{connection_name}"
            connection_touched = "LLM_CHANNELS" in submitted_map or any(
                key.startswith(f"{prefix}_") for key in submitted_map
            )
            if not connection_touched and not require_explicit_runtime_secrets:
                continue
            for suffix in cls._CONNECTION_SECRET_SCOPE_SUFFIXES:
                key = f"{prefix}_{suffix}"
                if (saved_map.get(key) or "").strip():
                    continue
                submitted = submitted_map.get(key)
                submitted_is_masked = submitted is not None and (
                    submitted == mask_token or is_masked_secret_placeholder(submitted)
                )
                # Explicit mask submissions are handled once in the generic
                # sensitive-field pass above. This loop owns omitted secrets.
                if submitted_is_masked:
                    continue
                runtime_secret = (runtime_map.get(key) or "").strip()
                if not runtime_secret:
                    continue
                if submitted is not None:
                    continue
                issues.append(
                    {
                        "key": key,
                        "code": "runtime_secret_not_reusable",
                        "severity": "error",
                        "message": (
                            f"{key} is injected at runtime and cannot be reused by a Settings draft. "
                            "Enter a fresh value before previewing, testing, or changing this Connection."
                        ),
                        "expected": "fresh literal secret",
                        "actual": "masked" if submitted_is_masked else "omitted",
                        "details": {
                            "reason": "runtime_secret_not_reusable",
                            "connection": connection_name.lower(),
                        },
                    }
                )
        return issues

    @staticmethod
    def _generation_backend_uses_litellm(effective_map: Dict[str, str]) -> bool:
        primary = normalize_backend_id(
            effective_map.get("GENERATION_BACKEND"),
            default=LITELLM_BACKEND_ID,
        )
        fallback = (
            LITELLM_BACKEND_ID
            if "GENERATION_FALLBACK_BACKEND" not in effective_map
            else (effective_map.get("GENERATION_FALLBACK_BACKEND") or "").strip().lower()
        )
        return LITELLM_BACKEND_ID in {primary, fallback}

    @staticmethod
    def _validate_field_contracts(effective_map: Dict[str, str]) -> List[Dict[str, Any]]:
        """Authoritative required/conditionally-required schema contract checks.

        Hidden fields (visibleWhen not met) are excluded; a field is required when
        requirement=required or its requiredWhen conditions are met.
        """
        issues: List[Dict[str, Any]] = []
        for key, contract in get_contract_field_definitions().items():
            if evaluate_config_conditions(contract.get("visible_when"), effective_map) == "not_met":
                continue
            required = contract.get("requirement") == "required"
            required_when = contract.get("required_when")
            if required_when and evaluate_config_conditions(required_when, effective_map) == "met":
                required = True
            if required and not str(effective_map.get(key, "") or "").strip():
                issues.append({
                    "key": key,
                    "code": "field_required",
                    "severity": "error",
                    "message": f"{key} is required by the current configuration.",
                    "expected": "non-empty value",
                    "actual": "",
                })
        return issues

    @classmethod
    def _is_generation_backend_status_key(cls, key: str) -> bool:
        normalized = str(key or "").strip().upper()
        return (
            normalized in cls._GENERATION_BACKEND_STATUS_EXACT_KEYS
            or normalized == "LLM_CHANNELS"
            or bool(cls._GENERATION_BACKEND_STATUS_LLM_CHANNEL_RE.fullmatch(normalized))
        )

    @classmethod
    def _filter_generation_backend_items(
        cls,
        items: Sequence[Dict[str, str]],
    ) -> List[Dict[str, str]]:
        filtered: List[Dict[str, str]] = []
        for item in items:
            key = str(item.get("key", "")).strip().upper()
            if not key or not cls._is_generation_backend_status_key(key):
                continue
            filtered.append({"key": key, "value": "" if item.get("value") is None else str(item.get("value"))})
        return filtered

    def _collect_generation_backend_issues(
        self,
        *,
        items: Sequence[Dict[str, str]],
        mask_token: str,
    ) -> List[Dict[str, Any]]:
        """Collect only config issues that affect generation backend status/smoke."""
        issues = self._collect_issues(
            items=self._filter_generation_backend_items(items),
            mask_token=mask_token,
            require_explicit_runtime_secrets=True,
        )
        effective_map = self._build_generation_backend_effective_map(
            items=items,
            mask_token=mask_token,
        )
        issues.extend(self._validate_generation_backend_litellm_runtime_source(effective_map))
        return [
            issue for issue in issues
            if self._is_generation_backend_status_key(str(issue.get("key", "")))
        ]

    @staticmethod
    def _validate_generation_backend_litellm_runtime_source(effective_map: Dict[str, str]) -> List[Dict[str, Any]]:
        """Validate explicit LiteLLM models when no route list can back them."""
        primary_backend = normalize_backend_id(
            effective_map.get("GENERATION_BACKEND"),
            default=LITELLM_BACKEND_ID,
        )
        fallback_backend = (
            LITELLM_BACKEND_ID
            if "GENERATION_FALLBACK_BACKEND" not in effective_map
            else (effective_map.get("GENERATION_FALLBACK_BACKEND") or "").strip().lower()
        )
        litellm_selected = (
            primary_backend == LITELLM_BACKEND_ID
            or (fallback_backend == LITELLM_BACKEND_ID and primary_backend != LITELLM_BACKEND_ID)
        )
        if not litellm_selected:
            return []
        if SystemConfigService._uses_litellm_yaml(effective_map):
            return []
        if SystemConfigService._collect_llm_channel_models_from_map(effective_map):
            return []
        if (effective_map.get("LLM_CHANNELS") or "").strip():
            return []

        issues: List[Dict[str, Any]] = []
        primary_model = (effective_map.get("LITELLM_MODEL") or "").strip()
        if primary_model and not SystemConfigService._has_runtime_source_for_model(primary_model, effective_map):
            issues.append(
                {
                    "key": "LITELLM_MODEL",
                    "code": "missing_runtime_source",
                    "message": (
                        "A primary model is selected, but no usable runtime source was found. "
                        "Configure a matching provider API key, LLM channel, or LiteLLM YAML route."
                    ),
                    "severity": "error",
                    "expected": "matching provider API key, enabled channel model, or YAML model",
                    "actual": primary_model,
                }
            )

        fallback_models = [
            model.strip()
            for model in (effective_map.get("LITELLM_FALLBACK_MODELS") or "").split(",")
            if model.strip()
        ]
        invalid_fallbacks = [
            model for model in fallback_models
            if not SystemConfigService._has_runtime_source_for_model(model, effective_map)
        ]
        if invalid_fallbacks:
            issues.append(
                {
                    "key": "LITELLM_FALLBACK_MODELS",
                    "code": "missing_runtime_source",
                    "message": (
                        "Some fallback models do not have a matching provider API key, "
                        "enabled channel, or LiteLLM YAML route."
                    ),
                    "severity": "error",
                    "expected": "matching provider API key, enabled channel model, or YAML model",
                    "actual": ", ".join(invalid_fallbacks[:3]),
                }
            )
        return issues

    def _collect_generation_backend_issues_from_map(
        self,
        effective_map: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        items = [
            {"key": key, "value": value}
            for key, value in effective_map.items()
            if self._is_generation_backend_status_key(key)
        ]
        return self._collect_generation_backend_issues(items=items, mask_token="******")

    @staticmethod
    def _validate_value(key: str, value: str, field_schema: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Validate a single field value against schema metadata."""
        issues: List[Dict[str, Any]] = []
        data_type = field_schema.get("data_type", "string")
        validation = field_schema.get("validation", {}) or {}
        is_required = field_schema.get("is_required", False)

        # Empty values are valid for non-required fields (skip type validation)
        if not value.strip() and not is_required:
            return issues

        if ("\n" in value or "\r" in value) and data_type != "json":
            issues.append(
                {
                    "key": key,
                    "code": "invalid_value",
                    "message": "Value cannot contain newline characters",
                    "severity": "error",
                    "expected": "single-line value",
                    "actual": "contains newline",
                }
            )
            return issues

        if data_type == "integer":
            try:
                numeric = int(value)
            except ValueError:
                return [
                    {
                        "key": key,
                        "code": "invalid_type",
                        "message": "Value must be an integer",
                        "severity": "error",
                        "expected": "integer",
                        "actual": value,
                    }
                ]
            issues.extend(SystemConfigService._validate_numeric_range(key, numeric, validation))

        elif data_type == "number":
            try:
                numeric = float(value)
            except ValueError:
                return [
                    {
                        "key": key,
                        "code": "invalid_type",
                        "message": "Value must be a number",
                        "severity": "error",
                        "expected": "number",
                        "actual": value,
                    }
                ]
            issues.extend(SystemConfigService._validate_numeric_range(key, numeric, validation))

        elif data_type == "boolean":
            if value.strip().lower() not in {"true", "false"}:
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_type",
                        "message": "Value must be true or false",
                        "severity": "error",
                        "expected": "true|false",
                        "actual": value,
                    }
                )

        elif data_type == "time":
            pattern = validation.get("pattern") or r"^([01]\d|2[0-3]):[0-5]\d$"
            if not re.match(pattern, value.strip()):
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_format",
                        "message": "Value must be in HH:MM format",
                        "severity": "error",
                        "expected": "HH:MM",
                        "actual": value,
                    }
                )

        elif data_type == "json":
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_json",
                        "message": "Value must be valid JSON",
                        "severity": "error",
                        "expected": "valid JSON",
                        "actual": (
                            "[REDACTED]"
                            if field_schema.get("is_sensitive", False)
                            else value[:120]
                        ),
                    }
                )
            else:
                if key.endswith("_EXTRA_HEADERS") and not isinstance(parsed, dict):
                    issues.append(
                        {
                            "key": key,
                            "code": "invalid_json_object",
                            "message": "Value must be a JSON object",
                            "severity": "error",
                            "expected": "JSON object",
                            "actual": "[REDACTED]",
                        }
                    )
                elif key == "AGENT_EVENT_ALERT_RULES_JSON":
                    try:
                        from src.agent.events import parse_event_alert_rules, validate_event_alert_rule

                        rule_index = 0
                        for rule_index, rule in enumerate(parse_event_alert_rules(parsed), start=1):
                            validate_event_alert_rule(rule)
                    except ValueError as exc:
                        issues.append(
                            {
                                "key": key,
                                "code": "invalid_event_rule",
                                "message": f"Rule validation failed: {exc}",
                                "severity": "error",
                                "expected": "supported EventMonitor rule fields and enum values",
                                "actual": f"rule #{rule_index or 1}",
                            }
                        )

        elif validation.get("pattern"):
            pattern = validation["pattern"]
            if not re.match(pattern, value.strip()):
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_format",
                        "message": "Value does not match the required format",
                        "severity": "error",
                        "expected": pattern,
                        "actual": value,
                    }
                )

        if validation.get("timezone") and value:
            try:
                validate_notification_timezone(value)
            except ValueError as exc:
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_timezone",
                        "message": str(exc),
                        "severity": "error",
                        "expected": "valid IANA timezone or empty",
                        "actual": value,
                    }
                )

        if "enum" in validation and value and value not in validation["enum"]:
            issues.append(
                {
                    "key": key,
                    "code": "invalid_enum",
                    "message": "Value is not in allowed options",
                    "severity": "error",
                    "expected": ",".join(validation["enum"]),
                    "actual": value,
                }
            )

        if "allowed_values" in validation and value:
            delimiter = validation.get("delimiter")
            raw_values = value.split(delimiter) if delimiter else [value]
            allowed_values = {str(item).strip().lower() for item in validation["allowed_values"]}
            invalid_values = []
            seen_invalid = set()
            for raw_item in raw_values:
                item = raw_item.strip().lower()
                if not item:
                    continue
                if item not in allowed_values and item not in seen_invalid:
                    invalid_values.append(item)
                    seen_invalid.add(item)
            if invalid_values:
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_allowed_value",
                        "message": "Value contains unsupported item(s)",
                        "severity": "error",
                        "expected": ",".join(str(item) for item in validation["allowed_values"]),
                        "actual": ", ".join(invalid_values),
                    }
                )

        if validation.get("item_type") == "url":
            delimiter = validation.get("delimiter", ",")
            values = [item.strip() for item in value.split(delimiter)] if validation.get("multi_value") else [value.strip()]
            allowed_schemes = tuple(validation.get("allowed_schemes", ["http", "https"]))
            invalid_values = [
                item for item in values
                if item and not SystemConfigService._is_valid_url(item, allowed_schemes=allowed_schemes)
            ]
            if invalid_values:
                issues.append(
                    {
                        "key": key,
                        "code": "invalid_url",
                        "message": "Value must contain valid URLs with scheme and host",
                        "severity": "error",
                        "expected": ",".join(allowed_schemes) + " URL(s)",
                        "actual": ", ".join(invalid_values[:3]),
                    }
                )

        if key == "NTFY_URL" and value.strip():
            allowed_schemes = tuple(validation.get("allowed_schemes", ["http", "https"]))
            if SystemConfigService._is_valid_url(value.strip(), allowed_schemes=allowed_schemes):
                ntfy_server_url, ntfy_topic = resolve_ntfy_endpoint(value)
                if not ntfy_server_url or not ntfy_topic:
                    issues.append(
                        {
                            "key": key,
                            "code": "invalid_ntfy_url",
                            "message": "NTFY_URL must include a topic path, e.g. https://ntfy.sh/my-topic",
                            "severity": "error",
                            "expected": "ntfy publish endpoint with topic path",
                            "actual": value,
                        }
                    )

        if key == "GOTIFY_URL" and value.strip():
            allowed_schemes = tuple(validation.get("allowed_schemes", ["http", "https"]))
            if SystemConfigService._is_valid_url(value.strip(), allowed_schemes=allowed_schemes):
                gotify_endpoint = resolve_gotify_message_endpoint(value)
                if not gotify_endpoint:
                    issues.append(
                        {
                            "key": key,
                            "code": "invalid_gotify_url",
                            "message": "GOTIFY_URL must be a Gotify server base URL and must not include /message",
                            "severity": "error",
                            "expected": "Gotify server base URL, e.g. https://gotify.example",
                            "actual": value,
                        }
                    )

        return issues

    @staticmethod
    def _normalize_value_for_storage(value: str, field_schema: Dict[str, Any]) -> str:
        """Normalize submitted values before persisting to the single-line .env file."""
        if field_schema.get("data_type", "string") != "json":
            return value

        if not value.strip():
            return value

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value

        return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def _validate_numeric_range(key: str, numeric_value: float, validation: Dict[str, Any]) -> List[Dict[str, Any]]:
        issues: List[Dict[str, Any]] = []
        min_value = validation.get("min")
        max_value = validation.get("max")

        if min_value is not None and numeric_value < min_value:
            issues.append(
                {
                    "key": key,
                    "code": "out_of_range",
                    "message": "Value is lower than minimum",
                    "severity": "error",
                    "expected": f">={min_value}",
                    "actual": str(numeric_value),
                }
            )
        if max_value is not None and numeric_value > max_value:
            issues.append(
                {
                    "key": key,
                    "code": "out_of_range",
                    "message": "Value is greater than maximum",
                    "severity": "error",
                    "expected": f"<={max_value}",
                    "actual": str(numeric_value),
                }
            )
        return issues

    @staticmethod
    def _is_valid_url(value: str, allowed_schemes: Tuple[str, ...]) -> bool:
        """Return True when *value* looks like a valid absolute URL."""
        parsed = urlparse(value)
        return parsed.scheme in allowed_schemes and bool(parsed.netloc)

    @staticmethod
    def _canonical_ipv4_numeric_host(host: str) -> Optional[str]:
        """Return canonical IPv4 for libc-style numeric host aliases."""
        import socket

        candidate = (host or "").lower()
        if not candidate or ":" in candidate:
            return None

        try:
            return socket.inet_ntoa(socket.inet_aton(candidate))
        except (OSError, ValueError):
            return None

    @staticmethod
    def _is_noncanonical_ipv4_numeric_host(host: str) -> bool:
        canonical = SystemConfigService._canonical_ipv4_numeric_host(host)
        return canonical is not None and host.lower() != canonical

    @staticmethod
    def _normalize_hostname_for_security(host: str) -> Optional[str]:
        """Return a normalized ASCII host for URL safety checks."""
        import unicodedata

        candidate = (host or "").strip().lower().rstrip(".")
        if not candidate:
            return None
        if ":" in candidate:
            return candidate
        try:
            normalized = unicodedata.normalize("NFKC", candidate)
            ascii_host = normalized.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError:
            return None
        return ascii_host or None

    @staticmethod
    def _is_valid_llm_base_url(value: str, allowed_schemes: Tuple[str, ...] = ("http", "https")) -> bool:
        """Return True when an LLM base URL is safe to parse consistently."""
        if not value:
            return False
        if any(char == "\\" or char.isspace() or ord(char) < 32 or ord(char) == 127 for char in value):
            return False

        try:
            parsed = urlparse(value)
            host = parsed.hostname
            _ = parsed.port
        except ValueError:
            return False

        if parsed.scheme not in allowed_schemes or not parsed.netloc or not host:
            return False
        if "@" in parsed.netloc or parsed.username is not None or parsed.password is not None:
            return False
        if SystemConfigService._is_noncanonical_ipv4_numeric_host(host):
            return False

        return True

    @staticmethod
    def _split_csv(value: str) -> List[str]:
        return [item.strip() for item in (value or "").split(",") if item.strip()]
