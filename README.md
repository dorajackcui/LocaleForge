# LocaleForge

LocaleForge is a local-first Excel QA tool for localization teams. It processes workbook rows with a local Ollama model and currently supports two tasks:

- `english-check`: detect untranslated English leaking into French localized text
- `term-extraction`: extract game-related terms from a text segment

The prompts remain as standalone files at the repo root so you can tune them without editing Python modules.

## Why LocaleForge

- Keeps sensitive localization data on your machine
- Uses a local model instead of a hosted API
- Fits Excel-based review workflows common in localization pipelines
- Separates task config, prompts, model integration, workbook logic, CLI, and UI for easier iteration

## What It Does

- Reads an `.xlsx` workbook and processes a target worksheet
- Inspects one source column, defaulting to column `C`
- Writes a task result to a result column, defaulting to column `F`
- Writes extracted spans or terms to the next column, defaulting to column `G`
- Saves a new workbook instead of modifying the original file

Common status values:

- `OK`
- `EMPTY`
- `疑似英文未翻译` for `english-check`
- `提取到术语` for `term-extraction`

## Tasks

### `english-check`

- Uses fast local rules to catch obvious empty or English-heavy rows
- Sends borderline rows to Ollama for strict judgment
- Writes suspicious untranslated tokens or phrases to the detail column

Default files and headers:

- Prompt: `translation_checker_prompt.txt`
- Headers: `CheckResult` / `CheckResultSpans`

### `term-extraction`

- Sends every non-empty row to Ollama
- Extracts game-related terms in any language
- Writes the extracted terms to the detail column using ` | ` separators
- Adds a `TermSummary` worksheet with deduplicated extracted terms, occurrence counts, and source rows

Default files and headers:

- Prompt: `term_extractor_prompt.txt`
- Headers: `TermExtractResult` / `ExtractedTerms`

## How It Works

LocaleForge now uses a small internal package structure:

1. `localeforge.config.tasks` defines task ids, labels, statuses, headers, and defaults.
2. `localeforge.prompts` resolves and validates prompt templates.
3. `localeforge.model.ollama` handles Ollama availability checks and response parsing.
4. `localeforge.rules` contains the English/French heuristic prechecks.
5. `localeforge.workbook` handles workbook reading, row processing, cache reuse, and writeback.
6. `localeforge.runtime` provides the shared task execution flow used by both CLI and UI.
7. `localeforge.ui` contains the Tkinter app and UI-specific helpers.

By default the tool expects:

- Ollama running at `http://127.0.0.1:11434`
- Model name `gemma4:e4b`
- Worksheet `Sheet1`

## Privacy

LocaleForge is designed for local localization workflows.

- Workbook content stays on your machine
- Model calls go only to your local Ollama instance
- Sensitive test files are excluded from Git with [`.gitignore`](D:\e4b\.gitignore)

You should still review your local machine, model setup, and access controls for your own environment.

## Requirements

- Python 3.11 or newer recommended
- [Ollama](https://ollama.com/) installed locally
- Python packages from [`requirements.txt`](D:\e4b\requirements.txt)

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Verify Ollama:

```powershell
ollama list
ollama serve
```

## CLI Usage

The user-facing entrypoint is unchanged:

```powershell
python .\check_excel_translations.py
```

Run term extraction:

```powershell
python .\check_excel_translations.py --task term-extraction
```

Run with explicit paths:

```powershell
python .\check_excel_translations.py --task term-extraction --input "D:\path\to\input.xlsx" --output "D:\path\to\input_checked.xlsx"
```

Common options:

```powershell
python .\check_excel_translations.py `
  --task "english-check" `
  --input "D:\path\to\input.xlsx" `
  --output "D:\path\to\input_checked.xlsx" `
  --sheet "Sheet1" `
  --source-col "C" `
  --result-col "F" `
  --prompt-file ".\translation_checker_prompt.txt" `
  --start-row 2 `
  --model "gemma4:e4b" `
  --api-url "http://127.0.0.1:11434"
```

Prompt template notes:

- English check default: `translation_checker_prompt.txt`
- Term extraction default: `term_extractor_prompt.txt`
- Required placeholders: `{{STATUS_OK}}`, `{{STATUS_SUSPECT}}`, `{{TEXT}}`
- For `term-extraction`, `{{STATUS_SUSPECT}}` is mapped to `提取到术语`
- You can override the default prompt with `--prompt-file`

## Desktop UI

The user-facing desktop entrypoint is also unchanged:

```powershell
python .\app.py
```

The UI lets you:

- Choose an Excel file
- Select the worksheet
- Switch between the two tasks
- Configure source and output columns
- Change the local model and Ollama API URL
- Use a different prompt template file for prompt debugging
- Run the task and review progress in a log panel

When you switch tasks, the prompt file auto-switches only if it is still using the previous task's default prompt.

## Output

For each processed row, LocaleForge writes:

- A task status in the result column
- A detail list in the next column

Examples:

- `english-check`: suspicious untranslated English spans
- `term-extraction`: extracted game terms

For `term-extraction`, LocaleForge also adds a `TermSummary` worksheet that deduplicates the extracted terms and shows how many rows each term appeared in.

The original workbook is left unchanged. Results are saved to a new file ending in `_checked.xlsx` unless you provide another output path.

## Project Structure

- [`check_excel_translations.py`](D:\e4b\check_excel_translations.py): thin CLI wrapper
- [`app.py`](D:\e4b\app.py): thin desktop wrapper
- [`localeforge`](D:\e4b\localeforge): shared package for config, prompts, rules, runtime, model integration, workbook logic, and UI
- [`translation_checker_prompt.txt`](D:\e4b\translation_checker_prompt.txt): English leak check prompt
- [`term_extractor_prompt.txt`](D:\e4b\term_extractor_prompt.txt): Game term extraction prompt
- [`tests`](D:\e4b\tests): unit tests for extracted modules and behavior-preserving workbook flows
- [`requirements.txt`](D:\e4b\requirements.txt): Python dependencies
