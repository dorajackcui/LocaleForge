from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from localeforge.settings import (
    ProviderConfig,
    add_provider,
    load_settings,
    resolve_api_key,
    resolve_base_url,
    save_settings,
    settings_to_public_dict,
)


class SettingsTests(unittest.TestCase):
    def test_load_settings_supports_legacy_nested_api_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            path.write_text(
                '{\n'
                '  "defaults": {\n'
                '    "execution_mode": "api",\n'
                '    "api": {\n'
                '      "provider_id": "test",\n'
                '      "model": "gpt-5.5",\n'
                '      "concurrency": 5\n'
                '    }\n'
                '  },\n'
                '  "providers": [\n'
                '    {\n'
                '      "provider_id": "test",\n'
                '      "base_url": "https://api.example.com/v1",\n'
                '      "api_key": "secret",\n'
                '      "models": ["gpt-5.5"]\n'
                '    }\n'
                '  ]\n'
                '}\n',
                encoding="utf-8",
            )

            settings = load_settings(path)

        self.assertEqual(settings.defaults.execution_mode, "api")
        self.assertEqual(settings.defaults.provider_id, "test")
        self.assertEqual(settings.defaults.model, "gpt-5.5")
        self.assertEqual(settings.defaults.concurrency, 5)
        self.assertEqual(settings.providers[0].default_model, "gpt-5.5")

    def test_add_provider_from_local_env_file_without_persisting_secret(self) -> None:
        tmpdir_context = tempfile.TemporaryDirectory()
        self.addCleanup(tmpdir_context.cleanup)
        tmpdir = tmpdir_context.name
        path = Path(tmpdir) / "settings.json"
        env_path = Path(tmpdir) / ".env"
        env_path.write_text(
            'LF_TEST_API_KEY="secret-value"\n'
            'LF_TEST_BASE_URL="https://api.example.com/v1"\n',
            encoding="utf-8",
        )
        previous_cwd = Path.cwd()
        os.chdir(tmpdir)
        self.addCleanup(os.chdir, previous_cwd)
        self.addCleanup(os.environ.pop, "LF_TEST_API_KEY", None)
        self.addCleanup(os.environ.pop, "LF_TEST_BASE_URL", None)

        settings = load_settings(path)
        add_provider(
            settings,
            ProviderConfig(
                provider_id="default-api",
                base_url="",
                base_url_env="LF_TEST_BASE_URL",
                api_key="",
                api_key_env="LF_TEST_API_KEY",
                default_model="gpt-4.1-mini",
                models=["gpt-4.1-mini"],
            ),
            set_default=True,
        )
        save_settings(settings, path)

        reloaded = load_settings(path)
        self.assertEqual(reloaded.defaults.provider_id, "default-api")
        self.assertEqual(reloaded.providers[0].base_url, "")
        self.assertEqual(reloaded.providers[0].base_url_env, "LF_TEST_BASE_URL")
        self.assertEqual(reloaded.providers[0].api_key, "")
        self.assertEqual(reloaded.providers[0].api_key_env, "LF_TEST_API_KEY")
        self.assertEqual(resolve_base_url(reloaded.providers[0]), "https://api.example.com/v1")
        self.assertEqual(resolve_api_key(reloaded.providers[0]), "secret-value")
        self.assertEqual(settings_to_public_dict(reloaded)["providers"][0]["api_key"], "")


if __name__ == "__main__":
    unittest.main()
