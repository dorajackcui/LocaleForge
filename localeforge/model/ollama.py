from __future__ import annotations

import json
import re
from typing import Optional

from ..config.tasks import STATUS_OK, TaskConfig
from ..prompts import render_prompt
from ..rules import normalize_text
from ..types import ClassificationResult

try:
    import requests
except ImportError:  # pragma: no cover - fallback for machines without requests
    requests = None
    import urllib.request


def parse_classification_response(raw: str, hit_status: str) -> Optional[ClassificationResult]:
    raw = raw.strip()
    candidates = [raw]
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        candidates.append(match.group(0))

    valid_statuses = {STATUS_OK, hit_status}
    for item in candidates:
        try:
            parsed = json.loads(item)
        except json.JSONDecodeError:
            continue
        status = str(parsed.get("status", "")).strip()
        if status in valid_statuses:
            spans = normalize_spans(parsed.get("spans"))
            return ClassificationResult(status=status, spans=spans)

    if hit_status in raw:
        return ClassificationResult(status=hit_status, spans=[])
    if STATUS_OK in raw:
        return ClassificationResult(status=STATUS_OK, spans=[])
    return None


def normalize_spans(spans_value: object) -> list[str]:
    if not isinstance(spans_value, list):
        return []
    normalized: list[str] = []
    for item in spans_value:
        text = normalize_text(item)
        if text and text not in normalized:
            normalized.append(text)
    return normalized


class OllamaClient:
    def __init__(
        self,
        api_url: str,
        model: str,
        timeout: float,
        prompt_template: str,
        task_config: TaskConfig,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.prompt_template = prompt_template
        self.task_config = task_config
        self.session = requests.Session() if requests is not None else None

    def ensure_available(self) -> None:
        tags_url = f"{self.api_url}/api/tags"
        try:
            payload = self._get_json(tags_url)
        except Exception as exc:  # pragma: no cover - depends on local service
            raise RuntimeError(
                f"Cannot reach local Ollama service at {tags_url}. "
                "Please make sure `ollama serve` is running."
            ) from exc

        models = {item.get("name") for item in payload.get("models", [])}
        if self.model not in models:
            raise RuntimeError(
                f"Model `{self.model}` was not found in the local Ollama service. "
                "Run `ollama list` to verify the installed models."
            )

    def classify(self, text: str) -> ClassificationResult:
        prompt = render_prompt(self.prompt_template, text, self.task_config)
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": 0,
            },
        }
        response = self._post_json(f"{self.api_url}/api/generate", payload)
        raw = response.get("response", "")
        result = parse_classification_response(raw, self.task_config.hit_status)
        if result is None:
            raise RuntimeError(f"Model returned an unparseable response: {raw!r}")
        return result

    def _get_json(self, url: str) -> dict:
        if self.session is not None:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        request = urllib.request.Request(url=url, method="GET")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, url: str, payload: dict) -> dict:
        if self.session is not None:
            response = self.session.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))
