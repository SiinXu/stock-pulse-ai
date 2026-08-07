# -*- coding: utf-8 -*-
"""Shared retry and request-timeout policy for data providers.

This module is the single place for per-fetcher retry/backoff parameters and the
explicit request-timeout contract used by baostock, pytdx, and longbridge.

BaseFetcher-level enforcement is intentionally out of scope here (follow-up once
manager/health refactors settle). Fetchers opt in by decorating their network
entry points and wrapping library calls with :func:`call_with_timeout`.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from typing import Any, Callable, Optional, Sequence, Tuple, Type, TypeVar

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.utils.sanitize import safe_before_sleep_log

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Defaults match the historical baostock/pytdx tenacity parameters.
DEFAULT_ATTEMPTS = 3
DEFAULT_BACKOFF_MULTIPLIER = 1.0
DEFAULT_BACKOFF_MIN_SECONDS = 2.0
DEFAULT_BACKOFF_MAX_SECONDS = 30.0
DEFAULT_REQUEST_TIMEOUT_SECONDS = 30.0
DEFAULT_RETRYABLE_EXCEPTIONS: Tuple[Type[BaseException], ...] = (
    ConnectionError,
    TimeoutError,
)


def call_with_timeout(
    func: Callable[..., T],
    *args: Any,
    timeout: Optional[float] = None,
    call_name: str = "provider",
    **kwargs: Any,
) -> T:
    """Run ``func`` in a worker thread and enforce a request timeout.

    **Contract**

    - Every network-bound library call that lacks a native timeout must go
      through this helper (or an equivalent per-call timeout parameter).
    - On deadline, raises the built-in :class:`TimeoutError` (never a private
      futures alias) so :func:`provider_retry` and other retry policies that
      list ``TimeoutError`` observe a real, retryable failure.
    - Worker threads are not forcibly killed; a hung library call may continue
      in the background until the OS-level socket timeout. The calling thread
      always returns when the deadline is exceeded.

    Args:
        func: Callable to execute.
        *args: Positional arguments for ``func``.
        timeout: Deadline in seconds. ``None`` or ``<= 0`` uses
            :data:`DEFAULT_REQUEST_TIMEOUT_SECONDS`.
        call_name: Stable label embedded in the timeout message for logs/tests.
        **kwargs: Keyword arguments for ``func``.

    Returns:
        Whatever ``func`` returns.

    Raises:
        TimeoutError: When the deadline is exceeded.
    """
    wait_seconds = (
        DEFAULT_REQUEST_TIMEOUT_SECONDS
        if timeout is None
        else float(timeout)
    )
    if wait_seconds <= 0:
        wait_seconds = DEFAULT_REQUEST_TIMEOUT_SECONDS

    # Do NOT use `with ThreadPoolExecutor`: __exit__ calls shutdown(wait=True)
    # and would re-block the calling thread on a hung worker.
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=wait_seconds)
        except FuturesTimeoutError as exc:
            raise TimeoutError(
                f"{call_name} exceeded {wait_seconds:g}s request timeout"
            ) from exc
    finally:
        executor.shutdown(wait=False)


def provider_retry(
    *,
    attempts: int = DEFAULT_ATTEMPTS,
    multiplier: float = DEFAULT_BACKOFF_MULTIPLIER,
    min_wait: float = DEFAULT_BACKOFF_MIN_SECONDS,
    max_wait: float = DEFAULT_BACKOFF_MAX_SECONDS,
    retryable: Sequence[Type[BaseException]] = DEFAULT_RETRYABLE_EXCEPTIONS,
    target_logger: Optional[logging.Logger] = None,
    event: str = "provider retry scheduled",
    error_code: str = "provider_retry",
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Configurable exponential-backoff retry decorator for provider methods.

    Intentional per-fetcher deviations (attempt count, wait bounds, retryable
    exception set, log event/code) are expressed as keyword parameters here —
    do not fork a parallel tenacity copy in individual fetchers.

    Args:
        attempts: Maximum attempts including the first try.
        multiplier: Exponential backoff multiplier.
        min_wait: Minimum wait between attempts (seconds).
        max_wait: Maximum wait between attempts (seconds).
        retryable: Exception types that schedule another attempt.
        target_logger: Logger for before-sleep diagnostics.
        event: Safe log event string.
        error_code: Stable error code for structured logs.
    """
    attempt_count = max(1, int(attempts))
    retryable_types = tuple(retryable) or DEFAULT_RETRYABLE_EXCEPTIONS
    log = target_logger if target_logger is not None else logger

    return retry(
        stop=stop_after_attempt(attempt_count),
        wait=wait_exponential(
            multiplier=float(multiplier),
            min=float(min_wait),
            max=float(max_wait),
        ),
        retry=retry_if_exception_type(retryable_types),
        before_sleep=safe_before_sleep_log(
            log,
            logging.WARNING,
            event=event,
            error_code=error_code,
        ),
        reraise=True,
    )
