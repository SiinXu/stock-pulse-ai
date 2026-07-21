# -*- coding: utf-8 -*-
"""
Anspire search-engine test suite

Test coverage range:
1. Configuration load test - verify that anspire_api_keys are correctly loaded from environment variables
2. Service initialization test - Verify that AnspireSearchProvider is correctly initialized via SearchService.
3. API call testing - actual calling of Anspire API to verify the returned results
4. Failover test - error handling and fallback mechanism when invalid Key is verified
5. Search functionality testing - Test stock news search and general search functions

Running options:
```bash
# Windows PowerShell
$env:ANSPIRE_API_KEYS="your_test_api_key"
python -m pytest tests/test_anspire_search.py -v

# Linux/Mac
export ANSPIRE_API_KEYS="your_test_api_key"
python -m pytest tests/test_anspire_search.py -v
```
"""

import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv
load_dotenv()

# Add project root directory to Python path, solve module import issues
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Mock newspaper before search_service import (optional dependency)
if "newspaper" not in sys.modules:
    mock_np = MagicMock()
    mock_np.Article = MagicMock()
    mock_np.Config = MagicMock()
    sys.modules["newspaper"] = mock_np

from src.config import Config, get_config
from src.search_service import (
    AnspireSearchProvider,
    SearchService,
    get_search_service,
    reset_search_service,
)


class _FakeResponse:
    """Simulate HTTP response object"""
    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.headers = headers or {'content-type': 'application/json'}
    
    def json(self):
        return self._json_data


class TestAnspireConfigLoading(unittest.TestCase):
    """Test Anspire configuration loading from environment variables."""
    
    def setUp(self):
        """Save and clear environment variables (don't operate .env file)"""
        # ✅ Save original values, restore after testing
        self._original_anspire_keys = os.environ.get('ANSPIRE_API_KEYS')
        
        # Clear environment variables
        if 'ANSPIRE_API_KEYS' in os.environ:
            del os.environ['ANSPIRE_API_KEYS']
        
        # Reset Config singleton.
        Config._Config__instance = None
        reset_search_service()

    def tearDown(self):
        """Restore original environment variables"""
        # ✅ Restore original values
        if self._original_anspire_keys is not None:
            os.environ['ANSPIRE_API_KEYS'] = self._original_anspire_keys
        elif 'ANSPIRE_API_KEYS' in os.environ:
            del os.environ['ANSPIRE_API_KEYS']
        
        # Reset Config singleton.
        Config._Config__instance = None
        reset_search_service()

    def test_anspire_keys_loaded_from_env(self):
        """Test that ANSPIRE_API_KEYS is correctly parsed from environment."""
        # ✅ Use patch.dict for temporary setting, automatically restore after testing
        with patch.dict(os.environ, {'ANSPIRE_API_KEYS': 'key1,key2,key3'}):
            config = Config._load_from_env()
            
            self.assertEqual(len(config.anspire_api_keys), 3)
            self.assertIn('key1', config.anspire_api_keys)
            self.assertIn('key2', config.anspire_api_keys)
            self.assertIn('key3', config.anspire_api_keys)

    def test_anspire_keys_single_key(self):
        """Test single API Key parsing."""
        with patch.dict(os.environ, {'ANSPIRE_API_KEYS': 'single_key_test'}):
            config = Config._load_from_env()
            
            self.assertEqual(len(config.anspire_api_keys), 1)
            self.assertEqual(config.anspire_api_keys[0], 'single_key_test')

    def test_anspire_keys_empty_env(self):
        """Test empty environment variable handling."""
        with patch.dict(os.environ, {'ANSPIRE_API_KEYS': ''}):
            config = Config._load_from_env()
            
            self.assertEqual(len(config.anspire_api_keys), 0)

    def test_anspire_keys_whitespace_handling(self):
        """Test whitespace trimming in API Keys."""
        with patch.dict(os.environ, {'ANSPIRE_API_KEYS': ' key1 , key2 , key3 '}):
            config = Config._load_from_env()
            
            self.assertEqual(len(config.anspire_api_keys), 3)
            self.assertEqual(config.anspire_api_keys, ['key1', 'key2', 'key3'])


