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
    def test_add_provider_from_local_env_file_without_persisting_secret(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
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
