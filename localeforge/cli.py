from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .engine import RunOptions, run_task, validate_task
from .errors import ConfigError, LocaleForgeError, exit_code_for_error
from .providers import OllamaClient, OpenAICompatibleClient
from .report import RunReport
from .settings import (
    DEFAULT_BASE_URL,
    ProviderConfig,
    add_provider,
    get_provider,
    load_settings,
    save_settings,
    settings_to_public_dict,
)
from .task_profile import TaskProfile, load_task_profile


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="localeforge",
        description="Agent-first CLI for LLM batch processing over Excel and CSV files.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run a task against one file or a folder.")
    _add_task_run_args(run)
    run.add_argument("--dry-run", action="store_true", help="Validate without calling a model or writing outputs.")

    validate = subparsers.add_parser("validate", help="Validate a task/input run without model calls or writes.")
    _add_task_run_args(validate)

    doctor = subparsers.add_parser("doctor", help="Check global LocaleForge runtime health.")
    doctor.add_argument("--json", action="store_true", help="Emit machine-readable JSON.")
    doctor.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")

    provider = subparsers.add_parser("provider", help="Manage saved model providers.")
    provider_subparsers = provider.add_subparsers(dest="provider_command", required=True)

    provider_add = provider_subparsers.add_parser("add", help="Add or update a provider.")
    provider_add.add_argument("provider_id")
    provider_add.add_argument("--base-url", required=True)
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


def _handle_provider(args: argparse.Namespace) -> int:
    settings = load_settings()
    if args.provider_command == "add":
        provider = ProviderConfig(
            provider_id=args.provider_id,
            base_url=args.base_url,
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
        client = _create_client_for_effective_config(None, settings, argparse.Namespace(
            execution_mode=None,
            provider=None,
            model=None,
            base_url=None,
            timeout=args.timeout,
        ))
        models = client.ensure_available()
        checks.append({"name": "provider", "status": "success", "models": models})
    except LocaleForgeError as exc:
        payload["status"] = "error"
        checks.append({"name": "provider", "status": "error", "error": str(exc)})
    _emit(payload, json_output=args.json)
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
        report = run_task(profile, task_path, options, client)

    _write_report(report, args.report)
    _emit(report.to_dict(), json_output=args.json)
    if report.status == "success":
        return 0
    return 4 if report.status == "partial_failure" else 2


def _run_options(args: argparse.Namespace, profile: TaskProfile, settings: object | None) -> RunOptions:
    execution_mode = getattr(args, "execution_mode", None) or profile.model.execution_mode
    provider = getattr(args, "provider", None) or profile.model.provider
    model = getattr(args, "model", None) or profile.model.name
    if settings is not None:
        defaults = settings.defaults  # type: ignore[attr-defined]
        execution_mode = execution_mode or defaults.execution_mode
        provider = provider or defaults.provider_id
        model = model or defaults.model
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
    )


def _create_client_for_effective_config(
    profile: TaskProfile | None,
    settings: object,
    args: argparse.Namespace,
):
    defaults = settings.defaults  # type: ignore[attr-defined]
    execution_mode = getattr(args, "execution_mode", None) or (profile.model.execution_mode if profile else None) or defaults.execution_mode
    model = getattr(args, "model", None) or (profile.model.name if profile else None) or defaults.model
    base_url = getattr(args, "base_url", None)

    if execution_mode == "api":
        provider_id = getattr(args, "provider", None) or (profile.model.provider if profile else None) or defaults.provider_id
        provider = get_provider(settings, provider_id)  # type: ignore[arg-type]
        if provider is None:
            raise ConfigError("API execution requires a saved provider. Run `localeforge provider add` first.")
        return OpenAICompatibleClient(
            base_url=base_url or provider.base_url,
            api_key=provider.api_key,
            model=model or provider.default_model,
            timeout=getattr(args, "timeout", 120.0),
        )

    return OllamaClient(
        base_url=base_url or DEFAULT_BASE_URL,
        model=model,
        timeout=getattr(args, "timeout", 120.0),
    )


def _validate_provider_resolution(profile: TaskProfile, settings: object, args: argparse.Namespace) -> None:
    defaults = settings.defaults  # type: ignore[attr-defined]
    execution_mode = getattr(args, "execution_mode", None) or profile.model.execution_mode or defaults.execution_mode
    if execution_mode != "api":
        return
    provider_id = getattr(args, "provider", None) or profile.model.provider or defaults.provider_id
    provider = get_provider(settings, provider_id)  # type: ignore[arg-type]
    if provider is None:
        raise ConfigError("API execution requires a saved provider. Run `localeforge provider add` first.")


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


def _handle_error(error: LocaleForgeError, json_output: bool) -> int:
    if json_output:
        print(json.dumps({"status": "error", "errors": [str(error)]}, ensure_ascii=False, indent=2))
    else:
        print(f"error: {error}", file=sys.stderr)
    return exit_code_for_error(error)
