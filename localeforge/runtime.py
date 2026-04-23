from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .config.tasks import TaskConfig
from .model.openai_compatible import OpenAICompatibleClient
from .model.ollama import OllamaClient
from .prompts import load_prompt_template
from .types import ProgressCallback
from .workbook import process_workbook


@dataclass(frozen=True)
class TaskRunRequest:
    task_config: TaskConfig
    input_path: Path
    output_path: Path
    prompt_path: Path
    sheet_name: str
    source_col: str
    result_col: str
    start_row: int
    execution_mode: str = "local"
    provider_id: str | None = None
    api_url: str = ""
    api_key: str | None = None
    model: str = ""
    concurrency: int = 1
    timeout: float = 120.0


@dataclass(frozen=True)
class TaskRunResult:
    output_path: Path
    total_rows: int
    stats: dict[str, int]


def run_task(
    request: TaskRunRequest,
    progress_callback: ProgressCallback | None = None,
    log_callback: Callable[[str], None] | None = None,
) -> TaskRunResult:
    prompt_template = load_prompt_template(request.prompt_path)
    if request.execution_mode == "api":
        client = OpenAICompatibleClient(
            api_url=request.api_url,
            api_key=request.api_key or "",
            model=request.model,
            timeout=request.timeout,
            prompt_template=prompt_template,
            task_config=request.task_config,
        )
    else:
        client = OllamaClient(
            api_url=request.api_url,
            model=request.model,
            timeout=request.timeout,
            prompt_template=prompt_template,
            task_config=request.task_config,
        )

    if log_callback is not None:
        if request.execution_mode == "api":
            label = request.provider_id or request.api_url
            log_callback(f"Checking API provider `{label}`...")
        else:
            log_callback("Checking local Ollama service...")
    available_models = client.ensure_available()
    if log_callback is not None:
        if request.execution_mode == "api":
            label = request.provider_id or request.api_url
            model_count = len(available_models or [])
            log_callback(f"API provider `{label}` is ready ({model_count} models). Starting workbook processing...")
        else:
            log_callback("Ollama is ready. Starting workbook processing...")

    total_rows, stats = process_workbook(
        input_path=request.input_path,
        output_path=request.output_path,
        sheet_name=request.sheet_name,
        source_col=request.source_col,
        result_col=request.result_col,
        start_row=request.start_row,
        client=client,
        task_config=request.task_config,
        concurrency=request.concurrency,
        progress_callback=progress_callback,
    )
    return TaskRunResult(
        output_path=request.output_path,
        total_rows=total_rows,
        stats=stats,
    )
