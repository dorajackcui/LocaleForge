from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from localeforge.errors import TaskProfileError
from localeforge.task_profile import load_task_profile


class TaskProfileTests(unittest.TestCase):
    def write_task(self, text: str) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "task.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_minimal_transform_task_uses_defaults(self) -> None:
        path = self.write_task("---\nid: proofread\n---\n\nPolish the text.\n")
        profile = load_task_profile(path)

        self.assertEqual(profile.id, "proofread")
        self.assertEqual(profile.mode, "transform")
        self.assertEqual(profile.input.column, "source")
        self.assertEqual(profile.output.column, "target")
        self.assertTrue(profile.output.overwrite)
        self.assertEqual(profile.prompt, "Polish the text.")

    def test_full_task_reads_nested_config(self) -> None:
        path = self.write_task(
            "---\n"
            "id: proofread-fr\n"
            "mode: transform\n"
            "input:\n"
            "  sheet: Sheet1\n"
            "  column: C\n"
            "  start_row: 3\n"
            "output:\n"
            "  column: F\n"
            "model:\n"
            "  execution_mode: api\n"
            "  provider: default-api\n"
            "  name: gpt-4.1-mini\n"
            "  concurrency: 4\n"
            "---\n\nPrompt body\n"
        )
        profile = load_task_profile(path)

        self.assertEqual(profile.input.column, "C")
        self.assertEqual(profile.input.start_row, 3)
        self.assertEqual(profile.model.provider, "default-api")
        self.assertEqual(profile.model.concurrency, 4)

    def test_missing_prompt_body_is_invalid(self) -> None:
        path = self.write_task("---\nid: empty\n---\n")

        with self.assertRaises(TaskProfileError):
            load_task_profile(path)

    def test_invalid_yaml_is_invalid(self) -> None:
        path = self.write_task("---\nid: [broken\n---\n\nPrompt\n")

        with self.assertRaises(TaskProfileError):
            load_task_profile(path)


if __name__ == "__main__":
    unittest.main()
