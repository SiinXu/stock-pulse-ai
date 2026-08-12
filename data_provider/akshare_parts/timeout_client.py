# -*- coding: utf-8 -*-
"""Bounded-wait process wrappers for AkShare SDK calls.

Extracted from ``data_provider.akshare_fetcher`` (Issue #1068). The facade
re-exports these names so tests can still patch
``data_provider.akshare_fetcher._akshare_call_with_timeout`` and
``data_provider.akshare_fetcher.multiprocessing``.
"""

from __future__ import annotations

import multiprocessing
from typing import Optional

_AKSHARE_HISTORY_CALL_TIMEOUT = 30.0
_AKSHARE_TIMEOUT_PROCESS_JOIN_GRACE = 1.0
_AKSHARE_TIMEOUT_PROCESS_START_METHOD = "spawn"


def _akshare_call_with_timeout(
    func,
    *args,
    timeout: Optional[float] = None,
    call_name: str = "akshare",
    **kwargs,
):
    """Run an akshare call with a bounded wait time."""
    wait_seconds = _AKSHARE_HISTORY_CALL_TIMEOUT if timeout is None else float(timeout)

    multiprocessing.freeze_support()
    ctx = multiprocessing.get_context(_AKSHARE_TIMEOUT_PROCESS_START_METHOD)
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    process = ctx.Process(
        target=_akshare_timeout_worker,
        args=(child_conn, func, args, kwargs),
        name=f"akshare-{call_name}",
        daemon=True,
    )

    process.start()
    child_conn.close()

    try:
        if not parent_conn.poll(wait_seconds):
            _terminate_akshare_process(process)
            raise TimeoutError(f"{call_name} 调用超过 {wait_seconds:g}s，已放弃等待")

        try:
            ok, value = parent_conn.recv()
        except EOFError as exc:
            raise RuntimeError(f"{call_name} 调用进程未返回结果") from exc
    finally:
        parent_conn.close()
        process.join(_AKSHARE_TIMEOUT_PROCESS_JOIN_GRACE)
        _terminate_akshare_process(process)

    if ok:
        return value
    raise value


def _akshare_timeout_worker(conn, func, args, kwargs) -> None:
    try:
        conn.send((True, func(*args, **kwargs)))
    except BaseException as exc:  # broad-exception: cleanup - child IPC is unusable
        try:
            conn.send((False, exc))
        except BaseException:  # broad-exception: cleanup - child IPC is unusable
            try:
                conn.send((False, RuntimeError(f"{type(exc).__name__}: {exc}")))
            except BaseException:  # broad-exception: cleanup - child IPC is unusable.
                pass
    finally:
        conn.close()


def _terminate_akshare_process(process) -> None:
    if process.is_alive():
        process.terminate()
        process.join(_AKSHARE_TIMEOUT_PROCESS_JOIN_GRACE)
    if process.is_alive():
        process.kill()
        process.join(_AKSHARE_TIMEOUT_PROCESS_JOIN_GRACE)

