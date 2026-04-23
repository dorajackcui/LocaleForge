from __future__ import annotations

import unittest

from localeforge.config.tasks import STATUS_SUSPECT, get_task_config
from localeforge.model.openai_compatible import OpenAICompatibleClient


class FakeOpenAICompatibleClient(OpenAICompatibleClient):
    def __init__(self) -> None:
        super().__init__(
            api_url="https://example.test/v1",
            api_key="secret-key",
            model="gpt-4o-mini",
            timeout=30.0,
            prompt_template="Return JSON with {{STATUS_OK}} or {{STATUS_SUSPECT}} for {{TEXT}}",
            task_config=get_task_config("english-check"),
        )
        self.last_get: tuple[str, dict[str, str]] | None = None
        self.last_post: tuple[str, dict[str, object], dict[str, str]] | None = None

    def _get_json(self, url: str, headers: dict[str, str]) -> dict:
        self.last_get = (url, headers)
        return {"data": [{"id": "gpt-4o-mini"}, {"id": "gpt-4.1-mini"}]}

    def _post_json(self, url: str, payload: dict, headers: dict[str, str]) -> dict:
        self.last_post = (url, payload, headers)
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"status":"%s","spans":["castle"]}' % STATUS_SUSPECT,
                    }
                }
            ]
        }


class OpenAICompatibleClientTests(unittest.TestCase):
    def test_ensure_available_returns_models_from_models_endpoint(self) -> None:
        client = FakeOpenAICompatibleClient()

        models = client.ensure_available()

        self.assertEqual(models, ["gpt-4o-mini", "gpt-4.1-mini"])
        self.assertIsNotNone(client.last_get)
        assert client.last_get is not None
        self.assertEqual(client.last_get[0], "https://example.test/v1/models")
        self.assertEqual(client.last_get[1]["Authorization"], "Bearer secret-key")

    def test_classify_posts_chat_completions_request(self) -> None:
        client = FakeOpenAICompatibleClient()

        result = client.classify("the hero is in the castle")

        self.assertEqual(result.status, STATUS_SUSPECT)
        self.assertEqual(result.spans, ["castle"])
        self.assertIsNotNone(client.last_post)
        assert client.last_post is not None
        url, payload, headers = client.last_post
        self.assertEqual(url, "https://example.test/v1/chat/completions")
        self.assertEqual(headers["Authorization"], "Bearer secret-key")
        self.assertEqual(payload["model"], "gpt-4o-mini")
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["messages"][0]["role"], "system")
        self.assertIn("Return JSON", payload["messages"][0]["content"])
        self.assertEqual(payload["messages"][1]["role"], "user")
        self.assertEqual(payload["messages"][1]["content"], "the hero is in the castle")


if __name__ == "__main__":
    unittest.main()
