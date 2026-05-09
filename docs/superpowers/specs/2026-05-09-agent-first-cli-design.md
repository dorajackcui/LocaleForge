# Agent-First CLI Redesign

Date: 2026-05-09

## Summary

LocaleForge will become a clean-slate, agent-first CLI for batch processing Excel and CSV files with LLM tasks. The new product is a tabular text transformation middleware: it reads a `source` column from one file or a folder of files, sends each row through a task prompt and model provider, and writes the result to a `target` column.

The previous desktop UI, wrapper scripts, built-in Python task registry, and prompt text files are reference material only. The new CLI does not need to preserve old commands or behavior.

## Goals

- Make the CLI simple for agents and workflows to call.
- Support both single-file and folder-batch execution through one `run` command.
- Use Markdown task files as the durable task unit.
- Store provider credentials and defaults once, so repeated runs do not need API details.
- Support `.xlsx` and `.csv` with one tabular processing model.
- Default to direct text transformation while allowing structured task modes for QA or extraction.
- Produce stable machine-readable output, reports, and exit codes.
- Keep internal modules small, testable, and easy to extend.

## Non-Goals

- Preserve the old `check_excel_translations.py` command.
- Preserve the Tk desktop UI.
- Keep `TASK_CONFIGS` as the task source of truth.
- Maintain compatibility with root-level prompt `.txt` files.
- Build a general workflow engine or plugin system in the first version.

## Product Model

LocaleForge has five core concepts:

- Task: a Markdown file with YAML front matter and a system prompt body.
- Provider: a saved OpenAI-compatible or local model endpoint.
- Input: one `.xlsx`, one `.csv`, or a directory containing those files.
- Output: a new file with processed rows written to the target column.
- Report: machine-readable execution metadata for agents and workflows.

The default tabular contract is:

- Input column: `source`
- Output column: `target`
- Header row: `1`
- First data row: `2`

Column matching is case-insensitive. The output column is created when missing.

## CLI Surface

The main execution command is:

```powershell
localeforge run --task tasks/proofread.md --input data/source.xlsx
localeforge run --task tasks/proofread.md --input data/source.csv
localeforge run --task tasks/proofread.md --input data/raw --output-dir data/out
```

`--input` accepts either a file or a directory. If it is a directory, LocaleForge recursively scans `.xlsx` and `.csv` files and mirrors the folder structure under `--output-dir`.

Single-file output defaults to a sibling file:

```text
a.xlsx -> a.localeforge.xlsx
a.csv  -> a.localeforge.csv
```

Folder-batch output defaults to mirrored paths under `--output-dir`:

```text
data/raw/fr/a.xlsx   -> data/out/fr/a.localeforge.xlsx
data/raw/ui/menu.csv -> data/out/ui/menu.localeforge.csv
```

`--output-dir` is required for directory input. This keeps folder runs explicit and avoids accidental writes into the source tree.

Useful execution options:

```powershell
localeforge run `
  --task tasks/proofread.md `
  --input data/raw `
  --output-dir data/out `
  --report reports/run.json `
  --json
```

Override options:

```powershell
localeforge run --task tasks/proofread.md --input a.xlsx --input-col C --output-col F
localeforge run --task tasks/proofread.md --input a.xlsx --model gpt-4.1-mini
localeforge run --task tasks/proofread.md --input a.xlsx --provider default-api
```

Support commands:

```powershell
localeforge provider add default-api --base-url https://api.example.com/v1 --api-key-env OPENAI_API_KEY --default-model gpt-4.1-mini --set-default
localeforge provider list --json
localeforge doctor --json
localeforge validate --task tasks/proofread.md --input data/raw --output-dir data/out --json
```

`doctor` checks global runtime health: settings readability, default provider, model connectivity, and dependency readiness.

`validate` checks one task/input run without calling a model or writing output: task schema, files, sheet names, source column, target column behavior, output path safety, provider resolution, and report path validity.

## Task Markdown Format

A minimal task:

```markdown
---
id: proofread
mode: transform
---

