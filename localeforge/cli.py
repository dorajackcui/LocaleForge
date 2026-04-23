from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config.settings import AppSettings, get_provider, load_settings
from .config.tasks import DEFAULT_TASK_ID, STATUS_EMPTY, STATUS_OK, TASK_CONFIGS, TaskConfig, get_task_config
from .prompts import default_prompt_path
from .runtime import TaskRunRequest, run_task
from .types import ProgressCallback
from .workbook import default_input_path, default_output_path


def build_cli_progress_callback(task_config: TaskConfig) -> ProgressCallback:
    def cli_progress(offset: int, total_rows: int, row_idx: int, stats: dict[str, int]) -> None:
        if offset % 100 != 0 and offset != total_rows:
            return
        print(
            f"[{offset}/{total_rows}] row={row_idx} "
            f"OK={stats[STATUS_OK]} "
            f"{task_config.hit_status}={stats[task_config.hit_status]} "
            f"EMPTY={stats[STATUS_EMPTY]} "
            f"MODEL={stats['MODEL_CALLS']}"
        )

    return cli_progress


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a workbook QA or extraction task with either local Ollama or an OpenAI-compatible API."
    )
    parser.add_argument(
        "--input",
        default=str(default_input_path()),
        help="Path to the source Excel file.",
    )
    parser.add_argument(
        "--output",
        help="Path to the output Excel file. Defaults to <input>_checked.xlsx.",
    )
    parser.add_argument(
        "--task",
        default=DEFAULT_TASK_ID,
        choices=list(TASK_CONFIGS),
        help="Task to run. Default: english-check",
    )
    parser.add_argument(
        "--sheet",
        default="Sheet1",
        help="Worksheet name to process.",
    )
    parser.add_argument(
        "--source-col",
        default="C",
        help="Column to inspect. Default: C",
    )
    parser.add_argument(
        "--result-col",
        default="F",
        help="Column to write results to. Default: F",
    )
    parser.add_argument(
        "--model",
        help="Model name. Defaults to the saved model for the selected execution mode.",
    )
    parser.add_argument(
        "--prompt-file",
        help="Path to the prompt template file. Defaults to the selected task prompt.",
    )
    parser.add_argument(
        "--start-row",
        type=int,
        default=2,
        help="First row to process. Default: 2",
    )
    parser.add_argument(
        "--api-url",
        help="Base URL for the selected runtime. Local mode defaults to the saved Ollama URL.",
    )
    parser.add_argument(
        "--execution-mode",
        choices=["local", "api"],
        help="Choose whether to run against local Ollama or an OpenAI-compatible API provider.",
    )
    parser.add_argument(
        "--provider",
        help="Saved provider id to use in API mode.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        help="Maximum number of concurrent model requests.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP timeout in seconds for Ollama API calls.",
    )
    return parser


def _build_request_from_args(args: argparse.Namespace, settings: AppSettings) -> TaskRunRequest:
    task_config = get_task_config(args.task)
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else default_output_path(input_path)
    prompt_path = (
        Path(args.prompt_file).expanduser().resolve()
        if args.prompt_file
        else default_prompt_path(task_config.task_id)
    )
    execution_mode = args.execution_mode or settings.defaults.execution_mode

    provider_id: str | None = None
    api_key: str | None = None
    api_url = args.api_url or settings.defaults.local.base_url
    model = args.model or settings.defaults.local.model
    concurrency = args.concurrency or settings.defaults.local.concurrency

    if execution_mode == "api":
        provider_id = args.provider or settings.defaults.api.provider_id
        provider = get_provider(settings, provider_id)
        if provider is None:
            raise RuntimeError("API mode requires a saved provider. Configure one in the desktop app first.")
        if not provider.models:
            raise RuntimeError(f"Provider `{provider.provider_id}` has not been tested yet.")
        api_url = args.api_url or provider.base_url
        api_key = provider.api_key
        model = args.model or settings.defaults.api.model or provider.models[0]
        concurrency = args.concurrency or settings.defaults.api.concurrency

    return TaskRunRequest(
        task_config=task_config,
        input_path=input_path,
        output_path=output_path,
        prompt_path=prompt_path,
        sheet_name=args.sheet,
        source_col=args.source_col,
        result_col=args.result_col,
        start_row=args.start_row,
        execution_mode=execution_mode,
        provider_id=provider_id,
        api_url=api_url,
        api_key=api_key,
        model=model,
        concurrency=concurrency,
        timeout=args.timeout,
    )


def main() -> int:
    settings = load_settings()
    parser = build_parser()
    args = parser.parse_args()

    request = _build_request_from_args(args, settings)

    if not request.input_path.exists():
        print(f"Input file does not exist: {request.input_path}", file=sys.stderr)
        return 1

    print(f"Task  : {request.task_config.task_id}")
    print(f"Mode  : {request.execution_mode}")
    if request.provider_id:
        print(f"Provider: {request.provider_id}")
    print(f"Input : {request.input_path}")
    print(f"Output: {request.output_path}")
    print(f"Sheet : {request.sheet_name}")
    print(f"Model : {request.model}")
    print(f"Prompt: {request.prompt_path}")

    result = run_task(
        request,
        progress_callback=build_cli_progress_callback(request.task_config),
    )

    print("\nFinished.")
    print(f"Rows processed : {result.total_rows}")
    print(f"{STATUS_OK:<12}: {result.stats[STATUS_OK]}")
    print(f"{request.task_config.hit_status:<12}: {result.stats[request.task_config.hit_status]}")
    print(f"{STATUS_EMPTY:<12}: {result.stats[STATUS_EMPTY]}")
    print(f"MODEL_CALLS  : {result.stats['MODEL_CALLS']}")
    print(f"CACHE_HITS   : {result.stats['CACHE_HITS']}")
    if request.task_config.summary_sheet_name is not None:
        print(f"SUMMARY_TAB  : {request.task_config.summary_sheet_name}")
    return 0
