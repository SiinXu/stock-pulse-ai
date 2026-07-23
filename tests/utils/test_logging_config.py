# -*- coding: utf-8 -*-
"""Regression tests for application logging configuration."""

import io
import logging

import pytest

from src.logging_config import LITELLM_LOGGERS, RelativePathFormatter, setup_logging


class LogMessageRenderFailure(BaseException):
    pass


class BrokenLogMessageValue:
    def __str__(self) -> str:
        raise LogMessageRenderFailure("log message conversion interrupted")

    def __repr__(self) -> str:
        return "BROKEN_LOG_MESSAGE_REPR_CANARY"


class LogMetadataFailure(BaseException):
    pass


class BrokenPathMetadata:
    def __fspath__(self) -> str:
        raise LogMetadataFailure("path conversion interrupted")

    def __str__(self) -> str:
        raise LogMetadataFailure("path string conversion interrupted")

    def __repr__(self) -> str:
        return "BROKEN_PATH_METADATA_REPR_CANARY"


class BrokenExcInfoTruthiness:
    def __bool__(self) -> bool:
        raise LogMetadataFailure("exc_info truthiness interrupted")

    def __repr__(self) -> str:
        return "BROKEN_EXC_INFO_REPR_CANARY"


class BrokenCopyLogRecord(logging.LogRecord):
    def __copy__(self):
        raise LogMetadataFailure("record copy interrupted")

    def __reduce_ex__(self, protocol):
        raise LogMetadataFailure("record reduction interrupted")


class HostileSetterLogRecord(logging.LogRecord):
    def __setattr__(self, name, value):
        if object.__getattribute__(self, "__dict__").get("_block_setattr"):
            raise LogMetadataFailure("record setter interrupted")
        super().__setattr__(name, value)


@pytest.fixture(autouse=True)
def restore_logging_state():
    root_logger = logging.getLogger()
    original_root_level = root_logger.level
    original_handlers = list(root_logger.handlers)
    original_litellm_levels = {
        logger_name: logging.getLogger(logger_name).level
        for logger_name in LITELLM_LOGGERS
    }

    yield

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        if handler not in original_handlers:
            handler.close()
    for handler in original_handlers:
        root_logger.addHandler(handler)
    root_logger.setLevel(original_root_level)

    for logger_name, level in original_litellm_levels.items():
        logging.getLogger(logger_name).setLevel(level)


def _read_debug_log(log_dir) -> str:
    for handler in logging.getLogger().handlers:
        handler.flush()
    debug_log = next(log_dir.glob("stock_analysis_debug_*.log"))
    return debug_log.read_text(encoding="utf-8")


def test_log_format_includes_logger_name(tmp_path, monkeypatch):
    monkeypatch.delenv("LITELLM_LOG_LEVEL", raising=False)

    setup_logging(log_prefix="stock_analysis", log_dir=str(tmp_path), debug=False)

    logging.getLogger("src.sample").info("logger context smoke")

    debug_log_text = _read_debug_log(tmp_path)
    assert " | src.sample | " in debug_log_text
    assert "logger context smoke" in debug_log_text


@pytest.mark.parametrize("env_value", [None, "", "  "])
def test_litellm_debug_is_quiet_by_default_and_empty_env(tmp_path, monkeypatch, env_value):
    if env_value is None:
        monkeypatch.delenv("LITELLM_LOG_LEVEL", raising=False)
    else:
        monkeypatch.setenv("LITELLM_LOG_LEVEL", env_value)

    setup_logging(log_prefix="stock_analysis", log_dir=str(tmp_path), debug=False)

    for logger_name in LITELLM_LOGGERS:
        logging.getLogger(logger_name).debug("%s token debug should be filtered", logger_name)
    logging.getLogger("LiteLLM").warning("litellm warning should remain")
    logging.getLogger("src.sample").debug("project debug should remain")

    debug_log_text = _read_debug_log(tmp_path)

    for logger_name in LITELLM_LOGGERS:
        assert f"{logger_name} token debug should be filtered" not in debug_log_text
    assert "litellm warning should remain" in debug_log_text
    assert "project debug should remain" in debug_log_text


