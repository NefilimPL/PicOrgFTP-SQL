import json
import locale
import os
from pathlib import Path

# Directory containing translation files
_LOCALE_DIR = Path(__file__).resolve().parent / "locales"

_translations = {}
_languages = {}
_current_lang = None

def _load_languages():
    """Load all available language files from the locales directory."""
    if _languages:
        return
    if not _LOCALE_DIR.exists():
        return
    for file in _LOCALE_DIR.glob("*.json"):
        try:
            with open(file, encoding="utf-8") as f:
                _languages[file.stem] = json.load(f)
        except Exception:
            # Skip invalid JSON files
            continue

def available_languages():
    """Return a list of loaded language codes."""
    _load_languages()
    return sorted(_languages.keys())

def set_language(lang: str | None = None):
    """Select active language.

    If *lang* is None, tries APP_LANG env var, then system locale,
    finally falls back to English.
    """
    global _current_lang, _translations
    _load_languages()
    if lang is None:
        lang = os.getenv("APP_LANG")
        if not lang:
            loc, _ = locale.getdefaultlocale() or (None, None)
            if loc:
                lang = loc.split("_")[0]
    if lang not in _languages:
        lang = "en" if "en" in _languages else next(iter(_languages), "")
    _current_lang = lang
    _translations = _languages.get(lang, {})

def t(key: str) -> str:
    """Return the translated text for *key*.
    If the key does not exist, return the key itself."""
    return _translations.get(key, key)

# Initialize on import
set_language()
