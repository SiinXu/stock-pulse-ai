# Copyright (c) 2026 SiinXu / StockPulse contributors
# SPDX-License-Identifier: AGPL-3.0-only
"""Local offline OCR for agent image extraction (issue #196).

Extracts raw text/numbers from user-supplied chart screenshots, brokerage
statements, and table-like images using an optional system Tesseract engine.
Never uploads bytes to a cloud vision model. Complements (does not replace)
``chart_reading_service`` (semantic chart understanding via Vision LLM) and
``image_stock_extractor`` (stock-code extraction via Vision LLM).
"""

from __future__ import annotations

import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Sequence

from src.services.pdf_parsing_service import resolve_safe_file_path
from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

OCR_SCHEMA_VERSION = "ocr-extract-v1"
OCR_DISCLAIMER = (
    "OCR text is a local, model-free extraction for research support only. "
    "Dense tables and low-contrast screenshots may be incomplete or noisy. "
    "Not investment advice and not a substitute for source documents."
)

MAX_OCR_IMAGE_BYTES = 5 * 1024 * 1024  # 5 MiB — aligned with image_stock_extractor
DEFAULT_OCR_TIMEOUT_SECONDS = 30
MIN_OCR_TIMEOUT_SECONDS = 1
MAX_OCR_TIMEOUT_SECONDS = 120
DEFAULT_OCR_LANGS = "chi_sim+eng"
MAX_OCR_TEXT_CHARS = 50_000
MAX_OCR_LINES = 500

ALLOWED_OCR_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif"})
MIME_BY_SUFFIX = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
}
_IMAGE_SIGNATURES = {
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
    "image/gif": (b"GIF87a", b"GIF89a"),
    "image/webp": (b"RIFF",),  # plus WEBP at [8:12]
}
_LANG_TOKEN_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")

OcrEngine = Callable[[bytes, str, str], str]
"""(image_bytes, mime_type, langs) -> raw text."""


def _result(
    *,
    status: str,
    reason_code: Optional[str] = None,
    text: str = "",
    lines: Optional[Sequence[str]] = None,
    langs: str = DEFAULT_OCR_LANGS,
    engine: str = "none",
    source: Optional[Mapping[str, Any]] = None,
    duration_ms: Optional[int] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": OCR_SCHEMA_VERSION,
        "status": status,
        "reason_code": reason_code,
        "text": text[:MAX_OCR_TEXT_CHARS],
        "lines": list(lines or [])[:MAX_OCR_LINES],
        "langs": langs,
        "engine": engine,
        "source": dict(source or {}),
        "disclaimer": OCR_DISCLAIMER,
    }
    if duration_ms is not None:
        payload["duration_ms"] = int(duration_ms)
    return payload


def normalize_ocr_langs(raw: Optional[str]) -> str:
    """Return a sanitized Tesseract language string or the default."""
    if raw is None:
        return DEFAULT_OCR_LANGS
    text = str(raw).strip().lower().replace(" ", "")
    if not text:
        return DEFAULT_OCR_LANGS
    parts = [p for p in text.split("+") if p]
    if not parts or len(parts) > 8:
        return DEFAULT_OCR_LANGS
    if any(not _LANG_TOKEN_RE.match(p) for p in parts):
        return DEFAULT_OCR_LANGS
    return "+".join(parts)


def clamp_ocr_timeout(raw: Any) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_OCR_TIMEOUT_SECONDS
    return max(MIN_OCR_TIMEOUT_SECONDS, min(value, MAX_OCR_TIMEOUT_SECONDS))


def _suffix_mime(path: Path) -> Optional[str]:
    return MIME_BY_SUFFIX.get(path.suffix.lower())


def _verify_magic_bytes(image_bytes: bytes, mime_type: str) -> None:
    if len(image_bytes) < 12:
        raise ValueError("image_too_small")
    if mime_type == "image/webp":
        if image_bytes[:4] != b"RIFF" or image_bytes[8:12] != b"WEBP":
            raise ValueError("mime_mismatch")
        return
    signatures = _IMAGE_SIGNATURES.get(mime_type)
    if not signatures:
        raise ValueError("unsupported_mime")
    if not any(image_bytes.startswith(sig) for sig in signatures):
        raise ValueError("mime_mismatch")


def _split_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        cleaned = raw.strip()
        if cleaned:
            lines.append(cleaned[:500])
        if len(lines) >= MAX_OCR_LINES:
            break
    return lines


def assess_ocr_dependencies(
    *,
    import_probe: Optional[Callable[[str], bool]] = None,
) -> dict[str, Any]:
    """Probe optional Python package and system Tesseract binary readiness."""

    def _default_probe(module_name: str) -> bool:
        try:
            __import__(module_name)
            return True
        except Exception:  # broad-exception: fallback_recorded - dependency probe must never raise
            logger.debug("OCR dependency readiness probe failed module=%s", module_name)
            return False

    probe = import_probe or _default_probe
    pytesseract_ok = bool(probe("pytesseract"))
    pil_ok = bool(probe("PIL"))

    tesseract_version: Optional[str] = None
    binary_ok = False
    if pytesseract_ok:
        try:
            import pytesseract  # type: ignore[import-not-found]

            version = pytesseract.get_tesseract_version()
            tesseract_version = str(version)
            binary_ok = True
        except Exception as exc:  # broad-exception: fallback_recorded - readiness probe only
            log_safe_exception(
                logger,
                "Tesseract binary probe failed",
                exc,
                error_code="ocr_tesseract_probe_failed",
                level=logging.DEBUG,
            )
            binary_ok = False

    ready = pytesseract_ok and pil_ok and binary_ok
    if not pytesseract_ok or not pil_ok:
        reason = "python_deps_missing"
        message = (
            "Install optional OCR packages with: "
            "python -m pip install --constraint constraints.txt "
            "--build-constraint build-constraints.txt -r requirements-ocr.txt "
            "(Pillow + pytesseract)."
        )
    elif not binary_ok:
        reason = "tesseract_binary_missing"
        message = (
            "Install system Tesseract OCR and language packs "
            "(e.g. brew install tesseract tesseract-lang, or apt install "
            "tesseract-ocr tesseract-ocr-chi-sim). Chinese needs chi_sim."
        )
    else:
        reason = "ready"
        message = "OCR dependencies are available."

    return {
        "ready": ready,
        "reason": reason,
        "message": message,
        "pytesseract": pytesseract_ok,
        "pillow": pil_ok,
        "tesseract_binary": binary_ok,
        "tesseract_version": tesseract_version,
    }


