# Agent-First CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the old LocaleForge app with a clean, agent-first CLI that runs Markdown-defined LLM tasks over single `.xlsx`/`.csv` files or folders.

**Architecture:** The CLI is the product surface. Markdown task profiles, saved provider settings, tabular readers/writers, mode processors, and report objects are separate modules with narrow interfaces. `localeforge run` resolves file/folder work items, validates tabular contracts, calls the selected model client, writes new output files, and emits stable JSON reports and exit codes.

**Tech Stack:** Python 3.11+, standard-library `argparse`, `dataclasses`, `csv`, `json`, `unittest`; `openpyxl` for `.xlsx`; `requests` for HTTP providers; `PyYAML` for Markdown front matter.

---

## File Structure

- Create `pyproject.toml`: package metadata and `localeforge` console script.
- Modify `requirements.txt`: keep `openpyxl` and `requests`; add `PyYAML`.
- Replace `README.md`: document the new CLI only.
- Modify `localeforge/__init__.py`: expose version.
- Create `localeforge/errors.py`: typed errors and exit-code mapping.
- Create `localeforge/task_profile.py`: Markdown front matter parser and task schema.
- Create `localeforge/settings.py`: provider persistence, defaults, secret redaction.
- Create `localeforge/providers.py`: provider client protocol, OpenAI-compatible client, local Ollama client, fake-friendly factory.
- Create `localeforge/inputs.py`: input discovery, single-file/folder output mapping.
- Create `localeforge/tabular.py`: CSV/XLSX read/write and column resolution.
- Create `localeforge/modes.py`: `transform` and `status-json` response processors.
- Create `localeforge/report.py`: report dataclasses and JSON serialization.
- Create `localeforge/engine.py`: validate/run orchestration, caching, concurrency, per-file failure handling.
- Replace `localeforge/cli.py`: command parser and command handlers for `run`, `validate`, `doctor`, `provider`.
- Create `localeforge/__main__.py`: `python -m localeforge` entry.
- Create starter task files under `tasks/`.
- Replace tests under `tests/` with the new CLI-first test suite.
- Delete old UI, wrapper scripts, old task registry, old prompt files, and obsolete model/runtime modules after replacements exist.

---

### Task 1: Package Metadata And Baseline Tests

**Files:**
- Create: `pyproject.toml`
- Modify: `requirements.txt`
- Modify: `localeforge/__init__.py`
- Create: `localeforge/__main__.py`
- Create: `tests/test_package.py`

- [ ] **Step 1: Write the failing package test**

Create `tests/test_package.py`:

```python
from __future__ import annotations

import unittest

import localeforge
from localeforge.cli import build_parser


class PackageTests(unittest.TestCase):
    def test_version_is_available(self) -> None:
        self.assertRegex(localeforge.__version__, r"^\d+\.\d+\.\d+$")

    def test_parser_has_agent_first_commands(self) -> None:
        parser = build_parser()
        help_text = parser.format_help()

        self.assertIn("run", help_text)
        self.assertIn("validate", help_text)
        self.assertIn("doctor", help_text)
        self.assertIn("provider", help_text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the package test and verify it fails**

Run: `python -m unittest tests.test_package -v`

Expected: fails because the new parser and version are not implemented yet.

- [ ] **Step 3: Add package metadata and minimal entry points**

Create `pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "localeforge"
version = "0.1.0"
description = "Agent-first CLI for LLM batch processing over Excel and CSV files."
readme = "README.md"
requires-python = ">=3.11"
dependencies = [
  "openpyxl",
  "requests",
  "PyYAML",
]

[project.scripts]
localeforge = "localeforge.cli:main"
```

Replace `requirements.txt`:

```text
openpyxl
requests
PyYAML
```

Replace `localeforge/__init__.py`:

```python
from __future__ import annotations

__version__ = "0.1.0"
```

Create `localeforge/__main__.py`:

```python
from __future__ import annotations

from .cli import main


if __name__ == "__main__":
    raise SystemExit(main())
