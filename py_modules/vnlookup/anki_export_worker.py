#!/usr/bin/env python3
"""apkg export worker — runs under the venv python, never under Decky's
runtime (genanki is only installed there; nothing heavy is imported into
the Decky process, mirroring ocr_worker.py's convention).

Reads opts JSON from stdin:
  {"cards": [{"id","expression","reading","glosses","sentence","game",
              "word_type"}, ...],
   "deck_name", "deck_id", "note_type_name", "model_id",
   "field_map": {"expression"|"reading"|"glossary"|"word_type"|"sentence"|
                 "game": "<field name>"},
   "out_path"}
Prints JSON: {"error", "path", "count"} as the last (only) stdout line.
"""

import json
import sys

# Back-of-card order: reading first (right under the word it's the
# reading of, same visual weight as the word itself), then glossary,
# word_type, sentence, game. "game" stays last: reference info, not part
# of what you're being quizzed on.
ROLE_ORDER = ["expression", "reading", "glossary", "word_type", "sentence", "game"]
# buffered-card dict key for each role (glossary role holds the "glosses" key)
CARD_KEY = {"expression": "expression", "reading": "reading",
            "glossary": "glosses", "word_type": "word_type",
            "sentence": "sentence", "game": "game"}

# Each field is wrapped in a role-tagged block so the CSS below can give
# each role genuinely different visual weight, rather than one uniform
# font-size for the whole card. Design intent: expression (front, and
# repeated via {{FrontSide}} on the back) and reading are the two things
# that make up "the word" and share the same large size/weight. glossary +
# sentence are what you're actually testing yourself on — the main
# content, medium-large. word_type is small secondary detail; game is the
# smallest, purely-reference info.
_CSS = """
.card {
 font-family: "Noto Sans CJK JP", "Hiragino Sans", "Yu Gothic", arial, sans-serif;
 text-align: center;
 color: #1a1a1a;
 background-color: white;
 line-height: 1.5;
}
.r-expression, .r-reading {
 font-size: 34px;
 font-weight: 600;
}
.r-reading {
 margin-top: 4px;
}
.r-glossary, .r-sentence {
 font-size: 22px;
 margin-top: 12px;
}
.r-word_type {
 font-size: 16px;
 color: #666;
 margin-top: 4px;
}
.r-game {
 font-size: 13px;
 color: #999;
 margin-top: 16px;
}
#answer {
 width: 60%;
 margin: 14px auto;
 border: none;
 border-top: 1px solid #ddd;
}
"""

# Frozen (not time.time()) so every export looks *older* than any local
# edit the user makes afterward. This is belt-and-suspenders, not the
# actual mechanism that gets a shipped design update into an
# already-imported collection — that's TEMPLATE_VERSION in
# anki_export.py, folded into the model_id itself, because on-device
# testing found AnkiMobile's plain .apkg import just keeps an existing
# note type's template/CSS as-is on an ID match, with no mod-time
# comparison happening at all (whatever the sync-time collision policy
# is, it evidently isn't consulted for a bare package import). A frozen
# timestamp can't fix that — nothing here needs bumping for a design
# change anymore, only TEMPLATE_VERSION does.
_FROZEN_TIMESTAMP = 1735776000  # 2025-01-02T00:00:00Z


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

    def field_block(role):
        return f'<div class="r-{role}">{{{{{field_map[role]}}}}}</div>'

    model = genanki.Model(
        opts["model_id"],
        opts["note_type_name"],
        fields=[{"name": field_map[r]} for r in roles],
        templates=[{
            "name": "Card 1",
            "qfmt": field_block(roles[0]),
            "afmt": ('{{FrontSide}}<hr id="answer">'
                     + "".join(field_block(r) for r in roles[1:])),
        }],
        css=_CSS,
    )
    deck = genanki.Deck(opts["deck_id"], opts["deck_name"])

    try:
        for card in opts.get("cards", []):
            # Anki fields are raw HTML — a literal "\n" collapses in
            # rendering, so multi-sense glosses (one per line) need real
            # <br> tags or they'd all run together on one line.
            fields = [(card.get(CARD_KEY[r], "") or "").replace("\n", "<br>")
                      for r in roles]
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
