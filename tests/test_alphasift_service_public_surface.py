"""Compatibility guards for the public AlphaSift service facade."""

import ast
import hashlib
import importlib
import inspect
import json
from pathlib import Path
import subprocess
import sys
import typing

import src.services.alphasift_service as service_module


EXPECTED_MODULE_SURFACE_SHA256 = (
    "ba1fa896f144aaa859df3aca372caf0f759f53b0e0099e10eba1ccd76175ed29"
)
EXPECTED_PUBLIC_SURFACE_SHA256 = (
    "204d9062412c7b49a779df555ecdb680a7f02fb7fa52b23b182b572ac0b68a9a"
)
EXPECTED_TOP_LEVEL_FUNCTION_NAMES_SHA256 = (
    "9e1d3ca12377f3655df4ae3663000a93b5f9d94066ef8349f1e7c83bf88c7f08"
)
EXPECTED_TOP_LEVEL_FUNCTION_METADATA_SHA256 = (
    "40eb90f0646befb06997c18b403c1c68bcdfda81ed522c9661386c80b144c902"
)
EXPECTED_MODULE_ANNOTATIONS = {
    "_DSA_FETCHER_MANAGER": "Any",
    "_ALPHASIFT_LITELLM_COMPLETION_ROUTES": (
        "ContextVar[Optional[Tuple[Dict[str, Any], ...]]]"
    ),
}
EXPECTED_SERVICE_SURFACE = (
    "__init__",
    "status",
    "strategies",
    "install",
    "hotspots",
    "_prefetch_hotspot_details",
    "hotspot_detail",
    "screen",
)
EXPECTED_SERVICE_METHOD_METADATA_SHA256 = (
    "59fe497d1cb6108972453543476f6e47abc535c2eeab3f4ec9cffbf5cbc95baf"
)
EXPECTED_PROVIDER_SURFACE = (
    "_BASE_URL",
    "_HTTP_TIMEOUT_SECONDS",
    "_COMMON_PARAMS",
    "_BROAD_BOARD_KEYWORDS",
    "_CHANGE_EVENT_LABELS",
    "_METAL_TOPIC_GROUPS",
    "__init__",
    "_eastmoney_get_once",
    "_eastmoney_get",
    "stock_board_concept_name_em",
    "stock_board_industry_name_em",
    "hotspot_rows",
    "stock_board_concept_cons_em",
    "stock_board_industry_cons_em",
    "hotspot_detail",
    "_fetch_board_changes",
    "_fetch_board_changes_raw",
    "_fetch_board_changes_with_fallback",
    "_is_broad_board",
    "_fetch_rankings",
    "_fetch_rankings_with_fallback",
    "_fetch_board_names",
    "_find_board_change",
    "_is_industry_hotspot",
    "_derive_trend_score",
    "_derive_persistence_score",
    "_derive_hotspot_stage",
    "_hotspot_group",
    "_display_hotspot_name",
    "_board_frame_contains_topic",
    "_build_hotspot_summary",
    "_build_hotspot_route",
    "_extract_route_date",
    "_parse_change_events",
    "_fetch_ths_summary_event",
    "_fetch_ths_info",
    "_fetch_eastmoney_constituents",
    "_fetch_ths_constituents",
    "_resolve_ths_concept_code",
    "_fallback_constituents",
    "_related_hotspot_constituents",
    "_get_constituent_cache",
    "_set_constituent_cache",
    "_merge_constituent_frames",
    "_enrich_constituent_quotes",
    "_normalize_constituent_records",
)
EXPECTED_PROVIDER_METHOD_METADATA_SHA256 = (
    "dcf692655c07c90229343cbedd86a3b12e1ee826cd2dd8b54a4d1624eba33edf"
)
EXPECTED_PROVIDER_METHOD_AST_SHA256 = (
    "778e5222e78ff2ad45ff8ea4ad0c864f1c30365a61d5519838d24df1054e6252"
)


