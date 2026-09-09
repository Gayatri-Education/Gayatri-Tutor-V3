"""Gayatri AI — Settings persistence.

Validated settings.json for app configuration.
Read/write with schema validation.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any

from core.config import SETTINGS_PATH

logger = logging.getLogger("gayatri.settings")

# Schema: key → expected type
_SETTINGS_SCHEMA: dict[str, type] = {
    "theme": str,           # "dark" | "light"
    "local_model_installed": bool,
    "local_model_path": str,
    "providers": dict,      # {provider_key: {enabled, api_key_ref, ...}}
    "router_preference": str,  # "balanced" | "quality" | "cheap" | "local_only"
    "first_run_complete": bool,
    "telemetry_enabled": bool,
    "auto_download_model": bool,
    "max_tokens": int,
    "temperature": float,
    "system_prompt": str,
}

# Defaults
_DEFAULTS: dict[str, Any] = {
    "theme": "dark",
    "local_model_installed": False,
    "local_model_path": "",
    "providers": {},
    "router_preference": "balanced",
    "first_run_complete": False,
    "telemetry_enabled": False,
    "auto_download_model": True,
    "max_tokens": 512,
    "temperature": 0.7,
    "system_prompt": "You are Gayatri AI, a helpful learning assistant.",
}


class SettingsStore:
    """Thread-safe settings persistence.

    Reads/writes a JSON file with validation.
    """

    def __init__(self, settings_path: str | Path | None = None):
        self._path = Path(settings_path) if settings_path else SETTINGS_PATH
        self._lock = threading.RLock()
        self._settings: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load settings from disk."""
        with self._lock:
            if self._path.exists():
                try:
                    with open(self._path) as f:
                        self._settings = json.load(f)
                    # Validate and apply defaults
                    for key, default in _DEFAULTS.items():
                        if key not in self._settings:
                            self._settings[key] = default
                    logger.info(f"Settings loaded from {self._path}")
                except Exception as exc:
                    logger.error(f"Failed to load settings: {exc}")
                    self._settings = dict(_DEFAULTS)
            else:
                self._settings = dict(_DEFAULTS)
                self._save()

    def _save(self) -> None:
        """Save settings to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".tmp")
        with open(tmp_path, "w") as f:
            json.dump(self._settings, f, indent=2)
        tmp_path.replace(self._path)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting value."""
        with self._lock:
            return self._settings.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Set a setting value with validation."""
        if key in _SETTINGS_SCHEMA and value is not None:
            expected_type = _SETTINGS_SCHEMA[key]
            # Handle float allowing int
            if expected_type is float and isinstance(value, int) and not isinstance(value, bool):
                value = float(value)
            elif not isinstance(value, expected_type):
                raise ValueError(f"Setting '{key}' must be {expected_type.__name__}, got {type(value).__name__}")

        with self._lock:
            self._settings[key] = value
            self._save()
            logger.debug(f"Setting: {key} = {value!r}")

    def get_all(self) -> dict[str, Any]:
        """Get all settings."""
        with self._lock:
            return dict(self._settings)

    def update(self, updates: dict[str, Any]) -> None:
        """Update multiple settings at once."""
        with self._lock:
            for key, value in updates.items():
                if key in _SETTINGS_SCHEMA and value is not None:
                    expected_type = _SETTINGS_SCHEMA[key]
                    if expected_type is float and isinstance(value, int) and not isinstance(value, bool):
                        value = float(value)
                    elif not isinstance(value, expected_type):
                        raise ValueError(f"Setting '{key}' must be {expected_type.__name__}")
                self._settings[key] = value
            self._save()

    def reset(self) -> None:
        """Reset all settings to defaults."""
        with self._lock:
            self._settings = dict(_DEFAULTS)
            self._save()
            logger.info("Settings reset to defaults")


# Global instance
_settings: SettingsStore | None = None


def get_settings() -> SettingsStore:
    """Get the global settings store."""
    global _settings
    if _settings is None:
        _settings = SettingsStore()
    return _settings
