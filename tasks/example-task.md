---
id: example-rewrite-fr
mode: transform
description: Rewrite source text into natural French and write the result to target.

# Optional. These are the defaults, shown here so agents know the schema.
input:
  column: source
  header_row: 1
  start_row: 2

# Optional. The target column is created when it does not exist.
output:
  column: target
  create: true
  overwrite: true

# Optional. Omit this field to use OPENAI_MODEL from .env.
# model: gpt-5.5

# Optional advanced form when this task needs its own concurrency.
# model:
#   name: gpt-5.5
#   concurrency: 4
---

Rewrite the user text into clear, natural, concise French.

Rules:
- Preserve tags like `<name>` and placeholders like `{count}` exactly.
- Preserve literal escape sequences like `\n` as literal text.
- Fix grammar, spelling, accents, and punctuation.
- Use idiomatic French phrasing instead of literal translation.
- Return only the rewritten text.
