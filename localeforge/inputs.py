from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .errors import InputOutputError


SUPPORTED_SUFFIXES = {".csv", ".xlsx"}
UNSAFE_FILENAME_CHARS_RE = re.compile(r'[\x00-\x1f<>:"/\\|?*]+')


@dataclass(frozen=True)
class WorkItem:
    input: Path
    output: Path


def with_localeforge_suffix(path: Path) -> Path:
    return with_output_suffix(path, "localeforge")


def with_output_suffix(path: Path, suffix: str) -> Path:
    safe_suffix = _safe_filename_part(suffix)
    return path.with_name(f"{path.stem}_{safe_suffix}{path.suffix}")


def discover_work_items(
    input_path: Path | str,
    output_dir: Path | str | None = None,
    output_path: Path | str | None = None,
    output_suffix: str = "localeforge",
    allow_overwrite: bool = False,
) -> list[WorkItem]:
    source = Path(input_path).expanduser().resolve()
    if not source.exists():
        raise InputOutputError(f"Input path does not exist: {source}")

    if source.is_file():
        _ensure_supported(source)
        output = Path(output_path).expanduser().resolve() if output_path else with_output_suffix(source, output_suffix)
        _ensure_output_can_be_written(source, output, allow_overwrite)
        return [WorkItem(input=source, output=output)]

    if output_path is not None:
        raise InputOutputError("--output is only valid for single-file input.")
    if output_dir is None:
        raise InputOutputError("--output-dir is required when --input is a directory.")

    target_root = Path(output_dir).expanduser().resolve()
    if target_root == source or _is_relative_to(target_root, source):
        raise InputOutputError("Directory output root must be outside the input directory.")

    items: list[WorkItem] = []
    for item in sorted(source.rglob("*")):
        if not item.is_file() or item.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        relative = item.relative_to(source)
        output = target_root / relative.parent / with_output_suffix(relative, output_suffix).name
        resolved_output = output.resolve()
        _ensure_output_can_be_written(item.resolve(), resolved_output, allow_overwrite)
        items.append(WorkItem(input=item.resolve(), output=resolved_output))

    if not items:
        raise InputOutputError(f"No supported .xlsx or .csv files found in: {source}")
    return items


def _ensure_supported(path: Path) -> None:
    if path.suffix.lower() not in SUPPORTED_SUFFIXES:
        known = ", ".join(sorted(SUPPORTED_SUFFIXES))
        raise InputOutputError(f"Unsupported input file type `{path.suffix}`. Supported: {known}.")


def _ensure_output_can_be_written(input_path: Path, output_path: Path, allow_overwrite: bool) -> None:
    if output_path == input_path:
        raise InputOutputError("Output path must be different from input path.")
    if output_path.exists() and not allow_overwrite:
        raise InputOutputError(f"Output path already exists: {output_path}. Use --force to overwrite it.")


def _is_relative_to(path: Path, possible_parent: Path) -> bool:
    try:
        path.relative_to(possible_parent)
    except ValueError:
        return False
    return True


def _safe_filename_part(value: str) -> str:
    cleaned = UNSAFE_FILENAME_CHARS_RE.sub("-", str(value).strip())
    cleaned = cleaned.strip(" .")
    return cleaned or "localeforge"
