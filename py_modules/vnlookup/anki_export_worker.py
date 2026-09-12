#!/usr/bin/env python3
"""apkg export worker — runs under the venv python, never under Decky's
runtime (genanki is only installed there; nothing heavy is imported into
the Decky process, mirroring ocr_worker.py's convention).

Reads opts JSON from stdin:
  {"cards": [{"id","expression","reading","glosses","sentence"}, ...],
   "deck_name", "deck_id", "note_type_name", "model_id",
   "field_map": {"expression"|"reading"|"glossary"|"sentence": "<field name>"},
   "out_path"}
Prints JSON: {"error", "path", "count"} as the last (only) stdout line.
"""

import json
import sys

ROLE_ORDER = ["expression", "reading", "glossary", "sentence"]
# buffered-card dict key for each role (glossary role holds the "glosses" key)
CARD_KEY = {"expression": "expression", "reading": "reading",
            "glossary": "glosses", "sentence": "sentence"}


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
    )
    deck = genanki.Deck(opts["deck_id"], opts["deck_name"])

    try:
        for card in opts.get("cards", []):
            fields = [card.get(CARD_KEY[r], "") or "" for r in roles]
            deck.add_note(genanki.Note(model=model, fields=fields, guid=card["id"]))
        genanki.Package(deck).write_to_file(opts["out_path"])
    except Exception as e:
        import traceback
        _fail(f"apkg build failed: {e}", trace=traceback.format_exc())
        return

    print(json.dumps({"error": None, "path": opts["out_path"],
                      "count": len(opts.get("cards", []))}))


if __name__ == "__main__":
    main()
