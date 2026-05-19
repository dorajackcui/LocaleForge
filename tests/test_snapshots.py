from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from localeforge.errors import InputOutputError
from localeforge.snapshots import (
    RunSnapshot,
    SnapshotDescriptor,
    SnapshotRow,
    assert_snapshot_compatible,
    delete_snapshot,
    load_snapshot,
    save_snapshot,
    snapshot_exists,
    snapshot_path_for,
)


class SnapshotTests(unittest.TestCase):
    def descriptor(self, tmpdir: str) -> SnapshotDescriptor:
        root = Path(tmpdir)
        input_path = root / "source.csv"
        output_path = root / "source_rewrite.csv"
        input_path.write_text("source\nhello\n", encoding="utf-8")
        return SnapshotDescriptor(
            task_id="rewrite",
            task_mode="transform",
            task_fingerprint="task-size:mtime",
            input_path=input_path,
            input_fingerprint="input-size:mtime",
            output_path=output_path,
            request_mode="concurrent",
            window_size=5,
            model_name="gpt-5.5",
            provider_id="env",
            sheet=None,
            input_column="source",
            output_column="target",
            output_fields=(),
        )

    def test_snapshot_path_lives_next_to_output_in_hidden_directory(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            descriptor = self.descriptor(tmpdir)

            path = snapshot_path_for(descriptor.output_path)

            self.assertEqual(path.parent.name, ".localeforge-snapshots")
            self.assertEqual(path.name, "source_rewrite.csv.snapshot.json")
            self.assertEqual(path.parent.parent, Path(tmpdir))

    def test_snapshot_round_trips_completed_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            descriptor = self.descriptor(tmpdir)
            snapshot = RunSnapshot.new(descriptor)
            snapshot.completed_rows[2] = SnapshotRow(primary="bonjour", fields={})
            snapshot.completed_rows[3] = SnapshotRow(primary="", fields={"status": "OK"})

            save_snapshot(snapshot)
            loaded = load_snapshot(snapshot_path_for(descriptor.output_path))

            self.assertEqual(loaded.descriptor, descriptor)
            self.assertEqual(loaded.completed_rows[2].primary, "bonjour")
            self.assertEqual(loaded.completed_rows[3].fields["status"], "OK")

    def test_mismatched_snapshot_metadata_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            descriptor = self.descriptor(tmpdir)
            snapshot = RunSnapshot.new(descriptor)
            changed = replace(descriptor, request_mode="window")

            with self.assertRaisesRegex(InputOutputError, "Snapshot does not match this run"):
                assert_snapshot_compatible(snapshot, changed)

    def test_delete_snapshot_removes_existing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            descriptor = self.descriptor(tmpdir)
            save_snapshot(RunSnapshot.new(descriptor))
            self.assertTrue(snapshot_exists(descriptor.output_path))

            delete_snapshot(descriptor.output_path)

            self.assertFalse(snapshot_exists(descriptor.output_path))


if __name__ == "__main__":
    unittest.main()
