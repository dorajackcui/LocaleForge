---
id: example-transform
mode: transform
description: Minimal text-in/text-out task template.

# Default table contract.
input:
  column: source
  header_row: 1
  start_row: 2

output:
  column: target
  create: true
  overwrite: true

# Optional. Omit this field to use OPENAI_MODEL from .env.
# model: gpt-5.5

# Optional. Omit request to use concurrent mode.
# request:
#   mode: window
#   window_size: 5
---

Rewrite the user text into clear, natural French and return only the rewritten text.
