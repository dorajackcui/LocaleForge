---
id: status-check
mode: status-json
description: Classify source text and write status plus optional spans.
output:
  column: target
  details_column: details
---

Check the user text.
Return JSON only using this shape:
{"status":"OK","spans":[]}
