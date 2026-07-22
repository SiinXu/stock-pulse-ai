# -*- coding: utf-8 -*-
"""
===================================
Markdown 转图片工具模块
===================================

将 Markdown 转为 PNG 图片（用于不支持 Markdown 的通知渠道）。
支持 wkhtmltoimage (imgkit) 与 markdown-to-file (m2f)，后者对 emoji 支持更好 (Issue #455)。

Security note: imgkit passes HTML to wkhtmltoimage via stdin, not argv, so
command injection from content is not applicable. Output is rasterized to PNG
(no script execution). Input is from system-generated reports, not raw user
input. Risk is considered low for the current use case.
"""

import logging
import os
import shutil
import subprocess
import tempfile
from typing import Optional

from src.formatters import markdown_to_html_document
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)


def _markdown_to_image_m2f(markdown_text: str) -> Optional[bytes]:
    """Convert Markdown to PNG via markdown-to-file (m2f) CLI. Better emoji support (Issue #455)."""
    if shutil.which("m2f") is None:
        logger.warning(
            "m2f (markdown-to-file) not found in PATH. "
            "Install with: npm i -g markdown-to-file. Fallback to text."
        )
        return None

    temp_dir = None
    try:
        temp_dir = tempfile.mkdtemp()
        md_path = os.path.join(temp_dir, "report.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)

        result = subprocess.run(
            ["m2f", md_path, "png", f"outputDirectory={temp_dir}"],
            capture_output=True,
            timeout=60,
            check=False,
        )
        png_path = os.path.join(temp_dir, "report.png")
        if result.returncode != 0 or not os.path.isfile(png_path):
            logger.warning(
                "m2f conversion failed: returncode=%s, stderr=%s",
                result.returncode,
                (result.stderr or b"").decode("utf-8", errors="replace")[:200],
            )
            return None

        with open(png_path, "rb") as f:
            return f.read()
    except subprocess.TimeoutExpired:
        logger.warning("m2f conversion timed out (60s)")
        return None
    except Exception as exc:
        log_safe_exception(
            logger,
            "Markdown-to-file image conversion failed",
            exc,
            error_code="markdown_to_file_conversion_failed",
            level=logging.WARNING,
        )
        return None
    finally:
        if temp_dir and os.path.isdir(temp_dir):
            try:
                shutil.rmtree(temp_dir)
            except OSError as exc:
                log_safe_exception(
                    logger,
                    "Markdown image temporary directory cleanup failed",
                    exc,
                    error_code="markdown_image_temp_cleanup_failed",
                    level=logging.DEBUG,
                )


def _markdown_to_image_wkhtml(markdown_text: str) -> Optional[bytes]:
    """Convert Markdown to PNG via imgkit/wkhtmltoimage."""
    try:
        import imgkit
    except ImportError:
        logger.debug("imgkit not installed, markdown_to_image unavailable")
        return None

    html = markdown_to_html_document(markdown_text)
    try:
        options = {
            "format": "png",
            "encoding": "UTF-8",
            "quiet": "",
        }
        out = imgkit.from_string(html, False, options=options)
        if out and isinstance(out, bytes) and len(out) > 0:
            return out
        logger.warning("imgkit.from_string returned empty or invalid result")
        return None
    except OSError as exc:
        if "wkhtmltoimage" in str(exc).lower() or "wkhtmltopdf" in str(exc).lower():
            log_safe_exception(
                logger,
                "wkhtmltoimage executable is unavailable",
                exc,
                error_code="wkhtmltoimage_unavailable",
                level=logging.DEBUG,
            )
        else:
            log_safe_exception(
                logger,
                "wkhtmltoimage conversion failed",
                exc,
                error_code="wkhtmltoimage_conversion_failed",
                level=logging.WARNING,
            )
        return None
    except Exception as exc:
        log_safe_exception(
            logger,
            "Markdown image conversion failed",
            exc,
            error_code="markdown_image_conversion_failed",
            level=logging.WARNING,
        )
        return None


def markdown_to_image(markdown_text: str, max_chars: int = 15000) -> Optional[bytes]:
    """
    Convert Markdown to PNG image bytes.

    Engine is read from config.md2img_engine: wkhtmltoimage (default) or
    markdown-to-file (better emoji support, Issue #455).

    When conversion fails or dependencies unavailable, returns None so caller
    can fall back to text sending.

    Args:
        markdown_text: Raw Markdown content.
        max_chars: Skip conversion and return None if content exceeds this length
            (avoids huge images). Default 15000.

    Returns:
        PNG bytes, or None if conversion fails or dependencies unavailable.
    """
    if len(markdown_text) > max_chars:
        logger.warning(
            "Markdown content (%d chars) exceeds max_chars (%d), skipping image conversion",
            len(markdown_text),
            max_chars,
        )
        return None

    try:
        from src.config import get_config

        engine = getattr(get_config(), "md2img_engine", "wkhtmltoimage")
    except Exception:
        engine = "wkhtmltoimage"

    if engine == "markdown-to-file":
        return _markdown_to_image_m2f(markdown_text)
    return _markdown_to_image_wkhtml(markdown_text)
