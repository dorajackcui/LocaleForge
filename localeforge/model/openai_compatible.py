from __future__ import annotations

import json
from typing import Any

from ..config.tasks import TaskConfig
from ..prompts import render_chat_messages
from .ollama import parse_classification_response

try:
    import requests
except ImportError:  # pragma: no cover - fallback for machines without requests
    requests = None
    import urllib.request


class OpenAICompatibleClient:
    def __init__(
        self,
        api_url: str,
        api_key: str,
        model: str,
        timeout: float,
        prompt_template: str,
        task_config: TaskConfig,
    ) -> None:
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model
        self.timeout = timeout
        self.prompt_template = prompt_template
        self.task_config = task_config
        self.session = requests.Session() if requests is not None else None

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def ensure_available(self) -> list[str]:
        try:
            payload = self._get_json(f"{self.api_url}/models", self._headers())
        except Exception as exc:  # pragma: no cover - depends on remote service
            raise RuntimeError(f"Cannot reach OpenAI-compatible provider at {self.api_url}/models.") from exc

        models = [
            str(item.get("id", "")).strip()
            for item in payload.get("data", [])
            if isinstance(item, dict) and str(item.get("id", "")).strip()
        ]
        if not models:
            raise RuntimeError("Provider test succeeded but did not return any models.")
        return models

    def classify(self, text: str):
        payload = {
            "model": self.model,
            "messages": render_chat_messages(self.prompt_template, text, self.task_config),
            "temperature": 0,
        }
        response = self._post_json(f"{self.api_url}/chat/completions", payload, self._headers())
        raw = self._extract_content(response)
        result = parse_classification_response(raw, self.task_config.hit_status)
        if result is None:
            raise RuntimeError(f"Model returned an unparseable response: {raw!r}")
        return result

    def _extract_content(self, payload: dict[str, Any]) -> str:
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("Provider response did not include any choices.")

        first = choices[0]
        if not isinstance(first, dict):
            raise RuntimeError("Provider choice payload is invalid.")

        message = first.get("message")
        if not isinstance(message, dict):
            raise RuntimeError("Provider response did not include a message payload.")

        content = message.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
            return "\n".join(part for part in parts if part)
        return str(content)

    def _get_json(self, url: str, headers: dict[str, str]) -> dict:
        if self.session is not None:
            response = self.session.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        request = urllib.request.Request(url=url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, url: str, payload: dict, headers: dict[str, str]) -> dict:
        if self.session is not None:
            response = self.session.post(url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.json()

        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url=url,
            data=body,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return json.loads(response.read().decode("utf-8"))