def _digest(value) -> str:
    payload = json.dumps(value, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _stable_ast_dump(node: ast.AST) -> str:
    # Python 3.12 adds an empty type_params field to function AST nodes.
    return ast.dump(node, include_attributes=False).replace(", type_params=[]", "")


def _class_surface(cls) -> tuple[str, ...]:
    metadata = {
        "__module__",
        "__doc__",
        "__dict__",
        "__weakref__",
        "__firstlineno__",
    }
    return tuple(name for name in vars(cls) if name not in metadata)


def _class_method_metadata(cls) -> list[tuple]:
    metadata = []
    for name, descriptor in vars(cls).items():
        function = (
            descriptor.__func__
            if isinstance(descriptor, (staticmethod, classmethod))
            else descriptor
        )
        if not inspect.isfunction(function):
            continue
        typing.get_type_hints(function)
        metadata.append(
            (
                name,
                type(descriptor).__name__,
                function.__module__,
                function.__qualname__,
                str(inspect.signature(function)),
                function.__globals__ is service_module.__dict__,
                function.__code__.co_freevars,
            )
        )
    return metadata


def test_alphasift_service_module_surface_is_stable():
    module_names = tuple(
        name for name in vars(service_module) if not name.startswith("__")
    )
    public_names = tuple(
        name for name in vars(service_module) if not name.startswith("_")
    )
    assert len(module_names) == 218
    assert len(public_names) == 84
    assert _digest(module_names) == EXPECTED_MODULE_SURFACE_SHA256
    assert _digest(public_names) == EXPECTED_PUBLIC_SURFACE_SHA256
    assert service_module.__annotations__ == EXPECTED_MODULE_ANNOTATIONS


def test_alphasift_top_level_function_metadata_is_stable():
    metadata = []
    for name, value in vars(service_module).items():
        if not inspect.isfunction(value) or value.__module__ != service_module.__name__:
            continue
        typing.get_type_hints(value)
        metadata.append(
            (
                name,
                value.__module__,
                value.__qualname__,
                str(inspect.signature(value)),
                value.__globals__ is service_module.__dict__,
            )
        )
    assert len(metadata) == 128
    assert _digest(tuple(item[0] for item in metadata)) == (
        EXPECTED_TOP_LEVEL_FUNCTION_NAMES_SHA256
    )
    assert _digest(metadata) == EXPECTED_TOP_LEVEL_FUNCTION_METADATA_SHA256


def test_alphasift_service_and_provider_class_surfaces_are_stable():
    service = service_module.AlphaSiftService
    provider = service_module.DsaEastMoneyHotspotProvider

    assert service.__module__ == service_module.__name__
    assert provider.__module__ == service_module.__name__
    assert service.__mro__ == (service, object)
    assert provider.__mro__ == (provider, object)
    assert _class_surface(service) == EXPECTED_SERVICE_SURFACE
    assert _class_surface(provider) == EXPECTED_PROVIDER_SURFACE
    assert _digest(_class_method_metadata(service)) == (
        EXPECTED_SERVICE_METHOD_METADATA_SHA256
    )
    assert _digest(_class_method_metadata(provider)) == (
        EXPECTED_PROVIDER_METHOD_METADATA_SHA256
    )


def test_alphasift_provider_method_ast_is_unchanged():
    source_path = (
        Path(service_module.__file__).parent
        / "alphasift_service_parts"
        / "hotspot_provider.py"
    )
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    provider = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "DsaEastMoneyHotspotProvider"
    )
    methods = [
        node
        for node in provider.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    payload = "\n".join(
        _stable_ast_dump(method)
        for method in methods
    ).encode()
    assert len(methods) == 40
    assert hashlib.sha256(payload).hexdigest() == EXPECTED_PROVIDER_METHOD_AST_SHA256


def test_alphasift_provider_uses_facade_patch_seams(monkeypatch):
    provider = service_module.DsaEastMoneyHotspotProvider()
    monkeypatch.setattr(service_module, "_env_text", lambda _value: "patched")
    monkeypatch.setattr(service_module, "_safe_float", lambda _value: 7.0)

    assert provider._display_hotspot_name("ignored") == "patched"
    assert provider._parse_change_events([{"t": 1, "ct": 2}]) == [
        {"type": 7, "label": "异动类型 7", "count": 7}
    ]


def test_alphasift_service_reload_recreates_facade_bound_provider():
    script = r'''
import importlib
import src.services.alphasift_service as module
import src.services.alphasift_service_parts.hotspot_provider as provider_part

old_class = module.DsaEastMoneyHotspotProvider
old_method = old_class._display_hotspot_name
old_common_params = old_class._COMMON_PARAMS
provider_part.DsaEastMoneyHotspotProvider._display_hotspot_name = lambda *_args: "stale"

first = importlib.reload(module)
first_class = first.DsaEastMoneyHotspotProvider
first_method = first_class._display_hotspot_name
assert first_class is not old_class
assert first_method is not old_method
assert first_class._COMMON_PARAMS is not old_common_params
assert first_method.__module__ == first.__name__
assert first_method.__qualname__ == "DsaEastMoneyHotspotProvider._display_hotspot_name"
assert first_method.__globals__ is vars(first)
assert first_class()._display_hotspot_name("AI") == "AI"

second = importlib.reload(first)
assert second.DsaEastMoneyHotspotProvider is not first_class
assert second.DsaEastMoneyHotspotProvider._display_hotspot_name is not first_method
assert second.DsaEastMoneyHotspotProvider._display_hotspot_name.__globals__ is vars(second)
'''
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