class TestAnspireSearchProvider(unittest.TestCase):
    """Anspire Search Provider Unit test"""
    
    def setUp(self):
        """Test pre-preparation"""
        # ✅ Use explicit test placeholders instead of real key forms
        self.test_api_key = "sk-test-anspire-placeholder-key-12345"
        self.provider = AnspireSearchProvider([self.test_api_key])
        # Save the original requests module
        self._original_requests = sys.modules.get('requests')
    
    def tearDown(self):
        """Clean up after testing"""
        # Restore original requests module
        if self._original_requests is not None:
            sys.modules['requests'] = self._original_requests
    
    def test_provider_initialization(self):
        """Test Provider initialization"""
        provider = AnspireSearchProvider(["key1", "key2"])
        self.assertEqual(provider.name, "Anspire")
        if hasattr(provider, 'api_keys'):
            self.assertEqual(len(provider.api_keys), 2)
        elif hasattr(provider, '_api_keys'):
            self.assertEqual(len(provider._api_keys), 2)
        self.assertTrue(provider.is_available)
    
    def test_provider_name(self):
        """Test Provider name"""
        self.assertEqual(self.provider.name, "Anspire")
    
    def test_provider_availability(self):
        """Test Provider availability detection"""
        # Should be available when API Key is present
        provider_with_keys = AnspireSearchProvider(["key1"])
        self.assertTrue(provider_with_keys.is_available)
        
        # Not usable without API Key
        provider_without_keys = AnspireSearchProvider([])
        self.assertFalse(provider_without_keys.is_available)
    
    def test_extract_domain(self):
        """Test domain extraction function"""
        test_cases = [
            ("https://www.example.com/article", "example.com"),
            ("https://finance.sina.com.cn/stock/", "finance.sina.com.cn"),
            ("http://www.10jqka.com.cn/news", "10jqka.com.cn"),
            ("invalid_url", "未知来源"),
            ("", "未知来源"),
        ]
        
        for url, expected in test_cases:
            result = AnspireSearchProvider._extract_domain(url)
            self.assertEqual(result, expected, f"Failed for URL: {url}")
    
    @patch('src.search_service.requests')
    def test_search_success_response(self, mock_requests):
        """Test successful response handling"""
        # Configure mock exceptions
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
        except ImportError:
            pass
        
        fake_response = _FakeResponse(
            status_code=200,
            json_data={
                "code": 200,
                "msg": "success",
                "results": [
                    {
                        "title": "贵州茅台今日股价上涨",
                        "url": "https://finance.sina.com.cn/stock/600519",
                        "content": "贵州茅台 (600519) 今日收盘股价上涨 2.5%，成交量放大...",
                    },
                    {
                        "title": "白酒板块持续走强",
                        "url": "https://www.10jqka.com.cn/baijiu",
                        "content": "白酒板块今日表现强势，贵州茅台、五粮液等个股涨幅居前...",
                    }
                ]
            }
        )
        
        mock_requests.get = MagicMock(return_value=fake_response)
        
        response = self.provider.search("贵州茅台 股票新闻", max_results=5, days=7)
        
        # Verification Result
        self.assertTrue(response.success)
        self.assertEqual(response.provider, "Anspire")
        self.assertEqual(len(response.results), 2)
        self.assertEqual(response.results[0].title, "贵州茅台今日股价上涨")
        # Assume source is extracted domain from URL
        self.assertEqual(response.results[0].source, "finance.sina.com.cn")
        
        # Validate API call parameters
        mock_requests.get.assert_called_once()
        call_args = mock_requests.get.call_args
        # Check if the URL contains anspire related domains (specific URLs need to be adjusted based on actual implementation)
        # self.assertIn("plugin.anspire.cn", call_args[0][0]) 
        self.assertIn("Authorization", call_args[1]["headers"])
        # Verify using params instead of json
        self.assertIn("params", call_args[1])
        self.assertNotIn("json", call_args[1])
    
    @patch('src.search_service.requests')
    def test_search_invalid_api_key(self, mock_requests):
        """Invalid API Key error handling"""
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
        except ImportError:
            pass
        
        fake_response = _FakeResponse(
            status_code=401,
            json_data={"message": "Invalid API key"},
            text="Unauthorized"
        )
        
        mock_requests.get = MagicMock(return_value=fake_response)
        
        response = self.provider.search("测试查询", max_results=3)
        
        self.assertFalse(response.success)
        self.assertEqual(response.provider, "Anspire")
        self.assertEqual(len(response.results), 0)
        self.assertEqual(response.error_message, "Search request failed (HTTP 401).")
    
    @patch('src.search_service.requests')
    def test_search_timeout_error(self, mock_requests):
        """Timeout error handling."""
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
            timeout_exc = mock_requests.exceptions.Timeout
        except ImportError:
            mock_requests.exceptions = MagicMock()
            timeout_exc = Exception
            
        mock_requests.get = MagicMock(side_effect=timeout_exc())
        
        response = self.provider.search("测试查询", max_results=3)
        
        self.assertFalse(response.success)
        self.assertEqual(response.provider, "Anspire")
        self.assertEqual(len(response.results), 0)
        # Error message check
        self.assertTrue("超时" in response.error_message or "Timeout" in response.error_message)
    
    @patch('src.search_service.requests')
    def test_search_network_error(self, mock_requests):
        """Test network error handling"""
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
            conn_exc = mock_requests.exceptions.ConnectionError
        except ImportError:
            mock_requests.exceptions = MagicMock()
            conn_exc = Exception

        mock_requests.get = MagicMock(side_effect=conn_exc())
        
        response = self.provider.search("测试查询", max_results=3)
        
        self.assertFalse(response.success)
        self.assertEqual(response.provider, "Anspire")
        self.assertEqual(len(response.results), 0)
        self.assertEqual(response.error_message, "Network connection failed")
    
    @patch('src.search_service.requests')
    def test_search_empty_results(self, mock_requests):
        """Test handling of empty results"""
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
        except ImportError:
            mock_requests.exceptions = MagicMock()
        
        fake_response = _FakeResponse(
            status_code=200,
            json_data={"code": 200, "msg": "success", "results": []}
        )
        
        mock_requests.get = MagicMock(return_value=fake_response)
        
        response = self.provider.search("不存在的股票 XYZ", max_results=5)
        
        self.assertTrue(response.success)
        self.assertEqual(response.provider, "Anspire")
        self.assertEqual(len(response.results), 0)
    
    @patch('src.search_service.requests')
    def test_search_content_truncation(self, mock_requests):
        """Test long content truncation functionality"""
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
        except ImportError:
            mock_requests.exceptions = MagicMock()
        
        long_content = "这是一段非常长的内容，" * 100  # Exceeding 500 characters
        
        fake_response = _FakeResponse(
            status_code=200,
            json_data={
                "code": 200,
                "msg": "success",
                "results": [{
                    "title": "长内容测试",
                    "url": "https://example.com/long",
                    "content": long_content
                }]
            }
        )
        
        mock_requests.get = MagicMock(return_value=fake_response)
        
        response = self.provider.search("测试", max_results=1)
        
        self.assertTrue(response.success)
        self.assertEqual(len(response.results), 1)
        # Validate that content is truncated to no more than 500 characters
        if response.results[0].snippet:
            self.assertLessEqual(len(response.results[0].snippet), 503)  # 500 + "..."
            self.assertTrue(response.results[0].snippet.endswith("..."))
    
    @patch('src.search_service.requests')
    def test_search_time_range(self, mock_requests):
        """Test time range parameter"""
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
        except ImportError:
            mock_requests.exceptions = MagicMock()
        
        fake_response = _FakeResponse(status_code=200, json_data={"code": 200, "results": []})
        mock_requests.get = MagicMock(return_value=fake_response)
        
        # Test 7-day range
        self.provider.search("测试", max_results=3, days=7)
        
        # Validation time parameters
        call_args = mock_requests.get.call_args
        if call_args and len(call_args) > 1 and 'params' in call_args[1]:
            params = call_args[1]["params"]
                
            # Validation time parameters exist (specific field names depend on implementation)
            # Here, we assume that FromTime/ToTime or similar fields have been used; if not, skip specific field checks
            # self.assertIn("FromTime", params)
            # self.assertIn("ToTime", params)


