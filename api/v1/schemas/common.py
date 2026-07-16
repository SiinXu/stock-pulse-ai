"""Shared API response models."""

from typing import Any, Dict, Mapping, Optional

from pydantic import BaseModel, ConfigDict, Field, model_serializer, model_validator


class ErrorDetailsCompatibilityModel(BaseModel):
    """Keep the deprecated ``detail`` output identical to ``details``."""

    details: Optional[Any] = Field(None, description="Diagnostic details")
    detail: Optional[Any] = Field(
        None,
        deprecated=True,
        description=(
            "Deprecated read-only alias of details; retained for patch/minor "
            "compatibility and removed only in a future major or versioned API"
        ),
        json_schema_extra={"readOnly": True},
    )

    model_config = ConfigDict(validate_assignment=True)

    @model_validator(mode="before")
    @classmethod
    def _accept_legacy_detail_input(cls, value: Any) -> Any:
        """Normalize legacy ``detail`` input into the canonical field."""
        if not isinstance(value, Mapping):
            return value
        normalized = dict(value)
        if "details" not in normalized:
            normalized["details"] = normalized.get("detail")
        normalized["detail"] = normalized.get("details")
        return normalized

    @model_validator(mode="after")
    def _synchronize_detail_alias(self) -> "ErrorDetailsCompatibilityModel":
        """Keep the deprecated alias synchronized after validation."""
        self.__dict__["detail"] = self.details
        return self

    @model_serializer(mode="wrap")
    def _serialize_detail_alias(self, handler):
        """Serialize ``detail`` as a read-only alias of ``details``."""
        serialized = handler(self)
        if isinstance(serialized, dict):
            serialized["detail"] = serialized.get("details")
        return serialized


class RootResponse(BaseModel):
    """Root API route response."""
    
    message: str = Field(
        ...,
        description="API runtime status message",
        json_schema_extra={"example": "StockPulse API is running"},
    )
    version: Optional[str] = Field(
        None,
        description="API version",
        json_schema_extra={"example": "1.0.0"},
    )
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "message": "StockPulse API is running",
            "version": "1.0.0"
        }
    })


class HealthResponse(BaseModel):
    """Health check response."""
    
    status: str = Field(..., description="Service status", json_schema_extra={"example": "ok"})
    timestamp: Optional[str] = Field(None, description="Timestamp")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "status": "ok",
            "timestamp": "2024-01-01T12:00:00"
        }
    })


class ErrorResponse(ErrorDetailsCompatibilityModel):
    """Stable API error envelope."""

    error: str = Field(..., description="Error type", json_schema_extra={"example": "validation_error"})
    message: str = Field(
        ...,
        description="Error details",
        json_schema_extra={"example": "Invalid request parameters"},
    )
    params: Dict[str, Any] = Field(default_factory=dict, description="Localization interpolation parameters")
    trace_id: Optional[str] = Field(None, description="Diagnostic trace ID")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "error": "not_found",
            "message": "Resource not found",
            "params": {},
            "details": None,
            "detail": None,
            "trace_id": "7f48e8f72ab04b7db8c4c1df6fc9bb35"
        }
    })


class SuccessResponse(BaseModel):
    """Generic success response."""
    
    success: bool = Field(True, description="Whether the operation succeeded")
    message: Optional[str] = Field(None, description="Success message")
    data: Optional[Any] = Field(None, description="Response data")
    
    model_config = ConfigDict(json_schema_extra={
        "example": {
            "success": True,
            "message": "Operation completed successfully",
            "data": None
        }
    })
