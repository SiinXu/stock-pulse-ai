# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Manager-owned failed/rejected fundamental builders rebound onto DataFetcherManager.

Extracted from ``src.data_provider.base`` behind an ADR-006 compatibility
facade. TickFlow, prefetch, ``_init_default_fetchers``, timeout slot
construction, and remaining ``get_config()`` sites stay on the facade.
These descriptors own ``build_failed_fundamental_context`` and
``build_validation_rejected_fundamental_context``. Cloned bodies still
resolve facade ``_market_tag`` / ``sanitize_diagnostic_text`` and rebound
``self._build_fundamental_block``. ``DataFetcherManager`` remains the
public import and patch surface.
"""

from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    Optional,
    Tuple,
    Type,
)

from .daily_cache_methods import _clone_facade_descriptor, _descriptor_function

# Facade-only symbols cannot be imported from ``src.data_provider.base`` while
# that module is still assembling this part (circular import). Declare anchors
# so flake8 F821 is clean; rebound methods resolve the real objects from the
# ``src.data_provider.base`` global namespace.
_market_tag = None  # type: ignore[assignment,misc]
sanitize_diagnostic_text = None  # type: ignore[assignment,misc]

# ``importlib.reload`` retains a module dictionary. Preserve the callback
# installed by the loaded compatibility facade so an owner reload can
# atomically rebuild and rebind both sides of the seam.
_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get(
    "_FACADE_RELOAD_HOOK"
)


class _FundamentalOutcomeMethods:
    """Source descriptors rebound onto ``DataFetcherManager`` by its facade."""

    def build_failed_fundamental_context(self, stock_code: str, reason: str) -> Dict[str, Any]:
        """Build a consistent failed-context payload for caller-side fallback."""
        market = _market_tag(stock_code)
        block_names = (
            "valuation",
            "growth",
            "earnings",
            "institution",
            "capital_flow",
            "dragon_tiger",
            "boards",
        )
        blocks = {
            block: self._build_fundamental_block(
                "failed",
                {},
                [{"provider": "fundamental_pipeline", "result": "failed", "duration_ms": 0}],
                [reason],
            )
            for block in block_names
        }
        return {
            "market": market,
            "status": "failed",
            "coverage": {block: "failed" for block in block_names},
            "source_chain": [{"provider": "fundamental_pipeline", "result": "failed", "duration_ms": 0}],
            "errors": [reason],
            **blocks,
        }

    def build_validation_rejected_fundamental_context(
        self,
        stock_code: str,
        rejection: Any,
    ) -> Dict[str, Any]:
        """Build a typed upper-layer policy outcome without claiming provider failure."""
        market = _market_tag(stock_code)
        reason_codes = [
            sanitize_diagnostic_text(code, max_length=96)
            for code in getattr(rejection, "reason_codes", ())
            if sanitize_diagnostic_text(code, max_length=96)
        ][:24]
        evidence = getattr(rejection, "evidence", None)
        evidence_list = [dict(evidence)] if isinstance(evidence, dict) else []
        source_chain = [
            {
                "provider": "data_validation",
                "result": "rejected",
                "duration_ms": 0,
            }
        ]
        block_names = (
            "valuation",
            "growth",
            "earnings",
            "institution",
            "capital_flow",
            "dragon_tiger",
            "boards",
        )
        blocks = {
            block: self._build_fundamental_block(
                "validation_rejected",
                {},
                source_chain,
                reason_codes or ["data_validation_rejected"],
            )
            for block in block_names
        }
        return {
            "market": market,
            "status": "validation_rejected",
            "data_quality": "rejected",
            "coverage": {block: "validation_rejected" for block in block_names},
            "source_chain": source_chain,
            "errors": reason_codes or ["data_validation_rejected"],
            "validation_rejection": {
                "outcome": "rejected",
                "reason_codes": reason_codes,
            },
            "data_quality_evidence": evidence_list,
            **blocks,
        }


EXPECTED_FUNDAMENTAL_OUTCOME_METHOD_NAMES: Tuple[str, ...] = (
    "build_failed_fundamental_context",
    "build_validation_rejected_fundamental_context",
)


def bind_fundamental_outcome_methods_facade(
    target_class: Type[Any],
    global_namespace: Dict[str, Any],
) -> Tuple[str, ...]:
    """Bind fundamental outcome descriptors without changing the manager API."""

    bound_names = []
    for name, descriptor in vars(_FundamentalOutcomeMethods).items():
        if name.startswith("__") or _descriptor_function(descriptor) is None:
            continue
        setattr(
            target_class,
            name,
            _clone_facade_descriptor(
                descriptor,
                global_namespace,
                owner_qualname=target_class.__qualname__,
            ),
        )
        bound_names.append(name)
    return tuple(bound_names)


def _install_facade_reload_hook(hook: Callable[[], None]) -> None:
    """Register the loaded facade assembly callback for owner reloads."""

    global _FACADE_RELOAD_HOOK
    _FACADE_RELOAD_HOOK = hook


def _rebind_loaded_facade() -> None:
    """Refresh a registered facade after this owner module is reloaded."""

    hook = _FACADE_RELOAD_HOOK
    if hook is not None:
        hook()


_rebind_loaded_facade()
