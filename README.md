# Local Excel Translation Check

This workspace includes a local batch checker for Excel column `C`.

## What It Does

- Reads `Sheet1` from the sample workbook
- Checks whether column `C` still contains untranslated English
- Writes only the status to column `F`
- Saves a new file ending with `_checked.xlsx`

## Status Values

- `OK`
- suspect label configured in the script
- `EMPTY`

## Requirements

Install Python packages if needed:

```powershell
python -m pip install -r requirements.txt
```

Make sure Ollama is available locally:

```powershell
ollama list
ollama serve
```

## Run

```powershell
python .\check_excel_translations.py
```

Run the minimal desktop UI:

```powershell
python .\translation_checker_ui.py
```

Or specify paths explicitly:

```powershell
python .\check_excel_translations.py --input "D:\e4b\your-file.xlsx" --output "D:\e4b\your-file_checked.xlsx"
```

## Notes

- The script uses rules first, then sends only borderline cases to `gemma4:e4b`.
- Ollama is called through `http://127.0.0.1:11434/api/generate`.
- The original Excel file is not modified.
