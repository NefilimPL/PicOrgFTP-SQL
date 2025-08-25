from pathlib import Path
import sys

# Ensure the project root is on sys.path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from i18n import Translator

LOCALES = Path(__file__).parent / "locales"

def test_load_existing_language():
    translator = Translator(LOCALES)
    assert translator.gettext("greeting", "pl") == "Cześć"

def test_language_fallback_to_english():
    translator = Translator(LOCALES)
    assert translator.gettext("greeting", "de") == "Hello"

def test_missing_key_fallback_to_english():
    translator = Translator(LOCALES)
    assert translator.gettext("farewell", "pl") == "Goodbye"
