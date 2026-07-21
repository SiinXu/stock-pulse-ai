# -*- coding: utf-8 -*-
"""
===================================
Health check interface
===================================

Responsibilities:
1. Provide /api/v1/health health check interface
2. For load balancers and monitoring systems.
"""

from datetime import datetime

from fastapi import APIRouter

from api.v1.schemas.common import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """
    Health check interface
    
    Checks the status of services on a load balancer or monitoring system.
    
    Returns:
        HealthResponse: Contains service status and timestamp
    """
    return HealthResponse(
        status="ok",
        timestamp=datetime.now().isoformat()
    )
