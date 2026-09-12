"""Rule-based cleanup of Japanese OCR output from VN text boxes.

No network, no models — just normalization rules tuned for the common
failure modes of OCR on VN screenshots: stray whitespace between glyphs,
half-width punctuation, iteration-mark and long-vowel misreads, and the
speaker-name/quote furniture around the actual line.
"""

import re
import unicodedata

# Characters OCR engines commonly emit for the long vowel mark ー when the
# source font is stylized. Only substituted between Japanese characters.
_CHOONPU_LOOKALIKES = "‐-–—−一"

_JP_CHAR = (
    r"぀-ゟ"   # hiragana
    r"゠-ヿ"   # katakana
    r"一-鿿"   # kanji
    r"㐀-䶿"   # kanji ext A
    r"ｦ-ﾝ"   # half-width katakana
    r"々"          # 々
)

_KANA = r"぀-ゟ゠-ヿ"


def _nfkc_preserving_choonpu(text: str) -> str:
    # NFKC folds full-width ASCII and half-width kana into canonical forms,
    # which is what dictionaries expect, but it must not touch 「」…― etc.
    # NFKC keeps those; it's safe as a whole-string pass.
    return unicodedata.normalize("NFKC", text)


def strip_speaker_name(text: str) -> str:
    """Drop a leading speaker label like 【玲奈】 or a bare name line before 「.

    VN boxes are single-speaker; the label is noise for lookup purposes.
    Only strips clearly label-shaped prefixes so narration lines survive.
    """
    text = re.sub(r"^[【\[（(][^】\])）]{1,12}[】\])）]\s*", "", text)
    # "name" line immediately followed by an opening quote: 玲奈「…」
    m = re.match(r"^([" + _JP_CHAR + r"・=＝]{1,10})(「)", text)
    if m:
        text = text[m.end(1):]
    return text


def _join_lines(text: str) -> str:
    # Japanese needs no space at a line wrap; OCR line breaks inside a text
    # box are layout artifacts, not sentence boundaries.
    lines = [ln.strip() for ln in text.splitlines()]
    return "".join(ln for ln in lines if ln)


def _drop_interword_spaces(text: str) -> str:
    # Spaces between two Japanese characters are OCR noise. Spaces adjacent
    # to Latin runs (e.g. a title drop) are kept.
    pattern = re.compile(r"(?<=[" + _JP_CHAR + r"])[ \t　]+(?=[" + _JP_CHAR + r"])")
    prev = None
    while prev != text:
        prev = text
        text = pattern.sub("", text)
    return text


def _fix_choonpu(text: str) -> str:
    # A dash between kana is virtually always ー (e.g. デ一タ → データ).
    return re.sub(
        r"(?<=[" + _KANA + r"])[" + _CHOONPU_LOOKALIKES + r"](?=[" + _KANA + r"])",
        "ー",
        text,
    )


_MISREAD_TABLE = str.maketrans({
    "ロ": "ロ",  # identity; placeholder so the table is easy to extend
})

# Ellipsis variants OCR produces for VN 「……」 — normalize to standard …
_ELLIPSIS_RE = re.compile(r"(?:\.\s*){3,}|・{3,}|,{3,}")


def clean_ocr_text(raw: str, *, remove_speaker: bool = True) -> str:
    """Full cleanup pipeline. Returns "" if nothing survives."""
    if not raw:
        return ""
    text = raw
    text = _join_lines(text)
    text = _nfkc_preserving_choonpu(text)
    text = _ELLIPSIS_RE.sub("…", text)
    text = _drop_interword_spaces(text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = _fix_choonpu(text)
    text = text.translate(_MISREAD_TABLE)
    if remove_speaker:
        text = strip_speaker_name(text)
    return text.strip()


def filter_ui_regions(regions):
    """Drop short pure-ASCII fragments when Japanese regions are present.

    VN screens surround the text box with UI chrome (Auto, Skip, Save,
    Log…). If the capture contains real Japanese, those latin-only scraps
    are noise. When nothing Japanese was found, keep everything — the user
    needs to see what was actually read.

    Returns (kept_regions, dropped_texts).
    """
    has_japanese = any(looks_like_japanese(r["text"], 0.25) for r in regions)
    if not has_japanese:
        return regions, []
    kept, dropped = [], []
    for r in regions:
        t = r["text"].strip()
        is_ascii_scrap = (len(t) <= 12
                          and not looks_like_japanese(t, 0.25)
                          and all(ord(c) < 0x2000 for c in t))
        if is_ascii_scrap:
            dropped.append(t)
        else:
            kept.append(r)
    return kept, dropped


def group_into_rows(regions):
    """Group regions into visual text rows by vertical (y) overlap. Each row
    is sorted left-to-right; rows are sorted top-to-bottom by average top.

    A flat sort by (top, left) alone is not reading order: when one line
    gets split into multiple detection boxes (a quote mark, a tall kanji, or
    just detector noise nudges one fragment's top a few px off its
    neighbors), a pure top-sort can place a same-line fragment before the
    one visually to its left, scrambling the sentence. Grouping by row
    first, and only then sorting within/across rows, fixes that.
    """
    n = len(regions)
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i, j):
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[ri] = rj

    def y_overlap(a, b):
        top = max(a["rect"]["top"], b["rect"]["top"])
        bottom = min(a["rect"]["bottom"], b["rect"]["bottom"])
        return max(0, bottom - top)

    for i in range(n):
        hi = regions[i]["rect"]["bottom"] - regions[i]["rect"]["top"]
        for j in range(i + 1, n):
            hj = regions[j]["rect"]["bottom"] - regions[j]["rect"]["top"]
            if hi <= 0 or hj <= 0:
                continue
            if y_overlap(regions[i], regions[j]) >= 0.5 * min(hi, hj):
                union(i, j)

    groups = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(regions[i])

    rows = list(groups.values())
    for row in rows:
        row.sort(key=lambda r: r["rect"]["left"])
    rows.sort(key=lambda row: sum(r["rect"]["top"] for r in row) / len(row))
    return rows


def reading_order(regions):
    """Flatten `regions` into correct top-to-bottom, left-to-right order."""
    return [r for row in group_into_rows(regions) for r in row]


def drop_ui_chrome_rows(regions, max_chrome_len: int = 10):
    """Drop rows of 2+ short, separate fragments sharing a line — a VN
    button/hint bar (Auto | Skip | Log | Option), as opposed to a single
    wide dialogue line. Used by detect_region so the auto-suggested capture
    box doesn't sweep in a hint bar sitting near the text box: it's easy to
    OCR as "real" Japanese text, but it isn't the dialogue.

    A real multi-region same-line dialogue split is rare and, when the
    detector does split a long line in two, each half is still long — so
    length is what tells a button row apart from dialogue, not row-sharing
    alone.
    """
    drop_ids = set()
    for row in group_into_rows(regions):
        if len(row) >= 2 and all(len(r["text"]) <= max_chrome_len for r in row):
            drop_ids.update(id(r) for r in row)
    return [r for r in regions if id(r) not in drop_ids]


def looks_like_japanese(text: str, threshold: float = 0.3) -> bool:
    """Heuristic used to flag 'OCR returned something, but probably garbage'."""
    if not text:
        return False
    jp = sum(1 for ch in text if re.match(r"[" + _JP_CHAR + r"]", ch))
    return jp / len(text) >= threshold
