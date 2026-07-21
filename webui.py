# -*- coding: utf-8 -*-
"""
===================================
WebUI startup script
===================================

Interface for launching the web service.
Run `python webui.py` to start the Web backend service.

Equivalent command:
    python main.py --webui-only

Usage:
  python webui.py
  WEBUI_HOST=0.0.0.0 WEBUI_PORT=8000 python webui.py
"""

from __future__ import annotations

import os
import logging

logger = logging.getLogger(__name__)


def main() -> int:
    """
    Start Web service
    """
    # Compatible with old environment variable names
    host = os.getenv("WEBUI_HOST", os.getenv("API_HOST", "127.0.0.1"))
    port = int(os.getenv("WEBUI_PORT", os.getenv("API_PORT", "8000")))

    print(f"正在启动 Web 服务: http://{host}:{port}")
    print(f"API 文档: http://{host}:{port}/docs")
    print()

    try:
        import uvicorn
        from src.config import setup_env
        from src.logging_config import setup_logging

        setup_env()
        setup_logging(log_prefix="web_server")

        uvicorn.run(
            "api.app:app",
            host=host,
            port=port,
            log_level="info",
        )
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
