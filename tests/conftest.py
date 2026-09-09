"""Gayatri AI — Test configuration and shared fixtures."""

from __future__ import annotations

from pathlib import Path

import pytest

# Ensure core module can be imported
sys_path = str(Path(__file__).resolve().parent.parent)
import sys

if sys_path not in sys.path:
    sys.path.insert(0, sys_path)


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path, monkeypatch):
    """Redirect all data to a temp directory for each test."""
    monkeypatch.setenv("GAYATRI_DATA_DIR", str(tmp_path))
