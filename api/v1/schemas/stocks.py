# -*- coding: utf-8 -*-
"""
===================================
股票数据相关模型
===================================

职责：
1. 定义股票实时行情模型
2. 定义历史 K 线数据模型
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


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


class MoneyFlowViewResponse(BaseModel):
    """User-facing SmartMoney / main-force money-flow view (Issue #989)."""

    schema_version: str = Field(..., description="money_flow_view schema version")
    stock_code: str = Field(..., description="Canonical stock code")
    enabled: bool = Field(..., description="Whether SMARTMONEY_ENABLED is on")
    status: str = Field(
        ...,
        description=(
            "disabled | available | partial | not_supported | fetch_failed | "
            "empty | stale | fallback"
        ),
    )
    requested_days: int = Field(..., ge=1, le=20, description="Requested history window")
    fetched_at: Optional[str] = Field(None, description="UTC fetch timestamp (ISO 8601)")
    as_of: Optional[str] = Field(None, description="Observation as-of timestamp (ISO 8601)")
    provider_date: Optional[str] = Field(None, description="Provider session date YYYY-MM-DD")
    age_days: Optional[int] = Field(None, description="Session age in days")
    source: Optional[str] = Field(None, description="Primary data source label")
    source_chain: List[Dict[str, Any]] = Field(
        default_factory=list, description="Provider attempt chain"
    )
    market: Optional[str] = Field(None, description="Market tag (cn/hk/us/...)")
    error_code: Optional[str] = Field(None, description="Machine-readable failure code")
    warnings: List[str] = Field(default_factory=list, description="Quality / calibration warnings")
    cache_state: Optional[str] = Field(None, description="miss | fresh | stale")
    fallback_from: Optional[str] = Field(None, description="Fallback provenance when applicable")
    snapshot: Optional[Dict[str, Any]] = Field(
        None, description="Normalized bucket ratios/amounts when data-bearing"
    )
    message: Optional[str] = Field(None, description="Human-readable degradation note")
    disclaimer: str = Field(..., description="Honesty disclaimer for research use")

    model_config = ConfigDict(extra="forbid")


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
