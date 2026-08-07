# -*- coding: utf-8 -*-
"""Shared repository base types and error contract.

``RepositoryError`` is raised when a persistence or query operation fails.
Missing rows continue to return ``None`` / empty collections so callers can
distinguish not-found from infrastructure failure.
"""

from __future__ import annotations

import logging
from typing import Any, Mapping, NoReturn, Optional

from src.storage import DatabaseManager
from src.utils.sanitize import log_safe_exception


class RepositoryError(RuntimeError):
    """Raised when a repository operation fails (not for missing rows)."""

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "repository_error",
        context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.error_code = str(error_code or "repository_error")
        self.context = dict(context or {})


class BaseRepository:
    """Common database handle and failure logging for repositories."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None) -> None:
        self.db = db_manager or DatabaseManager.get_instance()

    def _log_and_raise(
        self,
        logger: logging.Logger,
        event: str,
        exc: BaseException,
        *,
        error_code: str,
        context: Optional[Mapping[str, Any]] = None,
        message: Optional[str] = None,
    ) -> NoReturn:
        """Sanitize-log a failure and re-raise it as ``RepositoryError``."""
        safe_context = dict(context or {})
        log_safe_exception(
            logger,
            event,
            exc,
            error_code=error_code,
            context=safe_context,
        )
        raise RepositoryError(
            message or event,
            error_code=error_code,
            context=safe_context,
        ) from exc
