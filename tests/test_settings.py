import json

from vnlookup.settings import DEFAULTS, Settings


def test_defaults_when_no_file(tmp_path):
    s = Settings(str(tmp_path))
    assert s.get("anki_deck") == DEFAULTS["anki_deck"]
    assert s.all() == DEFAULTS


def test_roundtrip_persistence(tmp_path):
    s = Settings(str(tmp_path))
    s.set("anki_deck", "Custom Deck")
    s2 = Settings(str(tmp_path))
    assert s2.get("anki_deck") == "Custom Deck"


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    (tmp_path / "vn-lookup.json").write_text("{not json")
    s = Settings(str(tmp_path))
    assert s.all() == DEFAULTS


def test_new_default_appears_after_update(tmp_path):
    # settings written by an older plugin version lack newer keys
    (tmp_path / "vn-lookup.json").write_text(json.dumps({"ocr_backend": "gemini"}))
    s = Settings(str(tmp_path))
    assert s.get("ocr_backend") == "gemini"
    assert s.get("anki_deck") == DEFAULTS["anki_deck"]


def test_retired_keys_dropped_on_load(tmp_path):
    (tmp_path / "vn-lookup.json").write_text(
        json.dumps({"trigger_button": "R5", "anki_deck": "Kept"}))
    s = Settings(str(tmp_path))
    assert "trigger_button" not in s.all()
    assert s.get("anki_deck") == "Kept"
