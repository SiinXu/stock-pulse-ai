# Offline Image OCR Agent Tool

StockPulse can extract raw text and numbers from local images using **offline OCR**
(Tesseract). This is distinct from multimodal Vision tools that send image bytes
to a cloud model.

Issue: #196. Related offline/privacy posture: #218 (partial coverage only).

## Decision: why OCR next to multimodal Vision

| Path | Network | Best for |
| --- | --- | --- |
| **OCR** `extract_image_text` | None (local) | Dense digits, statements, privacy-sensitive screenshots |
| Chart reading `read_price_chart` | Vision API | Semantic K-line structure/trend/levels |
| Image stock extract | Vision API | Stock codes/names from screenshots |
| PDF parse | None | Text-layer PDFs (not raster OCR) |

OCR is **not** a parallel reimplementation of chart reading.

## Registration contract

Registers only when all gates pass:

1. `OCR_AGENT_TOOL_ENABLED=true`
2. `OCR_FILE_ROOT` or fallback `MULTIMODAL_FILE_ROOT`
3. Packages from `requirements-ocr.txt` import
4. System `tesseract` binary available

Otherwise the tool is absent; default product paths are unchanged.

Registration uses built-in plugin `builtin.ocr` + `agent_tool` extension
(same pattern as Kronos). Only `ToolRegistry.register` is called; registry
contracts are not modified.

Capability: `multimodal:read`. Side effects: `fs_read`, `local_model_inference`.

## Configuration

```bash
OCR_AGENT_TOOL_ENABLED=false
# OCR_FILE_ROOT=/absolute/path/to/ocr-uploads
# OCR_LANGS=chi_sim+eng
# OCR_TIMEOUT_SECONDS=30
```

Restart required after enabling.

## Install

```bash
python -m pip install --constraint constraints.txt --build-constraint build-constraints.txt -r requirements-ocr.txt
# macOS: brew install tesseract tesseract-lang
# Debian: apt install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
```

## Safety

Path sandbox, extension whitelist, magic-byte MIME check, 5 MiB size cap,
timeout 1–120s. Image bytes never leave the host for OCR.

## Rollback

Set `OCR_AGENT_TOOL_ENABLED=false` and restart, or revert the PR.
