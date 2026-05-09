# LocaleForge Agent Entry

Use this file as the quick-start contract when another agent needs to run LocaleForge.

## What This Tool Does

LocaleForge runs Markdown-defined LLM tasks over `.csv` and `.xlsx` files.

Default table contract:

- read input text from `source`
- write output text to `target`
- header row is row `1`
- first data row is row `2`

The source file is not modified. LocaleForge writes new `.localeforge.csv` or `.localeforge.xlsx` files.

## First Check

Before running a task, check the environment:

```powershell
localeforge doctor --json
```

Expected default credential shape:

```text
copy .env.example to .env
.env contains OPENAI_API_KEY=...
provider settings reference OPENAI_API_KEY by name
task files do not contain secrets
```

Configure provider once:

```powershell
Copy-Item .env.example .env
# Edit .env and set OPENAI_API_KEY.

localeforge provider add default-api `
  --base-url https://api.example.com/v1 `
  --api-key-env OPENAI_API_KEY `
  --default-model gpt-4.1-mini `
  --set-default `
  --json
```

## Validate Before Run

For a single file:

```powershell
localeforge validate --task tasks/proofread.md --input data/source.csv --json
```

For a folder:

```powershell
localeforge validate --task tasks/proofread.md --input data/raw --output-dir data/out --json
```

`validate` must not call the model or write output files. Use it before spending API calls.

## Run

Single file:

```powershell
localeforge run --task tasks/proofread.md --input data/source.csv --json
```

Folder batch:

```powershell
localeforge run --task tasks/proofread.md --input data/raw --output-dir data/out --report reports/run.json --json
```

If a file uses different columns:

```powershell
localeforge run --task tasks/proofread.md --input data/source.xlsx --input-col C --output-col F --json
```

## Task Files

A task is a Markdown file with YAML front matter and a prompt body.

```markdown
---
id: proofread
mode: transform
---

Polish the user text.
Return only the polished text. Do not explain.
```

Use `transform` for text-in/text-out tasks. Use `status-json` only when the task needs structured status and spans.

Do not put API keys in task files.

## Exit Codes

```text
0 success
1 usage or configuration error
2 input or output file error
3 model or provider error
4 partial failure in folder batch
```

When `--json` is used, parse stdout as JSON. Treat human stderr as diagnostic text only.
