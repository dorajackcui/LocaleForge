# LocaleForge Tasks

This folder contains runnable tasks and copyable task templates.

## Runnable Tasks

### `tasks/rewrite.md`

- mode: `transform`
- model: `gpt-5.5`
- input: reads `source`
- output: writes rewritten French text to `target`
- output file suffix: `_rewrite`

Use it when the batch needs a natural French rewrite.

```powershell
localeforge run --task tasks/rewrite.md --input data/source.csv --json
```

Expected table output:

```text
source,target
"Original text","Rewritten French text"
```

### `tasks/review.md`

- mode: `status-json`
- model: `gpt-5.5`
- input: reads `source`
- output fields: `status`, `problem_review`, `better_french`
- output file suffix: `_review`

Use it when the batch needs a native-style French review plus a polished replacement.

```powershell
localeforge run --task tasks/review.md --input data/source.csv --json
```

Expected table output:

```text
source,status,problem_review,better_french
"Draft French text","Problem","Brief issue in French","Polished French text"
```

`status` is `OK` or `Problem`. `better_french` contains the final text to use.

## Request Modes

By default, LocaleForge uses `--request-mode concurrent`: each unique non-empty source value is requested once, and `--concurrency` controls parallel model calls.

Use `--request-mode window --window-size 5` when adjacent rows need shared context. Window mode sends previous generated results, current rows, and next source rows together. It requires the model to return a JSON array with one object per current row.

For `status-json` tasks in window mode, declare stable `output.fields` so LocaleForge can validate each returned object.

## Templates

### `tasks/example-transform.md`

Copy this when one input cell should produce one output cell.

### `tasks/example-status-json.md`

Copy this when one input cell should produce multiple structured output columns.

Declare stable fields:

```yaml
mode: status-json
output:
  fields:
    - status
    - reason
    - suggestion
```

In concurrent mode, the model must return exactly one JSON object. In window mode, the model must return a JSON array with one object per current row. Missing or unknown fields are response validation errors and are retried.
