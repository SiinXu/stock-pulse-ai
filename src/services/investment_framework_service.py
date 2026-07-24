# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Business service for versioned personal investment frameworks."""

from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional

from pydantic import ValidationError

from src.repositories.investment_framework_repo import (
    InvestmentFrameworkAlreadyExistsError as RepositoryAlreadyExistsError,
    InvestmentFrameworkNotFoundError as RepositoryNotFoundError,
    InvestmentFrameworkRepository,
    InvestmentFrameworkRevisionConflictError as RepositoryRevisionConflictError,
    StoredInvestmentFramework,
    StoredInvestmentFrameworkVersion,
)
from src.schemas.investment_framework import (
    InvestmentFrameworkAnalysisContext,
    InvestmentFrameworkContent,
)
from src.storage import DatabaseManager


class InvestmentFrameworkServiceError(ValueError):
    """Base stable service error."""

    error_code = "investment_framework_error"


class InvestmentFrameworkNotFoundError(InvestmentFrameworkServiceError):
    error_code = "investment_framework_not_found"


class InvestmentFrameworkAlreadyExistsError(InvestmentFrameworkServiceError):
    error_code = "investment_framework_already_exists"


class InvestmentFrameworkRevisionConflictError(InvestmentFrameworkServiceError):
    error_code = "investment_framework_revision_conflict"

    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__("Investment framework was changed by another request")


class InvestmentFrameworkDataError(RuntimeError):
    """Raised when persisted content violates the versioned content schema."""


class InvestmentFrameworkService:
    """Create immutable content versions and manage aggregate activation."""

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.repo = InvestmentFrameworkRepository(db_manager)

    def create(
        self,
        *,
        content: InvestmentFrameworkContent | Mapping[str, Any],
        change_summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized = self._normalize_content(content)
        try:
            stored = self.repo.create(
                content_json=self._encode_content(normalized),
                change_summary=change_summary,
            )
        except RepositoryAlreadyExistsError as exc:
            raise InvestmentFrameworkAlreadyExistsError(str(exc)) from exc
        return self._serialize(stored, content=normalized)

    def get(self) -> Dict[str, Any]:
        stored = self.repo.get_current()
        if stored is None:
            raise InvestmentFrameworkNotFoundError(
                "Investment framework does not exist"
            )
        return self._serialize(stored)

    def update(
        self,
        *,
        expected_revision: int,
        content: InvestmentFrameworkContent | Mapping[str, Any],
        change_summary: Optional[str] = None,
    ) -> Dict[str, Any]:
        normalized = self._normalize_content(content)
        try:
            stored = self.repo.update(
                expected_revision=expected_revision,
                content_json=self._encode_content(normalized),
                change_summary=change_summary,
            )
        except RepositoryNotFoundError as exc:
            raise InvestmentFrameworkNotFoundError(str(exc)) from exc
        except RepositoryRevisionConflictError as exc:
            raise InvestmentFrameworkRevisionConflictError(
                exc.current_revision
            ) from exc
        return self._serialize(stored, content=normalized)

    def deactivate(self, *, expected_revision: int) -> Dict[str, Any]:
        try:
            stored = self.repo.deactivate(expected_revision=expected_revision)
        except RepositoryNotFoundError as exc:
            raise InvestmentFrameworkNotFoundError(str(exc)) from exc
        except RepositoryRevisionConflictError as exc:
            raise InvestmentFrameworkRevisionConflictError(
                exc.current_revision
            ) from exc
        return self._serialize(stored)

    def delete(self, *, expected_revision: int) -> Dict[str, Any]:
        try:
            deleted = self.repo.delete(expected_revision=expected_revision)
        except RepositoryNotFoundError as exc:
            raise InvestmentFrameworkNotFoundError(str(exc)) from exc
        except RepositoryRevisionConflictError as exc:
            raise InvestmentFrameworkRevisionConflictError(
                exc.current_revision
            ) from exc
        return {
            "deleted": True,
            "framework_id": deleted.framework_id,
            "deleted_through_version": deleted.latest_version,
        }

    def list_history(self) -> Dict[str, Any]:
        try:
            current, versions = self.repo.list_history()
        except RepositoryNotFoundError as exc:
            raise InvestmentFrameworkNotFoundError(str(exc)) from exc
        return {
            "framework_id": current.framework_id,
            "latest_version": current.latest_version,
            "active_version": current.active_version,
            "revision": current.revision,
            "items": [
                self._serialize_history_item(
                    version,
                    active_version=current.active_version,
                )
                for version in versions
            ],
            "total": len(versions),
        }

    def read_active_context(self) -> Optional[InvestmentFrameworkAnalysisContext]:
        """Return active context only; absence and deactivation remain no-ops."""
        stored = self.repo.get_active()
        if stored is None:
            return None
        return InvestmentFrameworkAnalysisContext(
            framework_id=stored.framework_id,
            framework_version=stored.version,
            content=self._decode_content(stored.content_json),
            updated_at=stored.updated_at,
        )

    @staticmethod
    def _normalize_content(
        content: InvestmentFrameworkContent | Mapping[str, Any],
    ) -> InvestmentFrameworkContent:
        if isinstance(content, InvestmentFrameworkContent):
            return content
        return InvestmentFrameworkContent.model_validate(content)

    @staticmethod
    def _encode_content(content: InvestmentFrameworkContent) -> str:
        return json.dumps(
            content.model_dump(mode="json"),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _decode_content(content_json: str) -> InvestmentFrameworkContent:
        try:
            raw = json.loads(content_json)
            return InvestmentFrameworkContent.model_validate(raw)
        except (TypeError, ValueError, ValidationError) as exc:
            raise InvestmentFrameworkDataError(
                "Persisted investment framework content is invalid"
            ) from exc

    def _serialize(
        self,
        stored: StoredInvestmentFramework,
        *,
        content: Optional[InvestmentFrameworkContent] = None,
    ) -> Dict[str, Any]:
        resolved_content = content or self._decode_content(stored.content_json)
        return {
            "framework_id": stored.framework_id,
            "scope": stored.scope_key,
            "version": stored.version,
            "active_version": stored.active_version,
            "revision": stored.revision,
            "is_active": stored.active_version == stored.version,
            "content": resolved_content,
            "change_summary": stored.change_summary,
            "created_at": stored.created_at,
            "updated_at": stored.updated_at,
            "version_created_at": stored.version_created_at,
        }

    def _serialize_history_item(
        self,
        stored: StoredInvestmentFrameworkVersion,
        *,
        active_version: Optional[int],
    ) -> Dict[str, Any]:
        return {
            "version": stored.version,
            "is_active": stored.version == active_version,
            "content": self._decode_content(stored.content_json),
            "change_summary": stored.change_summary,
            "created_at": stored.created_at,
        }


__all__ = [
    "InvestmentFrameworkAlreadyExistsError",
    "InvestmentFrameworkDataError",
    "InvestmentFrameworkNotFoundError",
    "InvestmentFrameworkRevisionConflictError",
    "InvestmentFrameworkService",
    "InvestmentFrameworkServiceError",
]
