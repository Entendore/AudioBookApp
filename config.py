#!/usr/bin/env python3
"""
Configuration management for Advanced Audiobook Studio.
Handles loading, saving, and merging of user preferences.
"""

import os
import sys
import json
from kivy.utils import platform as kivy_platform

CONFIG_FILENAME = "audiobook_config.json"

DEFAULT_CONFIG = {
    "voice": "en-US-AvaNeural",
    "rate": "+0%",
    "volume": "+0%",
    "pitch": "+0Hz",
    "concurrency": 15,
    "chunk_size": 500,
    "output_format": "both",
    "output_dir": "",
    "last_file": "",
    "para_pause": 0.5,
    # Audio effects
    "fx_highpass": False,   "fx_highpass_f": 80,
    "fx_clarity": False,    "fx_clarity_g": 5.0,
    "fx_compressor": False,
    "fx_loudnorm": True,
    "fx_reverb": False,     "fx_reverb_room": 50,
    "fx_chorus": False,
    "fx_radio": False,
    "fx_vibrato": False,    "fx_vibrato_freq": 5.0,  "fx_vibrato_depth": 0.5,
    "fx_bass": False,       "fx_bass_gain": 5.0,
    # Chapter splitting
    "split_chapters": False,
    "chapter_regex": r"^Chapter\s+\d+",
}


def config_path() -> str:
    """Return the platform-appropriate path for the config file."""
    if kivy_platform == "android":
        try:
            from android.storage import app_storage_path
            return os.path.join(app_storage_path(), CONFIG_FILENAME)
        except Exception:
            pass
    return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), CONFIG_FILENAME)


def load_config() -> dict:
    """Load config from disk, merging with defaults for any missing keys."""
    cp = config_path()
    if os.path.exists(cp):
        try:
            with open(cp, "r", encoding="utf-8") as f:
                data = json.load(f)
            for key, value in DEFAULT_CONFIG.items():
                data.setdefault(key, value)
            return data
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[Config] Load failed ({exc}), using defaults.")
    return DEFAULT_CONFIG.copy()


def save_config(cfg: dict) -> None:
    """Persist config dict to disk."""
    try:
        with open(config_path(), "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=4)
    except OSError as exc:
        print(f"[Config] Save failed: {exc}")


def default_output_dir() -> str:
    """Return the platform-appropriate default output directory."""
    if kivy_platform == "android":
        try:
            from android.storage import app_storage_path
            return os.path.join(app_storage_path(), "output")
        except Exception:
            pass
    return os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "output")