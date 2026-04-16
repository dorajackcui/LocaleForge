from __future__ import annotations

import unittest

from localeforge.config.tasks import STATUS_EMPTY, STATUS_SUSPECT, get_task_config
from localeforge.rules import analyze_text, get_rule_decision, normalize_text


class RuleTests(unittest.TestCase):
    def test_normalize_text_compacts_whitespace(self) -> None:
        self.assertEqual(normalize_text(" Fireball\r\n  Mana "), "Fireball Mana")

    def test_analyze_text_flags_obvious_english(self) -> None:
        decision = analyze_text("the hero is in the castle")
        self.assertEqual(decision.status, STATUS_SUSPECT)

    def test_get_rule_decision_skips_precheck_for_term_task(self) -> None:
        decision = get_rule_decision(get_task_config("term-extraction"), "the hero is in the castle")
        self.assertIsNone(decision.status)

    def test_get_rule_decision_handles_empty_text(self) -> None:
        decision = get_rule_decision(get_task_config("english-check"), "")
        self.assertEqual(decision.status, STATUS_EMPTY)


if __name__ == "__main__":
    unittest.main()

