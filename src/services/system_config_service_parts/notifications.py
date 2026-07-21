"""Notifications methods for the system-config facade."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.services.system_config_service import (
        Any,
        Config,
        Dict,
        List,
        Optional,
        Sequence,
        Tuple,
        get_field_definition,
        get_registered_field_keys,
        os,
        parse_env_bool,
        parse_env_int,
        re,
        requests,
        resolve_gotify_message_endpoint,
        resolve_ntfy_endpoint,
        time,
        urlparse,
        urlunparse,
    )


class _SystemConfigNotificationMethods:
    def _build_notification_test_effective_map(
        self,
        *,
        items: Sequence[Dict[str, str]],
        mask_token: str,
    ) -> Dict[str, str]:
        """Merge saved/runtime config with unsaved notification test items."""
        allowed_keys = set(self._NOTIFICATION_TEST_KEY_MAP)
        effective = {
            key: value
            for key, value in self._build_display_config_map(self._manager.read_config_map()).items()
            if key in allowed_keys
        }

        for raw_key, raw_value in os.environ.items():
            key = str(raw_key).upper()
            if key in allowed_keys:
                effective[key] = "" if raw_value is None else str(raw_value)

        for item in items:
            key = str(item.get("key", "")).strip().upper()
            if key not in allowed_keys:
                continue
            value = "" if item.get("value") is None else str(item.get("value"))
            if value == mask_token:
                continue
            effective[key] = value

        return effective

    def _get_missing_notification_test_keys(
        self,
        channel: str,
        effective_map: Dict[str, str],
    ) -> List[str]:
        """Return missing keys for a channel, honoring alternative key groups."""
        groups = self._NOTIFICATION_REQUIRED_KEY_GROUPS.get(channel, ())
        if not groups:
            return []

        missing_by_group: List[List[str]] = []
        for group in groups:
            missing = [key for key in group if not (effective_map.get(key) or "").strip()]
            if not missing:
                return []
            missing_by_group.append(missing)

        if not missing_by_group:
            return []
        ranked_groups = []
        for group, missing in zip(groups, missing_by_group):
            present_count = len(group) - len(missing)
            ranked_groups.append((len(missing), -present_count, missing))
        ranked_groups.sort(key=lambda item: (item[0], item[1]))
        return ranked_groups[0][2]

    @staticmethod
    def _get_invalid_notification_test_config_message(
        channel: str,
        effective_map: Dict[str, str],
    ) -> Optional[str]:
        if channel == "ntfy":
            ntfy_url = (effective_map.get("NTFY_URL") or "").strip()
            if not ntfy_url:
                return None
            ntfy_server_url, ntfy_topic = resolve_ntfy_endpoint(ntfy_url)
            if ntfy_server_url and ntfy_topic:
                return None
            return "NTFY_URL 必须包含 topic path，例如 https://ntfy.sh/my-topic。"
        if channel == "gotify":
            gotify_url = (effective_map.get("GOTIFY_URL") or "").strip()
            if not gotify_url:
                return None
            if resolve_gotify_message_endpoint(gotify_url):
                return None
            return "GOTIFY_URL 必须是 Gotify server base URL，不包含 /message。"
        return None

    def _build_notification_config(self, effective_map: Dict[str, str]) -> Config:
        """Build an isolated Config instance from notification values."""
        kwargs: Dict[str, Any] = {"stock_list": []}
        for key, (attr, value_type) in self._NOTIFICATION_TEST_KEY_MAP.items():
            if key not in effective_map:
                continue
            if key == "DISCORD_CHANNEL_ID" and (effective_map.get("DISCORD_MAIN_CHANNEL_ID") or "").strip():
                continue
            raw_value = effective_map.get(key, "")
            kwargs[attr] = self._parse_notification_test_value(key, raw_value, value_type)
        return Config(**kwargs)

    def _parse_notification_test_value(self, key: str, value: str, value_type: str) -> Any:
        if value_type == "csv":
            return self._split_csv(value)
        if value_type == "bool":
            return parse_env_bool(value, default=True)
        if value_type == "int":
            defaults = {
                "WECHAT_MAX_BYTES": 4000,
                "FEISHU_MAX_BYTES": 20000,
                "DISCORD_MAX_WORDS": 2000,
            }
            return parse_env_int(value, defaults.get(key, 0), field_name=key, minimum=1)
        stripped = (value or "").strip()
        return stripped or None

    def _dispatch_notification_test(
        self,
        *,
        channel: str,
        config: Config,
        effective_map: Dict[str, str],
        title: str,
        content: str,
        timeout_seconds: float,
    ) -> Dict[str, Any]:
        from src.notification_sender import (
            AstrbotSender,
            CustomWebhookSender,
            DiscordSender,
            EmailSender,
            FeishuSender,
            GotifySender,
            NtfySender,
            PushoverSender,
            PushplusSender,
            Serverchan3Sender,
            SlackSender,
            TelegramSender,
            WechatSender,
            DingtalkSender,
        )

        started_at = time.perf_counter()
        target = self._resolve_notification_test_target(channel, effective_map)
        titled_content = self._build_notification_test_content(title, content)

        if channel == "custom":
            attempts = CustomWebhookSender(config).test_custom_webhooks(
                titled_content,
                timeout_seconds=timeout_seconds,
            )
            latency_ms = int((time.perf_counter() - started_at) * 1000)
            success_count = sum(1 for attempt in attempts if bool(attempt.get("success")))
            total_count = len(attempts)
            success = success_count > 0
            if success_count == total_count and total_count > 0:
                message = f"自定义 Webhook 通知测试成功（{success_count}/{total_count}）"
            elif success_count > 0:
                message = f"自定义 Webhook 通知测试部分成功（{success_count}/{total_count}）"
            else:
                message = f"自定义 Webhook 通知测试失败（{success_count}/{total_count}）"
            return self._build_notification_test_result(
                success=success,
                message=message,
                error_code=None if success else "send_failed",
                stage="notification_send",
                retryable=any(bool(attempt.get("retryable")) for attempt in attempts),
                latency_ms=latency_ms,
                attempts=attempts,
            )

        dispatch = {
            "wechat": lambda: WechatSender(config).send_to_wechat(titled_content, timeout_seconds=timeout_seconds),
            "dingtalk": lambda: DingtalkSender(config).send_to_dingtalk(titled_content, title="Test Message", timeout_seconds=timeout_seconds),
            "feishu": lambda: FeishuSender(config).send_to_feishu(titled_content, timeout_seconds=timeout_seconds),
            "telegram": lambda: TelegramSender(config).send_to_telegram(titled_content, timeout_seconds=timeout_seconds),
            "email": lambda: EmailSender(config).send_to_email(content, subject=title, timeout_seconds=timeout_seconds),
            "pushover": lambda: PushoverSender(config).send_to_pushover(content, title=title, timeout_seconds=timeout_seconds),
            "ntfy": lambda: NtfySender(config).send_to_ntfy(content, title=title, timeout_seconds=timeout_seconds),
            "gotify": lambda: GotifySender(config).send_to_gotify(content, title=title, timeout_seconds=timeout_seconds),
            "pushplus": lambda: PushplusSender(config).send_to_pushplus(content, title=title, timeout_seconds=timeout_seconds),
            "serverchan3": lambda: Serverchan3Sender(config).send_to_serverchan3(content, title=title, timeout_seconds=timeout_seconds),
            "discord": lambda: DiscordSender(config).send_to_discord(titled_content, timeout_seconds=timeout_seconds),
            "slack": lambda: SlackSender(config).send_to_slack(titled_content, timeout_seconds=timeout_seconds),
            "astrbot": lambda: AstrbotSender(config).send_to_astrbot(titled_content, timeout_seconds=timeout_seconds),
        }

        ok = bool(dispatch[channel]())
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        attempt = {
            "channel": channel,
            "success": ok,
            "message": "通知测试发送成功" if ok else "通知测试发送失败",
            "target": target,
            "error_code": None if ok else "send_failed",
            "stage": "notification_send",
            "retryable": False,
            "latency_ms": latency_ms,
        }
        return self._build_notification_test_result(
            success=ok,
            message=f"{channel} 通知测试成功" if ok else f"{channel} 通知测试失败",
            error_code=None if ok else "send_failed",
            stage="notification_send",
            retryable=False,
            latency_ms=latency_ms,
            attempts=[attempt],
        )

    @staticmethod
    def _build_notification_test_content(title: str, content: str) -> str:
        title = title.strip()
        content = content.strip()
        return f"{title}\n\n{content}" if title else content

    def _resolve_notification_test_target(self, channel: str, effective_map: Dict[str, str]) -> str:
        for key in self._NOTIFICATION_TEST_TARGET_KEYS.get(channel, ()):
            raw_value = (effective_map.get(key) or "").strip()
            if not raw_value:
                continue
            if key == "CUSTOM_WEBHOOK_URLS":
                first_url = self._split_csv(raw_value)[0] if self._split_csv(raw_value) else ""
                return self._mask_notification_target(first_url, source_key=key)
            return self._mask_notification_target(raw_value, source_key=key)
        return channel

    @classmethod
    def _build_notification_test_result(
        cls,
        *,
        success: bool,
        message: str,
        error_code: Optional[str],
        stage: Optional[str],
        retryable: bool,
        latency_ms: Optional[int],
        attempts: Sequence[Dict[str, Any]],
    ) -> Dict[str, Any]:
        sanitized_attempts = [cls._sanitize_notification_attempt(attempt) for attempt in attempts]
        return {
            "success": success,
            "message": cls._sanitize_notification_text(message),
            "error_code": error_code,
            "stage": stage,
            "retryable": retryable,
            "latency_ms": latency_ms,
            "attempts": sanitized_attempts,
        }

    @classmethod
    def _sanitize_notification_attempt(cls, attempt: Dict[str, Any]) -> Dict[str, Any]:
        sanitized = dict(attempt)
        if "message" in sanitized:
            sanitized["message"] = cls._sanitize_notification_text(sanitized["message"])
        if "target" in sanitized:
            sanitized["target"] = cls._mask_notification_target(str(sanitized.get("target") or ""))
        return sanitized

    @classmethod
    def _sanitize_notification_text(cls, text: Any) -> str:
        sanitized = cls._sanitize_llm_error_text(text)
        if not sanitized:
            return ""
        sanitized = re.sub(r"(?i)(bearer\s+)[a-z0-9._\-:]+", r"\1[REDACTED]", sanitized)
        sanitized = re.sub(r"(?i)(token|secret|password|sendkey)([=:]\s*)[^\s,;&]+", r"\1\2[REDACTED]", sanitized)
        sanitized = re.sub(
            r"https?://[^\s]+",
            lambda match: cls._mask_notification_target(match.group(0)),
            sanitized,
        )
        return sanitized[:300]

    @staticmethod
    def _mask_notification_target(target: str, *, source_key: Optional[str] = None) -> str:
        value = (target or "").strip()
        if not value:
            return ""
        source_key_upper = (source_key or "").upper()
        sensitive_source = any(
            marker in source_key_upper
            for marker in ("TOKEN", "PASSWORD", "SECRET", "SENDKEY", "USER_KEY", "API_KEY")
        )
        parsed = urlparse(value)
        if not parsed.scheme or not parsed.netloc:
            if sensitive_source:
                return "***"
            if len(value) > 10:
                return f"{value[:3]}***{value[-2:]}"
            return value

        safe_netloc = parsed.netloc.rsplit("@", 1)[-1]
        safe_segments: List[str] = []
        path_segments = parsed.path.split("/")
        last_non_empty_index = next(
            (index for index in range(len(path_segments) - 1, -1, -1) if path_segments[index]),
            -1,
        )
        for index, segment in enumerate(path_segments):
            if not segment:
                safe_segments.append(segment)
                continue
            lower = segment.lower()
            looks_secret = (
                (source_key_upper == "NTFY_URL" and index == last_non_empty_index)
                or
                len(segment) >= 16
                or lower.startswith("bot")
                or "token" in lower
                or "sendkey" in lower
                or "secret" in lower
                or re.search(r"[a-zA-Z].*\d|\d.*[a-zA-Z]", segment) is not None and len(segment) >= 10
            )
            if looks_secret:
                safe_segments.append("***")
            else:
                safe_segments.append(segment)

        query = ""
        if parsed.query:
            query = "&".join(
                f"{part.split('=', 1)[0]}=***" if "=" in part else "***"
                for part in parsed.query.split("&")
                if part
            )
        return urlunparse(parsed._replace(netloc=safe_netloc, path="/".join(safe_segments), query=query, fragment=""))

    @staticmethod
    def _classify_notification_exception(exc: Exception) -> Tuple[str, bool]:
        if isinstance(exc, requests.exceptions.Timeout):
            return "timeout", True
        if isinstance(exc, requests.exceptions.ConnectionError):
            return "network_error", True
        if isinstance(exc, requests.exceptions.RequestException):
            return "network_error", True
        return "unexpected_error", False

    @staticmethod
    def _setup_check(
        key: str,
        title: str,
        category: str,
        required: bool,
        status: str,
        message: str,
        next_step: Optional[str] = None,
    ) -> Dict[str, Any]:
        return {
            "key": key,
            "title": title,
            "category": category,
            "required": required,
            "status": status,
            "message": message,
            "next_step": next_step,
        }

    @staticmethod
    def _is_setup_relevant_env_key(key: str) -> bool:
        if key in {
            "STOCK_LIST",
            "DATABASE_PATH",
            "LITELLM_CONFIG",
            "LITELLM_MODEL",
            "LITELLM_FALLBACK_MODELS",
            "AGENT_LITELLM_MODEL",
            "VISION_MODEL",
            "OPENAI_BASE_URL",
            "OLLAMA_API_BASE",
            "FEISHU_STREAM_ENABLED",
        }:
            return True
        prefixes = (
            "LLM_",
            "GEMINI_",
            "OPENAI_",
            "ANTHROPIC_",
            "DEEPSEEK_",
            "OLLAMA_",
            "FEISHU_",
            "TELEGRAM_",
            "EMAIL_",
            "DISCORD_",
            "SLACK_",
            "DINGTALK_",
            "WECHAT_",
            "PUSHOVER_",
            "NTFY_",
            "GOTIFY_",
            "PUSHPLUS_",
            "SERVERCHAN",
            "CUSTOM_WEBHOOK",
            "WECOM_",
            "ASTRBOT_",
        )
        return key.startswith(prefixes) or key.endswith("_API_KEY") or key.endswith("_API_KEYS")

    def _build_setup_effective_config_map(self) -> Dict[str, str]:
        """Combine saved `.env` values with injected runtime env values for status checks."""
        saved_map = self._build_display_config_map(self._manager.read_config_map())
        effective_map = dict(saved_map)
        registered_keys = {key.upper() for key in get_registered_field_keys()}

        for raw_key, raw_value in os.environ.items():
            key = str(raw_key).upper()
            value = "" if raw_value is None else str(raw_value)
            if key in registered_keys or self._is_setup_relevant_env_key(key):
                effective_map[key] = value

        return self._build_display_config_map(effective_map)

    def _build_generation_backend_base_map(self) -> Dict[str, str]:
        """Build generation backend status config with saved values taking precedence."""
        saved_map = self._build_display_config_map(self._manager.read_config_map())
        effective_map = dict(saved_map)
        registered_keys = {key.upper() for key in get_registered_field_keys()}

        for raw_key, raw_value in os.environ.items():
            key = str(raw_key).upper()
            if key in effective_map:
                continue
            value = "" if raw_value is None else str(raw_value)
            if key in registered_keys or self._is_setup_relevant_env_key(key):
                effective_map[key] = value

        return self._build_display_config_map(effective_map)

    def _build_generation_backend_effective_map(
        self,
        *,
        items: Sequence[Dict[str, str]],
        mask_token: str,
    ) -> Dict[str, str]:
        """Merge saved/runtime config with unsaved status/smoke preview items."""
        effective_map = self._build_generation_backend_base_map()
        saved_map = self._build_display_config_map(self._manager.read_config_map())

        for item in self._filter_generation_backend_items(items):
            key = str(item.get("key", "")).strip().upper()
            if not key:
                continue
            value = "" if item.get("value") is None else str(item.get("value"))
            field_schema = get_field_definition(key, value)
            if bool(field_schema.get("is_sensitive", False)) and value == mask_token:
                if key in saved_map:
                    continue
            effective_map[key] = value

        return self._build_display_config_map(effective_map)

    @staticmethod
    def _has_any_config_value(effective_map: Dict[str, str], keys: Sequence[str]) -> bool:
        return any((effective_map.get(key) or "").strip() for key in keys)

    @staticmethod
    def _has_valid_ntfy_endpoint(effective_map: Dict[str, str]) -> bool:
        ntfy_server_url, ntfy_topic = resolve_ntfy_endpoint(effective_map.get("NTFY_URL"))
        return bool(ntfy_server_url and ntfy_topic)

    @staticmethod
    def _has_valid_gotify_config(effective_map: Dict[str, str]) -> bool:
        return bool(
            resolve_gotify_message_endpoint(effective_map.get("GOTIFY_URL"))
            and (effective_map.get("GOTIFY_TOKEN") or "").strip()
        )
