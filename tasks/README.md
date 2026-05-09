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

The model must return exactly one JSON object. Missing or unknown fields are response validation errors and are retried.
