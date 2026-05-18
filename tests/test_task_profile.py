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
            "  columns:\n"
            "    status: G\n"
            "    reason: H\n"
            "model:\n"
            "  execution_mode: api\n"
            "  provider: default-api\n"
            "  name: gpt-4.1-mini\n"
            "---\n\nPrompt body\n"
        )
        profile = load_task_profile(path)

        self.assertEqual(profile.input.column, "C")
        self.assertEqual(profile.input.start_row, 3)
        self.assertEqual(profile.output.columns["status"], "G")
        self.assertEqual(profile.output.columns["reason"], "H")
        self.assertEqual(profile.model.provider, "default-api")

    def test_output_boolean_strings_are_parsed_as_booleans(self) -> None:
        path = self.write_task(
            "---\n"
            "id: proofread-fr\n"
            "output:\n"
            '  create: "false"\n'
            '  overwrite: "false"\n'
            "---\n\n"
            "Prompt body\n"
        )

        profile = load_task_profile(path)

        self.assertFalse(profile.output.create)
        self.assertFalse(profile.output.overwrite)

    def test_invalid_output_boolean_string_is_rejected(self) -> None:
        path = self.write_task(
            "---\n"
            "id: proofread-fr\n"
            "output:\n"
            '  overwrite: "sometimes"\n'
            "---\n\n"
            "Prompt body\n"
        )

        with self.assertRaisesRegex(TaskProfileError, "output.overwrite"):
            load_task_profile(path)

    def test_status_json_can_declare_stable_output_fields(self) -> None:
        path = self.write_task(
            "---\n"
            "id: review\n"
            "mode: status-json\n"
            "output:\n"
            "  fields:\n"
            "    - status\n"
            "    - reason\n"
            "---\n\n"
            "Return JSON.\n"
        )

        profile = load_task_profile(path)

        self.assertEqual(profile.output.fields, ("status", "reason"))

    def test_request_config_reads_window_metadata(self) -> None:
        path = self.write_task(
            "---\n"
            "id: translate-window\n"
            "request:\n"
            "  mode: window\n"
            "  window_size: 7\n"
            "---\n\n"
            "Translate.\n"
        )

        profile = load_task_profile(path)

        self.assertEqual(profile.request.mode, "window")
        self.assertEqual(profile.request.window_size, 7)

    def test_request_window_size_requires_window_mode(self) -> None:
        path = self.write_task(
            "---\n"
            "id: translate-window\n"
            "request:\n"
            "  mode: concurrent\n"
            "  window_size: 7\n"
            "---\n\n"
            "Translate.\n"
        )

        with self.assertRaisesRegex(TaskProfileError, "request.window_size"):
            load_task_profile(path)

    def test_output_column_mappings_must_match_declared_fields(self) -> None:
        path = self.write_task(
            "---\n"
            "id: review\n"
            "mode: status-json\n"
            "output:\n"
            "  fields:\n"
            "    - status\n"
            "  columns:\n"
            "    reason: review_reason\n"
            "---\n\n"
            "Return JSON.\n"
        )

        with self.assertRaisesRegex(TaskProfileError, "output.columns"):
            load_task_profile(path)

    def test_model_runtime_fields_are_global_settings(self) -> None:
        path = self.write_task(
            "---\n"
            "id: proofread-fr\n"
            "model:\n"
            "  name: gpt-4.1-mini\n"
            "  concurrency: 4\n"
            "---\n\nPrompt body\n"
        )

        with self.assertRaisesRegex(TaskProfileError, "global runtime settings"):
            load_task_profile(path)

    def test_scalar_model_is_model_name_shorthand(self) -> None:
        path = self.write_task("---\nid: rewrite\nmode: transform\nmodel: gpt-5.5\n---\n\nRewrite.\n")

        profile = load_task_profile(path)

        self.assertEqual(profile.model.name, "gpt-5.5")
        self.assertIsNone(profile.model.provider)
        self.assertIsNone(profile.model.execution_mode)

    def test_example_transform_task_is_valid(self) -> None:
        root = Path(__file__).resolve().parents[1]
        profile = load_task_profile(root / "tasks" / "example-transform.md")

        self.assertEqual(profile.id, "example-transform")
        self.assertEqual(profile.mode, "transform")
        self.assertEqual(profile.input.column, "source")
        self.assertEqual(profile.output.column, "target")
        self.assertIn("return only the rewritten text", profile.prompt)

    def test_example_status_json_task_is_valid(self) -> None:
        root = Path(__file__).resolve().parents[1]
        profile = load_task_profile(root / "tasks" / "example-status-json.md")

        self.assertEqual(profile.id, "example-status-json")
        self.assertEqual(profile.mode, "status-json")
        self.assertEqual(profile.output.fields, ("status", "category", "reason", "suggestion"))
        self.assertIn("return exactly one JSON object", profile.prompt)

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
