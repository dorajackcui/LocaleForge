from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from localeforge.config.settings import (
    ApiDefaults,
    AppDefaults,
    AppSettings,
    LocalDefaults,
    ProviderConfig,
    ProviderMutationError,
    delete_provider,
    load_settings,
    save_settings,
    upsert_provider,
)


class SettingsTests(unittest.TestCase):
    def test_load_settings_creates_default_file_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"

            settings = load_settings(settings_path)

            self.assertTrue(settings_path.exists())
            self.assertEqual(settings.defaults.execution_mode, "local")
            self.assertEqual(settings.defaults.local.model, "gemma4:e4b")
            self.assertEqual(settings.defaults.api.concurrency, 4)

    def test_save_and_load_round_trip_preserves_provider_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            settings = AppSettings(
                defaults=AppDefaults(
                    execution_mode="api",
                    local=LocalDefaults(
                        base_url="http://127.0.0.1:11434",
                        model="gemma4:e4b",
                        concurrency=1,
                    ),
                    api=ApiDefaults(
                        provider_id="demo",
                        model="gpt-4o-mini",
                        concurrency=6,
                    ),
                ),
                providers=[
                    ProviderConfig(
                        provider_id="demo",
                        name="Demo",
                        base_url="https://example.test/v1",
                        api_key="secret-key",
                        models=["gpt-4o-mini", "gpt-4.1-mini"],
                        last_tested_at="2026-04-23T10:00:00Z",
                    )
                ],
            )

            save_settings(settings, settings_path)
            reloaded = load_settings(settings_path)

            self.assertEqual(reloaded.defaults.execution_mode, "api")
            self.assertEqual(reloaded.defaults.api.provider_id, "demo")
            self.assertEqual(reloaded.defaults.api.model, "gpt-4o-mini")
            self.assertEqual(reloaded.providers[0].api_key, "secret-key")
            self.assertEqual(reloaded.providers[0].models, ["gpt-4o-mini", "gpt-4.1-mini"])

    def test_invalid_json_falls_back_to_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            settings_path = Path(tmpdir) / "settings.json"
            settings_path.write_text("{invalid", encoding="utf-8")

            settings = load_settings(settings_path)

            self.assertEqual(settings.defaults.execution_mode, "local")
            self.assertEqual(settings.providers, [])

    def test_new_provider_requires_successful_test_before_save(self) -> None:
        settings = AppSettings()

        with self.assertRaises(ProviderMutationError):
            upsert_provider(
                settings,
                ProviderConfig(
                    provider_id="demo",
                    name="Demo",
                    base_url="https://example.test/v1",
                    api_key="secret-key",
                ),
            )

    def test_provider_connection_change_requires_retest(self) -> None:
        settings = AppSettings(
            providers=[
                ProviderConfig(
                    provider_id="demo",
                    name="Demo",
                    base_url="https://example.test/v1",
                    api_key="secret-key",
                    models=["gpt-4o-mini"],
                    last_tested_at="2026-04-23T10:00:00Z",
                )
            ]
        )

        with self.assertRaises(ProviderMutationError):
            upsert_provider(
                settings,
                ProviderConfig(
                    provider_id="demo",
                    name="Demo Updated",
                    base_url="https://example.test/v2",
                    api_key="secret-key",
                    models=["gpt-4o-mini"],
                    last_tested_at="2026-04-23T10:00:00Z",
                ),
            )

    def test_delete_provider_clears_matching_api_defaults(self) -> None:
        settings = AppSettings(
            defaults=AppDefaults(
                execution_mode="api",
                local=LocalDefaults(),
                api=ApiDefaults(provider_id="demo", model="gpt-4o-mini", concurrency=4),
            ),
            providers=[
                ProviderConfig(
                    provider_id="demo",
                    name="Demo",
                    base_url="https://example.test/v1",
                    api_key="secret-key",
                    models=["gpt-4o-mini"],
                    last_tested_at="2026-04-23T10:00:00Z",
                )
            ],
        )

        delete_provider(settings, "demo")

        self.assertEqual(settings.providers, [])
        self.assertIsNone(settings.defaults.api.provider_id)
        self.assertEqual(settings.defaults.api.model, "")


if __name__ == "__main__":
    unittest.main()
