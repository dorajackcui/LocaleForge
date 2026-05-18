---
id: example-status-json
mode: status-json
description: Minimal structured JSON task template.

# Default table contract.
input:
  column: source
  header_row: 1
  start_row: 2

# Each declared field is written to a column with the same name.
# Use output.columns only when a field should be written to a different column.
output:
  create: true
  overwrite: true
  fields:
    - status
    - category
    - reason
    - suggestion
  # columns:
  #   status: review_status
  #   reason: review_reason

# Optional. Omit this field to use OPENAI_MODEL from .env.
# model: gpt-5.5

# Optional. Omit request to use concurrent mode.
# request:
#   mode: window
#   window_size: 5
---

Classify the user text and return exactly one JSON object with status, category, reason, and suggestion; do not add markdown or prose.
