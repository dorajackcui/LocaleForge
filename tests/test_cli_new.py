from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from localeforge.cli import main


class CliTests(unittest.TestCase):
    def test_provider_add_and_list_json_redacts_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            os.environ["LOCALEFORGE_SETTINGS_PATH"] = str(settings_path)
            os.environ["LF_KEY"] = "secret"
            self.addCleanup(os.environ.pop, "LOCALEFORGE_SETTINGS_PATH", None)
            self.addCleanup(os.environ.pop, "LF_KEY", None)

            code = main(
                [
                    "provider",
                    "add",
                    "default-api",
                    "--base-url",
                    "https://api.example.com/v1",
                    "--api-key-env",
                    "LF_KEY",
                    "--default-model",
                    "gpt-4.1-mini",
                    "--set-default",
                    "--json",
                ]
            )

            self.assertEqual(code, 0)

    def test_validate_json_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task = Path(tmpdir) / "task.md"
            task.write_text("---\nid: proofread\n---\n\nPolish.\n", encoding="utf-8")
            source = Path(tmpdir) / "a.csv"
            source.write_text("source\nhello\n", encoding="utf-8")

            code = main(["validate", "--task", str(task), "--input", str(source), "--json"])

            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
