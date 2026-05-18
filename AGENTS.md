# LocaleForge Agent Guide

Use LocaleForge when you need to run one Markdown-defined LLM task over `.csv` or `.xlsx` tables.

## What It Does

By default, LocaleForge reads text from a table column, calls the configured model once per unique non-empty cell, and writes a new output table. The source file is never modified.

Default table contract:

- input column: `source`
- output column: `target`
- header row: `1`
- first data row: `2`

Default output name:

```text
data/source.csv + tasks/rewrite.md -> data/source_rewrite.csv
data/raw/a.xlsx + tasks/review.md -> data/out/a_review.xlsx
```

## Before Running

Check configuration first:

```powershell
localeforge doctor
```

Expected `.env` keys:

```text
OPENAI_BASE_URL=...
OPENAI_API_KEY=...
OPENAI_MODEL=...
LOCALEFORGE_CONCURRENCY=4
LOCALEFORGE_MAX_ATTEMPTS=2
```

Do not put API keys in task files or command arguments.

## Workflow

Validate before any model call:

```powershell
localeforge validate --task tasks/rewrite.md --input data/source.csv --json
```

Run one file:

```powershell
localeforge run --task tasks/rewrite.md --input data/source.csv --json
```

Run a folder:

```powershell
localeforge run --task tasks/rewrite.md --input data/raw --output-dir data/out --report reports/run.json --json
```

Use different columns:

```powershell
localeforge run --task tasks/rewrite.md --input data/source.xlsx --input-col C --output-col F --json
```

Add temporary run-only guidance:

```powershell
localeforge run --task tasks/rewrite.md --input data/source.csv --tips "Keep product names unchanged." --json
```

Use window request mode for files where nearby rows depend on each other:

```powershell
localeforge validate --task tasks/review.md --input data/source.csv --request-mode window --window-size 5 --json
localeforge run --task tasks/review.md --input data/source.csv --request-mode window --window-size 5 --json
```

Window mode processes rows sequentially in windows. It does not use `--concurrency`, de-duplication, or cache hits. For `status-json` tasks, `output.fields` must be declared.

## Output Contract

With `--json`, stdout is a run report. Parse stdout as JSON.

```json
{
  "status": "success",
  "files": [
    {
      "input": "data/source.csv",
      "output": "data/source_rewrite.csv",
      "rows_processed": 10,
      "rows_empty": 1,
      "model_calls": 8,
      "cache_hits": 2
    }
  ]
}
```

Progress and diagnostics go to stderr.

Exit codes:

```text
0 success
1 usage or configuration error
2 input or output file error
3 model or provider error
4 partial failure in folder batch
```

## Task Selection

Current supported tasks are documented in [tasks/README.md](tasks/README.md).

Use:

- `tasks/rewrite.md` to rewrite one source cell into one target cell.
- `tasks/review.md` to review one source cell into structured columns.
- `tasks/example-transform.md` as a template for new text-in/text-out tasks.
- `tasks/example-status-json.md` as a template for new structured output tasks.

## Rules

- Always run `validate` before `run`.
- `--request-mode concurrent` is the default request mode.
- Use `--request-mode window --window-size 5` when adjacent rows need shared context.
- Do not combine `--concurrency` with `--request-mode window`.
- Do not combine `--window-size` with the default `concurrent` request mode.
- Use `--tips` for one-off instructions; do not edit a task file for one batch.
- For folder runs, `--output-dir` must be outside the input directory.
- Output and report files must not already exist unless `--force` is used.
- `--report` must not point at an input or output table file.
- Task-level `model` takes precedence over `OPENAI_MODEL` from `.env`.
- Tasks without `model` use the configured default model from `.env` or the saved API provider.
