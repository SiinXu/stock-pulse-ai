"""Command-line parsing and mode dispatch implementation."""

from __future__ import annotations

import argparse
from types import FunctionType
from typing import TYPE_CHECKING, Any, Dict

from src.config import Config
from src.utils.sanitize import log_safe_exception

if TYPE_CHECKING:
    from main import (
        __coordinate_service_runtime,
        __keep_service_runtime_alive,
        __run_schedule_mode,
        __run_service_only_mode,
        _run_analysis_with_runtime_scheduler_lock,
        _run_market_review_with_shared_lock,
        logger,
        resolve_index_stock_code_for_analysis,
        split_stock_list,
    )


def clone_facade_function(
    function: FunctionType,
    facade_globals: Dict[str, Any],
    *,
    module_name: str,
    qualname: str,
) -> FunctionType:
    """Clone a moved CLI function with the legacy facade globals."""

    cloned = FunctionType(
        function.__code__,
        facade_globals,
        name=function.__name__,
        argdefs=function.__defaults__,
        closure=function.__closure__,
    )
    cloned.__annotations__ = dict(function.__annotations__)
    cloned.__dict__.update(function.__dict__)
    cloned.__doc__ = function.__doc__
    cloned.__kwdefaults__ = (
        dict(function.__kwdefaults__) if function.__kwdefaults__ else None
    )
    cloned.__module__ = module_name
    cloned.__qualname__ = qualname
    if hasattr(function, "__type_params__"):
        cloned.__type_params__ = function.__type_params__
    return cloned


