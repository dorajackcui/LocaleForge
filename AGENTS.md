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

Resume an interrupted run by repeating the same run command with `--resume`:

```powershell
localeforge run --task tasks/rewrite.md --input data/raw --output-dir data/out --report reports/run.json --resume --json
```

LocaleForge saves snapshots under `.localeforge-snapshots` next to the output files. Completed files in a folder run are skipped during `--resume`; incomplete files continue from their snapshots. If a snapshot exists and `--resume` is not used, LocaleForge stops before model calls. Use `--force` only when you want to discard old snapshots and rerun outputs.

Use different columns:

```powershell
localeforge run --task tasks/rewrite.md --input data/source.xlsx --input-col C --output-col F --json
```

Add temporary run-only guidance:

```powershell
localeforge run --task tasks/rewrite.md --input data/source.csv --tips "Keep product names unchanged." --json
```

Use window request mode for files where nearby rows depend on each other. Prefer declaring it in the task front matter:

```yaml
request:
  mode: window
  window_size: 5
```

Then validate and run normally:

```powershell
localeforge validate --task tasks/review.md --input data/source.csv --json
localeforge run --task tasks/review.md --input data/source.csv --json
```

Window mode processes rows sequentially in windows. It does not use `--concurrency`, de-duplication, or cache hits. For `status-json` tasks, `output.fields` must be declared. Use `--request-mode` or `--window-size` only for temporary run-level overrides.

## Output Contract

With `--json`, stdout is a run report. Parse stdout as JSON.

```json
{
  "status": "success",
  "request": {
    "mode": "concurrent",
    "window_size": 5
  },
  "resume": {
    "enabled": false,
    "rows_resumed": 0,
    "files_skipped": 0
  },
  "files": [
    {
      "input": "data/source.csv",
      "output": "data/source_rewrite.csv",
      "rows_processed": 10,
      "rows_empty": 1,
      "model_calls": 8,
      "cache_hits": 2,
      "rows_resumed": 0,
      "snapshot": "data/.localeforge-snapshots/source_rewrite.csv.snapshot.json",
      "skipped_existing_output": false
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
- Omit `request` metadata to use `concurrent` mode.
- Use task metadata `request.mode: window` and `request.window_size: 5` when adjacent rows need shared context.
- CLI `--request-mode` and `--window-size` override task metadata for one run.
- Do not combine `--concurrency` with effective `window` mode.
- Do not combine `--window-size` with the default `concurrent` request mode.
- Use `--tips` for one-off instructions; do not edit a task file for one batch.
- Use `--resume` to continue an interrupted run; repeat the same task/input/output command.
- Use `--force` to overwrite outputs and discard matching snapshots.
- For folder runs, `--output-dir` must be outside the input directory.
- Output and report files must not already exist unless `--force` is used.
- `--report` must not point at an input or output table file.
- Task-level `model` takes precedence over `OPENAI_MODEL` from `.env`.
- Tasks without `model` use the configured default model from `.env` or the saved API provider.
