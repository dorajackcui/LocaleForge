from __future__ import annotations

from pathlib import Path

from ..config.settings import MAX_CONCURRENCY, MIN_CONCURRENCY, AppSettings, get_provider
from ..config.tasks import STATUS_EMPTY, STATUS_OK, TaskConfig
from ..runtime import TaskRunRequest
from ..workbook import default_output_path


class ValidationError(ValueError):
    """Raised when UI form values are invalid."""


def get_api_provider_models(settings: AppSettings, provider_id: str | None) -> list[str]:
    provider = get_provider(settings, provider_id)
    if provider is None:
        return []
    return list(provider.models)


def api_provider_is_ready(settings: AppSettings, provider_id: str | None) -> bool:
    provider = get_provider(settings, provider_id)
    return provider is not None and bool(provider.api_key.strip()) and bool(provider.models)


def build_run_request(
    task_config: TaskConfig,
    input_text: str,
    output_text: str,
    prompt_text: str,
    source_col_text: str,
    result_col_text: str,
    start_row_text: str,
    sheet_name: str,
    settings: AppSettings,
    execution_mode: str,
    provider_id: str | None,
    model: str,
    api_url: str,
    concurrency_text: str,
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

    try:
        concurrency = int(concurrency_text)
    except ValueError as exc:
        raise ValidationError("Concurrency must be an integer.") from exc

    if concurrency < MIN_CONCURRENCY or concurrency > MAX_CONCURRENCY:
        raise ValidationError(f"Concurrency must be between {MIN_CONCURRENCY} and {MAX_CONCURRENCY}.")

    output_path = Path(output_text).expanduser() if output_text.strip() else default_output_path(input_path)
    normalized_mode = execution_mode.strip() or "local"
    normalized_model = model.strip()
    normalized_api_url = api_url.strip()
    normalized_provider_id = provider_id.strip() if provider_id else None
    api_key: str | None = None

    if normalized_mode == "api":
        provider = get_provider(settings, normalized_provider_id)
        if provider is None:
            raise ValidationError("Please choose a tested API provider.")
        if not provider.models:
            raise ValidationError("Selected API provider has no tested models yet.")
        if not normalized_model:
            raise ValidationError("Please choose an API model.")
        normalized_api_url = normalized_api_url or provider.base_url
        api_key = provider.api_key
        if not api_key:
            raise ValidationError("Selected API provider is missing an API key.")
    else:
        normalized_mode = "local"
        normalized_provider_id = None
        if not normalized_api_url:
            raise ValidationError("Local API URL is required.")
        if not normalized_model:
            raise ValidationError("Local model is required.")

    return TaskRunRequest(
        task_config=task_config,
        input_path=input_path.resolve(),
        output_path=output_path.resolve(),
        prompt_path=prompt_path.resolve(),
        sheet_name=sheet_name.strip(),
        source_col=source_col_text.strip().upper(),
        result_col=result_col_text.strip().upper(),
        start_row=start_row,
        execution_mode=normalized_mode,
        provider_id=normalized_provider_id,
        api_url=normalized_api_url,
        api_key=api_key,
        model=normalized_model,
        concurrency=concurrency,
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
    lines = [
        "Finished.",
        f"Rows processed : {total_rows}",
        f"{STATUS_OK}: {stats[STATUS_OK]}",
        f"{task_config.hit_status}: {stats[task_config.hit_status]}",
        f"{STATUS_EMPTY}: {stats[STATUS_EMPTY]}",
        f"MODEL_CALLS: {stats['MODEL_CALLS']}",
        f"CACHE_HITS : {stats['CACHE_HITS']}",
        f"Saved to   : {output_path}",
    ]
    if task_config.summary_sheet_name is not None:
        lines.append(f"Summary tab: {task_config.summary_sheet_name}")
    return lines
