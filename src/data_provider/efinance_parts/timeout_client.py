# -*- coding: utf-8 -*-
"""Bounded-wait thread wrapper for efinance SDK calls.

The helper is cloned onto ``src.data_provider.efinance_fetcher`` globals
(ADR-006) so ``_ef_call_with_timeout`` call sites and test patches stay on
the compatibility facade. The wrapper remains a module-level function, not a
class method.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional, Tuple

_FACADE_RELOAD_HOOK: Optional[Callable[[], None]] = globals().get("_FACADE_RELOAD_HOOK")

# Facade free-name anchors for flake8 F821. The cloned function resolves
# ``_EF_CALL_TIMEOUT`` and ``ThreadPoolExecutor`` from
# ``src.data_provider.efinance_fetcher`` globals at runtime (ADR-006).
_EF_CALL_TIMEOUT = 0


def _ef_call_with_timeout(func, *args, timeout=None, **kwargs):
    """Run an efinance library call in a thread with a timeout.

    efinance internally uses requests/urllib3 with no timeout, so when
    eastmoney hosts are unreachable the call can hang for many minutes.
    This helper caps the *calling thread's* wait time.  Note: Python threads
    cannot be forcibly killed, so the worker thread may continue running in
    the background until the OS-level TCP timeout fires or the process exits.
    This is acceptable — the calling thread returns promptly on timeout.
    """
    if timeout is None:
        timeout = _EF_CALL_TIMEOUT
    # Do NOT use 'with ThreadPoolExecutor(...)' here: the context manager calls
    # shutdown(wait=True) on __exit__, which would re-block on the hung thread.
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(func, *args, **kwargs)
        return future.result(timeout=timeout)
    finally:
        # wait=False: calling thread returns immediately; worker cleans up later
        executor.shutdown(wait=False)


EXPECTED_TIMEOUT_CLIENT_NAMES: Tuple[str, ...] = (
    "_ef_call_with_timeout",
)


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
