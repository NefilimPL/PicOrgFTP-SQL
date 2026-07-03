import json
from unittest.mock import Mock

from picorgftp_sql.services.translation_service import translate_text


class Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.payload


def test_google_translation_returns_translated_text():
    opener = Mock(
        return_value=Response(
            json.dumps([[['White cabinet', "Biala szafka"]]]).encode()
        )
    )

    result = translate_text(
        "Biala szafka",
        "en",
        {"provider": "google", "api_key": "", "api_url": ""},
        opener=opener,
    )

    assert result.text == "White cabinet"
    assert result.warning is None


def test_provider_failure_keeps_source_text_and_warning():
    opener = Mock(side_effect=TimeoutError("timeout"))

    result = translate_text(
        "Biala szafka",
        "en",
        {"provider": "google"},
        opener=opener,
    )

    assert result.text == "Biala szafka"
    assert result.warning["code"] == "translation_failed"
    assert "timeout" in result.warning["message"]


def test_deepl_without_key_keeps_source_without_network_call():
    opener = Mock()

    result = translate_text(
        "Biala",
        "en",
        {"provider": "deepl", "api_key": ""},
        opener=opener,
    )

    assert result.text == "Biala"
    assert result.warning["code"] == "missing_translation_key"
    opener.assert_not_called()
