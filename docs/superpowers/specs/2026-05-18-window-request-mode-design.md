# Window Request Mode Design

Date: 2026-05-18
Project: LocaleForge

## Goal

Add a second request scheduling mode for table tasks whose adjacent rows are strongly related. Existing behavior remains the default: one unique non-empty source cell produces one model request, with optional parallelism from `--concurrency`. The new mode, named `window`, sends ordered groups of rows together with nearby context and expects one structured response item per current row.

The task business mode stays unchanged. `mode: transform` and `mode: status-json` must both work with either request scheduling mode.

## CLI Contract

`localeforge run` and `localeforge validate` gain:

```text
--request-mode concurrent|window
--window-size N
```

Rules:

- `--request-mode` defaults to `concurrent`.
- `concurrent` preserves current behavior exactly.
- `window` processes files sequentially by row order.
- `--window-size` defaults to `5` and must be a positive integer.
- `--window-size` is valid only with `--request-mode window`; using it with `concurrent` is a usage/configuration error.
- `--concurrency` applies only to `concurrent`; using it with `window` is a usage/configuration error.

Example:

```powershell
localeforge run --task tasks/review.md --input data/source.csv --request-mode window --window-size 5 --json
```

## Engine Behavior

`RunOptions` stores `request_mode` and `window_size`. `_run_file()` dispatches to one of two paths:

- `concurrent`: the existing implementation, including source de-duplication, cache reuse, and bounded parallel model calls.
- `window`: a new ordered path that batches non-empty source rows into windows.

The `window` path does not read existing target cells. It assumes target cells are empty. Previous targets in the prompt come only from rows generated and validated earlier in the same run.

Empty source rows are counted as `rows_empty`, are not included in window requests, and do not require model output.

## Window Request Shape

For each current window of up to `window_size` non-empty source rows, the user message is a JSON object:

```json
{
  "previous": [
    {"row": 2, "source": "Previous source", "target": "Previous target"}
  ],
  "current": [
    {"row": 7, "source": "Current source"}
  ],
  "next": [
    {"row": 12, "source": "Next source"}
  ]
}
```

Window selection:

- `previous` contains up to `window_size` immediately preceding non-empty source rows that already have validated outputs from this run.
- `current` contains up to `window_size` non-empty source rows to process now.
- `next` contains up to `window_size` immediately following non-empty source rows. It includes source only.

The system prompt is the task prompt plus fixed LocaleForge instructions for window mode. The fixed instructions tell the model to return only a JSON array and to output results only for rows listed in `current`.

## Response Contract

For `mode: transform`, the model returns:

```json
[
  {"row": 7, "target": "Generated target"}
]
```

For `mode: status-json`, the task must declare `output.fields`, and the model returns one object per current row:

```json
[
  {
    "row": 7,
    "status": "OK",
    "problem_review": "",
    "better_french": "Polished text"
  }
]
```

The response parser validates:

- The response is a JSON array.
- Array length equals the number of current rows.
- Each item is an object.
- Each item has a `row` value.
- Each row belongs to `current`.
- Rows are not missing, duplicated, or unknown.
- `transform` items have a non-empty `target` and no extra output fields.
- `status-json` items match declared `output.fields` exactly, with no missing or unknown fields.

After validation, each item is converted to the existing `ProcessedResult` shape and written through the existing output writers.

## Retries and Reporting

`window` mode retries an entire window up to `--max-attempts`. Retry prompts include the previous validation/provider error, mirroring the current single-cell retry behavior.

Reporting:

- `rows_processed` counts rows successfully generated.
- `rows_empty` counts empty source rows.
- `model_calls` counts window request attempts.
- `cache_hits` is always `0` in `window` mode.

For a single input file, unrecoverable window failure raises the same provider/input-output errors currently used by `run_task`. For folder input, existing partial failure behavior remains.

## Validation

`validate` should catch configuration and contract issues that do not require model calls:

- Invalid `request_mode`.
- Non-positive `window_size`.
- `--window-size` used with `concurrent`.
- `--concurrency` used with `window`.
- `window` plus `status-json` without declared `output.fields`.

It should still validate input/output files and output columns using the existing table checks.

## Tests

Add focused tests for:

- CLI defaults to `request_mode="concurrent"` and preserves existing behavior.
- CLI accepts `--request-mode window --window-size 5`.
- CLI rejects `--window-size` with `concurrent`.
- CLI rejects `--concurrency` with `window`.
- `window + transform` writes multiple targets from one JSON array response.
- `window + status-json` writes declared fields from one JSON array response.
- The second window receives previous source/target context and next source context.
- Invalid window responses retry the whole window.
- Row mismatch, duplicate row, missing field, and extra field validation errors are not written to output.

## Non-Goals

- No fallback to pre-existing target cells.
- No de-duplication or cache reuse in `window` mode.
- No parallel requests in `window` mode.
- No task-file-level request mode setting in the first version.
- No support for `status-json` window mode without declared `output.fields`.
