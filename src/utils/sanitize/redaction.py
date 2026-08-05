# -*- coding: utf-8 -*-
"""Exception redaction machinery and chain primitives."""

from __future__ import annotations

import inspect
from typing import Any, Callable, Iterable, Mapping, Optional

_REDACTED = "[REDACTED]"
_SAFE_EXCEPTION_CHAIN_LIMIT = 4
_SAFE_EXCEPTION_PART_MAX_LENGTH = 240
_SAFE_EXCEPTION_SUMMARY_MAX_LENGTH = 900
_EXACT_REDACTION_VALUE_LIMIT = 64
_EXCEPTION_REDACTION_FAIL_CLOSED_LIMIT = _EXACT_REDACTION_VALUE_LIMIT + 1
_SAFE_RENDER_FAILURE = "[UNRENDERABLE]"
_UNSAFE_EXCEPTION_ACCESS = object()
_EXCEPTION_REDACTION_PROVENANCE = "\0stockpulse-exception-redaction\0"


class _ExceptionRedactionSnapshot:
    def __init__(self, root_id: int) -> None:
        self.root_id = root_id
        self.summary = _SAFE_RENDER_FAILURE


class _ExceptionRedactionValue(str):
    """Carry snapshot provenance without changing the public set contract."""

    def __new__(cls, value: str, snapshot: _ExceptionRedactionSnapshot):
        instance = super().__new__(cls, value)
        instance.snapshot = snapshot
        return instance

    def __copy__(self):
        return self

    def __deepcopy__(self, memo: dict[int, Any]):
        memo[id(self)] = self
        return self

    def __reduce__(self):
        return type(self), (str(self), self.snapshot)


class _ExceptionRedactionMarker(str):
    """Keep provenance when an empty or failed snapshot is copied or merged."""

    def __new__(cls, snapshot: _ExceptionRedactionSnapshot):
        instance = super().__new__(cls, _EXCEPTION_REDACTION_PROVENANCE)
        instance.snapshot = snapshot
        return instance

    def __hash__(self) -> int:
        return object.__hash__(self)

    def __eq__(self, other: object) -> bool:
        return self is other

    def __ne__(self, other: object) -> bool:
        return self is not other

    def __copy__(self):
        return self

    def __deepcopy__(self, memo: dict[int, Any]):
        memo[id(self)] = self
        return self

    def __reduce__(self):
        return type(self), (self.snapshot,)


class _ExceptionRedactionValues(set[str]):
    """Exact redactions paired with a single-render sanitized chain snapshot."""

    def __init__(self, root_id: int) -> None:
        super().__init__()
        self.snapshot = _ExceptionRedactionSnapshot(root_id)
        super().add(_ExceptionRedactionMarker(self.snapshot))

    def add_snapshot_value(self, value: str) -> None:
        super().add(_ExceptionRedactionValue(value, self.snapshot))

    def __copy__(self) -> set[str]:
        return set(self)

    def __deepcopy__(self, memo: dict[int, Any]) -> set[str]:
        del memo
        return set(self)

    @property
    def root_id(self) -> int:
        return self.snapshot.root_id

    @property
    def summary(self) -> str:
        return self.snapshot.summary

    @summary.setter
    def summary(self, value: str) -> None:
        self.snapshot.summary = value


class _NormalizedRedactionValues(tuple):
    """Normalized exact values with optional exception snapshot provenance."""

    def __new__(
        cls,
        values: Iterable[str],
        *,
        exception_snapshots: Iterable[_ExceptionRedactionSnapshot] = (),
    ):
        instance = super().__new__(cls, values)
        instance.exception_snapshots = tuple(exception_snapshots)
        instance.trusted_exception_parts: set[str] = set()
        return instance

    def __init__(
        self,
        values: Iterable[str],
        *,
        exception_snapshots: Iterable[_ExceptionRedactionSnapshot] = (),
    ) -> None:
        del values, exception_snapshots


def _bounded_render_failure(max_length: Any) -> str:
    """Return the fixed render-failure marker without trusting a custom bound."""

    if type(max_length) is not int:
        return _SAFE_RENDER_FAILURE
    return _SAFE_RENDER_FAILURE[: max(0, max_length)]


def _safe_string(value: Any) -> str:
    """Render one value without consulting repr or propagating conversion failures."""

    if value is None:
        return ""
    try:
        return str(value)
    except BaseException:
        return _SAFE_RENDER_FAILURE