Polish the user text.
Return only the polished text. Do not explain.
```

A fuller task:

```markdown
---
id: proofread-fr
mode: transform
description: Polish French localization text.

input:
  sheet: Sheet1
  column: source
  header_row: 1
  start_row: 2

output:
  column: target
  create: true
  overwrite: true

model:
  execution_mode: api
  provider: default-api
  name: gpt-4.1-mini
  concurrency: 4
---

You are a localization proofreader.

Rewrite the user text into polished French.
Return only the rewritten text. Do not explain.
```

Task prompt body is the system prompt. The row text is sent as the user message in chat-style providers. For local completion-style providers, the renderer builds an equivalent prompt with the task body and row input.

The implementation should parse front matter with `PyYAML` rather than an ad hoc parser. Invalid YAML is a task schema error.

Configuration precedence is:

```text
CLI arguments > task front matter > saved settings > built-in defaults
```

This lets repeated agent calls stay short after the provider is configured:

```powershell
localeforge run --task tasks/proofread.md --input data/raw --output-dir data/out
```

## Task Modes

### transform

`transform` is the default mode.

Input:

- One row value from the source column.

Model contract:

- Return only the final output text.

Output:

- The returned text is stripped of surrounding whitespace and written to the target column.
- Empty model responses are treated as model errors, not successful empty output.

This mode supports polishing, proofreading, translation, rewriting, normalization, summarization, and similar row-by-row transformations.

### status-json

`status-json` is a first-class structured mode for QA, extraction, classification, and audits.

Input:

- One row value from the source column.

Model contract:

```json
{
  "status": "OK",
  "spans": []
}
```

Output:

- `status` is written to the configured output column.
- `spans` are written to a details column when configured.
- Future task-specific summaries can be generated by structured processors.

This mode replaces the old hardcoded English-check and term-extraction behavior with task-file-driven configuration.

## Provider Configuration

Provider settings are persisted under:

```text
~/.localeforge/settings.json
```

The CLI supports a one-time setup flow:

```powershell
localeforge provider add default-api `
  --base-url https://api.example.com/v1 `
  --api-key-env OPENAI_API_KEY `
  --default-model gpt-4.1-mini `
  --set-default
```

`provider add` also supports direct `--api-key` input for automation, but `--api-key-env` is the recommended path because it avoids putting secrets in shell history.

Saved settings include:

- default execution mode
- default provider id
- default model
- base URL
- API key
- tested model list
- concurrency defaults

Tasks do not need to repeat provider details unless they intentionally require a specific model or provider.

The CLI must not print API keys in human logs, JSON output, reports, or error messages.

## Data Flow

1. Parse CLI arguments.
2. Load saved settings.
3. Load and validate the Markdown task.
4. Resolve effective configuration through precedence rules.
5. Resolve input into one or more work items.
6. Validate output paths and tabular contracts.
7. Create the model client.
8. For each work item:
   - read `.xlsx` or `.csv`
   - resolve source and target columns
   - iterate rows from `start_row`
   - skip empty values and record them
   - cache repeated source text within the run
   - call the model for unique non-empty text
   - parse mode-specific response
   - write output rows
   - save the output file
9. Write the report file when requested.
10. Print human output or JSON summary.
11. Exit with a stable code.

Folder runs continue after per-file failures and return partial-failure status when any file fails.

## Report Format

Reports are JSON and stable enough for workflows to parse.

Example:

```json
{
  "status": "success",
  "task": {
    "id": "proofread-fr",
    "mode": "transform",
    "path": "tasks/proofread.md"
  },
  "model": {
    "execution_mode": "api",
    "provider": "default-api",
    "name": "gpt-4.1-mini"
  },
  "files": [
    {
      "status": "success",
      "input": "data/raw/a.xlsx",
      "output": "data/out/a.localeforge.xlsx",
      "rows_total": 120,
      "rows_processed": 118,
      "rows_empty": 2,
      "model_calls": 80,
      "cache_hits": 38,
      "errors": []
    }
  ],
  "errors": []
}
```

`--json` prints a compact version of the same result to stdout. Human logs go to stderr when JSON stdout is requested.

## Exit Codes

```text
0 success
1 usage or configuration error
2 input or output file error
3 model or provider error
4 partial failure in folder batch
```

The report gives full details. Exit codes are intentionally coarse so shell workflows can make simple decisions.

## Internal Architecture

The implementation should prefer small modules with clear interfaces:

```text
localeforge.cli
  Argument parsing, command dispatch, JSON/human output, exit-code mapping.