def test_litellm_log_level_debug_restores_litellm_debug(tmp_path, monkeypatch):
    monkeypatch.setenv("LITELLM_LOG_LEVEL", "DEBUG")

    setup_logging(log_prefix="stock_analysis", log_dir=str(tmp_path), debug=False)

    for logger_name in LITELLM_LOGGERS:
        logging.getLogger(logger_name).debug("%s debug should remain", logger_name)

    debug_log_text = _read_debug_log(tmp_path)

    for logger_name in LITELLM_LOGGERS:
        assert f"{logger_name} debug should remain" in debug_log_text


def test_invalid_litellm_log_level_falls_back_to_warning(tmp_path, monkeypatch):
    monkeypatch.setenv("LITELLM_LOG_LEVEL", "verbose")

    setup_logging(log_prefix="stock_analysis", log_dir=str(tmp_path), debug=False)

    logging.getLogger("LiteLLM").debug("invalid level debug should be filtered")
    logging.getLogger("LiteLLM").warning("invalid level warning should remain")

    debug_log_text = _read_debug_log(tmp_path)

    assert "invalid level debug should be filtered" not in debug_log_text
    assert "invalid level warning should remain" in debug_log_text
    assert "LITELLM_LOG_LEVEL" in debug_log_text
    assert "falling back to WARNING" in debug_log_text


def test_configured_handlers_sanitize_legacy_exception_logging(tmp_path, monkeypatch):
    monkeypatch.delenv("LITELLM_LOG_LEVEL", raising=False)
    setup_logging(log_prefix="stock_analysis", log_dir=str(tmp_path), debug=False)

    try:
        raise ValueError(
            "api_key=logging-config-canary "
            "https://user:password@private.logging.invalid/path?token=query-canary"
        )
    except ValueError as exc:
        logging.getLogger("src.legacy").exception("Legacy exception boundary")
        logging.getLogger("src.legacy").warning("Legacy fallback failed: %s", exc)

    debug_log_text = _read_debug_log(tmp_path)
    assert "logging-config-canary" not in debug_log_text
    assert "query-canary" not in debug_log_text
    assert "private.logging.invalid" not in debug_log_text
    assert "Traceback" not in debug_log_text
    assert "exception_type=ValueError" in debug_log_text
    assert "[REDACTED]" in debug_log_text


def test_formatter_preserves_a_sanitized_record_message_for_observers():
    formatter = RelativePathFormatter("%(message)s")
    record = logging.LogRecord(
        name="src.observer",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="Legacy failure: api_key=%s",
        args=("formatter-observer-canary",),
        exc_info=None,
    )

    rendered = formatter.format(record)

    assert record.message == rendered
    assert record.getMessage() == rendered
    assert record.args == ()
    assert record.exc_info is None
    assert "formatter-observer-canary" not in record.message
    assert "[REDACTED]" in record.message


def test_formatter_fails_closed_when_message_rendering_raises_base_exception():
    formatter = RelativePathFormatter("%(message)s")
    record = logging.LogRecord(
        name="src.broken_observer",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="Legacy failure: %s",
        args=(BrokenLogMessageValue(),),
        exc_info=None,
    )

    escaped = None
    rendered = None
    try:
        rendered = formatter.format(record)
    except BaseException as exc:  # pragma: no cover - asserted below
        escaped = exc

    assert escaped is None
    assert rendered is not None
    assert "Log message formatting failed" in rendered
    assert "BROKEN_LOG_MESSAGE_REPR_CANARY" not in rendered
    assert record.exc_info is None


def test_formatter_fails_closed_for_hostile_path_and_relative_root_metadata():
    record = logging.LogRecord(
        name="src.hostile_path",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="ordinary message",
        args=(),
        exc_info=None,
    )
    record.pathname = BrokenPathMetadata()

    escaped = None
    rendered = None
    try:
        formatter = RelativePathFormatter(
            "%(pathname)s | %(message)s",
            relative_to=BrokenPathMetadata(),
        )
        rendered = formatter.format(record)
    except BaseException as exc:  # pragma: no cover - asserted below
        escaped = exc

    assert escaped is None
    assert rendered is not None
    assert "BROKEN_PATH_METADATA_REPR_CANARY" not in rendered


def test_formatter_redacts_out_of_root_path_metadata():
    formatter = RelativePathFormatter(
        "%(pathname)s | %(message)s",
        relative_to="/safe/project",
    )
    record = logging.LogRecord(
        name="src.outside_path",
        level=logging.WARNING,
        pathname="/outside/api_key=PATH_METADATA_CANARY.py",
        lineno=1,
        msg="ordinary message",
        args=(),
        exc_info=None,
    )

    rendered = formatter.format(record)

    assert "PATH_METADATA_CANARY" not in rendered
    assert "/outside/" not in rendered
    assert "PATH_METADATA_CANARY" not in str(record.pathname)