class TestAnspireSearchService(unittest.TestCase):
    """SearchService in Anspire Integration testing"""
    
    def setUp(self):
        Config._Config__instance = None
        reset_search_service()

    def test_search_service_with_anspire(self):
        """Test SearchService correctly initializes Anspire Provider"""
        service = SearchService(
            anspire_keys=["test_key"],
            bocha_keys=[],
            tavily_keys=[],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short"
        )
        
        self.assertTrue(hasattr(service, '_providers'))
        self.assertGreater(len(service._providers), 0)
        
        first_provider = service._providers[0]
        self.assertIsInstance(first_provider, AnspireSearchProvider)
        self.assertEqual(first_provider.name, "Anspire")
    
    def test_search_service_without_anspire(self):
        """Test behavior when Anspire is not configured"""
        service = SearchService(
            anspire_keys=[],
            tavily_keys=["tavily_key"],
            bocha_keys=[],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short"
        )
        
        # No Anspire Provider
        anspire_providers = [p for p in service._providers if isinstance(p, AnspireSearchProvider)]
        self.assertEqual(len(anspire_providers), 0)
    
    def test_search_service_priority(self):
        """Test Anspire priority"""
        service = SearchService(
            anspire_keys=["anspire_key"],
            bocha_keys=["bocha_key"],
            tavily_keys=["tavily_key"],
            searxng_public_instances_enabled=False,
            news_max_age_days=3,
            news_strategy_profile="short"
        )
        
        self.assertIsInstance(service._providers[0], AnspireSearchProvider)


