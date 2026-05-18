from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

from .errors import ConfigError, InputOutputError, ModelProviderError, PartialFailureError
from .inputs import WorkItem, discover_work_items
from .modes import ProcessedResult, process_model_response
from .progress import ProgressReporter
from .providers import ModelClient
from .report import FileReport, ModelReport, RunReport, TaskReport
from .tabular import Table, load_table
from .task_profile import TaskProfile
from .windowing import (
    WindowSourceRow,
    build_window_user_text,
    process_window_response,
    window_prompt_instructions,
)


@dataclass(frozen=True)
class RunOptions:
    input_path: Path
    output_dir: Path | None = None
    output_path: Path | None = None
    allow_overwrite_output: bool = False
    input_col: str | None = None
    output_col: str | None = None
    sheet: str | None = None
    execution_mode: str = "api"
    provider: str | None = None
    model: str = ""
    concurrency: int = 1
    max_attempts: int = 2
    tips: str | None = None
    request_mode: str = "concurrent"
    window_size: int = 5


def validate_task(profile: TaskProfile, task_path: Path, options: RunOptions) -> RunReport:
    _validate_request_contract(profile, options)
    items = discover_work_items(
        options.input_path,
        options.output_dir,
        options.output_path,
        output_suffix=profile.id,
        allow_overwrite=options.allow_overwrite_output,
    )
    report = _new_report(profile, task_path, options)
    errors: list[str] = []

    for item in items:
        try:
            table = _load_for_profile(item.input, profile, options)
            source_col = table.resolve_column(options.input_col or profile.input.column, create=False)
            _validate_output_columns(table, profile, options)
            rows_total = max(table.max_row - profile.input.start_row + 1, 0)
            report.files.append(
                FileReport(
                    status="success",
                    input=item.input,
                    output=item.output,
                    rows_total=rows_total,
                )
            )
            _ = source_col
        except Exception as exc:
            errors.append(str(exc))
            report.files.append(_failed_file(item, exc))

    if errors:
        report.status = "partial_failure" if len(items) > 1 else "error"
        report.errors.extend(errors)
    return report


def run_task(
    profile: TaskProfile,
    task_path: Path,
    options: RunOptions,
    client: ModelClient,
    progress: ProgressReporter | None = None,
) -> RunReport:
    _validate_request_contract(profile, options)
    items = discover_work_items(
        options.input_path,
        options.output_dir,
        options.output_path,
        output_suffix=profile.id,
        allow_overwrite=options.allow_overwrite_output,
    )
    report = _new_report(profile, task_path, options)
    cache: dict[str, ProcessedResult] = {}
    errors: list[str] = []

    for file_index, item in enumerate(items, start=1):
        try:
            file_report = _run_file(profile, options, item, client, cache, progress, file_index, len(items))
            report.files.append(file_report)
        except Exception as exc:
            if len(items) == 1:
                raise
            errors.append(str(exc))
            report.files.append(_failed_file(item, exc))

    if errors:
        report.status = "partial_failure"
        report.errors.extend(errors)
    return report


def _run_file(
    profile: TaskProfile,
    options: RunOptions,
    item: WorkItem,
    client: ModelClient,
    cache: dict[str, ProcessedResult],
    progress: ProgressReporter | None,
    file_index: int,
    file_count: int,
) -> FileReport:
    table = _load_for_profile(item.input, profile, options)
    source_col = table.resolve_column(options.input_col or profile.input.column, create=False)
    target_col: int | None = None
    if profile.mode == "transform":
        target_col = table.resolve_column(options.output_col or profile.output.column, create=profile.output.create)

    if options.request_mode == "window":
        return _run_file_window(
            profile,
            options,
            item,
            client,
            table,
            source_col,
            target_col,
            progress,
            file_index,
            file_count,
        )
    return _run_file_concurrent(
        profile,
        options,
        item,
        client,
        cache,
        table,
        source_col,
        target_col,
        progress,
        file_index,
        file_count,
    )


