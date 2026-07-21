import unittest
import json
from unittest.mock import patch, MagicMock
from src.notification_sender.dingtalk_sender import DingtalkSender
from src.config import Config

class TestDingtalkSender(unittest.TestCase):
    def setUp(self):
        self.config = Config()
        self.config.dingtalk_webhook_url = "https://oapi.dingtalk.com/robot/send?access_token=test_token"
        self.config.dingtalk_secret = "test_secret"
        self.sender = DingtalkSender(self.config)

    @patch("src.notification_sender.dingtalk_sender.requests.post")
    def test_send_success(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_post.return_value = mock_response

        result = self.sender.send_to_dingtalk("Test content", "Test Title")
        self.assertTrue(result)
        mock_post.assert_called_once()
        
        called_url = mock_post.call_args[0][0]
        self.assertIn("timestamp=", called_url)
        self.assertIn("sign=", called_url)

    @patch("src.notification_sender.dingtalk_sender.requests.post")
    def test_send_chunked_long_chinese_message_payload_size(self, mock_post):
        """Testing multi-byte Chinese long text and long titles exceeding 20KB limits, verifying that the actual JSON payload byte count strictly adheres to the restriction."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"errcode": 0, "errmsg": "ok"}
        mock_post.return_value = mock_response

        # Generate ultra-long Chinese content (each Chinese character is 3 bytes, generating approximately 30,000 bytes of text)
        long_chinese_content = "股票复盘" * 2500 
        # Generate extremely long titles
        long_title = "这是一个用来测试钉钉机器人极端边界情况的超长超长超长超长标题" * 10 

        result = self.sender.send_to_dingtalk(long_chinese_content, long_title)
        
        self.assertTrue(result)
        # Should be split into at least 2 requests
        self.assertGreaterEqual(mock_post.call_count, 2)
        
        # The absolute number of JSON bytes actually serialized in each request to DingTalk does not exceed 20000 bytes
        for call in mock_post.call_args_list:
            payload = call.kwargs['json']
            # Simulate JSON serialization as in actual network transmission (no spaces, UTF-8 encoded)
            payload_bytes = len(json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8'))
            
            # Assert that the entire JSON request body sent is <= 20000 bytes
            self.assertLessEqual(payload_bytes, 20000, f"Payload 字节数为 {payload_bytes}，超过钉钉 20KB 限制！")
            
            # Ensure titles are successfully truncated without losing pagination information
            self.assertLessEqual(len(payload['markdown']['title']), 120)

    @patch("src.notification_sender.dingtalk_sender.requests.post")
    def test_send_api_error(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"errcode": 310000, "errmsg": "invalid token"}
        mock_post.return_value = mock_response

        result = self.sender.send_to_dingtalk("Test content")
        self.assertFalse(result)

    @patch("src.notification_sender.dingtalk_sender.requests.post")
    def test_send_exception(self, mock_post):
        mock_post.side_effect = Exception("Network Error")
        result = self.sender.send_to_dingtalk("Test content")
        self.assertFalse(result)