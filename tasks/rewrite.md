---
id: rewrite
mode: transform
model: gpt-5.5
description: Rewrite source text and output the final result to target.
---

## Task 
Rewrite freely the source text into clear, natural, and concise French, as if it were originally written in French by a skilled native writer. 

## Instructions
- If there is any doubt at all about whether a passage should be rewritten, rewrite it.
- Write natural, idiomatic French as a native speaker would.
- Freely change wording, sentence structure, and phrasing whenever needed.
- Make the phrasing flow naturally, with good rhythm and a natural spoken or narrative cadence.
- Condense, soften, or reshape details whenever needed for better French.
- Remove repetition, heaviness, and anything stiff or overly literal.
- Only tags (`<...>`) and placeholders (`{...}`) must remain untouched.
- Rewrite everything else, including text inside quotation marks, square brackets (`[...]`), and parentheses (`(...)`).

## Typography & French Conventions
- Use straight apostrophes `'`, never `’`.
- Ensure correct French spelling, accents, grammar, and idiomatic usage.
- Follow French punctuation conventions, including spacing before `: ; ? !`.
- Use `œ` and `æ` where appropriate.

## Formatting Constraints
-  Preserve tag (<...>) and placeholders ({...}) exactly as they appear.
- Treat literal escape (`\n`, `\r`) sequences as literal text. Do not interpret them.

## Output Rules
- Output ONLY the final French rewritten text, with no explanations.
