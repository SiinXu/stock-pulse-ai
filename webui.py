# -*- coding: utf-8 -*-
"""Compatibility launcher for the local Web service.

Running ``python webui.py`` is equivalent to ``python main.py --webui-only``.
Non-local binds require administrator authentication unless the documented
emergency override is explicitly enabled.

Usage:
  python webui.py
  WEBUI_HOST=127.0.0.1 WEBUI_PORT=8000 python webui.py
"""

from __future__ import annotations

import os
import logging

from src.security.http_bind import (
    INSECURE_PUBLIC_BIND_ERROR_MESSAGE,
    InsecurePublicBindError,
    enforce_http_bind_security,
)

logger = logging.getLogger(__name__)


def main() -> int:
    """Start the compatibility Web service launcher."""
    try:
        import uvicorn
        from src.config import setup_env
        from src.logging_config import setup_logging

        setup_env()
        setup_logging(log_prefix="web_server")

        # Compatible with old environment variable names.
        host = os.getenv("WEBUI_HOST", os.getenv("API_HOST", "127.0.0.1"))
        port = int(os.getenv("WEBUI_PORT", os.getenv("API_PORT", "8000")))
        enforce_http_bind_security(
            host,
            event_logger=logger,
            entrypoint="webui.py",
        )

        print(f"正在启动 Web 服务: http://{host}:{port}")
        print(f"API 文档: http://{host}:{port}/docs")
        print()

        uvicorn.run(
            "api.app:app",
            host=host,
            port=port,
            log_level="info",
        )
    except InsecurePublicBindError:
        logger.error(INSECURE_PUBLIC_BIND_ERROR_MESSAGE)
        return 2
    except KeyboardInterrupt:
        pass

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
