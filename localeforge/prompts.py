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
