from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import requests

from src.model_pack import (
    ModelPackError,
    OllamaHttpModelPackExecutor,
    inspect_model_pack,
    normalize_ollama_native_base_url,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _write_pack(root: Path) -> Path:
    root.mkdir()
    gguf = root / "finance.gguf"
    modelfile = root / "Modelfile"
    license_file = root / "LICENSE"
    gguf.write_bytes(b"GGUF-finance-test")
    modelfile.write_text(
        (
            "FROM ./finance.gguf\n"
            "PARAMETER temperature 0.1\n"
            "PARAMETER num_ctx 8192\n"
            "PARAMETER use_mmap true\n"
            'PARAMETER stop "END"\n'
            'PARAMETER stop "DONE"\n'
            r'PARAMETER stop "\n"' + "\n"
            'SYSTEM """You are a finance model.\nUse cited evidence."""\n'
        ),
        encoding="utf-8",
    )
    license_file.write_text("LicenseRef-Finance terms\n", encoding="utf-8")
    manifest = {
        "format_version": 1,
        "model_id": "stockpulse/finance-test:q4",
        "display_name": "Finance Test",
        "gguf_file": gguf.name,
        "modelfile": modelfile.name,
        "license": {"id": "LicenseRef-Finance", "file": license_file.name},
        "minimum_memory_gb": 16,
        "files": [
            {
                "path": gguf.name,
                "role": "gguf",
                "sha256": _sha256(gguf),
                "size_bytes": gguf.stat().st_size,
            },
            {
                "path": modelfile.name,
                "role": "modelfile",
                "sha256": _sha256(modelfile),
                "size_bytes": modelfile.stat().st_size,
            },
            {
                "path": license_file.name,
                "role": "license",
                "sha256": _sha256(license_file),
                "size_bytes": license_file.stat().st_size,
            },
        ],
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest) + "\n",
        encoding="utf-8",
    )
    return root


class _Response:
    def __init__(self, status_code: int, body=None) -> None:
        self.status_code = status_code
        self._body = {} if body is None else body

    def json(self):
        return self._body


def test_normalize_ollama_native_base_url_accepts_only_root_or_v1() -> None:
    assert (
        normalize_ollama_native_base_url("http://127.0.0.1:11434/v1/")
        == "http://127.0.0.1:11434"
    )
    assert (
        normalize_ollama_native_base_url("https://ollama.example:443")
        == "https://ollama.example:443"
    )

    for invalid in (
        "file:///tmp/ollama",
        "http://user:secret@localhost:11434",
        "http://localhost:11434/private",
        "http://localhost:11434?target=other",
    ):
        with pytest.raises(ModelPackError) as error:
            normalize_ollama_native_base_url(invalid)
        assert error.value.code == "invalid_ollama_configuration"


def test_http_executor_uploads_verified_blob_then_creates_from_controlled_fields(
    tmp_path: Path,
) -> None:
    pack_path = _write_pack(tmp_path / "pack")
    requests_seen = []

    def requester(method: str, url: str, **kwargs):
        requests_seen.append((method, url, kwargs))
        if method == "HEAD":
            return _Response(404)
        if url.endswith("/api/create"):
            return _Response(200, {"status": "success"})
        assert kwargs["data"].read() == b"GGUF-finance-test"
        return _Response(201)

    progress = []
    executor = OllamaHttpModelPackExecutor(
        base_url_provider=lambda: "http://127.0.0.1:11434/v1",
        requester=requester,
    )
    with inspect_model_pack(pack_path) as inspected:
        executor.create(
            inspected,
            on_progress=lambda percent, message: progress.append((percent, message)),
        )

    digest = hashlib.sha256(b"GGUF-finance-test").hexdigest()
    assert [(method, url) for method, url, _kwargs in requests_seen] == [
        ("HEAD", f"http://127.0.0.1:11434/api/blobs/sha256:{digest}"),
        ("POST", f"http://127.0.0.1:11434/api/blobs/sha256:{digest}"),
        ("POST", "http://127.0.0.1:11434/api/create"),
    ]
    create_payload = requests_seen[-1][2]["json"]
    assert create_payload == {
        "model": "stockpulse/finance-test:q4",
        "files": {"finance.gguf": f"sha256:{digest}"},
        "stream": False,
        "parameters": {
            "temperature": 0.1,
            "num_ctx": 8192,
            "use_mmap": True,
            "stop": ["END", "DONE", r"\n"],
        },
        "system": "You are a finance model.\nUse cited evidence.",
    }
    assert progress == [
        (45, "Uploading the verified GGUF data to Ollama"),
        (75, "Creating the Ollama model"),
        (90, "Activating the imported model"),
    ]


