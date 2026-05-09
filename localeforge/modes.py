from __future__ import annotations

import json
from dataclasses import dataclass

from .errors import ModelProviderError


@dataclass(frozen=True)
class ProcessedResult:
    primary: str
    details: str = ""


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

    status = str(payload.get("status", "")).strip()
    if not status:
        raise ModelProviderError("Model JSON response requires a non-empty `status`.")

    spans_value = payload.get("spans", [])
    if spans_value is None:
        spans: list[str] = []
    elif isinstance(spans_value, list):
        spans = [str(item).strip() for item in spans_value if str(item).strip()]
    else:
        raise ModelProviderError("Model JSON response field `spans` must be a list.")
    return ProcessedResult(primary=status, details=" | ".join(spans))


def _excerpt(value: str, limit: int = 160) -> str:
    value = value.replace("\n", "\\n")
    if len(value) <= limit:
        return value
    return value[: limit - 3] + "..."
