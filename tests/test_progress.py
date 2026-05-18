from __future__ import annotations

import unittest
from io import StringIO
from pathlib import Path

from localeforge.progress import ProgressReporter


class ProgressReporterTests(unittest.TestCase):
    def test_text_progress_uses_done_over_total_format(self) -> None:
        stream = StringIO()
        reporter = ProgressReporter(mode="text", stream=stream)
        path = Path("mt.localeforge.xlsx")

        reporter.file_start(1, 1, path, rows_total=19)
        reporter.file_done(1, 1, path, rows_total=19, model_calls=19, cache_hits=0)

        text = stream.getvalue()
        self.assertIn("[1/1] mt.localeforge.xlsx start rows 0/19", text)
        self.assertIn("[1/1] mt.localeforge.xlsx done rows 19/19 calls=19 cache=0", text)


if __name__ == "__main__":
    unittest.main()