def _run_file_concurrent(
    profile: TaskProfile,
    options: RunOptions,
    item: WorkItem,
    client: ModelClient,
    cache: dict[str, ProcessedResult],
    table: Table,
    source_col: int,
    target_col: int | None,
    progress: ProgressReporter | None,
    file_index: int,
    file_count: int,
) -> FileReport:
    rows_total = max(table.max_row - profile.input.start_row + 1, 0)
    file_report = FileReport(status="success", input=item.input, output=item.output, rows_total=rows_total)
    if progress:
        progress.file_start(file_index, file_count, item.input, rows_total)

    results_by_row: dict[int, ProcessedResult] = {}
    pending: dict[str, list[int]] = {}
    rows_done = 0
    for row_idx in range(profile.input.start_row, table.max_row + 1):
        source_text = table.get_cell(row_idx, source_col)
        if not source_text:
            file_report.rows_empty += 1
            rows_done += 1
            continue

        if source_text in cache:
            results_by_row[row_idx] = cache[source_text]
            file_report.cache_hits += 1
            file_report.rows_processed += 1
            rows_done += 1
            _emit_progress(progress, file_index, file_count, item.input, rows_done, rows_total, file_report)
        elif source_text in pending:
            pending[source_text].append(row_idx)
            file_report.cache_hits += 1
        else:
            pending[source_text] = [row_idx]

    for source_text, processed, attempts in _generate_pending(profile, options, client, pending):
        cache[source_text] = processed
        row_indices = pending[source_text]
        file_report.model_calls += attempts
        file_report.rows_processed += len(row_indices)
        rows_done += len(row_indices)
        for row_idx in row_indices:
            results_by_row[row_idx] = processed
        _emit_progress(progress, file_index, file_count, item.input, rows_done, rows_total, file_report)

    for row_idx in sorted(results_by_row):
        processed = results_by_row[row_idx]
        if profile.mode == "status-json":
            _write_json_fields(table, row_idx, processed, profile)
        else:
            assert target_col is not None
            if profile.output.overwrite or not table.get_cell(row_idx, target_col):
                table.set_cell(row_idx, target_col, processed.primary)

    table.save(item.output)
    if progress:
        progress.file_done(file_index, file_count, item.input, rows_total, file_report.model_calls, file_report.cache_hits)
    return file_report


def _run_file_window(
    profile: TaskProfile,
    options: RunOptions,
    item: WorkItem,
    client: ModelClient,
    table: Table,
    source_col: int,
    target_col: int | None,
    progress: ProgressReporter | None,
    file_index: int,
    file_count: int,
) -> FileReport:
    rows_total = max(table.max_row - profile.input.start_row + 1, 0)
    file_report = FileReport(status="success", input=item.input, output=item.output, rows_total=rows_total)
    if progress:
        progress.file_start(file_index, file_count, item.input, rows_total)

    source_rows: list[WindowSourceRow] = []
    for row_idx in range(profile.input.start_row, table.max_row + 1):
        source_text = table.get_cell(row_idx, source_col)
        if not source_text:
            file_report.rows_empty += 1
            continue
        source_rows.append(WindowSourceRow(row=row_idx, source=source_text))

    results_by_row: dict[int, ProcessedResult] = {}
    rows_done = file_report.rows_empty
    for start in range(0, len(source_rows), options.window_size):
        current = source_rows[start : start + options.window_size]
        previous_rows = source_rows[max(0, start - options.window_size) : start]
        next_rows = source_rows[start + options.window_size : start + (options.window_size * 2)]
        previous = [_window_previous_item(row, results_by_row[row.row]) for row in previous_rows if row.row in results_by_row]

        processed_by_row, attempts = _generate_window(profile, options, client, previous, current, next_rows)
        results_by_row.update(processed_by_row)
        file_report.model_calls += attempts
        file_report.rows_processed += len(current)
        rows_done += len(current)
        _emit_progress(progress, file_index, file_count, item.input, rows_done, rows_total, file_report)

    for row_idx in sorted(results_by_row):
        processed = results_by_row[row_idx]
        if profile.mode == "status-json":
            _write_json_fields(table, row_idx, processed, profile, force_overwrite=True)
        else:
            assert target_col is not None
            table.set_cell(row_idx, target_col, processed.primary)

    table.save(item.output)
    if progress:
        progress.file_done(file_index, file_count, item.input, rows_total, file_report.model_calls, file_report.cache_hits)
    return file_report


