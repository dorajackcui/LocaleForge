from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import TextIO


class ProgressReporter:
    def __init__(self, mode: str = "none", stream: TextIO | None = None) -> None:
        self.mode = mode
        self.stream = stream or sys.stderr

    @property
    def enabled(self) -> bool:
        return self.mode in {"text", "jsonl"}

    def file_start(self, file_index: int, file_count: int, input_path: Path, rows_total: int) -> None:
        self._emit("file_start", file_index, file_count, input_path, rows_done=0, rows_total=rows_total, model_calls=0, cache_hits=0)

    def file_progress(
        self,
        file_index: int,
        file_count: int,
        input_path: Path,
        rows_done: int,
        rows_total: int,
        model_calls: int,
        cache_hits: int,
    ) -> None:
        self._emit("file_progress", file_index, file_count, input_path, rows_done, rows_total, model_calls, cache_hits)

    def file_done(
        self,
        file_index: int,
        file_count: int,
        input_path: Path,
        rows_total: int,
        model_calls: int,
        cache_hits: int,
    ) -> None:
        self._emit("file_done", file_index, file_count, input_path, rows_total, rows_total, model_calls, cache_hits)

    def _emit(
        self,
        event: str,
        file_index: int,
        file_count: int,
        input_path: Path,
        rows_done: int,
        rows_total: int,
        model_calls: int,
        cache_hits: int,
    ) -> None:
        if not self.enabled:
            return
        if self.mode == "jsonl":
            print(
                json.dumps(
                    {
                        "event": event,
                        "file_index": file_index,
                        "file_count": file_count,
                        "input": input_path.as_posix(),
                        "rows_done": rows_done,
                        "rows_total": rows_total,
                        "model_calls": model_calls,
                        "cache_hits": cache_hits,
                    },
                    ensure_ascii=False,
                ),
                file=self.stream,
                flush=True,
            )
            return

        label = f"[{file_index}/{file_count}] {input_path.name}"
        if event == "file_start":
            message = f"{label} start rows 0/{rows_total}"
        elif event == "file_done":
            message = f"{label} done rows {rows_total}/{rows_total} calls={model_calls} cache={cache_hits}"
        else:
            message = f"{label} rows {rows_done}/{rows_total} calls={model_calls} cache={cache_hits}"
        print(message, file=self.stream, flush=True)
