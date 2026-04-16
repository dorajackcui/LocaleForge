from __future__ import annotations

import unittest

from localeforge.cli import build_parser
from localeforge.config.tasks import get_task_config
from localeforge.prompts import default_prompt_path


class TaskConfigTests(unittest.TestCase):
    def test_task_configs_resolve_default_prompts(self) -> None:
        english_task = get_task_config("english-check")
        term_task = get_task_config("term-extraction")

        self.assertEqual(default_prompt_path(english_task.task_id).name, "translation_checker_prompt.txt")
        self.assertEqual(default_prompt_path(term_task.task_id).name, "term_extractor_prompt.txt")

    def test_cli_accepts_term_extraction_task(self) -> None:
        args = build_parser().parse_args(["--task", "term-extraction"])
        self.assertEqual(args.task, "term-extraction")


if __name__ == "__main__":
    unittest.main()

