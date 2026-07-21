#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Test generate_index_from_csv.py
"""

import csv
import json
import pytest
from pathlib import Path
from typing import Dict, List

# Add scripts directory to path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / 'scripts'))

from generate_index_from_csv import (
    extract_symbol_from_ts_code,
    get_stock_name,
    get_us_delist_priority,
    parse_stock_row,
    determine_market,
    generate_aliases,
    normalize_name_for_pinyin,
    normalize_stock_name_for_index,
    generate_pinyin,
    main,
    compress_index,
    build_stock_index,
    load_tushare_data,
    load_akshare_data,
)


class TestExtractSymbol:
    """Test Symbol extraction function"""

    def test_a_stock_sz(self):
        """Test A-shares Shenzhen"""
        result = extract_symbol_from_ts_code("000001.SZ", "CN")
        assert result == "000001"

    def test_a_stock_sh(self):
        """Test A-shares Shanghai"""
        result = extract_symbol_from_ts_code("600519.SH", "CN")
        assert result == "600519"

    def test_hk_stock(self):
        """Test Hong Kong stocks."""
        result = extract_symbol_from_ts_code("00700.HK", "HK")
        assert result == "00700"

    def test_us_stock(self):
        """Test US stocks"""
        result = extract_symbol_from_ts_code("AAPL", "US")
        assert result == "AAPL"

    def test_jp_stock_preserves_suffix(self):
        """Test daily stock retains Yahoo suffix to avoid raw code conflicts"""
        result = extract_symbol_from_ts_code("7203.T", "JP")
        assert result == "7203.T"

    def test_kr_stock_preserves_suffix(self):
        """Test retaining Yahoo suffix to avoid bare code conflicts for Korean stocks"""
        result = extract_symbol_from_ts_code("005930.KS", "KR")
        assert result == "005930.KS"

    def test_empty_ts_code(self):
        """Test empty ts_code."""
        result = extract_symbol_from_ts_code("", "CN")
        assert result is None

    def test_none_ts_code(self):
        """Test None ts_code"""
        result = extract_symbol_from_ts_code(None, "CN")
        assert result is None


class TestDetermineMarket:
    """Test market judgment function"""

    def test_a_stock_sz(self):
        """Test A-shares Shenzhen"""
        result = determine_market("000001.SZ")
        assert result == "CN"

    def test_a_stock_sh(self):
        """Test A-shares Shanghai"""
        result = determine_market("600519.SH")
        assert result == "CN"

    def test_hk_stock(self):
        """Test Hong Kong stocks."""
        result = determine_market("00700.HK")
        assert result == "HK"

    def test_bse_stock(self):
        """Test Beijing Stock Exchange (Binance Hong Kong Exchange)"""
        result = determine_market("832566.BJ")
        assert result == "BSE"

    def test_us_stock(self):
        """Test US stocks"""
        result = determine_market("AAPL")
        assert result == "US"

    def test_us_stock_tesla(self):
        """Test US stock Tesla"""
        result = determine_market("TSLA")
        assert result == "US"

    def test_us_stock_with_dot_suffix(self):
        """Test US stock with dot suffix (BRK.B)"""
        result = determine_market("BRK.B")
        assert result == "US"

    def test_us_stock_class_a(self):
        """Test US stocks A shares (GOOG.A)"""
        result = determine_market("GOOG.A")
        assert result == "US"

    def test_us_stock_units(self):
        """Test US stocks Unit (AAPL.U)"""
        result = determine_market("AAPL.U")
        assert result == "US"

    def test_jp_stock_with_yahoo_suffix(self):
        """Test the Yahoo suffix for Japanese stocks."""
        result = determine_market("7203.T")
        assert result == "JP"

    def test_kr_kospi_stock_with_yahoo_suffix(self):
        """Test KOSPI Yahoo suffix for Korean stocks"""
        result = determine_market("005930.KS")
        assert result == "KR"

    def test_kr_kosdaq_stock_with_yahoo_suffix(self):
        """Test KOSDAQ Yahoo suffix for Korean stocks"""
        result = determine_market("035720.KQ")
        assert result == "KR"


class TestGetStockName:
    """Test stock name retrieval function"""

    def test_cn_stock_name(self):
        """Test A-shares using the name field"""
        row = {'name': '平安银行', 'enname': 'Ping An Bank'}
        result = get_stock_name(row, 'CN')
        assert result == '平安银行'

    def test_hk_stock_name(self):
        """Test Hong Kong stocks using the name field."""
        row = {'name': '腾讯控股', 'enname': 'Tencent'}
        result = get_stock_name(row, 'HK')
        assert result == '腾讯控股'

    def test_us_stock_name(self):
        """Test US stocks using enname field"""
        row = {'name': '苹果', 'enname': 'Apple Inc.'}
        result = get_stock_name(row, 'US')
        assert result == 'Apple Inc.'

    def test_empty_name(self):
        """Test empty name"""
        row = {'name': '', 'enname': ''}
        result = get_stock_name(row, 'CN')
        assert result is None

    def test_cn_stock_name_strips_ex_rights_prefix(self):
        """Test A-shares short-term delisting/dividend adjustment prefix will not be written to the long-term index name"""
        row = {'name': 'XD西藏药', 'enname': ''}
        result = get_stock_name(row, 'CN')
        assert result == '西藏药'

    def test_cn_stock_name_preserves_new_stock_prefix(self):
        """Test A-shares new stock prefix is preserved, waiting for subsequent data package refresh to naturally disappear"""
        row = {'name': 'N惠康', 'enname': ''}
        result = get_stock_name(row, 'CN')
        assert result == 'N惠康'


class TestDataCleaning:
    """Testing data cleaning logic"""

    def test_valid_cn_stock(self):
        """Test valid A-shares records"""
        row = {
            'ts_code': '000001.SZ',
            'symbol': '000001',
            'name': '平安银行'
        }
        result = parse_stock_row(row, 'CN')
        assert result is not None
        assert result['ts_code'] == '000001.SZ'
        assert result['symbol'] == '000001'
        assert result['name'] == '平安银行'
        assert result['market'] == 'CN'

    def test_valid_hk_stock(self):
        """Test valid Hong Kong stocks records"""
        row = {
            'ts_code': '00700.HK',
            'name': '腾讯控股',
            'enname': 'Tencent'
        }
        result = parse_stock_row(row, 'HK')
        assert result is not None
        assert result['ts_code'] == '00700.HK'
        assert result['symbol'] == '00700'
        assert result['name'] == '腾讯控股'
        assert result['market'] == 'HK'

    def test_valid_us_stock(self):
        """Test valid US stocks records"""
        row = {
            'ts_code': 'AAPL',
            'name': '苹果',
            'enname': 'Apple Inc.'
        }
        result = parse_stock_row(row, 'US')
        assert result is not None
        assert result['ts_code'] == 'AAPL'
        assert result['symbol'] == 'AAPL'
        assert result['name'] == 'Apple Inc.'
        assert result['market'] == 'US'

    def test_valid_us_stock_with_dot_suffix(self):
        """Test valid US stocks records (with dot suffix, such as BRK.B)"""
        row = {
            'ts_code': 'BRK.B',
            'name': '',
            'enname': "BERKSHIRE HATHAWAY 'B'"
        }
        result = parse_stock_row(row, None)
        assert result is not None
        assert result['ts_code'] == 'BRK.B'
        assert result['symbol'] == 'BRK.B'
        assert result['name'] == "BERKSHIRE HATHAWAY 'B'"
        assert result['market'] == 'US'

    def test_valid_jp_stock_with_seed_aliases(self):
        """Test valid daily seed records"""
        row = {
            'ts_code': '7203.T',
            'name': '丰田汽车',
            'enname': 'Toyota Motor Corporation',
            'aliases': 'Toyota|Toyota Motor|丰田'
        }
        result = parse_stock_row(row, 'JP')
        assert result is not None
        assert result['ts_code'] == '7203.T'
        assert result['symbol'] == '7203.T'
        assert result['name'] == '丰田汽车'
        assert result['market'] == 'JP'
        assert result['aliases'] == ['Toyota', 'Toyota Motor', '丰田']

    def test_valid_kr_stock_with_seed_aliases(self):
        """Test valid Korean seed records"""
        row = {
            'ts_code': '005930.KS',
            'name': '三星电子',
            'enname': 'Samsung Electronics',
            'aliases': 'Samsung|Samsung Electronics|三星'
        }
        result = parse_stock_row(row, 'KR')
        assert result is not None
        assert result['ts_code'] == '005930.KS'
        assert result['symbol'] == '005930.KS'
        assert result['name'] == '三星电子'
        assert result['market'] == 'KR'
        assert result['aliases'] == ['Samsung', 'Samsung Electronics', '三星']

    def test_us_dummy_filtered(self):
        """Test filtered DUMMY records for US stocks"""
        row = {
            'ts_code': 'DUMMY001',
            'name': '测试',
            'enname': 'DUMMY Test Stock'
        }
        result = parse_stock_row(row, 'US')
        assert result is None

    def test_us_dummy_case_insensitive(self):
        """Test DUMMY filter is case-insensitive"""
        row = {
            'ts_code': 'DUMMY002',
            'name': '测试',
            'enname': 'dummy test stock'
        }
        result = parse_stock_row(row, 'US')
        assert result is None

    def test_empty_ts_code(self):
        """Test empty ts_code is filtered."""
        row = {
            'ts_code': '',
            'symbol': '000001',
            'name': '平安银行'
        }
        result = parse_stock_row(row, 'CN')
        assert result is None

    def test_empty_name(self):
        """Test empty name filtering"""
        row = {
            'ts_code': '000001.SZ',
            'symbol': '000001',
            'name': ''
        }
        result = parse_stock_row(row, 'CN')
        assert result is None

    def test_us_empty_enname(self):
        """Test US stock empty enname is filtered"""
        row = {
            'ts_code': 'AAPL',
            'name': '苹果',
            'enname': ''
        }
        result = parse_stock_row(row, 'US')
        assert result is None

    def test_us_delist_priority_prefers_blank_over_nat(self):
        """Test US stock deduplication priority: empty delist_date takes precedence over NaT"""
        assert get_us_delist_priority({'delist_date': ''}) == 2
        assert get_us_delist_priority({'delist_date': 'NaT'}) == 1
        assert get_us_delist_priority({'delist_date': '20250131'}) == 0


class TestNormalizeStockNameForIndex:
    """Test index name normalization"""

    def test_strips_a_share_ex_rights_prefixes(self):
        assert normalize_stock_name_for_index('XD西藏药', 'CN') == '西藏药'
        assert normalize_stock_name_for_index('XR示例股', 'CN') == '示例股'
        assert normalize_stock_name_for_index('DR罗曼股', 'CN') == '罗曼股'
        assert normalize_stock_name_for_index('XD朱老六', 'BSE') == '朱老六'

    def test_preserves_a_share_new_stock_and_st_prefixes(self):
        assert normalize_stock_name_for_index('N惠康', 'CN') == 'N惠康'
        assert normalize_stock_name_for_index('C天海', 'CN') == 'C天海'
        assert normalize_stock_name_for_index('ST海王', 'CN') == 'ST海王'
        assert normalize_stock_name_for_index('*ST美丽', 'CN') == '*ST美丽'

    def test_does_not_strip_other_markets(self):
        assert normalize_stock_name_for_index('DRAGONFLY ENERGY', 'US') == 'DRAGONFLY ENERGY'
        assert normalize_stock_name_for_index('XD港股示例', 'HK') == 'XD港股示例'


class TestAliases:
    """Test alias generation function"""

    def test_cn_aliases(self):
        """Test A-shares alias"""
        result = generate_aliases('贵州茅台', 'CN')
        assert '茅台' in result

    def test_hk_aliases(self):
        """Test Hong Kong stock aliases."""
        result = generate_aliases('腾讯控股', 'HK')
        assert '腾讯' in result or 'Tencent' in result

    def test_us_aliases(self):
        """Test US stock aliases"""
        result = generate_aliases('Apple Inc.', 'US')
        assert 'Apple' in result or 'AAPL' in result

    def test_no_aliases(self):
        """Testing cases without aliases"""
        result = generate_aliases('未知股票', 'CN')
        assert result == []


class TestOutputFormat:
    """Test output format."""

    def test_compress_index_field_order(self):
        """Test field order of compression format"""
        index = [{
            "canonicalCode": "000001.SZ",
            "displayCode": "000001",
            "nameZh": "平安银行",
            "pinyinFull": "pinganyinhang",
            "pinyinAbbr": "pyyh",
            "aliases": ["平银"],
            "market": "CN",
            "assetType": "stock",
            "active": True,
            "popularity": 100,
        }]

        compressed = compress_index(index)

        assert len(compressed) == 1
        item = compressed[0]

        # Validate field order
        assert item[0] == "000001.SZ"      # canonicalCode
        assert item[1] == "000001"         # displayCode
        assert item[2] == "平安银行"       # nameZh
        assert item[3] == "pinganyinhang"  # pinyinFull
        assert item[4] == "pyyh"           # pinyinAbbr
        assert item[5] == ["平银"]         # aliases
        assert item[6] == "CN"             # market
        assert item[7] == "stock"          # assetType
        assert item[8] == True             # active
        assert item[9] == 100              # popularity

    def test_compress_index_field_count(self):
        """Test field count of compression format"""
        index = [{
            "canonicalCode": "AAPL",
            "displayCode": "AAPL",
            "nameZh": "Apple Inc.",
            "pinyinFull": None,
            "pinyinAbbr": None,
            "aliases": [],
            "market": "US",
            "assetType": "stock",
            "active": True,
            "popularity": 100,
        }]

        compressed = compress_index(index)
        assert len(compressed[0]) == 10  # 10 fields

    def test_json_serialization(self):
        """Test JSON serialization"""
        index = [{
            "canonicalCode": "00700.HK",
            "displayCode": "00700",
            "nameZh": "腾讯控股",
            "pinyinFull": "xunxiongkonggu",
            "pinyinAbbr": "xxkg",
            "aliases": ["腾讯"],
            "market": "HK",
            "assetType": "stock",
            "active": True,
            "popularity": 100,
        }]

        compressed = compress_index(index)

        # Should successfully serialize to JSON
        json_str = json.dumps(compressed, ensure_ascii=False)
        assert json_str is not None

        # Should successfully deserialize
        loaded = json.loads(json_str)
        assert len(loaded) == 1


class TestIntegration:
    """Integration testing"""

    def test_full_workflow_tushare(self, tmp_path):
        """Test the complete Tushare workflow"""
        # Create test CSV file
        a_csv = tmp_path / 'stock_list_a.csv'
        with open(a_csv, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['ts_code', 'symbol', 'name'])
            writer.writeheader()
            writer.writerow({
                'ts_code': '000001.SZ',
                'symbol': '000001',
                'name': '平安银行'
            })

        hk_csv = tmp_path / 'stock_list_hk.csv'
        with open(hk_csv, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['ts_code', 'name', 'enname'])
            writer.writeheader()
            writer.writerow({
                'ts_code': '00700.HK',
                'name': '腾讯控股',
                'enname': 'Tencent'
            })

        us_csv = tmp_path / 'stock_list_us.csv'
        with open(us_csv, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['ts_code', 'name', 'enname'])
            writer.writeheader()
            writer.writerow({
                'ts_code': 'AAPL',
                'name': '苹果',
                'enname': 'Apple Inc.'
            })

        jp_csv = tmp_path / 'stock_list_jp.csv'
        with open(jp_csv, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['ts_code', 'name', 'enname', 'aliases'])
            writer.writeheader()
            writer.writerow({
                'ts_code': '7203.T',
                'name': '丰田汽车',
                'enname': 'Toyota Motor Corporation',
                'aliases': 'Toyota|丰田'
            })

        kr_csv = tmp_path / 'stock_list_kr.csv'
        with open(kr_csv, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['ts_code', 'name', 'enname', 'aliases'])
            writer.writeheader()
            writer.writerow({
                'ts_code': '005930.KS',
                'name': '三星电子',
                'enname': 'Samsung Electronics',
                'aliases': 'Samsung|三星'
            })

        # Load data
        stocks = load_tushare_data(tmp_path)

        # Data validation
        assert len(stocks) == 5

        # Build index
        index = build_stock_index(stocks)

        # Validate index
        assert len(index) == 5
        assert next(item for item in index if item['canonicalCode'] == '7203.T')['aliases'] == ['Toyota', '丰田']
        assert next(item for item in index if item['canonicalCode'] == '005930.KS')['aliases'] == ['Samsung', '三星']

        # Index compression
        compressed = compress_index(index)

        # Validate compression
        assert len(compressed) == 5

        # Validate the number of fields
        for item in compressed:
            assert len(item) == 10

    def test_market_distribution(self, tmp_path):
        """Test market distribution statistics"""
        # Create test data
        csv_file = tmp_path / 'stock_list_a.csv'
        with open(csv_file, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=['ts_code', 'symbol', 'name'])
            writer.writeheader()
            writer.writerow({'ts_code': '000001.SZ', 'symbol': '000001', 'name': '平安银行'})
            writer.writerow({'ts_code': '600519.SH', 'symbol': '600519', 'name': '贵州茅台'})
            writer.writerow({'ts_code': '832566.BJ', 'symbol': '832566', 'name': '梓撞科技'})

        stocks = load_tushare_data(tmp_path)
        index = build_stock_index(stocks)

        # Statistics market distribution
        market_stats = {}
        for item in index:
            market = item['market']
            market_stats[market] = market_stats.get(market, 0) + 1

        # Verification Statistics
        assert market_stats.get('CN', 0) == 2  # SZ, SH
        assert market_stats.get('BSE', 0) == 1  # BJ

    def test_us_reused_symbols_are_deduplicated(self, tmp_path):
        """Test US stock ticker reuse will first deduplicate when loading"""
        us_csv = tmp_path / 'stock_list_us.csv'
        with open(us_csv, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(
                f,
                fieldnames=['ts_code', 'name', 'enname', 'list_date', 'delist_date']
            )
            writer.writeheader()
            writer.writerow({
                'ts_code': 'B',
                'name': '',
                'enname': 'BARNES GROUP',
                'list_date': '19631014',
                'delist_date': 'NaT',
            })
            writer.writerow({
                'ts_code': 'B',
                'name': '',
                'enname': 'BARRICK MINING (NYS)',
                'list_date': '19850213',
                'delist_date': '',
            })
            writer.writerow({
                'ts_code': 'DOC',
                'name': '',
                'enname': 'HEALTHPEAK PROPERTIES',
                'list_date': '19850523',
                'delist_date': '',
            })
            writer.writerow({
                'ts_code': 'DOC',
                'name': '',
                'enname': 'PHYSICIANS REALTY TST.',
                'list_date': '20130719',
                'delist_date': '',
            })
            writer.writerow({
                'ts_code': 'SPWR',
                'name': '',
                'enname': 'COMPLETE SOLARIA',
                'list_date': '20210419',
                'delist_date': '',
            })
            writer.writerow({
                'ts_code': 'SPWR',
                'name': '',
                'enname': 'SUNPOWER',
                'list_date': '20051109',
                'delist_date': 'NaT',
            })

        stocks = load_tushare_data(tmp_path)

        assert len(stocks) == 3
        assert {stock['ts_code'] for stock in stocks} == {'B', 'DOC', 'SPWR'}
        assert next(stock for stock in stocks if stock['ts_code'] == 'B')['name'] == 'BARRICK MINING (NYS)'
        assert next(stock for stock in stocks if stock['ts_code'] == 'DOC')['name'] == 'HEALTHPEAK PROPERTIES'
        assert next(stock for stock in stocks if stock['ts_code'] == 'SPWR')['name'] == 'COMPLETE SOLARIA'


class TestPinyin:
    """Testing phonetic generation"""

    def test_normalize_name(self):
        """Test name standardization"""
        # Test ST prefix removal
        result = normalize_name_for_pinyin('*ST平安')
        assert 'ST' not in result

        # Test removing N prefixes
        result = normalize_name_for_pinyin('N平安银行')
        assert 'N' not in result

    def test_generate_pinyin(self):
        """Testing phonetic generation"""
        pinyin_full, pinyin_abbr = generate_pinyin('平安银行')
        assert pinyin_full == 'pinganyinhang'
        assert pinyin_abbr == 'payh'

    def test_generate_pinyin_requires_dependency(self, monkeypatch):
        """Test that no fallback pinyin field is generated when pypinyin is missing"""
        import generate_index_from_csv

        monkeypatch.setattr(generate_index_from_csv, 'PYPINYIN_AVAILABLE', False)

        with pytest.raises(RuntimeError, match='pypinyin is required'):
            generate_index_from_csv.generate_pinyin('平安银行')

    def test_main_fails_without_pypinyin(self, monkeypatch):
        """Test must have pypinyin before generating the index."""
        import generate_index_from_csv

        monkeypatch.setattr(generate_index_from_csv, 'PYPINYIN_AVAILABLE', False)
        monkeypatch.setattr(sys, 'argv', ['generate_index_from_csv.py'])

        assert main() == 1
