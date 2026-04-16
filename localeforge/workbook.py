from __future__ import annotations

from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import column_index_from_string

from .config.tasks import DEFAULT_INPUT_NAME, STATUS_EMPTY, STATUS_OK, TaskConfig
from .rules import get_rule_decision, normalize_text
from .types import ClassificationResult, Classifier, ProgressCallback


def default_input_path() -> Path:
    preferred = Path.cwd() / DEFAULT_INPUT_NAME
    if preferred.exists():
        return preferred.resolve()

    matches = sorted(Path.cwd().glob("*.xlsx"))
    if matches:
        return matches[0].resolve()
    return preferred.resolve()


def default_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}_checked{input_path.suffix}")


def get_workbook_sheet_names(input_path: Path) -> list[str]:
    workbook = load_workbook(input_path, read_only=True)
    try:
        return list(workbook.sheetnames)
    finally:
        workbook.close()


def process_workbook(
    input_path: Path,
    output_path: Path,
    sheet_name: str,
    source_col: str,
    result_col: str,
    start_row: int,
    client: Classifier,
    task_config: TaskConfig,
    progress_callback: ProgressCallback | None = None,
) -> tuple[int, dict[str, int]]:
    workbook = load_workbook(input_path)
    if sheet_name not in workbook.sheetnames:
        available = ", ".join(workbook.sheetnames)
        raise KeyError(f"Worksheet `{sheet_name}` not found. Available sheets: {available}")

    worksheet = workbook[sheet_name]
    source_index = column_index_from_string(source_col)
    result_index = column_index_from_string(result_col)
    spans_index = result_index + 1

    if not worksheet.cell(row=1, column=result_index).value:
        worksheet.cell(row=1, column=result_index).value = task_config.result_header
    if not worksheet.cell(row=1, column=spans_index).value:
        worksheet.cell(row=1, column=spans_index).value = task_config.details_header

    cache: dict[str, ClassificationResult] = {}
    stats = {
        STATUS_OK: 0,
        STATUS_EMPTY: 0,
        task_config.hit_status: 0,
        "MODEL_CALLS": 0,
        "CACHE_HITS": 0,
    }

    total_rows = max(worksheet.max_row - start_row + 1, 0)
    for offset, row_idx in enumerate(range(start_row, worksheet.max_row + 1), start=1):
        raw_value = worksheet.cell(row=row_idx, column=source_index).value
        text = normalize_text(raw_value)

        decision = get_rule_decision(task_config, text)
        result: ClassificationResult | None = None

        if decision.status is not None:
            result = ClassificationResult(status=decision.status, spans=[])
        else:
            cached = cache.get(text)
            if cached is not None:
                result = cached
                stats["CACHE_HITS"] += 1
            else:
                result = client.classify(text)
                cache[text] = result
                stats["MODEL_CALLS"] += 1

        if result is None:
            raise RuntimeError(f"Failed to classify row {row_idx}")

        worksheet.cell(row=row_idx, column=result_index).value = result.status
        worksheet.cell(row=row_idx, column=spans_index).value = " | ".join(result.spans)
        stats[result.status] += 1

        if progress_callback is not None:
            progress_callback(offset, total_rows, row_idx, dict(stats))

    workbook.save(output_path)
    return total_rows, stats
