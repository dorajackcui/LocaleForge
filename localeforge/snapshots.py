from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import InputOutputError


SCHEMA_VERSION = 1
SNAPSHOT_DIR_NAME = ".localeforge-snapshots"
SNAPSHOT_SUFFIX = ".snapshot.json"


@dataclass(frozen=True)
class SnapshotDescriptor:
    task_id: str
    task_mode: str
    task_fingerprint: str
    input_path: Path
    input_fingerprint: str
    output_path: Path
    request_mode: str
    window_size: int
    model_name: str
    provider_id: str | None
    sheet: str | None
    input_column: str
    output_column: str | None
    output_fields: tuple[str, ...] = ()
    output_columns: tuple[tuple[str, str], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_mode": self.task_mode,
            "task_fingerprint": self.task_fingerprint,
            "input_path": self.input_path.as_posix(),
            "input_fingerprint": self.input_fingerprint,
            "output_path": self.output_path.as_posix(),
            "request_mode": self.request_mode,
            "window_size": self.window_size,
            "model_name": self.model_name,
            "provider_id": self.provider_id,
            "sheet": self.sheet,
            "input_column": self.input_column,
            "output_column": self.output_column,
            "output_fields": list(self.output_fields),
            "output_columns": [[key, value] for key, value in self.output_columns],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SnapshotDescriptor:
        return cls(
            task_id=str(payload["task_id"]),
            task_mode=str(payload["task_mode"]),
            task_fingerprint=str(payload["task_fingerprint"]),
            input_path=Path(str(payload["input_path"])),
            input_fingerprint=str(payload["input_fingerprint"]),
            output_path=Path(str(payload["output_path"])),
            request_mode=str(payload["request_mode"]),
            window_size=int(payload["window_size"]),
            model_name=str(payload["model_name"]),
            provider_id=str(payload["provider_id"]) if payload.get("provider_id") is not None else None,
            sheet=str(payload["sheet"]) if payload.get("sheet") is not None else None,
            input_column=str(payload["input_column"]),
            output_column=str(payload["output_column"]) if payload.get("output_column") is not None else None,
            output_fields=tuple(str(item) for item in payload.get("output_fields", [])),
            output_columns=tuple((str(key), str(value)) for key, value in payload.get("output_columns", [])),
        )


@dataclass
class SnapshotRow:
    primary: str = ""
    fields: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "primary": self.primary,
            "fields": dict(self.fields),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> SnapshotRow:
        fields = payload.get("fields", {})
        if not isinstance(fields, dict):
            raise InputOutputError("Snapshot row fields must be an object.")
        return cls(
            primary=str(payload.get("primary", "")),
            fields={str(key): str(value) for key, value in fields.items()},
        )


@dataclass
class RunSnapshot:
    schema_version: int
    descriptor: SnapshotDescriptor
    completed_rows: dict[int, SnapshotRow] = field(default_factory=dict)

    @classmethod
    def new(cls, descriptor: SnapshotDescriptor) -> RunSnapshot:
        return cls(schema_version=SCHEMA_VERSION, descriptor=descriptor)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "descriptor": self.descriptor.to_dict(),
            "completed_rows": {
                str(row_index): row.to_dict()
                for row_index, row in sorted(self.completed_rows.items())
            },
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> RunSnapshot:
        schema_version = int(payload.get("schema_version", 0))
        if schema_version != SCHEMA_VERSION:
            raise InputOutputError(
                f"Unsupported snapshot schema version {schema_version}; expected {SCHEMA_VERSION}."
            )
        rows_payload = payload.get("completed_rows", {})
        if not isinstance(rows_payload, dict):
            raise InputOutputError("Snapshot completed_rows must be an object.")
        return cls(
            schema_version=schema_version,
            descriptor=SnapshotDescriptor.from_dict(payload["descriptor"]),
            completed_rows={
                int(row_index): SnapshotRow.from_dict(row_payload)
                for row_index, row_payload in rows_payload.items()
            },
        )


def snapshot_path_for(output_path: Path | str) -> Path:
    output = Path(output_path)
    return output.parent / SNAPSHOT_DIR_NAME / f"{output.name}{SNAPSHOT_SUFFIX}"


def snapshot_exists(output_path: Path | str) -> bool:
    return snapshot_path_for(output_path).exists()


def load_snapshot(path: Path | str) -> RunSnapshot:
    resolved = Path(path)
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise InputOutputError("Snapshot root must be an object.")
        return RunSnapshot.from_dict(payload)
    except json.JSONDecodeError as exc:
        raise InputOutputError(f"Snapshot is not valid JSON: {resolved}") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise InputOutputError(f"Snapshot is malformed: {resolved}") from exc


def save_snapshot(snapshot: RunSnapshot) -> None:
    path = snapshot_path_for(snapshot.descriptor.output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp_path.replace(path)


def delete_snapshot(output_path: Path | str) -> None:
    path = snapshot_path_for(output_path)
    try:
        path.unlink()
    except FileNotFoundError:
        return


def assert_snapshot_compatible(snapshot: RunSnapshot, descriptor: SnapshotDescriptor) -> None:
    if snapshot.descriptor == descriptor:
        return

    mismatches = [
        name
        for name in snapshot.descriptor.__dataclass_fields__
        if getattr(snapshot.descriptor, name) != getattr(descriptor, name)
    ]
    details = ", ".join(mismatches) if mismatches else "metadata"
    raise InputOutputError(
        "Snapshot does not match this run "
        f"({details}). Use --resume with the original command or --force to discard the snapshot."
    )


def fingerprint_path(path: Path | str) -> str:
    resolved = Path(path)
    stat = resolved.stat()
    return f"{stat.st_size}:{stat.st_mtime_ns}"
