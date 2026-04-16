from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from localeforge.config.tasks import get_task_config
from localeforge.ui.helpers import build_run_request, format_completion_lines, format_progress_message


class UiHelperTests(unittest.TestCase):
    def test_build_run_request_normalizes_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.xlsx"
            prompt_path = Path(tmpdir) / "prompt.txt"
            input_path.write_text("stub", encoding="utf-8")
            prompt_path.write_text("{{STATUS_OK}} {{STATUS_SUSPECT}} {{TEXT}}", encoding="utf-8")

            request = build_run_request(
                task_config=get_task_config("term-extraction"),
                input_text=str(input_path),
                output_text="",
                prompt_text=str(prompt_path),
                source_col_text=" a ",
                result_col_text=" b ",
                start_row_text="2",
                sheet_name="Sheet1",
                model=" gemma4:e4b ",
                api_url=" http://127.0.0.1:11434 ",
            )

            self.assertEqual(request.source_col, "A")
            self.assertEqual(request.result_col, "B")
            self.assertEqual(request.start_row, 2)
            self.assertEqual(request.model, "gemma4:e4b")
            self.assertEqual(request.api_url, "http://127.0.0.1:11434")
            self.assertTrue(request.output_path.name.endswith("_checked.xlsx"))

    def test_format_helpers_include_task_hit_status(self) -> None:
        task_config = get_task_config("term-extraction")
        stats = {"OK": 2, "EMPTY": 1, task_config.hit_status: 3, "MODEL_CALLS": 4, "CACHE_HITS": 1}
        message = format_progress_message(3, 10, 4, stats, task_config)
        self.assertIn(task_config.hit_status, message)

        lines = format_completion_lines(10, stats, Path("output.xlsx"), task_config)
        self.assertTrue(any(task_config.hit_status in line for line in lines))


if __name__ == "__main__":
    unittest.main()
