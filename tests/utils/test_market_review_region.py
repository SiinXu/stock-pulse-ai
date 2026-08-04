# -*- coding: utf-8 -*-
import pytest
from src.utils.market_review_region import (
    MARKET_REVIEW_REGION_ALL,
    normalize_market_review_region_lenient,
    normalize_market_review_region_strict,
)

def test_lenient_defaults_and_both_expansion():
    assert normalize_market_review_region_lenient(None) == "cn"
    assert normalize_market_review_region_lenient("both") == MARKET_REVIEW_REGION_ALL
    assert normalize_market_review_region_lenient("us,cn") == "cn,us"

def test_strict_request_validation_and_ordering():
    assert normalize_market_review_region_strict("US, cn") == "cn,us"
    with pytest.raises(ValueError):
        normalize_market_review_region_strict("cn,both")
