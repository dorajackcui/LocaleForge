from __future__ import annotations

import unittest

from localeforge.config.tasks import STATUS_TERM_EXTRACTED, get_task_config
from localeforge.prompts import (
    default_prompt_path,
    load_prompt_template,
    render_chat_messages,
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

    def test_render_chat_messages_splits_default_prompt_into_system_and_user(self) -> None:
        task_config = get_task_config("english-check")
        template = load_prompt_template(default_prompt_path(task_config.task_id))

        messages = render_chat_messages(
            template,
            "{a}. Les MS de {b} etoiles ou plus d",
            task_config,
        )

        self.assertEqual(
            messages,
            [
                {
                    "role": "system",
                    "content": (
                        "Check whether this text, expected to be French, still contains any untranslated English.\n"
                        "Return JSON only.\n\n"
                        "Rules:\n"
                        "- MUST be strict.\n"
                        "- A single English word is enough.\n"
                        "- Do not ignore one token just because the rest is French.\n"
                        "- English-looking hyphenated forms are suspicious unless clearly protected by the exceptions below.\n"
                        "- If unsure, mark suspicious.\n\n"
                        "Allowed exceptions:\n"
                        "- Tags or placeholders, for example: {a}, {player_name}, <color=red>, %s\n\n"
                        "Output format:\n"
                        '- Suspicious: {"status":"疑似英文未翻译","spans":["token or phrase"]}\n'
                        '- Clean: {"status":"OK","spans":[]}\n\n'
                        "Do not translate. Do not explain.\n\n"
                        "The next user message contains the text to analyze."
                    ),
                },
                {
                    "role": "user",
                    "content": "{a}. Les MS de {b} etoiles ou plus d",
                },
            ],
        )

    def test_render_chat_messages_falls_back_when_text_placeholder_appears_multiple_times(self) -> None:
        task_config = get_task_config("english-check")

        messages = render_chat_messages(
            "Compare {{TEXT}} and {{TEXT}} with {{STATUS_SUSPECT}}.",
            "castle",
            task_config,
        )

        self.assertEqual(
            messages,
            [
                {
                    "role": "user",
                    "content": "Compare castle and castle with 疑似英文未翻译.",
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
