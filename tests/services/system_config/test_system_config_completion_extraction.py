# -*- coding: utf-8 -*-
"""Channel-test completion extraction: dict-shaped MiniMax payloads and <think> wrappers."""
import unittest
from types import SimpleNamespace

from src.services.system_config_service import SystemConfigService


class TestExtractLlmCompletionContent(unittest.TestCase):
    def _extract(self, response):
        return SystemConfigService._extract_llm_completion_content(response)

    def test_dict_shaped_minimax_response_is_read(self):
        # MiniMax returns dict-shaped choices/message; attribute access used to
        # reject the whole payload as malformed (issue-2013).
        response = {"choices": [{"message": {"content": '{"status":"ok"}'}}]}
        content, error_code, _error, _reason = self._extract(response)
        self.assertEqual(content, '{"status":"ok"}')
        self.assertIsNone(error_code)

    def test_strips_leading_think_wrapper(self):
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    content_blocks=None,
                    message=SimpleNamespace(
                        content='<think>Internal reasoning</think>{"status":"ok"}'
                    ),
                )
            ]
        )
        content, error_code, _error, _reason = self._extract(response)
        self.assertEqual(content, '{"status":"ok"}')
        self.assertIsNone(error_code)

    def test_filters_typed_reasoning_blocks(self):
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    content_blocks=[
                        SimpleNamespace(type="thinking", text="internal reasoning"),
                        SimpleNamespace(type="text", text='{"status":"ok"}'),
                    ],
                    message=None,
                )
            ]
        )
        content, error_code, _error, _reason = self._extract(response)
        self.assertEqual(content, '{"status":"ok"}')
        self.assertIsNone(error_code)

    def test_preserves_literal_think_inside_json_string(self):
        payload = '{"summary":"literal <think>text</think>"}'
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(content_blocks=None, message=SimpleNamespace(content=payload))
            ]
        )
        content, error_code, _error, _reason = self._extract(response)
        self.assertEqual(content, payload)
        self.assertIsNone(error_code)

    def test_dict_message_without_content_reports_format_error(self):
        response = {"choices": [{"message": {}}]}
        content, error_code, _error, _reason = self._extract(response)
        self.assertEqual(content, "")
        self.assertEqual(error_code, "format_error")


if __name__ == "__main__":
    unittest.main()
