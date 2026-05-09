from __future__ import annotations

import unittest

from localeforge.errors import ModelProviderError
from localeforge.modes import process_model_response
from localeforge.providers import StaticModelClient


class ProvidersAndModesTests(unittest.TestCase):
    def test_static_client_returns_configured_values(self) -> None:
        client = StaticModelClient({"hello": "bonjour"})

        self.assertEqual(client.generate("Prompt", "hello"), "bonjour")

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
