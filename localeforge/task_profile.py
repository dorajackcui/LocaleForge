from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .errors import TaskProfileError


SUPPORTED_MODES = {"transform", "status-json"}
SUPPORTED_REQUEST_MODES = {"concurrent", "window"}


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
    fields: tuple[str, ...] = ()
    columns: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ModelConfig:
    execution_mode: str | None = None
    provider: str | None = None
    name: str | None = None


@dataclass(frozen=True)
class RequestConfig:
    mode: str | None = None
    window_size: int | None = None


@dataclass(frozen=True)
class TaskProfile:
    id: str
    mode: str = "transform"
    description: str = ""
    input: InputConfig = field(default_factory=InputConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    request: RequestConfig = field(default_factory=RequestConfig)
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
        request=_request_config(metadata.get("request")),
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
    fields = _string_sequence(data.get("fields"), "output.fields")
    columns = _string_mapping(data.get("columns"), "output.columns")
    if fields:
        unknown_mappings = sorted(set(columns) - set(fields))
        if unknown_mappings:
            raise TaskProfileError(
                "`output.columns` contains fields not listed in `output.fields`: "
                + ", ".join(unknown_mappings)
            )
    return OutputConfig(
        column=str(data.get("column", "target")).strip() or "target",
        create=_bool_config(data.get("create"), True, "output.create"),
        overwrite=_bool_config(data.get("overwrite"), True, "output.overwrite"),
        details_column=_optional_str(data.get("details_column")),
        fields=fields,
        columns=columns,
    )


def _model_config(value: object) -> ModelConfig:
    if value is None:
        return ModelConfig()
    if isinstance(value, str):
        return ModelConfig(name=_optional_str(value))
    data = _mapping(value, "model")
    runtime_fields = sorted(field for field in ("concurrency", "max_attempts") if field in data)
    if runtime_fields:
        fields = ", ".join(f"model.{field}" for field in runtime_fields)
        raise TaskProfileError(f"{fields} are global runtime settings. Use .env or CLI flags instead.")
    return ModelConfig(
        execution_mode=_optional_str(data.get("execution_mode")),
        provider=_optional_str(data.get("provider")),
        name=_optional_str(data.get("name")),
    )


def _request_config(value: object) -> RequestConfig:
    data = _mapping(value, "request")
    mode = _optional_str(data.get("mode"))
    if mode is not None and mode not in SUPPORTED_REQUEST_MODES:
        known = ", ".join(sorted(SUPPORTED_REQUEST_MODES))
        raise TaskProfileError(f"Unsupported request mode `{mode}`. Supported modes: {known}.")
    window_size = _optional_positive_int(data.get("window_size"), "request.window_size")
    if window_size is not None and mode != "window":
        raise TaskProfileError("`request.window_size` requires `request.mode: window`.")
    return RequestConfig(
        mode=mode,
        window_size=window_size,
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


def _string_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise TaskProfileError(f"`{field_name}` must be a list.")
    result: list[str] = []
    for item in value:
        field = str(item).strip()
        if field and field not in result:
            result.append(field)
    return tuple(result)


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, 1, field_name)


def _bool_config(value: object, fallback: bool, field_name: str) -> bool:
    if value is None:
        return fallback
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "on", "1"}:
            return True
        if normalized in {"false", "no", "off", "0"}:
            return False
    raise TaskProfileError(f"`{field_name}` must be a boolean.")