def test_http_executor_cancellation_before_blob_work_issues_no_request(
    tmp_path: Path,
) -> None:
    pack_path = _write_pack(tmp_path / "cancel-before-blob")
    requests_seen = []
    executor = OllamaHttpModelPackExecutor(
        base_url_provider=lambda: "http://127.0.0.1:11434",
        requester=lambda *args, **kwargs: requests_seen.append((args, kwargs)),
    )

    with inspect_model_pack(pack_path) as inspected:
        created = executor.create(
            inspected,
            is_cancel_requested=lambda: True,
        )

    assert created is False
    assert requests_seen == []


def test_http_executor_cancellation_after_blob_upload_skips_create(
    tmp_path: Path,
) -> None:
    pack_path = _write_pack(tmp_path / "cancel-after-blob")
    requests_seen = []
    cancelled = False

    def requester(method: str, url: str, **kwargs):
        nonlocal cancelled
        requests_seen.append((method, url))
        if method == "HEAD":
            return _Response(404)
        assert url.endswith("/api/blobs/sha256:" + _sha256(pack_path / "finance.gguf"))
        assert kwargs["data"].read() == b"GGUF-finance-test"
        cancelled = True
        return _Response(201)

    executor = OllamaHttpModelPackExecutor(
        base_url_provider=lambda: "http://127.0.0.1:11434",
        requester=requester,
    )
    with inspect_model_pack(pack_path) as inspected:
        created = executor.create(
            inspected,
            is_cancel_requested=lambda: cancelled,
        )

    assert created is False
    assert [method for method, _url in requests_seen] == ["HEAD", "POST"]
    assert all(not url.endswith("/api/create") for _method, url in requests_seen)


def test_web_pack_inspection_uses_the_portable_manifest_text_contract(
    tmp_path: Path,
) -> None:
    pack_path = _write_pack(tmp_path / "portable-web-pack")
    manifest_path = pack_path / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["display_name"] = "😀" * 81
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with inspect_model_pack(pack_path) as inspected:
        assert inspected.manifest.display_name == "😀" * 81

    manifest["model_id"] = "K:q4"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ModelPackError) as error:
        with inspect_model_pack(pack_path):
            pass
    assert error.value.code == "invalid_manifest"
    assert "model_id" in error.value.user_message


def test_http_executor_translates_unreachable_ollama_without_exposing_traceback(
    tmp_path: Path,
) -> None:
    pack_path = _write_pack(tmp_path / "pack")

    def unavailable(_method: str, _url: str, **_kwargs):
        raise requests.ConnectionError("connection refused at a private path")

    executor = OllamaHttpModelPackExecutor(
        base_url_provider=lambda: "http://127.0.0.1:11434",
        requester=unavailable,
    )
    with inspect_model_pack(pack_path) as inspected:
        with pytest.raises(ModelPackError) as error:
            executor.create(inspected)

    assert error.value.code == "ollama_unavailable"
    assert "Start Ollama" in error.value.user_message
    assert "private path" not in error.value.user_message


def test_http_executor_requires_private_target_allowlisting(tmp_path: Path) -> None:
    pack_path = _write_pack(tmp_path / "pack")
    executor = OllamaHttpModelPackExecutor(
        base_url_provider=lambda: "http://127.0.0.1:11434",
        allowlist_provider=lambda: (),
    )

    with inspect_model_pack(pack_path) as inspected:
        with pytest.raises(ModelPackError) as error:
            executor.create(inspected)

    assert error.value.code == "ollama_access_blocked"
    assert "OUTBOUND_HTTP_ALLOWLIST" in error.value.user_message
