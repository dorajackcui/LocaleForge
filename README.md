# LocaleForge

LocaleForge is an agent-first CLI for running LLM tasks over Excel and CSV files. It is designed as middleware for localization and content workflows: read text from a `source` column, process it with a Markdown-defined task, and write the result to a `target` column.

The CLI supports one file or a whole folder with the same command.

Agents should start with [AGENTS.md](AGENTS.md). Copy [.env.example](.env.example) to `.env` for local provider configuration.

## Install

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Configure Once

Put the base URL, API key, and default model in a local `.env` file. After that, repeated runs do not need provider details:

```powershell
Copy-Item .env.example .env
# Edit .env and set OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL.
```

If `.env` contains `OPENAI_BASE_URL` and `OPENAI_API_KEY`, LocaleForge automatically uses an API provider named `env`. `OPENAI_MODEL` becomes the default model for tasks that do not specify one.

Check the environment:

```powershell
localeforge doctor
```

Use `localeforge doctor --json` only when another tool needs machine-readable output.

`localeforge provider add` is optional. Use it only when you need named providers or persisted defaults beyond the simple `.env` path.

## Run

Single CSV or Excel file:

```powershell
localeforge run --task tasks/proofread.md --input data/source.csv
localeforge run --task tasks/proofread.md --input data/source.xlsx
```

Folder batch:

```powershell
localeforge run --task tasks/proofread.md --input data/raw --output-dir data/out
```

Directory input recursively scans `.csv` and `.xlsx` files and mirrors the structure under `--output-dir`.

## Validate Before Running

`validate` checks a task/input combination without calling the model or writing output files:

```powershell
localeforge validate --task tasks/proofread.md --input data/raw --output-dir data/out --json
```

It checks the task schema, files, worksheets, source column, target column behavior, output path shape, and provider resolution.

## Task Files

A task is one Markdown file. YAML front matter stores durable configuration; the Markdown body is the system prompt.

Use [tasks/example-task.md](tasks/example-task.md) as the copyable template when creating a new task.

Minimal transform task:

```markdown
---
id: proofread
mode: transform
model: gpt-5.5
---

Polish the user text.
Return only the polished text. Do not explain.
```

`model` is optional. Omit it to use `OPENAI_MODEL` from `.env`; set it when a task needs a specific model.

Default table contract:

- input column: `source`
- output column: `target`
- header row: `1`
- first data row: `2`

Column matching is case-insensitive. The `target` column is created when missing.

Override columns only when a file uses a different schema:

```powershell
localeforge run --task tasks/proofread.md --input data/a.xlsx --input-col C --output-col F
```

## Task Modes

`transform` is the default mode. The model returns final text, and LocaleForge writes it to `target`.

`status-json` is for QA, extraction, and classification tasks. The model returns:

```json
{"status":"OK","spans":[]}
```

The `status` value is written to `target`. If `output.details_column` is configured, `spans` are joined with ` | ` and written there.

## Reports And JSON

Use `--json` for machine-readable stdout and `--report` for a JSON file:

```powershell
localeforge run `
  --task tasks/proofread.md `
  --input data/raw `
  --output-dir data/out `
  --report reports/run.json `
  --json
```

Exit codes:

```text
0 success
1 usage or configuration error
2 input or output file error
3 model or provider error
4 partial failure in folder batch
```

## Privacy

LocaleForge writes new output files and leaves source files unchanged. Input text is sent only to the selected model provider. Secrets stay in local `.env` files; provider settings store env var names and are redacted from reports and JSON output.
