from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path


DEFAULT_SETTINGS_ENV = "LOCALEFORGE_SETTINGS_PATH"
DEFAULT_LOCAL_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_LOCAL_MODEL = "gemma4:e4b"
DEFAULT_LOCAL_CONCURRENCY = 1
DEFAULT_API_CONCURRENCY = 4
MIN_CONCURRENCY = 1
MAX_CONCURRENCY = 16


class ProviderMutationError(ValueError):
    """Raised when a provider cannot be saved safely."""


@dataclass
class ProviderConfig:
    provider_id: str
    name: str
    base_url: str
    api_key: str
    models: list[str] = field(default_factory=list)
    last_tested_at: str | None = None


@dataclass
class LocalDefaults:
    base_url: str = DEFAULT_LOCAL_BASE_URL
    model: str = DEFAULT_LOCAL_MODEL
    concurrency: int = DEFAULT_LOCAL_CONCURRENCY


@dataclass
class ApiDefaults:
    provider_id: str | None = None
    model: str = ""
    concurrency: int = DEFAULT_API_CONCURRENCY


@dataclass
class AppDefaults:
    execution_mode: str = "local"
    local: LocalDefaults = field(default_factory=LocalDefaults)
    api: ApiDefaults = field(default_factory=ApiDefaults)


@dataclass
class AppSettings:
    defaults: AppDefaults = field(default_factory=AppDefaults)
    providers: list[ProviderConfig] = field(default_factory=list)


def settings_path(path: Path | None = None) -> Path:
    if path is not None:
        return path.expanduser().resolve()

    env_path = os.environ.get(DEFAULT_SETTINGS_ENV)
    if env_path:
        return Path(env_path).expanduser().resolve()
    return (Path.home() / ".localeforge" / "settings.json").resolve()


def _normalize_concurrency(value: int, fallback: int) -> int:
    if not isinstance(value, int):
        return fallback
    return max(MIN_CONCURRENCY, min(MAX_CONCURRENCY, value))


