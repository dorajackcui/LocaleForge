from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
        description="Run a local workbook QA or extraction task with deterministic rules plus Ollama."
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
        default="gemma4:e4b",
        help="Ollama model name. Default: gemma4:e4b",
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
        default="http://127.0.0.1:11434",
        help="Base URL of the Ollama API.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=120.0,
        help="HTTP timeout in seconds for Ollama API calls.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    task_config = get_task_config(args.task)
    input_path = Path(args.input).expanduser().resolve()
    output_path = Path(args.output).expanduser().resolve() if args.output else default_output_path(input_path)
    prompt_path = (
        Path(args.prompt_file).expanduser().resolve()
        if args.prompt_file
        else default_prompt_path(task_config.task_id)
    )

    if not input_path.exists():
        print(f"Input file does not exist: {input_path}", file=sys.stderr)
        return 1

    print(f"Task  : {task_config.task_id}")
    print(f"Input : {input_path}")
    print(f"Output: {output_path}")
    print(f"Sheet : {args.sheet}")
    print(f"Model : {args.model}")
    print(f"Prompt: {prompt_path}")

    result = run_task(
        TaskRunRequest(
            task_config=task_config,
            input_path=input_path,
            output_path=output_path,
            prompt_path=prompt_path,
            sheet_name=args.sheet,
            source_col=args.source_col,
            result_col=args.result_col,
            start_row=args.start_row,
            api_url=args.api_url,
            model=args.model,
            timeout=args.timeout,
        ),
        progress_callback=build_cli_progress_callback(task_config),
    )

    print("\nFinished.")
    print(f"Rows processed : {result.total_rows}")
    print(f"{STATUS_OK:<12}: {result.stats[STATUS_OK]}")
    print(f"{task_config.hit_status:<12}: {result.stats[task_config.hit_status]}")
    print(f"{STATUS_EMPTY:<12}: {result.stats[STATUS_EMPTY]}")
    print(f"MODEL_CALLS  : {result.stats['MODEL_CALLS']}")
    print(f"CACHE_HITS   : {result.stats['CACHE_HITS']}")
    if task_config.summary_sheet_name is not None:
        print(f"SUMMARY_TAB  : {task_config.summary_sheet_name}")
    return 0
