from __future__ import annotations

import json
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
            os.environ["LF_BASE_URL"] = "https://api.example.com/v1"
            self.addCleanup(os.environ.pop, "LOCALEFORGE_SETTINGS_PATH", None)
            self.addCleanup(os.environ.pop, "LF_KEY", None)
            self.addCleanup(os.environ.pop, "LF_BASE_URL", None)

            code = main(
                [
                    "provider",
                    "add",
                    "default-api",
                    "--base-url-env",
                    "LF_BASE_URL",
                    "--api-key-env",
                    "LF_KEY",
                    "--default-model",
                    "gpt-4.1-mini",
                    "--set-default",
                    "--json",
                ]
            )

            self.assertEqual(code, 0)
            payload = json.loads(settings_path.read_text(encoding="utf-8"))
            provider = payload["providers"][0]
            self.assertEqual(provider["base_url"], "")
            self.assertEqual(provider["base_url_env"], "LF_BASE_URL")
            self.assertEqual(provider["api_key"], "")
            self.assertEqual(provider["api_key_env"], "LF_KEY")

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
