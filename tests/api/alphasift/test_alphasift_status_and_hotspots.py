# -*- coding: utf-8 -*-
"""AlphaSift status and hotspot API contracts."""

from __future__ import annotations

from tests.alphasift_api_test_support import (
    os,
    json,
    tempfile,
    time,
    datetime,
    Path,
    SimpleNamespace,
    Any,
    Dict,
    List,
    MagicMock,
    patch,
    FastAPI,
    HTTPException,
    TestClient,
    alphasift_endpoint,
    Config,
    alphasift_service,
    DEFAULT_ALPHASIFT_TEST_SPEC,
    PUBLIC_DIAGNOSTIC_SECRET,
    _raise_alphasift_unavailable,
    _make_adapter_module,
    _AlphaSiftApiTestCaseBase,
)


class AlphaSiftOpportunitiesApiTestCase(_AlphaSiftApiTestCaseBase):
    def test_hotspot_cache_failure_logs_topic_metadata_without_private_text(self) -> None:
        private_topic = (
            "Board discussion about Northwind acquiring Contoso before announcement"
        )
        cache_path = MagicMock()
        cache_path.write_text.side_effect = RuntimeError("cache write unavailable")

        with (
            patch(
                "src.services.alphasift_service._alphasift_hotspot_detail_cache_path",
                return_value=cache_path,
            ),
            self.assertLogs("src.services.alphasift_service", level="WARNING") as captured,
        ):
            alphasift_service._write_alphasift_hotspot_detail_cache(
                provider="akshare",
                topic=private_topic,
                payload={"topic": private_topic, "stocks": []},
            )

        rendered = "\n".join(captured.output)
        self.assertNotIn(private_topic, rendered)
        self.assertIn(f"topic_length={len(private_topic)}", rendered)
        self.assertIn("provider=akshare", rendered)

    def test_default_install_spec_is_commit_pinned(self) -> None:
        self.assertRegex(
            DEFAULT_ALPHASIFT_TEST_SPEC,
            r"^git\+https://github\.com/ZhuLinsen/alphasift\.git@[0-9a-f]{40}$",
        )

    def test_status_defaults_to_disabled(self) -> None:
        config = self._config(enabled=False)

        with patch("src.services.alphasift_service._call_alphasift_status", side_effect=_raise_alphasift_unavailable):
            payload = alphasift_endpoint.alphasift_status(config=config)

        self.assertEqual(payload["enabled"], False)
        self.assertEqual(payload["available"], False)
        self.assertEqual(payload["install_spec_is_default"], True)
        self.assertNotIn("diagnostics", payload)
        self.assertNotIn("install_spec", payload)

    def test_status_marks_custom_install_source(self) -> None:
        config = self._config(enabled=False, install_spec="git+https://example.com/private/alphasift.git")

        with patch("src.services.alphasift_service._call_alphasift_status", side_effect=_raise_alphasift_unavailable):
            payload = alphasift_endpoint.alphasift_status(config=config)

        self.assertEqual(payload["install_spec_is_default"], False)
        self.assertNotIn("install_spec", payload)

    def test_status_includes_adapter_contract_metadata(self) -> None:
        config = self._config(enabled=True)

        with patch(
            "src.services.alphasift_service._call_alphasift_status",
            return_value={"available": True, "contract_version": "1", "version": "0.2.0", "strategy_count": 8},
        ):
            payload = alphasift_endpoint.alphasift_status(config=config)

        self.assertTrue(payload["available"])
        self.assertEqual(payload["contract_version"], "1")
        self.assertEqual(payload["version"], "0.2.0")
        self.assertEqual(payload["strategy_count"], 8)

    def test_status_includes_alphasift_source_health_snapshot(self) -> None:
        config = self._config(enabled=True)

        with (
            patch(
                "src.services.alphasift_service._call_alphasift_status",
                return_value={"available": True, "contract_version": "1", "version": "0.2.0", "strategy_count": 8},
            ),
            patch(
                "src.services.alphasift_service._get_alphasift_source_health_snapshot",
                return_value={"snapshot": {"sina": {"failures": 2, "disabled": False}}},
            ),
        ):
            payload = alphasift_endpoint.alphasift_status(config=config)

        self.assertEqual(payload["source_health"]["snapshot"]["sina"]["failures"], 2)

    def test_status_hides_raw_source_health_diagnostics(self) -> None:
        config = self._config(enabled=True)

        with (
            patch(
                "src.services.alphasift_service._call_alphasift_status",
                return_value={"available": True, "contract_version": "1", "version": "0.2.0"},
            ),
            patch(
                "src.services.alphasift_service._get_alphasift_source_health_snapshot",
                return_value={
                    "snapshot": {
                        "source_errors": [PUBLIC_DIAGNOSTIC_SECRET],
                        "warnings": [PUBLIC_DIAGNOSTIC_SECRET],
                        "exception": PUBLIC_DIAGNOSTIC_SECRET,
                    },
                },
            ),
        ):
            payload = alphasift_endpoint.alphasift_status(config=config)

        self.assertEqual(payload["source_health"]["snapshot"]["source_errors"], ["alphasift_source_error"])
        self.assertEqual(payload["source_health"]["snapshot"]["warnings"], ["alphasift_warning"])
        self.assertEqual(payload["source_health"]["snapshot"]["exception"], "alphasift_internal_error")
        self.assert_public_payload_is_private(payload)

    def test_status_preserves_adapter_available_false_without_diagnostics(self) -> None:
        config = self._config(enabled=False)

        with patch(
            "src.services.alphasift_service._call_alphasift_status",
            return_value={"available": False, "contract_version": "1", "version": "0.2.0", "strategy_count": 0},
        ):
            payload = alphasift_endpoint.alphasift_status(config=config)

        self.assertFalse(payload["available"])
        self.assertEqual(payload["contract_version"], "1")
        self.assertNotIn("diagnostics", payload)

    def test_status_logs_and_reports_adapter_runtime_exception_diagnostics(self) -> None:
        config = self._config(enabled=False)
        fake_module = _make_adapter_module(get_status=MagicMock(side_effect=RuntimeError("get_status failed")))

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            self.assertLogs("src.services.alphasift_service", level="WARNING") as captured,
        ):
            payload = alphasift_endpoint.alphasift_status(config=config)

        self.assertFalse(payload["available"])
        self.assertEqual(payload["diagnostics"]["reason"], "unexpected_exception")
        self.assertEqual(payload["diagnostics"]["stage"], "get_status")
        self.assertEqual(payload["diagnostics"]["error_type"], "RuntimeError")
        self.assertIn("Unexpected AlphaSift get_status failure", "\n".join(captured.output))

    def test_status_logs_and_reports_unexpected_import_exception_diagnostics(self) -> None:
        config = self._config(enabled=False)
        missing_sub_dependency = ModuleNotFoundError("No module named 'optional_dep'", name="optional_dep")

        with (
            patch("src.services.alphasift_service._prepare_alphasift_runtime_env"),
            patch("src.services.alphasift_service.importlib.import_module", side_effect=missing_sub_dependency),
            self.assertLogs("src.services.alphasift_service", level="WARNING") as captured,
        ):
            payload = alphasift_endpoint.alphasift_status(config=config)

        self.assertFalse(payload["available"])
        self.assertEqual(payload["diagnostics"]["reason"], "unexpected_exception")
        self.assertEqual(payload["diagnostics"]["stage"], "import_adapter")
        self.assertEqual(payload["diagnostics"]["error_type"], "ModuleNotFoundError")
        self.assertIn("Unexpected AlphaSift import_adapter failure", "\n".join(captured.output))

    def test_status_marks_missing_module_for_dependency_diagnostic(self) -> None:
        config = self._config(enabled=True)
        missing_module_exc = ModuleNotFoundError("No module named 'alphasift.dsa_adapter'", name="alphasift.dsa_adapter")

        with (
            patch("src.services.alphasift_service._import_alphasift", side_effect=missing_module_exc),
            self.assertLogs("src.services.alphasift_service", level="WARNING"),
        ):
            payload = alphasift_endpoint.alphasift_status(config=config)

        self.assertFalse(payload["available"])
        self.assertEqual(payload["diagnostics"]["reason"], "missing_module")
        self.assertEqual(payload["diagnostics"]["stage"], "import_adapter")
        self.assertEqual(payload["diagnostics"]["error_type"], "ModuleNotFoundError")

    def test_status_logs_and_reports_invalid_get_status_result_diagnostics(self) -> None:
        config = self._config(enabled=False)
        fake_module = _make_adapter_module(get_status=lambda: ["not", "a", "dict"])

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            self.assertLogs("src.services.alphasift_service", level="WARNING") as captured,
        ):
            payload = alphasift_endpoint.alphasift_status(config=config)

        self.assertFalse(payload["available"])
        self.assertEqual(payload["diagnostics"]["reason"], "unexpected_exception")
        self.assertEqual(payload["diagnostics"]["stage"], "get_status_result")
        self.assertEqual(payload["diagnostics"]["error_type"], "TypeError")
        self.assertIn("Unexpected AlphaSift get_status_result failure", "\n".join(captured.output))

    def test_status_logs_and_reports_missing_get_status_callable_diagnostics(self) -> None:
        config = self._config(enabled=False)
        fake_module = SimpleNamespace(list_strategies=lambda: [], screen=MagicMock(return_value=[]))

        with (
            patch("src.services.alphasift_service._import_alphasift", return_value=fake_module),
            self.assertLogs("src.services.alphasift_service", level="WARNING") as captured,
        ):
            payload = alphasift_endpoint.alphasift_status(config=config)

        self.assertFalse(payload["available"])
        self.assertEqual(payload["diagnostics"]["reason"], "unexpected_exception")
        self.assertEqual(payload["diagnostics"]["stage"], "get_status_callable")
        self.assertEqual(payload["diagnostics"]["error_type"], "HTTPException")
        self.assertIn("Unexpected AlphaSift get_status_callable failure", "\n".join(captured.output))

    def test_strategies_returns_adapter_strategies(self) -> None:
        config = self._config(enabled=True)
        fake_module = _make_adapter_module(
            list_strategies=lambda: [
                {"id": "dual_low", "name": "双低选股", "description": "value", "category": "价值"},
                {"id": "trend_quality", "title": "趋势质量", "description": "trend", "tag": "框架"},
            ],
        )

        with patch("src.services.alphasift_service._import_alphasift", return_value=fake_module):
            payload = self._strategies(config=config)

        self.assertEqual(payload["enabled"], True)
        self.assertEqual(payload["strategy_count"], 2)
        self.assertEqual(payload["strategies"][0]["id"], "dual_low")
        self.assertEqual(payload["strategies"][0]["name"], "双低选股")
        self.assertEqual(payload["strategies"][1]["name"], "趋势质量")

    def test_hotspots_returns_alphasift_hotspot_summaries(self) -> None:
        config = self._config(enabled=True)

        class HotspotRows(list):
            provider_used = "akshare"
            fallback_used = False
            source_errors = []
            stale = False
            stale_age_hours = None

        rows = HotspotRows([
            {
                "topic": "AI算力",
                "name": "AI算力",
                "heat_score": 88.0,
                "change_pct": 6.2,
                "stage": "加速主升",
                "leaders": ["中际旭创"],
            }
        ])
        discover = MagicMock(return_value=rows)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "hotspots.json"
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace(discover_hotspots=discover)),
            ):
                payload = self._hotspots(config=config, provider="akshare", top=1, refresh=True)

        self.assertEqual(payload["enabled"], True)
        self.assertEqual(payload["provider"], "akshare")
        self.assertEqual(payload["provider_used"], "akshare")
        self.assertEqual(payload["hotspot_count"], 1)
        self.assertEqual(payload["hotspots"][0]["topic"], "AI算力")
        self.assertEqual(payload["hotspots"][0]["heat_score"], 88.0)
        discover.assert_called_once()
        provider = discover.call_args.kwargs["provider"]
        self.assertTrue(hasattr(provider, "stock_board_concept_name_em"))
        self.assertTrue(hasattr(provider, "stock_board_industry_name_em"))
        self.assertEqual(discover.call_args.kwargs["top"], 1)

    def test_hotspots_default_provider_uses_dsa_eastmoney_provider(self) -> None:
        provider_name, provider = alphasift_service._resolve_hotspot_provider("")

        self.assertEqual(provider_name, "akshare")
        self.assertIsInstance(provider, alphasift_service.DsaEastMoneyHotspotProvider)

    def test_hotspots_refresh_uses_dsa_direct_rows_when_alphasift_rows_are_thin(self) -> None:
        config = self._config(enabled=True)

        class ThinRows(list):
            provider_used = "akshare"
            fallback_used = False
            source_errors = []
            stale = False
            stale_age_hours = None

        class FakeProvider(alphasift_service.DsaEastMoneyHotspotProvider):
            def hotspot_rows(self, *, top: int = 12) -> List[Dict[str, Any]]:
                return [
                    {"topic": "钼", "name": "钼", "heat_score": 96.0, "change_pct": 10.0, "leaders": ["盛龙股份"]},
                    {"topic": "铅锌", "name": "铅锌", "heat_score": 92.0, "change_pct": 9.14, "leaders": ["豫光金铅"]},
                    {"topic": "铜", "name": "铜", "heat_score": 89.0, "change_pct": 7.03, "leaders": ["江西铜业"]},
                ][:top]

        discover = MagicMock(return_value=ThinRows([
            {"topic": "AI算力", "name": "AI算力", "heat_score": 88.0},
        ]))

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "hotspots.json"
            provider = FakeProvider()
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace(discover_hotspots=discover)),
            ):
                payload = self._hotspots(config=config, provider="akshare", top=6, refresh=True)

        self.assertEqual(payload["provider_used"], "dsa_eastmoney_board_change")
        self.assertEqual(payload["hotspot_count"], 3)
        self.assertEqual([item["topic"] for item in payload["hotspots"][:3]], ["钼", "铅锌", "铜"])
        self.assertTrue(payload["fallback_used"])

    def test_hotspots_enriches_missing_metrics_from_dsa_provider(self) -> None:
        config = self._config(enabled=True)

        class HotspotRows(list):
            provider_used = "akshare"
            fallback_used = False
            source_errors = []
            stale = False
            stale_age_hours = None

        class FakeProvider(alphasift_service.DsaEastMoneyHotspotProvider):
            def hotspot_rows(self, *, top: int = 12) -> List[Dict[str, Any]]:
                return [{
                    "topic": "铜",
                    "name": "工业金属 · 铜",
                    "heat_score": 92.0,
                    "change_pct": 7.03,
                    "trend_score": 99.0,
                    "persistence_score": 64.3,
                    "sample_stock_count": 11,
                    "leaders": ["嘉元科技", "方邦股份"],
                    "theme_group": "工业金属",
                }]

        discover = MagicMock(return_value=HotspotRows([{
            "topic": "铜",
            "name": "铜",
            "heat_score": 92.0,
            "change_pct": 7.03,
        }]))

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "hotspots.json"
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", FakeProvider())),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace(discover_hotspots=discover)),
            ):
                payload = self._hotspots(config=config, provider="akshare", top=1, refresh=True)

        hotspot = payload["hotspots"][0]
        self.assertEqual(hotspot["name"], "工业金属 · 铜")
        self.assertEqual(hotspot["trend_score"], 99.0)
        self.assertEqual(hotspot["persistence_score"], 64.3)
        self.assertEqual(hotspot["sample_stock_count"], 11)
        self.assertEqual(hotspot["leaders"], ["嘉元科技", "方邦股份"])

    def test_hotspots_default_cache_miss_does_not_import_hotspot_module(self) -> None:
        config = self._config(enabled=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "missing-hotspots.json"
            import_hotspot = MagicMock(side_effect=AssertionError("default cache read must not import live hotspot module"))
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._import_alphasift_hotspot", import_hotspot),
            ):
                payload = self._hotspots(config=config, provider="akshare", top=6, refresh=False)

        self.assertEqual(payload["enabled"], True)
        self.assertEqual(payload["provider"], "akshare")
        self.assertEqual(payload["cache_used"], False)
        self.assertEqual(payload["hotspots"], [])
        self.assertEqual(payload["hotspot_count"], 0)
        self.assertEqual(payload["source_errors"], [])
        import_hotspot.assert_not_called()

    def test_hotspots_ignores_too_thin_default_cache(self) -> None:
        config = self._config(enabled=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "hotspots.json"
            cache_path.write_text(
                json.dumps({
                    "cached_at": "2026-06-13T08:06:50Z",
                    "payload": {
                        "enabled": True,
                        "provider": "akshare",
                        "hotspots": [{"topic": "AI算力", "name": "AI算力", "heat_score": 88.0}],
                        "hotspot_count": 1,
                    },
                }),
                encoding="utf-8",
            )
            import_hotspot = MagicMock(side_effect=AssertionError("default cache read must not import live hotspot module"))
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._import_alphasift_hotspot", import_hotspot),
            ):
                payload = self._hotspots(config=config, provider="akshare", top=12, refresh=False)

        self.assertEqual(payload["hotspots"], [])
        self.assertEqual(payload["hotspot_count"], 0)
        import_hotspot.assert_not_called()

    def test_hotspots_uses_last_success_cache_by_default(self) -> None:
        config = self._config(enabled=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "hotspots.json"
            cache_path.write_text(
                json.dumps({
                    "cached_at": "2026-06-07T12:00:00Z",
                    "payload": {
                        "enabled": True,
                        "provider": "akshare",
                        "provider_used": "DsaEastMoneyHotspotProvider",
                        "fallback_used": False,
                        "cache_used": False,
                        "cached_at": "2026-06-07T12:00:00Z",
                        "source_errors": [],
                        "hotspots": [
                            {"topic": "玻璃基板", "heat_score": 88.0},
                            {"topic": "机器人执行器", "heat_score": 80.0},
                        ],
                        "hotspot_count": 2,
                    },
                }),
                encoding="utf-8",
            )
            discover = MagicMock()
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace(discover_hotspots=discover)),
            ):
                payload = self._hotspots(config=config, provider="akshare", top=1, refresh=False)

        self.assertEqual(payload["cache_used"], True)
        self.assertEqual(payload["cached_at"], "2026-06-07T12:00:00Z")
        self.assertEqual(payload["hotspot_count"], 1)
        self.assertEqual(payload["hotspots"][0]["topic"], "玻璃基板")
        discover.assert_not_called()

    def test_hotspots_refresh_falls_back_to_cache_when_provider_returns_only_errors(self) -> None:
        config = self._config(enabled=True)

        class HotspotRows(list):
            provider_used = "akshare"
            fallback_used = False
            source_errors = ["akshare returned no usable board rows"]
            stale = False
            stale_age_hours = None

        rows = HotspotRows()
        discover = MagicMock(return_value=rows)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "hotspots.json"
            cache_path.write_text(
                json.dumps({
                    "cached_at": "2026-06-07T12:00:00Z",
                    "payload": {
                        "enabled": True,
                        "provider": "akshare",
                        "provider_used": "DsaEastMoneyHotspotProvider",
                        "fallback_used": False,
                        "cache_used": False,
                        "cached_at": "2026-06-07T12:00:00Z",
                        "source_errors": [],
                        "hotspots": [
                            {"topic": "MLCC", "heat_score": 91.0},
                        ],
                        "hotspot_count": 1,
                    },
                }),
                encoding="utf-8",
            )
            provider = alphasift_service.DsaEastMoneyHotspotProvider()
            provider.hotspot_rows = MagicMock(return_value=[])
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace(discover_hotspots=discover)),
            ):
                payload = self._hotspots(config=config, provider="akshare", top=1, refresh=True)

        self.assertEqual(payload["cache_used"], True)
        self.assertEqual(payload["fallback_used"], True)
        self.assertEqual(payload["hotspot_count"], 1)
        self.assertEqual(payload["hotspots"][0]["topic"], "MLCC")
        self.assertEqual(payload["source_errors"], ["alphasift_hotspot_source_error"])
        discover.assert_called_once()

    def test_hotspots_refresh_failure_without_cache_returns_friendly_empty_payload(self) -> None:
        config = self._config(enabled=True)
        discover = MagicMock(side_effect=RuntimeError("RemoteDisconnected('Remote end closed connection without response')"))

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "missing-hotspots.json"
            provider = alphasift_service.DsaEastMoneyHotspotProvider()
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace(discover_hotspots=discover)),
            ):
                payload = self._hotspots(config=config, provider="akshare", top=1, refresh=True)

        self.assertEqual(payload["hotspots"], [])
        self.assertEqual(payload["hotspot_count"], 0)
        self.assertEqual(payload["source_errors"], ["eastmoney_hotspot_unavailable"])
        self.assertEqual(payload["message"], "热点源连接中断，暂无可用缓存。")
        self.assertNotIn("RemoteDisconnected", payload["message"])
        discover.assert_called_once()

    def test_hotspots_refresh_failure_with_cache_uses_stable_public_error_code(self) -> None:
        config = self._config(enabled=True)
        discover = MagicMock(side_effect=RuntimeError(PUBLIC_DIAGNOSTIC_SECRET))

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "hotspots.json"
            cache_path.write_text(
                json.dumps({
                    "cached_at": "2026-06-07T12:00:00Z",
                    "payload": {
                        "enabled": True,
                        "provider": "akshare",
                        "provider_used": "DsaEastMoneyHotspotProvider",
                        "source_errors": [],
                        "hotspots": [{"topic": "MLCC", "heat_score": 91.0}],
                    },
                }),
                encoding="utf-8",
            )
            provider = alphasift_service.DsaEastMoneyHotspotProvider()
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
                patch(
                    "src.services.alphasift_service._import_alphasift_hotspot",
                    return_value=SimpleNamespace(discover_hotspots=discover),
                ),
            ):
                payload = self._hotspots(config=config, provider="akshare", top=1, refresh=True)

        self.assertEqual(payload["source_errors"], ["alphasift_hotspot_refresh_failed"])
        self.assertTrue(payload["cache_used"])
        self.assert_public_payload_is_private(payload)

    def test_hotspots_default_refresh_degraded_eastmoney_failure_without_cache_returns_friendly_empty_payload(self) -> None:
        config = self._config(enabled=True)

        class HotspotRows(list):
            provider_used = "DsaEastMoneyHotspotProvider"
            fallback_used = False
            source_errors = ["RemoteDisconnected('Remote end closed connection without response')"]
            stale = False
            stale_age_hours = None

        discover = MagicMock(return_value=HotspotRows())

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "missing-hotspots.json"
            app = FastAPI()
            app.include_router(alphasift_endpoint.router, prefix="/api/v1/alphasift")
            app.dependency_overrides[alphasift_endpoint.get_config_dep] = lambda: config
            with (
                patch.dict(os.environ, {"INDUSTRY_PROVIDER": ""}, clear=False),
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service.DsaEastMoneyHotspotProvider.hotspot_rows", return_value=[]),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace(discover_hotspots=discover)),
            ):
                response = TestClient(app).get("/api/v1/alphasift/hotspots?refresh=true&top=1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(payload["provider"], "akshare")
        self.assertEqual(payload["provider_used"], "DsaEastMoneyHotspotProvider")
        self.assertEqual(payload["hotspots"], [])
        self.assertEqual(payload["hotspot_count"], 0)
        self.assertEqual(payload["source_errors"], ["eastmoney_hotspot_unavailable"])
        self.assertEqual(payload["message"], "热点源连接中断，暂无可用缓存。")
        self.assertNotIn("RemoteDisconnected", payload["message"])
        discover.assert_called_once()

    def test_hotspots_refresh_runtime_failure_without_cache_raises_integration_error(self) -> None:
        config = self._config(enabled=True)
        discover = MagicMock(side_effect=RuntimeError("adapter contract returned invalid payload"))

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "missing-hotspots.json"
            provider = alphasift_service.DsaEastMoneyHotspotProvider()
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace(discover_hotspots=discover)),
            ):
                with self.assertRaises(HTTPException) as caught:
                    self._hotspots(config=config, provider="akshare", top=1, refresh=True)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_hotspot_refresh_failed")
        self.assertEqual(caught.exception.detail["message"], "AlphaSift 热点刷新失败，请稍后重试。")
        discover.assert_called_once()

    def test_hotspots_refresh_runtime_failure_without_cache_hides_raw_diagnostic(self) -> None:
        config = self._config(enabled=True)
        discover = MagicMock(side_effect=RuntimeError(PUBLIC_DIAGNOSTIC_SECRET))

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "missing-hotspots.json"
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("custom", "custom")),
                patch(
                    "src.services.alphasift_service._import_alphasift_hotspot",
                    return_value=SimpleNamespace(discover_hotspots=discover),
                ),
            ):
                with self.assertRaises(HTTPException) as caught:
                    self._hotspots(config=config, provider="custom", top=1, refresh=True)

        self.assertEqual(caught.exception.detail["error"], "alphasift_hotspot_refresh_failed")
        self.assertEqual(caught.exception.detail["message"], "AlphaSift 热点刷新失败，请稍后重试。")
        self.assert_public_payload_is_private(caught.exception.detail)

    def test_hotspots_refresh_non_akshare_failure_without_cache_raises_integration_error(self) -> None:
        config = self._config(enabled=True)
        discover = MagicMock(side_effect=RuntimeError("RemoteDisconnected('remote provider failed')"))

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "missing-hotspots.json"
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("custom", "custom")),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace(discover_hotspots=discover)),
            ):
                with self.assertRaises(HTTPException) as caught:
                    self._hotspots(config=config, provider="custom", top=1, refresh=True)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_hotspot_refresh_failed")
        self.assertEqual(caught.exception.detail["message"], "AlphaSift 热点刷新失败，请稍后重试。")
        discover.assert_called_once()

    def test_hotspot_provider_retries_transient_eastmoney_failure(self) -> None:
        import requests

        provider = alphasift_service.DsaEastMoneyHotspotProvider()

        class FakeResponse:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> Dict[str, Any]:
                return {
                    "data": {
                        "diff": [
                            {"f14": "AI算力", "f3": 4.2, "f140": "工业富联", "f104": 8, "f105": 2},
                        ]
                    }
                }

        get_mock = MagicMock(side_effect=[requests.exceptions.ConnectionError("Connection aborted"), FakeResponse()])
        provider._last_request_ts = time.monotonic()
        with (
            patch("src.services.alphasift_service.time.sleep") as sleep_mock,
            patch.object(provider._session, "get", get_mock),
            patch("requests.get", side_effect=AssertionError("bare requests.get should not be used for EastMoney hotspots")) as bare_get,
        ):
            frame = provider._fetch_board_names(source_fs="m:90 t:3 f:!50")

        self.assertFalse(frame.empty)
        self.assertEqual(frame.iloc[0]["name"], "AI算力")
        self.assertEqual(get_mock.call_count, 2)
        bare_get.assert_not_called()
        sleep_values = [call.args[0] for call in sleep_mock.call_args_list if call.args]
        self.assertIn(0.3, sleep_values)
        self.assertTrue(any(0 < value <= provider._min_request_interval for value in sleep_values))

    def test_hotspots_respects_custom_alphasift_data_dir_for_cache_paths(self) -> None:
        config = self._config(enabled=True)

        class HotspotRows(list):
            provider_used = "akshare"
            fallback_used = False
            source_errors = []
            stale = False
            stale_age_hours = None

        rows = HotspotRows([
            {"topic": "机器人执行器", "heat_score": 86.0, "change_pct": 4.2},
            {"topic": "减速器", "heat_score": 82.0, "change_pct": 3.8},
            {"topic": "铜", "heat_score": 80.0, "change_pct": 3.2},
        ])
        captured: Dict[str, Any] = {}

        def discover(**kwargs):
            captured.update(kwargs)
            return rows

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "persistent-alphasift"
            cache_path = data_dir / "hotspots.json"
            history_path = data_dir / "hotspot.history.jsonl"
            with (
                patch.dict(os.environ, {"ALPHASIFT_DATA_DIR": str(data_dir)}, clear=False),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch(
                    "src.services.alphasift_service._import_alphasift_hotspot",
                    return_value=SimpleNamespace(discover_hotspots=discover),
                ),
            ):
                payload = self._hotspots(config=config, provider="akshare", top=3, refresh=True)

            self.assertEqual(payload["hotspots"][0]["topic"], "机器人执行器")
            self.assertEqual(captured["history_path"], history_path)
            self.assertEqual(captured["fallback_cache_path"], cache_path)
            self.assertTrue(cache_path.exists())

            discover_again = MagicMock()
            with (
                patch.dict(os.environ, {"ALPHASIFT_DATA_DIR": str(data_dir)}, clear=False),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch(
                    "src.services.alphasift_service._import_alphasift_hotspot",
                    return_value=SimpleNamespace(discover_hotspots=discover_again),
                ),
            ):
                cached = self._hotspots(config=config, provider="akshare", top=1, refresh=False)

            cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))

        self.assertEqual(cached["cache_used"], True)
        self.assertEqual(cached["hotspots"][0]["topic"], "机器人执行器")
        discover_again.assert_not_called()
        self.assertEqual(cache_payload["schema_version"], 2)
        self.assertEqual(cache_payload["hotspots"][0]["topic"], "机器人执行器")

    def test_hotspots_reads_alphasift_v2_hotspot_cache(self) -> None:
        config = self._config(enabled=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "hotspots.json"
            cache_path.write_text(
                json.dumps({
                    "schema_version": 2,
                    "generated_at": "2026-06-13T02:55:00Z",
                    "source_errors": "provider timeout",
                    "metadata": {"schema_version": 2, "provider_used": "last_good_cache"},
                    "hotspots": [
                        {
                            "topic": "算力",
                            "canonical_topic": "算力",
                            "aliases": ["AI算力"],
                            "heat_score": 88.0,
                            "quality_status": "available",
                        }
                    ],
                }),
                encoding="utf-8",
            )
            discover = MagicMock()
            with (
                patch("src.services.alphasift_service.DSA_ALPHASIFT_HOTSPOT_CACHE_PATH", cache_path),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace(discover_hotspots=discover)),
            ):
                cached = self._hotspots(config=config, provider="akshare", top=1, refresh=False)

        self.assertEqual(cached["cache_used"], True)
        self.assertEqual(cached["cached_at"], "2026-06-13T02:55:00Z")
        self.assertEqual(cached["schema_version"], 2)
        self.assertEqual(cached["source_errors"], ["alphasift_hotspot_source_error"])
        self.assertEqual(cached["hotspots"][0]["canonical_topic"], "算力")
        discover.assert_not_called()

    def test_hotspots_refresh_prefetches_detail_payloads(self) -> None:
        config = self._config(enabled=True)

        class HotspotRows(list):
            provider_used = "akshare"
            fallback_used = False
            source_errors = []
            stale = False
            stale_age_hours = None

        rows = HotspotRows([
            {"topic": "Moly", "heat_score": 96.0, "change_pct": 10.0},
            {"topic": "Copper", "heat_score": 88.0, "change_pct": 6.0},
        ])

        def detail_side_effect(*, topic: str, provider: str = "", refresh: bool = False) -> Dict[str, Any]:
            return {
                "enabled": True,
                "provider": provider,
                "topic": topic,
                "summary": f"{topic} summary",
                "route": [{"title": f"{topic} event", "description": f"{topic} catalyst"}],
                "stocks": [],
                "stock_count": 0,
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "alphasift"
            with (
                patch.dict(os.environ, {"ALPHASIFT_DATA_DIR": str(data_dir)}, clear=False),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch(
                    "src.services.alphasift_service._import_alphasift_hotspot",
                    return_value=SimpleNamespace(discover_hotspots=MagicMock(return_value=rows)),
                ),
                patch.object(alphasift_service.AlphaSiftService, "hotspot_detail", side_effect=detail_side_effect) as detail_mock,
            ):
                payload = self._hotspots(config=config, provider="akshare", top=2, refresh=True, include_details=True)

            cache_payload = json.loads((data_dir / "hotspots.json").read_text(encoding="utf-8"))

        self.assertEqual(set(payload["details"].keys()), {"Moly", "Copper"})
        self.assertEqual(payload["details"]["Moly"]["route"][0]["title"], "Moly event")
        self.assertEqual(cache_payload["payload"]["details"]["Copper"]["summary"], "Copper summary")
        self.assertEqual(detail_mock.call_count, 2)

    def test_hotspot_news_local_summary_extracts_event_instead_of_truncating(self) -> None:
        text = (
            "【股商异动】钼板块异动大涨5.64%！金钼股份涨停，机构看好行业机遇。"
            "消息称以钼代钨带动小金属行情，市场关注材料替代和供需偏紧。"
            "截至10:30，相关个股现价和成交额继续变化，后续建议关注供需平衡。"
        )

        summary = alphasift_service._summarize_hotspot_news_event_locally(topic="钼", text=text)

        self.assertIn("以钼代钨", summary)
        self.assertIn("小金属", summary)
        self.assertNotIn("截至", summary)
        self.assertNotIn("后续建议", summary)
        self.assertLessEqual(len(summary), alphasift_service.DSA_ALPHASIFT_HOTSPOT_EVENT_SUMMARY_MAX_CHARS)

    def test_hotspot_detail_uses_alphasift_contract_detail_cache(self) -> None:
        config = self._config(enabled=True)
        captured: Dict[str, Any] = {}

        def get_hotspot_detail(topic: str, **kwargs: Any) -> Dict[str, Any]:
            captured.update({"topic": topic, **kwargs})
            return {
                "summary": {
                    "topic": topic,
                    "name": "算力",
                    "canonical_topic": "算力",
                    "aliases": "AI算力",
                    "heat_score": 88.0,
                    "stage": "加速主升",
                    "leaders": ["算力龙头"],
                    "quality_status": "stale",
                    "missing_fields": "live_stocks",
                    "source_errors": "none: no live detail rows",
                    "fallback_used": True,
                    "stale": True,
                    "stale_age_hours": 1.5,
                    "resolver_candidates": [{"topic": "算力", "confidence": 1.0}],
                },
                "stocks": [{
                    "code": "300001",
                    "name": "算力龙头",
                    "role": "核心龙头",
                    "source": "last_good_cache.leader_stocks",
                    "source_confidence": 0.65,
                    "fallback_used": True,
                }],
                "timeline": [{"date": "2026-06-13", "source": "新闻", "title": "AI算力催化"}],
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "alphasift"
            provider = alphasift_service.DsaEastMoneyHotspotProvider()
            with (
                patch.dict(os.environ, {"ALPHASIFT_DATA_DIR": str(data_dir)}, clear=False),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
                patch(
                    "src.services.alphasift_service._import_alphasift_hotspot",
                    return_value=SimpleNamespace(get_hotspot_detail=get_hotspot_detail),
                ),
            ):
                payload = self._hotspot_detail(config=config, provider="akshare", topic="AI算力")

        self.assertEqual(captured["topic"], "AI算力")
        self.assertIs(captured["provider"], provider)
        self.assertEqual(captured["fallback_cache_path"], data_dir / "hotspots.json")
        self.assertEqual(captured["history_path"], data_dir / "hotspot.history.jsonl")
        self.assertEqual(payload["enabled"], True)
        self.assertEqual(payload["provider"], "akshare")
        self.assertEqual(payload["topic"], "AI算力")
        self.assertEqual(payload["canonical_topic"], "算力")
        self.assertEqual(payload["quality_status"], "stale")
        self.assertEqual(payload["aliases"], ["AI算力"])
        self.assertEqual(payload["missing_fields"], ["live_stocks"])
        self.assertEqual(payload["source_errors"], ["alphasift_hotspot_detail_source_error"])
        self.assertEqual(payload["stocks"][0]["source"], "last_good_cache.leader_stocks")
        self.assertEqual(payload["leader_stocks"][0]["source"], "last_good_cache.leader_stocks")
        self.assertEqual(payload["route"][0]["title"], "AI算力催化")

    def test_hotspot_detail_backfills_stocks_from_contract_leader_stocks(self) -> None:
        config = self._config(enabled=True)

        def get_hotspot_detail(topic: str, **_kwargs: Any) -> Dict[str, Any]:
            return {
                "summary": {"topic": topic, "name": "算力"},
                "leader_stocks": [{
                    "code": "300001",
                    "name": "算力龙头",
                    "role": "核心龙头",
                    "source": "last_good_cache.leader_stocks",
                }],
                "route": [{"title": "盘中发酵", "description": "真实新闻催化", "source": "news"}],
            }

        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider.hotspot_detail = MagicMock(side_effect=AssertionError("provider route fallback should not be used"))
        with (
            patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
            patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
            patch(
                "src.services.alphasift_service._import_alphasift_hotspot",
                return_value=SimpleNamespace(get_hotspot_detail=get_hotspot_detail),
            ),
        ):
            payload = self._hotspot_detail(config=config, provider="akshare", topic="AI算力")

        self.assertEqual(payload["stocks"][0]["name"], "算力龙头")
        self.assertEqual(payload["leader_stocks"][0]["name"], "算力龙头")
        self.assertEqual(payload["stock_count"], 1)
        provider.hotspot_detail.assert_not_called()

    def test_hotspot_detail_compat_backfills_from_summary_detail_leader_stocks(self) -> None:
        payload = alphasift_service._ensure_hotspot_detail_compat_fields({
            "summary_detail": {
                "leader_stocks": [{
                    "code": "300001",
                    "name": "缓存龙头",
                    "source": "legacy.summary_detail.leader_stocks",
                }],
            },
        })

        self.assertEqual(payload["stocks"][0]["name"], "缓存龙头")
        self.assertEqual(payload["leader_stocks"][0]["name"], "缓存龙头")
        self.assertEqual(payload["stock_count"], 1)

    def test_hotspot_detail_backfills_stocks_from_summary_leader_stocks(self) -> None:
        config = self._config(enabled=True)

        def get_hotspot_detail(topic: str, **_kwargs: Any) -> Dict[str, Any]:
            return {
                "summary": {
                    "topic": topic,
                    "name": "算力",
                    "leader_stocks": [{
                        "code": "300001",
                        "name": "嵌套龙头",
                        "role": "缓存龙头",
                        "source": "last_good_cache.summary.leader_stocks",
                    }],
                },
                "route": [{"title": "盘中发酵", "description": "真实新闻催化", "source": "news"}],
            }

        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider.hotspot_detail = MagicMock(side_effect=AssertionError("provider route fallback should not be used"))
        with (
            patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
            patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
            patch(
                "src.services.alphasift_service._import_alphasift_hotspot",
                return_value=SimpleNamespace(get_hotspot_detail=get_hotspot_detail),
            ),
        ):
            payload = self._hotspot_detail(config=config, provider="akshare", topic="AI算力")

        self.assertEqual(payload["stocks"][0]["name"], "嵌套龙头")
        self.assertEqual(payload["leader_stocks"][0]["name"], "嵌套龙头")
        self.assertEqual(payload["stock_count"], 1)
        provider.hotspot_detail.assert_not_called()

    def test_hotspot_detail_uses_dsa_detail_cache_after_first_fetch(self) -> None:
        config = self._config(enabled=True)
        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider.hotspot_detail = MagicMock(return_value={
            "topic": "钼",
            "name": "小金属 · 钼",
            "summary": "钼 当前涨跌幅 10.00%。",
            "route": [{"title": "当日发酵", "description": "钼板块异动。", "source": "eastmoney_board_change"}],
            "stocks": [{"code": "001257", "name": "盛龙股份"}],
            "stock_count": 1,
            "source_errors": [],
        })

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(os.environ, {"ALPHASIFT_DATA_DIR": str(Path(tmpdir) / "alphasift")}, clear=False),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace()),
            ):
                first = self._hotspot_detail(config=config, provider="akshare", topic="钼")
                second = self._hotspot_detail(config=config, provider="akshare", topic="钼")

        provider.hotspot_detail.assert_called_once_with("钼")
        self.assertFalse(first.get("cache_used", False))
        self.assertTrue(second["cache_used"])
        self.assertEqual(second["stocks"][0]["name"], "盛龙股份")
        self.assertEqual(second["leader_stocks"][0]["name"], "盛龙股份")

    def test_hotspot_detail_refresh_bypasses_dsa_detail_cache(self) -> None:
        config = self._config(enabled=True)
        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider.hotspot_detail = MagicMock(side_effect=[
            {
                "topic": "钼",
                "summary": "旧详情",
                "route": [{"title": "旧发酵", "description": "旧缓存", "source": "eastmoney_board_change"}],
                "stocks": [{"code": "001257", "name": "旧龙头"}],
                "stock_count": 1,
                "source_errors": [],
            },
            {
                "topic": "钼",
                "summary": "新详情",
                "route": [{"title": "新发酵", "description": "实时刷新", "source": "eastmoney_board_change"}],
                "stocks": [{"code": "001257", "name": "新龙头"}],
                "stock_count": 1,
                "source_errors": [],
            },
        ])

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(os.environ, {"ALPHASIFT_DATA_DIR": str(Path(tmpdir) / "alphasift")}, clear=False),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace()),
            ):
                first = self._hotspot_detail(config=config, provider="akshare", topic="钼")
                cached = self._hotspot_detail(config=config, provider="akshare", topic="钼")
                refreshed = self._hotspot_detail(config=config, provider="akshare", topic="钼", refresh=True)

        self.assertEqual(provider.hotspot_detail.call_count, 2)
        self.assertEqual(first["stocks"][0]["name"], "旧龙头")
        self.assertEqual(cached["stocks"][0]["name"], "旧龙头")
        self.assertTrue(cached["cache_used"])
        self.assertEqual(refreshed["stocks"][0]["name"], "新龙头")
        self.assertFalse(refreshed.get("cache_used", False))

    def test_hotspot_detail_adds_real_search_event_when_configured(self) -> None:
        config = Config(alphasift_enabled=True, bocha_api_keys=["test-key"])
        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider.hotspot_detail = MagicMock(return_value={
            "topic": "钼",
            "summary": "钼 当前涨跌幅 10.00%。",
            "route": [{"title": "当日发酵", "description": "钼板块异动。", "source": "eastmoney_board_change"}],
            "stocks": [],
            "stock_count": 0,
            "source_errors": [],
        })
        search_service = MagicMock()
        search_service.search_stock_news.return_value = SimpleNamespace(
            success=True,
            provider="Bocha",
            results=[
                SimpleNamespace(
                    title="以钼代钨带动小金属行情",
                    snippet=(
                        "以钼代钨带动小金属行情 2026-06-12 市场关注材料替代和供需偏紧。"
                        "金钼股份、盛龙股份等相关个股出现异动，报道还详细列出价格、成交、"
                        "机构观点、供需格局和完整产业链背景，后续建议继续关注供需平衡与政策动力。"
                    ),
                    url="https://example.com/news",
                    source="ExampleNews",
                    published_date="2026-06-12",
                )
            ],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(os.environ, {"ALPHASIFT_DATA_DIR": str(Path(tmpdir) / "alphasift")}, clear=False),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace()),
                patch("src.search_service.SearchService", return_value=search_service),
            ):
                payload = self._hotspot_detail(config=config, provider="akshare", topic="钼")

        self.assertEqual(payload["route"][0]["source"], "ExampleNews")
        self.assertEqual(payload["route"][0]["title"], "消息催化")
        self.assertEqual(payload["route"][0]["date"], "2026-06-12")
        self.assertEqual(payload["route"][0]["url"], "https://example.com/news")
        self.assertLessEqual(len(payload["route"][0]["description"]), 93)
        self.assertNotIn("完整产业链背景", payload["route"][0]["description"])
        search_service.search_stock_news.assert_called_once()

    def test_hotspot_detail_prefers_timeline_when_contract_route_is_empty(self) -> None:
        config = self._config(enabled=True)
        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider.hotspot_detail = MagicMock(side_effect=RuntimeError("provider fallback should not be used"))

        def get_hotspot_detail(topic: str, **_kwargs: Any) -> Dict[str, Any]:
            return {
                "summary": {
                    "topic": topic,
                    "name": "算力",
                    "canonical_topic": "算力",
                    "quality_status": "available",
                },
                "stocks": [{
                    "code": "300001",
                    "name": "算力龙头",
                }],
                "timeline": [{"date": "2026-06-13", "source": "新闻", "title": "AI算力催化"}],
                "route": [],
            }

        with (
            patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
            patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
            patch(
                "src.services.alphasift_service._import_alphasift_hotspot",
                return_value=SimpleNamespace(get_hotspot_detail=get_hotspot_detail),
            ),
        ):
            payload = self._hotspot_detail(config=config, provider="akshare", topic="AI算力")

        self.assertEqual(payload["route"][0]["title"], "AI算力催化")
        self.assertEqual(payload["route"][0]["source"], "新闻")
        provider.hotspot_detail.assert_not_called()

    def test_hotspot_detail_falls_back_to_provider_when_contract_helper_fails(self) -> None:
        config = self._config(enabled=True)
        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider.hotspot_detail = MagicMock(return_value={
            "topic": "机器人执行器",
            "summary": "机器人执行器 盘中发酵。",
            "route": [{"title": "盘中发酵", "description": "provider fallback route.", "source": "eastmoney_board_change"}],
            "stocks": [{"code": "002000", "name": "旧路径个股"}],
            "stock_count": 1,
            "source_errors": [],
        })

        def get_hotspot_detail(topic: str, **_kwargs: Any) -> Dict[str, Any]:
            raise RuntimeError("contract parser broken")

        with (
            patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
            patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
            patch(
                "src.services.alphasift_service._import_alphasift_hotspot",
                return_value=SimpleNamespace(get_hotspot_detail=get_hotspot_detail),
            ),
        ):
            payload = self._hotspot_detail(config=config, provider="akshare", topic="机器人执行器")

        self.assertEqual(payload["route"][0]["title"], "盘中发酵")
        self.assertEqual(payload["route"][0]["source"], "eastmoney_board_change")
        provider.hotspot_detail.assert_called_once_with("机器人执行器")
        self.assertEqual(payload["source_errors"], ["alphasift_hotspot_detail_fallback"])
        self.assertTrue(payload["fallback_used"])

    def test_hotspot_detail_helper_fallback_hides_raw_diagnostic(self) -> None:
        config = self._config(enabled=True)
        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider.hotspot_detail = MagicMock(return_value={
            "topic": "机器人执行器",
            "summary": "机器人执行器盘中发酵。",
            "route": [{"title": "盘中发酵", "source": "eastmoney_board_change"}],
            "stocks": [],
            "source_errors": [],
        })

        with (
            patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
            patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
            patch(
                "src.services.alphasift_service._import_alphasift_hotspot",
                return_value=SimpleNamespace(
                    get_hotspot_detail=MagicMock(side_effect=RuntimeError(PUBLIC_DIAGNOSTIC_SECRET))
                ),
            ),
        ):
            payload = self._hotspot_detail(config=config, provider="akshare", topic="机器人执行器")

        self.assertEqual(payload["source_errors"], ["alphasift_hotspot_detail_fallback"])
        self.assert_public_payload_is_private(payload)

    def test_hotspot_detail_failure_with_stale_cache_uses_stable_public_error_code(self) -> None:
        config = self._config(enabled=True)
        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider.hotspot_detail = MagicMock(side_effect=RuntimeError(PUBLIC_DIAGNOSTIC_SECRET))

        with tempfile.TemporaryDirectory() as tmpdir:
            data_dir = Path(tmpdir) / "alphasift"
            with patch.dict(os.environ, {"ALPHASIFT_DATA_DIR": str(data_dir)}, clear=False):
                cache_path = alphasift_service._alphasift_hotspot_detail_cache_path(
                    provider="akshare",
                    topic="机器人执行器",
                )
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(
                    json.dumps({
                        "cached_at": "2020-01-01T00:00:00Z",
                        "payload": {
                            "topic": "机器人执行器",
                            "summary": "stale",
                            "stocks": [],
                            "source_errors": [],
                        },
                    }),
                    encoding="utf-8",
                )
                with (
                    patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                    patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
                    patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace()),
                ):
                    payload = self._hotspot_detail(
                        config=config,
                        provider="akshare",
                        topic="机器人执行器",
                        refresh=True,
                    )

        self.assertEqual(payload["source_errors"], ["alphasift_hotspot_detail_stale_cache"])
        self.assertTrue(payload["stale"])
        self.assert_public_payload_is_private(payload)

    def test_hotspot_detail_failure_without_cache_hides_raw_diagnostic(self) -> None:
        config = self._config(enabled=True)
        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider.hotspot_detail = MagicMock(side_effect=RuntimeError(PUBLIC_DIAGNOSTIC_SECRET))

        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch.dict(os.environ, {"ALPHASIFT_DATA_DIR": str(Path(tmpdir) / "alphasift")}, clear=False),
                patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
                patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
                patch("src.services.alphasift_service._import_alphasift_hotspot", return_value=SimpleNamespace()),
            ):
                with self.assertRaises(HTTPException) as caught:
                    self._hotspot_detail(
                        config=config,
                        provider="akshare",
                        topic="机器人执行器",
                        refresh=True,
                    )

        self.assertEqual(caught.exception.detail["error"], "alphasift_hotspot_detail_failed")
        self.assertEqual(caught.exception.detail["message"], "AlphaSift 热点详情获取失败，请稍后重试。")
        self.assert_public_payload_is_private(caught.exception.detail)

    def test_hotspot_detail_preserves_provider_route_when_contract_detail_has_no_timeline(self) -> None:
        config = self._config(enabled=True)
        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider.hotspot_detail = MagicMock(return_value={
            "topic": "机器人执行器",
            "summary": "机器人执行器 盘中发酵。",
            "route": [{
                "title": "盘中发酵",
                "description": "机器人执行器 当前有异动记录。",
                "source": "eastmoney_board_change",
            }],
            "stocks": [{"code": "002000", "name": "旧路径个股"}],
            "stock_count": 1,
            "source_errors": [],
        })

        def get_hotspot_detail(topic: str, **_kwargs: Any) -> Dict[str, Any]:
            return {
                "summary": {
                    "topic": topic,
                    "name": "机器人执行器",
                    "canonical_topic": "机器人执行器",
                    "quality_status": "available",
                },
                "stocks": [{
                    "code": "300000",
                    "name": "合约路径个股",
                    "source": "alphasift_contract",
                }],
            }

        with (
            patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
            patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
            patch(
                "src.services.alphasift_service._import_alphasift_hotspot",
                return_value=SimpleNamespace(get_hotspot_detail=get_hotspot_detail),
            ),
        ):
            payload = self._hotspot_detail(config=config, provider="akshare", topic="机器人执行器")

        self.assertEqual(payload["route"][0]["title"], "盘中发酵")
        self.assertEqual(payload["route"][0]["source"], "eastmoney_board_change")
        self.assertEqual(payload["stocks"][0]["name"], "合约路径个股")
        provider.hotspot_detail.assert_called_once_with("机器人执行器")

    def test_hotspot_detail_returns_route_and_concept_stocks(self) -> None:
        config = self._config(enabled=True)

        class FakeProvider(alphasift_service.DsaEastMoneyHotspotProvider):
            def hotspot_detail(self, topic: str) -> Dict[str, Any]:
                return {
                    "topic": topic,
                    "summary": f"{topic} 盘中发酵。",
                    "route": [{"title": "盘中发酵", "description": "出现大笔买入。"}],
                    "stocks": [{"code": "920438", "name": "戈碧迦", "role": "异动核心"}],
                    "stock_count": 1,
                    "source_errors": [],
                }

        with (
            patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
            patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", FakeProvider())),
        ):
            payload = self._hotspot_detail(config=config, provider="akshare", topic="玻璃基板")

        self.assertEqual(payload["enabled"], True)
        self.assertEqual(payload["provider"], "akshare")
        self.assertEqual(payload["topic"], "玻璃基板")
        self.assertEqual(payload["route"][0]["title"], "盘中发酵")
        self.assertEqual(payload["stocks"][0]["name"], "戈碧迦")
        self.assertEqual(payload["leader_stocks"][0]["name"], "戈碧迦")

    def test_hotspot_detail_route_accepts_slash_containing_topic(self) -> None:
        config = self._config(enabled=True)
        app = FastAPI()
        app.include_router(alphasift_endpoint.router, prefix="/api/v1/alphasift")
        app.dependency_overrides[alphasift_endpoint.get_config_dep] = lambda: config
        service = MagicMock()
        service.hotspot_detail.return_value = {
            "enabled": True,
            "provider": "akshare",
            "topic": "DRG/DIP",
            "route": [],
            "stocks": [],
            "stock_count": 0,
        }

        with patch("api.v1.endpoints.alphasift._service", return_value=service):
            response = TestClient(app).get("/api/v1/alphasift/hotspots/DRG%2FDIP?provider=akshare")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["topic"], "DRG/DIP")
        service.hotspot_detail.assert_called_once_with(topic="DRG/DIP", provider="akshare", refresh=False)

    def test_hotspot_detail_falls_back_when_ths_constituents_fail(self) -> None:
        import pandas as pd

        config = self._config(enabled=True)

        class FakeProvider(alphasift_service.DsaEastMoneyHotspotProvider):
            def _fetch_ths_constituents(self, topic: str) -> Any:
                raise TimeoutError("ths timeout")

            def _fallback_constituents(self, topic: str) -> Any:
                return pd.DataFrame([{
                    "code": "300000",
                    "name": "中际旭创",
                    "change_pct": None,
                    "hot_stock_score": 60.0,
                }])

            def _fetch_eastmoney_constituents(self, topic: str, *, source: str) -> Any:
                return pd.DataFrame()

            def _find_board_change(self, topic: str) -> Dict[str, Any]:
                return {}

            def _build_hotspot_route(self, topic: str, summary: Dict[str, Any]) -> Any:
                return [{"title": "fallback", "description": topic, "source": "test"}]

            def _fetch_ths_info(self, topic: str) -> Dict[str, str]:
                return {}

        with (
            patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
            patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", FakeProvider())),
        ):
            payload = self._hotspot_detail(config=config, provider="akshare", topic="AI算力")

        self.assertEqual(payload["enabled"], True)
        self.assertEqual(payload["provider"], "akshare")
        self.assertEqual(payload["topic"], "AI算力")
        self.assertEqual(payload["stocks"][0]["name"], "中际旭创")
        self.assertEqual(payload["route"][0]["title"], "fallback")

    def test_hotspot_provider_merges_constituent_sources_before_single_leader_fallback(self) -> None:
        import pandas as pd

        class FakeProvider(alphasift_service.DsaEastMoneyHotspotProvider):
            def _fetch_eastmoney_constituents(self, topic: str, *, source: str) -> Any:
                return pd.DataFrame([
                    {"代码": "000001", "名称": "平安银行", "涨跌幅": 1.2},
                    {"代码": "000002", "名称": "万科A", "涨跌幅": 0.8},
                ])

            def _fetch_ths_constituents(self, topic: str) -> Any:
                return pd.DataFrame([
                    {"code": "000002", "name": "万科A"},
                    {"code": "000003", "name": "国农科技"},
                ])

            def _fallback_constituents(self, topic: str) -> Any:
                return pd.DataFrame([{
                    "code": "000001",
                    "name": "平安银行",
                    "hot_stock_score": 60.0,
                }])

        provider = FakeProvider()
        frame = provider.stock_board_concept_cons_em("金融")

        self.assertEqual(list(frame["code"]), ["000001", "000002", "000003"])
        self.assertEqual(provider.stock_board_concept_cons_em("金融").shape[0], 3)

    def test_hotspot_provider_adds_related_metal_leaders_for_narrow_topic(self) -> None:
        import pandas as pd

        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        raw = pd.DataFrame([
            {
                "板块名称": "钼",
                "涨跌幅": 10.0,
                "板块异动最频繁个股及所属类型-股票代码": "001257",
                "板块异动最频繁个股及所属类型-股票名称": "盛龙股份",
            },
            {
                "板块名称": "钴",
                "涨跌幅": 5.9,
                "板块异动最频繁个股及所属类型-股票代码": "300618",
                "板块异动最频繁个股及所属类型-股票名称": "寒锐钴业",
            },
            {
                "板块名称": "铜",
                "涨跌幅": 7.0,
                "板块异动最频繁个股及所属类型-股票代码": "600362",
                "板块异动最频繁个股及所属类型-股票名称": "江西铜业",
            },
        ])
        with patch.object(provider, "_fetch_board_changes_raw", return_value=raw):
            frame = provider._related_hotspot_constituents("钼")

        self.assertEqual(list(frame["code"]), ["001257", "300618"])
        self.assertEqual(frame.iloc[0]["role"], "小金属活跃股")

    def test_hotspot_route_is_grouped_by_daily_markers(self) -> None:
        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider._fetch_ths_summary_event = MagicMock(return_value="2026-06-12：政策催化")
        summary = {
            "板块名称": "AI算力",
            "涨跌幅": 4.2,
            "板块异动总次数": 186,
            "板块异动最频繁个股及所属类型-股票名称": "中际旭创",
            "板块具体异动类型列表及出现次数": [{"t": 8203, "ct": 8}, {"t": 8204, "ct": 6}],
        }

        route = provider._build_hotspot_route("AI算力", summary)

        self.assertLessEqual(len(route), 2)
        self.assertEqual(route[0]["date"], datetime.now().date().isoformat())
        self.assertEqual(route[0]["published_at"], route[0]["date"])
        self.assertIn("当日结构", route[0]["description"])
        self.assertEqual(route[1]["date"], "2026-06-12")

    def test_hotspot_route_does_not_invent_metal_catalyst_hint(self) -> None:
        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        provider._fetch_ths_summary_event = MagicMock(return_value="")

        route = provider._build_hotspot_route("钼", {})

        self.assertEqual(route[0]["source"], "fallback")
        self.assertNotIn("以钼代钨", route[0]["description"])

    def test_hotspot_detail_uses_constituent_fallback_when_board_change_summary_fails(self) -> None:
        import pandas as pd

        config = self._config(enabled=True)

        class FakeProvider(alphasift_service.DsaEastMoneyHotspotProvider):
            def _find_board_change(self, topic: str) -> Dict[str, Any]:
                raise TimeoutError("board change timeout")

            def _fetch_ths_constituents(self, topic: str) -> Any:
                return pd.DataFrame()

            def _fetch_eastmoney_constituents(self, topic: str, *, source: str) -> Any:
                return pd.DataFrame([{
                    "代码": "002138",
                    "名称": "顺络电子",
                    "涨跌幅": 3.2,
                }])

            def _fetch_ths_summary_event(self, topic: str) -> str:
                return "需求升温"

            def _fetch_ths_info(self, topic: str) -> Dict[str, str]:
                return {}

        with (
            patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
            patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", FakeProvider())),
        ):
            payload = self._hotspot_detail(config=config, provider="akshare", topic="MLCC")

        self.assertEqual(payload["enabled"], True)
        self.assertEqual(payload["topic"], "MLCC")
        self.assertEqual(payload["summary"], "MLCC 当前暂无可用的板块异动摘要。")
        self.assertEqual(payload["route"][0]["source"], "ths_summary")
        self.assertEqual(payload["stocks"][0]["name"], "顺络电子")

    def test_hotspot_detail_uses_industry_constituents_for_industry_hotspots(self) -> None:
        import pandas as pd

        config = self._config(enabled=True)

        class FakeProvider(alphasift_service.DsaEastMoneyHotspotProvider):
            def __init__(self) -> None:
                self.constituent_sources = []

            def stock_board_industry_name_em(self) -> Any:
                return pd.DataFrame([{"name": "电池", "rank": 1}])

            def _fetch_eastmoney_constituents(self, topic: str, *, source: str) -> Any:
                self.constituent_sources.append(source)
                if source == "industry":
                    return pd.DataFrame([{
                        "代码": "300750",
                        "名称": "宁德时代",
                        "涨跌幅": 2.6,
                    }])
                return pd.DataFrame()

            def _fetch_ths_constituents(self, topic: str) -> Any:
                raise AssertionError("industry hotspots must not use concept constituents")

            def _find_board_change(self, topic: str) -> Dict[str, Any]:
                return {}

            def _fetch_ths_summary_event(self, topic: str) -> str:
                return ""

            def _fetch_ths_info(self, topic: str) -> Dict[str, str]:
                return {}

        provider = FakeProvider()
        with (
            patch("src.services.alphasift_service._get_alphasift_status_snapshot", return_value=({}, True, {})),
            patch("src.services.alphasift_service._resolve_hotspot_provider", return_value=("akshare", provider)),
        ):
            payload = self._hotspot_detail(config=config, provider="akshare", topic="电池")

        self.assertEqual(payload["enabled"], True)
        self.assertEqual(payload["topic"], "电池")
        self.assertEqual(payload["stocks"][0]["name"], "宁德时代")
        self.assertEqual(provider.constituent_sources, ["industry"])

    def test_hotspot_provider_uses_board_name_fallback_when_rankings_fail(self) -> None:
        import pandas as pd

        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        fallback = pd.DataFrame([{"板块名称": "玻璃基板", "涨跌幅": 1.8, "序号": 1}])
        with (
            patch.object(provider, "_fetch_board_changes", return_value=pd.DataFrame()),
            patch.object(provider, "_fetch_rankings", side_effect=RuntimeError("ranking schema changed")),
            patch.object(provider, "_fetch_board_names", return_value=fallback) as fetch_board_names,
        ):
            concept = provider.stock_board_concept_name_em()
            industry = provider.stock_board_industry_name_em()

        self.assertEqual(concept.iloc[0]["板块名称"], "玻璃基板")
        self.assertEqual(industry.iloc[0]["板块名称"], "玻璃基板")
        fetch_board_names.assert_any_call(source_fs="m:90 t:3 f:!50")
        fetch_board_names.assert_any_call(source_fs="m:90 t:2 f:!50")

    def test_hotspot_provider_continues_fallback_when_board_change_fails(self) -> None:
        import pandas as pd

        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        rankings = pd.DataFrame([{"name": "减速器", "change_pct": 2.2, "rank": 1}])
        with (
            patch.object(provider, "_fetch_board_changes", side_effect=RuntimeError("akshare timeout")),
            patch.object(provider, "_fetch_rankings", return_value=rankings) as fetch_rankings,
        ):
            concept = provider.stock_board_concept_name_em()

        self.assertEqual(concept.iloc[0]["name"], "减速器")
        fetch_rankings.assert_called_once_with("concept")

    def test_hotspot_provider_derives_trend_metrics_from_board_changes(self) -> None:
        import pandas as pd

        board_changes = pd.DataFrame([
            {
                "板块名称": "AI算力",
                "涨跌幅": 4.2,
                "板块异动总次数": 186,
                "板块异动最频繁个股及所属类型-股票名称": "中际旭创",
            },
        ])

        class _MockAkshare:
            calls = 0

            @staticmethod
            def stock_board_change_em():
                _MockAkshare.calls += 1
                return board_changes

        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        with patch.dict("sys.modules", {"akshare": _MockAkshare()}):
            frame = provider._fetch_board_changes()
            summary = provider._find_board_change("AI算力")

        self.assertEqual(_MockAkshare.calls, 1)
        self.assertEqual(frame.iloc[0]["name"], "AI算力")
        self.assertEqual(frame.iloc[0]["stage"], "加速发酵")
        self.assertGreater(frame.iloc[0]["trend_score"], 0)
        self.assertGreater(frame.iloc[0]["persistence_score"], 0)
        self.assertEqual(frame.iloc[0]["sample_stock_count"], 1)
        self.assertEqual(frame.iloc[0]["leaders"], ["中际旭创"])
        self.assertEqual(summary["板块名称"], "AI算力")

    def test_fetch_ths_summary_event_ignores_missing_concept_name_column(self) -> None:
        import pandas as pd

        provider = alphasift_service.DsaEastMoneyHotspotProvider()
        summary = pd.DataFrame([
            {"日期": "2026-06-07", "驱动事件": "行业政策利好"},
        ])

        class _MockAkshare:
            @staticmethod
            def stock_board_concept_summary_ths():
                return summary

        with patch.dict("sys.modules", {"akshare": _MockAkshare()}):
            text = provider._fetch_ths_summary_event("MLCC")

        self.assertEqual(text, "")
