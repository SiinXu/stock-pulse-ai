# -*- coding: utf-8 -*-
"""AlphaSift availability, install, and task API contracts."""

from __future__ import annotations

from tests.alphasift_api_test_support import (
    os,
    sys,
    Path,
    tempfile,
    SimpleNamespace,
    MagicMock,
    patch,
    HTTPException,
    alphasift_endpoint,
    alphasift_service,
    TaskInfo,
    QueueTaskStatus,
    DEFAULT_ALPHASIFT_TEST_SPEC,
    PUBLIC_DIAGNOSTIC_SECRET,
    _make_adapter_module,
    _missing_alphasift_module_diagnostics,
    _AlphaSiftApiTestCaseBase,
)


class AlphaSiftOpportunitiesApiTestCase(_AlphaSiftApiTestCaseBase):
    def test_strategies_rejects_when_enabled_but_adapter_missing(self) -> None:
        config = self._config(enabled=True)

        with (
            patch(
                "src.services.alphasift_service._get_alphasift_status_snapshot",
                return_value=({}, False, _missing_alphasift_module_diagnostics()),
            ),
            patch("src.services.alphasift_service._install_alphasift") as install_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                self._strategies(config=config)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_unavailable")
        self.assertEqual(caught.exception.detail.get("diagnostics", {}).get("reason"), "missing_module")
        install_mock.assert_not_called()

    def test_screen_rejects_when_disabled(self) -> None:
        config = self._config(enabled=False)

        with self.assertRaises(HTTPException) as caught:
            self._screen(config)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail["error"], "alphasift_disabled")

    def test_screen_rejects_when_alphasift_unavailable(self) -> None:
        config = self._config(enabled=True)

        with (
            patch(
                "src.services.alphasift_service._get_alphasift_status_snapshot",
                return_value=({}, False, _missing_alphasift_module_diagnostics()),
            ),
            patch("src.services.alphasift_service._install_alphasift") as install_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_unavailable")
        self.assertEqual(caught.exception.detail.get("diagnostics", {}).get("reason"), "missing_module")
        for expected in (
            "python -m pip install --upgrade --constraint constraints.txt pip",
            "python -m pip install --build-constraint build-constraints.txt -r requirements.txt",
            "python -m pip check",
        ):
            self.assertIn(expected, caught.exception.detail["message"])
        install_mock.assert_not_called()

    def test_start_screen_task_submits_background_work(self) -> None:
        config = self._config(enabled=True)
        fake_queue = MagicMock()
        fake_queue.submit_background_task.return_value = SimpleNamespace(
            task_id="screen-task-1",
            trace_id="screen-task-1",
            status=QueueTaskStatus.PENDING,
            message="AlphaSift 选股任务已提交",
        )

        with (
            patch("api.v1.endpoints.alphasift.get_task_queue", return_value=fake_queue),
            patch("api.v1.endpoints.alphasift.uuid.uuid4", return_value=SimpleNamespace(hex="screen-task-1")),
            patch.object(
                alphasift_endpoint.AlphaSiftService,
                "screen",
                return_value={"enabled": True, "candidates": [], "candidate_count": 0},
            ) as screen_mock,
        ):
            payload = alphasift_endpoint.alphasift_start_screen_task(
                alphasift_endpoint.AlphaSiftScreenRequest(market="cn", strategy="dual_low", max_results=3),
                http_request=self._request(),
                config=config,
            )
            run_task = fake_queue.submit_background_task.call_args.args[0]
            result = run_task()

        self.assertEqual(payload.task_id, "screen-task-1")
        self.assertEqual(payload.max_results, 3)
        fake_queue.submit_background_task.assert_called_once()
        self.assertEqual(fake_queue.submit_background_task.call_args.kwargs["report_type"], "alphasift_screen")
        self.assertEqual(
            fake_queue.submit_background_task.call_args.kwargs["failure_error_code"],
            "alphasift_screen_failed",
        )
        screen_mock.assert_called_once_with(strategy="dual_low", market="cn", max_results=3)
        self.assertEqual(result["candidate_count"], 0)
        fake_queue.update_task_progress.assert_any_call(
            "screen-task-1",
            20,
            "正在执行 AlphaSift 选股，外部数据源较慢时会持续后台运行",
        )

    def test_screen_task_status_returns_alphasift_result(self) -> None:
        task = TaskInfo(
            task_id="screen-task-1",
            trace_id="screen-task-1",
            stock_code="alphasift_screen",
            status=QueueTaskStatus.COMPLETED,
            progress=100,
            message="任务执行完成",
            result={"enabled": True, "candidates": [], "candidate_count": 0},
            report_type="alphasift_screen",
        )
        fake_queue = MagicMock()
        fake_queue.get_task.return_value = task

        with patch("api.v1.endpoints.alphasift.get_task_queue", return_value=fake_queue):
            payload = alphasift_endpoint.alphasift_screen_task_status("screen-task-1")

        self.assertEqual(payload.status, "completed")
        self.assertEqual(payload.result["candidate_count"], 0)

    def test_screen_task_status_does_not_expose_legacy_diagnostic_text(self) -> None:
        secret_marker = "Authorization: Bearer sk-alphasift-secret-marker"
        task = TaskInfo(
            task_id="screen-task-failed",
            trace_id="trace-screen-task-failed",
            stock_code="alphasift_screen",
            status=QueueTaskStatus.FAILED,
            progress=40,
            message=f"任务失败: {secret_marker}",
            message_code="task.failed",
            error=secret_marker,
            diagnostic_error=secret_marker,
            failure_error_code="alphasift_screen_failed",
            report_type="alphasift_screen",
        )
        fake_queue = MagicMock()
        fake_queue.get_task.return_value = task

        with patch("api.v1.endpoints.alphasift.get_task_queue", return_value=fake_queue):
            payload = alphasift_endpoint.alphasift_screen_task_status(task.task_id)

        self.assertEqual(payload.error, "alphasift_screen_failed")
        self.assertEqual(payload.message, "任务执行失败")
        self.assertNotIn(secret_marker, payload.model_dump_json())

    def test_screen_task_status_rejects_non_alphasift_task(self) -> None:
        task = TaskInfo(
            task_id="analysis-task-1",
            stock_code="600519",
            status=QueueTaskStatus.COMPLETED,
            report_type="detailed",
        )
        fake_queue = MagicMock()
        fake_queue.get_task.return_value = task

        with patch("api.v1.endpoints.alphasift.get_task_queue", return_value=fake_queue):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_screen_task_status("analysis-task-1")

        self.assertEqual(caught.exception.status_code, 404)
        self.assertEqual(caught.exception.detail["error"], "alphasift_screen_task_not_found")

    def test_screen_does_not_auto_install_when_adapter_runtime_unavailable(self) -> None:
        config = self._config(enabled=True)

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch(
                "src.services.alphasift_service._get_alphasift_status_snapshot",
                return_value=(
                    {},
                    False,
                    {"reason": "unexpected_exception", "stage": "get_status", "error_type": "RuntimeError"},
                ),
            ),
            patch("src.services.alphasift_service._install_alphasift") as install_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                self._screen(config)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_unavailable")
        self.assertEqual(caught.exception.detail.get("diagnostics", {}).get("resolution"), "no_auto_install")
        self.assertEqual(
            caught.exception.detail.get("diagnostics", {}).get("message"),
            "请先检查后端日志并修复运行时异常，当前未触发修复安装。",
        )
        install_mock.assert_not_called()

    def test_install_rejects_spoofed_localhost_without_admin_session(self) -> None:
        config = self._config(enabled=True)
        request = SimpleNamespace(
            cookies={alphasift_service.COOKIE_NAME: "invalid-session"},
            url=SimpleNamespace(hostname="localhost"),
            client=SimpleNamespace(host="127.0.0.1"),
        )

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "false"}, clear=False),
            patch("src.services.alphasift_service.refresh_auth_state") as refresh_mock,
            patch("src.services.alphasift_service.is_auth_enabled", return_value=True),
            patch("src.services.alphasift_service.verify_session", return_value=False) as verify_session_mock,
            patch("src.services.alphasift_service.subprocess.run") as run_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=request, config=config)

        self.assertEqual(caught.exception.status_code, 401)
        self.assertEqual(caught.exception.detail["error"], "alphasift_install_access_denied")
        refresh_mock.assert_called_once()
        verify_session_mock.assert_called_once_with("invalid-session")
        run_mock.assert_not_called()

    def test_install_allows_valid_admin_session_outside_desktop_mode(self) -> None:
        config = self._config(enabled=True)
        request = self._request({alphasift_service.COOKIE_NAME: "valid-session"})

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "false"}, clear=False),
            patch("src.services.alphasift_service.refresh_auth_state") as refresh_mock,
            patch("src.services.alphasift_service.is_auth_enabled", return_value=True),
            patch("src.services.alphasift_service.verify_session", return_value=True) as verify_session_mock,
            patch("src.services.alphasift_service._install_alphasift", return_value={"installed": True}) as install_mock,
        ):
            payload = alphasift_endpoint.alphasift_install(request=request, config=config)

        self.assertEqual(payload["installed"], True)
        refresh_mock.assert_called_once()
        verify_session_mock.assert_called_once_with("valid-session")
        install_mock.assert_called_once_with(config)

    def test_install_rejects_when_disabled_without_side_effects(self) -> None:
        config = self._config(enabled=False)

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch("src.services.alphasift_service.subprocess.run") as run_mock,
            patch("src.services.alphasift_service._import_alphasift") as import_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail["error"], "alphasift_disabled")
        import_mock.assert_not_called()
        run_mock.assert_not_called()

    def test_install_invokes_pip_when_enabled_and_missing(self) -> None:
        config = self._config(enabled=True)
        completed = SimpleNamespace(returncode=0, stdout="installed", stderr="")

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch("src.services.alphasift_service._is_alphasift_available", side_effect=[False, True]),
            patch(
                "src.services.alphasift_service._call_alphasift_status",
                return_value={"available": True, "supported_markets": ["cn"], "contract_version": "1", "version": "0.2.0", "strategy_count": 1},
            ),
            patch("src.services.alphasift_service.subprocess.run", return_value=completed) as run_mock,
            patch("src.services.alphasift_service._get_dsa_adapter", return_value=_make_adapter_module()),
        ):
            payload = alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(payload["installed"], True)
        self.assertEqual(payload["already_installed"], False)
        self.assertEqual(payload["install_spec_is_default"], True)
        self.assertNotIn("install_spec", payload)
        run_mock.assert_called_once()
        install_command = run_mock.call_args.args[0]
        repo_root = Path(alphasift_service.__file__).resolve().parents[2]
        constraint_path = str(repo_root / "constraints.txt")
        build_constraint_path = str(repo_root / "build-constraints.txt")
        self.assertEqual(
            install_command,
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--force-reinstall",
                "--no-deps",
                "--constraint",
                constraint_path,
                "--build-constraint",
                build_constraint_path,
                DEFAULT_ALPHASIFT_TEST_SPEC,
            ],
        )
        # Dependency-isolation boundary: --no-deps blocks transitive resolution and both
        # constraint flags resolve to the committed lock files on disk.
        self.assertIn("--no-deps", install_command)
        self.assertTrue((repo_root / "constraints.txt").is_file())
        self.assertTrue((repo_root / "build-constraints.txt").is_file())

    def test_install_degrades_to_no_deps_when_lock_files_absent(self) -> None:
        # Packaged desktop artifacts do not ship constraints.txt / build-constraints.txt.
        # Repair must still run (unchanged user-facing behavior) while --no-deps keeps the
        # dependency-isolation boundary intact.
        config = self._config(enabled=True)
        completed = SimpleNamespace(returncode=0, stdout="installed", stderr="")

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch("src.services.alphasift_service._is_alphasift_available", side_effect=[False, True]),
            patch(
                "src.services.alphasift_service._call_alphasift_status",
                return_value={"available": True, "supported_markets": ["cn"], "contract_version": "1", "version": "0.2.0", "strategy_count": 1},
            ),
            # Simulate the packaged desktop artifact: no constraints.txt / build-constraints.txt
            # exists above the runtime file, so the constraint flags are omitted.
            patch("pathlib.Path.is_file", return_value=False),
            patch("src.services.alphasift_service.subprocess.run", return_value=completed) as run_mock,
            patch("src.services.alphasift_service._get_dsa_adapter", return_value=_make_adapter_module()),
        ):
            payload = alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(payload["installed"], True)
        run_mock.assert_called_once()
        install_command = run_mock.call_args.args[0]
        self.assertEqual(
            install_command,
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--upgrade",
                "--force-reinstall",
                "--no-deps",
                DEFAULT_ALPHASIFT_TEST_SPEC,
            ],
        )
        self.assertIn("--no-deps", install_command)
        self.assertNotIn("--constraint", install_command)
        self.assertNotIn("--build-constraint", install_command)

    def test_install_uses_bundled_lock_when_frozen(self) -> None:
        # A PyInstaller desktop build bundles the lock files at sys._MEIPASS. The repair
        # install must pin against the bundled copy instead of degrading to --no-deps only.
        config = self._config(enabled=True)
        completed = SimpleNamespace(returncode=0, stdout="installed", stderr="")

        with tempfile.TemporaryDirectory() as bundle:
            (Path(bundle) / "constraints.txt").write_text("", encoding="utf-8")
            (Path(bundle) / "build-constraints.txt").write_text("", encoding="utf-8")
            with (
                patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
                patch("src.services.alphasift_service._is_alphasift_available", side_effect=[False, True]),
                patch(
                    "src.services.alphasift_service._call_alphasift_status",
                    return_value={"available": True, "supported_markets": ["cn"], "contract_version": "1", "version": "0.2.0", "strategy_count": 1},
                ),
                patch.object(sys, "_MEIPASS", bundle, create=True),
                patch("src.services.alphasift_service.subprocess.run", return_value=completed) as run_mock,
                patch("src.services.alphasift_service._get_dsa_adapter", return_value=_make_adapter_module()),
            ):
                payload = alphasift_endpoint.alphasift_install(request=self._request(), config=config)

            self.assertEqual(payload["installed"], True)
            run_mock.assert_called_once()
            install_command = run_mock.call_args.args[0]
            self.assertEqual(
                install_command,
                [
                    sys.executable,
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "--force-reinstall",
                    "--no-deps",
                    "--constraint",
                    str(Path(bundle) / "constraints.txt"),
                    "--build-constraint",
                    str(Path(bundle) / "build-constraints.txt"),
                    DEFAULT_ALPHASIFT_TEST_SPEC,
                ],
            )

    def test_install_start_failure_hides_raw_diagnostic(self) -> None:
        config = self._config(enabled=True)

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch("src.services.alphasift_service._is_alphasift_available", return_value=False),
            patch("src.services.alphasift_service.subprocess.run", side_effect=RuntimeError(PUBLIC_DIAGNOSTIC_SECRET)),
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(caught.exception.detail["error"], "alphasift_install_failed")
        self.assertEqual(caught.exception.detail["message"], "修复安装 AlphaSift 失败，请检查后端日志。")
        self.assert_public_payload_is_private(caught.exception.detail)

    def test_install_command_failure_hides_raw_diagnostic(self) -> None:
        config = self._config(enabled=True)
        completed = SimpleNamespace(returncode=1, stdout="", stderr=PUBLIC_DIAGNOSTIC_SECRET)

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch("src.services.alphasift_service._is_alphasift_available", return_value=False),
            patch("src.services.alphasift_service.subprocess.run", return_value=completed),
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(caught.exception.detail["error"], "alphasift_install_failed")
        self.assertEqual(caught.exception.detail["message"], "修复安装 AlphaSift 失败，请检查后端日志。")
        self.assert_public_payload_is_private(caught.exception.detail)

    def test_install_rejects_when_alphasift_adapter_reports_unavailable(self) -> None:
        config = self._config(enabled=True)
        completed = SimpleNamespace(returncode=0, stdout="installed", stderr="")

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch(
                "src.services.alphasift_service._call_alphasift_status",
                side_effect=[
                    {"available": False},
                    {"available": False},
                ],
            ),
            patch("src.services.alphasift_service.subprocess.run", return_value=completed) as run_mock,
            patch("src.services.alphasift_service._get_dsa_adapter") as get_adapter_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(caught.exception.status_code, 424)
        self.assertEqual(caught.exception.detail["error"], "alphasift_unavailable")
        run_mock.assert_called_once()
        get_adapter_mock.assert_not_called()

    def test_install_rejects_untrusted_spec(self) -> None:
        config = self._config(enabled=True, install_spec="git+https://example.com/private/alphasift.git")

        with (
            patch.dict(os.environ, {"DSA_DESKTOP_MODE": "true"}, clear=False),
            patch("src.services.alphasift_service._is_alphasift_available", return_value=False),
            patch("src.services.alphasift_service.subprocess.run") as run_mock,
        ):
            with self.assertRaises(HTTPException) as caught:
                alphasift_endpoint.alphasift_install(request=self._request(), config=config)

        self.assertEqual(caught.exception.status_code, 403)
        self.assertEqual(caught.exception.detail["error"], "alphasift_install_spec_not_allowed")
        run_mock.assert_not_called()
