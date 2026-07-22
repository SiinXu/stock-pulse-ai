"""Guard the class compatibility surface of :mod:`src.analyzer`."""

import __future__
import importlib
import inspect
import subprocess
import sys
import textwrap
import typing
from types import CodeType, FunctionType, SimpleNamespace


GENERATION_METHODS = (
    "__init__",
    "_get_runtime_config",
    "_get_skill_prompt_sections",
    "_get_analysis_system_prompt",
    "_has_channel_config",
    "_legacy_router_provider_alias",
    "_build_legacy_router_model_list_from_config",
    "_init_litellm",
    "is_available",
    "_litellm_runtime_available",
    "_can_use_generation_fallback",
    "_resolve_generation_backend_config",
    "get_generation_backend_config_error",
    "_get_hermes_config_error",
    "_get_mixed_hermes_route_error",
    "_hermes_redaction_values_for_model",
    "_sanitize_hermes_exception_text",
    "_litellm_redaction_values_for_model",
    "_sanitize_litellm_exception_text",
    "get_generation_log_redaction_values",
    "sanitize_generation_diagnostic",
    "_dispatch_litellm_completion",
    "_normalize_usage",
    "_get_response_field",
    "_extract_text_blocks",
    "_extract_completion_text",
    "_extract_stream_text",
    "_consume_litellm_stream",
    "_get_generation_backend",
    "_call_litellm",
    "_call_litellm_impl",
    "generate_text",
)

ANALYSIS_METHODS = (
    "analyze",
    "_format_prompt",
    "_format_volume",
    "_format_amount",
    "_format_percent",
    "_format_price",
    "_build_market_snapshot",
    "_check_content_integrity",
    "_build_integrity_complement_prompt",
    "_build_integrity_retry_prompt",
    "_apply_placeholder_fill",
)

RESPONSE_METHODS = (
    "_extract_analysis_json_object",
    "_load_analysis_json_candidate",
    "_contains_embedded_json_object",
    "_validate_analysis_minimal_contract",
    "_generation_validation_error",
    "_parse_response",
    "_fix_json_string",
    "_validate_json_response",
    "_parse_text_response",
    "batch_analyze",
)

ANALYZER_METHODS = GENERATION_METHODS + ANALYSIS_METHODS + RESPONSE_METHODS
STATIC_METHODS = frozenset(
    {
        "_legacy_router_provider_alias",
        "_build_legacy_router_model_list_from_config",
        "_get_response_field",
        "_contains_embedded_json_object",
    }
)
EXPECTED_CLASS_KEYS = (
    "__module__",
    "__doc__",
    "LEGACY_DEFAULT_SYSTEM_PROMPT",
    "SYSTEM_PROMPT",
    "TEXT_SYSTEM_PROMPT",
    *ANALYZER_METHODS,
    "__dict__",
    "__weakref__",
)