def parse_arguments() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='A股自选股智能分析系统',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  python main.py                    # 正常运行
  python main.py --debug            # 调试模式
  python main.py --dry-run          # 仅获取数据，不进行 AI 分析
  python main.py --stocks 600519,000001  # 指定分析特定股票
  python main.py --portfolio futu   # 从 Futu OpenD 读取实盘持仓作为分析范围
  python main.py --no-notify        # 不发送推送通知
  python main.py --check-notify     # 检查通知配置，不发送通知
  python main.py --single-notify    # 启用单股推送模式（每分析完一只立即推送）
  python main.py --schedule         # 启用定时任务模式
  python main.py --market-review    # 仅运行大盘复盘
        '''
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='启用调试模式，输出详细日志'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='仅获取数据，不进行 AI 分析'
    )

    parser.add_argument(
        '--stocks',
        type=str,
        help='指定要分析的股票代码，逗号分隔（覆盖配置文件）'
    )

    from src.services.stock_list_parser import SUPPORTED_PORTFOLIO_SOURCES

    parser.add_argument(
        '--portfolio',
        choices=SUPPORTED_PORTFOLIO_SOURCES,
        default=None,
        help='从只读实盘持仓加载分析股票范围（当前支持 futu）',
    )

    parser.add_argument(
        '--no-notify',
        action='store_true',
        help='不发送推送通知'
    )

    parser.add_argument(
        '--check-notify',
        action='store_true',
        help='只读检查通知渠道配置，不发送通知'
    )

    parser.add_argument(
        '--single-notify',
        action='store_true',
        help='启用单股推送模式：每分析完一只股票立即推送，而不是汇总推送'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='并发线程数（默认使用配置值）'
    )

    parser.add_argument(
        '--schedule',
        action='store_true',
        help='启用定时任务模式，每日定时执行'
    )

    parser.add_argument(
        '--no-run-immediately',
        action='store_true',
        help='定时任务启动时不立即执行一次'
    )

    parser.add_argument(
        '--market-review',
        action='store_true',
        help='仅运行大盘复盘分析'
    )

    parser.add_argument(
        '--no-market-review',
        action='store_true',
        help='跳过大盘复盘分析'
    )

    parser.add_argument(
        '--force-run',
        action='store_true',
        help='跳过交易日检查，强制执行全量分析（Issue #373）'
    )

    parser.add_argument(
        '--webui',
        action='store_true',
        help='启动 Web 管理界面'
    )

    parser.add_argument(
        '--webui-only',
        action='store_true',
        help='仅启动 Web 服务，不执行自动分析'
    )

    parser.add_argument(
        '--serve',
        action='store_true',
        help='启动 FastAPI 后端服务（同时执行分析任务）'
    )

    parser.add_argument(
        '--serve-only',
        action='store_true',
        help='仅启动 FastAPI 后端服务，不自动执行分析'
    )

    parser.add_argument(
        '--port',
        type=int,
        default=None,
        help='FastAPI 服务端口（默认使用 WEBUI_PORT，未配置时为 8000）'
    )

    parser.add_argument(
        '--host',
        type=str,
        default=None,
        help='FastAPI 服务监听地址（默认使用 WEBUI_HOST，未配置时为 127.0.0.1）'
    )

    parser.add_argument(
        '--no-context-snapshot',
        action='store_true',
        help='不保存分析上下文快照'
    )

    # === Backtest ===
    parser.add_argument(
        '--backtest',
        action='store_true',
        help='运行回测（对历史分析结果进行评估）'
    )

    parser.add_argument(
        '--backtest-code',
        type=str,
        default=None,
        help='仅回测指定股票代码'
    )

    parser.add_argument(
        '--backtest-days',
        type=int,
        default=None,
        help='回测评估窗口（交易日数，默认使用配置）'
    )

    parser.add_argument(
        '--backtest-force',
        action='store_true',
        help='强制回测（即使已有回测结果也重新计算）'
    )

    return parser.parse_args()


def _dispatch_cli(config: Config, args: argparse.Namespace) -> int:
    """Dispatch the configured CLI mode after startup bootstrap completes."""

    # Verification Configuration
    warnings = config.validate()
    for warning in warnings:
        logger.warning(warning)

    if getattr(args, "check_notify", False):
        from src.application_services import get_application_services
        from src.plugins import available_notification_channel_snapshot
        from src.services.notification_diagnostics import (
            format_notification_diagnostics,
            run_notification_diagnostics,
        )

        plugin_snapshot = (
            get_application_services().notification_channel_registry.snapshot()
        )
        available_plugin_snapshot = available_notification_channel_snapshot(
            plugin_snapshot
        )
        result = run_notification_diagnostics(
            config,
            enabled_plugin_channels=tuple(
                channel.channel_id for channel in plugin_snapshot
            ),
            available_plugin_channels=tuple(
                channel.channel_id for channel in available_plugin_snapshot
            ),
        )
        print(format_notification_diagnostics(result))
        return 0 if result.ok else 1

    # Parse stock lists (convert to uppercase - Issue #355)
    stock_codes = None
    if args.stocks:
        stock_codes = [
            resolve_index_stock_code_for_analysis(c)
            for c in split_stock_list(args.stocks)
            if (c or "").strip()
        ]
        logger.info("Using the stock list supplied on the command line: %s", stock_codes)
    if getattr(args, "portfolio", None):
        if stock_codes is not None:
            logger.warning(
                "--portfolio %s overrides the stock list supplied by --stocks",
                args.portfolio,
            )
        logger.info("Using live portfolio source for analysis scope: %s", args.portfolio)

    start_serve, service_exit_code = __coordinate_service_runtime(config, args)
    if service_exit_code is not None:
        return service_exit_code

    # === Only Web Service Mode: No automatic analysis ===
    if args.serve_only:
        return __run_service_only_mode(args)

    try:
        # Mode 0: Backtesting
        if getattr(args, 'backtest', False):
            logger.info("Mode: backtest")
            from src.services.backtest_service import BacktestService

            service = BacktestService()
            stats = service.run_backtest(
                code=getattr(args, 'backtest_code', None),
                force=getattr(args, 'backtest_force', False),
                eval_window_days=getattr(args, 'backtest_days', None),
            )
            logger.info(
                f"Backtest completed: processed={stats.get('processed')} saved={stats.get('saved')} "
                f"completed={stats.get('completed')} insufficient={stats.get('insufficient')} errors={stats.get('errors')}"
            )
            return 0

        # Mode 1: Market review for major indices only
        if args.market_review:
            from src.core.market_review import run_market_review
            from src.core.market_review_runtime import build_market_review_runtime

            # Issue #373: Trading day check for market-review-only mode.
            # Do NOT use _compute_trading_day_filter here: that helper checks
            # config.market_review_enabled, which would wrongly block an
            # explicit --market-review invocation when the flag is disabled.
            effective_region = None
            if not getattr(args, 'force_run', False) and getattr(config, 'trading_day_check_enabled', True):
                from src.core.trading_calendar import get_open_markets_today, compute_effective_region as _compute_region
                open_markets = get_open_markets_today()
                effective_region = _compute_region(
                    getattr(config, 'market_review_region', 'cn') or 'cn', open_markets
                )
                if effective_region == '':
                    logger.info(
                        "All markets relevant to the review are closed today; skipping the run. "
                        "Use --force-run to override."
                    )
                    return 0

            logger.info("Mode: market review only")
            notifier, analyzer, search_service = build_market_review_runtime(config)

            _run_market_review_with_shared_lock(
                config,
                run_market_review,
                notifier=notifier,
                analyzer=analyzer,
                search_service=search_service,
                send_notification=not args.no_notify,
                override_region=effective_region,
                trigger_source="cli",
            )
            return 0

        # Mode 2: Scheduled task mode
        if args.schedule or config.schedule_enabled:
            return __run_schedule_mode(config, args, stock_codes, start_serve)

        # Mode 3: Normal single run
        if config.run_immediately:
            analysis_succeeded = _run_analysis_with_runtime_scheduler_lock(
                config,
                args,
                stock_codes,
            )
            if (
                analysis_succeeded is False
                and getattr(args, "portfolio", None)
                and not start_serve
            ):
                return 1
        else:
            logger.info("Immediate analysis is disabled (RUN_IMMEDIATELY=false)")

        logger.info("\nProgram execution completed")

        __keep_service_runtime_alive(start_serve, args, config)
        return 0

    except KeyboardInterrupt:
        logger.info("\nInterrupted by the user; exiting")
        return 130

    except Exception as exc:  # broad-exception: fallback_recorded - preserve the logged top-level CLI failure boundary
        log_safe_exception(
            logger,
            "Main execution failed",
            exc,
            error_code="main_execution_failed",
        )
        return 1
