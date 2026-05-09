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

    def test_status_json_parses_status_and_spans(self) -> None:
        result = process_model_response("status-json", '{"status":"OK","spans":["Mana"]}')

        self.assertEqual(result.primary, "OK")
        self.assertEqual(result.details, "Mana")


if __name__ == "__main__":
    unittest.main()