def _coerce_int(value: object, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_models(models: list[str] | None) -> list[str]:
    if not models:
        return []
    normalized: list[str] = []
    for model in models:
        item = str(model).strip()
        if item and item not in normalized:
            normalized.append(item)
    return normalized


def _provider_from_dict(data: dict[str, object]) -> ProviderConfig:
    return ProviderConfig(
        provider_id=str(data.get("provider_id", "")).strip(),
        name=str(data.get("name", "")).strip(),
        base_url=str(data.get("base_url", "")).strip(),
        api_key=str(data.get("api_key", "")).strip(),
        models=_normalize_models(data.get("models") if isinstance(data.get("models"), list) else None),
        last_tested_at=str(data.get("last_tested_at")).strip() if data.get("last_tested_at") else None,
    )


def _defaults_from_dict(data: dict[str, object]) -> AppDefaults:
    local_raw = data.get("local") if isinstance(data.get("local"), dict) else {}
    api_raw = data.get("api") if isinstance(data.get("api"), dict) else {}
    assert isinstance(local_raw, dict)
    assert isinstance(api_raw, dict)
    execution_mode = str(data.get("execution_mode", "local")).strip() or "local"
    if execution_mode not in {"local", "api"}:
        execution_mode = "local"

    return AppDefaults(
        execution_mode=execution_mode,
        local=LocalDefaults(
            base_url=str(local_raw.get("base_url", DEFAULT_LOCAL_BASE_URL)).strip() or DEFAULT_LOCAL_BASE_URL,
            model=str(local_raw.get("model", DEFAULT_LOCAL_MODEL)).strip() or DEFAULT_LOCAL_MODEL,
            concurrency=_normalize_concurrency(
                _coerce_int(local_raw.get("concurrency", DEFAULT_LOCAL_CONCURRENCY), DEFAULT_LOCAL_CONCURRENCY),
                DEFAULT_LOCAL_CONCURRENCY,
            ),
        ),
        api=ApiDefaults(
            provider_id=str(api_raw.get("provider_id")).strip() if api_raw.get("provider_id") else None,
            model=str(api_raw.get("model", "")).strip(),
            concurrency=_normalize_concurrency(
                _coerce_int(api_raw.get("concurrency", DEFAULT_API_CONCURRENCY), DEFAULT_API_CONCURRENCY),
                DEFAULT_API_CONCURRENCY,
            ),
        ),
    )


def _settings_from_dict(data: dict[str, object]) -> AppSettings:
    defaults_raw = data.get("defaults") if isinstance(data.get("defaults"), dict) else {}
    providers_raw = data.get("providers") if isinstance(data.get("providers"), list) else []
    assert isinstance(defaults_raw, dict)

    providers: list[ProviderConfig] = []
    for item in providers_raw:
        if not isinstance(item, dict):
            continue
        provider = _provider_from_dict(item)
        if provider.provider_id and provider.name and provider.base_url:
            providers.append(provider)

    settings = AppSettings(
        defaults=_defaults_from_dict(defaults_raw),
        providers=providers,
    )
    if settings.defaults.api.provider_id and get_provider(settings, settings.defaults.api.provider_id) is None:
        settings.defaults.api.provider_id = None
        settings.defaults.api.model = ""
    return settings


def load_settings(path: Path | None = None) -> AppSettings:
    target = settings_path(path)
    if not target.exists():
        defaults = AppSettings()
        save_settings(defaults, target)
        return defaults

    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        defaults = AppSettings()
        save_settings(defaults, target)
        return defaults
    if not isinstance(payload, dict):
        defaults = AppSettings()
        save_settings(defaults, target)
        return defaults

    settings = _settings_from_dict(payload)
    save_settings(settings, target)
    return settings


def save_settings(settings: AppSettings, path: Path | None = None) -> Path:
    target = settings_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(settings), indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return target


def get_provider(settings: AppSettings, provider_id: str | None) -> ProviderConfig | None:
    if not provider_id:
        return None
    for provider in settings.providers:
        if provider.provider_id == provider_id:
            return provider
    return None


def now_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def upsert_provider(
    settings: AppSettings,
    candidate: ProviderConfig,
    tested_models: list[str] | None = None,
) -> ProviderConfig:
    candidate.provider_id = candidate.provider_id.strip()
    candidate.name = candidate.name.strip()
    candidate.base_url = candidate.base_url.strip().rstrip("/")
    candidate.api_key = candidate.api_key.strip()
    candidate.models = _normalize_models(candidate.models)

    if not candidate.provider_id or not candidate.name or not candidate.base_url or not candidate.api_key:
        raise ProviderMutationError("Provider id, name, base URL, and API key are required.")

    existing = get_provider(settings, candidate.provider_id)
    if existing is None and not tested_models:
        raise ProviderMutationError("New providers must pass testing before they can be saved.")

    connection_changed = (
        existing is not None
        and (existing.base_url != candidate.base_url or existing.api_key != candidate.api_key)
    )
    if connection_changed and not tested_models:
        raise ProviderMutationError("Provider connection changes require a fresh test before saving.")

    if tested_models is not None:
        models = _normalize_models(tested_models)
        if not models:
            raise ProviderMutationError("Provider test must return at least one model before saving.")
        candidate.models = models
        candidate.last_tested_at = now_timestamp()
    elif existing is not None:
        candidate.models = list(existing.models)
        candidate.last_tested_at = existing.last_tested_at

    if existing is None:
        settings.providers.append(candidate)
    else:
        existing.name = candidate.name
        existing.base_url = candidate.base_url
        existing.api_key = candidate.api_key
        existing.models = list(candidate.models)
        existing.last_tested_at = candidate.last_tested_at
        candidate = existing

    return candidate


def delete_provider(settings: AppSettings, provider_id: str) -> None:
    settings.providers = [provider for provider in settings.providers if provider.provider_id != provider_id]
    if settings.defaults.api.provider_id == provider_id:
        settings.defaults.api.provider_id = None
        settings.defaults.api.model = ""