def test_formatter_fails_closed_for_malformed_or_hostile_exc_info():
    formatter = RelativePathFormatter("%(message)s")
    exc_info_values = (
        (None,),
        BrokenExcInfoTruthiness(),
    )

    for exc_info in exc_info_values:
        record = logging.LogRecord(
            name="src.hostile_exc_info",
            level=logging.WARNING,
            pathname=__file__,
            lineno=1,
            msg="ordinary message",
            args=(),
            exc_info=None,
        )
        record.exc_info = exc_info
        escaped = None
        rendered = None
        try:
            rendered = formatter.format(record)
        except BaseException as exc:  # pragma: no cover - asserted below
            escaped = exc

        assert escaped is None
        assert rendered is not None
        assert "BROKEN_EXC_INFO_REPR_CANARY" not in rendered
        assert record.exc_info is None


def test_formatter_uses_plain_safe_record_for_copy_setter_and_standard_metadata():
    formatter = RelativePathFormatter(
        "%(name)s | %(levelname)s | %(lineno)s | %(created)s | %(message)s"
    )
    records = (
        BrokenCopyLogRecord(
            "src.copy",
            logging.ERROR,
            __file__,
            1,
            "ordinary message",
            (),
            None,
        ),
        HostileSetterLogRecord(
            "src.setter",
            logging.ERROR,
            __file__,
            1,
            "ordinary message",
            (),
            None,
        ),
    )
    object.__setattr__(records[1], "_block_setattr", True)
    for record in records:
        record_dict = object.__getattribute__(record, "__dict__")
        record_dict["name"] = "api_key=NAME_METADATA_CANARY"
        record_dict["levelname"] = "token=LEVEL_METADATA_CANARY"
        record_dict["lineno"] = BrokenLogMessageValue()
        record_dict["created"] = BrokenLogMessageValue()

        escaped = None
        rendered = None
        try:
            rendered = formatter.format(record)
        except BaseException as exc:  # pragma: no cover - asserted below
            escaped = exc

        assert escaped is None
        assert rendered is not None
        assert "NAME_METADATA_CANARY" not in rendered
        assert "LEVEL_METADATA_CANARY" not in rendered
        assert "BROKEN_LOG_MESSAGE_REPR_CANARY" not in rendered
        scrubbed_fields = object.__getattribute__(record, "__dict__")
        assert "NAME_METADATA_CANARY" not in str(scrubbed_fields["name"])
        assert "LEVEL_METADATA_CANARY" not in str(scrubbed_fields["levelname"])
        assert scrubbed_fields["lineno"] == 0


def test_formatter_scrubs_shared_record_before_later_handler():
    safe_stream = io.StringIO()
    plain_stream = io.StringIO()
    logger = logging.Logger("tests.formatter_order", level=logging.ERROR)

    safe_handler = logging.StreamHandler(safe_stream)
    safe_handler.setFormatter(RelativePathFormatter("%(message)s"))
    plain_handler = logging.StreamHandler(plain_stream)
    plain_handler.setFormatter(logging.Formatter("%(message)s"))
    later_records = []
    plain_handler.addFilter(lambda record: later_records.append(record) or True)
    logger.addHandler(safe_handler)
    logger.addHandler(plain_handler)

    try:
        raise RuntimeError("api_key=FORMATTER_ORDER_CANARY")
    except RuntimeError:
        logger.exception("failure token=FORMATTER_MESSAGE_CANARY")

    safe_output = safe_stream.getvalue()
    plain_output = plain_stream.getvalue()
    assert "failure token=[REDACTED]" in safe_output
    assert "exception_type=RuntimeError" in safe_output
    assert "failure token=[REDACTED]" in plain_output
    assert "exception_type=RuntimeError" in plain_output
    for output in (safe_output, plain_output):
        assert "FORMATTER_ORDER_CANARY" not in output
        assert "FORMATTER_MESSAGE_CANARY" not in output
        assert "Traceback" not in output

    assert len(later_records) == 1
    later_record = later_records[0]
    assert "FORMATTER_ORDER_CANARY" not in later_record.getMessage()
    assert "FORMATTER_MESSAGE_CANARY" not in later_record.getMessage()
    assert later_record.exc_info is None
