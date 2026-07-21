# -*- coding: utf-8 -*-
"""
===================================
Daily Stock Analysis - FastAPI Backend Service Entrypoint
===================================

Responsibilities:
1. Provides RESTful API service
2. Configure CORS cross-origin support
3. Health check interface
4. Host frontend static files (production mode)

Startup method:
    uvicorn server:app --reload --host 0.0.0.0 --port 8000
    
    Or use main.py:
    python main.py --serve-only      # Start only the API service
    python main.py --serve           # Start the API service and run analysis
"""

import logging

from src.application_services import ApplicationServices, set_application_services
from src.config import setup_env, get_config
from src.logging_config import setup_logging

# Initialize environment variables and logging
setup_env()

config = get_config()
level_name = (config.log_level or "INFO").upper()
level = getattr(logging, level_name, logging.INFO)

setup_logging(
    log_prefix="api_server",
    console_level=level,
    extra_quiet_loggers=['uvicorn', 'fastapi'],
)

# Establish the application composition root at the API startup layer so the
# process-wide service singletons have a single owner before the app loads.
set_application_services(ApplicationServices())

# Import application instance from api.app
from api.app import app  # noqa: E402

# Export app for uvicorn usage
__all__ = ['app']


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
