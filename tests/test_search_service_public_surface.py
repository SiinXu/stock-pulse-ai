"""Guard the compatibility surface of :mod:`src.search_service`."""

import ast
import dataclasses
import hashlib
import importlib
import inspect
import json
import subprocess
import sys
import typing
from pathlib import Path


EXPECTED_RAW_MODULE_COUNT = 74
EXPECTED_RAW_MODULE_SURFACE_SHA256 = (
    "3efea536587dc1ec7869bb10b5e1af280d41a1395e7e51f3356f146d0bef4805"
)
EXPECTED_MODULE_COUNT = 65
EXPECTED_MODULE_SURFACE_SHA256 = (
    "4e54d92e2c354ac18ab7bdce417ced14af5910ae12063cba802a6eddc684286e"
)
EXPECTED_PUBLIC_COUNT = 54
EXPECTED_PUBLIC_SURFACE_SHA256 = (
    "c527fe8817034ae49440db32d059f8c7498a3bff246c1ca36d8fd7e54f1ad305"
)
EXPECTED_REFLECTION_SHA256 = (
    "a7c6be2ceb001b21eaa8c4e4eb8c7c37b58938abee6c487f1bb12a2042d90933"
)
PYTHON_310_REFLECTION_SHA256 = (
    "845d67ae77120c1b379bfddec5c465979c21ef291a4d9fcc9b7a2d8768b31e9f"
)

EXPECTED_AST_GROUPS = (
    (
        "provider_base.py",
        (
            "_stable_search_failure_message",
            "_log_search_failure",
            "_safe_search_exception_message",
            "_SEARCH_TRANSIENT_EXCEPTIONS",
            "_post_with_retry",
            "_get_with_retry",
            "fetch_url_content",
            "SearchResult",
            "SearchResponse",
            "_stabilize_failed_search_response",
            "BaseSearchProvider",
        ),
        "d056368e83f587e55c37c4bb5d54118c844ac423b84aa36d49e52cd5bf03ae92",
        325,
    ),
    (
        "tavily.py",
        ("TavilySearchProvider",),
        "dc9e10ee3a046d7153ed77536513543653eed32fb88a6373a497b48bb0336089",
        170,
    ),
    (
        "serpapi.py",
        ("SerpAPISearchProvider",),
        "cd556f72e045917e44249289ad1aa396d9d2c2876fedbc1b14a8255466161d87",
        458,
    ),
    (
        "bocha.py",
        ("BochaSearchProvider",),
        "c19f826ebdb6ea4f70b0bc143be1e48dee81997798d29382cad2ec3c8e65f8b8",
        201,
    ),
    (
        "anspire.py",
        ("AnspireSearchProvider",),
        "59922e88bb960fef0525d8266dd5f1c10c66c7a597b4ce1de0d2341cdab340de",
        197,
    ),
    (
        "minimax.py",
        ("MiniMaxSearchProvider",),
        "9ca050a72dca0ee2a45b9ef07f80ef61eb352e6653cdd03d6552c49c1832cca4",
        241,
    ),
    (
        "brave.py",
        ("BraveSearchProvider",),
        "dcfc4d45c074ea6d5364d7116ea919ed94880183ef23fef30b6294b51fdc8d72",
        218,
    ),
    (
        "searxng.py",
        ("SearXNGSearchProvider",),
        "b14c330cb994e2e8a704a21daa60d14f5dd71e323cf33bdd9d60812ab5cbdfdb",
        416,
    ),
)
EXPECTED_MOVED_AST_LINES = 2_226

MOVED_FUNCTIONS = (
    "_stable_search_failure_message",
    "_log_search_failure",
    "_safe_search_exception_message",
    "_post_with_retry",
    "_get_with_retry",
    "fetch_url_content",
    "_stabilize_failed_search_response",
)
MOVED_VALUES = ("_SEARCH_TRANSIENT_EXCEPTIONS",)
MOVED_CLASSES = (
    "SearchResult",
    "SearchResponse",
    "BaseSearchProvider",
    "TavilySearchProvider",
    "SerpAPISearchProvider",
    "BochaSearchProvider",
    "AnspireSearchProvider",
    "MiniMaxSearchProvider",
    "BraveSearchProvider",
    "SearXNGSearchProvider",
)
PRIVATE_MODULES = tuple(
    f"src.search_parts.{filename.removesuffix('.py')}"
    for filename, _, _, _ in EXPECTED_AST_GROUPS
)


def _digest(value) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


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


def _definition_name(node):
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    if (
        isinstance(node, ast.Assign)
        and len(node.targets) == 1
        and isinstance(node.targets[0], ast.Name)
    ):
        return node.targets[0].id
    return None


def _definition_group(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node
        for node in tree.body
        if _definition_name(node) is not None
    ]


def _definition_line_count(node):
    decorators = getattr(node, "decorator_list", ())
    first_line = min([node.lineno, *(item.lineno for item in decorators)])
    return node.end_lineno - first_line + 1


