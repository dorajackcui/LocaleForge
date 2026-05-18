from __future__ import annotations

import json
import unittest
from pathlib import Path

from localeforge.errors import ConfigError, InputOutputError, ModelProviderError, PartialFailureError, exit_code_for_error
from localeforge.report import FileReport, ModelReport, RunReport, TaskReport


class ErrorsAndReportTests(unittest.TestCase):
    def test_error_exit_codes_are_stable(self) -> None:
        self.assertEqual(exit_code_for_error(ConfigError("bad config")), 1)
        self.assertEqual(exit_code_for_error(InputOutputError("bad file")), 2)
        self.assertEqual(exit_code_for_error(ModelProviderError("bad model")), 3)
        self.assertEqual(exit_code_for_error(PartialFailureError("partial")), 4)

    def test_run_report_serializes_paths_and_counts(self) -> None:
        report = RunReport(
            status="success",
            task=TaskReport(id="proofread", mode="transform", path=Path("tasks/proofread.md")),
            model=ModelReport(execution_mode="api", provider="default-api", name="gpt-4.1-mini"),
            files=[
                FileReport(
                    status="success",
                    input=Path("data/a.csv"),
                    output=Path("out/a_proofread.csv"),
                    rows_total=2,
                    rows_processed=1,
                    rows_empty=1,
                    model_calls=1,
                    cache_hits=0,
                    errors=[],
                )
            ],
            errors=[],
        )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["files"][0]["input"], "data/a.csv")
        self.assertEqual(json.loads(report.to_json())["task"]["id"], "proofread")


if __name__ == "__main__":
    unittest.main()
