# -*- coding: utf-8 -*-
"""
===================================
股票数据相关模型
===================================

职责：
1. 定义股票实时行情模型
2. 定义历史 K 线数据模型
"""

from datetime import date
from typing import Annotated, List, Literal, Optional

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    model_validator,
)


class StockQuote(BaseModel):
    """股票实时行情"""
    
    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    current_price: float = Field(..., description="当前价格")
    change: Optional[float] = Field(None, description="涨跌额")
    change_percent: Optional[float] = Field(None, description="涨跌幅 (%)")
    open: Optional[float] = Field(None, description="开盘价")
    high: Optional[float] = Field(None, description="最高价")
    low: Optional[float] = Field(None, description="最低价")
    prev_close: Optional[float] = Field(None, description="昨收价")
    volume: Optional[float] = Field(None, description="成交量（股）")
    amount: Optional[float] = Field(None, description="成交额（元）")
    update_time: Optional[str] = Field(None, description="更新时间")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "current_price": 1800.00,
            "change": 15.00,
            "change_percent": 0.84,
            "open": 1785.00,
            "high": 1810.00,
            "low": 1780.00,
            "prev_close": 1785.00,
            "volume": 10000000,
            "amount": 18000000000,
            "update_time": "2024-01-01T15:00:00"
        }
    })


class KLineData(BaseModel):
    """K 线数据点"""
    
    date: str = Field(..., description="日期")
    open: float = Field(..., description="开盘价")
    high: float = Field(..., description="最高价")
    low: float = Field(..., description="最低价")
    close: float = Field(..., description="收盘价")
    volume: Optional[float] = Field(None, description="成交量")
    amount: Optional[float] = Field(None, description="成交额")
    change_percent: Optional[float] = Field(None, description="涨跌幅 (%)")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "date": "2024-01-01",
            "open": 1785.00,
            "high": 1810.00,
            "low": 1780.00,
            "close": 1800.00,
            "volume": 10000000,
            "amount": 18000000000,
            "change_percent": 0.84
        }
    })


MoneyFlowStatusValue = Literal[
    "disabled",
    "available",
    "partial",
    "not_supported",
    "fetch_failed",
    "empty",
    "stale",
    "fallback",
]
MoneyFlowMarket = Literal["cn", "hk", "us", "jp", "kr", "tw"]
MoneyFlowAmountScale = Literal[
    "unknown",
    "yuan",
    "thousand_yuan",
    "ten_thousand_yuan",
    "million_yuan",
]
MoneyFlowWarning = Annotated[str, Field(min_length=1, max_length=200)]


class MoneyFlowSourceAttempt(BaseModel):
    """Bounded public projection of one provider attempt."""

    provider: str = Field(min_length=1, max_length=160)
    status: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    latency_ms: Optional[FiniteFloat] = Field(default=None, ge=0, le=1e9)
    provider_date: Optional[date] = None
    error_code: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=120,
        pattern=r"^[A-Za-z0-9_.-]+$",
    )

    model_config = ConfigDict(extra="forbid")


