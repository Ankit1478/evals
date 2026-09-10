import os
import unittest
from unittest.mock import patch

import eval as eval_harness


class OpenAIClientTests(unittest.TestCase):
    @patch.dict(os.environ, {"OPENAI_API_KEY": "sk-test"}, clear=True)
    def test_chat_defaults_to_gpt_5_6_luna(self):
        def fake_post(url, headers, payload, timeout):
            self.assertEqual(payload["model"], "gpt-5.6-luna")
            self.assertEqual(payload.get("reasoning_effort"), "none")
            return 200, {"choices": [{"message": {"content": "Hello"}}], "usage": {}}

        with patch.object(eval_harness, "_post", side_effect=fake_post):
            result = eval_harness.chat(
                messages=[{"role": "user", "content": "Hello"}],
                tools=eval_harness.TOOLS,
                use_cache=False,
                max_retries=0,
            )

        self.assertTrue(result["ok"])

    @patch.dict(
        os.environ,
        {"OPENAI_API_KEY": "sk-test", "OPENAI_MODEL": "gpt-4.1-mini"},
        clear=False,
    )
    def test_chat_uses_standard_openai_api_and_normalizes_tool_calls(self):
        def fake_post(url, headers, payload, timeout):
            self.assertEqual(url, "https://api.openai.com/v1/chat/completions")
            self.assertEqual(headers["Authorization"], "Bearer sk-test")
            self.assertNotIn("api-key", headers)
            self.assertEqual(payload["model"], "gpt-4.1-mini")
            return 200, {
                "choices": [
                    {
                        "message": {
                            "content": None,
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "track_order",
                                        "arguments": '{"order_id":"123"}',
                                    }
                                }
                            ],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }

        with patch.object(eval_harness, "_post", side_effect=fake_post):
            result = eval_harness.chat(
                messages=[{"role": "user", "content": "Track order #123"}],
                tools=eval_harness.TOOLS,
                use_cache=False,
                max_retries=0,
            )

        self.assertTrue(result["ok"])
        self.assertEqual(
            result["tool_calls"],
            [{"name": "track_order", "args": {"order_id": "123"}}],
        )


if __name__ == "__main__":
    unittest.main()
