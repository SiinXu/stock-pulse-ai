"""API contracts for deterministic persisted scheduled tasks."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


CalendarMarket = Literal["cn", "hk", "us", "jp", "kr", "tw"]
ReportType = Literal["brief", "simple", "detailed", "full"]


class DailyScheduleRequest(BaseModel):
    """Version-one daily wall-clock schedule."""

    kind: Literal["daily"] = "daily"
    time: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(min_length=1, max_length=64)
    calendar_market: CalendarMarket
    non_trading_day_policy: Literal["skip", "run"] = "skip"

    model_config = ConfigDict(extra="forbid")


class StockAnalysisScheduledPayload(BaseModel):
    """Version-one stock-analysis execution payload."""

    stock_code: str = Field(min_length=1, max_length=32)
    report_type: ReportType = "detailed"
    notify: bool = True

    model_config = ConfigDict(extra="forbid")


class ScheduledTaskCreateRequest(BaseModel):
    """Request body for one version-one scheduled definition."""

    schema_version: Literal[1] = 1
    name: str = Field(min_length=1, max_length=128)
    task_type: Literal["stock_analysis"] = "stock_analysis"
    schedule: DailyScheduleRequest
    payload: StockAnalysisScheduledPayload
    enabled: bool = True
    max_attempts: int = Field(default=1, ge=1, le=3)

    model_config = ConfigDict(extra="forbid")


class ScheduledTaskItem(BaseModel):
    """Fully understood version-one scheduled definition."""

    compatibility: Literal["supported"] = "supported"
    id: str
    schema_version: int
    name: str
    task_type: str
    schedule: DailyScheduleRequest
    payload: StockAnalysisScheduledPayload
    enabled: bool
    max_attempts: int
    next_run_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


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


ScheduledTaskDefinitionItem = Annotated[
    Union[ScheduledTaskItem, UnsupportedScheduledTaskItem],
    Field(discriminator="compatibility"),
]


class ScheduledTaskListResponse(BaseModel):
    """Collection response containing supported and opaque definitions."""

    items: List[ScheduledTaskDefinitionItem] = Field(default_factory=list)
    total: int


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
    execution_task_ids: List[str] = Field(default_factory=list)
    result_refs: List[str] = Field(default_factory=list)
    error_code: Optional[str] = None
    next_attempt_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


class ScheduledTaskRunListResponse(BaseModel):
    """Collection response for one definition's occurrence history."""

    items: List[ScheduledTaskRunItem] = Field(default_factory=list)
    total: int


class ScheduledTaskStatusResponse(BaseModel):
    """Definition compatibility projection and latest occurrence."""

    task: ScheduledTaskDefinitionItem
    latest_run: Optional[ScheduledTaskRunItem] = None
