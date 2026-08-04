# -*- coding: utf-8 -*-
"""FastAPI service entrypoint with a fail-closed network bind guard.

Local development::

    uvicorn server:app --reload --host 127.0.0.1 --port 8000
    python main.py --serve-only

Non-local binds require administrator authentication unless the documented
emergency override is explicitly enabled.
"""

import argparse
import importlib.util
import logging
import os
from pathlib import Path
import sys
import sysconfig

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


def _resolved_existing_path(value: str) -> Path | None:
    """Resolve a launcher path without trusting its filename alone."""
    try:
        return Path(value).expanduser().resolve(strict=True)
    except OSError:
        return None


def _is_uvicorn_cli(argv: list[str]) -> bool:
    """Return whether the launcher is the installed Uvicorn CLI entrypoint."""
    if not argv or (launcher := _resolved_existing_path(argv[0])) is None:
        return False

    executable_name = launcher.name.lower()
    if executable_name in {"uvicorn", "uvicorn.exe"}:
        script_dirs = {
            Path(sys.executable).resolve().parent,
            Path(sysconfig.get_path("scripts")).resolve(),
        }
        return launcher in {
            directory / executable_name
            for directory in script_dirs
        }

    if executable_name not in {"__main__.py", "__main__.pyc"}:
        return False
    spec = importlib.util.find_spec("uvicorn")
    if spec is None or spec.origin is None:
        return False
    package_entrypoint = Path(spec.origin).resolve().with_name(executable_name)
    return launcher == package_entrypoint


def _is_direct_server_launch(argv: list[str]) -> bool:
    """Return whether this module is being executed as the server script."""
    return bool(argv) and _resolved_existing_path(argv[0]) == Path(__file__).resolve()


def _uvicorn_env(name: str) -> str | None:
    """Read a non-empty Uvicorn CLI environment option."""
    value = os.getenv(f"UVICORN_{name}")
    return value if value not in {None, ""} else None


def _parse_server_bind(argv: list[str] | None = None) -> argparse.Namespace:
    """Resolve the authoritative bind for supported server launch modes."""
    process_argv = list(sys.argv if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--uds")
    parser.add_argument("--fd", type=int)
    options, _ = parser.parse_known_args(process_argv[1:])

    if _is_uvicorn_cli(process_argv):
        options.host = (
            options.host
            if options.host is not None
            else (_uvicorn_env("HOST") or "127.0.0.1")
        )
        options.port = (
            options.port
            if options.port is not None
            else int(_uvicorn_env("PORT") or "8000")
        )
        options.uds = options.uds if options.uds is not None else _uvicorn_env("UDS")
        options.fd = options.fd if options.fd is not None else (
            int(value) if (value := _uvicorn_env("FD")) is not None else None
        )
        options.bind_authoritative = True
    elif _is_direct_server_launch(process_argv):
        options.host = (
            options.host
            if options.host is not None
            else os.getenv("WEBUI_HOST", os.getenv("API_HOST", "127.0.0.1"))
        )
        options.port = (
            options.port
            if options.port is not None
            else int(os.getenv("WEBUI_PORT", os.getenv("API_PORT", "8000")))
        )
        options.bind_authoritative = True
    else:
        # Import-based servers can bind sockets without exposing their Config
        # to the ASGI module. Treat that unprovable locality like an inherited FD.
        options.host = None
        options.port = None
        options.uds = None
        options.fd = None
        options.bind_authoritative = False
    return options


def _enforce_server_bind(options: argparse.Namespace) -> None:
    """Apply the shared bind policy for direct and Uvicorn CLI startup."""
    from src.security.http_bind import enforce_http_bind_security

    enforce_http_bind_security(
        options.host,
        unix_socket=options.uds,
        inherited_socket=options.fd is not None or not options.bind_authoritative,
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
