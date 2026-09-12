"""Plugin settings, persisted as JSON in Decky's settings dir."""

import json
import os
from typing import Any

DEFAULTS: dict[str, Any] = {
    # List of {"region": {x,y,w,h}, "button": "L4"|"R4"|"L5"|"R5"|None}.
    # Each area is a screen region (fraction of screen size) plus the back
    # button that triggers a capture of it; index 0 is the non-deletable
    # "Default" area. None here = not yet migrated from the legacy
    # region/region_alt/button_map/trigger_button settings — see
    # Plugin._main's one-time migration.
    "capture_areas": None,
    # Per-game overrides, keyed by Steam appid (string):
    # {"<appid>": {"display_name": str, "areas": [<capture_areas entry>, ...]}}.
    # A game with no entry here uses capture_areas ("Default") until the
    # user edits its areas, which creates an entry automatically.
    "capture_profiles": {},
    # "rapidocr" (local, default) | "gemini" (cloud, needs api key)
    "ocr_backend": "rapidocr",
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "min_confidence": 0.4,
    # delivery — clipboard copy is done by the frontend in Steam's CEF;
    # gamescope (SteamOS >= 3.7.14) syncs it to Firefox/Yomitan
    "texthooker_port": 8766,
    "copy_to_clipboard": True,
    # keep last N capture screenshots for Anki cards
    "screenshot_history": 20,
    # master switch — off by default; Anki is an opt-in feature
    "anki_enabled": False,
    # AnkiConnect enrichment of Yomitan-created cards
    "ankiconnect_url": "http://127.0.0.1:8765",
    "anki_auto_enrich": True,
    "anki_picture_field": "Picture",
    "anki_sentence_field": "Sentence",
    # which image goes on the card: "full" frame or textbox "crop"
    "anki_image": "full",
    # native lookup → direct card creation (no Yomitan). Field names map
    # onto the user's note type; empty field names are skipped.
    "anki_deck": "Mining",
    "anki_note_type": "Basic",
    "anki_expression_field": "Front",
    "anki_reading_field": "",
    "anki_glossary_field": "Back",
}


class Settings:
    def __init__(self, settings_dir: str):
        self.path = os.path.join(settings_dir, "vn-lookup.json")
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                stored = json.load(f)
            # merge so new defaults appear after plugin updates; dict-valued
            # settings (region) merge per-key so a stale/partial stored dict
            # can't drop required keys
            merged = {**DEFAULTS, **stored}
            for key, default in DEFAULTS.items():
                if isinstance(default, dict) and isinstance(merged.get(key), dict):
                    merged[key] = {**default, **merged[key]}
            self._data = merged
        except (FileNotFoundError, json.JSONDecodeError):
            self._data = dict(DEFAULTS)

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def get(self, key: str) -> Any:
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value
        self.save()

    def all(self) -> dict[str, Any]:
        return dict(self._data)
