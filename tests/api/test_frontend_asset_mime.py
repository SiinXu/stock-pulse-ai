# -*- coding: utf-8 -*-
"""Frontend static MIME registrations used by SPA / PWA hosting."""

from __future__ import annotations

import unittest

from src.api.app import _frontend_asset_media_type


class FrontendAssetMimeTestCase(unittest.TestCase):
    def test_webmanifest_media_type(self):
        self.assertEqual(
            _frontend_asset_media_type("manifest.webmanifest"),
            "application/manifest+json",
        )

    def test_js_and_css_media_types(self):
        self.assertEqual(_frontend_asset_media_type("assets/app.js"), "text/javascript")
        self.assertEqual(_frontend_asset_media_type("assets/app.css"), "text/css")


if __name__ == "__main__":
    unittest.main()
