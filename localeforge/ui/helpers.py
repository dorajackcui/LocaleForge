from __future__ import annotations

from pathlib import Path

from ..config.tasks import STATUS_EMPTY, STATUS_OK, TaskConfig
from ..runtime import TaskRunRequest
from ..workbook import default_output_path


class ValidationError(ValueError):
    """Raised when UI form values are invalid."""


def build_run_request(
    task_config: TaskConfig,
    input_text: str,
    output_text: str,
    prompt_text: str,
    source_col_text: str,
    result_col_text: str,
    start_row_text: str,
    sheet_name: str,
    model: str,
    api_url: str,
    timeout: float = 120.0,
) -> TaskRunRequest:
    input_path = Path(input_text).expanduser()
    prompt_path = Path(prompt_text).expanduser()

    if not input_path.exists():
        raise ValidationError("Please choose an existing Excel file.")
    if not prompt_path.exists():
        raise ValidationError("Please choose an existing prompt file.")

    for label, value in (
        ("Source column", source_col_text),
        ("Output column", result_col_text),
    ):
        if not value.strip().isalpha():
            raise ValidationError(f"{label} must be letters like C or F.")

    try:
        start_row = int(start_row_text)
    except ValueError as exc:
        raise ValidationError("Start row must be an integer.") from exc

    if start_row < 1:
        raise ValidationError("Start row must be at least 1.")

    output_path = Path(output_text).expanduser() if output_text.strip() else default_output_path(input_path)
    return TaskRunRequest(
        task_config=task_config,
        input_path=input_path.resolve(),
        output_path=output_path.resolve(),
        prompt_path=prompt_path.resolve(),
        sheet_name=sheet_name.strip(),
        source_col=source_col_text.strip().upper(),
        result_col=result_col_text.strip().upper(),
        start_row=start_row,
        api_url=api_url.strip(),
        model=model.strip(),
        timeout=timeout,
    )


def format_progress_message(
    offset: int,
    total_rows: int,
    row_idx: int,
    stats: dict[str, int],
    task_config: TaskConfig,
) -> str:
    return (
        f"[{offset}/{total_rows}] row={row_idx} "
        f"OK={stats[STATUS_OK]} "
        f"{task_config.hit_status}={stats[task_config.hit_status]} "
        f"EMPTY={stats[STATUS_EMPTY]} "
        f"MODEL={stats['MODEL_CALLS']}"
    )


def format_completion_lines(
    total_rows: int,
    stats: dict[str, int],
    output_path: Path,
    task_config: TaskConfig,
) -> list[str]:
    return [
        "Finished.",
        f"Rows processed : {total_rows}",
        f"{STATUS_OK}: {stats[STATUS_OK]}",
        f"{task_config.hit_status}: {stats[task_config.hit_status]}",
        f"{STATUS_EMPTY}: {stats[STATUS_EMPTY]}",
        f"MODEL_CALLS: {stats['MODEL_CALLS']}",
        f"CACHE_HITS : {stats['CACHE_HITS']}",
        f"Saved to   : {output_path}",
    ]
