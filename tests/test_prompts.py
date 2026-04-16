from __future__ import annotations

import unittest

from localeforge.config.tasks import STATUS_TERM_EXTRACTED, get_task_config
from localeforge.prompts import (
    default_prompt_path,
    load_prompt_template,
    render_prompt,
    resolve_prompt_path_for_task_switch,
)


class PromptTests(unittest.TestCase):
    def test_term_prompt_file_passes_template_validation(self) -> None:
        template = load_prompt_template(default_prompt_path("term-extraction"))
        self.assertIn("{{STATUS_OK}}", template)
        self.assertIn("{{STATUS_SUSPECT}}", template)
        self.assertIn("{{TEXT}}", template)

    def test_render_prompt_maps_hit_status_for_term_task(self) -> None:
        task_config = get_task_config("term-extraction")
        prompt = render_prompt(
            'status="{{STATUS_SUSPECT}}" ok="{{STATUS_OK}}" text="{{TEXT}}"',
            "Mana",
            task_config,
        )
        self.assertIn(f'status="{STATUS_TERM_EXTRACTED}"', prompt)
        self.assertIn('ok="OK"', prompt)
        self.assertIn('text="Mana"', prompt)

    def test_prompt_switch_updates_only_for_default_prompt(self) -> None:
        english_task = get_task_config("english-check")
        term_task = get_task_config("term-extraction")

        switched = resolve_prompt_path_for_task_switch(
            str(default_prompt_path(english_task.task_id)),
            english_task,
            term_task,
        )
        self.assertEqual(switched, str(default_prompt_path(term_task.task_id)))

        custom = resolve_prompt_path_for_task_switch(
            "custom_prompt.txt",
            english_task,
            term_task,
        )
        self.assertEqual(custom, "custom_prompt.txt")


if __name__ == "__main__":
    unittest.main()

