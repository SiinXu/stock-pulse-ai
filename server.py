# -*- coding: utf-8 -*-
"""FastAPI service entrypoint with a fail-closed network bind guard.

Local development::

    uvicorn server:app --reload --host 127.0.0.1 --port 8000
    python main.py --serve-only

Non-local binds require administrator authentication unless the documented
emergency override is explicitly enabled.
"""

import argparse
import logging
import os
import sys

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


def _parse_server_bind(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse Uvicorn bind options while leaving unrelated process args untouched."""
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--uds")
    parser.add_argument("--fd", type=int)
    options, _ = parser.parse_known_args((argv or sys.argv)[1:])
    if options.host is None:
        options.host = os.getenv("WEBUI_HOST", os.getenv("API_HOST", "127.0.0.1"))
    if options.port is None:
        options.port = int(os.getenv("WEBUI_PORT", os.getenv("API_PORT", "8000")))
    return options


def _enforce_server_bind(options: argparse.Namespace) -> None:
    """Apply the shared bind policy for direct and Uvicorn CLI startup."""
    from src.security.http_bind import enforce_http_bind_security

    enforce_http_bind_security(
        options.host,
        unix_socket=options.uds,
        inherited_socket=options.fd is not None,
        event_logger=logging.getLogger(__name__),
        entrypoint="server.py",
    )


_bind_options = _parse_server_bind()
_enforce_server_bind(_bind_options)

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
        host=_bind_options.host,
        port=_bind_options.port,
        uds=_bind_options.uds,
        fd=_bind_options.fd,
        reload=True,
    )
