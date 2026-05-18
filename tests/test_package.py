from __future__ import annotations

import unittest
from pathlib import Path

import localeforge
from localeforge.cli import build_parser


class PackageTests(unittest.TestCase):
    def test_version_is_available(self) -> None:
        self.assertRegex(localeforge.__version__, r"^\d+\.\d+\.\d+$")

    def test_parser_has_agent_first_commands(self) -> None:
        parser = build_parser()
        help_text = parser.format_help()

        self.assertIn("run", help_text)
        self.assertIn("validate", help_text)
        self.assertIn("doctor", help_text)
        self.assertIn("provider", help_text)

    def test_readme_documents_new_cli(self) -> None:
        text = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("localeforge run", text)
        self.assertIn("source", text)
        self.assertIn("target", text)


if __name__ == "__main__":
    unittest.main()
