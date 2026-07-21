# -*- coding: utf-8 -*-
"""
===================================
API v1 module initialization
===================================

Responsibilities:
1. Export v1 version API routes
"""

from api.v1.router import router as api_v1_router

__all__ = ["api_v1_router"]
