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

# Each field is wrapped in a role-tagged block so the CSS below can give
# the word/reading/glossary/sentence/game roles genuinely different visual
# weight, rather than one uniform font-size for the whole card. Design
# intent: glossary + sentence are what you're actually testing yourself on
# — they should read as the main content. expression is the big prompt on
# both sides (repeated via {{FrontSide}} on the back). reading and game are
# reference info, kept small and muted so they don't compete for attention.
_CSS = """
.card {
 font-family: "Noto Sans CJK JP", "Hiragino Sans", "Yu Gothic", arial, sans-serif;
 text-align: center;
 color: #1a1a1a;
 background-color: white;
 line-height: 1.5;
}
.r-expression {
 font-size: 34px;
 font-weight: 600;
}
.r-glossary, .r-sentence {
 font-size: 22px;
 margin-top: 12px;
}
.r-reading {
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

# Frozen (not time.time()) so every export looks *older* than any edit the
# user makes afterward in Anki's card template editor. Every export reuses
# the same deterministic model_id (see stable_id() in anki_export.py) so
# genanki notetype collisions merge instead of duplicating; Anki's import
# policy on a collision is "newest mod time wins, collection-wide" — freezing
# this means the plugin's export can never look newer than a real local
# edit and clobber it.
#
# A collection that already has this note type imported (from a previous
# export at this same timestamp) won't pick up a template/CSS change unless
# this constant increases — same-mod-time is a tie Anki resolves in favor
# of what's already there. So: bump this, by any amount, every time the
# default template/CSS in this file changes, so the update actually reaches
# collections nobody has customized yet. Only collections with a genuine
# local edit (stamped with the real time it was made, always far later
# than any of these) stay protected either way.
_FROZEN_TIMESTAMP = 1735776000  # 2025-01-02T00:00:00Z — v2: role-based font sizing


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
