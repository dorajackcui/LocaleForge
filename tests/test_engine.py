from __future__ import annotations

import tempfile
import threading
import time
import unittest
from pathlib import Path

from localeforge.engine import RunOptions, run_task, validate_task
from localeforge.providers import StaticModelClient
from localeforge.task_profile import load_task_profile


class EngineTests(unittest.TestCase):
    def write_task(self, tmpdir: str) -> Path:
        path = Path(tmpdir) / "proofread.md"
        path.write_text("---\nid: proofread\nmode: transform\n---\n\nPolish.\n", encoding="utf-8")
        return path

    def test_validate_does_not_call_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\n", encoding="utf-8")
            profile = load_task_profile(task_path)

            report = validate_task(profile, task_path, RunOptions(input_path=input_path))

            self.assertEqual(report.status, "success")
            self.assertEqual(report.files[0].rows_total, 1)
            self.assertFalse((Path(tmpdir) / "a.localeforge.csv").exists())

    def test_run_transforms_csv_and_uses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\nhello\n\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = StaticModelClient({"hello": "bonjour"})

            report = run_task(profile, task_path, RunOptions(input_path=input_path), client)

            self.assertEqual(report.status, "success")
            self.assertEqual(report.files[0].rows_processed, 2)
            self.assertEqual(report.files[0].rows_empty, 1)
            self.assertEqual(report.files[0].model_calls, 1)
            self.assertEqual(report.files[0].cache_hits, 1)
            self.assertIn("a.localeforge.csv", str(report.files[0].output))
            self.assertIn("bonjour", report.files[0].output.read_text(encoding="utf-8"))

    def test_run_uses_bounded_concurrency_for_model_calls(self) -> None:
        class SlowClient:
            def __init__(self) -> None:
                self.active = 0
                self.max_active = 0
                self.lock = threading.Lock()

            def ensure_available(self) -> list[str]:
                return ["slow"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                with self.lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                time.sleep(0.05)
                with self.lock:
                    self.active -= 1
                return user_text.upper()

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\na\nb\nc\nd\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = SlowClient()

            report = run_task(profile, task_path, RunOptions(input_path=input_path, concurrency=3), client)

            self.assertEqual(report.status, "success")
            self.assertGreater(client.max_active, 1)
            self.assertEqual(report.files[0].model_calls, 4)
            output_text = report.files[0].output.read_text(encoding="utf-8")
            self.assertIn("A", output_text)
            self.assertIn("D", output_text)


if __name__ == "__main__":
    unittest.main()