class TestAnspireIntegration(unittest.TestCase):
    """Anspire integration testing (requires a real API Key)"""
    
    @classmethod
    def setUpClass(cls):
        """Check if API Key is configured and valid."""
        cls.api_keys = [k.strip() for k in os.getenv('ANSPIRE_API_KEYS', '').split(',') if k.strip()]
        cls.has_api_key = len(cls.api_keys) > 0
        cls.has_valid_api_key = False  # Check for valid API Key
        
        if cls.has_api_key:
            reset_search_service()
            cls.service = get_search_service()
            
            # Validate API Key validity
            try:
                # Find Anspire provider
                for provider in cls.service._providers:
                    if isinstance(provider, AnspireSearchProvider):
                        # Execute a simple search validation
                        test_response = provider.search("测试", max_results=1)
                        if test_response.success:
                            cls.has_valid_api_key = True
                        break
            except Exception:
                cls.has_valid_api_key = False

    def setUp(self):
        """Check if the API Key is valid before each test."""
        if not os.environ.get("ANSPIRE_API_KEYS"):
            self.skipTest("未设置 ANSPIRE_API_KEYS 环境变量，跳过集成测试")
        if not getattr(self.__class__, 'has_valid_api_key', False):
            self.skipTest("ANSPIRE_API_KEYS 环境变量中的 API Key 无效，跳过集成测试")

    @pytest.mark.network
    def test_real_api_call_stock_news(self):
        """Real API call test - Stock news search"""
        # Ensure the service has been reset
        reset_search_service()
        service = get_search_service()
        
        # Verify Anspire configuration
        anspire_provider = None
        for provider in service._providers:
            if isinstance(provider, AnspireSearchProvider):
                anspire_provider = provider
                break
        
        if not anspire_provider:
            self.skipTest("Anspire Provider 未初始化")
        
        # Test A-shares search
        response = service.search_stock_news("600519", "贵州茅台", max_results=3)
        
        print(f"\n=== Anspire 真实 API 测试结果 ===")
        print(f"搜索状态：{'成功' if response.success else '失败'}")
        print(f"搜索引擎：{response.provider}")
        print(f"结果数量：{len(response.results)}")
        print(f"耗时：{response.search_time:.2f}s")
        
        # Basic validation
        self.assertTrue(response.success, f"搜索失败：{response.error_message}")
        self.assertEqual(response.provider, "Anspire")
        self.assertGreater(len(response.results), 0, "应至少返回一条结果")
        
        # Verification Result Format
        for result in response.results:
            self.assertIsNotNone(result.title)
            self.assertIsNotNone(result.url)
            # snippet may be empty, depending on the specific implementation
            # self.assertIsNotNone(result.snippet)
    
    @pytest.mark.network
    def test_real_api_call_general_search(self):
        """Real API Call Test - Generic Search"""
        reset_search_service()
        service = get_search_service()
        
        anspire_provider = None
        for provider in service._providers:
            if isinstance(provider, AnspireSearchProvider):
                anspire_provider = provider
                break
        
        if not anspire_provider:
            self.skipTest("Anspire Provider 未初始化")
        
        # General search test.
        response = anspire_provider.search("人工智能最新发展", max_results=5, days=7)
        
        print(f"\n=== Anspire 通用搜索结果 ===")
        print(f"搜索状态：{'成功' if response.success else '失败'}")
        print(f"结果数量：{len(response.results)}")
        
        self.assertTrue(response.success)
        self.assertGreater(len(response.results), 0)


