from __future__ import annotations

import unittest
from unittest.mock import patch

import requests

from localeforge.errors import ModelProviderError
from localeforge.modes import process_model_response
from localeforge.providers import OpenAICompatibleClient, StaticModelClient


class FakeResponse:
    def __init__(self, payload: dict[str, object], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            error = requests.HTTPError(f"{self.status_code} error")
            error.response = self
            raise error
        return None

    def json(self) -> dict[str, object]:
        return self.payload


class ProvidersAndModesTests(unittest.TestCase):
    def test_static_client_returns_configured_values(self) -> None:
        client = StaticModelClient({"hello": "bonjour"})

        self.assertEqual(client.generate("Prompt", "hello"), "bonjour")

    def test_openai_compatible_availability_does_not_require_model_listing(self) -> None:
        client = OpenAICompatibleClient(
            base_url="https://api.example.com/v1",
            api_key="secret",
            model="gpt-5.5",
        )

        with patch("localeforge.providers.requests.Session") as session_factory:
            session_factory.return_value.get.return_value = FakeResponse({"data": [{"id": "other-model"}]})

            models = client.ensure_available()

        self.assertEqual(models, ["other-model"])

    def test_openai_compatible_availability_tolerates_missing_models_endpoint(self) -> None:
        client = OpenAICompatibleClient(
            base_url="https://api.example.com/v1",
            api_key="secret",
            model="gpt-5.5",
        )

        with patch("localeforge.providers.requests.Session") as session_factory:
            session_factory.return_value.get.return_value = FakeResponse({}, status_code=404)

            models = client.ensure_available()

        self.assertEqual(models, [])

    def test_transform_strips_output_and_rejects_empty(self) -> None:
        result = process_model_response("transform", "  polished  ")
        self.assertEqual(result.primary, "polished")

        with self.assertRaises(ModelProviderError):
            process_model_response("transform", "   ")

    def test_status_json_parses_object_fields(self) -> None:
        result = process_model_response(
            "status-json",
            '{"status":"NEEDS_REVIEW","category":"tone","reason":"Too literal","suggestion":"Rewrite naturally"}',
        )

        self.assertEqual(result.primary, "NEEDS_REVIEW")
        self.assertEqual(result.fields["status"], "NEEDS_REVIEW")
        self.assertEqual(result.fields["category"], "tone")
        self.assertEqual(result.fields["reason"], "Too literal")
        self.assertEqual(result.fields["suggestion"], "Rewrite naturally")

    def test_status_json_stringifies_list_fields(self) -> None:
        result = process_model_response("status-json", '{"status":"OK","spans":["Mana","UI"]}')

        self.assertEqual(result.fields["spans"], "Mana | UI")

    def test_status_json_does_not_require_status_field(self) -> None:
        result = process_model_response("status-json", '{"category":"tone","reason":""}')

        self.assertEqual(result.primary, "tone")
        self.assertEqual(result.fields["category"], "tone")
        self.assertEqual(result.fields["reason"], "")


if __name__ == "__main__":
    unittest.main()
