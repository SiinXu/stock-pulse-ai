"""Fail-closed resolvers for repository-derived merge conflicts."""

from .common import ConflictContext, RefusalError

__all__ = ["ConflictContext", "RefusalError"]
