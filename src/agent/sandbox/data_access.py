# -*- coding: utf-8 -*-
"""Read-only live or snapshot data access for sandbox runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Mapping, Optional

from src.agent.sandbox.context import SandboxContext, SandboxDataMode


class SandboxDataAccessError(RuntimeError):
    """Raised when sandbox data access is refused or incomplete."""


@dataclass(frozen=True)
class SandboxDataAccess:
    """Bound data plane for one sandbox context.

    - ``readonly_live``: call a caller-supplied reader; never mutate.
    - ``snapshot``: serve only values from the frozen snapshot binding.
    """

    context: SandboxContext
    live_reader: Optional[Callable[[str, Mapping[str, Any]], Any]] = None

    @property
    def data_mode(self) -> SandboxDataMode:
        return self.context.data_mode

    def get(
        self,
        key: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        default: Any = None,
    ) -> Any:
        """Read one named data key without write capability."""
        if not key or not str(key).strip():
            raise SandboxDataAccessError("data key must be non-empty")
        mode = self.context.data_mode
        if mode == "snapshot":
            snapshot = self.context.snapshot
            if key not in snapshot:
                if default is not None:
                    return default
                raise SandboxDataAccessError(
                    f"snapshot has no key {key!r} for sandbox "
                    f"{self.context.sandbox_run_id}"
                )
            return snapshot[key]
        if self.live_reader is None:
            if default is not None:
                return default
            raise SandboxDataAccessError(
                "readonly_live mode requires a live_reader callable"
            )
        return self.live_reader(str(key), dict(params or {}))

    def describe(self) -> Dict[str, Any]:
        return {
            "data_mode": self.context.data_mode,
            "sandbox_run_id": self.context.sandbox_run_id,
            "snapshot_keys": (
                sorted(str(k) for k in self.context.snapshot.keys())
                if self.context.data_mode == "snapshot"
                else []
            ),
            "writable": False,
            "simulation": True,
            "label": self.context.label,
        }
