from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from localeforge.cli import main
from localeforge.providers import StaticModelClient


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir_context = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir_context.cleanup)

        self._env_names = [
            "LOCALEFORGE_SETTINGS_PATH",
            "OPENAI_BASE_URL",
            "OPENAI_API_KEY",
            "OPENAI_MODEL",
            "LOCALEFORGE_CONCURRENCY",
            "LOCALEFORGE_MAX_ATTEMPTS",
            "LF_KEY",
            "LF_BASE_URL",
        ]
        self._previous_env = {name: os.environ.get(name) for name in self._env_names}
        self.addCleanup(self._restore_env)
        for name in self._env_names:
            os.environ.pop(name, None)

        previous_cwd = Path.cwd()
        os.chdir(self._tmpdir_context.name)
        self.addCleanup(os.chdir, previous_cwd)
        os.environ["LOCALEFORGE_SETTINGS_PATH"] = str(Path(self._tmpdir_context.name) / "settings.json")

    def _restore_env(self) -> None:
        for name, value in self._previous_env.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    def test_provider_add_and_list_json_redacts_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            os.environ["LOCALEFORGE_SETTINGS_PATH"] = str(settings_path)
            os.environ["LF_KEY"] = "secret"
            os.environ["LF_BASE_URL"] = "https://api.example.com/v1"

            with redirect_stdout(StringIO()):
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

            stdout = StringIO()
            with redirect_stdout(stdout):
                code = main(["validate", "--task", str(task), "--input", str(source), "--json"])

            self.assertEqual(code, 0)
            payload = json.loads(stdout.getvalue())
            self.assertTrue(payload["files"][0]["output"].endswith("a_proofread.csv"))

    def test_doctor_defaults_to_human_readable_output(self) -> None:
        output = StringIO()

        with patch("localeforge.cli._create_client_for_effective_config", return_value=StaticModelClient({})):
            with redirect_stdout(output):
                code = main(["doctor"])

        self.assertEqual(code, 0)
        text = output.getvalue()
        self.assertIn("LocaleForge doctor", text)
        self.assertIn("status: success", text)
        self.assertIn("provider: ok", text)
        self.assertNotIn('"status"', text)

    def test_doctor_prefers_local_env_api_when_no_provider_is_saved(self) -> None:
        Path(".env").write_text(
            "OPENAI_BASE_URL=https://api.example.com/v1\n"
            "OPENAI_API_KEY=secret\n"
            "OPENAI_MODEL=gpt-4.1-mini\n",
            encoding="utf-8",
        )
        output = StringIO()

        with patch("localeforge.cli.OpenAICompatibleClient", return_value=StaticModelClient({})) as client:
            with redirect_stdout(output):
                code = main(["doctor"])

        self.assertEqual(code, 0)
        client.assert_called_once()
        self.assertEqual(client.call_args.kwargs["base_url"], "https://api.example.com/v1")
        self.assertEqual(client.call_args.kwargs["api_key"], "secret")
        self.assertEqual(client.call_args.kwargs["model"], "gpt-4.1-mini")
        text = output.getvalue()
        self.assertIn("execution_mode: api", text)
        self.assertIn("provider: env", text)
        self.assertIn("model: gpt-4.1-mini", text)
        self.assertNotIn("gemma4", text)

    def test_doctor_does_not_fall_back_to_local_model_when_env_model_is_missing(self) -> None:
        Path(".env").write_text(
            "OPENAI_BASE_URL=https://api.example.com/v1\n"
            "OPENAI_API_KEY=secret\n",
            encoding="utf-8",
        )
        output = StringIO()

        with patch("localeforge.cli.OpenAICompatibleClient", return_value=StaticModelClient({})) as client:
            with redirect_stdout(output):
                code = main(["doctor"])

        self.assertEqual(code, 0)
        client.assert_called_once()
        self.assertEqual(client.call_args.kwargs["base_url"], "https://api.example.com/v1")
        self.assertEqual(client.call_args.kwargs["api_key"], "secret")
        self.assertEqual(client.call_args.kwargs["model"], "")
        text = output.getvalue()
        self.assertIn("execution_mode: api", text)
        self.assertIn("provider: env", text)
        self.assertIn("model: <not set>", text)
        self.assertNotIn("gemma4", text)

    def test_run_progress_writes_to_stderr_without_polluting_json_stdout(self) -> None:
        task = Path("task.md")
        task.write_text("---\nid: proofread\n---\n\nPolish.\n", encoding="utf-8")
        source = Path("source.csv")
        source.write_text("source\nhello\n", encoding="utf-8")
        stdout = StringIO()
        stderr = StringIO()

        with patch("localeforge.cli._create_client_for_effective_config", return_value=StaticModelClient({"hello": "bonjour"})):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                code = main(["run", "--task", str(task), "--input", str(source), "--json", "--progress", "text"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["status"], "success")
        self.assertTrue(payload["files"][0]["output"].endswith("source_proofread.csv"))
        self.assertIn("[1/1]", stderr.getvalue())
        self.assertIn("done", stderr.getvalue())

    def test_run_max_attempts_cli_retries_invalid_json(self) -> None:
        class FlakyJsonClient:
            def __init__(self) -> None:
                self.calls = 0

            def ensure_available(self) -> list[str]:
                return ["flaky"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                self.calls += 1
                if self.calls == 1:
                    return "not json"
                return '{"status":"OK"}'

        task = Path("task.md")
        task.write_text("---\nid: qa\nmode: status-json\n---\n\nReturn JSON.\n", encoding="utf-8")
        source = Path("source.csv")
        source.write_text("source\nhello\n", encoding="utf-8")
        stdout = StringIO()
        client = FlakyJsonClient()

        with patch("localeforge.cli._create_client_for_effective_config", return_value=client):
            with redirect_stdout(stdout):
                code = main(["run", "--task", str(task), "--input", str(source), "--json", "--max-attempts", "2"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["files"][0]["model_calls"], 2)

    def test_run_uses_env_max_attempts_default(self) -> None:
        class TwiceInvalidJsonClient:
            def __init__(self) -> None:
                self.calls = 0

            def ensure_available(self) -> list[str]:
                return ["flaky"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                self.calls += 1
                if self.calls < 3:
                    return "not json"
                return '{"status":"OK"}'

        Path(".env").write_text("LOCALEFORGE_MAX_ATTEMPTS=3\n", encoding="utf-8")
        task = Path("task.md")
        task.write_text("---\nid: qa\nmode: status-json\n---\n\nReturn JSON.\n", encoding="utf-8")
        source = Path("source.csv")
        source.write_text("source\nhello\n", encoding="utf-8")
        stdout = StringIO()
        client = TwiceInvalidJsonClient()

        with patch("localeforge.cli._create_client_for_effective_config", return_value=client):
            with redirect_stdout(stdout):
                code = main(["run", "--task", str(task), "--input", str(source), "--json"])

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["files"][0]["model_calls"], 3)

    def test_run_uses_env_concurrency_default(self) -> None:
        class SlowClient:
            def __init__(self) -> None:
                self.active = 0
                self.max_active = 0
                self.lock = None

            def ensure_available(self) -> list[str]:
                return ["slow"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                import threading
                import time

                if self.lock is None:
                    self.lock = threading.Lock()
                with self.lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                time.sleep(0.05)
                with self.lock:
                    self.active -= 1
                return user_text.upper()

        Path(".env").write_text("LOCALEFORGE_CONCURRENCY=3\n", encoding="utf-8")
        task = Path("task.md")
        task.write_text("---\nid: proofread\nmode: transform\n---\n\nPolish.\n", encoding="utf-8")
        source = Path("source.csv")
        source.write_text("source\na\nb\nc\nd\n", encoding="utf-8")
        stdout = StringIO()
        client = SlowClient()

        with patch("localeforge.cli._create_client_for_effective_config", return_value=client):
            with redirect_stdout(stdout):
                code = main(["run", "--task", str(task), "--input", str(source), "--json"])

        self.assertEqual(code, 0)
        self.assertGreater(client.max_active, 1)


if __name__ == "__main__":
    unittest.main()
