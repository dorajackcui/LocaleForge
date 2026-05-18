from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _path_value(path: Path | None) -> str | None:
    if path is None:
        return None
    return Path(path).as_posix()


@dataclass(frozen=True)
class TaskReport:
    id: str
    mode: str
    path: Path

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "mode": self.mode,
            "path": _path_value(self.path),
        }


@dataclass(frozen=True)
class ModelReport:
    execution_mode: str
    provider: str | None
    name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "execution_mode": self.execution_mode,
            "provider": self.provider,
            "name": self.name,
        }


@dataclass
class FileReport:
    status: str
    input: Path
    output: Path
    rows_total: int = 0
    rows_processed: int = 0
    rows_empty: int = 0
    model_calls: int = 0
    cache_hits: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "input": _path_value(self.input),
            "output": _path_value(self.output),
            "rows_total": self.rows_total,
            "rows_processed": self.rows_processed,
            "rows_empty": self.rows_empty,
            "model_calls": self.model_calls,
            "cache_hits": self.cache_hits,
            "errors": list(self.errors),
        }


@dataclass
class RunReport:
    status: str
    task: TaskReport
    model: ModelReport
    files: list[FileReport] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "task": self.task.to_dict(),
            "model": self.model.to_dict(),
            "files": [item.to_dict() for item in self.files],
            "errors": list(self.errors),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