def _unwrap_descriptor(descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return descriptor.__func__
    return descriptor


def _assert_facade_code_matches_source(facade_code, source_code):
    """Compare executable metadata while excluding moved source locations."""

    assert facade_code.co_argcount == source_code.co_argcount
    assert facade_code.co_posonlyargcount == source_code.co_posonlyargcount
    assert facade_code.co_kwonlyargcount == source_code.co_kwonlyargcount
    assert facade_code.co_nlocals == source_code.co_nlocals
    assert facade_code.co_stacksize == source_code.co_stacksize
    assert facade_code.co_flags == source_code.co_flags
    assert facade_code.co_code == source_code.co_code
    assert facade_code.co_names == source_code.co_names
    assert facade_code.co_varnames == source_code.co_varnames
    assert facade_code.co_freevars == source_code.co_freevars
    assert facade_code.co_cellvars == source_code.co_cellvars
    assert facade_code.co_name == source_code.co_name
    if sys.version_info >= (3, 11):
        assert facade_code.co_qualname == source_code.co_qualname
        assert facade_code.co_exceptiontable == source_code.co_exceptiontable
    assert len(facade_code.co_consts) == len(source_code.co_consts)
    for facade_constant, source_constant in zip(
        facade_code.co_consts,
        source_code.co_consts,
    ):
        if isinstance(source_constant, CodeType):
            assert isinstance(facade_constant, CodeType)
            _assert_facade_code_matches_source(facade_constant, source_constant)
        else:
            assert facade_constant == source_constant


def _source_groups():
    generation = importlib.import_module("src.analyzer_parts.generation")
    analysis = importlib.import_module("src.analyzer_parts.analysis")
    response = importlib.import_module("src.analyzer_parts.response")
    return (
        (generation.GeminiAnalyzer, GENERATION_METHODS),
        (analysis.GeminiAnalyzer, ANALYSIS_METHODS),
        (response.GeminiAnalyzer, RESPONSE_METHODS),
    )


def _contains_forward_reference(annotation):
    """Return whether an annotation includes a forward reference."""

    if isinstance(annotation, typing.ForwardRef):
        return True
    return any(
        _contains_forward_reference(argument)
        for argument in typing.get_args(annotation)
    )


def _resolved_source_annotations(function, facade_globals):
    """Resolve private-source annotations as the facade must expose them."""

    annotations = dict(function.__annotations__)
    if any(_contains_forward_reference(value) for value in annotations.values()):
        resolved = typing.get_type_hints(
            function,
            globalns=facade_globals,
            localns=facade_globals,
            include_extras=True,
        )
        for name, value in annotations.items():
            if value is None:
                resolved[name] = None
        return resolved
    return inspect.get_annotations(
        function,
        globals=facade_globals,
        locals=facade_globals,
        eval_str=True,
    )


def _assert_eager_annotation_code(code):
    """Require eager annotations throughout a moved method's code tree."""

    assert not code.co_flags & __future__.annotations.compiler_flag
    for constant in code.co_consts:
        if isinstance(constant, CodeType):
            _assert_eager_annotation_code(constant)


class _AnnotationCaptured(BaseException):
    """Stop a method as soon as its nested function has been constructed."""


def _capture_local_annotations(function, local_name, *args, **kwargs):
    """Capture one nested function's runtime annotation dictionary."""

    target_code = getattr(function, "__func__", function).__code__
    captured = {}

    def tracer(frame, event, _arg):
        if event == "line" and frame.f_code is target_code and local_name in frame.f_locals:
            captured.update(frame.f_locals[local_name].__annotations__)
            raise _AnnotationCaptured
        return tracer

    previous_trace = sys.gettrace()
    sys.settrace(tracer)
    try:
        function(*args, **kwargs)
    except _AnnotationCaptured:
        pass
    finally:
        sys.settrace(previous_trace)

    assert captured
    return captured


def test_analyzer_class_preserves_owned_member_order_and_descriptors():
    """Keep the direct class shape and descriptor ordering stable."""

    analyzer = importlib.import_module("src.analyzer")
    facade = analyzer.GeminiAnalyzer

    assert facade.__module__ == "src.analyzer"
    assert facade.__qualname__ == "GeminiAnalyzer"
    assert facade.__bases__ == (object,)
    assert tuple(vars(facade)) == EXPECTED_CLASS_KEYS
    for name in ANALYZER_METHODS:
        descriptor = vars(facade)[name]
        if name in STATIC_METHODS:
            assert isinstance(descriptor, staticmethod)
        else:
            assert isinstance(descriptor, FunctionType)


def test_analyzer_methods_preserve_facade_metadata_and_globals():
    """Bind every moved method to the complete legacy facade namespace."""

    analyzer = importlib.import_module("src.analyzer")
    facade_globals = vars(analyzer)

    for source_class, method_names in _source_groups():
        for name in method_names:
            source_descriptor = vars(source_class)[name]
            facade_descriptor = vars(analyzer.GeminiAnalyzer)[name]
            assert type(facade_descriptor) is type(source_descriptor)

            source_function = _unwrap_descriptor(source_descriptor)
            facade_function = _unwrap_descriptor(facade_descriptor)
            expected_annotations = _resolved_source_annotations(
                source_function,
                facade_globals,
            )

            assert facade_function.__globals__ is facade_globals
            _assert_facade_code_matches_source(
                facade_function.__code__,
                source_function.__code__,
            )
            assert facade_function.__defaults__ == source_function.__defaults__
            assert facade_function.__kwdefaults__ == source_function.__kwdefaults__
            assert facade_function.__annotations__ == expected_annotations
            assert facade_function.__closure__ == source_function.__closure__
            assert facade_function.__dict__ == source_function.__dict__
            assert facade_function.__doc__ == source_function.__doc__
            assert facade_function.__module__ == "src.analyzer"
            assert facade_function.__name__ == name
            assert facade_function.__qualname__ == f"GeminiAnalyzer.{name}"
            if sys.version_info >= (3, 11):
                assert facade_function.__code__.co_qualname == f"GeminiAnalyzer.{name}"
            assert getattr(facade_function, "__type_params__", ()) == getattr(
                source_function,
                "__type_params__",
                (),
            )


def test_analyzer_method_sources_compile_annotations_eagerly():
    """Keep the monolith's eager annotation semantics in every code tree."""

    for source_class, method_names in _source_groups():
        for name in method_names:
            source_function = _unwrap_descriptor(vars(source_class)[name])
            _assert_eager_annotation_code(source_function.__code__)


def test_nested_method_annotations_preserve_monolith_values(monkeypatch):
    """Expose concrete nested annotations instead of postponed strings."""

    analyzer = importlib.import_module("src.analyzer")
    instance = analyzer.GeminiAnalyzer.__new__(analyzer.GeminiAnalyzer)

    progress_annotations = _capture_local_annotations(
        instance.analyze,
        "_emit_progress",
        {},
    )
    assert progress_annotations == {
        "progress": int,
        "message": str,
        "return": None,
    }

    config = SimpleNamespace(
        litellm_model="test-model",
        litellm_fallback_models=[],
        llm_model_list=[],
    )
    monkeypatch.setattr(instance, "_get_runtime_config", lambda: config)
    monkeypatch.setattr(instance, "_has_channel_config", lambda _config: False)
    monkeypatch.setattr(analyzer, "get_configured_llm_models", lambda _models: [])
    monkeypatch.setattr(
        analyzer,
        "route_deployment_origins",
        lambda _models, _model: SimpleNamespace(has_hermes=False),
    )
    monkeypatch.setattr(
        analyzer,
        "resolved_model_provider_identity",
        lambda _model, _models: ("test-model", "test-provider"),
    )

    usage_annotations = _capture_local_annotations(
        instance._call_litellm_impl,
        "_attach_usage_audit",
        "prompt",
        {},
    )
    assert usage_annotations == {
        "usage": typing.Dict[str, typing.Any],
        "messages": typing.List[typing.Dict[str, typing.Any]],
        "return": typing.Dict[str, typing.Any],
    }


def test_analyzer_methods_resolve_legacy_facade_patches(monkeypatch):
    """Keep existing module-level patch targets behaviorally effective."""

    analyzer = importlib.import_module("src.analyzer")
    instance = analyzer.GeminiAnalyzer.__new__(analyzer.GeminiAnalyzer)
    instance._config_override = None
    sentinel = object()
    monkeypatch.setattr(analyzer, "get_config", lambda: sentinel)

    assert instance._get_runtime_config() is sentinel
    assert instance._get_runtime_config.__func__.__globals__ is vars(analyzer)


def test_analyzer_class_and_method_sources_restore_on_reload():
    """Recreate patched facade and source descriptors on facade reload."""

    probe = textwrap.dedent(
        f"""
        import __future__
        import importlib
        import inspect
        import sys
        import typing
        from types import CodeType, FunctionType

        def assert_code_matches(facade_code, source_code):
            assert facade_code.co_flags == source_code.co_flags
            assert facade_code.co_code == source_code.co_code
            assert facade_code.co_names == source_code.co_names
            assert facade_code.co_varnames == source_code.co_varnames
            assert facade_code.co_freevars == source_code.co_freevars
            assert facade_code.co_cellvars == source_code.co_cellvars
            assert facade_code.co_name == source_code.co_name
            if sys.version_info >= (3, 11):
                assert facade_code.co_qualname == source_code.co_qualname
            assert len(facade_code.co_consts) == len(source_code.co_consts)
            for facade_constant, source_constant in zip(
                facade_code.co_consts,
                source_code.co_consts,
            ):
                if isinstance(source_constant, CodeType):
                    assert isinstance(facade_constant, CodeType)
                    assert_code_matches(facade_constant, source_constant)
                else:
                    assert facade_constant == source_constant

        def contains_forward_reference(annotation):
            if isinstance(annotation, typing.ForwardRef):
                return True
            return any(
                contains_forward_reference(argument)
                for argument in typing.get_args(annotation)
            )

        def resolved_annotations(function, facade_globals):
            annotations = dict(function.__annotations__)
            if any(
                contains_forward_reference(value)
                for value in annotations.values()
            ):
                resolved = typing.get_type_hints(
                    function,
                    globalns=facade_globals,
                    localns=facade_globals,
                    include_extras=True,
                )
                for name, value in annotations.items():
                    if value is None:
                        resolved[name] = None
                return resolved
            return inspect.get_annotations(
                function,
                globals=facade_globals,
                locals=facade_globals,
                eval_str=True,
            )

        method_groups = {(
            ("src.analyzer_parts.generation", GENERATION_METHODS),
            ("src.analyzer_parts.analysis", ANALYSIS_METHODS),
            ("src.analyzer_parts.response", RESPONSE_METHODS),
        )!r}
        static_methods = {STATIC_METHODS!r}
        expected_class_keys = {EXPECTED_CLASS_KEYS!r}

        analyzer = importlib.import_module("src.analyzer")
        original_class = analyzer.GeminiAnalyzer
        for module_name, method_names in method_groups:
            source_module = importlib.import_module(module_name)
            for name in method_names:
                setattr(analyzer.GeminiAnalyzer, name, lambda: None)
                setattr(source_module.GeminiAnalyzer, name, lambda: None)

        analyzer = importlib.reload(analyzer)
        assert analyzer.GeminiAnalyzer is not original_class
        assert tuple(vars(analyzer.GeminiAnalyzer)) == expected_class_keys
        facade_globals = vars(analyzer)

        for module_name, method_names in method_groups:
            source_module = importlib.import_module(module_name)
            for name in method_names:
                source_descriptor = vars(source_module.GeminiAnalyzer)[name]
                facade_descriptor = vars(analyzer.GeminiAnalyzer)[name]
                if name in static_methods:
                    assert isinstance(source_descriptor, staticmethod)
                    assert isinstance(facade_descriptor, staticmethod)
                    source_function = source_descriptor.__func__
                    facade_function = facade_descriptor.__func__
                else:
                    assert isinstance(source_descriptor, FunctionType)
                    assert isinstance(facade_descriptor, FunctionType)
                    source_function = source_descriptor
                    facade_function = facade_descriptor
                assert_code_matches(
                    facade_function.__code__,
                    source_function.__code__,
                )
                assert facade_function.__globals__ is facade_globals
                assert facade_function.__annotations__ == resolved_annotations(
                    source_function,
                    facade_globals,
                )
                assert facade_function.__module__ == "src.analyzer"
                assert facade_function.__qualname__ == f"GeminiAnalyzer.{{name}}"
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode == 0, result.stderr
