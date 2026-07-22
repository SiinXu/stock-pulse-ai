# -*- coding: utf-8 -*-
"""
===================================
日志配置模块 - 统一的日志系统初始化
===================================

职责：
1. 提供统一的日志格式和配置常量
2. 支持控制台 + 文件（常规/调试）三层日志输出
3. 自动降低第三方库日志级别
"""

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Optional, Tuple

from src.utils.sanitize import (
    safe_exception_type_name,
    sanitize_diagnostic_text,
    sanitize_exception_chain,
)


LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(pathname)s:%(lineno)d | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
_ALLOWED_LOG_LEVELS = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL,
}
_DEFAULT_LITELLM_LOG_LEVEL = 'WARNING'


class RelativePathFormatter(logging.Formatter):
    """自定义 Formatter，输出相对路径而非绝对路径"""

    def __init__(self, fmt=None, datefmt=None, relative_to=None):
        super().__init__(fmt, datefmt)
        try:
            self.relative_to = (
                Path.cwd() if relative_to is None else Path(relative_to)
            )
        except BaseException:
            self.relative_to = None

    @staticmethod
    def _record_fields(record) -> dict:
        try:
            fields = object.__getattribute__(record, "__dict__")
        except BaseException:
            return {}
        return fields if type(fields) is dict else {}

    @staticmethod
    def _render_message(fields: dict) -> str:
        try:
            message = str(fields.get("msg", ""))
            args = fields.get("args", ())
            if args is None:
                args = ()
            if type(args) not in {dict, tuple}:
                return "Log message formatting failed"
            if args:
                message = message % args
            return sanitize_diagnostic_text(message, max_length=4000)
        except BaseException:
            return "Log message formatting failed"

    def _safe_pathname(self, raw_pathname) -> str:
        try:
            pathname = Path(raw_pathname)
            if pathname.is_absolute():
                if self.relative_to is None:
                    return "[REDACTED_PATH]"
                try:
                    pathname = pathname.relative_to(self.relative_to)
                except ValueError:
                    return "[REDACTED_PATH]"
            return (
                sanitize_diagnostic_text(str(pathname), max_length=500)
                or "[UNRENDERABLE]"
            )
        except BaseException:
            return "[UNRENDERABLE]"

    @staticmethod
    def _safe_integer(value, *, fallback: int) -> int:
        if type(value) is not int:
            return fallback
        return value

    @staticmethod
    def _scrub_shared_record(record, safe_record: logging.LogRecord) -> None:
        safe_fields = object.__getattribute__(safe_record, "__dict__")
        for name in (
            "args",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "message",
            "module",
            "msecs",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
        ):
            if name not in safe_fields:
                continue
            try:
                object.__setattr__(record, name, safe_fields[name])
            except BaseException:
                continue

    def format(self, record):
        fields = self._record_fields(record)
        safe_message = self._render_message(fields)
        exc_info = fields.get("exc_info")
        if (
            type(exc_info) is tuple
            and len(exc_info) == 3
            and isinstance(exc_info[1], BaseException)
        ):
            exc = exc_info[1]
            summary = sanitize_exception_chain(exc)
            safe_message = " ".join(
                part
                for part in (
                    safe_message,
                    f"exception_type={safe_exception_type_name(exc)}",
                    f"summary={summary}",
                )
                if part
            )
        elif exc_info is not None:
            safe_message = " ".join(
                part
                for part in (
                    safe_message,
                    "exception_metadata=[UNRENDERABLE]",
                )
                if part
            )

        safe_name = (
            sanitize_diagnostic_text(fields.get("name"), max_length=160)
            or "unknown_logger"
        )
        safe_level = self._safe_integer(
            fields.get("levelno"),
            fallback=logging.ERROR,
        )
        safe_pathname = self._safe_pathname(fields.get("pathname", ""))
        safe_lineno = self._safe_integer(fields.get("lineno"), fallback=0)
        safe_func = (
            sanitize_diagnostic_text(fields.get("funcName"), max_length=160)
            or None
        )
        try:
            safe_record = logging.LogRecord(
                name=safe_name,
                level=safe_level,
                pathname=safe_pathname,
                lineno=safe_lineno,
                msg=safe_message,
                args=(),
                exc_info=None,
                func=safe_func,
                sinfo=None,
            )
            safe_record.message = safe_message
            self._scrub_shared_record(record, safe_record)
            return super().format(safe_record)
        except BaseException:
            return "Log record formatting failed"


# Defaults to lowering the log level of third-party libraries
DEFAULT_QUIET_LOGGERS = [
    'urllib3',
    'sqlalchemy',
    'google',
    'httpx',
]