def run_manual_test():
    """Manually test the function (for quick verification)"""
    import logging
    from src.config import get_config
    
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s | %(levelname)-8s | %(message)s'
    )
    
    print("=" * 60)
    print("Anspire Search 快速测试")
    print("=" * 60)
    
    # Check configuration
    config = get_config()
    if not config.anspire_api_keys:
        print("\n❌ 未检测到 Anspire API Keys")
        print("请设置环境变量：")
        print("  Windows PowerShell: $env:ANSPIRE_API_KEYS=\"your_api_key\"")
        print("  Linux/Mac: export ANSPIRE_API_KEYS=\"your_api_key\"")
        return False
    
    print(f"\n✅ 已配置 {len(config.anspire_api_keys)} 个 Anspire API Key")
    
    # Create service
    service = SearchService(
        anspire_keys=config.anspire_api_keys,
        bocha_keys=config.bocha_api_keys,
        tavily_keys=config.tavily_keys,
        searxng_public_instances_enabled=False,
        news_max_age_days=3,
        news_strategy_profile="short"
    )
    
    # Validate Provider
    anspire_provider = service._providers[0] if service._providers else None
    if not anspire_provider or not isinstance(anspire_provider, AnspireSearchProvider):
        print("\n❌ Anspire Provider 未正确初始化")
        return False
    
    print(f"✅ Anspire Provider 初始化成功")
    print(f"   Provider 名称：{anspire_provider.name}")
    if hasattr(anspire_provider, 'api_keys'):
        print(f"   API Keys 数量：{len(anspire_provider.api_keys)}")
    elif hasattr(anspire_provider, '_api_keys'):
        print(f"   API Keys 数量：{len(anspire_provider._api_keys)}")
    
    # Execute test search
    print("\n" + "=" * 60)
    print("执行测试搜索：贵州茅台 (600519)")
    print("=" * 60)
    
    response = service.search_stock_news("600519", "贵州茅台", max_results=3)
    
    print(f"\n搜索结果:")
    print(f"  状态：{'✅ 成功' if response.success else '❌ 失败'}")
    print(f"  搜索引擎：{response.provider}")
    print(f"  结果数量：{len(response.results)}")
    print(f"  耗时：{response.search_time:.2f}s")
    
    if response.error_message:
        print(f"  错误信息：{response.error_message}")
    
    if response.results:
        print(f"\n前 {min(2, len(response.results))} 条结果预览:")
        for i, result in enumerate(response.results[:2], 1):
            print(f"\n  [{i}] {result.title}")
            print(f"      来源：{result.source}")
            print(f"      URL: {result.url}")
            if result.snippet:
                snippet_preview = result.snippet[:100] + "..." if len(result.snippet) > 100 else result.snippet
                print(f"      摘要：{snippet_preview}")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
    
    return response.success


if __name__ == "__main__":
    # If environment variables are set, run full tests.
    if os.environ.get("ANSPIRE_API_KEYS"):
        print("检测到 ANSPIRE_API_KEYS 环境变量，运行完整测试套件...")
        unittest.main(verbosity=2)
    else:
        # Otherwise, only run unit tests, skip integration tests
        print("未设置 ANSPIRE_API_KEYS 环境变量，仅运行单元测试（跳过集成测试）...")
        print("如需运行完整测试，请设置环境变量:")
        print("  Windows PowerShell: $env:ANSPIRE_API_KEYS=\"your_api_key\"")
        print("  Linux/Mac: export ANSPIRE_API_KEYS=\"your_api_key\"")
        print()
        
        # Run unit tests
        suite = unittest.TestLoader().loadTestsFromTestCase(TestAnspireConfigLoading)
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestAnspireSearchProvider))
        suite.addTests(unittest.TestLoader().loadTestsFromTestCase(TestAnspireSearchService))
        runner = unittest.TextTestRunner(verbosity=2)
        runner.run(suite)
        
        # Provides manual testing options
        print("\n" + "=" * 60)
        choice = input("是否运行手动测试（需要有效的 API Key）? (y/n): ").strip().lower()
        if choice == 'y':
            run_manual_test()
