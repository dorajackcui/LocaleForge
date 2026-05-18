from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from io import StringIO
from pathlib import Path

from localeforge.engine import RunOptions, run_task, validate_task
from localeforge.errors import ConfigError, ModelProviderError
from localeforge.progress import ProgressReporter
from localeforge.providers import StaticModelClient
from localeforge.task_profile import load_task_profile


class EngineTests(unittest.TestCase):
    def write_task(self, tmpdir: str) -> Path:
        path = Path(tmpdir) / "proofread.md"
        path.write_text("---\nid: proofread\nmode: transform\n---\n\nPolish.\n", encoding="utf-8")
        return path

    def test_validate_does_not_call_model(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\n", encoding="utf-8")
            profile = load_task_profile(task_path)

            report = validate_task(profile, task_path, RunOptions(input_path=input_path))

            self.assertEqual(report.status, "success")
            self.assertEqual(report.files[0].rows_total, 1)
            self.assertFalse((Path(tmpdir) / "a_proofread.csv").exists())

    def test_run_transforms_csv_and_uses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\nhello\n\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = StaticModelClient({"hello": "bonjour"})

            report = run_task(profile, task_path, RunOptions(input_path=input_path), client)

            self.assertEqual(report.status, "success")
            self.assertEqual(report.files[0].rows_processed, 2)
            self.assertEqual(report.files[0].rows_empty, 1)
            self.assertEqual(report.files[0].model_calls, 1)
            self.assertEqual(report.files[0].cache_hits, 1)
            self.assertIn("a_proofread.csv", str(report.files[0].output))
            self.assertIn("bonjour", report.files[0].output.read_text(encoding="utf-8"))

    def test_run_adds_tips_to_system_prompt(self) -> None:
        class PromptCaptureClient:
            def __init__(self) -> None:
                self.prompts: list[str] = []

            def ensure_available(self) -> list[str]:
                return ["capture"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                self.prompts.append(system_prompt)
                return "bonjour"

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = PromptCaptureClient()

            run_task(
                profile,
                task_path,
                RunOptions(input_path=input_path, tips="Use informal tone for this batch."),
                client,
            )

            self.assertEqual(len(client.prompts), 1)
            self.assertIn("Polish.", client.prompts[0])
            self.assertIn("Session tips:", client.prompts[0])
            self.assertIn("Use informal tone for this batch.", client.prompts[0])

    def test_run_uses_bounded_concurrency_for_model_calls(self) -> None:
        class SlowClient:
            def __init__(self) -> None:
                self.active = 0
                self.max_active = 0
                self.lock = threading.Lock()

            def ensure_available(self) -> list[str]:
                return ["slow"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                with self.lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                time.sleep(0.05)
                with self.lock:
                    self.active -= 1
                return user_text.upper()

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\na\nb\nc\nd\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = SlowClient()

            report = run_task(profile, task_path, RunOptions(input_path=input_path, concurrency=3), client)

            self.assertEqual(report.status, "success")
            self.assertGreater(client.max_active, 1)
            self.assertEqual(report.files[0].model_calls, 4)
            output_text = report.files[0].output.read_text(encoding="utf-8")
            self.assertIn("A", output_text)
            self.assertIn("D", output_text)

    def test_progress_streams_as_model_calls_finish(self) -> None:
        class BlockingClient:
            def __init__(self) -> None:
                self.fast_done = threading.Event()
                self.slow_started = threading.Event()
                self.release_slow = threading.Event()

            def ensure_available(self) -> list[str]:
                return ["blocking"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                if user_text == "fast":
                    self.fast_done.set()
                    return "FAST"
                self.slow_started.set()
                if not self.release_slow.wait(timeout=5):
                    raise AssertionError("slow request was not released")
                return "SLOW"

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nfast\nslow\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = BlockingClient()
            progress_stream = StringIO()
            errors: list[BaseException] = []

            def run() -> None:
                try:
                    run_task(
                        profile,
                        task_path,
                        RunOptions(input_path=input_path, concurrency=2),
                        client,
                        progress=ProgressReporter(mode="text", stream=progress_stream),
                    )
                except BaseException as exc:
                    errors.append(exc)

            thread = threading.Thread(target=run)
            thread.start()
            self.assertTrue(client.fast_done.wait(timeout=2))
            self.assertTrue(client.slow_started.wait(timeout=2))
            time.sleep(0.05)
            observed = progress_stream.getvalue()

            client.release_slow.set()
            thread.join(timeout=2)

            self.assertIn("rows 1/2", observed)

            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])

    def test_status_json_writes_each_json_field_to_a_column(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = Path(tmpdir) / "status.md"
            task_path.write_text(
                "---\n"
                "id: qa\n"
                "mode: status-json\n"
                "---\n\n"
                "Return JSON.\n",
                encoding="utf-8",
            )
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = StaticModelClient(
                {
                    "hello": (
                        '{"status":"NEEDS_REVIEW","category":"tone",'
                        '"reason":"Too literal","suggestion":"Rewrite naturally"}'
                    )
                }
            )

            report = run_task(profile, task_path, RunOptions(input_path=input_path), client)

            self.assertEqual(report.status, "success")
            output_text = report.files[0].output.read_text(encoding="utf-8")
            self.assertIn("status,category,reason,suggestion", output_text)
            self.assertIn("NEEDS_REVIEW,tone,Too literal,Rewrite naturally", output_text)

    def test_status_json_retries_invalid_model_json(self) -> None:
        class FlakyJsonClient:
            def __init__(self) -> None:
                self.calls = 0
                self.prompts: list[str] = []

            def ensure_available(self) -> list[str]:
                return ["flaky"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                self.calls += 1
                self.prompts.append(system_prompt)
                if self.calls == 1:
                    return "not json"
                return '{"status":"OK","reason":"Valid on retry"}'

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = Path(tmpdir) / "status.md"
            task_path.write_text("---\nid: qa\nmode: status-json\n---\n\nReturn JSON.\n", encoding="utf-8")
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = FlakyJsonClient()

            report = run_task(profile, task_path, RunOptions(input_path=input_path, tips="Keep JSON compact."), client)

            self.assertEqual(report.status, "success")
            self.assertEqual(client.calls, 2)
            self.assertEqual(report.files[0].model_calls, 2)
            self.assertIn("Previous attempt failed", client.prompts[1])
            self.assertIn("Return JSON.", client.prompts[1])
            self.assertIn("Keep JSON compact.", client.prompts[1])
            self.assertIn("OK", report.files[0].output.read_text(encoding="utf-8"))

    def test_status_json_raises_after_retry_limit(self) -> None:
        class AlwaysInvalidJsonClient:
            def __init__(self) -> None:
                self.calls = 0

            def ensure_available(self) -> list[str]:
                return ["invalid"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                self.calls += 1
                return "not json"

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = Path(tmpdir) / "status.md"
            task_path.write_text("---\nid: qa\nmode: status-json\n---\n\nReturn JSON.\n", encoding="utf-8")
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = AlwaysInvalidJsonClient()

            with self.assertRaisesRegex(ModelProviderError, "after 2 attempts"):
                run_task(profile, task_path, RunOptions(input_path=input_path, max_attempts=2), client)

            self.assertEqual(client.calls, 2)

    def test_status_json_output_columns_can_rename_json_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = Path(tmpdir) / "status.md"
            task_path.write_text(
                "---\n"
                "id: qa\n"
                "mode: status-json\n"
                "output:\n"
                "  columns:\n"
                "    status: review_status\n"
                "    reason: review_reason\n"
                "---\n\n"
                "Return JSON.\n",
                encoding="utf-8",
            )
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = StaticModelClient({"hello": '{"status":"NEEDS_REVIEW","reason":"Too literal"}'})

            report = run_task(profile, task_path, RunOptions(input_path=input_path), client)

            output_text = report.files[0].output.read_text(encoding="utf-8")
            self.assertIn("review_status,review_reason", output_text)
            self.assertIn("NEEDS_REVIEW,Too literal", output_text)

    def test_status_json_declared_fields_reject_unknown_fields_and_retry(self) -> None:
        class ExtraFieldThenValidClient:
            def __init__(self) -> None:
                self.calls = 0

            def ensure_available(self) -> list[str]:
                return ["extra-then-valid"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                self.calls += 1
                if self.calls == 1:
                    return '{"status":"OK","reason":"Fine","extra":"surprise"}'
                return '{"status":"OK","reason":"Fine"}'

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = Path(tmpdir) / "status.md"
            task_path.write_text(
                "---\n"
                "id: qa\n"
                "mode: status-json\n"
                "output:\n"
                "  fields:\n"
                "    - status\n"
                "    - reason\n"
                "---\n\n"
                "Return JSON.\n",
                encoding="utf-8",
            )
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = ExtraFieldThenValidClient()

            report = run_task(profile, task_path, RunOptions(input_path=input_path, max_attempts=2), client)

            self.assertEqual(client.calls, 2)
            self.assertEqual(report.files[0].model_calls, 2)
            output_text = report.files[0].output.read_text(encoding="utf-8")
            self.assertIn("status,reason", output_text)
            self.assertNotIn("extra", output_text)

    def test_window_mode_transforms_rows_in_ordered_batches(self) -> None:
        class WindowClient:
            def __init__(self) -> None:
                self.user_texts: list[str] = []

            def ensure_available(self) -> list[str]:
                return ["window"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                self.user_texts.append(user_text)
                payload = json.loads(user_text)
                return json.dumps(
                    [
                        {"row": item["row"], "target": item["source"].upper()}
                        for item in payload["current"]
                    ],
                    ensure_ascii=False,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\na\nb\nc\n\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = WindowClient()

            report = run_task(
                profile,
                task_path,
                RunOptions(input_path=input_path, request_mode="window", window_size=2),
                client,
            )

            self.assertEqual(report.status, "success")
            self.assertEqual(report.files[0].rows_processed, 3)
            self.assertEqual(report.files[0].rows_empty, 1)
            self.assertEqual(report.files[0].model_calls, 2)
            self.assertEqual(report.files[0].cache_hits, 0)
            self.assertEqual(len(client.user_texts), 2)
            output_text = report.files[0].output.read_text(encoding="utf-8")
            self.assertIn("A", output_text)
            self.assertIn("C", output_text)

    def test_window_mode_status_json_writes_declared_fields(self) -> None:
        class StatusWindowClient:
            def ensure_available(self) -> list[str]:
                return ["window-status"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                payload = json.loads(user_text)
                return json.dumps(
                    [
                        {"row": item["row"], "status": "OK", "reason": item["source"].upper()}
                        for item in payload["current"]
                    ],
                    ensure_ascii=False,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = Path(tmpdir) / "status.md"
            task_path.write_text(
                "---\n"
                "id: qa\n"
                "mode: status-json\n"
                "output:\n"
                "  fields:\n"
                "    - status\n"
                "    - reason\n"
                "---\n\n"
                "Return JSON.\n",
                encoding="utf-8",
            )
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\nworld\n", encoding="utf-8")
            profile = load_task_profile(task_path)

            report = run_task(
                profile,
                task_path,
                RunOptions(input_path=input_path, request_mode="window", window_size=5),
                StatusWindowClient(),
            )

            output_text = report.files[0].output.read_text(encoding="utf-8")
            self.assertIn("status,reason", output_text)
            self.assertIn("OK,HELLO", output_text)
            self.assertIn("OK,WORLD", output_text)

    def test_window_mode_overwrites_existing_target_when_output_overwrite_false(self) -> None:
        class WindowOverwriteClient:
            def ensure_available(self) -> list[str]:
                return ["window-overwrite"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                payload = json.loads(user_text)
                return json.dumps(
                    [
                        {"row": item["row"], "target": item["source"].upper()}
                        for item in payload["current"]
                    ],
                    ensure_ascii=False,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = Path(tmpdir) / "proofread.md"
            task_path.write_text(
                "---\n"
                "id: proofread\n"
                "mode: transform\n"
                "output:\n"
                "  overwrite: false\n"
                "---\n\n"
                "Polish.\n",
                encoding="utf-8",
            )
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source,target\na,OLD\n", encoding="utf-8")
            profile = load_task_profile(task_path)

            report = run_task(
                profile,
                task_path,
                RunOptions(input_path=input_path, request_mode="window", window_size=1),
                WindowOverwriteClient(),
            )

            output_text = report.files[0].output.read_text(encoding="utf-8")
            self.assertIn("a,A", output_text)
            self.assertNotIn("a,OLD", output_text)

    def test_window_mode_status_json_overwrites_existing_fields_when_output_overwrite_false(self) -> None:
        class StatusOverwriteClient:
            def ensure_available(self) -> list[str]:
                return ["window-status-overwrite"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                payload = json.loads(user_text)
                return json.dumps(
                    [
                        {"row": item["row"], "status": "OK", "reason": item["source"].upper()}
                        for item in payload["current"]
                    ],
                    ensure_ascii=False,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = Path(tmpdir) / "status.md"
            task_path.write_text(
                "---\n"
                "id: qa\n"
                "mode: status-json\n"
                "output:\n"
                "  overwrite: false\n"
                "  fields:\n"
                "    - status\n"
                "    - reason\n"
                "---\n\n"
                "Return JSON.\n",
                encoding="utf-8",
            )
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source,status,reason\nhello,OLD_STATUS,OLD_REASON\n", encoding="utf-8")
            profile = load_task_profile(task_path)

            report = run_task(
                profile,
                task_path,
                RunOptions(input_path=input_path, request_mode="window", window_size=1),
                StatusOverwriteClient(),
            )

            output_text = report.files[0].output.read_text(encoding="utf-8")
            self.assertIn("hello,OK,HELLO", output_text)
            self.assertNotIn("OLD_STATUS", output_text)
            self.assertNotIn("OLD_REASON", output_text)

    def test_window_mode_duplicate_sources_do_not_dedupe_or_cache(self) -> None:
        class DuplicateWindowClient:
            def __init__(self) -> None:
                self.user_texts: list[str] = []

            def ensure_available(self) -> list[str]:
                return ["window-duplicates"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                self.user_texts.append(user_text)
                payload = json.loads(user_text)
                return json.dumps(
                    [
                        {"row": item["row"], "target": item["source"].upper()}
                        for item in payload["current"]
                    ],
                    ensure_ascii=False,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nsame\nsame\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = DuplicateWindowClient()

            report = run_task(
                profile,
                task_path,
                RunOptions(input_path=input_path, request_mode="window", window_size=1),
                client,
            )

            output_text = report.files[0].output.read_text(encoding="utf-8")
            self.assertEqual(report.files[0].rows_processed, 2)
            self.assertEqual(len(client.user_texts), 2)
            self.assertEqual(report.files[0].model_calls, 2)
            self.assertEqual(report.files[0].cache_hits, 0)
            self.assertEqual(output_text.count("SAME"), 2)

    def test_window_mode_status_json_requires_declared_output_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = Path(tmpdir) / "status.md"
            task_path.write_text("---\nid: qa\nmode: status-json\n---\n\nReturn JSON.\n", encoding="utf-8")
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\nhello\n", encoding="utf-8")
            profile = load_task_profile(task_path)

            with self.assertRaisesRegex(ConfigError, "requires status-json tasks to declare output.fields"):
                run_task(
                    profile,
                    task_path,
                    RunOptions(input_path=input_path, request_mode="window"),
                    StaticModelClient({}),
                )

    def test_window_mode_includes_previous_targets_and_next_sources(self) -> None:
        class ContextCaptureClient:
            def __init__(self) -> None:
                self.payloads: list[dict[str, object]] = []

            def ensure_available(self) -> list[str]:
                return ["capture"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                payload = json.loads(user_text)
                self.payloads.append(payload)
                return json.dumps(
                    [
                        {"row": item["row"], "target": item["source"].upper()}
                        for item in payload["current"]
                    ],
                    ensure_ascii=False,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\na\nb\nc\nd\ne\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = ContextCaptureClient()

            run_task(
                profile,
                task_path,
                RunOptions(input_path=input_path, request_mode="window", window_size=2),
                client,
            )

            self.assertEqual(client.payloads[0]["previous"], [])
            self.assertEqual([item["source"] for item in client.payloads[0]["next"]], ["c", "d"])
            self.assertEqual(client.payloads[1]["previous"][0]["source"], "a")
            self.assertEqual(client.payloads[1]["previous"][0]["target"], "A")
            self.assertEqual(client.payloads[1]["previous"][1]["target"], "B")
            self.assertEqual([item["source"] for item in client.payloads[1]["next"]], ["e"])

    def test_window_mode_retries_invalid_window_response(self) -> None:
        class FlakyWindowClient:
            def __init__(self) -> None:
                self.calls = 0
                self.prompts: list[str] = []

            def ensure_available(self) -> list[str]:
                return ["flaky-window"]

            def generate(self, system_prompt: str, user_text: str) -> str:
                self.calls += 1
                self.prompts.append(system_prompt)
                if self.calls == 1:
                    return '[{"row":999,"target":"bad"}]'
                payload = json.loads(user_text)
                return json.dumps(
                    [{"row": item["row"], "target": item["source"].upper()} for item in payload["current"]],
                    ensure_ascii=False,
                )

        with tempfile.TemporaryDirectory() as tmpdir:
            task_path = self.write_task(tmpdir)
            input_path = Path(tmpdir) / "a.csv"
            input_path.write_text("source\na\nb\n", encoding="utf-8")
            profile = load_task_profile(task_path)
            client = FlakyWindowClient()

            report = run_task(
                profile,
                task_path,
                RunOptions(input_path=input_path, request_mode="window", window_size=2, max_attempts=2),
                client,
            )

            self.assertEqual(client.calls, 2)
            self.assertEqual(report.files[0].model_calls, 2)
            self.assertIn("Previous attempt failed", client.prompts[1])
            self.assertIn("A", report.files[0].output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