LITELLM_LOGGERS = [
    'LiteLLM',
    'LiteLLM Router',
    'LiteLLM Proxy',
    'litellm',
]


def _resolve_litellm_log_level(raw_level: Optional[str] = None) -> Tuple[int, Optional[str]]:
    """Resolve LiteLLM logger level from env, returning invalid raw value if any."""
    if raw_level is None:
        raw_level = os.getenv('LITELLM_LOG_LEVEL', '')

    normalized = (raw_level or '').strip().upper()
    if not normalized:
        normalized = _DEFAULT_LITELLM_LOG_LEVEL

    level = _ALLOWED_LOG_LEVELS.get(normalized)
    if level is None:
        return _ALLOWED_LOG_LEVELS[_DEFAULT_LITELLM_LOG_LEVEL], raw_level
    return level, None


def setup_logging(
    log_prefix: str = "app",
    log_dir: str = "./logs",
    console_level: Optional[int] = None,
    debug: bool = False,
    extra_quiet_loggers: Optional[List[str]] = None,
) -> None:
    """
    统一的日志系统初始化

    配置三层日志输出：
    1. 控制台：根据 debug 参数或 console_level 设置级别
    2. 常规日志文件：INFO 级别，10MB 轮转，保留 5 个备份
    3. 调试日志文件：DEBUG 级别，50MB 轮转，保留 3 个备份

    Args:
        log_prefix: 日志文件名前缀（如 "api_server" -> api_server_20240101.log）
        log_dir: 日志文件目录，默认 ./logs
        console_level: 控制台日志级别（可选，优先于 debug 参数）
        debug: 是否启用调试模式（控制台输出 DEBUG 级别）
        extra_quiet_loggers: 额外需要降低日志级别的第三方库列表
    """
    # Determine console log level
    if console_level is not None:
        level = console_level
    else:
        level = logging.DEBUG if debug else logging.INFO

    # Create log directory
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)

    # Log file path (split by date)
    today_str = datetime.now().strftime('%Y%m%d')
    log_file = log_path / f"{log_prefix}_{today_str}.log"
    debug_log_file = log_path / f"{log_prefix}_debug_{today_str}.log"

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)  # Set logger to DEBUG, let handler control output level

    # Clear existing handlers to avoid adding duplicates
    if root_logger.handlers:
        root_logger.handlers.clear()
    # Create relative path Formatter (relative to project root)
    project_root = Path.cwd()
    rel_formatter = RelativePathFormatter(
        LOG_FORMAT, LOG_DATE_FORMAT, relative_to=project_root
    )
    # Handler 1: Console output
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(rel_formatter)
    root_logger.addHandler(console_handler)

    # Handler 2: Regular log file (INFO level, 10MB rotation)
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(rel_formatter)
    root_logger.addHandler(file_handler)

    # Handler 3: Debug log file (DEBUG level, includes all detailed information)
    debug_handler = RotatingFileHandler(
        debug_log_file,
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=3,
        encoding='utf-8'
    )
    debug_handler.setLevel(logging.DEBUG)
    debug_handler.setFormatter(rel_formatter)
    root_logger.addHandler(debug_handler)

    # Reduce the logging level of third-party libraries.
    quiet_loggers = DEFAULT_QUIET_LOGGERS.copy()
    if extra_quiet_loggers:
        quiet_loggers.extend(extra_quiet_loggers)

    for logger_name in quiet_loggers:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    litellm_level, invalid_litellm_level = _resolve_litellm_log_level()
    for logger_name in LITELLM_LOGGERS:
        logging.getLogger(logger_name).setLevel(litellm_level)

    # Output initialization completion information (using relative path)
    try:
        rel_log_path = log_path.resolve().relative_to(project_root)
    except ValueError:
        rel_log_path = log_path

    try:
        rel_log_file = log_file.resolve().relative_to(project_root)
    except ValueError:
        rel_log_file = log_file

    try:
        rel_debug_log_file = debug_log_file.resolve().relative_to(project_root)
    except ValueError:
        rel_debug_log_file = debug_log_file

    logging.info("Logging initialized; directory: %s", rel_log_path)
    logging.info("Application log: %s", rel_log_file)
    logging.info("Debug log: %s", rel_debug_log_file)
    if invalid_litellm_level is not None:
        logging.warning(
            "Invalid LITELLM_LOG_LEVEL=%r; falling back to %s. Allowed values: %s",
            invalid_litellm_level,
            _DEFAULT_LITELLM_LOG_LEVEL,
            ", ".join(_ALLOWED_LOG_LEVELS),
        )
