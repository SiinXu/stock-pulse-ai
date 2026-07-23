# -*- coding: utf-8 -*-
"""Compatibility facade for the canonical email sender."""

from src.notification_parts._facade import load_legacy_module as _load_legacy_module
from src.notification_parts.senders.email_sender import (
    Config,
    EmailSender,
    Header,
    List,
    MIMEImage,
    MIMEMultipart,
    MIMEText,
    Optional,
    SMTP_CONFIGS,
    datetime,
    formataddr,
    log_safe_exception,
    logger,
    logging,
    markdown_to_html_document,
    normalize_stock_code,
    smtplib,
)


__all__ = (
    "Config",
    "EmailSender",
    "Header",
    "List",
    "MIMEImage",
    "MIMEMultipart",
    "MIMEText",
    "Optional",
    "SMTP_CONFIGS",
    "datetime",
    "formataddr",
    "log_safe_exception",
    "logger",
    "logging",
    "markdown_to_html_document",
    "normalize_stock_code",
    "smtplib",
)

_load_legacy_module("src.notification_parts.senders.email_sender", globals(), __all__)
del _load_legacy_module
