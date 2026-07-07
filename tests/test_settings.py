import json

from vnlookup.settings import DEFAULTS, Settings


def test_defaults_when_no_file(tmp_path):
    s = Settings(str(tmp_path))
    assert s.get("trigger_button") == DEFAULTS["trigger_button"]
    assert s.all() == DEFAULTS


def test_roundtrip_persistence(tmp_path):
    s = Settings(str(tmp_path))
    s.set("trigger_button", "R4")
    s2 = Settings(str(tmp_path))
    assert s2.get("trigger_button") == "R4"


def test_partial_region_healed_by_deep_merge(tmp_path):
    # a stored region missing keys (older version / hand edit) must not
    # reach the crop worker incomplete
    path = tmp_path / "vn-lookup.json"
    path.write_text(json.dumps({"region": {"x": 0.1}, "trigger_button": "R4"}))
    s = Settings(str(tmp_path))
    region = s.get("region")
    assert set(region) == {"x", "y", "w", "h"}
    assert region["x"] == 0.1
    assert s.get("trigger_button") == "R4"


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
