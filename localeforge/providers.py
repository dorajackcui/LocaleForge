from __future__ import annotations

import json
from typing import Any, Protocol

import requests

from .errors import ModelProviderError


class ModelClient(Protocol):
    def ensure_available(self) -> list[str]:
        raise NotImplementedError

    def generate(self, system_prompt: str, user_text: str) -> str:
        raise NotImplementedError


class StaticModelClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.call_count = 0

    def ensure_available(self) -> list[str]:
        return ["static"]

    def generate(self, system_prompt: str, user_text: str) -> str:
        self.call_count += 1
        try:
            return self.responses[user_text]
        except KeyError as exc:
            raise ModelProviderError(f"No static response configured for input: {user_text}") from exc


class OpenAICompatibleClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.model = model
        self.timeout = timeout
        self.session = requests.Session()

    def ensure_available(self) -> list[str]:
        try:
            response = self.session.get(f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ModelProviderError(f"Cannot reach provider at {self.base_url}/models.") from exc
        models = [
            str(item.get("id", "")).strip()
            for item in payload.get("data", [])
            if isinstance(item, dict) and str(item.get("id", "")).strip()
        ]
        if self.model and models and self.model not in models:
            raise ModelProviderError(f"Model `{self.model}` was not returned by provider `{self.base_url}`.")
        return models

    def generate(self, system_prompt: str, user_text: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            "temperature": 0,
        }
        try:
            response = self.session.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise ModelProviderError(f"Provider request failed for model `{self.model}`.") from exc
        return _extract_chat_content(data)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.session = requests.Session()

    def ensure_available(self) -> list[str]:
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            raise ModelProviderError(f"Cannot reach local Ollama service at {self.base_url}/api/tags.") from exc
        models = [str(item.get("name", "")).strip() for item in payload.get("models", []) if isinstance(item, dict)]
        if models and self.model not in models:
            raise ModelProviderError(f"Model `{self.model}` was not found in local Ollama.")
        return [model for model in models if model]

    def generate(self, system_prompt: str, user_text: str) -> str:
        prompt = f"{system_prompt.strip()}\n\nInput:\n{user_text}"
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0},
        }
        try:
            response = self.session.post(f"{self.base_url}/api/generate", json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            raise ModelProviderError(f"Ollama request failed for model `{self.model}`.") from exc
        return str(data.get("response", ""))


def _extract_chat_content(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ModelProviderError("Provider response did not include choices.")
    first = choices[0]
    if not isinstance(first, dict):
        raise ModelProviderError("Provider choice payload is invalid.")
    message = first.get("message")
    if not isinstance(message, dict):
        raise ModelProviderError("Provider response did not include a message.")
    content = message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    return json.dumps(content, ensure_ascii=False)
