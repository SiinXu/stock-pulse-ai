"""Analysis API stock-input normalization regressions."""

from api.v1.services.analysis_api_service import AnalysisApiService


def _service(index_result):
    return AnalysisApiService(
        resolve_name_to_code=lambda _value: None,
        resolve_index_stock_code_for_analysis=lambda _value: index_result,
    )


def test_analysis_api_unresolved_four_digit_defaults_to_hk() -> None:
    assert _service(None).resolve_and_normalize_input("0941") == "HK00941"


def test_analysis_api_preserves_indexed_jp_precedence() -> None:
    assert _service("7203.T").resolve_and_normalize_input("7203") == "7203.T"


def test_analysis_api_preserves_explicit_suffix_markets() -> None:
    service = AnalysisApiService(
        resolve_name_to_code=lambda _value: None,
        resolve_index_stock_code_for_analysis=lambda value: value,
    )

    assert service.resolve_and_normalize_input("7203.T") == "7203.T"
    assert service.resolve_and_normalize_input("2330.TW") == "2330.TW"
    assert service.resolve_and_normalize_input("005930.KS") == "005930.KS"
