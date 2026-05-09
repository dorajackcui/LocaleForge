from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import InputOutputError, ModelProviderError, PartialFailureError
from .inputs import WorkItem, discover_work_items
from .modes import ProcessedResult, process_model_response
from .providers import ModelClient
from .report import FileReport, ModelReport, RunReport, TaskReport
from .tabular import Table, load_table
from .task_profile import TaskProfile


@dataclass(frozen=True)
class RunOptions:
    input_path: Path
    output_dir: Path | None = None
    output_path: Path | None = None
    input_col: str | None = None
    output_col: str | None = None
    sheet: str | None = None
    execution_mode: str = "local"
    provider: str | None = None
    model: str = ""


def validate_task(profile: TaskProfile, task_path: Path, options: RunOptions) -> RunReport:
    items = discover_work_items(options.input_path, options.output_dir, options.output_path)
    report = _new_report(profile, task_path, options)
    errors: list[str] = []

    for item in items:
        try:
            table = _load_for_profile(item.input, profile, options)
            source_col = table.resolve_column(options.input_col or profile.input.column, create=False)
            table.resolve_column(options.output_col or profile.output.column, create=profile.output.create)
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


def run_task(profile: TaskProfile, task_path: Path, options: RunOptions, client: ModelClient) -> RunReport:
    items = discover_work_items(options.input_path, options.output_dir, options.output_path)
    report = _new_report(profile, task_path, options)
    cache: dict[str, ProcessedResult] = {}
    errors: list[str] = []

    for item in items:
        try:
            file_report = _run_file(profile, options, item, client, cache)
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
) -> FileReport:
    table = _load_for_profile(item.input, profile, options)
    source_col = table.resolve_column(options.input_col or profile.input.column, create=False)
    target_col = table.resolve_column(options.output_col or profile.output.column, create=profile.output.create)
    details_col: int | None = None
    if profile.mode == "status-json" and profile.output.details_column:
        details_col = table.resolve_column(profile.output.details_column, create=True)

    rows_total = max(table.max_row - profile.input.start_row + 1, 0)
    file_report = FileReport(status="success", input=item.input, output=item.output, rows_total=rows_total)

    for row_idx in range(profile.input.start_row, table.max_row + 1):
        source_text = table.get_cell(row_idx, source_col)
        if not source_text:
            file_report.rows_empty += 1
            continue

        if source_text in cache:
            processed = cache[source_text]
            file_report.cache_hits += 1
        else:
            raw = client.generate(profile.prompt, source_text)
            processed = process_model_response(profile.mode, raw)
            cache[source_text] = processed
            file_report.model_calls += 1

        if profile.output.overwrite or not table.get_cell(row_idx, target_col):
            table.set_cell(row_idx, target_col, processed.primary)
        if details_col is not None and processed.details:
            table.set_cell(row_idx, details_col, processed.details)
        file_report.rows_processed += 1

    table.save(item.output)
    return file_report


def _load_for_profile(path: Path, profile: TaskProfile, options: RunOptions) -> Table:
    return load_table(path, sheet_name=options.sheet or profile.input.sheet, header_row=profile.input.header_row)


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
