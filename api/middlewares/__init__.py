# -*- coding: utf-8 -*-
"""
===================================
API middleware module initialization
===================================

Responsibilities:
1. Export all middlewares
"""

from api.middlewares.error_handler import ErrorHandlerMiddleware

__all__ = ["ErrorHandlerMiddleware"]
