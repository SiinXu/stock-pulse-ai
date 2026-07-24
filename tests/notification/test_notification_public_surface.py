"""Guard the compatibility surface of :mod:`src.notification`."""

import ast
import builtins
import hashlib
import importlib
import inspect
import json
import subprocess
import sys
import typing
from pathlib import Path
from types import CodeType, FunctionType, SimpleNamespace


EXPECTED_PUBLIC_EXPORTS = frozenset(
    """
    AnalysisRequestContext Any AstrbotSender ChannelAttemptResult
    ChannelDetector Config CustomWebhookSender Dict DingtalkSender
    DiscordSender EmailSender Enum FeishuSender GotifySender List
    NotificationBuilder NotificationChannel NotificationDispatchResult
    NotificationNoiseDecision NotificationService NtfySender Optional
    PushoverSender PushplusSender ReportType Serverchan3Sender SlackSender
    TYPE_CHECKING TelegramSender Tuple WECHAT_IMAGE_MAX_BYTES WechatSender
    annotations dataclass datetime display_action_fields_for_result
    display_decision_type_for_result display_operation_advice_for_result
    evaluate_notification_noise field format_public_market_status_line
    format_public_phase_pack_excerpt format_strategy_skill_items
    get_chip_unavailable_reason get_config get_localized_stock_name
    get_notification_route_config get_notification_service get_report_labels
    get_signal_level is_chip_structure_unavailable
    is_feishu_static_configured localize_chip_health
    localize_conflict_severity localize_consensus_level
    localize_strategy_conflict_description localize_strategy_signal
    localize_strategy_skill localize_strategy_synthesis_summary
    localize_trend_prediction log_safe_exception logger logging
    normalize_model_used normalize_report_language
    normalize_strategy_synthesis_payload record_notification_noise
    release_notification_noise resolve_gotify_message_endpoint
    resolve_ntfy_endpoint sanitize_diagnostic_text sanitize_exception_chain
    send_daily_report signal_attribution_has_content
    signal_attribution_weight_items split_notification_route_channels
    strategy_invalid_opinion_count time
    """.split()
)

EXPECTED_BASES = (
    "AstrbotSender",
    "CustomWebhookSender",
    "DingtalkSender",
    "DiscordSender",
    "EmailSender",
    "FeishuSender",
    "GotifySender",
    "NtfySender",
    "PushoverSender",
    "PushplusSender",
    "Serverchan3Sender",
    "SlackSender",
    "TelegramSender",
    "WechatSender",
)

EXPECTED_SOURCE_DISPLAY_NAMES = (
    ("tencent", (("zh", "腾讯财经"), ("en", "Tencent Finance"))),
    ("akshare_em", (("zh", "东方财富"), ("en", "Eastmoney"))),
    ("akshare_sina", (("zh", "新浪财经"), ("en", "Sina Finance"))),
    ("akshare_qq", (("zh", "腾讯财经"), ("en", "Tencent Finance"))),
    (
        "efinance",
        (("zh", "东方财富(efinance)"), ("en", "Eastmoney (efinance)")),
    ),
    ("tushare", (("zh", "Tushare Pro"), ("en", "Tushare Pro"))),
    ("sina", (("zh", "新浪财经"), ("en", "Sina Finance"))),
    ("stooq", (("zh", "Stooq"), ("en", "Stooq"))),
    ("longbridge", (("zh", "长桥"), ("en", "Longbridge"))),
    ("fallback", (("zh", "降级兜底"), ("en", "Fallback"))),
)
EXPECTED_CURRENCY_SUFFIX = (
    ("USD", "美元"),
    ("HKD", "港元"),
    ("CNY", "元"),
    ("RMB", "元"),
    ("CNH", "元"),
    ("TWD", "新台币"),
)
EXPECTED_UNRESOLVED_HINT_METHODS = frozenset(
    {
        "_append_fundamental_blocks",
        "_append_market_snapshot",
        "_append_market_status_line",
        "_collect_models_used",
        "_count_display_decisions",
        "_get_display_name",
        "_get_display_operation_advice",
        "_get_fundamental_blocks",
        "_get_history_compare_context",
        "_get_signal_level",
        "_public_market_status_line",
        "_public_phase_pack_excerpt",
        "generate_aggregate_report",
        "generate_brief_report",
        "generate_daily_report",
        "generate_dashboard_report",
        "generate_single_stock_report",
        "generate_wechat_dashboard",
        "generate_wechat_summary",
    }
)

