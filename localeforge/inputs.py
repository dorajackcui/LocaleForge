from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .errors import InputOutputError


SUPPORTED_SUFFIXES = {".csv", ".xlsx"}


@dataclass(frozen=True)
class WorkItem:
    input: Path
    output: Path


def with_localeforge_suffix(path: Path) -> Path:
    return path.with_name(f"{path.stem}.localeforge{path.suffix}")


def discover_work_items(
    input_path: Path | str,
    output_dir: Path | str | None = None,
    output_path: Path | str | None = None,
) -> list[WorkItem]:
    source = Path(input_path).expanduser().resolve()
    if not source.exists():
        raise InputOutputError(f"Input path does not exist: {source}")

    if source.is_file():
        _ensure_supported(source)
        output = Path(output_path).expanduser().resolve() if output_path else with_localeforge_suffix(source)
        if output == source:
            raise InputOutputError("Output path must be different from input path.")
        return [WorkItem(input=source, output=output)]

    if output_path is not None:
        raise InputOutputError("--output is only valid for single-file input.")
    if output_dir is None:
        raise InputOutputError("--output-dir is required when --input is a directory.")

    target_root = Path(output_dir).expanduser().resolve()
    items: list[WorkItem] = []
    for item in sorted(source.rglob("*")):
        if not item.is_file() or item.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        relative = item.relative_to(source)
        output = target_root / relative.parent / with_localeforge_suffix(relative).name
        items.append(WorkItem(input=item.resolve(), output=output.resolve()))

    if not items:
        raise InputOutputError(f"No supported .xlsx or .csv files found in: {source}")
    return items


def _ensure_supported(path: Path) -> None:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        known = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise InputOutputError(f"Unsupported input file type `{path.suffix}`. Supported: {known}.")
