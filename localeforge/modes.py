from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from .errors import ModelProviderError


@dataclass(frozen=True)
class ProcessedResult:
    primary: str
    details: str = ""
    fields: dict[str, str] = field(default_factory=dict)


def process_model_response(mode: str, raw: str) -> ProcessedResult:
    if mode == "transform":
        return _process_transform(raw)
    if mode == "status-json":
        return _process_status_json(raw)
    raise ModelProviderError(f"Unsupported task mode `{mode}`.")


def _process_transform(raw: str) -> ProcessedResult:
    text = str(raw).strip()
    if not text:
        raise ModelProviderError("Model returned an empty response.")
    return ProcessedResult(primary=text)


def _process_status_json(raw: str) -> ProcessedResult:
    text = str(raw).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelProviderError(f"Model returned invalid JSON: {_excerpt(text)}") from exc
    if not isinstance(payload, dict):
        raise ModelProviderError("Model JSON response must be an object.")

    fields = {
        str(key).strip(): _stringify_json_value(value)
        for key, value in payload.items()
        if str(key).strip()
    }
    if not fields:
        raise ModelProviderError("Model JSON response must include at least one field.")

    primary = fields.get("status", "") or next((value for value in fields.values() if value), "")
    return ProcessedResult(primary=primary, details=fields.get("spans", ""), fields=fields)


def _stringify_json_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        if all(not isinstance(item, (dict, list)) for item in value):
            return " | ".join(str(item).strip() for item in value if str(item).strip())
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value).strip()


def _excerpt(value: str, limit: int = 160) -> str:
    value = value.replace("\n", "\\n")
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
