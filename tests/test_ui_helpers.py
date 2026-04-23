from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from localeforge.config.settings import AppSettings, ProviderConfig
from localeforge.config.tasks import get_task_config
from localeforge.ui.helpers import (
    api_provider_is_ready,
    build_run_request,
    format_completion_lines,
    format_progress_message,
    get_api_provider_models,
)


class UiHelperTests(unittest.TestCase):
    def test_build_run_request_normalizes_local_fields(self) -> None:
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
                settings=AppSettings(),
                execution_mode="local",
                provider_id=None,
                model=" gemma4:e4b ",
                api_url=" http://127.0.0.1:11434 ",
                concurrency_text=" 1 ",
            )

            self.assertEqual(request.execution_mode, "local")
            self.assertEqual(request.source_col, "A")
            self.assertEqual(request.result_col, "B")
            self.assertEqual(request.start_row, 2)
            self.assertEqual(request.model, "gemma4:e4b")
            self.assertEqual(request.api_url, "http://127.0.0.1:11434")
            self.assertEqual(request.concurrency, 1)
            self.assertTrue(request.output_path.name.endswith("_checked.xlsx"))

    def test_build_run_request_resolves_api_provider_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            input_path = Path(tmpdir) / "input.xlsx"
            prompt_path = Path(tmpdir) / "prompt.txt"
            input_path.write_text("stub", encoding="utf-8")
            prompt_path.write_text("{{STATUS_OK}} {{STATUS_SUSPECT}} {{TEXT}}", encoding="utf-8")
            settings = AppSettings(
                providers=[
                    ProviderConfig(
                        provider_id="demo",
                        name="Demo",
                        base_url="https://example.test/v1",
                        api_key="secret-key",
                        models=["gpt-4o-mini"],
                        last_tested_at="2026-04-23T10:00:00Z",
                    )
                ]
            )

            request = build_run_request(
                task_config=get_task_config("english-check"),
                input_text=str(input_path),
                output_text="",
                prompt_text=str(prompt_path),
                source_col_text="A",
                result_col_text="B",
                start_row_text="2",
                sheet_name="Sheet1",
                settings=settings,
                execution_mode="api",
                provider_id="demo",
                model="gpt-4o-mini",
                api_url="",
                concurrency_text="4",
            )

            self.assertEqual(request.execution_mode, "api")
            self.assertEqual(request.provider_id, "demo")
            self.assertEqual(request.api_key, "secret-key")
            self.assertEqual(request.api_url, "https://example.test/v1")
            self.assertEqual(request.concurrency, 4)

    def test_format_helpers_include_task_hit_status(self) -> None:
        task_config = get_task_config("term-extraction")
        stats = {"OK": 2, "EMPTY": 1, task_config.hit_status: 3, "MODEL_CALLS": 4, "CACHE_HITS": 1}
        message = format_progress_message(3, 10, 4, stats, task_config)
        self.assertIn(task_config.hit_status, message)

        lines = format_completion_lines(10, stats, Path("output.xlsx"), task_config)
        self.assertTrue(any(task_config.hit_status in line for line in lines))
        self.assertIn("Summary tab: TermSummary", lines)

    def test_get_api_provider_models_returns_saved_models(self) -> None:
        settings = AppSettings(
            providers=[
                ProviderConfig(
                    provider_id="demo",
                    name="Demo",
                    base_url="https://example.test/v1",
                    api_key="secret-key",
                    models=["gpt-4o-mini", "gpt-4.1-mini"],
                    last_tested_at="2026-04-23T10:00:00Z",
                )
            ]
        )

        self.assertEqual(get_api_provider_models(settings, "demo"), ["gpt-4o-mini", "gpt-4.1-mini"])

    def test_api_provider_is_ready_requires_models_and_key(self) -> None:
        settings = AppSettings(
            providers=[
                ProviderConfig(
                    provider_id="ready",
                    name="Ready",
                    base_url="https://example.test/v1",
                    api_key="secret-key",
                    models=["gpt-4o-mini"],
                    last_tested_at="2026-04-23T10:00:00Z",
                ),
                ProviderConfig(
                    provider_id="missing-models",
                    name="Missing Models",
                    base_url="https://example.test/v1",
                    api_key="secret-key",
                    models=[],
                    last_tested_at=None,
                ),
            ]
        )

        self.assertTrue(api_provider_is_ready(settings, "ready"))
        self.assertFalse(api_provider_is_ready(settings, "missing-models"))
        self.assertFalse(api_provider_is_ready(settings, "unknown"))


if __name__ == "__main__":
    unittest.main()
