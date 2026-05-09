from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .engine import RunOptions, run_task, validate_task
from .errors import ConfigError, LocaleForgeError, exit_code_for_error
from .progress import ProgressReporter
from .providers import OllamaClient, OpenAICompatibleClient
from .report import RunReport
from .settings import (
    DEFAULT_BASE_URL,
    AppSettings,
    ProviderConfig,
    add_provider,
    get_provider,
    load_local_env,
    load_settings,
    resolve_base_url,
    resolve_api_key,
    save_settings,
    settings_to_public_dict,
)
from .task_profile import TaskProfile, load_task_profile


ENV_PROVIDER_ID = "env"
ENV_BASE_URL = "OPENAI_BASE_URL"
ENV_API_KEY = "OPENAI_API_KEY"
ENV_MODEL = "OPENAI_MODEL"
ENV_CONCURRENCY = "LOCALEFORGE_CONCURRENCY"
ENV_MAX_ATTEMPTS = "LOCALEFORGE_MAX_ATTEMPTS"


@dataclass(frozen=True)
class EffectiveModelConfig:
    execution_mode: str
    provider: ProviderConfig | None
    provider_id: str | None
    base_url: str
    api_key: str
    model: str


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="localeforge",
        description="Agent-first CLI for LLM batch processing over Excel and CSV files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run a task against one file or a folder.")
    _add_task_run_args(run)
    run.add_argument("--dry-run", action="store_true", help="Validate without calling a model or writing outputs.")
    run.add_argument("--progress", choices=["auto", "none", "text", "jsonl"], default="auto", help="Emit run progress to stderr.")
    run.add_argument("--tips", help="Temporary session note appended to the task system prompt for this run.")

    validate = subparsers.add_parser("validate", help="Validate a task/input run without model calls or writes.")
    _add_task_run_args(validate)

    doctor = subparsers.add_parser("doctor", help="Check global LocaleForge runtime health.")
    doctor.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    doctor.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")

    provider = subparsers.add_parser("provider", help="Manage saved model providers.")
    provider_subparsers = provider.add_subparsers(dest="provider_command", required=True)

    provider_add = provider_subparsers.add_parser("add", help="Add or update a provider.")
    provider_add.add_argument("provider_id")
    provider_add.add_argument("--base-url")
    provider_add.add_argument("--base-url-env")
    provider_add.add_argument("--api-key")
    provider_add.add_argument("--api-key-env")
    provider_add.add_argument("--default-model", required=True)
    provider_add.add_argument("--set-default", action="store_true")
    provider_add.add_argument("--json", action="store_true")

    provider_list = provider_subparsers.add_parser("list", help="List saved providers.")
    provider_list.add_argument("--json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "provider":
            return _handle_provider(args)
        if args.command == "doctor":
            return _handle_doctor(args)
        if args.command == "validate":
            return _handle_validate(args)
        if args.command == "run":
            return _handle_run(args)
    except LocaleForgeError as exc:
        return _handle_error(exc, json_output=bool(getattr(args, "json", False)))
    return 1


def _add_task_run_args(parser: argparse.ArgumentParser, include_model: bool = True) -> None:
    parser.add_argument("--task", required=True, help="Path to a Markdown task file.")
    parser.add_argument("--input", required=True, help="Input file or directory.")
    parser.add_argument("--output", help="Single-file output path.")
    parser.add_argument("--output-dir", help="Directory output root for folder input.")
    parser.add_argument("--input-col", help="Override task input column.")
    parser.add_argument("--output-col", help="Override task output column.")
    parser.add_argument("--sheet", help="Override task Excel worksheet.")
    parser.add_argument("--report", help="Write a JSON report to this path.")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    if include_model:
        parser.add_argument("--execution-mode", choices=["local", "api"])
        parser.add_argument("--provider")
        parser.add_argument("--model")
        parser.add_argument("--base-url", help="Override provider/local base URL.")
        parser.add_argument("--timeout", type=float, default=120.0)
        parser.add_argument("--concurrency", type=_positive_int_arg, help="Maximum concurrent model requests.")
        parser.add_argument("--max-attempts", type=_positive_int_arg, help="Maximum attempts per unique input, including the first try.")


def _handle_provider(args: argparse.Namespace) -> int:
    settings = load_settings()
    if args.provider_command == "add":
        provider = ProviderConfig(
            provider_id=args.provider_id,
            base_url=args.base_url or "",
            base_url_env=args.base_url_env,
            api_key=args.api_key or "",
            api_key_env=args.api_key_env,
            default_model=args.default_model,
            models=[args.default_model],
        )
        add_provider(settings, provider, set_default=args.set_default)
        save_settings(settings)
        payload = settings_to_public_dict(settings)
        _emit(payload, json_output=args.json)
        return 0

    if args.provider_command == "list":
        payload = settings_to_public_dict(settings)
        _emit(payload, json_output=args.json)
        return 0
    return 1


def _handle_doctor(args: argparse.Namespace) -> int:
    settings = load_settings()
    payload: dict[str, object] = {
        "status": "success",
        "settings": settings_to_public_dict(settings),
        "checks": [],
    }
    checks = payload["checks"]
    assert isinstance(checks, list)

    try:
        effective = _resolve_effective_model_config(None, settings, args, require_model=False)
        payload["effective"] = _effective_config_to_public_dict(effective)
        client = _client_from_effective_config(effective, args)
        models = client.ensure_available()
        checks.append({"name": "provider", "status": "success", "models": models})
    except LocaleForgeError as exc:
        payload["status"] = "error"
        checks.append({"name": "provider", "status": "error", "error": str(exc)})
    _emit_doctor(payload, json_output=args.json)
    return 0 if payload["status"] == "success" else 3


def _handle_validate(args: argparse.Namespace) -> int:
    task_path = Path(args.task).expanduser().resolve()
    profile = load_task_profile(task_path)
    settings = load_settings()
    _validate_provider_resolution(profile, settings, args)
    report = validate_task(profile, task_path, _run_options(args, profile, settings))
    _write_report(report, args.report)
    _emit(report.to_dict(), json_output=args.json)
    if report.status == "success":
        return 0
    return 4 if report.status == "partial_failure" else 2


def _handle_run(args: argparse.Namespace) -> int:
    task_path = Path(args.task).expanduser().resolve()
    profile = load_task_profile(task_path)
    settings = load_settings()
    options = _run_options(args, profile, settings)
    if args.dry_run:
        _validate_provider_resolution(profile, settings, args)
        report = validate_task(profile, task_path, options)
    else:
        client = _create_client_for_effective_config(profile, settings, args)
        client.ensure_available()
        report = run_task(profile, task_path, options, client, progress=_progress_reporter(args))

    _write_report(report, args.report)
    _emit(report.to_dict(), json_output=args.json)
    if report.status == "success":
        return 0
    return 4 if report.status == "partial_failure" else 2


def _run_options(args: argparse.Namespace, profile: TaskProfile, settings: object | None) -> RunOptions:
    concurrency = _resolve_concurrency(args, settings)
    max_attempts = _resolve_max_attempts(args, settings)
    if settings is not None:
        effective = _resolve_effective_model_config(profile, settings, args, require_model=False)  # type: ignore[arg-type]
        execution_mode = effective.execution_mode
        provider = effective.provider_id
        model = effective.model
    else:
        execution_mode = getattr(args, "execution_mode", None) or profile.model.execution_mode or "local"
        provider = getattr(args, "provider", None) or profile.model.provider
        model = getattr(args, "model", None) or profile.model.name or ""
    return RunOptions(
        input_path=Path(args.input).expanduser().resolve(),
        output_dir=Path(args.output_dir).expanduser().resolve() if args.output_dir else None,
        output_path=Path(args.output).expanduser().resolve() if args.output else None,
        input_col=args.input_col,
        output_col=args.output_col,
        sheet=args.sheet,
        execution_mode=execution_mode or "local",
        provider=provider,
        model=model or "",
        concurrency=concurrency,
        max_attempts=max_attempts,
        tips=getattr(args, "tips", None),
    )


def _resolve_concurrency(args: argparse.Namespace, settings: object | None) -> int:
    explicit = getattr(args, "concurrency", None)
    if explicit is not None:
        return explicit
    env_value = _positive_int_env(ENV_CONCURRENCY)
    if env_value is not None:
        return env_value
    if settings is not None:
        return settings.defaults.concurrency  # type: ignore[attr-defined]
    return 1


def _resolve_max_attempts(args: argparse.Namespace, settings: object | None) -> int:
    explicit = getattr(args, "max_attempts", None)
    if explicit is not None:
        return explicit
    env_value = _positive_int_env(ENV_MAX_ATTEMPTS)
    if env_value is not None:
        return env_value
    if settings is not None:
        return settings.defaults.max_attempts  # type: ignore[attr-defined]
    return 2


def _positive_int_env(name: str) -> int | None:
    load_local_env()
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a positive integer.") from exc
    if parsed < 1:
        raise ConfigError(f"{name} must be a positive integer.")
    return parsed


def _progress_reporter(args: argparse.Namespace) -> ProgressReporter:
    mode = getattr(args, "progress", "none")
    if mode == "auto":
        mode = "none" if getattr(args, "json", False) else "text"
    return ProgressReporter(mode=mode)


def _positive_int_arg(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _create_client_for_effective_config(
    profile: TaskProfile | None,
    settings: object,
    args: argparse.Namespace,
    require_model: bool = True,
):
    effective = _resolve_effective_model_config(profile, settings, args, require_model=require_model)  # type: ignore[arg-type]
    return _client_from_effective_config(effective, args)


def _client_from_effective_config(effective: EffectiveModelConfig, args: argparse.Namespace):
    if effective.execution_mode == "api":
        return OpenAICompatibleClient(
            base_url=effective.base_url,
            api_key=effective.api_key,
            model=effective.model,
            timeout=getattr(args, "timeout", 120.0),
        )

    return OllamaClient(
        base_url=effective.base_url,
        model=effective.model,
        timeout=getattr(args, "timeout", 120.0),
    )


def _validate_provider_resolution(profile: TaskProfile, settings: object, args: argparse.Namespace) -> None:
    _resolve_effective_model_config(profile, settings, args, require_model=True)  # type: ignore[arg-type]


def _resolve_effective_model_config(
    profile: TaskProfile | None,
    settings: AppSettings,
    args: argparse.Namespace,
    require_model: bool,
) -> EffectiveModelConfig:
    defaults = settings.defaults
    env_provider = _provider_from_env()
    explicit_execution_mode = getattr(args, "execution_mode", None) or (profile.model.execution_mode if profile else None)
    explicit_provider_id = getattr(args, "provider", None) or (profile.model.provider if profile else None)
    explicit_model = getattr(args, "model", None) or (profile.model.name if profile else None)

    execution_mode = explicit_execution_mode
    if execution_mode is None:
        if explicit_provider_id or defaults.execution_mode == "api" or defaults.provider_id:
            execution_mode = "api"
        elif env_provider is not None:
            execution_mode = "api"
        else:
            execution_mode = defaults.execution_mode or "local"

    if execution_mode == "api":
        provider_id = explicit_provider_id or defaults.provider_id or (env_provider.provider_id if env_provider else None)
        provider = get_provider(settings, provider_id)
        if provider is None and env_provider is not None and provider_id in {None, env_provider.provider_id}:
            provider = env_provider
        if provider is None:
            raise ConfigError("API execution requires a saved provider or OPENAI_BASE_URL/OPENAI_API_KEY in .env.")

        base_url = getattr(args, "base_url", None) or resolve_base_url(provider)
        if not base_url:
            raise ConfigError(f"Provider `{provider.provider_id}` requires a base URL. Set --base-url-env, --base-url, or OPENAI_BASE_URL.")
        api_key = resolve_api_key(provider)
        if not api_key:
            raise ConfigError(f"Provider `{provider.provider_id}` requires an API key. Set --api-key-env, --api-key, or OPENAI_API_KEY.")

        model = explicit_model or (defaults.model if defaults.execution_mode == "api" else "") or provider.default_model
        if require_model and not model:
            raise ConfigError("API execution requires a model. Set --model, task model.name, provider default model, or OPENAI_MODEL.")
        return EffectiveModelConfig(
            execution_mode="api",
            provider=provider,
            provider_id=provider.provider_id,
            base_url=base_url,
            api_key=api_key,
            model=model,
        )

    model = explicit_model or defaults.model or "gemma4:e4b"
    return EffectiveModelConfig(
        execution_mode="local",
        provider=None,
        provider_id=None,
        base_url=getattr(args, "base_url", None) or DEFAULT_BASE_URL,
        api_key="",
        model=model,
    )


def _provider_from_env() -> ProviderConfig | None:
    load_local_env()
    base_url = os.environ.get(ENV_BASE_URL, "").strip()
    api_key = os.environ.get(ENV_API_KEY, "").strip()
    model = os.environ.get(ENV_MODEL, "").strip()
    if not (base_url or api_key):
        return None
    return ProviderConfig(
        provider_id=ENV_PROVIDER_ID,
        base_url="",
        base_url_env=ENV_BASE_URL,
        api_key="",
        api_key_env=ENV_API_KEY,
        default_model=model,
        models=[model] if model else [],
    )


def _effective_config_to_public_dict(config: EffectiveModelConfig) -> dict[str, str | None]:
    return {
        "execution_mode": config.execution_mode,
        "provider_id": config.provider_id,
        "base_url": config.base_url,
        "model": config.model,
    }


def _write_report(report: RunReport, report_path: str | None) -> None:
    if not report_path:
        return
    path = Path(report_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report.to_json() + "\n", encoding="utf-8")


def _emit(payload: object, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if isinstance(payload, dict) and "status" in payload:
        print(f"status: {payload['status']}")
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


def _emit_doctor(payload: dict[str, object], json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print("LocaleForge doctor")
    print(f"status: {payload.get('status', 'unknown')}")

    effective = payload.get("effective")
    if isinstance(effective, dict):
        print(f"execution_mode: {effective.get('execution_mode', 'unknown')}")
        provider_id = effective.get("provider_id")
        if provider_id:
            print(f"provider: {provider_id}")
        print(f"model: {effective.get('model') or '<not set>'}")

    checks = payload.get("checks")
    if isinstance(checks, list):
        for check in checks:
            if not isinstance(check, dict):
                continue
            name = check.get("name", "check")
            status = check.get("status", "unknown")
            if status == "success":
                models = check.get("models")
                if isinstance(models, list):
                    print(f"{name}: ok ({len(models)} models)")
                else:
                    print(f"{name}: ok")
            else:
                print(f"{name}: error - {check.get('error', 'unknown error')}")


def _handle_error(error: LocaleForgeError, json_output: bool) -> int:
    if json_output:
        print(json.dumps({"status": "error", "errors": [str(error)]}, ensure_ascii=False, indent=2))
    else:
        print(f"error: {error}", file=sys.stderr)
    return exit_code_for_error(error)