```

Temporarily replace `localeforge/cli.py` with a parser skeleton:

```python
from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="localeforge")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run")
    subparsers.add_parser("validate")
    subparsers.add_parser("doctor")
    provider = subparsers.add_parser("provider")
    provider.add_subparsers(dest="provider_command")
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    return 0
```

- [ ] **Step 4: Run the package test and verify it passes**

Run: `python -m unittest tests.test_package -v`

Expected: passes.

- [ ] **Step 5: Commit**

Run:

```powershell
git add pyproject.toml requirements.txt localeforge\__init__.py localeforge\__main__.py localeforge\cli.py tests\test_package.py
git commit -m "Add agent-first package skeleton"
```

---

### Task 2: Typed Errors And Reports

**Files:**
- Create: `localeforge/errors.py`
- Create: `localeforge/report.py`
- Create: `tests/test_errors_report.py`

- [ ] **Step 1: Write failing tests for errors and report serialization**

Create `tests/test_errors_report.py`:

```python
from __future__ import annotations

import json
import unittest
from pathlib import Path

from localeforge.errors import ConfigError, InputOutputError, ModelProviderError, PartialFailureError, exit_code_for_error
from localeforge.report import FileReport, RunReport, TaskReport, ModelReport


class ErrorsAndReportTests(unittest.TestCase):
    def test_error_exit_codes_are_stable(self) -> None:
        self.assertEqual(exit_code_for_error(ConfigError("bad config")), 1)
        self.assertEqual(exit_code_for_error(InputOutputError("bad file")), 2)
        self.assertEqual(exit_code_for_error(ModelProviderError("bad model")), 3)
        self.assertEqual(exit_code_for_error(PartialFailureError("partial")), 4)

    def test_run_report_serializes_paths_and_counts(self) -> None:
        report = RunReport(
            status="success",
            task=TaskReport(id="proofread", mode="transform", path=Path("tasks/proofread.md")),
            model=ModelReport(execution_mode="api", provider="default-api", name="gpt-4.1-mini"),
            files=[
                FileReport(
                    status="success",
                    input=Path("data/a.csv"),
                    output=Path("out/a.localeforge.csv"),
                    rows_total=2,
                    rows_processed=1,
                    rows_empty=1,
                    model_calls=1,
                    cache_hits=0,
                    errors=[],
                )
            ],
            errors=[],
        )

        payload = report.to_dict()
        self.assertEqual(payload["status"], "success")
        self.assertEqual(payload["files"][0]["input"], "data/a.csv")
        self.assertEqual(json.loads(report.to_json())["task"]["id"], "proofread")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m unittest tests.test_errors_report -v`

Expected: fails because `errors.py` and `report.py` do not exist.

- [ ] **Step 3: Implement errors and report dataclasses**

Create `localeforge/errors.py` with `LocaleForgeError`, `ConfigError`, `TaskProfileError`, `InputOutputError`, `ModelProviderError`, `PartialFailureError`, and `exit_code_for_error`.

Create `localeforge/report.py` with `TaskReport`, `ModelReport`, `FileReport`, `RunReport`, `to_dict()`, and `to_json()` methods that convert paths to forward-slash strings.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `python -m unittest tests.test_errors_report -v`

Expected: passes.

- [ ] **Step 5: Commit**

Run:

```powershell
git add localeforge\errors.py localeforge\report.py tests\test_errors_report.py
git commit -m "Add errors and report primitives"
```

---

### Task 3: Markdown Task Profiles

**Files:**
- Create: `localeforge/task_profile.py`
- Create: `tests/test_task_profile.py`

- [ ] **Step 1: Write failing task profile tests**

Create `tests/test_task_profile.py` covering:

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from localeforge.errors import TaskProfileError
from localeforge.task_profile import load_task_profile


class TaskProfileTests(unittest.TestCase):
    def write_task(self, text: str) -> Path:
        tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir.cleanup)
        path = Path(tmpdir.name) / "task.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_minimal_transform_task_uses_defaults(self) -> None:
        path = self.write_task("---\nid: proofread\n---\n\nPolish the text.\n")
        profile = load_task_profile(path)

        self.assertEqual(profile.id, "proofread")
        self.assertEqual(profile.mode, "transform")
        self.assertEqual(profile.input.column, "source")
        self.assertEqual(profile.output.column, "target")
        self.assertTrue(profile.output.overwrite)
        self.assertEqual(profile.prompt, "Polish the text.")

    def test_full_task_reads_nested_config(self) -> None:
        path = self.write_task(
            "---\n"
            "id: proofread-fr\n"
            "mode: transform\n"
            "input:\n"
            "  sheet: Sheet1\n"
            "  column: C\n"
            "  start_row: 3\n"
            "output:\n"
            "  column: F\n"
            "model:\n"
            "  execution_mode: api\n"
            "  provider: default-api\n"
            "  name: gpt-4.1-mini\n"
            "  concurrency: 4\n"
            "---\n\nPrompt body\n"
        )
        profile = load_task_profile(path)

        self.assertEqual(profile.input.column, "C")
        self.assertEqual(profile.input.start_row, 3)
        self.assertEqual(profile.model.provider, "default-api")
        self.assertEqual(profile.model.concurrency, 4)

    def test_missing_prompt_body_is_invalid(self) -> None:
        path = self.write_task("---\nid: empty\n---\n")

        with self.assertRaises(TaskProfileError):
            load_task_profile(path)

    def test_invalid_yaml_is_invalid(self) -> None:
        path = self.write_task("---\nid: [broken\n---\n\nPrompt\n")

        with self.assertRaises(TaskProfileError):
            load_task_profile(path)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m unittest tests.test_task_profile -v`