def _default_tesseract_engine(image_bytes: bytes, mime_type: str, langs: str) -> str:
    """Run Tesseract via pytesseract. Raises on engine failure."""
    import io

    import pytesseract  # type: ignore[import-not-found]
    from PIL import Image

    with Image.open(io.BytesIO(image_bytes)) as image:
        rgb = image.convert("RGB")
        return pytesseract.image_to_string(rgb, lang=langs)


class OcrExtractionService:
    """Sandbox-aware local OCR for files under a configured root."""

    def __init__(
        self,
        *,
        file_root: str,
        langs: str = DEFAULT_OCR_LANGS,
        timeout_seconds: int = DEFAULT_OCR_TIMEOUT_SECONDS,
        engine: Optional[OcrEngine] = None,
        dependency_probe: Optional[Callable[[str], bool]] = None,
    ) -> None:
        root = str(file_root or "").strip()
        if not root:
            raise ValueError("file_root_required")
        self._file_root = root
        self._langs = normalize_ocr_langs(langs)
        self._timeout_seconds = clamp_ocr_timeout(timeout_seconds)
        self._engine = engine
        self._dependency_probe = dependency_probe

    def extract_path(self, file_path: str, *, langs: Optional[str] = None) -> dict[str, Any]:
        """OCR a local image path under the configured file root."""
        effective_langs = normalize_ocr_langs(langs) if langs is not None else self._langs
        try:
            resolved = resolve_safe_file_path(file_path, file_root=self._file_root)
        except ValueError as exc:
            return _result(
                status="unavailable",
                reason_code=str(exc),
                langs=effective_langs,
                source={"filename": Path(str(file_path or "")).name[:255], "byte_size": 0},
            )

        mime = _suffix_mime(resolved)
        if mime is None:
            return _result(
                status="unavailable",
                reason_code="unsupported_extension",
                langs=effective_langs,
                source={"filename": resolved.name[:255], "byte_size": resolved.stat().st_size},
            )

        size = resolved.stat().st_size
        source = {"filename": resolved.name[:255], "byte_size": size, "mime_type": mime}
        if size <= 0:
            return _result(
                status="unavailable",
                reason_code="empty_file",
                langs=effective_langs,
                source=source,
            )
        if size > MAX_OCR_IMAGE_BYTES:
            return _result(
                status="unavailable",
                reason_code="file_too_large",
                langs=effective_langs,
                source=source,
            )

        try:
            image_bytes = resolved.read_bytes()
        except OSError as exc:
            log_safe_exception(
                logger,
                "OCR image read failed",
                exc,
                error_code="ocr_image_read_failed",
                level=logging.WARNING,
            )
            return _result(
                status="unavailable",
                reason_code="read_failed",
                langs=effective_langs,
                source=source,
            )

        try:
            _verify_magic_bytes(image_bytes, mime)
        except ValueError as exc:
            return _result(
                status="unavailable",
                reason_code=str(exc),
                langs=effective_langs,
                source=source,
            )

        engine_fn = self._engine
        engine_name = "injected"
        if engine_fn is None:
            readiness = assess_ocr_dependencies(import_probe=self._dependency_probe)
            if not readiness["ready"]:
                return _result(
                    status="unavailable",
                    reason_code=str(readiness["reason"]),
                    langs=effective_langs,
                    source=source,
                    engine="none",
                )
            engine_fn = _default_tesseract_engine
            engine_name = "tesseract"

        started = time.monotonic()
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(engine_fn, image_bytes, mime, effective_langs)
                raw_text = future.result(timeout=self._timeout_seconds)
        except FuturesTimeoutError:
            return _result(
                status="unavailable",
                reason_code="ocr_timeout",
                langs=effective_langs,
                source=source,
                engine=engine_name,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:  # broad-exception: fallback_recorded - engine errors become structured status
            log_safe_exception(
                logger,
                "OCR engine failed",
                exc,
                error_code="ocr_engine_failed",
                level=logging.WARNING,
            )
            return _result(
                status="unavailable",
                reason_code="ocr_engine_failed",
                langs=effective_langs,
                source=source,
                engine=engine_name,
                duration_ms=int((time.monotonic() - started) * 1000),
            )

        duration_ms = int((time.monotonic() - started) * 1000)
        text = (raw_text or "").strip()
        if not text:
            return _result(
                status="degraded",
                reason_code="empty_ocr_text",
                text="",
                lines=[],
                langs=effective_langs,
                source=source,
                engine=engine_name,
                duration_ms=duration_ms,
            )

        lines = _split_lines(text)
        return _result(
            status="available",
            text=text[:MAX_OCR_TEXT_CHARS],
            lines=lines,
            langs=effective_langs,
            source=source,
            engine=engine_name,
            duration_ms=duration_ms,
        )
