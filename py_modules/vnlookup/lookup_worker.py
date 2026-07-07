#!/usr/bin/env python3
"""Tokenizer worker — runs under the venv python (fugashi + unidic-lite).

Usage: lookup_worker.py tokenize '<json>'
  input:  {"text": "..."}
  output: {"error": null, "tokens": [{surface, lemma, dict_form, reading,
           pos, selectable}]}

- dict_form is orthBase (base form in the surface's own orthography:
  食べた → 食べる, する → する) — the best dictionary-lookup key.
- lemma is UniDic's normalized lemma (する → 為る) — secondary key.
- reading is the surface pronunciation converted to hiragana.
- selectable=false marks punctuation/whitespace so the UI renders but
  doesn't focus them.
"""

import json
import sys

_NON_SELECTABLE_POS = {"補助記号", "空白", "記号"}


def _kata_to_hira(text: str) -> str:
    return "".join(
        chr(ord(ch) - 0x60) if "ァ" <= ch <= "ヶ" else ch
        for ch in text or ""
    )


def _feature(f, name):
    val = getattr(f, name, None)
    # fugashi returns '*' for empty UniDic fields
    return None if val in (None, "*", "") else val


def tokenize(text: str):
    from fugashi import Tagger

    tagger = Tagger()  # finds unidic-lite automatically
    tokens = []
    for word in tagger(text):
        f = word.feature
        pos = _feature(f, "pos1") or ""
        surface = word.surface
        tokens.append({
            "surface": surface,
            "dict_form": _feature(f, "orthBase") or surface,
            "lemma": _feature(f, "lemma") or surface,
            "reading": _kata_to_hira(_feature(f, "pron")
                                     or _feature(f, "kana") or ""),
            "pos": pos,
            "selectable": pos not in _NON_SELECTABLE_POS,
        })
    return tokens


def main():
    try:
        if len(sys.argv) < 3 or sys.argv[1] != "tokenize":
            raise ValueError("usage: lookup_worker.py tokenize '<json>'")
        text = json.loads(sys.argv[2])["text"]
        print(json.dumps({"error": None, "tokens": tokenize(text)},
                         ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e), "tokens": []}, ensure_ascii=False))


if __name__ == "__main__":
    main()
