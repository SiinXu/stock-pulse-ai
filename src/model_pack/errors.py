from __future__ import annotations

from typing import Any, Mapping, Optional


class ModelPackError(Exception):
    """Stable, actionable Model Pack failure safe for API and desktop surfaces."""

    def __init__(
        self,
        code: str,
        user_message: str,
        *,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.details = dict(details or {})


__all__ = ["ModelPackError"]
