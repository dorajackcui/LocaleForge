from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from localeforge.cli import _build_request_from_args, build_parser
from localeforge.config.settings import ApiDefaults, AppDefaults, AppSettings, LocalDefaults, ProviderConfig
from localeforge.config.tasks import get_task_config
from localeforge.prompts import default_prompt_path
from localeforge.runtime import TaskRunRequest, run_task


class TaskConfigTests(unittest.TestCase):
    def test_task_configs_resolve_default_prompts(self) -> None:
        english_task = get_task_config("english-check")
        term_task = get_task_config("term-extraction")

        self.assertEqual(default_prompt_path(english_task.task_id).name, "translation_checker_prompt.txt")
        self.assertEqual(default_prompt_path(term_task.task_id).name, "term_extractor_prompt.txt")

    def test_cli_accepts_term_extraction_task(self) -> None:
        args = build_parser().parse_args(["--task", "term-extraction"])
        self.assertEqual(args.task, "term-extraction")

    def test_cli_request_uses_saved_api_defaults_when_not_overridden(self) -> None:
        settings = AppSettings(
            defaults=AppDefaults(
                execution_mode="api",
                local=LocalDefaults(),
                api=ApiDefaults(provider_id="demo", model="gpt-4o-mini", concurrency=5),
            ),
            providers=[
                ProviderConfig(
                    provider_id="demo",
                    name="Demo",
                    base_url="https://example.test/v1",
                    api_key="secret-key",
                    models=["gpt-4o-mini", "gpt-4.1-mini"],
                    last_tested_at="2026-04-23T10:00:00Z",
                )
            ],
        )
        args = build_parser().parse_args(
            [
                "--input",
                "input.xlsx",
                "--output",
                "output.xlsx",
            ]
        )

        request = _build_request_from_args(args, settings)

        self.assertEqual(request.execution_mode, "api")
        self.assertEqual(request.provider_id, "demo")
        self.assertEqual(request.api_url, "https://example.test/v1")
        self.assertEqual(request.api_key, "secret-key")
        self.assertEqual(request.model, "gpt-4o-mini")
        self.assertEqual(request.concurrency, 5)

    @patch(
        "localeforge.runtime.process_workbook",
        return_value=(0, {"OK": 0, "EMPTY": 0, "疑似英文未翻译": 0, "MODEL_CALLS": 0, "CACHE_HITS": 0}),
    )
    @patch("localeforge.runtime.load_prompt_template", return_value="{{TEXT}}")
    @patch("localeforge.runtime.OpenAICompatibleClient")
    def test_runtime_uses_openai_compatible_client_for_api_mode(
        self,
        openai_client,
        _load_prompt,
        _process_workbook,
    ) -> None:
        request = TaskRunRequest(
            task_config=get_task_config("english-check"),
            input_path=Path("dummy.xlsx"),
            output_path=Path("dummy_out.xlsx"),
            prompt_path=default_prompt_path(),
            sheet_name="Sheet1",
            source_col="A",
            result_col="B",
            start_row=2,
            execution_mode="api",
            provider_id="demo",
            api_url="https://example.test/v1",
            api_key="secret-key",
            model="gpt-4o-mini",
            concurrency=4,
            timeout=120.0,
        )

        run_task(request)

        openai_client.assert_called_once()


if __name__ == "__main__":
    unittest.main()