class MoneyFlowSnapshotResponse(BaseModel):
    """Strict finite snapshot exposed by the Stock Details API."""

    code: str = Field(min_length=1, max_length=32)
    date: date
    source: str = Field(min_length=1, max_length=160)
    market: MoneyFlowMarket
    main_net_inflow: Optional[FiniteFloat] = Field(default=None, ge=-1e18, le=1e18)
    super_large_net_inflow: Optional[FiniteFloat] = Field(default=None, ge=-1e18, le=1e18)
    large_net_inflow: Optional[FiniteFloat] = Field(default=None, ge=-1e18, le=1e18)
    medium_net_inflow: Optional[FiniteFloat] = Field(default=None, ge=-1e18, le=1e18)
    small_net_inflow: Optional[FiniteFloat] = Field(default=None, ge=-1e18, le=1e18)
    main_net_inflow_ratio: Optional[FiniteFloat] = Field(default=None, ge=-100, le=100)
    super_large_net_inflow_ratio: Optional[FiniteFloat] = Field(default=None, ge=-100, le=100)
    large_net_inflow_ratio: Optional[FiniteFloat] = Field(default=None, ge=-100, le=100)
    medium_net_inflow_ratio: Optional[FiniteFloat] = Field(default=None, ge=-100, le=100)
    small_net_inflow_ratio: Optional[FiniteFloat] = Field(default=None, ge=-100, le=100)
    main_net_inflow_5d: Optional[FiniteFloat] = Field(default=None, ge=-1e18, le=1e18)
    main_net_inflow_10d: Optional[FiniteFloat] = Field(default=None, ge=-1e18, le=1e18)
    close: Optional[FiniteFloat] = Field(default=None, ge=0, le=1e12)
    change_pct: Optional[FiniteFloat] = Field(default=None, ge=-100, le=1000)
    unit: str = Field(pattern=r"^(unknown|[A-Z]{3})$")
    amount_scale: MoneyFlowAmountScale
    bucket_definition: str = Field(min_length=1, max_length=1000)
    as_of: AwareDatetime
    requested_days: int = Field(ge=1, le=20)
    observed_days: int = Field(ge=1, le=20)
    completeness: Literal["complete", "partial"]
    attitude: Literal["inflow", "outflow", "neutral", "unknown"]
    calibration_note: str = Field(min_length=1, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_calibration_and_coverage(self) -> "MoneyFlowSnapshotResponse":
        amount_fields = (
            self.main_net_inflow,
            self.super_large_net_inflow,
            self.large_net_inflow,
            self.medium_net_inflow,
            self.small_net_inflow,
            self.main_net_inflow_5d,
            self.main_net_inflow_10d,
        )
        calibrated = self.unit != "unknown" and self.amount_scale != "unknown"
        if (self.unit == "unknown") != (self.amount_scale == "unknown"):
            raise ValueError("money-flow currency and scale must be calibrated together")
        if not calibrated and any(value is not None for value in amount_fields):
            raise ValueError("uncalibrated money-flow amounts must not be exposed")
        if self.observed_days > self.requested_days:
            raise ValueError("observed_days exceeds requested_days")
        if self.completeness == "complete" and self.observed_days != self.requested_days:
            raise ValueError("complete coverage must match the requested window")
        if self.completeness == "partial" and self.observed_days >= self.requested_days:
            raise ValueError("partial coverage must be shorter than the requested window")
        return self


class MoneyFlowViewResponse(BaseModel):
    """User-facing SmartMoney / main-force money-flow view (Issue #989)."""

    schema_version: Literal["money_flow_view/1.0"]
    stock_code: str = Field(min_length=1, max_length=32, description="Canonical stock code")
    enabled: bool = Field(..., description="Whether SMARTMONEY_ENABLED is on")
    status: MoneyFlowStatusValue
    requested_days: int = Field(..., ge=1, le=20, description="Requested history window")
    fetched_at: Optional[AwareDatetime] = Field(None, description="UTC fetch timestamp")
    as_of: Optional[AwareDatetime] = Field(None, description="Observation as-of timestamp")
    provider_date: Optional[date] = Field(None, description="Provider session date")
    age_days: Optional[int] = Field(None, ge=0, description="Session age in days")
    source: Optional[str] = Field(None, min_length=1, max_length=160)
    source_chain: List[MoneyFlowSourceAttempt] = Field(
        default_factory=list, max_length=16, description="Provider attempt chain"
    )
    market: Optional[MoneyFlowMarket] = None
    error_code: Optional[str] = Field(
        None, min_length=1, max_length=120, pattern=r"^[A-Za-z0-9_.-]+$"
    )
    warnings: List[MoneyFlowWarning] = Field(default_factory=list, max_length=16)
    cache_state: Optional[Literal["miss", "fresh", "stale"]] = None
    fallback_from: Optional[str] = Field(None, min_length=1, max_length=160)
    snapshot: Optional[MoneyFlowSnapshotResponse] = None
    message: Optional[str] = Field(None, min_length=1, max_length=500)
    disclaimer: str = Field(min_length=1, max_length=1000)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_status_payload(self) -> "MoneyFlowViewResponse":
        data_statuses = {"available", "partial", "stale", "fallback"}
        if (not self.enabled and self.status != "disabled") or (
            self.enabled and self.status == "disabled"
        ):
            raise ValueError("money-flow enabled flag and status disagree")
        if (self.snapshot is not None) != (self.status in data_statuses):
            raise ValueError("money-flow snapshot and status disagree")
        if self.snapshot is not None and (
            self.as_of is None or self.source is None or self.provider_date is None
        ):
            raise ValueError("data-bearing money-flow view requires provenance")
        if self.snapshot is not None and (
            self.snapshot.code != self.stock_code
            or self.snapshot.market != self.market
            or self.snapshot.requested_days != self.requested_days
            or self.snapshot.date != self.provider_date
        ):
            raise ValueError("money-flow view and snapshot identity disagree")
        if self.status == "fallback" and self.fallback_from is None:
            raise ValueError("fallback money-flow view requires provenance")
        if self.status == "stale" and (self.age_days is None or self.age_days < 1):
            raise ValueError("stale money-flow view requires positive age")
        if self.status in {"available", "partial"} and self.age_days != 0:
            raise ValueError("current money-flow view requires zero age")
        if self.status in {"not_supported", "fetch_failed", "empty"} and self.error_code is None:
            raise ValueError("unavailable money-flow view requires an error code")
        return self


class ExtractItem(BaseModel):
    """单条提取结果（代码、名称、置信度）"""

    code: Optional[str] = Field(None, description="股票代码，None 表示解析失败")
    name: Optional[str] = Field(None, description="股票名称（如有）")
    confidence: str = Field("medium", description="置信度：high/medium/low")


class ExtractFromImageResponse(BaseModel):
    """图片股票代码提取响应"""

    codes: List[str] = Field(..., description="提取的股票代码（已去重，向后兼容）")
    items: List[ExtractItem] = Field(default_factory=list, description="提取结果明细（代码+名称+置信度）")
    raw_text: Optional[str] = Field(None, description="原始 LLM 响应（调试用）")


class StockHistoryResponse(BaseModel):
    """股票历史行情响应"""
    
    stock_code: str = Field(..., description="股票代码")
    stock_name: Optional[str] = Field(None, description="股票名称")
    period: str = Field(..., description="K 线周期")
    data: List[KLineData] = Field(default_factory=list, description="K 线数据列表")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "stock_code": "600519",
            "stock_name": "贵州茅台",
            "period": "daily",
            "data": []
        }
    })


