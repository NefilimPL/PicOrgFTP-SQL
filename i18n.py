import json
from pathlib import Path
from typing import Dict

DEFAULT_LANG = "en"

class Translator:
    """Simple translation loader with English fallback."""

    def __init__(self, locales_path: Path):
        self.locales_path = Path(locales_path)
        self._cache: Dict[str, Dict[str, str]] = {}

    def _load_file(self, lang: str) -> Dict[str, str]:
        """Load a translation file for the given language.

        Falls back to the default language if the file doesn't exist.
        """
        if lang in self._cache:
            return self._cache[lang]

        path = self.locales_path / f"{lang}.json"
        if not path.exists():
            if lang != DEFAULT_LANG:
                return self._load_file(DEFAULT_LANG)
            data: Dict[str, str] = {}
        else:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)

        if lang != DEFAULT_LANG:
            # Merge with default translations, giving priority to specific lang
            merged = self._load_file(DEFAULT_LANG).copy()
            merged.update(data)
            data = merged

        self._cache[lang] = data
        return data

    def gettext(self, key: str, lang: str) -> str:
        """Return translated string for the given key.

        Falls back to English if the key or language is missing.
        """
        translations = self._load_file(lang)
        if key in translations:
            return translations[key]
        default = self._load_file(DEFAULT_LANG)
        return default.get(key, key)
