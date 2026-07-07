import asyncio

import pytest
from vnlookup.anki import AnkiConnect, AnkiError


class StubAnki(AnkiConnect):
    """Capture invoke() calls instead of hitting AnkiConnect."""

    def __init__(self, responses=None):
        super().__init__("http://stub")
        self.calls = []
        self.responses = responses or {}

    async def invoke(self, action, **params):
        self.calls.append((action, params))
        return self.responses.get(action)


def test_add_note_builds_payload_with_picture(tmp_path):
    png = tmp_path / "shot.png"
    png.write_bytes(b"\x89PNG fake")
    anki = StubAnki(responses={"addNote": 12345})

    note_id = asyncio.run(anki.add_note(
        "Mining", "Japanese",
        {"Expression": "不安", "Sentence": "不安だ", "Picture": ""},
        picture_path=str(png), picture_field="Picture"))

    assert note_id == 12345
    action, params = anki.calls[0]
    note = params["note"]
    assert note["deckName"] == "Mining"
    assert note["modelName"] == "Japanese"
    # picture rides in the picture attachment, not as a plain field
    assert "Picture" not in note["fields"]
    assert note["picture"][0]["fields"] == ["Picture"]
    assert note["picture"][0]["data"]  # base64 of the file


def test_add_note_without_picture_keeps_fields(tmp_path):
    anki = StubAnki(responses={"addNote": 1})
    asyncio.run(anki.add_note("D", "M", {"Front": "言葉"}))
    note = anki.calls[0][1]["note"]
    assert note["fields"] == {"Front": "言葉"}
    assert "picture" not in note


def test_add_note_unreadable_screenshot_degrades_gracefully(tmp_path):
    anki = StubAnki(responses={"addNote": 2})
    note_id = asyncio.run(anki.add_note(
        "D", "M", {"Front": "x", "Picture": ""},
        picture_path=str(tmp_path / "missing.png"), picture_field="Picture"))
    assert note_id == 2
    assert "picture" not in anki.calls[0][1]["note"]


def test_add_note_no_result_raises():
    anki = StubAnki(responses={"addNote": None})
    with pytest.raises(AnkiError):
        asyncio.run(anki.add_note("D", "M", {"Front": "x"}))


def test_enrich_note_skips_unknown_picture_field(tmp_path):
    png = tmp_path / "shot.png"
    png.write_bytes(b"fake")
    anki = StubAnki(responses={
        "notesInfo": [{"fields": {"Front": {"value": ""}}}],
    })
    wrote = asyncio.run(anki.enrich_note(
        1, str(png), "sentence", picture_field="Picture",
        sentence_field="Sentence"))
    # neither field exists on this note type: nothing written, no crash
    assert wrote == {"picture": False, "sentence": False}
    assert [c[0] for c in anki.calls] == ["notesInfo"]
