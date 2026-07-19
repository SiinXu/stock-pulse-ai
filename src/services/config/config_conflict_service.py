# -*- coding: utf-8 -*-
"""Single authority for optimistic config-version conflict detection."""

from __future__ import annotations

from src.core.config_manager import ConfigManager, ConfigVersionMismatchError


class ConfigConflictError(Exception):
    """Raised when a submitted ``config_version`` is stale."""

    def __init__(self, current_version: str):
        super().__init__("Configuration version conflict")
        self.current_version = current_version


class ConfigConflictService:
    """Own the "did the config change under us" decision for the write path.

    Both the up-front guard (fast fail before validation) and the atomic
    write path need the same notion of a version conflict. Centralizing the
    comparison and the ``ConfigVersionMismatchError`` -> ``ConfigConflictError``
    translation here keeps a single authority for that state instead of letting
    each caller re-derive it.
    """

    def __init__(self, manager: ConfigManager):
        self._manager = manager

    def guard_version(self, expected_version: str) -> str:
        """Return the current version when it still matches ``expected_version``.

        Raises ``ConfigConflictError`` when the on-disk ``.env`` changed since the
        client last read it.
        """
        current_version = self._manager.get_config_version()
        if current_version != expected_version:
            raise ConfigConflictError(current_version=current_version)
        return current_version

    @staticmethod
    def as_conflict(exc: ConfigVersionMismatchError) -> ConfigConflictError:
        """Translate the manager's atomic-write mismatch into a service conflict."""
        return ConfigConflictError(current_version=exc.current_version)
