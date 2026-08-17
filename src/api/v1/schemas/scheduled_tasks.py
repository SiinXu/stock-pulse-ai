"""API contracts for deterministic persisted scheduled tasks."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


CalendarMarket = Literal["cn", "hk", "us", "jp", "kr", "tw"]
ReportType = Literal["brief", "simple", "detailed", "full"]


class DailyScheduleRequest(BaseModel):
    """Daily wall-clock schedule shared by supported task schemas."""

    kind: Literal["daily"] = "daily"
    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(min_length=1, max_length=64)
    calendar_market: CalendarMarket
    non_trading_day_policy: Literal["skip", "run"] = "skip"

    model_config = ConfigDict(extra="forbid", strict=True)


class StockAnalysisScheduledPayload(BaseModel):
    """Version-one stock-analysis execution payload."""

    stock_code: str = Field(min_length=1, max_length=32)
    report_type: ReportType = "detailed"
    notify: bool = True

    model_config = ConfigDict(extra="forbid", strict=True)


class ResearchScheduledPayload(BaseModel):
    """Schema-v2 single-symbol research payload."""

    stock_code: str = Field(min_length=1, max_length=32)
    notify: bool = True

    model_config = ConfigDict(extra="forbid", strict=True)


class ScheduledTaskCreateRequest(BaseModel):
    """Request body for a supported scheduled definition."""

    schema_version: Literal[1, 2] = 1
    name: str = Field(min_length=1, max_length=128)
    task_type: Literal[
        "stock_analysis",
        "research_brief",
        "risk_check",
    ] = "stock_analysis"
    schedule: DailyScheduleRequest
    payload: Union[ResearchScheduledPayload, StockAnalysisScheduledPayload]
    enabled: bool = True
    max_attempts: int = Field(default=1, ge=1, le=3)

    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="before")
    @classmethod
    def select_versioned_payload_model(cls, value):
        """Preserve the v1 default while keeping the payload union strict."""
        if not isinstance(value, dict):
            return value
        task_type = value.get("task_type", "stock_analysis")
        payload = value.get("payload")
        if task_type != "stock_analysis" or not isinstance(payload, dict):
            return value
        if "report_type" in payload:
            return value
        normalized = dict(value)
        normalized["payload"] = {**payload, "report_type": "detailed"}
        return normalized

    @model_validator(mode="after")
    def validate_versioned_task_payload(self):
        """Keep schema, task type, and payload interpretation inseparable."""
        if self.task_type == "stock_analysis":
            if self.schema_version != 1:
                raise ValueError("stock_analysis requires schema_version 1")
            if not isinstance(self.payload, StockAnalysisScheduledPayload):
                raise ValueError(
                    "stock_analysis requires a stock-analysis payload"
                )
        else:
            if self.schema_version != 2:
                raise ValueError("research tasks require schema_version 2")
            if not isinstance(self.payload, ResearchScheduledPayload):
                raise ValueError("research tasks require a research payload")
        return self


class ScheduledTaskItem(BaseModel):
    """Fully understood supported scheduled definition."""

    compatibility: Literal["supported"] = "supported"
    id: str
    schema_version: int
    name: str
    task_type: str
    schedule: DailyScheduleRequest
    payload: Union[ResearchScheduledPayload, StockAnalysisScheduledPayload]
    enabled: bool
    max_attempts: int
    next_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", strict=True)


class UnsupportedScheduledTaskItem(BaseModel):
    """Opaque projection of a definition written by a newer application."""

    compatibility: Literal["unsupported_schema"] = "unsupported_schema"
    id: str
    schema_version: int
    name: str
    enabled: bool
    next_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", strict=True)


ScheduledTaskDefinitionItem = Annotated[
    Union[ScheduledTaskItem, UnsupportedScheduledTaskItem],
    Field(discriminator="compatibility"),
]


class ScheduledTaskListResponse(BaseModel):
    """Collection response containing supported and opaque definitions."""

    items: List[ScheduledTaskDefinitionItem] = Field(default_factory=list)
    total: int

    model_config = ConfigDict(extra="forbid", strict=True)


class ScheduledTaskRunItem(BaseModel):
    """Durable aggregate projection for one scheduled occurrence."""

    id: str
    task_id: str
    scheduled_for: datetime
    status: Literal[
        "dispatching",
        "running",
        "retry_wait",
        "succeeded",
        "failed",
        "skipped",
        "interrupted",
    ]
    attempt_count: int
    dispatch_failure_count: int
    execution_task_ids: List[str] = Field(default_factory=list)
    result_refs: List[str] = Field(default_factory=list)
    notification_status: Optional[
        Literal[
            "not_requested",
            "ok",
            "degraded",
            "failed",
            "skipped",
            "not_configured",
            "unknown",
        ]
    ] = None
    notification_channels: List[str] = Field(default_factory=list)
    notification_failed_channels: List[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    next_attempt_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(extra="forbid", strict=True)


class ScheduledTaskRunListResponse(BaseModel):
    """Collection response for one definition's occurrence history."""

    items: List[ScheduledTaskRunItem] = Field(default_factory=list)
    total: int

    model_config = ConfigDict(extra="forbid", strict=True)


class ScheduledTaskStatusResponse(BaseModel):
    """Definition compatibility projection and latest occurrence."""

    task: ScheduledTaskDefinitionItem
    latest_run: Optional[ScheduledTaskRunItem] = None

    model_config = ConfigDict(extra="forbid", strict=True)


class ScheduledTaskTodayItem(BaseModel):
    """One scheduled occurrence on the requested local calendar date."""

    task: ScheduledTaskDefinitionItem
    scheduled_for: datetime
    status: Literal[
        "scheduled",
        "dispatching",
        "running",
        "retry_wait",
        "succeeded",
        "failed",
        "skipped",
        "interrupted",
    ]
    run: Optional[ScheduledTaskRunItem] = None

    model_config = ConfigDict(extra="forbid", strict=True)


class ScheduledTaskTodayResponse(BaseModel):
    """Timezone-aware read projection for today's scheduled occurrences."""

    date: date
    timezone: str
    generated_at: datetime
    items: List[ScheduledTaskTodayItem] = Field(default_factory=list)
    total: int

    model_config = ConfigDict(extra="forbid", strict=True)