Expected: fails because `task_profile.py` does not exist.

- [ ] **Step 3: Implement task profile parsing**

Create dataclasses `InputConfig`, `OutputConfig`, `ModelConfig`, `TaskProfile`. Implement `load_task_profile(path)` using `yaml.safe_load`, require front matter delimited by `---`, default mode to `transform`, default input column to `source`, default output column to `target`, default `header_row=1`, `start_row=2`, `create=True`, `overwrite=True`, and reject unsupported modes.

- [ ] **Step 4: Run the task profile tests**

Run: `python -m unittest tests.test_task_profile -v`

Expected: passes.

- [ ] **Step 5: Commit**

Run:

```powershell
git add localeforge\task_profile.py tests\test_task_profile.py
git commit -m "Add markdown task profiles"
```

---

### Task 4: Provider Settings

**Files:**
- Create: `localeforge/settings.py`
- Create: `tests/test_settings_new.py`

- [ ] **Step 1: Write failing settings tests**

Create `tests/test_settings_new.py` covering:

```python
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from localeforge.settings import ProviderConfig, add_provider, load_settings, save_settings, settings_to_public_dict


class SettingsTests(unittest.TestCase):
    def test_add_provider_from_env_and_redacts_public_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            os.environ["LF_TEST_API_KEY"] = "secret-value"
            self.addCleanup(os.environ.pop, "LF_TEST_API_KEY", None)

            settings = load_settings(path)
            add_provider(
                settings,
                ProviderConfig(
                    provider_id="default-api",
                    base_url="https://api.example.com/v1",
                    api_key="",
                    api_key_env="LF_TEST_API_KEY",
                    default_model="gpt-4.1-mini",
                    models=["gpt-4.1-mini"],
                ),
                set_default=True,
            )
            save_settings(settings, path)

            reloaded = load_settings(path)
            self.assertEqual(reloaded.defaults.provider_id, "default-api")
            self.assertEqual(reloaded.providers[0].api_key, "secret-value")
            self.assertEqual(settings_to_public_dict(reloaded)["providers"][0]["api_key"], "<redacted>")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m unittest tests.test_settings_new -v`

Expected: fails because `settings.py` does not exist.

- [ ] **Step 3: Implement settings persistence**

Implement `ProviderConfig`, `SettingsDefaults`, `AppSettings`, `load_settings(path=None)`, `save_settings`, `add_provider`, `get_provider`, `resolve_api_key`, and `settings_to_public_dict`. Use `LOCALEFORGE_SETTINGS_PATH` when no explicit path is supplied. Store API keys locally but always redact in public output.

- [ ] **Step 4: Run settings tests**

Run: `python -m unittest tests.test_settings_new -v`

Expected: passes.

- [ ] **Step 5: Commit**

Run:

```powershell
git add localeforge\settings.py tests\test_settings_new.py
git commit -m "Add provider settings"
```

---

### Task 5: Input Discovery And Tabular IO

**Files:**
- Create: `localeforge/inputs.py`
- Create: `localeforge/tabular.py`
- Create: `tests/test_inputs_tabular.py`

- [ ] **Step 1: Write failing tests for work items and tabular files**

Create `tests/test_inputs_tabular.py` covering:

```python
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from openpyxl import Workbook, load_workbook

from localeforge.errors import InputOutputError
from localeforge.inputs import discover_work_items
from localeforge.tabular import load_table


class InputsAndTabularTests(unittest.TestCase):
    def test_single_file_default_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "a.csv"
            source.write_text("source\nhello\n", encoding="utf-8")

            items = discover_work_items(source)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].output.name, "a.localeforge.csv")

    def test_folder_requires_output_dir_and_mirrors_supported_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir) / "raw"
            nested = root / "fr"
            nested.mkdir(parents=True)
            (nested / "a.csv").write_text("source\nhello\n", encoding="utf-8")
            (nested / "skip.txt").write_text("nope", encoding="utf-8")

            with self.assertRaises(InputOutputError):
                discover_work_items(root)

            items = discover_work_items(root, Path(tmpdir) / "out")
            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].output, Path(tmpdir) / "out" / "fr" / "a.localeforge.csv")

    def test_csv_header_matching_and_target_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "a.csv"
            path.write_text("Source,Other\nhello,x\n,y\n", encoding="utf-8", newline="")

            table = load_table(path, sheet_name=None)
            source_col = table.resolve_column("source", create=False)
            target_col = table.resolve_column("target", create=True)

            self.assertEqual(table.get_cell(2, source_col), "hello")
            table.set_cell(2, target_col, "HELLO")
            table.save(Path(tmpdir) / "out.csv")

            with (Path(tmpdir) / "out.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))
            self.assertEqual(rows[0], ["Source", "Other", "target"])
            self.assertEqual(rows[1][2], "HELLO")

    def test_xlsx_header_matching_and_target_creation(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "a.xlsx"
            wb = Workbook()
            ws = wb.active
            ws.title = "Sheet1"
            ws["A1"] = "source"
            ws["A2"] = "hello"
            wb.save(path)

            table = load_table(path, sheet_name="Sheet1")
            source_col = table.resolve_column("source", create=False)
            target_col = table.resolve_column("target", create=True)
            table.set_cell(2, target_col, "HELLO")
            output = Path(tmpdir) / "out.xlsx"
            table.save(output)

            checked = load_workbook(output)
            try:
                self.assertEqual(checked["Sheet1"]["B1"].value, "target")
                self.assertEqual(checked["Sheet1"]["B2"].value, "HELLO")
            finally:
                checked.close()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests and verify they fail**

Run: `python -m unittest tests.test_inputs_tabular -v`

Expected: fails because `inputs.py` and `tabular.py` do not exist.

- [ ] **Step 3: Implement input discovery and tabular readers**

Implement `WorkItem`, `discover_work_items`, `with_localeforge_suffix`, `load_table`, `CsvTable`, and `XlsxTable`. Support `.csv` and `.xlsx` only. Resolve columns by case-insensitive header name, Excel letter, or 1-based integer string. Create target columns at the end when requested.

- [ ] **Step 4: Run input/tabular tests**

Run: `python -m unittest tests.test_inputs_tabular -v`

Expected: passes.

- [ ] **Step 5: Commit**

Run:

```powershell
git add localeforge\inputs.py localeforge\tabular.py tests\test_inputs_tabular.py
git commit -m "Add tabular input discovery"
```

---

### Task 6: Providers And Mode Processing

**Files:**
- Create: `localeforge/providers.py`
- Create: `localeforge/modes.py`
- Create: `tests/test_providers_modes.py`

- [ ] **Step 1: Write failing provider and mode tests**

Create `tests/test_providers_modes.py` covering:

```python
from __future__ import annotations

import unittest

from localeforge.errors import ModelProviderError
from localeforge.modes import process_model_response
from localeforge.providers import StaticModelClient