def _stable_value(value):
    if value is dataclasses.MISSING:
        return "<MISSING>"
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if value is typing.Any:
        return {"typing": "Any"}
    if (
        typing.get_origin(value) is typing.Union
        and set(typing.get_args(value)) == {typing.Any, type(None)}
    ):
        # Python 3.10 implicitly wraps defaulted Any hints in Optional.
        return {"typing": "Any"}
    if isinstance(value, type):
        return {"type": f"{value.__module__}.{value.__qualname__}"}
    if isinstance(value, (tuple, list)):
        return [_stable_value(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_stable_value(item) for item in value), key=repr)
    if isinstance(value, dict):
        return [
            [_stable_value(key), _stable_value(item)]
            for key, item in value.items()
        ]
    if inspect.isfunction(value):
        return {"function": f"{value.__module__}.{value.__qualname__}"}
    return {"object_type": f"{type(value).__module__}.{type(value).__qualname__}"}


def _hint_record(function):
    try:
        hints = typing.get_type_hints(function)
    except Exception as exc:  # broad-exception: fallback_recorded - Snapshot preserves any legacy hint-resolution failure.
        return ["error", type(exc).__name__, str(exc)]
    return ["ok", [[key, _stable_value(value)] for key, value in hints.items()]]


def _function_record(module, function):
    unwrapped = inspect.unwrap(function)
    return {
        "kind": type(function).__name__,
        "module": function.__module__,
        "qualname": function.__qualname__,
        "name": function.__name__,
        "signature": str(inspect.signature(function)),
        "annotations": [
            [key, _stable_value(value)]
            for key, value in function.__annotations__.items()
        ],
        "hints": _hint_record(function),
        "defaults": _stable_value(function.__defaults__),
        "kwdefaults": _stable_value(function.__kwdefaults__),
        "doc": function.__doc__,
        "dict_keys": tuple(function.__dict__),
        "globals": function.__globals__ is vars(module),
        "abstract": bool(getattr(function, "__isabstractmethod__", False)),
        "wrapped": {
            "module": unwrapped.__module__,
            "qualname": unwrapped.__qualname__,
            "signature": str(inspect.signature(unwrapped)),
            "globals": unwrapped.__globals__ is vars(module),
        },
    }


def _descriptor_record(module, name, descriptor):
    if isinstance(descriptor, (staticmethod, classmethod)):
        return [
            name,
            type(descriptor).__name__,
            _function_record(module, descriptor.__func__),
        ]
    if isinstance(descriptor, property):
        return [
            name,
            "property",
            _function_record(module, descriptor.fget),
            _function_record(module, descriptor.fset) if descriptor.fset else None,
            _function_record(module, descriptor.fdel) if descriptor.fdel else None,
            descriptor.__doc__,
        ]
    if inspect.isfunction(descriptor):
        return [name, "function", _function_record(module, descriptor)]
    return [name, type(descriptor).__name__, _stable_value(descriptor)]


def _class_record(module, cls):
    ignored = {"__dict__", "__weakref__", "__firstlineno__"}
    record = {
        "module": cls.__module__,
        "qualname": cls.__qualname__,
        "name": cls.__name__,
        "bases": [f"{base.__module__}.{base.__qualname__}" for base in cls.__bases__],
        "mro": [f"{base.__module__}.{base.__qualname__}" for base in cls.__mro__],
        "surface": [name for name in vars(cls) if name not in ignored],
        "members": [
            _descriptor_record(module, name, descriptor)
            for name, descriptor in vars(cls).items()
            if name not in ignored
        ],
        "dataclass": dataclasses.is_dataclass(cls),
    }
    if dataclasses.is_dataclass(cls):
        record["fields"] = [
            [
                field.name,
                _stable_value(field.type),
                _stable_value(field.default),
                _stable_value(field.default_factory),
                field.init,
                field.repr,
                field.hash,
                field.compare,
                field.kw_only,
            ]
            for field in dataclasses.fields(cls)
        ]
        params = cls.__dataclass_params__
        # Keep this payload stable on Python 3.11 and 3.12. The newer
        # _DataclassParams attributes are already covered through signatures,
        # fields, __match_args__, and the raw class surface above.
        record["dataclass_params"] = [
            getattr(params, name, None)
            for name in (
                "init",
                "repr",
                "eq",
                "order",
                "unsafe_hash",
                "frozen",
            )
        ]
    return record


def _reflection_snapshot(module):
    return {
        "functions": [
            [name, _function_record(module, getattr(module, name))]
            for name in MOVED_FUNCTIONS
        ],
        "classes": [
            [name, _class_record(module, getattr(module, name))]
            for name in MOVED_CLASSES
        ],
    }