def _window_previous_item(row: WindowSourceRow, processed: ProcessedResult) -> dict[str, object]:
    target: object = processed.fields if processed.fields else processed.primary
    return {"row": row.row, "source": row.source, "target": target}


def _generate_pending(
    profile: TaskProfile,
    options: RunOptions,
    client: ModelClient,
    pending: dict[str, list[int]],
) -> Iterator[tuple[str, ProcessedResult, int]]:
    if not pending:
        return
    if options.concurrency <= 1:
        for source_text in pending:
            processed, attempts = _generate_processed(profile, options, client, source_text)
            yield source_text, processed, attempts
        return

    with ThreadPoolExecutor(max_workers=options.concurrency) as executor:
        futures = {
            executor.submit(_generate_processed, profile, options, client, source_text): source_text
            for source_text in pending
        }
        for future in as_completed(futures):
            source_text = futures[future]
            processed, attempts = future.result()
            yield source_text, processed, attempts


def _generate_processed(
    profile: TaskProfile,
    options: RunOptions,
    client: ModelClient,
    source_text: str,
) -> tuple[ProcessedResult, int]:
    max_attempts = max(1, options.max_attempts)
    last_error: ModelProviderError | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            raw = client.generate(_prompt_for_attempt(profile, options, attempt, last_error), source_text)
            processed = process_model_response(profile.mode, raw)
            _validate_processed_result(profile, processed)
            return processed, attempt
        except ModelProviderError as exc:
            last_error = exc
            if attempt == max_attempts:
                raise ModelProviderError(f"Model failed after {max_attempts} attempts. Last error: {exc}") from exc

    raise ModelProviderError("Model failed before producing a response.")


def _generate_window(
    profile: TaskProfile,
    options: RunOptions,
    client: ModelClient,
    previous: list[dict[str, object]],
    current: list[WindowSourceRow],
    next_rows: list[WindowSourceRow],
) -> tuple[dict[int, ProcessedResult], int]:
    max_attempts = max(1, options.max_attempts)
    last_error: ModelProviderError | None = None
    user_text = build_window_user_text(previous, current, next_rows)
    for attempt in range(1, max_attempts + 1):
        try:
            raw = client.generate(_window_prompt_for_attempt(profile, options, attempt, last_error), user_text)
            processed = process_window_response(profile, raw, current)
            for item in processed.values():
                _validate_processed_result(profile, item)
            return processed, attempt
        except ModelProviderError as exc:
            last_error = exc
            if attempt == max_attempts:
                raise ModelProviderError(f"Model failed after {max_attempts} attempts. Last error: {exc}") from exc

    raise ModelProviderError("Model failed before producing a window response.")


def _prompt_for_attempt(
    profile: TaskProfile,
    options: RunOptions,
    attempt: int,
    last_error: ModelProviderError | None,
) -> str:
    prompt = _prompt_with_tips(profile.prompt, options.tips)
    if attempt <= 1 or last_error is None:
        return prompt

    if profile.mode == "status-json":
        retry_instruction = (
            "Previous attempt failed: "
            f"{last_error}\n"
            "Return exactly one valid JSON object. Do not wrap it in markdown or add prose."
        )
    else:
        retry_instruction = (
            "Previous attempt failed: "
            f"{last_error}\n"
            "Return a valid, non-empty response that satisfies the task."
        )
    return f"{prompt}\n\n{retry_instruction}"


def _window_prompt_for_attempt(
    profile: TaskProfile,
    options: RunOptions,
    attempt: int,
    last_error: ModelProviderError | None,
) -> str:
    prompt = f"{_prompt_with_tips(profile.prompt, options.tips)}\n\n{window_prompt_instructions(profile)}"
    if attempt <= 1 or last_error is None:
        return prompt
    return (
        f"{prompt}\n\n"
        f"Previous attempt failed: {last_error}\n"
        "Return exactly one valid JSON array. Do not wrap it in markdown or add prose."
    )


