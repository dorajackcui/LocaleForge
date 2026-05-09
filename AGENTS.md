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
localeforge doctor
```

Use `localeforge doctor --json` only if you need to parse the result programmatically.

Expected default credential shape:

```text
copy .env.example to .env
.env contains OPENAI_BASE_URL=...
.env contains OPENAI_API_KEY=...
.env contains OPENAI_MODEL=...
task files do not contain secrets
```

Configure once:

```powershell
Copy-Item .env.example .env
# Edit .env and set OPENAI_BASE_URL, OPENAI_API_KEY, and OPENAI_MODEL.
```

When `.env` is present, LocaleForge automatically uses an API provider named `env`. Do not put API keys in task files or command arguments.

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
localeforge run --task tasks/proofread.md --input data/raw --output-dir data/out --report reports/run.json --json --progress jsonl
```

If a file uses different columns:

```powershell
localeforge run --task tasks/proofread.md --input data/source.xlsx --input-col C --output-col F --json
```

## Task Files

A task is a Markdown file with YAML front matter and a prompt body.

When creating a new task, copy [tasks/example-task.md](tasks/example-task.md) and change:

- `id`: stable task identifier, lowercase with hyphens
- `description`: short human summary
- `input.column` and `output.column`: omit or keep `source` and `target` for the default schema
- `model`: optional model name shorthand, for example `model: gpt-5.5`
- `model.concurrency`: optional max concurrent model requests when using nested model config
- prompt body: the full system prompt sent to the model

Most tasks should omit `model` and use `OPENAI_MODEL` from `.env`. Set `model` only when a task needs a specific model.

```markdown
---
id: proofread
mode: transform
model: gpt-5.5
---

Polish the user text.
Return only the polished text. Do not explain.
```

Use `transform` for text-in/text-out tasks. Use `status-json` only when the task needs structured status and spans.

Do not put API keys in task files.

## Progress And Concurrency

Progress is emitted to stderr, never stdout. This keeps `--json` stdout parseable.

- `--progress auto`: default; text for human runs, none for `--json`
- `--progress text`: human-readable progress on stderr
- `--progress jsonl`: machine-readable progress events on stderr
- `--progress none`: disable progress

Use `--concurrency N` for per-run model request concurrency. The task front matter can also set:

```yaml
model:
  name: gpt-5.5
  concurrency: 4
```

## Exit Codes

```text
0 success
1 usage or configuration error
2 input or output file error
3 model or provider error
4 partial failure in folder batch
```

When `--json` is used, parse stdout as JSON. Treat human stderr as diagnostic text only.
