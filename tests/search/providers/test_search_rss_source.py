# -*- coding: utf-8 -*-
"""Deterministic tests for the RSS/Atom search-pipeline provider."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Mock newspaper before search_service import (optional dependency)
if "newspaper" not in sys.modules:
    mock_np = MagicMock()
    mock_np.Article = MagicMock()
    mock_np.Config = MagicMock()
    sys.modules["newspaper"] = mock_np

from src.search_service import RssAtomSearchProvider, SearchService
from src.security.outbound_policy import OutboundPolicyError

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "rss"


def _load_fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


class TestRssAtomSearchProvider(unittest.TestCase):
    def setUp(self) -> None:
        self.feed_a = "https://feeds.example.com/market.rss"
        self.feed_b = "https://feeds.example.com/dup.rss"
        self.feed_atom = "https://feeds.example.com/market.atom"
        self.feed_empty = "https://feeds.example.com/empty.rss"
        self.feed_bad = "https://feeds.example.com/bad.rss"
        self.loopback_feed = "http://127.0.0.1:9/feed.rss"

    def _response(self, body: bytes, *, status_code: int = 200, url: str = "") -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.content = body
        resp.url = url or self.feed_a
        resp.headers = {"content-type": "application/rss+xml"}
        resp.raise_for_status = MagicMock()
        resp.iter_content = MagicMock(return_value=[body] if body else [])
        resp.close = MagicMock()
        return resp

    def test_empty_config_is_inert(self) -> None:
        provider = RssAtomSearchProvider([])
        self.assertFalse(provider.is_available)
        service = SearchService(
            searxng_public_instances_enabled=False,
            rss_news_feed_urls=[],
        )
        names = [p.name for p in service._providers]
        self.assertNotIn("RSS/Atom", names)

    def test_well_formed_rss_maps_fields_and_filters_query(self) -> None:
        body = _load_fixture("well_formed_rss.xml")
        provider = RssAtomSearchProvider([self.feed_a])
        with patch("src.search_service.safe_get", return_value=self._response(body)) as mock_get:
            resp = provider.search("AAPL stock latest news", max_results=10, days=30)

        mock_get.assert_called()
        self.assertTrue(resp.success)
        self.assertEqual(resp.provider, "RSS/Atom")
        self.assertGreaterEqual(len(resp.results), 2)
        titles = [r.title for r in resp.results]
        self.assertTrue(any("AAPL" in t for t in titles))
        self.assertFalse(any("Oil futures" in t for t in titles))
        first = next(r for r in resp.results if "AAPL" in r.title)
        self.assertEqual(first.url, "https://news.example.com/aapl-earnings")
        self.assertIn("RSS", first.source)
        self.assertEqual(first.published_date, "2026-08-05")

    def test_well_formed_atom_parse(self) -> None:
        body = _load_fixture("well_formed_atom.xml")
        provider = RssAtomSearchProvider([self.feed_atom])
        with patch(
            "src.search_service.safe_get",
            return_value=self._response(body, url=self.feed_atom),
        ):
            resp = provider.search("AAPL", max_results=5, days=30)

        self.assertTrue(resp.success)
        self.assertEqual(len(resp.results), 1)
        self.assertIn("AAPL filing", resp.results[0].title)
        self.assertEqual(resp.results[0].url, "https://news.example.com/aapl-filing")

    def test_empty_feed_success_with_no_results(self) -> None:
        body = _load_fixture("empty_feed.xml")
        provider = RssAtomSearchProvider([self.feed_empty])
        with patch(
            "src.search_service.safe_get",
            return_value=self._response(body, url=self.feed_empty),
        ):
            resp = provider.search("AAPL", max_results=5, days=30)

        self.assertTrue(resp.success)
        self.assertEqual(resp.results, [])

    def test_malformed_feed_degrades_without_raising(self) -> None:
        body = _load_fixture("malformed.xml")
        provider = RssAtomSearchProvider([self.feed_bad])
        with patch(
            "src.search_service.safe_get",
            return_value=self._response(body, url=self.feed_bad),
        ):
            resp = provider.search("AAPL", max_results=5, days=30)

        self.assertFalse(resp.success)
        self.assertEqual(resp.results, [])

    def test_malformed_sibling_does_not_block_good_feed(self) -> None:
        good = _load_fixture("well_formed_rss.xml")
        bad = _load_fixture("malformed.xml")

        def _side_effect(url, **_kwargs):
            if "bad" in url:
                return self._response(bad, url=url)
            return self._response(good, url=url)

        provider = RssAtomSearchProvider([self.feed_bad, self.feed_a])
        with patch("src.search_service.safe_get", side_effect=_side_effect):
            resp = provider.search("AAPL", max_results=10, days=30)

        self.assertTrue(resp.success)
        self.assertGreaterEqual(len(resp.results), 1)

    def test_duplicate_urls_across_feeds_deduped(self) -> None:
        body_a = _load_fixture("well_formed_rss.xml")
        body_b = _load_fixture("duplicate_items.xml")

        def _side_effect(url, **_kwargs):
            if "dup" in url:
                return self._response(body_b, url=url)
            return self._response(body_a, url=url)

        provider = RssAtomSearchProvider([self.feed_a, self.feed_b])
        with patch("src.search_service.safe_get", side_effect=_side_effect):
            resp = provider.search("AAPL", max_results=20, days=30)

        urls = [r.url for r in resp.results]
        self.assertEqual(len(urls), len(set(urls)))
        self.assertIn("https://news.example.com/aapl-earnings", urls)
        self.assertIn("https://news.example.com/aapl-unique-b", urls)

    def test_outbound_policy_blocks_loopback_feed(self) -> None:
        provider = RssAtomSearchProvider([self.loopback_feed])

        def _deny(*_args, **_kwargs):
            raise OutboundPolicyError("loopback_blocked", "testcid")

        with patch("src.search_service.safe_get", side_effect=_deny):
            resp = provider.search("AAPL", max_results=5, days=30)

        self.assertFalse(resp.success)
        self.assertEqual(resp.results, [])

    def test_fetch_uses_safe_get_not_raw_requests(self) -> None:
        body = _load_fixture("well_formed_rss.xml")
        provider = RssAtomSearchProvider([self.feed_a])
        with patch("src.search_service.safe_get", return_value=self._response(body)) as mock_safe:
            with patch("src.search_service.requests.get") as mock_raw:
                provider.search("AAPL", max_results=5, days=30)
                mock_safe.assert_called()
                mock_raw.assert_not_called()

    def test_search_service_registers_rss_provider(self) -> None:
        service = SearchService(
            searxng_public_instances_enabled=False,
            rss_news_feed_urls=[self.feed_a],
        )
        names = [p.name for p in service._providers]
        self.assertIn("RSS/Atom", names)
        rss = next(p for p in service._providers if p.name == "RSS/Atom")
        self.assertTrue(rss.is_available)

    def test_invalid_scheme_urls_ignored_at_init(self) -> None:
        provider = RssAtomSearchProvider(
            ["ftp://bad.example/feed", "not-a-url", "https://feeds.example.com/ok.rss"]
        )
        self.assertEqual(provider._feed_urls, ["https://feeds.example.com/ok.rss"])

    def test_parse_feed_bytes_empty_content(self) -> None:
        provider = RssAtomSearchProvider([self.feed_a])
        self.assertEqual(provider._parse_feed_bytes(bytes(), feed_url=self.feed_a), [])
        self.assertEqual(provider._parse_feed_bytes(b"   ", feed_url=self.feed_a), [])


class TestRssConfigLoading(unittest.TestCase):
    def test_config_parses_rss_feed_urls(self) -> None:
        from src.config import Config

        keys = (
            "RSS_NEWS_FEED_URLS",
            "RSS_NEWS_FETCH_TIMEOUT_SEC",
            "SEARXNG_PUBLIC_INSTANCES_ENABLED",
        )
        old = {k: os.environ.get(k) for k in keys}
        try:
            os.environ["RSS_NEWS_FEED_URLS"] = (
                "https://feeds.example.com/a.rss, https://feeds.example.com/b.atom"
            )
            os.environ["RSS_NEWS_FETCH_TIMEOUT_SEC"] = "6"
            os.environ["SEARXNG_PUBLIC_INSTANCES_ENABLED"] = "false"
            cfg = Config._load_from_env()
            self.assertEqual(
                cfg.rss_news_feed_urls,
                [
                    "https://feeds.example.com/a.rss",
                    "https://feeds.example.com/b.atom",
                ],
            )
            self.assertEqual(cfg.rss_news_fetch_timeout_sec, 6.0)
            self.assertTrue(cfg.has_rss_news_feeds_enabled())
            self.assertTrue(cfg.has_search_capability_enabled())
        finally:
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value


if __name__ == "__main__":
    unittest.main()
