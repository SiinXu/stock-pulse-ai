"""MCP server configuration field definitions (optional external tool surface)."""

from typing import Any, Dict

from src.mcp_server.config import (
    ALL_MCP_SCOPES,
    DEFAULT_ANALYSIS_MAX_STOCKS,
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_TRANSPORT,
)

_MCP_SCOPE_HINT = ", ".join(sorted(ALL_MCP_SCOPES))
_MCP_DOCS = [
    {
        "label": "MCP server integration (EN)",
        "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/mcp-server-integration_EN.md",
    },
    {
        "label": "MCP 服务集成说明",
        "href": "https://github.com/SiinXu/stock-pulse-ai/blob/main/docs/mcp-server-integration.md",
    },
]

MCP_FIELD_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "MCP_SERVER_ENABLED": {
        "title": "Enable MCP Server",
        "description": (
            "Master switch for the optional MCP (Model Context Protocol) process. "
            "Default off. The main API/Web process never starts MCP automatically; "
            "start explicitly with MCP_SERVER_ENABLED=true python -m src.mcp_server. "
            "Requires a process restart of the MCP process to take effect."
        ),
        "category": "mcp",
        "data_type": "boolean",
        "ui_control": "switch",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "false",
        "options": [],
        "validation": {},
        "display_order": 10,
        "help_key": "settings.mcp.MCP_SERVER_ENABLED",
        "examples": [
            "MCP_SERVER_ENABLED=false",
            "MCP_SERVER_ENABLED=true",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": ["restart_required", "security_surface"],
    },
    "MCP_SERVER_TRANSPORT": {
        "title": "MCP Transport",
        "description": (
            "Official SDK transport. stdio (default) is a local process boundary; "
            "streamable-http exposes HTTP and always requires admin auth, explicit scopes, "
            "and a session token digest. The runtime accepts http as an alias of streamable-http."
        ),
        "category": "mcp",
        "data_type": "string",
        "ui_control": "select",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": DEFAULT_TRANSPORT,
        "options": [
            {"label": "stdio (local process)", "value": "stdio"},
            {"label": "streamable-http", "value": "streamable-http"},
        ],
        "validation": {"enum": ["stdio", "streamable-http"]},
        "display_order": 20,
        "help_key": "settings.mcp.MCP_SERVER_TRANSPORT",
        "examples": [
            "MCP_SERVER_TRANSPORT=stdio",
            "MCP_SERVER_TRANSPORT=streamable-http",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": ["restart_required", "security_surface"],
    },
    "MCP_SERVER_HOST": {
        "title": "MCP Bind Host",
        "description": (
            "Bind host for streamable-http. Prefer loopback (127.0.0.1 / localhost / ::1). "
            "Binding beyond loopback expands the attack surface and must only be done behind "
            "trusted network controls."
        ),
        "category": "mcp",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": DEFAULT_HOST,
        "options": [],
        "validation": {"maxLength": 253},
        "display_order": 30,
        "help_key": "settings.mcp.MCP_SERVER_HOST",
        "examples": [
            f"MCP_SERVER_HOST={DEFAULT_HOST}",
            "MCP_SERVER_HOST=localhost",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": ["restart_required", "network_scope"],
    },
    "MCP_SERVER_PORT": {
        "title": "MCP Bind Port",
        "description": "TCP port for streamable-http. Valid range 1–65535.",
        "category": "mcp",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": str(DEFAULT_PORT),
        "options": [],
        "validation": {"min": 1, "max": 65535},
        "display_order": 40,
        "help_key": "settings.mcp.MCP_SERVER_PORT",
        "examples": [
            f"MCP_SERVER_PORT={DEFAULT_PORT}",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": ["restart_required"],
    },
    "MCP_STDIO_PRINCIPAL": {
        "title": "MCP stdio Principal",
        "description": (
            "Stable principal name attached to stdio tool calls for audit and rate limits. "
            "Must match [A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}."
        ),
        "category": "mcp",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "local-operator",
        "options": [],
        "validation": {
            "pattern": r"^[A-Za-z0-9][A-Za-z0-9_.:@/-]{0,127}$",
            "maxLength": 128,
        },
        "display_order": 50,
        "help_key": "settings.mcp.MCP_STDIO_PRINCIPAL",
        "examples": [
            "MCP_STDIO_PRINCIPAL=local-operator",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": [],
    },
    "MCP_STDIO_SCOPES": {
        "title": "MCP stdio Scopes",
        "description": (
            f"Comma-separated least-privilege scopes for stdio. Required when the server is "
            f"enabled with transport=stdio. Allowed values: {_MCP_SCOPE_HINT}."
        ),
        "category": "mcp",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {"maxLength": 512},
        "display_order": 60,
        "help_key": "settings.mcp.MCP_STDIO_SCOPES",
        "examples": [
            "MCP_STDIO_SCOPES=market.read,history.read",
            "MCP_STDIO_SCOPES=market.read,history.read,portfolio.read,analysis.trigger",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": ["security_surface"],
    },
    "MCP_HTTP_SCOPES": {
        "title": "MCP HTTP Scopes",
        "description": (
            f"Comma-separated least-privilege scopes for streamable-http. Required when transport "
            f"is streamable-http and the server is enabled. Allowed values: {_MCP_SCOPE_HINT}."
        ),
        "category": "mcp",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {"maxLength": 512},
        "display_order": 70,
        "help_key": "settings.mcp.MCP_HTTP_SCOPES",
        "examples": [
            "MCP_HTTP_SCOPES=market.read,history.read",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": ["security_surface"],
    },
    "MCP_HTTP_SESSION_TOKEN_SHA256": {
        "title": "MCP HTTP Session Token SHA-256",
        "description": (
            "SHA-256 hex digest (64 characters) of the single admin session token accepted by "
            "streamable-http. Required when HTTP transport is enabled. Store only the digest, "
            "never the raw bearer token, in settings or version control."
        ),
        "category": "mcp",
        "data_type": "string",
        "ui_control": "password",
        "is_sensitive": True,
        "is_required": False,
        "is_editable": True,
        "default_value": "",
        "options": [],
        "validation": {
            "pattern": r"^$|^[0-9a-fA-F]{64}$",
            "maxLength": 64,
        },
        "display_order": 80,
        "help_key": "settings.mcp.MCP_HTTP_SESSION_TOKEN_SHA256",
        "examples": [
            "MCP_HTTP_SESSION_TOKEN_SHA256=",
            "MCP_HTTP_SESSION_TOKEN_SHA256=<64_hex_chars>",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": ["secret_value", "security_surface", "restart_required"],
    },
    "MCP_HTTP_RESOURCE": {
        "title": "MCP HTTP Resource URL",
        "description": (
            "Absolute http(s) audience/resource URL advertised for streamable-http "
            f"(default http://{DEFAULT_HOST}:{DEFAULT_PORT}/mcp)."
        ),
        "category": "mcp",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": f"http://{DEFAULT_HOST}:{DEFAULT_PORT}/mcp",
        "options": [],
        "validation": {
            "item_type": "url",
            "allowed_schemes": ["http", "https"],
            "maxLength": 2048,
        },
        "display_order": 90,
        "help_key": "settings.mcp.MCP_HTTP_RESOURCE",
        "examples": [
            f"MCP_HTTP_RESOURCE=http://{DEFAULT_HOST}:{DEFAULT_PORT}/mcp",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": [],
    },
    "MCP_HTTP_ALLOWED_HOSTS": {
        "title": "MCP HTTP Allowed Hosts",
        "description": (
            "Comma-separated Host header allowlist for streamable-http. Default is loopback only "
            f"({DEFAULT_HOST}:*,localhost:*,[::1]:*). Wildcard ports use the official SDK :* form. "
            "Widening this list (for example to * or a public hostname) increases host-header and "
            "cross-site request risk; keep the list minimal."
        ),
        "category": "mcp",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": f"{DEFAULT_HOST}:*,localhost:*,[::1]:*",
        "options": [],
        "validation": {"maxLength": 2048},
        "display_order": 100,
        "help_key": "settings.mcp.MCP_HTTP_ALLOWED_HOSTS",
        "examples": [
            f"MCP_HTTP_ALLOWED_HOSTS={DEFAULT_HOST}:*,localhost:*,[::1]:*",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": ["security_surface", "network_scope"],
    },
    "MCP_HTTP_ALLOWED_ORIGINS": {
        "title": "MCP HTTP Allowed Origins",
        "description": (
            "Comma-separated Origin allowlist for streamable-http browser clients. Default is "
            f"loopback HTTP origins only (http://{DEFAULT_HOST}:*, http://localhost:*, "
            "http://[::1]:*). Expanding origins (especially to * or untrusted sites) enables "
            "cross-origin browser access to MCP tools and should be treated as a security "
            "decision, not a convenience toggle."
        ),
        "category": "mcp",
        "data_type": "string",
        "ui_control": "text",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": f"http://{DEFAULT_HOST}:*,http://localhost:*,http://[::1]:*",
        "options": [],
        "validation": {"maxLength": 2048},
        "display_order": 110,
        "help_key": "settings.mcp.MCP_HTTP_ALLOWED_ORIGINS",
        "examples": [
            f"MCP_HTTP_ALLOWED_ORIGINS=http://{DEFAULT_HOST}:*,http://localhost:*,http://[::1]:*",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": ["security_surface", "network_scope"],
    },
    "MCP_HTTP_MAX_BODY_BYTES": {
        "title": "MCP HTTP Max Body Bytes",
        "description": "Maximum JSON body size accepted by streamable-http (bytes).",
        "category": "mcp",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "1000000",
        "unit": "B",
        "options": [],
        "validation": {"min": 1024, "max": 10_000_000},
        "display_order": 120,
        "help_key": "settings.mcp.MCP_HTTP_MAX_BODY_BYTES",
        "examples": [
            "MCP_HTTP_MAX_BODY_BYTES=1000000",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": [],
    },
    "MCP_HTTP_MAX_HEADER_BYTES": {
        "title": "MCP HTTP Max Header Bytes",
        "description": "Maximum incomplete header block size for streamable-http (bytes).",
        "category": "mcp",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "32768",
        "unit": "B",
        "options": [],
        "validation": {"min": 4096, "max": 262_144},
        "display_order": 130,
        "help_key": "settings.mcp.MCP_HTTP_MAX_HEADER_BYTES",
        "examples": [
            "MCP_HTTP_MAX_HEADER_BYTES=32768",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": [],
    },
    "MCP_HTTP_MAX_CONNECTIONS": {
        "title": "MCP HTTP Max Connections",
        "description": "Maximum concurrent streamable-http connections.",
        "category": "mcp",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "32",
        "options": [],
        "validation": {"min": 1, "max": 1024},
        "display_order": 140,
        "help_key": "settings.mcp.MCP_HTTP_MAX_CONNECTIONS",
        "examples": [
            "MCP_HTTP_MAX_CONNECTIONS=32",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": [],
    },
    "MCP_HTTP_BACKLOG": {
        "title": "MCP HTTP Listen Backlog",
        "description": "OS listen backlog for the streamable-http acceptor.",
        "category": "mcp",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "16",
        "options": [],
        "validation": {"min": 1, "max": 1024},
        "display_order": 150,
        "help_key": "settings.mcp.MCP_HTTP_BACKLOG",
        "examples": [
            "MCP_HTTP_BACKLOG=16",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": [],
    },
    "MCP_HTTP_READ_TIMEOUT_SECONDS": {
        "title": "MCP HTTP Read Timeout",
        "description": "Per-body-chunk read timeout for streamable-http (seconds).",
        "category": "mcp",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "10",
        "unit": "s",
        "options": [],
        "validation": {"min": 1, "max": 120},
        "display_order": 160,
        "help_key": "settings.mcp.MCP_HTTP_READ_TIMEOUT_SECONDS",
        "examples": [
            "MCP_HTTP_READ_TIMEOUT_SECONDS=10",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": [],
    },
    "MCP_HTTP_KEEPALIVE_TIMEOUT_SECONDS": {
        "title": "MCP HTTP Keep-Alive Timeout",
        "description": "Keep-alive idle timeout for streamable-http connections (seconds).",
        "category": "mcp",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "5",
        "unit": "s",
        "options": [],
        "validation": {"min": 1, "max": 120},
        "display_order": 170,
        "help_key": "settings.mcp.MCP_HTTP_KEEPALIVE_TIMEOUT_SECONDS",
        "examples": [
            "MCP_HTTP_KEEPALIVE_TIMEOUT_SECONDS=5",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": [],
    },
    "MCP_MAX_CONCURRENT_TOOLS": {
        "title": "MCP Max Concurrent Tools",
        "description": "Maximum concurrent tool workers for a single MCP process.",
        "category": "mcp",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "8",
        "options": [],
        "validation": {"min": 1, "max": 128},
        "display_order": 180,
        "help_key": "settings.mcp.MCP_MAX_CONCURRENT_TOOLS",
        "examples": [
            "MCP_MAX_CONCURRENT_TOOLS=8",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": [],
    },
    "MCP_RATE_LIMIT_PER_MINUTE": {
        "title": "MCP Tool Rate Limit",
        "description": "Per-principal/tool call rate limit per minute.",
        "category": "mcp",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "60",
        "unit": "/min",
        "options": [],
        "validation": {"min": 1, "max": 10_000},
        "display_order": 190,
        "help_key": "settings.mcp.MCP_RATE_LIMIT_PER_MINUTE",
        "examples": [
            "MCP_RATE_LIMIT_PER_MINUTE=60",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": [],
    },
    "MCP_ANALYSIS_RATE_LIMIT_PER_MINUTE": {
        "title": "MCP Analysis Rate Limit",
        "description": (
            "Rate limit for analysis.trigger scope invocations per minute. Keep low to bound cost."
        ),
        "category": "mcp",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": "2",
        "unit": "/min",
        "options": [],
        "validation": {"min": 1, "max": 60},
        "display_order": 200,
        "help_key": "settings.mcp.MCP_ANALYSIS_RATE_LIMIT_PER_MINUTE",
        "examples": [
            "MCP_ANALYSIS_RATE_LIMIT_PER_MINUTE=2",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": ["cost_control"],
    },
    "MCP_ANALYSIS_MAX_STOCKS": {
        "title": "MCP Analysis Max Stocks",
        "description": "Maximum symbols accepted in a single MCP analysis.trigger call.",
        "category": "mcp",
        "data_type": "integer",
        "ui_control": "number",
        "is_sensitive": False,
        "is_required": False,
        "is_editable": True,
        "default_value": str(DEFAULT_ANALYSIS_MAX_STOCKS),
        "options": [],
        "validation": {"min": 1, "max": 50},
        "display_order": 210,
        "help_key": "settings.mcp.MCP_ANALYSIS_MAX_STOCKS",
        "examples": [
            f"MCP_ANALYSIS_MAX_STOCKS={DEFAULT_ANALYSIS_MAX_STOCKS}",
        ],
        "docs": _MCP_DOCS,
        "warning_codes": ["cost_control"],
    },
}
