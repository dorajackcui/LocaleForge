from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from localeforge.errors import ModelProviderError
from localeforge.task_profile import load_task_profile
from localeforge.windowing import WindowSourceRow, build_window_user_text, process_window_response


class WindowingTests(unittest.TestCase):
    def _profile(self, tmpdir: str, metadata: str = "id: proofread\nmode: transform\n"):
        task = Path(tmpdir) / "task.md"
        task.write_text(f"---\n{metadata}---\n\nDo the task.\n", encoding="utf-8")
        return load_task_profile(task)

    def test_build_window_user_text_uses_previous_current_and_next(self) -> None:
        text = build_window_user_text(
            previous=[{"row": 2, "source": "a", "target": "A"}],
            current=[WindowSourceRow(row=3, source="b")],
            next_rows=[WindowSourceRow(row=4, source="c")],
        )

        self.assertIn('"previous"', text)
        self.assertIn('"target": "A"', text)
        self.assertIn('"current"', text)
        self.assertIn('"next"', text)

    def test_process_transform_window_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = self._profile(tmpdir)

            processed = process_window_response(
                profile,
                '[{"row":2,"target":"Bonjour"},{"row":3,"target":"Salut"}]',
                [WindowSourceRow(row=2, source="hello"), WindowSourceRow(row=3, source="hi")],
            )

            self.assertEqual(processed[2].primary, "Bonjour")
            self.assertEqual(processed[3].primary, "Salut")

    def test_process_status_json_window_response(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = self._profile(
                tmpdir,
                "id: qa\n"
                "mode: status-json\n"
                "output:\n"
                "  fields:\n"
                "    - status\n"
                "    - reason\n",
            )

            processed = process_window_response(
                profile,
                '[{"row":2,"status":"OK","reason":"Fine"}]',
                [WindowSourceRow(row=2, source="hello")],
            )

            self.assertEqual(processed[2].fields, {"status": "OK", "reason": "Fine"})

    def test_rejects_duplicate_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = self._profile(tmpdir)

            with self.assertRaisesRegex(ModelProviderError, "duplicate row"):
                process_window_response(
                    profile,
                    '[{"row":2,"target":"A"},{"row":2,"target":"B"}]',
                    [WindowSourceRow(row=2, source="a"), WindowSourceRow(row=3, source="b")],
                )

    def test_rejects_non_integer_rows(self) -> None:
        cases = [
            ("string", '[{"row":"2","target":"A"}]', [WindowSourceRow(row=2, source="a")]),
            ("float", '[{"row":2.9,"target":"A"}]', [WindowSourceRow(row=2, source="a")]),
            ("bool", '[{"row":true,"target":"A"}]', [WindowSourceRow(row=1, source="a")]),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            profile = self._profile(tmpdir)

            for label, raw, current in cases:
                with self.subTest(label=label):
                    with self.assertRaisesRegex(ModelProviderError, "integer row"):
                        process_window_response(profile, raw, current)

    def test_rejects_unknown_transform_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = self._profile(tmpdir)

            with self.assertRaisesRegex(ModelProviderError, "unknown fields"):
                process_window_response(
                    profile,
                    '[{"row":2,"target":"A","extra":"x"}]',
                    [WindowSourceRow(row=2, source="a")],
                )

    def test_rejects_status_json_missing_declared_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            profile = self._profile(
                tmpdir,
                "id: qa\n"
                "mode: status-json\n"
                "output:\n"
                "  fields:\n"
                "    - status\n"
                "    - reason\n",
            )

            with self.assertRaisesRegex(ModelProviderError, "missing fields"):
                process_window_response(
                    profile,
                    '[{"row":2,"status":"OK"}]',
                    [WindowSourceRow(row=2, source="a")],
                )


if __name__ == "__main__":
    unittest.main()