localeforge.task_profile
  Markdown front matter parsing, schema validation, prompt body loading.

localeforge.settings
  Provider settings, defaults, credential persistence, provider mutations.

localeforge.providers
  OpenAI-compatible and local model clients behind one interface.

localeforge.inputs
  File/folder input discovery and work item creation.

localeforge.tabular
  CSV/XLSX readers and writers, header matching, column creation.

localeforge.engine
  Run orchestration, caching, concurrency, per-file execution.

localeforge.modes
  transform and status-json processors.

localeforge.report
  Report dataclasses, JSON serialization, status aggregation.

localeforge.errors
  Typed errors mapped to exit codes.
```

Old files may be deleted or rewritten if that makes the new design simpler. Existing code can be copied or adapted where useful, especially provider clients and workbook access, but should not dictate public API shape.

First-version runtime dependencies:

- `openpyxl` for `.xlsx`
- `requests` for HTTP providers
- `PyYAML` for Markdown front matter

## Error Handling

Errors should be typed and user-actionable:

- Task schema errors explain the invalid field and expected shape.
- Missing input paths identify the missing path.
- Missing source columns list available headers.
- Unsafe output paths explain what would be overwritten or why a directory is required.
- Provider errors distinguish missing configuration, connectivity failure, and missing model.
- Model parsing errors include a short sanitized response excerpt.

Batch mode records per-file errors and continues when possible.

## Security And Privacy

- API keys are stored only in local settings.
- API keys are never emitted in reports or logs.
- Input file contents are sent only to the selected provider.
- `doctor --json` must redact sensitive fields.
- The default behavior writes new output files and leaves sources unchanged.

## Testing Strategy

Unit tests:

- Task Markdown parser accepts minimal and full tasks.
- Task parser rejects missing prompt bodies and invalid front matter.
- Configuration precedence resolves CLI over task over settings over defaults.
- Provider settings can add, list, set default, and redact API keys.
- Column matching handles `source`, `Source`, Excel letters, and numeric indexes.
- Target column creation works for CSV and XLSX.
- Transform mode writes model text to target.
- Status-json mode parses and writes structured output.
- Report serialization is stable.
- Errors map to intended exit codes.

Integration tests:

- `validate` succeeds without calling a model.
- `run` processes one CSV file.
- `run` processes one XLSX file.
- `run` processes a folder and mirrors outputs.
- Folder run continues after one bad file and returns exit code `4`.
- `--json` emits machine-readable stdout and keeps human logs off stdout.

## Migration Plan

This is a clean-slate branch, so migration means replacing the old product surface:

1. Add packaging metadata and a console entry point for `localeforge`.
2. Implement task profile loading and validation.
3. Implement settings and provider commands.
4. Implement tabular CSV/XLSX read-write layer.
5. Implement `validate`, `doctor`, and `run`.
6. Add transform mode.
7. Add status-json mode.
8. Add report generation and stable exit-code mapping.
9. Replace README with the new CLI-first documentation.
10. Remove obsolete UI, wrappers, hardcoded task registry, and root prompt text files.

## First Version Decisions

- Support `.xlsx` and `.csv` only.
- Do not support `.xlsm` in the first version.
- Require `--output-dir` for directory input.
- Default `output.overwrite` to true because the tool writes new output files.
- Put reusable starter tasks under `tasks/` so agents can discover and copy them easily.
