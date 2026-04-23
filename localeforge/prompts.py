from __future__ import annotations

from pathlib import Path

from .config.tasks import DEFAULT_TASK_ID, STATUS_OK, TaskConfig, get_task_config

PROMPT_STATUS_OK = "{{STATUS_OK}}"
PROMPT_STATUS_SUSPECT = "{{STATUS_SUSPECT}}"
PROMPT_TEXT = "{{TEXT}}"
REQUIRED_PROMPT_MARKERS = (
    PROMPT_STATUS_OK,
    PROMPT_STATUS_SUSPECT,
    PROMPT_TEXT,
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRAILING_TEXT_LABELS = {"text:", "input:", "content:"}


def default_prompt_path(task_id: str = DEFAULT_TASK_ID) -> Path:
    return (PROJECT_ROOT / get_task_config(task_id).prompt_file_name).resolve()


def load_prompt_template(prompt_path: Path) -> str:
    resolved = Path(prompt_path).expanduser().resolve()
    if not resolved.exists():
        raise FileNotFoundError(f"Prompt file does not exist: {resolved}")

    template = resolved.read_text(encoding="utf-8").strip()
    if not template:
        raise ValueError(f"Prompt file is empty: {resolved}")

    missing = [marker for marker in REQUIRED_PROMPT_MARKERS if marker not in template]
    if missing:
        missing_list = ", ".join(missing)
        raise ValueError(
            f"Prompt file `{resolved}` is missing required placeholders: {missing_list}"
        )
    return template


def render_prompt(template: str, text: str, task_config: TaskConfig) -> str:
    prompt = template
    replacements = {
        PROMPT_STATUS_OK: STATUS_OK,
        PROMPT_STATUS_SUSPECT: task_config.hit_status,
        PROMPT_TEXT: text,
    }
    for marker, value in replacements.items():
        prompt = prompt.replace(marker, value)
    return prompt


def render_chat_messages(template: str, text: str, task_config: TaskConfig) -> list[dict[str, str]]:
    if template.count(PROMPT_TEXT) != 1:
        return [{"role": "user", "content": render_prompt(template, text, task_config)}]

    prefix, suffix = template.split(PROMPT_TEXT, maxsplit=1)
    system_sections: list[str] = []

    cleaned_prefix = _strip_trailing_text_label(prefix)
    if cleaned_prefix:
        system_sections.append(cleaned_prefix)

    cleaned_suffix = suffix.strip()
    if cleaned_suffix:
        system_sections.append(cleaned_suffix)

    system_sections.append("The next user message contains the text to analyze.")
    system_prompt = render_prompt("\n\n".join(system_sections), "", task_config)
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": text},
    ]


def _strip_trailing_text_label(prefix: str) -> str:
    lines = prefix.rstrip().splitlines()
    if lines and lines[-1].strip().lower() in TRAILING_TEXT_LABELS:
        lines = lines[:-1]
    return "\n".join(lines).rstrip()


def resolve_prompt_path_for_task_switch(
    current_prompt_text: str,
    previous_task: TaskConfig,
    new_task: TaskConfig,
) -> str:
    current_prompt = current_prompt_text.strip()
    if not current_prompt:
        return str(default_prompt_path(new_task.task_id))

    normalized_current = str(Path(current_prompt).expanduser().resolve())
    previous_default = str(default_prompt_path(previous_task.task_id))
    if normalized_current == previous_default:
        return str(default_prompt_path(new_task.task_id))
    return current_prompt_text
