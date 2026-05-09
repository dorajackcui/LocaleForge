from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .errors import ConfigError


SETTINGS_ENV = "LOCALEFORGE_SETTINGS_PATH"
DEFAULT_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_LOCAL_MODEL = "gemma4:e4b"


@dataclass
class ProviderConfig:
    provider_id: str
    base_url: str
    api_key: str = ""
    api_key_env: str | None = None
    default_model: str = ""
    models: list[str] = field(default_factory=list)


@dataclass
class SettingsDefaults:
    execution_mode: str = "local"
    provider_id: str | None = None
    model: str = DEFAULT_LOCAL_MODEL
    concurrency: int = 1


@dataclass
class AppSettings:
    defaults: SettingsDefaults = field(default_factory=SettingsDefaults)
    providers: list[ProviderConfig] = field(default_factory=list)


def settings_path(path: Path | str | None = None) -> Path:
    if path is not None:
        return Path(path).expanduser().resolve()
    env_path = os.environ.get(SETTINGS_ENV)
    if env_path:
        return Path(env_path).expanduser().resolve()
    return (Path.home() / ".localeforge" / "settings.json").resolve()


def load_settings(path: Path | str | None = None) -> AppSettings:
    target = settings_path(path)
    if not target.exists():
        return AppSettings()

    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Settings file is not valid JSON: {target}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"Settings file must contain a JSON object: {target}")

    defaults_raw = raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {}
    assert isinstance(defaults_raw, dict)
    providers_raw = raw.get("providers") if isinstance(raw.get("providers"), list) else []
    defaults = SettingsDefaults(
        execution_mode=str(defaults_raw.get("execution_mode", "local")).strip() or "local",
        provider_id=_optional_str(defaults_raw.get("provider_id")),
        model=str(defaults_raw.get("model", DEFAULT_LOCAL_MODEL)).strip() or DEFAULT_LOCAL_MODEL,
        concurrency=_positive_int(defaults_raw.get("concurrency"), 1),
    )
    providers = [_provider_from_dict(item) for item in providers_raw if isinstance(item, dict)]
    return AppSettings(defaults=defaults, providers=providers)


def save_settings(settings: AppSettings, path: Path | str | None = None) -> Path:
    target = settings_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def get_provider(settings: AppSettings, provider_id: str | None) -> ProviderConfig | None:
    if not provider_id:
        return None
    for provider in settings.providers:
        if provider.provider_id == provider_id:
            return provider
    return None


def add_provider(settings: AppSettings, provider: ProviderConfig, set_default: bool = False) -> ProviderConfig:
    provider.provider_id = provider.provider_id.strip()
    provider.base_url = provider.base_url.strip().rstrip("/")
    provider.default_model = provider.default_model.strip()
    provider.api_key_env = _optional_str(provider.api_key_env)
    provider.api_key = resolve_api_key(provider)
    provider.models = _unique([*provider.models, provider.default_model])

    if not provider.provider_id:
        raise ConfigError("Provider id is required.")
    if not provider.base_url:
        raise ConfigError("Provider base URL is required.")
    if not provider.default_model:
        raise ConfigError("Provider default model is required.")
    if not provider.api_key:
        raise ConfigError("Provider API key is required. Use --api-key-env or --api-key.")

    existing = get_provider(settings, provider.provider_id)
    if existing is None:
        settings.providers.append(provider)
        saved = provider
    else:
        existing.base_url = provider.base_url
        existing.api_key = provider.api_key
        existing.api_key_env = provider.api_key_env
        existing.default_model = provider.default_model
        existing.models = list(provider.models)
        saved = existing

    if set_default:
        settings.defaults.execution_mode = "api"
        settings.defaults.provider_id = saved.provider_id
        settings.defaults.model = saved.default_model
    return saved


def resolve_api_key(provider: ProviderConfig) -> str:
    if provider.api_key:
        return provider.api_key.strip()
    if provider.api_key_env:
        return os.environ.get(provider.api_key_env, "").strip()
    return ""


def settings_to_public_dict(settings: AppSettings) -> dict[str, Any]:
    payload = asdict(settings)
    for provider in payload.get("providers", []):
        if provider.get("api_key"):
            provider["api_key"] = "<redacted>"
    return payload


def _provider_from_dict(data: dict[str, Any]) -> ProviderConfig:
    return ProviderConfig(
        provider_id=str(data.get("provider_id", "")).strip(),
        base_url=str(data.get("base_url", "")).strip(),
        api_key=str(data.get("api_key", "")).strip(),
        api_key_env=_optional_str(data.get("api_key_env")),
        default_model=str(data.get("default_model", "")).strip(),
        models=_unique(data.get("models") if isinstance(data.get("models"), list) else []),
    )


def _positive_int(value: object, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return max(1, parsed)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _unique(values: list[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if item and item not in result:
            result.append(item)
    return result