def test_search_module_surface_matches_pre_split_snapshot():
    module = importlib.import_module("src.search_service")
    raw_names = tuple(vars(module))
    module_names = tuple(name for name in vars(module) if not name.startswith("__"))
    public_names = tuple(name for name in vars(module) if not name.startswith("_"))

    assert len(raw_names) == EXPECTED_RAW_MODULE_COUNT
    assert _digest(raw_names) == EXPECTED_RAW_MODULE_SURFACE_SHA256
    assert len(module_names) == EXPECTED_MODULE_COUNT
    assert _digest(module_names) == EXPECTED_MODULE_SURFACE_SHA256
    assert len(public_names) == EXPECTED_PUBLIC_COUNT
    assert _digest(public_names) == EXPECTED_PUBLIC_SURFACE_SHA256
    assert tuple(module.__annotations__) == ("_search_service",)
    assert module.__annotations__["_search_service"] == typing.Optional[
        module.SearchService
    ]


def test_search_moved_definition_asts_match_pre_split_snapshot():
    parts = Path(__file__).parents[1] / "src" / "search_parts"
    moved_lines = 0

    for filename, expected_names, expected_hash, expected_lines in EXPECTED_AST_GROUPS:
        definitions = _definition_group(parts / filename)
        assert tuple(_definition_name(node) for node in definitions) == expected_names
        assert _digest(
            [(_definition_name(node), _canonical_ast(node)) for node in definitions]
        ) == expected_hash
        actual_lines = sum(_definition_line_count(node) for node in definitions)
        assert actual_lines == expected_lines
        moved_lines += actual_lines

    assert moved_lines == EXPECTED_MOVED_AST_LINES


def test_search_moved_reflection_matches_pre_split_snapshot():
    script = r'''
import src.search_service as module
from tests.test_search_service_public_surface import _digest, _reflection_snapshot

print(_digest(_reflection_snapshot(module)))
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    # Python 3.10 implicitly wraps Any hints with Optional when the default is
    # None; Python 3.11 removed that get_type_hints behavior.
    expected_hash = (
        PYTHON_310_REFLECTION_SHA256
        if sys.version_info[:2] == (3, 10)
        else EXPECTED_REFLECTION_SHA256
    )
    assert completed.stdout.strip() == expected_hash

    module = importlib.import_module("src.search_service")
    for class_name in MOVED_CLASSES:
        cls = getattr(module, class_name)
        assert cls.__module__ == module.__name__
    for class_name in MOVED_CLASSES[3:]:
        assert getattr(module, class_name).__bases__ == (module.BaseSearchProvider,)


def test_search_provider_methods_use_facade_patch_seams(monkeypatch):
    module = importlib.import_module("src.search_service")

    class ExplodingProvider(module.BaseSearchProvider):
        def _do_search(self, query, api_key, max_results, days=7):
            raise RuntimeError("provider failed")

    monkeypatch.setattr(
        module,
        "_safe_search_exception_message",
        lambda **_kwargs: "patched failure",
    )
    response = ExplodingProvider(["key"], "Patched").search("query")

    assert response.error_message == "patched failure"
    assert response.provider == "Patched"


def test_search_private_modules_do_not_replace_facade_definitions():
    module = importlib.import_module("src.search_service")
    facade_definitions = {
        name: getattr(module, name)
        for name in (*MOVED_FUNCTIONS, *MOVED_VALUES, *MOVED_CLASSES)
    }

    for private_name, (_, defined_names, _, _) in zip(
        PRIVATE_MODULES,
        EXPECTED_AST_GROUPS,
    ):
        private_module = importlib.import_module(private_name)
        for name in defined_names:
            private_value = getattr(private_module, name)
            if name in MOVED_VALUES:
                assert private_value == facade_definitions[name]
                continue
            assert private_value is not facade_definitions[name]
            assert private_value.__module__ == private_name

    assert {
        name: getattr(module, name) for name in facade_definitions
    } == facade_definitions


def test_search_reload_recreates_facade_definitions_and_singleton():
    script = r'''
import importlib
import src.search_parts.tavily as private_tavily
import src.search_service as module

old_result = module.SearchResult
old_provider = module.TavilySearchProvider
old_method = old_provider._extract_domain
private_tavily.TavilySearchProvider._extract_domain = staticmethod(
    lambda _url: "stale"
)
module._search_service = object()

first = importlib.reload(module)
first_result = first.SearchResult
first_provider = first.TavilySearchProvider
first_method = first_provider._extract_domain

assert first.SearchResult is not old_result
assert first_provider is not old_provider
assert first_method is not old_method
assert first_method.__globals__ is vars(first)
assert first_method.__module__ == first.__name__
assert first_method.__qualname__ == "TavilySearchProvider._extract_domain"
assert first_provider._extract_domain("https://example.com/path") == "example.com"
assert first._search_service is None

second = importlib.reload(first)
assert second.SearchResult is not first_result
assert second.TavilySearchProvider is not first_provider
assert second.TavilySearchProvider._extract_domain is not first_method
assert second.TavilySearchProvider._extract_domain.__globals__ is vars(second)
assert second._search_service is None
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