class ProvidersAndModesTests(unittest.TestCase):
    def test_static_client_returns_configured_values(self) -> None:
        client = StaticModelClient({"hello": "bonjour"})

        self.assertEqual(client.generate("Prompt", "hello"), "bonjour")

    def test_transform_strips_output_and_rejects_empty(self) -> None:
        result = process_model_response("transform", "  polished  ")
        self.assertEqual(result.primary, "polished")

        with self.assertRaises(ModelProviderError):
            process_model_response("transform", "   ")

    def test_status_json_parses_status_and_spans(self) -> None:
        result = process_model_response("status-json", '{"status":"OK","spans":["Mana"]}')

        self.assertEqual(result.primary, "OK")
        self.assertEqual(result.details, "Mana")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m unittest tests.test_providers_modes -v`

Expected: fails because the modules do not exist.

- [ ] **Step 3: Implement providers and mode processors**

Implement a `ModelClient` protocol with `ensure_available()` and `generate(system_prompt, user_text)`. Add `OpenAICompatibleClient`, `OllamaClient`, and `StaticModelClient` for tests. Implement `process_model_response(mode, raw)` returning `ProcessedResult(primary, details)`.

- [ ] **Step 4: Run provider/mode tests**

Run: `python -m unittest tests.test_providers_modes -v`

Expected: passes.

- [ ] **Step 5: Commit**

Run:

```powershell
git add localeforge\providers.py localeforge\modes.py tests\test_providers_modes.py
git commit -m "Add providers and task modes"
```

---

### Task 7: Engine Validate And Run

**Files:**
- Create: `localeforge/engine.py`
- Create: `tests/test_engine.py`

- [ ] **Step 1: Write failing engine tests**

Create `tests/test_engine.py` covering:

```python
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from localeforge.engine import RunOptions, run_task, validate_task
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
            self.assertFalse((Path(tmpdir) / "a.localeforge.csv").exists())

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
            self.assertIn("a.localeforge.csv", str(report.files[0].output))
            self.assertIn("bonjour", report.files[0].output.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify they fail**

Run: `python -m unittest tests.test_engine -v`

Expected: fails because `engine.py` does not exist.

- [ ] **Step 3: Implement validation and run orchestration**

Implement `RunOptions`, `validate_task`, and `run_task`. Validation resolves work items and columns without writing outputs or calling clients. Run processes each file, caches repeated source text per run, writes outputs, records per-file stats, and marks folder partial failures as `partial_failure`.

- [ ] **Step 4: Run engine tests**

Run: `python -m unittest tests.test_engine -v`

Expected: passes.

- [ ] **Step 5: Commit**

Run:

```powershell
git add localeforge\engine.py tests\test_engine.py
git commit -m "Add run engine"
```

---

### Task 8: CLI Commands

**Files:**
- Replace: `localeforge/cli.py`
- Create: `tests/test_cli_new.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/test_cli_new.py` covering:

```python
from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from localeforge.cli import main


class CliTests(unittest.TestCase):
    def test_provider_add_and_list_json_redacts_key(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            os.environ["LOCALEFORGE_SETTINGS_PATH"] = str(settings_path)
            os.environ["LF_KEY"] = "secret"
            self.addCleanup(os.environ.pop, "LOCALEFORGE_SETTINGS_PATH", None)
            self.addCleanup(os.environ.pop, "LF_KEY", None)

            code = main([
                "provider",
                "add",
                "default-api",
                "--base-url",
                "https://api.example.com/v1",
                "--api-key-env",
                "LF_KEY",
                "--default-model",
                "gpt-4.1-mini",
                "--set-default",
                "--json",
            ])

            self.assertEqual(code, 0)

    def test_validate_json_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            task = Path(tmpdir) / "task.md"
            task.write_text("---\nid: proofread\n---\n\nPolish.\n", encoding="utf-8")
            source = Path(tmpdir) / "a.csv"
            source.write_text("source\nhello\n", encoding="utf-8")

            code = main(["validate", "--task", str(task), "--input", str(source), "--json"])

            self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run CLI tests and verify they fail**

Run: `python -m unittest tests.test_cli_new -v`

Expected: fails because CLI handlers are not implemented.

- [ ] **Step 3: Implement CLI handlers**

Implement subcommands:

- `provider add`
- `provider list`
- `doctor`
- `validate`
- `run`

Add options from the spec. Map exceptions through `exit_code_for_error`. Write JSON to stdout when `--json` is set. Write report files when `--report` is supplied. Resolve providers from settings for real runs.

- [ ] **Step 4: Run CLI tests**

Run: `python -m unittest tests.test_cli_new -v`

Expected: passes.

- [ ] **Step 5: Commit**

Run:

```powershell
git add localeforge\cli.py tests\test_cli_new.py
git commit -m "Add agent-first CLI commands"
```

---

### Task 9: Starter Tasks, README, And Cleanup

**Files:**
- Create: `tasks/proofread.md`
- Create: `tasks/status-check.md`
- Replace: `README.md`
- Delete: old wrapper scripts, UI modules, obsolete config/model/runtime files, obsolete prompt files, obsolete tests.
- Keep or adjust: new tests only.

- [ ] **Step 1: Write README smoke test**

Add a small assertion to `tests/test_package.py`:

```python
    def test_readme_documents_new_cli(self) -> None:
        text = Path("README.md").read_text(encoding="utf-8")
        self.assertIn("localeforge run", text)
        self.assertIn("source", text)
        self.assertIn("target", text)
```

Import `Path` at the top of the file.

- [ ] **Step 2: Run the README smoke test and verify it fails**

Run: `python -m unittest tests.test_package -v`

Expected: fails until README is replaced.

- [ ] **Step 3: Add starter tasks and replace README**

Create `tasks/proofread.md` with a minimal transform task using `source` -> `target`.

Create `tasks/status-check.md` with a minimal `status-json` example.

Replace `README.md` with documentation for:

- purpose
- install
- provider setup
- `doctor`
- `validate`
- `run` for single file and folder
- task markdown schema
- report and exit codes
- privacy notes

- [ ] **Step 4: Remove obsolete code and tests**

Delete:

- `app.py`
- `check_excel_translations.py`
- `translation_checker_prompt.txt`
- `term_extractor_prompt.txt`
- `localeforge/ui/`
- `localeforge/config/`
- `localeforge/model/`
- `localeforge/runtime.py`
- `localeforge/workbook.py`
- `localeforge/rules.py`
- `localeforge/prompts.py`
- `localeforge/types.py`
- old tests that target deleted modules

Keep the new tests created in this plan.

- [ ] **Step 5: Run full test suite**

Run: `python -m unittest discover -s tests -v`

Expected: all new tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add README.md tasks tests localeforge pyproject.toml requirements.txt
git add -u
git commit -m "Replace legacy app with agent-first CLI"
```

---

### Task 10: Final Verification

**Files:**
- Modify as needed based on verification failures.

- [ ] **Step 1: Run full tests**

Run: `python -m unittest discover -s tests -v`

Expected: all tests pass.

- [ ] **Step 2: Run CLI help smoke checks**

Run:

```powershell
python -m localeforge --help
python -m localeforge run --help
python -m localeforge validate --help
python -m localeforge provider --help
```

Expected: each command exits `0` and prints help.

- [ ] **Step 3: Run a real local CSV transform with static test path if supported by tests**

Use the engine tests as the real transform verification. Do not call an external model during final verification.

- [ ] **Step 4: Inspect git status**

Run: `git status --short`

Expected: only intentional changes are present.

- [ ] **Step 5: Commit any final fixes**

Run:

```powershell
git add -A
git commit -m "Stabilize agent-first CLI"
```

Skip this commit if there are no changes after Task 9.

---

## Self-Review Notes

- Spec coverage: tasks cover packaging, task markdown, provider settings, input discovery, CSV/XLSX tabular IO, transform/status-json modes, reports, exit codes, CLI commands, starter tasks, README, and legacy cleanup.
- Placeholder scan: no `TBD`, `TODO`, or open implementation placeholders remain.
- Type consistency: `TaskProfile`, `RunOptions`, `RunReport`, `ModelClient`, `ProcessedResult`, and provider settings names are used consistently across tasks.
