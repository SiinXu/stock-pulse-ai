# -*- coding: utf-8 -*-
"""System configuration API schemas."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from api.v1.schemas.common import ErrorDetailsCompatibilityModel

LLMCapabilityCheck = Literal["json", "tools", "vision", "stream"]
GenerationBackendSmokeMode = Literal["text", "json"]
GenerationBackendHealthStatus = Literal["not_tested", "passed", "failed", "skipped"]
NotificationTestChannel = Literal[
    "wechat",
    "feishu",
    "telegram",
    "email",
    "pushover",
    "ntfy",
    "gotify",
    "pushplus",
    "serverchan3",
    "custom",
    "discord",
    "slack",
    "astrbot",
]


class SystemConfigOption(BaseModel):
    """Select option metadata for frontend rendering."""

    label: str
    value: str


class SystemConfigDocLink(BaseModel):
    """Documentation link metadata for field help panels."""

    label: str
    href: str


class SystemConfigCondition(BaseModel):
    """One condition in an AND-composed configuration field contract."""

    key: str
    operator: Literal["equals", "notEquals", "in", "notEmpty"]
    value: Optional[str | List[str]] = None


class SystemConfigFieldContract(BaseModel):
    """Authoritative conditional behavior for a configuration field."""

    requirement: Literal["required", "optional", "inherited"]
    required_when: Optional[List[SystemConfigCondition]] = None
    visible_when: Optional[List[SystemConfigCondition]] = None
    enabled_when: Optional[List[SystemConfigCondition]] = None
    requires_connection_test: Optional[bool] = None


class LLMConnectionFieldSchema(BaseModel):
    """Schema for one dynamic per-Connection configuration field."""

    key: str
    env_suffix: Optional[str] = None
    data_type: Literal["string", "boolean", "array", "json"]
    is_sensitive: bool
    is_required: bool = Field(
        ...,
        deprecated=True,
        description=(
            "Deprecated unconditional compatibility projection; "
            "contract.requirement and required_when are authoritative"
        ),
    )
    contract: SystemConfigFieldContract


class LLMProviderCatalogEntry(BaseModel):
    """Authoritative model-service Provider metadata."""

    id: str
    label: str = Field(
        ...,
        deprecated=True,
        description="Deprecated Chinese compatibility label; use label_zh or label_en",
    )
    label_zh: str
    label_en: str
    protocol: str
    default_base_url: str
    credential_url: Optional[str] = None
    console_url: Optional[str] = None
    models_url: Optional[str] = None
    docs_url: Optional[str] = None
    capabilities: List[str] = Field(default_factory=list)
    requires_api_key: bool
    requires_base_url: bool
    supports_discovery: bool
    is_local: bool
    is_custom: bool


class LLMProviderCatalogResponse(BaseModel):
    """Provider metadata plus the shared dynamic Connection field contract."""

    providers: List[LLMProviderCatalogEntry]
    connection_fields: List[LLMConnectionFieldSchema]
    empty_api_key_hosts: List[str] = Field(default_factory=list)


class SystemConfigFieldSchema(BaseModel):
    """Metadata schema for a single config field."""

    key: str = Field(..., description="Configuration key name")
    title: Optional[str] = Field(None, description="Display title")
    description: Optional[str] = Field(None, description="Field description")
    category: Literal["base", "data_source", "ai_model", "notification", "system", "agent", "backtest", "uncategorized"]
    data_type: Literal["string", "integer", "number", "boolean", "array", "json", "time"]
    ui_control: Literal["text", "password", "number", "select", "textarea", "switch", "time"]
    is_sensitive: bool
    is_required: bool = Field(
        ...,
        deprecated=True,
        description="Deprecated compatibility flag; contract.requirement is authoritative when present",
    )
    is_editable: bool
    default_value: Optional[str] = None
    options: List[str | SystemConfigOption] = Field(default_factory=list)
    validation: Dict[str, Any] = Field(default_factory=dict)
    display_order: int
    help_key: Optional[str] = Field(None, description="Stable localization key for detailed help content")
    examples: List[str] = Field(default_factory=list, description="Safe example values for help panels")
    docs: List[SystemConfigDocLink] = Field(default_factory=list, description="Related documentation links")
    warning_codes: List[str] = Field(default_factory=list, description="Stable warning identifiers for help panels")
    contract: Optional[SystemConfigFieldContract] = Field(
        None,
        description="Authoritative requirement, condition, and connection-test metadata",
    )
    ui_placement: Optional[
        Literal[
            "model_access",
            "task_routing",
            "developer_diagnostics",
            "hidden_legacy",
        ]
    ] = Field(
        None,
        description="Dedicated settings surface that owns this field; null means generic rendering",
    )


class SystemConfigCategorySchema(BaseModel):
    """Category grouping metadata."""

    category: str
    title: str
    description: Optional[str] = None
    display_order: int
    fields: List[SystemConfigFieldSchema]


class SystemConfigSchemaResponse(BaseModel):
    """Metadata response for dynamic frontend rendering."""

    schema_version: str
    categories: List[SystemConfigCategorySchema]


class SystemConfigItem(BaseModel):
    """Config value entry with optional schema metadata."""

    model_config = ConfigDict(populate_by_name=True)

    key: str
    value: str
    raw_value_exists: bool
    is_masked: bool
    schema_: Optional[SystemConfigFieldSchema] = Field(default=None, alias="schema")


class SystemConfigResponse(BaseModel):
    """Read response for current configuration values."""

    config_version: str
    mask_token: str
    items: List[SystemConfigItem]
    configured_notification_channels: List[str] = Field(
        default_factory=list,
        description="Routable static channels detected from the current live runtime Config snapshot",
    )
    updated_at: Optional[str] = None


class SetupStatusCheck(BaseModel):
    """One first-run setup readiness check."""

    key: str
    title: str
    category: Literal["base", "ai_model", "agent", "notification", "system"]
    required: bool
    status: Literal["configured", "inherited", "optional", "needs_action"]
    message: str
    next_step: Optional[str] = None


class SetupStatusResponse(BaseModel):
    """Read-only first-run setup status."""

    is_complete: bool
    ready_for_smoke: bool
    required_missing_keys: List[str] = Field(default_factory=list)
    next_step_key: Optional[str] = None
    checks: List[SetupStatusCheck] = Field(default_factory=list)


class GenerationBackendStatus(BaseModel):
    """Cheap status for one generation backend.

    ``health_status`` and ``last_error_*`` describe the current status request
    or the explicit smoke-test request only; they are not persisted history.
    """

    backend_id: str
    backend_type: Literal["litellm", "local_cli"]
    provider_id: str
    available: bool
    health_status: GenerationBackendHealthStatus = "not_tested"
    supports_json: bool
    supports_tools: bool
    supports_stream: bool
    supports_vision: bool
    is_primary: bool
    fallback_target: Optional[str] = None
    max_concurrency: int
    usage_available: bool
    last_error_code: Optional[str] = None
    last_error_message: Optional[str] = None


class GenerationBackendStatusResponse(BaseModel):
    """Generation backend status payload."""

    primary_backend_id: str
    fallback_backend_id: Optional[str] = None
    primary: GenerationBackendStatus
    fallback: Optional[GenerationBackendStatus] = None
    backends: List[GenerationBackendStatus] = Field(default_factory=list)


class ExportSystemConfigResponse(BaseModel):
    """Export payload for raw `.env` backups."""

    content: str
    config_version: str
    updated_at: Optional[str] = None


class SystemConfigUpdateItem(BaseModel):
    """Single key-value update item."""

    key: str
    value: str


class GenerationBackendStatusPreviewRequest(BaseModel):
    """Unsaved-draft preview request for generation backend status."""

    items: List[SystemConfigUpdateItem] = Field(default_factory=list)
    mask_token: str = "******"


class TestGenerationBackendRequest(BaseModel):
    """Explicit generation backend smoke-test request."""

    backend_id: Optional[str] = None
    mode: GenerationBackendSmokeMode = "json"
    items: List[SystemConfigUpdateItem] = Field(default_factory=list)
    mask_token: str = "******"
    timeout_seconds: Optional[float] = Field(default=None, ge=1.0, le=3600.0)


class TestGenerationBackendResponse(BaseModel):
    """Generation backend smoke-test result."""

    success: bool
    mode: GenerationBackendSmokeMode
    message: str
    status: GenerationBackendStatus


class UpdateSystemConfigRequest(BaseModel):
    """Update request payload."""

    config_version: str
    mask_token: str = "******"
    reload_now: bool = True
    items: List[SystemConfigUpdateItem] = Field(..., min_length=1)


class UpdateSystemConfigResponse(BaseModel):
    """Update operation result payload."""

    success: bool
    config_version: str
    applied_count: int
    skipped_masked_count: int
    reload_triggered: bool
    updated_keys: List[str]
    warnings: List[str] = Field(default_factory=list)


class ValidateSystemConfigRequest(BaseModel):
    """Validation request payload."""

    items: List[SystemConfigUpdateItem] = Field(..., min_length=1)


class ImportSystemConfigRequest(BaseModel):
    """Import request payload for raw `.env` backups."""

    config_version: str
    content: str
    reload_now: bool = True


class ConfigValidationIssue(BaseModel):
    """Validation issue details."""

    key: str
    code: str
    message: str
    severity: Literal["error", "warning"]
    expected: Optional[str] = None
    actual: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class ValidateSystemConfigResponse(BaseModel):
    """Validation result payload."""

    valid: bool
    issues: List[ConfigValidationIssue]


class TestLLMChannelRequest(BaseModel):
    """Request payload for testing one LLM channel."""

    name: str = "channel"
    provider_id: Optional[str] = None
    protocol: str = "openai"
    base_url: str = ""
    api_key: str = ""
    models: List[str] = Field(default_factory=list)
    enabled: bool = True
    timeout_seconds: float = 20.0
    capability_checks: List[LLMCapabilityCheck] = Field(default_factory=list)
    use_saved_secret: bool = False


class LLMCapabilityCheckResult(BaseModel):
    """Runtime capability smoke result for one requested check."""

    status: Literal["passed", "failed", "skipped"]
    message: str
    error_code: Optional[str] = None
    stage: str
    retryable: bool = False
    latency_ms: Optional[int] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class TestLLMChannelResponse(BaseModel):
    """Response payload for one LLM channel connectivity test."""

    success: bool
    message: str
    error: Optional[str] = None
    error_code: Optional[str] = None
    stage: Optional[str] = None
    retryable: Optional[bool] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    resolved_protocol: Optional[str] = None
    resolved_model: Optional[str] = None
    latency_ms: Optional[int] = None
    capability_results: Dict[str, LLMCapabilityCheckResult] = Field(default_factory=dict)


class NotificationTestAttempt(BaseModel):
    """One notification delivery attempt result."""

    channel: NotificationTestChannel
    success: bool
    message: str
    target: Optional[str] = None
    error_code: Optional[str] = None
    stage: str = "notification_send"
    retryable: bool = False
    latency_ms: Optional[int] = None
    http_status: Optional[int] = None


class TestNotificationChannelRequest(BaseModel):
    """Request payload for testing one notification channel."""

    channel: NotificationTestChannel
    items: List[SystemConfigUpdateItem] = Field(default_factory=list)
    mask_token: str = "******"
    title: str = Field(default="StockPulse 通知测试", min_length=1, max_length=80)
    content: str = Field(default="这是一条来自 StockPulse Web 设置页的通知测试消息。", min_length=1, max_length=1000)
    timeout_seconds: float = Field(default=20.0, ge=1.0, le=120.0)


class TestNotificationChannelResponse(BaseModel):
    """Response payload for one notification channel connectivity test."""

    success: bool
    message: str
    error_code: Optional[str] = None
    stage: Optional[str] = None
    retryable: bool = False
    latency_ms: Optional[int] = None
    attempts: List[NotificationTestAttempt] = Field(default_factory=list)


class DiscoverLLMChannelModelsRequest(BaseModel):
    """Request payload for discovering models from one LLM channel."""

    name: str = "channel"
    provider_id: Optional[str] = None
    protocol: str = "openai"
    base_url: str = ""
    api_key: str = ""
    models: List[str] = Field(default_factory=list)
    timeout_seconds: float = 20.0
    use_saved_secret: bool = False


class DiscoverLLMChannelModelsResponse(BaseModel):
    """Response payload for one LLM channel model discovery request."""

    success: bool
    message: str
    error: Optional[str] = None
    error_code: Optional[str] = None
    stage: Optional[str] = None
    retryable: Optional[bool] = None
    details: Dict[str, Any] = Field(default_factory=dict)
    resolved_protocol: Optional[str] = None
    models: List[str] = Field(default_factory=list)
    latency_ms: Optional[int] = None


class SystemConfigValidationErrorResponse(ErrorDetailsCompatibilityModel):
    """Stable envelope for failed update validation."""

    error: str
    message: str
    params: Dict[str, List[ConfigValidationIssue]] = Field(default_factory=dict)
    trace_id: Optional[str] = None


class SystemConfigConflictResponse(ErrorDetailsCompatibilityModel):
    """Stable envelope for optimistic-lock conflicts."""

    error: str
    message: str
    params: Dict[str, str] = Field(default_factory=dict)
    trace_id: Optional[str] = None
