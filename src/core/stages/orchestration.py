# -*- coding: utf-8 -*-
"""Runtime orchestration stages for the stock analysis pipeline."""

import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextvars import ContextVar
from datetime import date, datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

from data_provider.base import normalize_stock_code
from src.analyzer import AnalysisResult
from src.core.pipeline_stage_results import (
    PipelineStageName,
    PipelineStageResult,
    PipelineStageRunner,
)
from src.core.trading_calendar import (
    get_effective_trading_date,
    get_market_for_stock,
)
from src.enums import ReportType
from src.services.run_diagnostics import (
    PIPELINE_STAGE_NAMES,
    PipelineStageObservation,
    activate_run_diagnostic_context,
    get_current_diagnostic_context,
    observe_pipeline_stage,
    record_missing_pipeline_stages_as_skipped,
    record_pipeline_stage,
    reset_run_diagnostic_context,
)
from src.utils.sanitize import log_safe_exception


logger = logging.getLogger("src.core.pipeline")
_PIPELINE_STAGE_RUNNER_INIT_GUARD = threading.Lock()
_DEFER_PIPELINE_DELIVERY_OBSERVATION: ContextVar[bool] = ContextVar(
    "defer_pipeline_delivery_observation",
    default=False,
)


class _OrchestrationStageMixin:
    """Provide runtime stage execution and batch orchestration."""

    def _emit_progress(self, progress: int, message: str) -> None:
        """Best-effort bridge from pipeline stages to task SSE progress."""
        callback = getattr(self, "progress_callback", None)
        if callback is None:
            return
        try:
            callback(progress, message)
        except Exception as exc:  # broad-exception: fallback_recorded - Progress callback failures are logged and cannot interrupt pipeline execution.
            query_id = getattr(self, "query_id", None)
            log_safe_exception(
                logger,
                "Pipeline progress callback failed",
                exc,
                error_code="pipeline_progress_callback_failed",
                level=logging.WARNING,
                context={"progress": progress, "query_id": query_id},
            )

    def _get_pipeline_stage_runner(self) -> PipelineStageRunner:
        """Return the request-scoped runner, including for lightweight test instances."""
        runner = getattr(self, "_pipeline_stage_runner", None)
        if isinstance(runner, PipelineStageRunner):
            return runner
        with _PIPELINE_STAGE_RUNNER_INIT_GUARD:
            runner = getattr(self, "_pipeline_stage_runner", None)
            if not isinstance(runner, PipelineStageRunner):
                runner = PipelineStageRunner()
                self._pipeline_stage_runner = runner
        return runner

    def _run_pipeline_stage(
        self,
        stage: PipelineStageName,
        operation: Callable[[], Any],
        *,
        retryable: bool = False,
        side_effect_key: Optional[Any] = None,
    ) -> PipelineStageResult[Any]:
        """Execute one stage through the typed result and retry-fence contract."""
        return self._get_pipeline_stage_runner().run(
            stage,
            operation,
            retryable=retryable,
            side_effect_key=side_effect_key,
        )

    def _finish_pipeline_stage(
        self,
        observation: PipelineStageObservation,
        result: PipelineStageResult[Any],
        *,
        output_summary: Optional[Dict[str, Any]] = None,
    ) -> PipelineStageResult[Any]:
        """Record a typed result through the existing diagnostic observation."""
        self._get_pipeline_stage_runner().record(result)
        observation.finish(
            status=result.status.value,
            output_summary=output_summary,
            degradation_reason=result.degradation_reason,
            retryable=result.retryable,
            error=result.error,
        )
        return result

    def _record_pipeline_stage_result(
        self,
        result: PipelineStageResult[Any],
        *,
        input_summary: Optional[Dict[str, Any]] = None,
        output_summary: Optional[Dict[str, Any]] = None,
    ) -> PipelineStageResult[Any]:
        """Record a typed result for a stage without an active timer."""
        self._get_pipeline_stage_runner().record(result)
        record_pipeline_stage(
            stage=result.stage.value,
            status=result.status.value,
            input_summary=input_summary,
            output_summary=output_summary,
            degradation_reason=result.degradation_reason,
            retryable=result.retryable,
            error_type=(
                type(result.error).__name__
                if result.error is not None
                else None
            ),
            error_message=result.error,
        )
        return result

    def fetch_and_save_stock_data(
        self,
        code: str,
        force_refresh: bool = False,
        current_time: Optional[datetime] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        获取并保存单只股票数据
\x20\x20\x20\x20\x20\x20\x20\x20
        断点续传逻辑：
        1. 检查数据库是否已有最新可复用交易日数据
        2. 如果有且不强制刷新，则跳过网络请求
        3. 否则从数据源获取并保存
\x20\x20\x20\x20\x20\x20\x20\x20
        Args:
            code: 股票代码
            force_refresh: 是否强制刷新（忽略本地缓存）
            current_time: 本轮运行冻结的参考时间，用于统一断点续传目标交易日判断
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
        Returns:
            Tuple[是否成功, 错误信息]
        """
        stock_name = code
        try:
            # 首先获取股票名称
            stock_name = self.fetcher_manager.get_stock_name(code, allow_realtime=False)

            target_date = self._resolve_resume_target_date(
                code, current_time=current_time
            )

            # 断点续传检查：如果最新可复用交易日的数据已存在，则跳过
            if not force_refresh and self.db.has_today_data(code, target_date):
                logger.info(
                    "%s(%s) already has data for %s; skipping fetch for resumability",
                    stock_name,
                    code,
                    target_date,
                )
                return True, None

            # 从数据源获取数据
            logger.info("%s(%s) fetching market data", stock_name, code)
            df, source_name = self.fetcher_manager.get_daily_data(code, days=30)

            if df is None or df.empty:
                return False, "获取数据为空"

            # 保存到数据库
            saved_count = self.db.save_daily_data(df, code, source_name)
            logger.info(
                "%s(%s) market data saved: source=%s rows_added=%s",
                stock_name,
                code,
                source_name,
                saved_count,
            )

            return True, None

        except Exception as e:  # broad-exception: fallback_recorded - Market-data failures are logged and returned as stage failure details.
            error_msg = f"获取/保存数据失败: {str(e)}"
            log_safe_exception(
                logger,
                "Market data fetch or persistence failed",
                e,
                error_code="pipeline_market_data_fetch_or_save_failed",
                context={"stock_code": code},
            )
            return False, error_msg

    @staticmethod
    def _resolve_resume_target_date(
        code: str, current_time: Optional[datetime] = None
    ) -> date:
        """
        Resolve the trading date used by checkpoint/resume checks.
        """
        market = get_market_for_stock(normalize_stock_code(code))
        return get_effective_trading_date(market, current_time=current_time)

    def _resolve_query_source(self, query_source: Optional[str] = None) -> str:
        """Resolve the request source using explicit, Bot, Web, then system precedence.

        An explicit source wins. Otherwise an application request context identifies
        a Bot request, a query id identifies a Web request, and all other calls are
        classified as system work.
        """
        if query_source:
            return query_source
        if getattr(self, "request_context", None):
            return "bot"
        if getattr(self, "query_id", None):
            return "web"
        return "system"

    def process_single_stock(
        self,
        code: str,
        skip_analysis: bool = False,
        single_stock_notify: bool = False,
        report_type: ReportType = ReportType.SIMPLE,
        analysis_query_id: Optional[str] = None,
        current_time: Optional[datetime] = None,
    ) -> Optional[AnalysisResult]:
        """
        处理单只股票的完整流程

        包括：
        1. 获取数据
        2. 保存数据
        3. AI 分析
        4. 单股推送（可选，#55）

        此方法会被线程池调用，需要处理好异常

        Args:
            analysis_query_id: 查询链路关联 id
            code: 股票代码
            skip_analysis: 是否跳过 AI 分析
            single_stock_notify: 是否启用单股推送模式（每分析完一只立即推送）
            report_type: 报告类型枚举（从配置读取，Issue #119）
            current_time: 本轮运行冻结的参考时间，用于统一断点续传目标交易日判断

        Returns:
            AnalysisResult 或 None
        """
        logger.info("========== Processing %s ==========", code)

        from src.services.history_loader import set_frozen_target_date, reset_frozen_target_date
        effective_query_id = analysis_query_id or getattr(self, "query_id", None) or uuid.uuid4().hex
        effective_trace_id = getattr(self, "trace_id", None) or effective_query_id
        diag_token = None
        frozen_target_token = None
        if get_current_diagnostic_context() is None:
            diag_token = activate_run_diagnostic_context(
                trace_id=effective_trace_id,
                query_id=effective_query_id,
                stock_code=code,
                trigger_source=getattr(self, "query_source", None),
            )
        try:
            with observe_pipeline_stage(
                "resolve",
                input_summary={
                    "stock_code": code,
                    "query_source": getattr(self, "query_source", None),
                },
                retryable=False,
            ) as resolve_stage:
                def _resolve_target() -> Tuple[date, Any]:
                    target_date = self._resolve_resume_target_date(
                        code,
                        current_time=current_time,
                    )
                    return target_date, set_frozen_target_date(target_date)

                resolve_result = self._run_pipeline_stage(
                    PipelineStageName.RESOLVE,
                    _resolve_target,
                    retryable=False,
                )
                resolved_value = resolve_result.value
                self._finish_pipeline_stage(
                    resolve_stage,
                    resolve_result,
                    output_summary=(
                        {
                            "query_id": effective_query_id,
                            "target_date": resolved_value[0].isoformat(),
                        }
                        if resolved_value is not None
                        else None
                    ),
                )
                frozen_td, frozen_target_token = resolve_result.unwrap()
        except Exception:
            record_missing_pipeline_stages_as_skipped(
                PIPELINE_STAGE_NAMES,
                input_summary={"stock_code": code},
                reason="stock_resolution_failed",
            )
            reset_run_diagnostic_context(diag_token)
            if frozen_target_token is not None:
                reset_frozen_target_date(frozen_target_token)
            raise

        try:
            self._emit_progress(12, f"{code}：正在准备分析任务")
            # Step 1: 获取并保存数据
            with observe_pipeline_stage(
                "fetch",
                input_summary={
                    "stock_code": code,
                    "operation": "prepare_daily_data",
                    "force_refresh": False,
                },
                retryable=True,
            ) as fetch_stage:
                def _prepare_daily_data() -> PipelineStageResult[Any]:
                    stage_value = self.fetch_and_save_stock_data(
                        code,
                        current_time=current_time,
                    )
                    data_ready, stage_error = stage_value
                    if data_ready:
                        return PipelineStageResult.success(
                            PipelineStageName.FETCH,
                            stage_value,
                        )
                    return PipelineStageResult.degraded(
                        PipelineStageName.FETCH,
                        stage_value,
                        reason=stage_error,
                        retryable=True,
                    )

                fetch_result = self._run_pipeline_stage(
                    PipelineStageName.FETCH,
                    _prepare_daily_data,
                    retryable=True,
                )
                fetch_value = fetch_result.value
                self._finish_pipeline_stage(
                    fetch_stage,
                    fetch_result,
                    output_summary={
                        "data_ready": bool(fetch_value and fetch_value[0]),
                    },
                )
                success, error = fetch_result.unwrap()

            if not success:
                logger.warning("[%s] Market data preparation failed", code)
                # 即使获取失败，也尝试用已有数据分析
            else:
                self._emit_progress(16, f"{code}：行情数据准备完成")

            # Step 2: AI 分析
            if skip_analysis:
                logger.info("[%s] Skipping AI analysis in dry-run mode", code)
                for stage_name in (
                    "intelligence",
                    "context",
                    "analyze",
                    "persist",
                    "render",
                    "dispatch",
                ):
                    self._record_pipeline_stage_result(
                        PipelineStageResult.skipped(
                            PipelineStageName(stage_name),
                            reason="analysis_disabled",
                        ),
                        input_summary={
                            "stock_code": code,
                            "mode": "dry_run",
                        },
                        output_summary={"reason": "analysis_disabled"},
                    )
                return None

            analyze_kwargs = {"query_id": effective_query_id}
            if current_time is not None:
                analyze_kwargs["current_time"] = current_time
            result = self.analyze_stock(code, report_type, **analyze_kwargs)

            if result and result.success:
                logger.info(
                    "[%s] Analysis completed: sentiment_score=%s",
                    code,
                    result.sentiment_score,
                )

                # 单股推送模式（#55）：每分析完一只股票立即推送
                if single_stock_notify:
                    self._send_single_stock_notification(
                        result,
                        report_type=report_type,
                        fallback_code=code,
                    )
            elif result:
                logger.warning("[%s] Analysis returned an unsuccessful result", code)

            missing_stage_count = 0
            if result and result.success:
                if (
                    not single_stock_notify
                    and not _DEFER_PIPELINE_DELIVERY_OBSERVATION.get()
                ):
                    missing_stage_count = record_missing_pipeline_stages_as_skipped(
                        ("render", "dispatch"),
                        input_summary={"stock_code": code},
                        reason="stock_delivery_not_requested",
                    )
            else:
                missing_stage_count = record_missing_pipeline_stages_as_skipped(
                    (
                        "intelligence",
                        "context",
                        "analyze",
                        "persist",
                        "render",
                        "dispatch",
                    ),
                    input_summary={"stock_code": code},
                    reason="analysis_unsuccessful",
                )
            if missing_stage_count and result and result.success:
                self._refresh_saved_diagnostic_snapshot(
                    result=result,
                    fallback_code=code,
                )

            return result

        except Exception as e:  # broad-exception: fallback_recorded - Per-stock failures are safely logged so the batch can continue.
            # 捕获所有异常，确保单股失败不影响整体
            record_missing_pipeline_stages_as_skipped(
                PIPELINE_STAGE_NAMES,
                input_summary={"stock_code": code},
                reason="stock_processing_failed",
            )
            log_safe_exception(
                logger,
                "Stock processing failed",
                e,
                error_code="pipeline_stock_processing_failed",
                context={"stock_code": code},
            )
            return None
        finally:
            reset_run_diagnostic_context(diag_token)
            if frozen_target_token is not None:
                reset_frozen_target_date(frozen_target_token)

    def _process_single_stock_for_batch(
        self,
        code: str,
        **kwargs,
    ) -> Optional[AnalysisResult]:
        """Run one stock while deferring delivery observations to the batch trace."""
        token = _DEFER_PIPELINE_DELIVERY_OBSERVATION.set(True)
        try:
            return self.process_single_stock(code, **kwargs)
        finally:
            _DEFER_PIPELINE_DELIVERY_OBSERVATION.reset(token)

    def run(
        self,
        stock_codes: Optional[List[str]] = None,
        dry_run: bool = False,
        send_notification: bool = True,
        merge_notification: bool = False,
        current_time: Optional[datetime] = None,
    ) -> List[AnalysisResult]:
        """
        运行完整的分析流程

        流程：
        1. 获取待分析的股票列表
        2. 使用线程池并发处理
        3. 收集分析结果
        4. 发送通知

        Args:
            stock_codes: 股票代码列表（可选，默认使用配置中的自选股）
            dry_run: 是否仅获取数据不分析
            send_notification: 是否发送推送通知
            merge_notification: 是否合并推送（跳过本次推送，由 main 层合并个股+大盘后统一发送，Issue #190）
            current_time: 本轮运行冻结的参考时间；为空时在 run 内生成

        Returns:
            分析结果列表
        """
        start_time = time.time()

        # 使用配置中的股票列表
        if stock_codes is None:
            self.config.refresh_stock_list()
            stock_codes = self.config.stock_list

        if not stock_codes:
            logger.error("No watchlist is configured; set STOCK_LIST in the environment file")
            return []

        logger.info("===== Starting analysis for %s stocks =====", len(stock_codes))
        logger.info("Stock list: %s", ", ".join(stock_codes))
        logger.info(
            "Concurrency=%s mode=%s",
            self.max_workers,
            "data-only" if dry_run else "full-analysis",
        )

        # 冻结本轮运行的统一参考时间，避免跨市场收盘边界时同批股票使用不同目标交易日。
        resume_reference_time = current_time or datetime.now(timezone.utc)

        # === 批量预取实时行情（优化：避免每只股票都触发全量拉取）===
        # 只有股票数量 >= 5 时才进行预取，少量股票直接逐个查询更高效
        if len(stock_codes) >= 5:
            daily_prefetch_count = self.fetcher_manager.prefetch_daily_klines(stock_codes, days=30)
            if daily_prefetch_count > 0:
                logger.info(
                    "[prefetch] component=daily_kline_prefetch action=complete "
                    "provider=TickFlowFetcher cached=%d stock_count=%d",
                    daily_prefetch_count,
                    len(stock_codes),
                )

            prefetch_count = self.fetcher_manager.prefetch_realtime_quotes(stock_codes)
            if prefetch_count > 0:
                logger.info(
                    "Bulk realtime prefetch enabled: stock_count=%s cache_entries=%s",
                    len(stock_codes),
                    prefetch_count,
                )

        # Issue #455: 预取股票名称，避免并发分析时显示「股票xxxxx」
        # dry_run 仅做数据拉取，不需要名称预取，避免额外网络开销
        if not dry_run:
            self.fetcher_manager.prefetch_stock_names(stock_codes, use_bulk=False)

        # 单股推送模式（#55）：从配置读取
        single_stock_notify = getattr(self.config, 'single_stock_notify', False)
        # Issue #119: 从配置读取报告类型
        report_type_str = getattr(self.config, 'report_type', 'simple').lower()
        if report_type_str == 'brief':
            report_type = ReportType.BRIEF
        elif report_type_str == 'full':
            report_type = ReportType.FULL
        else:
            report_type = ReportType.SIMPLE
        # Issue #128: 从配置读取分析间隔
        analysis_delay = getattr(self.config, 'analysis_delay', 0)

        if single_stock_notify:
            logger.info(
                "Single-stock notification mode enabled; analysis remains concurrent and "
                "notifications are serialized while collecting results: report_type=%s",
                report_type_str,
            )

        results: List[AnalysisResult] = []

        # 使用线程池并发处理
        # 注意：max_workers 设置较低（默认3）以避免触发反爬
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # 提交任务
            future_to_code = {
                executor.submit(
                    self._process_single_stock_for_batch,
                    code,
                    skip_analysis=dry_run,
                    single_stock_notify=False,
                    report_type=report_type,  # Issue #119: 传递报告类型
                    analysis_query_id=uuid.uuid4().hex,
                    current_time=resume_reference_time,
                ): code
                for code in stock_codes
            }

            # 收集结果
            for idx, future in enumerate(as_completed(future_to_code)):
                code = future_to_code[future]
                try:
                    result = future.result()
                    if result and result.success:
                        results.append(result)
                        if single_stock_notify and send_notification and not dry_run:
                            delivery_diag_token = (
                                self._activate_delivery_diagnostic_context([result])
                            )
                            try:
                                self._send_single_stock_notification(
                                    result,
                                    report_type=report_type,
                                    fallback_code=code,
                                )
                            finally:
                                reset_run_diagnostic_context(delivery_diag_token)
                    elif result and not result.success:
                        logger.warning(
                            "[%s] Unsuccessful analysis result excluded from aggregate output",
                            code,
                        )

                    # Issue #128: 分析间隔 - 在个股分析和大盘分析之间添加延迟
                    if idx < len(stock_codes) - 1 and analysis_delay > 0:
                        # 注意：此 sleep 发生在“主线程收集 future 的循环”中，
                        # 并不会阻止线程池中的任务同时发起网络请求。
                        # 因此它对降低并发请求峰值的效果有限；真正的峰值主要由 max_workers 决定。
                        # 该行为目前保留（按需求不改逻辑）。
                        logger.debug(
                            "Waiting %s seconds before collecting the next stock result",
                            analysis_delay,
                        )
                        time.sleep(analysis_delay)

                except Exception as e:  # broad-exception: fallback_recorded - Worker failures are safely logged and the remaining stock tasks continue.
                    log_safe_exception(
                        logger,
                        "Stock analysis task failed",
                        e,
                        error_code="pipeline_stock_task_failed",
                        context={"stock_code": code},
                    )

        # 统计
        elapsed_time = time.time() - start_time

        # dry-run 模式下，数据获取成功即视为成功
        if dry_run:
            # 检查哪些股票的最新可复用交易日数据已存在
            success_count = sum(
                1
                for code in stock_codes
                if self.db.has_today_data(
                    code,
                    self._resolve_resume_target_date(
                        code, current_time=resume_reference_time
                    ),
                )
            )
            fail_count = len(stock_codes) - success_count
        else:
            success_count = len(results)
            fail_count = len(stock_codes) - success_count

        logger.info("===== Analysis completed =====")
        logger.info(
            "Analysis summary: succeeded=%s failed=%s elapsed_seconds=%.2f",
            success_count,
            fail_count,
            elapsed_time,
        )

        delivery_diag_token = (
            self._activate_delivery_diagnostic_context(results)
            if results and not dry_run
            else None
        )
        try:
            # Always save the report locally, independently of notification delivery.
            if results and not dry_run:
                self._save_local_report(results, report_type)
                self._refresh_saved_diagnostic_snapshot(results=results)
            else:
                render_skip_reason = (
                    "dry_run" if dry_run else "no_successful_results"
                )
                self._record_pipeline_stage_result(
                    PipelineStageResult.skipped(
                        PipelineStageName.RENDER,
                        reason=render_skip_reason,
                    ),
                    input_summary={
                        "result_count": len(results),
                        "dry_run": dry_run,
                        "report_type": report_type.value,
                    },
                    output_summary={"reason": render_skip_reason},
                )

            if not (results and send_notification and not dry_run):
                dispatch_skip_reason = (
                    "dry_run"
                    if dry_run
                    else (
                        "notification_disabled"
                        if not send_notification
                        else "no_successful_results"
                    )
                )
                self._record_pipeline_stage_result(
                    PipelineStageResult.skipped(
                        PipelineStageName.DISPATCH,
                        reason=dispatch_skip_reason,
                    ),
                    input_summary={
                        "result_count": len(results),
                        "dry_run": dry_run,
                        "send_notification": send_notification,
                    },
                    output_summary={"reason": dispatch_skip_reason},
                )
                if results and not dry_run:
                    self._refresh_saved_diagnostic_snapshot(results=results)

            # Deliver notifications; single-stock mode skips duplicate aggregate delivery.
            if results and send_notification and not dry_run:
                if single_stock_notify:
                    # Save the aggregate report without delivering it again.
                    logger.info(
                        "Single-stock notification mode: skipping aggregate delivery and saving locally"
                    )
                    self._send_notifications(results, report_type, skip_push=True)
                elif merge_notification:
                    # Issue #190: defer delivery until stock and market reports are combined.
                    logger.info(
                        "Combined-delivery mode: deferring delivery until stock and market reports are merged"
                    )
                    self._send_notifications(results, report_type, skip_push=True)
                else:
                    self._send_notifications(results, report_type)
        finally:
            reset_run_diagnostic_context(delivery_diag_token)

        return results
