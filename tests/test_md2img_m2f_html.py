# -*- coding: utf-8 -*-
"""Regression notes and light checks for m2f share-image HTML pass-through."""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch


class TestM2fHtmlCapability(unittest.TestCase):
    def test_m2f_path_writes_share_image_html_document(self):
        """Share-image path hands a full HTML document to m2f (raw HTML engine)."""
        from src.md2img import _markdown_to_image_m2f

        written = {}

        def fake_which(name):
            return "/usr/bin/m2f" if name == "m2f" else None

        class _Result:
            returncode = 0
            stderr = b""

        def fake_run(cmd, capture_output=True, timeout=60, check=False):
            # m2f would write report.png beside report.md; simulate success file.
            md_path = cmd[1]
            out_dir = md_path.rsplit("/", 1)[0]
            with open(md_path, encoding="utf-8") as handle:
                written["content"] = handle.read()
            with open(f"{out_dir}/report.png", "wb") as handle:
                handle.write(b"\x89PNG\r\n\x1a\nfake")
            return _Result()

        with patch("src.md2img.shutil.which", side_effect=fake_which), patch(
            "src.md2img.subprocess.run", side_effect=fake_run
        ), patch(
            "src.md2img.build_share_image_html",
            return_value="<!DOCTYPE html><html><body><h1>poster</h1></body></html>",
        ):
            png = _markdown_to_image_m2f("# hello", structured_payload=None, branding=None)

        self.assertEqual(png, b"\x89PNG\r\n\x1a\nfake")
        self.assertIn("<!DOCTYPE html>", written["content"])
        self.assertIn("<h1>poster</h1>", written["content"])

    def test_m2f_html_true_documented_in_source_comment(self):
        """Pin the verified markdown-to-file@1.5.4 html:true evidence in code comments."""
        import inspect

        from src import md2img

        source = inspect.getsource(md2img._markdown_to_image_m2f)
        self.assertIn("html: true", source)
        self.assertIn("markdown-to-file@1.5.4", source)
        self.assertIn("{{{content}}}", source)


if __name__ == "__main__":
    unittest.main()
