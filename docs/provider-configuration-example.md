# Provider Configuration Example

LocaleForge stores provider configuration once, then tasks and agents can reuse it without repeating base URL or API key arguments.

Settings are stored locally at:

```text
~/.localeforge/settings.json
```

API keys are redacted from `provider list`, `doctor`, JSON reports, and normal logs.

## Recommended: API Key From Environment

PowerShell:

```powershell
$env:OPENAI_API_KEY="sk-your-key"

localeforge provider add default-api `
  --base-url https://api.example.com/v1 `
  --api-key-env OPENAI_API_KEY `
  --default-model gpt-4.1-mini `
  --set-default `
  --json
```

After this, agents can run:

```powershell
localeforge doctor --json
localeforge run --task tasks/proofread.md --input data/source.csv --json
```

No API key or base URL is needed in the task file or run command.

## Automation: Direct API Key Argument

Use direct `--api-key` only when the caller controls shell history and logs:

```powershell
localeforge provider add default-api `
  --base-url https://api.example.com/v1 `
  --api-key sk-your-key `
  --default-model gpt-4.1-mini `
  --set-default `
  --json
```

Prefer `--api-key-env` for normal use.

## Verify Configuration

```powershell
localeforge provider list --json
localeforge doctor --json
```

Expected shape:

```json
{
  "defaults": {
    "execution_mode": "api",
    "provider_id": "default-api",
    "model": "gpt-4.1-mini"
  },
  "providers": [
    {
      "provider_id": "default-api",
      "base_url": "https://api.example.com/v1",
      "api_key": "<redacted>",
      "default_model": "gpt-4.1-mini"
    }
  ]
}
```

## Switching Providers Or Models

Set another default provider:

```powershell
localeforge provider add backup-api `
  --base-url https://backup.example.com/v1 `
  --api-key-env BACKUP_API_KEY `
  --default-model gpt-4.1-mini `
  --set-default
```

Override model for one run:

```powershell
localeforge run --task tasks/proofread.md --input data/source.csv --model gpt-4.1-mini --json
```

## Security Notes

- Do not commit `.env` files.
- Do not commit local provider settings.
- Do not put secrets in task Markdown files.
- Use `--json` for machine-readable output; secrets remain redacted.