EXPECTED_GROUPS = (
    (
        "_ReportSetupMethods",
        "_REPORT_SETUP_METHOD_NAMES",
        (
            "_normalize_report_type",
            "_get_report_language",
            "_get_labels",
            "_get_display_name",
            "_get_history_compare_context",
            "generate_aggregate_report",
            "_collect_models_used",
            "_public_phase_pack_excerpt",
            "_public_market_status_line",
            "_append_market_status_line",
            "_should_show_llm_model",
        ),
        "2b2ae6b5437065cff1cba53b5a9897c4bcafe6937586171fa07739b0c68ec79c",
    ),
    (
        "_RoutingMethods",
        "_ROUTING_METHOD_NAMES",
        (
            "detect_configured_channels",
            "_detect_all_channels",
            "is_available",
            "get_available_channels",
            "get_channels_for_route",
            "get_channel_names",
            "evaluate_noise_control",
            "record_noise_control",
            "release_noise_control",
            "_has_context_channel",
            "_extract_telegram_context_chat_id",
            "should_broadcast_static_channels",
            "_extract_dingtalk_session_webhook",
            "_extract_feishu_reply_info",
            "send_to_context",
            "_send_via_source_context",
            "_send_feishu_stream_reply",
            "_send_feishu_stream_chunked",
        ),
        "4ddd7490b49c2c90bd5d697e08285925ff08a18ff162ccdc680c8330de2f4d61",
    ),
    (
        "_RenderingMethods",
        "_RENDERING_METHOD_NAMES",
        (
            "generate_daily_report",
            "_escape_md",
            "_clean_sniper_value",
            "_phase_decision_list",
            "_phase_decision_has_content",
            "_append_phase_decision_block",
            "_get_display_operation_advice",
            "_count_display_decisions",
            "_get_signal_level",
            "generate_dashboard_report",
            "generate_wechat_dashboard",
            "generate_wechat_summary",
            "generate_brief_report",
            "generate_single_stock_report",
            "_get_source_display_name",
            "_append_market_snapshot",
            "_format_amount_cn",
            "_format_percent",
            "_format_per_share",
            "_format_text",
            "_get_fundamental_blocks",
            "_append_fundamental_blocks",
            "_append_financial_summary",
            "_append_shareholder_return",
            "_format_net_shares",
            "_append_institutional_flow",
            "_append_related_boards",
        ),
        "f913542b7e81159cc0243f7c4d854e2011321ac85baa6910b4508c3fd37f34bb",
    ),
    (
        "_DispatchMethods",
        "_DISPATCH_METHOD_NAMES",
        (
            "_should_use_image_for_channel",
            "_sanitize_notification_diagnostics",
            "_send_to_static_channel",
            "send_with_results",
            "send",
            "save_report_to_file",
            "save_and_send_feishu_file",
        ),
        "97f849e86a403cfb2de7247a21b759fd6a42bc0da730b41ffb5fab0c35a713fe",
    ),
)


def _canonical_ast(value):
    """Serialize ASTs without interpreter-version-only fields."""

    if isinstance(value, ast.AST):
        return [
            value.__class__.__name__,
            [
                [field, _canonical_ast(child)]
                for field, child in ast.iter_fields(value)
                if field != "type_params"
            ],
        ]
    if isinstance(value, list):
        return [_canonical_ast(item) for item in value]
    if value is Ellipsis:
        return {"constant": "Ellipsis"}
    return value


