from __future__ import annotations

import unittest

from localeforge.config.tasks import STATUS_SUSPECT, STATUS_TERM_EXTRACTED
from localeforge.model.ollama import parse_classification_response


class OllamaParsingTests(unittest.TestCase):
    def test_parses_json_with_spans(self) -> None:
        result = parse_classification_response(
            '{"status":"%s","spans":[" Fireball ","Mana","Mana"]}' % STATUS_TERM_EXTRACTED,
            STATUS_TERM_EXTRACTED,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.status, STATUS_TERM_EXTRACTED)
        self.assertEqual(result.spans, ["Fireball", "Mana"])

    def test_parses_embedded_json_fragment(self) -> None:
        result = parse_classification_response(
            'model said: {"status":"%s","spans":[]}' % STATUS_SUSPECT,
            STATUS_SUSPECT,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result.status, STATUS_SUSPECT)
        self.assertEqual(result.spans, [])

    def test_returns_none_for_unparseable_payload(self) -> None:
        result = parse_classification_response("not-json", STATUS_TERM_EXTRACTED)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

