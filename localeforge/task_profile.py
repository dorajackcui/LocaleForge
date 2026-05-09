from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import TaskProfileError


SUPPORTED_MODES = {"transform", "status-json"}


@dataclass(frozen=True)
class InputConfig:
    sheet: str | None = None
    column: str = "source"
    header_row: int = 1
    start_row: int = 2


@dataclass(frozen=True)
class OutputConfig:
    column: str = "target"
    create: bool = True
    overwrite: bool = True
    details_column: str | None = None
    columns: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelConfig:
    execution_mode: str | None = None
    provider: str | None = None
    name: str | None = None
    concurrency: int | None = None
    max_attempts: int | None = None


@dataclass(frozen=True)
class TaskProfile:
    id: str
    mode: str = "transform"
    description: str = ""
    input: InputConfig = field(default_factory=InputConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    prompt: str = ""


def load_task_profile(path: Path | str) -> TaskProfile:
    task_path = Path(path).expanduser().resolve()
    if not task_path.exists():
        raise TaskProfileError(f"Task file does not exist: {task_path}")

    text = task_path.read_text(encoding="utf-8")
    metadata, prompt = _split_front_matter(text, task_path)
    if not prompt.strip():
        raise TaskProfileError(f"Task file has an empty prompt body: {task_path}")

    task_id = str(metadata.get("id", "")).strip()
    if not task_id:
        raise TaskProfileError("Task front matter requires a non-empty `id`.")

    mode = str(metadata.get("mode", "transform")).strip() or "transform"
    if mode not in SUPPORTED_MODES:
        known = ", ".join(sorted(SUPPORTED_MODES))
        raise TaskProfileError(f"Unsupported task mode `{mode}`. Supported modes: {known}.")

    return TaskProfile(
        id=task_id,
        mode=mode,
        description=str(metadata.get("description", "")).strip(),
        input=_input_config(metadata.get("input")),
        output=_output_config(metadata.get("output")),
        model=_model_config(metadata.get("model")),
        prompt=prompt.strip(),
    )


def _split_front_matter(text: str, path: Path) -> tuple[dict[str, Any], str]:
    normalized = text.replace("\r\n", "\n")
    if not normalized.startswith("---\n"):
        raise TaskProfileError(f"Task file must start with YAML front matter: {path}")

    try:
        _, rest = normalized.split("---\n", maxsplit=1)
        raw_yaml, prompt = rest.split("\n---\n", maxsplit=1)
    except ValueError as exc:
        raise TaskProfileError(f"Task file has invalid front matter delimiters: {path}") from exc

    try:
        parsed = yaml.safe_load(raw_yaml) or {}
    except yaml.YAMLError as exc:
        raise TaskProfileError(f"Task front matter is invalid YAML: {path}") from exc
    if not isinstance(parsed, dict):
        raise TaskProfileError("Task front matter must be a mapping.")
    return parsed, prompt


def _mapping(value: object, field_name: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TaskProfileError(f"`{field_name}` must be a mapping.")
    return value


def _positive_int(value: object, fallback: int, field_name: str) -> int:
    if value is None:
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise TaskProfileError(f"`{field_name}` must be a positive integer.") from exc
    if parsed < 1:
        raise TaskProfileError(f"`{field_name}` must be a positive integer.")
    return parsed


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _input_config(value: object) -> InputConfig:
    data = _mapping(value, "input")
    return InputConfig(
        sheet=_optional_str(data.get("sheet")),
        column=str(data.get("column", "source")).strip() or "source",
        header_row=_positive_int(data.get("header_row"), 1, "input.header_row"),
        start_row=_positive_int(data.get("start_row"), 2, "input.start_row"),
    )


def _output_config(value: object) -> OutputConfig:
    data = _mapping(value, "output")
    return OutputConfig(
        column=str(data.get("column", "target")).strip() or "target",
        create=bool(data.get("create", True)),
        overwrite=bool(data.get("overwrite", True)),
        details_column=_optional_str(data.get("details_column")),
        columns=_string_mapping(data.get("columns"), "output.columns"),
    )


def _model_config(value: object) -> ModelConfig:
    if value is None:
        return ModelConfig()
    if isinstance(value, str):
        return ModelConfig(name=_optional_str(value))
    data = _mapping(value, "model")
    concurrency = data.get("concurrency")
    max_attempts = data.get("max_attempts")
    return ModelConfig(
        execution_mode=_optional_str(data.get("execution_mode")),
        provider=_optional_str(data.get("provider")),
        name=_optional_str(data.get("name")),
        concurrency=_positive_int(concurrency, 1, "model.concurrency") if concurrency is not None else None,
        max_attempts=_positive_int(max_attempts, 1, "model.max_attempts") if max_attempts is not None else None,
    )


def _string_mapping(value: object, field_name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TaskProfileError(f"`{field_name}` must be a mapping.")
    result: dict[str, str] = {}
    for key, item in value.items():
        field = str(key).strip()
        column = str(item).strip()
        if field and column:
            result[field] = column
    return result