def _container_ast_hash(container) -> str:
    source_path = inspect.getsourcefile(container)
    tree = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    class_node = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == container.__name__
    )
    records = [
        (node.name, _canonical_ast(node))
        for node in class_node.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    payload = json.dumps(
        records,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _descriptor_function(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    if isinstance(descriptor, property):
        return descriptor.fget
    return descriptor


def _loaded_globals(code: CodeType):
    import dis

    names = {
        instruction.argval
        for instruction in dis.get_instructions(code)
        if instruction.opname in {"LOAD_GLOBAL", "LOAD_NAME"}
    }
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            names.update(_loaded_globals(constant))
    return names


def _all_method_names():
    return tuple(
        name
        for _, _, method_names, _ in EXPECTED_GROUPS
        for name in method_names
    )


def test_notification_public_exports_match_pre_split_snapshot():
    module = importlib.import_module("src.notification")

    assert {name for name in vars(module) if not name.startswith("_")} == (
        EXPECTED_PUBLIC_EXPORTS
    )


def test_notification_method_asts_match_pre_split_snapshot():
    module = importlib.import_module("src.notification")

    assert {
        container_name: _container_ast_hash(getattr(module, container_name))
        for container_name, _, _, _ in EXPECTED_GROUPS
    } == {
        container_name: expected_hash
        for container_name, _, _, expected_hash in EXPECTED_GROUPS
    }


def test_notification_descriptors_preserve_facade_contract():
    module = importlib.import_module("src.notification")
    target = module.NotificationService
    facade_globals = vars(module)

    assert target.__module__ == "src.notification"
    assert target.__qualname__ == "NotificationService"
    assert target.__init__.__globals__ is facade_globals
    assert tuple(base.__name__ for base in target.__bases__) == EXPECTED_BASES
    assert target.__bases__ == tuple(getattr(module, name) for name in EXPECTED_BASES)
    assert tuple(
        (source, tuple(labels.items()))
        for source, labels in target._SOURCE_DISPLAY_NAMES.items()
    ) == EXPECTED_SOURCE_DISPLAY_NAMES
    assert tuple(target._CURRENCY_SUFFIX.items()) == EXPECTED_CURRENCY_SUFFIX

    for container_name, names_attribute, expected_names, _ in EXPECTED_GROUPS:
        container = getattr(module, container_name)
        assert getattr(module, names_attribute) == expected_names
        assert container.__name__.startswith("_")
        assert container.__module__.startswith("src.notification_parts.")
        assert container not in target.__bases__

        for name in expected_names:
            descriptor = target.__dict__[name]
            source_descriptor = container.__dict__[name]
            assert descriptor.__class__ is source_descriptor.__class__
            function = _descriptor_function(descriptor)
            source_function = _descriptor_function(source_descriptor)
            assert isinstance(function, FunctionType)
            assert function.__globals__ is facade_globals
            assert function.__code__ is source_function.__code__
            assert function.__defaults__ == source_function.__defaults__
            assert function.__kwdefaults__ == source_function.__kwdefaults__
            assert function.__annotations__ == source_function.__annotations__
            assert inspect.signature(function) == inspect.signature(source_function)
            assert function.__closure__ == source_function.__closure__
            assert function.__dict__ == source_function.__dict__
            assert function.__doc__ == source_function.__doc__
            assert getattr(function, "__type_params__", ()) == getattr(
                source_function,
                "__type_params__",
                (),
            )
            assert function.__module__ == "src.notification"
            assert function.__name__ == source_function.__name__
            assert function.__qualname__ == f"NotificationService.{name}"
            for global_name in _loaded_globals(function.__code__):
                assert global_name in facade_globals or hasattr(
                    builtins,
                    global_name,
                )


def test_notification_method_order_matches_pre_split_contract():
    module = importlib.import_module("src.notification")
    expected_names = ("__init__",) + _all_method_names()
    actual_names = tuple(
        name
        for name, descriptor in vars(module.NotificationService).items()
        if name in expected_names and isinstance(
            _descriptor_function(descriptor),
            FunctionType,
        )
    )

    assert len(expected_names) == 64
    assert actual_names == expected_names


def test_notification_complete_class_member_order_matches_pre_split_contract():
    module = importlib.import_module("src.notification")
    rendering_names = EXPECTED_GROUPS[2][2]
    expected_names = (
        "__module__",
        "__doc__",
        "__init__",
        *EXPECTED_GROUPS[0][2],
        *EXPECTED_GROUPS[1][2],
        *rendering_names[:14],
        "_SOURCE_DISPLAY_NAMES",
        *rendering_names[14:16],
        "_CURRENCY_SUFFIX",
        *rendering_names[16:],
        *EXPECTED_GROUPS[3][2],
    )

    assert tuple(vars(module.NotificationService)) == expected_names


def test_notification_type_hint_resolution_matches_pre_split_contract():
    module = importlib.import_module("src.notification")
    unresolved = set()

    for name in ("__init__",) + _all_method_names():
        function = _descriptor_function(module.NotificationService.__dict__[name])
        try:
            hints = typing.get_type_hints(function)
        except NameError as exc:
            assert str(exc) == "name 'AnalysisResult' is not defined"
            unresolved.add(name)
        else:
            assert isinstance(hints, dict)

    assert unresolved == EXPECTED_UNRESOLVED_HINT_METHODS


def test_notification_moved_methods_use_facade_patch_seams(monkeypatch):
    module = importlib.import_module("src.notification")
    service = object.__new__(module.NotificationService)
    normalized = []

    monkeypatch.setattr(
        module,
        "get_config",
        lambda: SimpleNamespace(report_language="patched-language"),
    )
    monkeypatch.setattr(
        module,
        "normalize_report_language",
        lambda value: normalized.append(value) or value,
    )

    assert service._get_report_language() == "patched-language"
    assert normalized == ["patched-language"]

    outbound_calls = []
    config = SimpleNamespace(
        ntfy_url="https://ntfy.example/topic",
        gotify_url="https://gotify.example",
        gotify_token="token",
    )
    monkeypatch.setattr(
        module,
        "resolve_ntfy_endpoint",
        lambda value: outbound_calls.append(("ntfy", value))
        or ("https://ntfy.example", "topic"),
    )
    monkeypatch.setattr(
        module,
        "resolve_gotify_message_endpoint",
        lambda value: outbound_calls.append(("gotify", value))
        or "https://gotify.example/message",
    )

    channels = module.NotificationService.detect_configured_channels(config)

    assert module.NotificationChannel.NTFY in channels
    assert module.NotificationChannel.GOTIFY in channels
    assert outbound_calls == [
        ("ntfy", "https://ntfy.example/topic"),
        ("gotify", "https://gotify.example"),
    ]


def test_notification_reload_recreates_facade_class_and_methods():
    code = """
import importlib
import src.notification as module

old_class = module.NotificationService
old_channel = module.NotificationChannel
old_method = old_class.send_with_results
old_source_names = old_class._SOURCE_DISPLAY_NAMES
old_currency_suffix = old_class._CURRENCY_SUFFIX
old_member_order = tuple(vars(old_class))

first = importlib.reload(module)
first_class = first.NotificationService
first_channel = first.NotificationChannel
first_method = first_class.send_with_results

assert first_class is not old_class
assert first.NotificationChannel is not old_channel
assert first_method is not old_method
assert first_class._SOURCE_DISPLAY_NAMES is not old_source_names
assert first_class._CURRENCY_SUFFIX is not old_currency_suffix
assert first_class._SOURCE_DISPLAY_NAMES == old_source_names
assert first_class._CURRENCY_SUFFIX == old_currency_suffix
assert tuple(vars(first_class)) == old_member_order
assert first_method.__globals__ is vars(first)
assert first_method.__module__ == "src.notification"
assert first_method.__qualname__ == "NotificationService.send_with_results"

second = importlib.reload(first)

assert second.NotificationService is not first_class
assert second.NotificationChannel is not first_channel
assert second.NotificationService.send_with_results is not first_method
assert tuple(vars(second.NotificationService)) == old_member_order
assert second.NotificationService.send_with_results.__globals__ is vars(second)
"""
    completed = subprocess.run(
        [sys.executable, "-c", code],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
