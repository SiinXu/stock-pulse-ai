"""Bound Model Pack uploads before multipart parsing can spool them to disk."""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from api.v1.errors import error_body
from src.model_pack import MAX_MODEL_PACK_BYTES


MODEL_PACK_IMPORT_PATH = "/api/v1/model-packs/import"
MAX_MODEL_PACK_UPLOAD_BYTES = MAX_MODEL_PACK_BYTES
MAX_MODEL_PACK_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
MAX_MODEL_PACK_UPLOAD_REQUEST_BYTES = (
    MAX_MODEL_PACK_UPLOAD_BYTES + MAX_MODEL_PACK_MULTIPART_OVERHEAD_BYTES
)
_MODEL_PACK_TOO_LARGE_MESSAGE = (
    "This Model Pack exceeds the 64 GiB upload limit. "
    "Select a smaller pack or import it from Desktop."
)


def model_pack_too_large_detail() -> dict[str, str]:
    """Return the stable public error used by ingress and file-size checks."""
    return {
        "error": "model_pack_too_large",
        "message": _MODEL_PACK_TOO_LARGE_MESSAGE,
    }


def _declared_content_length(scope: Scope) -> Optional[int]:
    """Return one unambiguous non-negative Content-Length, if present."""
    values: list[int] = []
    for raw_name, raw_value in scope.get("headers", ()):
        if raw_name.lower() != b"content-length":
            continue
        try:
            value = int(raw_value.decode("ascii"))
        except (UnicodeDecodeError, ValueError):
            return None
        if value < 0:
            return None
        values.append(value)
    if not values or any(value != values[0] for value in values[1:]):
        return None
    return values[0]


class ModelPackUploadLimitMiddleware:
    """Limit the raw multipart envelope before Starlette creates UploadFile."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        import_path: str = MODEL_PACK_IMPORT_PATH,
        max_request_bytes: int = MAX_MODEL_PACK_UPLOAD_REQUEST_BYTES,
    ) -> None:
        if not import_path.startswith("/"):
            raise ValueError("Model Pack import path must be absolute")
        if max_request_bytes < 1:
            raise ValueError("Model Pack request limit must be positive")
        self.app = app
        self.import_path = import_path
        self.max_request_bytes = max_request_bytes

    async def _send_too_large(self, scope: Scope, receive: Receive, send: Send) -> None:
        trace_id = uuid.uuid4().hex
        detail = model_pack_too_large_detail()
        response = JSONResponse(
            status_code=413,
            content=error_body(
                detail["error"],
                detail["message"],
                trace_id=trace_id,
            ),
            headers={"X-Trace-ID": trace_id},
        )
        await response(scope, receive, send)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope.get("method") != "POST"
            or scope.get("path") != self.import_path
        ):
            await self.app(scope, receive, send)
            return

        content_length = _declared_content_length(scope)
        if content_length is not None and content_length > self.max_request_bytes:
            await self._send_too_large(scope, receive, send)
            return

        received_bytes = 0
        limit_exceeded = False

        async def limited_receive() -> Message:
            nonlocal limit_exceeded, received_bytes
            message = await receive()
            if message["type"] != "http.request":
                return message
            body = message.get("body", b"")
            remaining = self.max_request_bytes - received_bytes
            if len(body) <= remaining:
                received_bytes += len(body)
                return message

            limit_exceeded = True
            received_bytes = self.max_request_bytes
            limited_message = dict(message)
            limited_message["body"] = body[:remaining]
            limited_message["more_body"] = False
            return limited_message

        async def limited_send(message: Message) -> None:
            if not limit_exceeded:
                await send(message)

        await self.app(scope, limited_receive, limited_send)
        if limit_exceeded:
            await self._send_too_large(scope, receive, send)


__all__ = [
    "MAX_MODEL_PACK_MULTIPART_OVERHEAD_BYTES",
    "MAX_MODEL_PACK_UPLOAD_BYTES",
    "MAX_MODEL_PACK_UPLOAD_REQUEST_BYTES",
    "MODEL_PACK_IMPORT_PATH",
    "ModelPackUploadLimitMiddleware",
    "model_pack_too_large_detail",
]
