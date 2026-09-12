#!/usr/bin/env python3
"""apkg export worker — runs under the venv python, never under Decky's
runtime (genanki is only installed there; nothing heavy is imported into
the Decky process, mirroring ocr_worker.py's convention).

Reads opts JSON from stdin:
  {"cards": [{"id","expression","reading","glosses","sentence","game"}, ...],
   "deck_name", "deck_id", "note_type_name", "model_id",
   "field_map": {"expression"|"reading"|"glossary"|"sentence"|"game": "<field name>"},
   "out_path"}
Prints JSON: {"error", "path", "count"} as the last (only) stdout line.
"""

import json
import sys

# "game" last so it always lands on the back (afmt), never the front
# (qfmt, which is always roles[0]) — the game a card came from is
# reference info, not part of what you're being quizzed on.
ROLE_ORDER = ["expression", "reading", "glossary", "sentence", "game"]
# buffered-card dict key for each role (glossary role holds the "glosses" key)
CARD_KEY = {"expression": "expression", "reading": "reading",
            "glossary": "glosses", "sentence": "sentence", "game": "game"}

# genanki's own default (arial, 20px, no CJK coverage) reads small on a
# phone and can't render Japanese at all on a device with no CJK-aware
# fallback wired to "arial" — mirrors the font stack already used for
# Japanese text in src/LookupPanel.tsx.
_CSS = """
.card {
 font-family: "Noto Sans CJK JP", "Hiragino Sans", "Yu Gothic", arial, sans-serif;
 font-size: 26px;
 line-height: 1.5;
 text-align: center;
 color: black;
 background-color: white;
}
"""

# Frozen (not time.time()) so every export looks *older* than any edit the
# user makes afterward in Anki's card template editor. Every export reuses
# the same deterministic model_id (see stable_id() in anki_export.py) so
# genanki notetype collisions merge instead of duplicating; Anki's import
# policy on a collision is "newest mod time wins, collection-wide" — freezing
# this means the plugin's export can never look newer than a real local
# edit and clobber it. Only the plugin's own first-ever import (nothing to
# collide with yet) is affected by this constant's actual value.
_FROZEN_TIMESTAMP = 1735689600  # 2025-01-01T00:00:00Z


def _fail(msg, **extra):
    print(json.dumps({"error": msg, **extra}, ensure_ascii=False))
    sys.exit(0)


def main():
    try:
        opts = json.load(sys.stdin)
    except json.JSONDecodeError as e:
        _fail(f"bad opts JSON: {e}")
        return

    try:
        import genanki
    except Exception as e:
        _fail(f"genanki not available: {e}")
        return

    field_map = opts.get("field_map") or {}
    roles = [r for r in ROLE_ORDER if r in field_map]
    if not roles:
        _fail("no Anki fields configured")
        return

    def field_ref(role):
        return "{{" + field_map[role] + "}}"

    model = genanki.Model(
        opts["model_id"],
        opts["note_type_name"],
        fields=[{"name": field_map[r]} for r in roles],
        templates=[{
            "name": "Card 1",
            "qfmt": field_ref(roles[0]),
            "afmt": ('{{FrontSide}}<hr id="answer">'
                     + "<br>".join(field_ref(r) for r in roles[1:])),
        }],
        css=_CSS,
    )
    deck = genanki.Deck(opts["deck_id"], opts["deck_name"])

    try:
        for card in opts.get("cards", []):
            fields = [card.get(CARD_KEY[r], "") or "" for r in roles]
            deck.add_note(genanki.Note(model=model, fields=fields, guid=card["id"]))
        genanki.Package(deck).write_to_file(opts["out_path"], timestamp=_FROZEN_TIMESTAMP)
    except Exception as e:
        import traceback
        _fail(f"apkg build failed: {e}", trace=traceback.format_exc())
        return

    print(json.dumps({"error": None, "path": opts["out_path"],
                      "count": len(opts.get("cards", []))}))


if __name__ == "__main__":
    main()
