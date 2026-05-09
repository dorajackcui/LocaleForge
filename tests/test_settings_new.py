from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from localeforge.settings import ProviderConfig, add_provider, load_settings, save_settings, settings_to_public_dict


class SettingsTests(unittest.TestCase):
    def test_add_provider_from_env_and_redacts_public_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "settings.json"
            os.environ["LF_TEST_API_KEY"] = "secret-value"
            self.addCleanup(os.environ.pop, "LF_TEST_API_KEY", None)

            settings = load_settings(path)
            add_provider(
                settings,
                ProviderConfig(
                    provider_id="default-api",
                    base_url="https://api.example.com/v1",
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
            self.assertEqual(reloaded.providers[0].api_key, "secret-value")
            self.assertEqual(settings_to_public_dict(reloaded)["providers"][0]["api_key"], "<redacted>")


if __name__ == "__main__":
    unittest.main()
