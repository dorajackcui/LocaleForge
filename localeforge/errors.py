from __future__ import annotations


class LocaleForgeError(Exception):
    """Base error for expected LocaleForge failures."""


class ConfigError(LocaleForgeError):
    """Raised when CLI, settings, or effective configuration is invalid."""


class TaskProfileError(ConfigError):
    """Raised when a Markdown task profile is invalid."""


class InputOutputError(LocaleForgeError):
    """Raised when input or output files cannot be used safely."""


class ModelProviderError(LocaleForgeError):
    """Raised when a model provider is unavailable or returns invalid data."""


class PartialFailureError(LocaleForgeError):
    """Raised when a folder run completes with one or more failed files."""


def exit_code_for_error(error: BaseException) -> int:
    if isinstance(error, PartialFailureError):
        return 4
    if isinstance(error, ModelProviderError):
        return 3
    if isinstance(error, InputOutputError):
        return 2
    if isinstance(error, ConfigError):
        return 1
    if isinstance(error, LocaleForgeError):
        return 1
    return 1
