# LocaleForge

LocaleForge is an agent-first CLI for running LLM tasks over Excel and CSV files. It is designed as middleware for localization and content workflows: read text from a `source` column, process it with a Markdown-defined task, and write the result to a `target` column.

The CLI supports one file or a whole folder with the same command.

Agents should start with [AGENTS.md](AGENTS.md). Provider setup examples live in [docs/provider-configuration-example.md](docs/provider-configuration-example.md).

## Install

```powershell
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Configure A Provider Once

Use an environment variable for the API key so secrets do not land in shell history:

```powershell
$env:OPENAI_API_KEY="sk-..."
localeforge provider add default-api `
  --base-url https://api.example.com/v1 `
  --api-key-env OPENAI_API_KEY `
  --default-model gpt-4.1-mini `
  --set-default
```

After this, tasks and workflow calls do not need to repeat the API key or base URL.

Check the environment:

```powershell
localeforge doctor --json
```

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

Minimal transform task:

```markdown
---
id: proofread
mode: transform
---

Polish the user text.
Return only the polished text. Do not explain.
```

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

LocaleForge writes new output files and leaves source files unchanged. Input text is sent only to the selected model provider. API keys are stored in local settings and are redacted from reports and JSON output.
