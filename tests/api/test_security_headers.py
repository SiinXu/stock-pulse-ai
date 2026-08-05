# -*- coding: utf-8 -*-
"""Tests for API security-headers middleware (CSP + nosniff + frame + referrer)."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api.app import create_app
from api.middlewares.security_headers import (
    CONTENT_SECURITY_POLICY,
    SECURITY_HEADERS,
    is_openapi_ui_path,
)


def _make_client_with_frontend() -> tuple[tempfile.TemporaryDirectory, TestClient]:
    temp_dir = tempfile.TemporaryDirectory()
    static_dir = Path(temp_dir.name)
    (static_dir / "assets").mkdir()
    (static_dir / "index.html").write_text(
        "<!doctype html><html><head><title>t</title></head>"
        "<body><div id=\"root\"></div></body></html>",
        encoding="utf-8",
    )
    (static_dir / "assets" / "app.js").write_text("console.log('ok');", encoding="utf-8")
    client = TestClient(create_app(static_dir=static_dir))
    return temp_dir, client


def _make_client_without_frontend() -> tuple[tempfile.TemporaryDirectory, TestClient]:
    temp_dir = tempfile.TemporaryDirectory()
    client = TestClient(create_app(static_dir=Path(temp_dir.name)))
    return temp_dir, client


class SecurityHeadersPolicyUnitTestCase(unittest.TestCase):
    """Pure policy helpers stay stable for operators and reverse proxies."""

    def test_openapi_ui_paths_detected(self):
        self.assertTrue(is_openapi_ui_path("/docs"))
        self.assertTrue(is_openapi_ui_path("/docs/"))
        self.assertTrue(is_openapi_ui_path("/docs/oauth2-redirect"))
        self.assertTrue(is_openapi_ui_path("/redoc"))
        self.assertTrue(is_openapi_ui_path("/redoc/"))
        self.assertFalse(is_openapi_ui_path("/api/v1/health"))
        self.assertFalse(is_openapi_ui_path("/"))
        self.assertFalse(is_openapi_ui_path("/openapi.json"))

    def test_csp_contains_required_directives(self):
        policy = CONTENT_SECURITY_POLICY
        for fragment in (
            "default-src 'self'",
            "object-src 'none'",
            "base-uri 'none'",
            "frame-ancestors 'none'",
            "script-src 'self' 'unsafe-inline'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "connect-src 'self'",
            "form-action 'self'",
        ):
            self.assertIn(fragment, policy)

        # Keep the production policy free of eval and remote script hosts.
        self.assertNotIn("unsafe-eval", policy)
        self.assertNotIn("cdn.jsdelivr.net", policy)
        self.assertNotIn("*", policy.split("default-src", 1)[1].split(";", 1)[0])


class SecurityHeadersOnRoutesTestCase(unittest.TestCase):
    """Representative routes must carry the defense-in-depth headers."""

    @classmethod
    def setUpClass(cls):
        cls._temp_dir, cls.client = _make_client_with_frontend()

    @classmethod
    def tearDownClass(cls):
        cls._temp_dir.cleanup()

    def _assert_core_headers(self, response, *, expect_csp: bool = True):
        self.assertEqual(response.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(
            response.headers.get("Referrer-Policy"),
            "strict-origin-when-cross-origin",
        )
        self.assertEqual(response.headers.get("X-Frame-Options"), "DENY")
        if expect_csp:
            self.assertEqual(
                response.headers.get("Content-Security-Policy"),
                CONTENT_SECURITY_POLICY,
            )
        else:
            self.assertIsNone(response.headers.get("Content-Security-Policy"))

    def test_health_json_routes_have_security_headers(self):
        for path in ("/health", "/api/health", "/api/v1/health"):
            with self.subTest(path=path):
                resp = self.client.get(path)
                self.assertEqual(resp.status_code, 200)
                self._assert_core_headers(resp, expect_csp=True)

    def test_spa_index_has_security_headers(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self._assert_core_headers(resp, expect_csp=True)

    def test_static_asset_has_security_headers(self):
        resp = self.client.get("/assets/app.js")
        self.assertEqual(resp.status_code, 200)
        self._assert_core_headers(resp, expect_csp=True)

    def test_spa_fallback_has_security_headers(self):
        resp = self.client.get("/history")
        self.assertEqual(resp.status_code, 200)
        self._assert_core_headers(resp, expect_csp=True)

    def test_missing_api_route_still_has_security_headers(self):
        # Status may be 404 (route missing) or 401 when admin auth is enabled in
        # the process environment; headers must still be present either way.
        resp = self.client.get("/api/v1/this-route-does-not-exist-for-headers")
        self.assertIn(resp.status_code, (401, 404))
        self._assert_core_headers(resp, expect_csp=True)

    def test_openapi_json_keeps_csp(self):
        # Machine-readable schema does not load CDN scripts; CSP stays on.
        resp = self.client.get("/openapi.json")
        self.assertEqual(resp.status_code, 200)
        self._assert_core_headers(resp, expect_csp=True)

    def test_docs_ui_omits_csp_but_keeps_other_headers(self):
        resp = self.client.get("/docs")
        self.assertEqual(resp.status_code, 200)
        self._assert_core_headers(resp, expect_csp=False)

    def test_redoc_ui_omits_csp_but_keeps_other_headers(self):
        resp = self.client.get("/redoc")
        self.assertEqual(resp.status_code, 200)
        self._assert_core_headers(resp, expect_csp=False)

    def test_security_header_constants_match_middleware_output(self):
        resp = self.client.get("/api/health")
        for name, value in SECURITY_HEADERS.items():
            self.assertEqual(resp.headers.get(name), value)


class SecurityHeadersWithoutFrontendTestCase(unittest.TestCase):
    """Not-built HTML guide page must still receive security headers."""

    @classmethod
    def setUpClass(cls):
        cls._temp_dir, cls.client = _make_client_without_frontend()

    @classmethod
    def tearDownClass(cls):
        cls._temp_dir.cleanup()

    def test_root_not_built_page_has_csp(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("content-type", ""))
        self.assertEqual(
            resp.headers.get("Content-Security-Policy"),
            CONTENT_SECURITY_POLICY,
        )
        self.assertEqual(resp.headers.get("X-Content-Type-Options"), "nosniff")
        self.assertEqual(resp.headers.get("X-Frame-Options"), "DENY")


if __name__ == "__main__":
    unittest.main()
