"""Persistent buffer of cards pending Anki export.

Same atomic-write idiom as settings.py, but its own file under RUNTIME_DIR
rather than inside vn-lookup.json — this is transient, user-clearable state,
not a setting.
"""

import json
import os
import uuid
from typing import Any


class PendingCards:
    def __init__(self, runtime_dir: str):
        self.path = os.path.join(runtime_dir, "anki_buffer.json")
        self._data: list[dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, encoding="utf-8") as f:
                self._data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._data = []

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def add(self, expression: str, reading: str, glosses: str, sentence: str,
            game: str = "") -> dict:
        """Add a card, or update glosses/game in place if the same
        expression/reading/sentence is already buffered (repeated +Anki
        taps on the same word don't grow the buffer)."""
        for card in self._data:
            if (card["expression"] == expression and card["reading"] == reading
                    and card["sentence"] == sentence):
                card["glosses"] = glosses
                card["game"] = game
                self.save()
                return card
        card = {
            "id": uuid.uuid4().hex,
            "expression": expression,
            "reading": reading,
            "glosses": glosses,
            "sentence": sentence,
            "game": game,
        }
        self._data.append(card)
        self.save()
        return card

    def all(self) -> list[dict]:
        return list(self._data)

    def count(self) -> int:
        return len(self._data)

    def remove(self, card_id: str) -> bool:
        """Drop one buffered card by id. Returns whether it was found."""
        before = len(self._data)
        self._data = [c for c in self._data if c["id"] != card_id]
        removed = len(self._data) != before
        if removed:
            self.save()
        return removed

    def clear(self) -> None:
        self._data = []
        self.save()
