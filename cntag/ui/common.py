"""Shared UI constants and helpers."""
from __future__ import annotations

import sys
from pathlib import Path

from ..settings import settings_path

BACKGROUND = "#F3F5FA"
CARD = "#FFFFFF"
INK = "#202236"
MUTED = "#73778C"
ACCENT = "#6857E5"
ACCENT_DARK = "#5140C8"
BORDER = "#E3E6EF"
SUCCESS = "#167A5B"
DANGER = "#B34452"
REPOSITORY_URL = "https://github.com/pretenderlu/CNTag"
LATEST_RELEASE_URL = f"{REPOSITORY_URL}/releases/latest"


def _resource_path(relative: str) -> Path:
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return root / relative


def _settings_path() -> Path:
    return settings_path()
