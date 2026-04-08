# LocaleForge

LocaleForge is a local-first QA tool for localization teams. It checks Excel translation sheets for untranslated English that may have leaked into French localized content, using rule-based filtering plus a local Ollama model.

## Why LocaleForge

- Keeps sensitive localization data on your machine
- Uses a local model instead of sending strings to a hosted API
- Handles Excel-based review workflows that are common in game and product localization
- Combines deterministic rules with model judgment so obvious cases stay fast

## What It Does

- Reads an `.xlsx` workbook and processes a target worksheet
- Inspects one source column, defaulting to column `C`
- Writes the review result to a result column, defaulting to column `F`
- Writes suspicious token spans to the next column, defaulting to column `G`
- Saves a new workbook instead of modifying the original file

Current status values:

- `OK`
- `EMPTY`
- the suspicious untranslated-English label configured in the script

## How It Works

LocaleForge uses a two-stage pipeline:

1. Fast local rules catch obvious empty rows and English-heavy rows.
2. Borderline rows are sent to a local Ollama model for a stricter decision.

By default the tool expects:

- Ollama running at `http://127.0.0.1:11434`
- Model name `gemma4:e4b`
- Worksheet `Sheet1`

## Privacy

LocaleForge is designed for local localization workflows.

- Workbook content stays on your machine
- Model calls go only to your local Ollama instance
- Sensitive test files are excluded from Git with [`.gitignore`](D:\e4b\.gitignore)

You should still review your local machine, model setup, and access controls based on your own security requirements.

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

Run with defaults:

```powershell
python .\check_excel_translations.py
```

Run with explicit paths:

```powershell
python .\check_excel_translations.py --input "D:\path\to\input.xlsx" --output "D:\path\to\input_checked.xlsx"
```

Common options:

```powershell
python .\check_excel_translations.py `
  --input "D:\path\to\input.xlsx" `
  --output "D:\path\to\input_checked.xlsx" `
  --sheet "Sheet1" `
  --source-col "C" `
  --result-col "F" `
  --start-row 2 `
  --model "gemma4:e4b" `
  --api-url "http://127.0.0.1:11434"
```

## Desktop UI

Launch the local desktop UI:

```powershell
python .\translation_checker_ui.py
```

The UI lets you:

- Choose an Excel file
- Select the worksheet
- Configure source and output columns
- Change the local model and Ollama API URL
- Run the check and review progress in a log panel

## Output

For each processed row, LocaleForge writes:

- `CheckResult` in the result column
- `CheckResultSpans` in the next column

The original workbook is left unchanged. Results are saved to a new file ending in `_checked.xlsx` unless you provide another output path.

## Project Structure

- [`check_excel_translations.py`](D:\e4b\check_excel_translations.py): CLI pipeline and Excel processing logic
- [`translation_checker_ui.py`](D:\e4b\translation_checker_ui.py): Tkinter desktop UI
- [`requirements.txt`](D:\e4b\requirements.txt): Python dependencies

## Roadmap

- Support more localization target languages
- Add configurable review labels and column mappings
- Export reviewer summaries for production QA workflows
- Improve model prompt tuning for game localization content