# ---------------------------------------------------------------------------
# Field-level data trust (Issue #1129)
# ---------------------------------------------------------------------------

FieldTrustStaleness = Literal["fresh", "stale", "unknown"]
FieldTrustOrigin = Literal["primary", "supplement", "unknown"]
FieldTrustStatus = Literal["ok", "degraded", "unavailable"]


class FieldTrustEntry(BaseModel):
    """Trust verdict for one quote field."""

    field: str = Field(min_length=1, max_length=64)
    value: Optional[FiniteFloat] = Field(default=None, description="Current field value")
    source: Optional[str] = Field(default=None, min_length=1, max_length=160)
    origin: FieldTrustOrigin = Field(
        default="unknown",
        description="Whether the field came from the primary provider or a supplement",
    )
    provider_timestamp: Optional[str] = Field(default=None, max_length=64)
    stale_seconds: Optional[int] = Field(default=None, ge=0)
    is_stale: Optional[bool] = None
    staleness: FieldTrustStaleness = Field(
        default="unknown",
        description="Staleness verdict; unknown must be rendered as degraded, never trusted",
    )
    conflict: bool = Field(
        default=False, description="True when providers disagreed on this field"
    )

    model_config = ConfigDict(extra="forbid")


class FieldTrustConflictValue(BaseModel):
    """One provider observation inside a conflict finding."""

    provider: str = Field(min_length=1, max_length=160)
    value: FiniteFloat

    model_config = ConfigDict(extra="forbid")


class FieldTrustConflict(BaseModel):
    """Cross-provider divergence on one field (never silently resolved)."""

    field: str = Field(min_length=1, max_length=64)
    severity: str = Field(default="warn", min_length=1, max_length=32)
    relative_difference: Optional[FiniteFloat] = Field(default=None, ge=0)
    threshold: Optional[FiniteFloat] = Field(default=None, ge=0)
    values: List[FieldTrustConflictValue] = Field(default_factory=list, max_length=16)

    model_config = ConfigDict(extra="forbid")


class FieldTrustConflictCheck(BaseModel):
    """Whether a cross-source comparison actually ran for a provider pair."""

    primary_provider: Optional[str] = Field(default=None, max_length=160)
    secondary_provider: Optional[str] = Field(default=None, max_length=160)
    status: Literal["evaluated", "skipped"]
    reason: Optional[str] = Field(default=None, max_length=120)

    model_config = ConfigDict(extra="forbid")


class StockFieldTrustResponse(BaseModel):
    """Structured field-level trust view for a stock quote (Issue #1129)."""

    schema_version: Literal["field_trust_view/1.0"]
    stock_code: str = Field(min_length=1, max_length=32)
    status: FieldTrustStatus = Field(
        description=(
            "ok = every covered field fresh, attributed, conflict-free; "
            "degraded = stale/conflicting/unattributed fields present; "
            "unavailable = no quote could be fetched"
        )
    )
    metadata_present: bool = Field(
        description="False when the quote carried no field-level trust metadata"
    )
    quote_source: Optional[str] = Field(default=None, max_length=160)
    fetched_at: Optional[str] = Field(default=None, max_length=64)
    provider_timestamp: Optional[str] = Field(default=None, max_length=64)
    stale_seconds: Optional[int] = Field(default=None, ge=0)
    is_stale: Optional[bool] = None
    fallback_from: Optional[str] = Field(default=None, max_length=160)
    data_quality: Optional[str] = Field(default=None, max_length=32)
    missing_fields: List[str] = Field(default_factory=list, max_length=64)
    fields: List[FieldTrustEntry] = Field(default_factory=list, max_length=64)
    conflicts: List[FieldTrustConflict] = Field(default_factory=list, max_length=64)
    conflict_checks: List[FieldTrustConflictCheck] = Field(
        default_factory=list, max_length=32
    )
    message: Optional[str] = Field(default=None, max_length=500)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_trust_invariants(self) -> "StockFieldTrustResponse":
        if self.status == "unavailable":
            if self.fields or self.metadata_present:
                raise ValueError("unavailable trust view must not carry field verdicts")
            return self
        if not self.metadata_present and self.status == "ok":
            raise ValueError("trust view without metadata must not report ok")
        degraded_signals = (
            any(
                entry.staleness != "fresh" or entry.conflict or entry.source is None
                for entry in self.fields
            )
            or bool(self.conflicts)
            or not self.fields
        )
        if self.status == "ok" and degraded_signals:
            raise ValueError("ok trust view must not contain degraded field verdicts")
        if self.status == "degraded" and self.metadata_present and not degraded_signals:
            raise ValueError("degraded trust view requires a degradation signal")
        return self