def _safe_structured_string(
    value: Any,
    *,
    nested: bool = False,
    _custom_values: Optional[dict[int, str]] = None,
) -> str:
    """Render built-in containers without invoking repr on nested custom objects."""

    if _custom_values is None:
        _custom_values = {}

    if type(value) is str:
        return repr(value) if nested else value
    if value is None:
        return "None" if nested else ""
    if type(value) in {bool, int, float, complex, bytes}:
        return str(value)
    if type(value) is dict:
        try:
            items = (
                f"{_safe_structured_string(key, nested=True, _custom_values=_custom_values)}: "
                f"{_safe_structured_string(item, nested=True, _custom_values=_custom_values)}"
                for key, item in value.items()
            )
            return "{" + ", ".join(items) + "}"
        except BaseException:
            return _SAFE_RENDER_FAILURE
    if type(value) is list:
        try:
            return "[" + ", ".join(
                _safe_structured_string(
                    item,
                    nested=True,
                    _custom_values=_custom_values,
                )
                for item in value
            ) + "]"
        except BaseException:
            return _SAFE_RENDER_FAILURE
    if type(value) is tuple:
        try:
            rendered = ", ".join(
                _safe_structured_string(
                    item,
                    nested=True,
                    _custom_values=_custom_values,
                )
                for item in value
            )
            if len(value) == 1:
                rendered += ","
            return f"({rendered})"
        except BaseException:
            return _SAFE_RENDER_FAILURE
    if type(value) in {set, frozenset}:
        try:
            rendered_items = sorted(
                _safe_structured_string(
                    item,
                    nested=True,
                    _custom_values=_custom_values,
                )
                for item in value
            )
            if type(value) is set:
                return "set()" if not rendered_items else "{" + ", ".join(rendered_items) + "}"
            if not rendered_items:
                return "frozenset()"
            return "frozenset({" + ", ".join(rendered_items) + "})"
        except BaseException:
            return _SAFE_RENDER_FAILURE

    identity = id(value)
    rendered = _custom_values.get(identity)
    if rendered is None:
        rendered = _safe_string(value)
        _custom_values[identity] = rendered
    return repr(rendered) if nested else rendered


def _normalize_redaction_values(
    redaction_values: Optional[Iterable[Any]],
) -> Optional[_NormalizedRedactionValues]:
    """Return bounded exact-match values, or None when normalization is unsafe."""
    if isinstance(redaction_values, _NormalizedRedactionValues):
        return redaction_values
    if redaction_values is None:
        return _NormalizedRedactionValues(())
    candidates: Iterable[Any]
    if isinstance(redaction_values, (str, bytes)):
        candidates = (redaction_values,)
    else:
        candidates = redaction_values

    normalized: set[str] = set()
    snapshots: dict[int, _ExceptionRedactionSnapshot] = {}
    if isinstance(redaction_values, _ExceptionRedactionValues):
        snapshots[redaction_values.root_id] = redaction_values.snapshot
    try:
        iterator = iter(candidates)
    except TypeError:
        iterator = iter((candidates,))
    except BaseException:
        return None
    try:
        for value in iterator:
            if value is None:
                continue
            if isinstance(value, (_ExceptionRedactionValue, _ExceptionRedactionMarker)):
                snapshot = value.snapshot
                snapshots[snapshot.root_id] = snapshot
                if isinstance(value, _ExceptionRedactionMarker):
                    continue
            rendered = (
                value.decode("utf-8", errors="replace")
                if isinstance(value, bytes)
                else str(value)
            )
            if rendered == _EXCEPTION_REDACTION_PROVENANCE:
                return None
            if rendered == _SAFE_RENDER_FAILURE:
                continue
            if rendered.strip():
                normalized.add(rendered)
                if len(normalized) > _EXACT_REDACTION_VALUE_LIMIT:
                    return None
    except BaseException:
        return None
    return _NormalizedRedactionValues(
        sorted(normalized, key=len, reverse=True),
        exception_snapshots=snapshots.values(),
    )


def _matching_exception_snapshot(
    values: _NormalizedRedactionValues,
    error: Any,
) -> Optional[_ExceptionRedactionSnapshot]:
    root_id = id(error)
    return next(
        (
            snapshot
            for snapshot in values.exception_snapshots
            if snapshot.root_id == root_id
        ),
        None,
    )


def has_matching_exception_snapshot(
    error: Any,
    redaction_values: Optional[Iterable[Any]],
) -> bool:
    """Return whether values carry a single-render snapshot for ``error``."""

    exact_values = _normalize_redaction_values(redaction_values)
    return (
        exact_values is not None
        and _matching_exception_snapshot(exact_values, error) is not None
    )


def _redact_exact_values(text: str, redaction_values: tuple[str, ...]) -> str:
    """Replace caller-provided sensitive values before pattern sanitization."""
    redacted = text
    for value in redaction_values:
        redacted = redacted.replace(value, _REDACTED)
    return redacted


def _safe_exception_diagnostic_source(error: BaseException) -> Any:
    """Select a diagnostic source without triggering built-in nested repr paths."""

    try:
        args = error.args
        if type(args) is not tuple:
            return _UNSAFE_EXCEPTION_ACCESS
        if not args:
            return error

        string_method = inspect.getattr_static(type(error), "__str__", None)
        render_args = (
            len(args) > 1
            or isinstance(args[0], (Mapping, list, tuple, set, frozenset))
            or inspect.ismethoddescriptor(string_method)
        )
        if render_args:
            return args[0] if len(args) == 1 else args
        return error
    except BaseException:
        return _UNSAFE_EXCEPTION_ACCESS


def _safe_next_exception(error: BaseException) -> Any:
    """Read the next explicit or implicit exception without propagating access errors."""

    try:
        cause = error.__cause__
        if cause is not None:
            return cause if isinstance(cause, BaseException) else _UNSAFE_EXCEPTION_ACCESS

        suppress_context = error.__suppress_context__
        if type(suppress_context) is not bool:
            return _UNSAFE_EXCEPTION_ACCESS
        if suppress_context:
            return None

        context = error.__context__
        if context is None or isinstance(context, BaseException):
            return context
        return _UNSAFE_EXCEPTION_ACCESS
    except BaseException:
        return _UNSAFE_EXCEPTION_ACCESS
