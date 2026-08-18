# -*- coding: utf-8 -*-
"""PWA service worker hosting headers (Refs #234)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from src.api.app import create_app


class PwaServiceWorkerHeadersTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._temp_dir = tempfile.TemporaryDirectory()
        static_dir = Path(cls._temp_dir.name)
        (static_dir / "assets").mkdir()
        (static_dir / "index.html").write_text(
            "<!doctype html><html><head><title>t</title></head>"
            "<body><div id=\"root\"></div></body></html>",
            encoding="utf-8",
        )
        (static_dir / "sw.js").write_text(
            "/* test service worker */\nself.addEventListener('fetch', () => {});\n",
            encoding="utf-8",
        )
        (static_dir / "manifest.webmanifest").write_text(
            '{"name":"StockPulse","start_url":"/","display":"standalone"}',
            encoding="utf-8",
        )
        cls.client = TestClient(create_app(static_dir=static_dir))

    @classmethod
    def tearDownClass(cls):
        cls._temp_dir.cleanup()

    def test_sw_js_has_no_cache_headers(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        cache_control = response.headers.get("Cache-Control", "")
        self.assertIn("no-cache", cache_control)
        self.assertIn("no-store", cache_control)

    def test_webmanifest_media_type(self):
        response = self.client.get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        content_type = response.headers.get("content-type", "")
        self.assertIn("application/manifest+json", content_type)


if __name__ == "__main__":
    unittest.main()