def _prompt_with_tips(prompt: str, tips: str | None) -> str:
    clean_tips = str(tips or "").strip()
    if not clean_tips:
        return prompt
    return f"{prompt}\n\nSession tips:\n{clean_tips}"


def _emit_progress(
    progress: ProgressReporter | None,
    file_index: int,
    file_count: int,
    input_path: Path,
    rows_done: int,
    rows_total: int,
    file_report: FileReport,
) -> None:
    if progress:
        progress.file_progress(
            file_index,
            file_count,
            input_path,
            rows_done,
            rows_total,
            file_report.model_calls,
            file_report.cache_hits,
        )


def _load_for_profile(path: Path, profile: TaskProfile, options: RunOptions) -> Table:
    return load_table(path, sheet_name=options.sheet or profile.input.sheet, header_row=profile.input.header_row)


def _validate_request_contract(profile: TaskProfile, options: RunOptions) -> None:
    if options.request_mode not in {"concurrent", "window"}:
        raise ConfigError(f"Unsupported request mode `{options.request_mode}`.")
    if options.window_size < 1:
        raise ConfigError("Window size must be a positive integer.")
    if options.request_mode == "window" and profile.mode == "status-json" and not profile.output.fields:
        raise ConfigError("Window request mode requires status-json tasks to declare output.fields.")


def _validate_output_columns(table: Table, profile: TaskProfile, options: RunOptions) -> None:
    if profile.mode != "status-json":
        table.resolve_column(options.output_col or profile.output.column, create=profile.output.create)
        return
    for field_name in profile.output.fields:
        table.resolve_column(_json_output_column(profile, field_name), create=profile.output.create)
    for column_name in profile.output.columns.values():
        table.resolve_column(column_name, create=profile.output.create)
    if profile.output.details_column:
        table.resolve_column(profile.output.details_column, create=profile.output.create)


def _write_json_fields(
    table: Table,
    row_idx: int,
    processed: ProcessedResult,
    profile: TaskProfile,
    force_overwrite: bool = False,
) -> None:
    field_names = profile.output.fields or tuple(processed.fields.keys())
    for field_name in field_names:
        value = processed.fields.get(field_name, "")
        column_name = _json_output_column(profile, field_name)
        column = table.resolve_column(column_name, create=profile.output.create)
        if force_overwrite or profile.output.overwrite or not table.get_cell(row_idx, column):
            table.set_cell(row_idx, column, value)


def _json_output_column(profile: TaskProfile, field_name: str) -> str:
    if field_name in profile.output.columns:
        return profile.output.columns[field_name]
    if field_name == "spans" and profile.output.details_column:
        return profile.output.details_column
    return field_name


def _validate_processed_result(profile: TaskProfile, processed: ProcessedResult) -> None:
    if profile.mode != "status-json" or not profile.output.fields:
        return

    expected = set(profile.output.fields)
    actual = set(processed.fields)
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown fields: {', '.join(unknown)}")
        raise ModelProviderError("Model JSON response did not match declared output.fields: " + "; ".join(details))


def _new_report(profile: TaskProfile, task_path: Path, options: RunOptions) -> RunReport:
    return RunReport(
        status="success",
        task=TaskReport(id=profile.id, mode=profile.mode, path=task_path),
        model=ModelReport(execution_mode=options.execution_mode, provider=options.provider, name=options.model),
    )


def _failed_file(item: WorkItem, error: BaseException) -> FileReport:
    return FileReport(
        status="error",
        input=item.input,
        output=item.output,
        errors=[str(error)],
    )


def raise_for_report(report: RunReport) -> None:
    if report.status == "partial_failure":
        raise PartialFailureError("; ".join(report.errors) or "One or more files failed.")
    if report.status == "error":
        message = "; ".join(report.errors) or "Run failed."
        if any(file.errors for file in report.files):
            raise InputOutputError(message)
        raise ModelProviderError(message)
