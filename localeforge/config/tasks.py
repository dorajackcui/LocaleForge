from __future__ import annotations

from dataclasses import dataclass


STATUS_OK = "OK"
STATUS_EMPTY = "EMPTY"
STATUS_SUSPECT = "\u7591\u4f3c\u82f1\u6587\u672a\u7ffb\u8bd1"
STATUS_TERM_EXTRACTED = "\u63d0\u53d6\u5230\u672f\u8bed"
DEFAULT_INPUT_NAME = "\u670d\u88c5\u76f8\u5173.xlsx"
DEFAULT_TASK_ID = "english-check"
DEFAULT_PROMPT_FILE = "translation_checker_prompt.txt"
DEFAULT_TERM_PROMPT_FILE = "term_extractor_prompt.txt"


@dataclass(frozen=True)
class TaskConfig:
    task_id: str
    display_name: str
    prompt_file_name: str
    result_header: str
    details_header: str
    hit_status: str
    use_rule_precheck: bool


TASK_CONFIGS: dict[str, TaskConfig] = {
    "english-check": TaskConfig(
        task_id="english-check",
        display_name="French translation English leak check",
        prompt_file_name=DEFAULT_PROMPT_FILE,
        result_header="CheckResult",
        details_header="CheckResultSpans",
        hit_status=STATUS_SUSPECT,
        use_rule_precheck=True,
    ),
    "term-extraction": TaskConfig(
        task_id="term-extraction",
        display_name="Game term extraction",
        prompt_file_name=DEFAULT_TERM_PROMPT_FILE,
        result_header="TermExtractResult",
        details_header="ExtractedTerms",
        hit_status=STATUS_TERM_EXTRACTED,
        use_rule_precheck=False,
    ),
}
TASK_DISPLAY_TO_ID = {config.display_name: task_id for task_id, config in TASK_CONFIGS.items()}


def get_task_config(task_id: str = DEFAULT_TASK_ID) -> TaskConfig:
    try:
        return TASK_CONFIGS[task_id]
    except KeyError as exc:
        known = ", ".join(TASK_CONFIGS)
        raise KeyError(f"Unknown task `{task_id}`. Available tasks: {known}") from exc


def get_task_config_by_display_name(display_name: str) -> TaskConfig:
    task_id = TASK_DISPLAY_TO_ID.get(display_name)
    if task_id is None:
        return get_task_config(DEFAULT_TASK_ID)
    return get_task_config(task_id)


def get_task_display_names() -> list[str]:
    return [config.display_name for config in TASK_CONFIGS.values()]
