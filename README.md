# LocaleForge

LocaleForge is an agent-first CLI for running Markdown-defined LLM tasks over CSV and Excel tables.

By default, it reads text from a table column, calls the configured model once per unique non-empty value, and writes a new output table. The source file is never modified.

## Start Here

- [AGENTS.md](AGENTS.md) is the operational runbook: configuration checks, validation, run commands, JSON output, exit codes, and batch rules.
- [tasks/README.md](tasks/README.md) lists the supported tasks and explains which template to copy for new tasks.
- [.env.example](.env.example) shows the API provider settings expected by the CLI.

## Install

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
```

LocaleForge requires Python 3.11 or newer.

## Configure

Copy the example environment file and fill in your API provider settings:

```powershell
Copy-Item .env.example .env
localeforge doctor
```

Keep API keys in `.env`; do not put secrets in task files or command arguments.

## Tasks

Tasks are Markdown files with YAML front matter. The front matter describes stable configuration, and the Markdown body is the system prompt sent to the model.

Use the existing runnable tasks for common flows:

- `tasks/rewrite.md` rewrites one source cell into one target cell.
- `tasks/review.md` reviews one source cell into structured output columns.

Default request mode processes one unique source value per model request and may run requests concurrently:

```powershell
localeforge run --task tasks/rewrite.md --input data/source.csv --json
```

For adjacent rows that need shared context, use window request mode:

```powershell
localeforge run --task tasks/review.md --input data/source.csv --request-mode window --window-size 5 --json
```

Window mode sends previous generated results, current source rows, and next source rows in each request. It expects the model to return one JSON array item per current row.

Use the templates when creating a new task:

- `tasks/example-transform.md` for text-in/text-out work.
- `tasks/example-status-json.md` for structured JSON output.

## Project Layout

```text
localeforge/       CLI package
tasks/            runnable tasks and templates
tests/            unit and integration tests
AGENTS.md         agent runbook
.env.example      local configuration template
```

## Guarantees

LocaleForge writes new output files instead of editing source tables in place. Input text is sent only to the selected model provider, and provider secrets stay in local environment configuration.
