from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .errors import ModelProviderError
from .modes import ProcessedResult, process_status_fields
from .task_profile import TaskProfile


@dataclass(frozen=True)
class WindowSourceRow:
    row: int
    source: str


def build_window_user_text(
    previous: Sequence[Mapping[str, Any]],
    current: Sequence[WindowSourceRow],
    next_rows: Sequence[WindowSourceRow],
) -> str:
    payload = {
        "previous": [dict(item) for item in previous],
        "current": [{"row": item.row, "source": item.source} for item in current],
        "next": [{"row": item.row, "source": item.source} for item in next_rows],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def window_prompt_instructions(profile: TaskProfile) -> str:
    if profile.mode == "status-json":
        _require_status_json_fields(profile)
        fields = ", ".join(profile.output.fields)
        return (
            "LocaleForge window mode instructions:\n"
            "These instructions override any task prompt output-format instructions written for one row, one cell, or one object.\n"
            "The user message is a JSON object with previous, current, and next arrays.\n"
            "Return exactly one JSON array for the current rows and no markdown or prose.\n"
            "Return one object for each item in current, and do not return objects for previous or next.\n"
            "Each object must include row and exactly these fields: "
            f"{fields}.\n"
            "The row value must match a row from current."
        )
    return (
        "LocaleForge window mode instructions:\n"
        "These instructions override any task prompt output-format instructions written for one row, one cell, or one object.\n"
        "The user message is a JSON object with previous, current, and next arrays.\n"
        "Return exactly one JSON array for the current rows and no markdown or prose.\n"
        "Return one object for each item in current, and do not return objects for previous or next.\n"
        "Each object must include row and target, and no other output fields.\n"
        "The row value must match a row from current."
    )


def process_window_response(
    profile: TaskProfile,
    raw: str,
    current: Sequence[WindowSourceRow],
) -> dict[int, ProcessedResult]:
    text = str(raw).strip()
    try:
        payload = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except json.JSONDecodeError as exc:
        raise ModelProviderError(f"Model returned invalid window JSON: {_excerpt(text)}") from exc
    if not isinstance(payload, list):
        raise ModelProviderError("Model window response must be a JSON array.")

    expected_rows = [item.row for item in current]
    expected_set = set(expected_rows)
    if len(payload) != len(expected_rows):
        raise ModelProviderError(
            f"Model window response returned {len(payload)} items for {len(expected_rows)} current rows."
        )

    results: dict[int, ProcessedResult] = {}
    for item in payload:
        if not isinstance(item, dict):
            raise ModelProviderError("Each model window response item must be an object.")
        row = _parse_row(item.get("row"))
        if row not in expected_set:
            raise ModelProviderError(f"Model window response included unknown row {row}.")
        if row in results:
            raise ModelProviderError(f"Model window response included duplicate row {row}.")
        results[row] = _process_window_item(profile, item)

    missing = [row for row in expected_rows if row not in results]
    if missing:
        raise ModelProviderError("Model window response missing rows: " + ", ".join(str(row) for row in missing))
    return results


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ModelProviderError(f"Model window response included duplicate key `{key}`.")
        result[key] = value
    return result


def _parse_row(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelProviderError("Each model window response item must include an integer row.")
    return value


def _process_window_item(profile: TaskProfile, item: Mapping[str, Any]) -> ProcessedResult:
    if profile.mode == "transform":
        return _process_transform_item(item)
    if profile.mode == "status-json":
        return _process_status_json_item(profile, item)
    raise ModelProviderError(f"Unsupported task mode `{profile.mode}`.")


def _process_transform_item(item: Mapping[str, Any]) -> ProcessedResult:
    expected = {"row", "target"}
    keys = set(item)
    missing = sorted(expected - keys)
    unknown = sorted(keys - expected)
    if unknown:
        raise ModelProviderError("Model window transform item included unknown fields: " + ", ".join(unknown))
    if missing:
        raise ModelProviderError("Model window transform item missing fields: " + ", ".join(missing))
    value = item.get("target")
    if not isinstance(value, str):
        raise ModelProviderError("Model window transform item must include a non-empty string target.")
    target = value.strip()
    if not target:
        raise ModelProviderError("Model window transform item must include a non-empty string target.")
    return ProcessedResult(primary=target)


def _process_status_json_item(profile: TaskProfile, item: Mapping[str, Any]) -> ProcessedResult:
    _require_status_json_fields(profile)
    expected = set(profile.output.fields)
    actual = {key for key in item if key != "row"}
    missing = sorted(expected - actual)
    unknown = sorted(actual - expected)
    if missing or unknown:
        details: list[str] = []
        if missing:
            details.append(f"missing fields: {', '.join(missing)}")
        if unknown:
            details.append(f"unknown fields: {', '.join(unknown)}")
        raise ModelProviderError(
            "Model window status-json item did not match declared output.fields: " + "; ".join(details)
        )
    return process_status_fields({field: item.get(field, "") for field in profile.output.fields})


def _require_status_json_fields(profile: TaskProfile) -> None:
    if not profile.output.fields:
        raise ModelProviderError("Window request mode requires status-json tasks to declare output.fields.")


def _excerpt(value: str, limit: int = 160) -> str:
    value = value.replace("\n", "\\n")
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
