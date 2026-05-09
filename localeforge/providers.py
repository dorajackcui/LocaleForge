from __future__ import annotations

import json
import threading
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
        self._local = threading.local()

    def ensure_available(self) -> list[str]:
        try:
            response = self._session().get(f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout)
            response.raise_for_status()
            payload = response.json()
        except requests.HTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            if status_code in {404, 405, 501}:
                return []
            raise ModelProviderError(f"Cannot reach provider at {self.base_url}/models.") from exc
        except Exception as exc:
            raise ModelProviderError(f"Cannot reach provider at {self.base_url}/models.") from exc
        models = [
            str(item.get("id", "")).strip()
            for item in payload.get("data", [])
            if isinstance(item, dict) and str(item.get("id", "")).strip()
        ]
        return models

    def generate(self, system_prompt: str, user_text: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        }
        try:
            response = self._session().post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=self._headers(),
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            detail = _provider_error_detail(exc)
            message = f"Provider request failed for model `{self.model}`."
            if detail:
                message = f"{message} {detail}"
            raise ModelProviderError(message) from exc
        return _extract_chat_content(data)

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            self._local.session = session
        return session

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }


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


def _provider_error_detail(exc: Exception) -> str:
    response = getattr(exc, "response", None)
    if response is None:
        return ""

    parts: list[str] = []
    status_code = getattr(response, "status_code", None)
    if status_code:
        parts.append(f"HTTP {status_code}.")

    body = _provider_error_body(response)
    if body:
        parts.append(body)

    return " ".join(parts)


def _provider_error_body(response: Any) -> str:
    try:
        payload = response.json()
    except Exception:
        text = str(getattr(response, "text", "")).strip()
        return text[:500]

    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message", "")).strip()
            if message:
                return message[:500]
        message = str(payload.get("message", "")).strip()
        if message:
            return message[:500]
    return json.dumps(payload, ensure_ascii=False)[:500]
