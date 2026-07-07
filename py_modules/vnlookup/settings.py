"""Plugin settings, persisted as JSON in Decky's settings dir."""

import json
import os
from typing import Any

DEFAULTS: dict[str, Any] = {
    # Capture region as fractions of screen size (VN text boxes live in the
    # bottom third by default). x, y = top-left corner.
    "region": {"x": 0.03, "y": 0.62, "w": 0.94, "h": 0.36},
    # crop to region before OCR ("region") or OCR the whole frame ("fullscreen")
    "capture_mode": "region",
    # "rapidocr" (local, default) | "gemini" (cloud, needs api key)
    "ocr_backend": "rapidocr",
    "gemini_api_key": "",
    "gemini_model": "gemini-2.5-flash",
    "min_confidence": 0.4,
    # cleanup options
    "strip_speaker_name": True,
    # trigger (read by the frontend poller)
    "trigger_button": "L5",
    "trigger_hold_ms": 250,
    # delivery — clipboard copy is done by the frontend in Steam's CEF;
    # gamescope (SteamOS >= 3.7.14) syncs it to Firefox/Yomitan
    "texthooker_port": 8766,
    "copy_to_clipboard": True,
    # keep last N capture screenshots for Anki cards
    "screenshot_history": 20,
    # AnkiConnect enrichment of Yomitan-created cards
    "ankiconnect_url": "http://127.0.0.1:8765",
    "anki_auto_enrich": True,
    "anki_picture_field": "Picture",
    "anki_sentence_field": "Sentence",
    # which image goes on the card: "full" frame or textbox "crop"
    "anki_image": "full",
}


class Settings:
    def __init__(self, settings_dir: str):
        self.path = os.path.join(settings_dir, "vn-lookup.json")
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
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
