import json
import sqlite3
import time
import zipfile

import pytest
from vnlookup.dictionary import (
    Dictionary,
    _cap_glosses,
    _freq_value,
    _SCHEMA_VERSION,
    flatten_glosses,
)


def make_dict_zip(path, title="TestDict"):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("index.json", json.dumps(
            {"title": title, "revision": "1", "format": 3}))
        z.writestr("term_bank_1.json", json.dumps([
            ["食べる", "たべる", "v1", "v1", 100,
             ["to eat",
              {"type": "structured-content",
               "content": {"tag": "ul",
                           "content": [{"tag": "li", "content": "to live on"}]}}],
             1, ""],
            ["する", "する", "vs", "vs", 90, ["to do"], 2, ""],
            ["言う", "いう", "v5", "v5", 80, ["to say"], 3, ""],
            ["言", "げん", "n", "", 10, ["word; remark"], 4, ""],
        ]))
        z.writestr("term_meta_bank_1.json", json.dumps([
            ["食べる", "freq", {"value": 500, "displayValue": "500"}],
            ["食べる", "pitch",
             {"reading": "たべる", "pitches": [{"position": 2}]}],
        ]))


@pytest.fixture
def dic(tmp_path):
    dicts_dir = tmp_path / "dicts"
    dicts_dir.mkdir()
    make_dict_zip(dicts_dir / "test.zip")
    d = Dictionary(str(tmp_path / "dict.sqlite3"), str(dicts_dir))
    assert d.start_import()
    while d.get_status()["importing"]:
        time.sleep(0.02)
    assert d.get_status()["error"] is None
    return d


def test_import_counts(dic):
    st = dic.get_status()
    assert st["dictionaries"] == ["TestDict"]
    assert st["term_count"] == 4
    assert st["ready"]


def _make_pre_word_type_db(db_path, dict_title):
    conn = sqlite3.connect(str(db_path))
    conn.executescript(f"""
        CREATE TABLE dictionaries (id INTEGER PRIMARY KEY, title TEXT UNIQUE,
                                    revision TEXT, kind TEXT);
        CREATE TABLE terms (dict_id INTEGER, expression TEXT, reading TEXT,
                             glosses TEXT, tags TEXT, score INTEGER);
        CREATE TABLE term_meta (dict_id INTEGER, expression TEXT, mode TEXT,
                                 data TEXT);
        INSERT INTO dictionaries VALUES (1, '{dict_title}', '1', 'term');
        INSERT INTO terms VALUES (1, '古い', 'ふるい', 'old', '', 1);
    """)
    conn.commit()
    conn.close()


def test_migrates_pre_word_type_database_with_no_cached_zip(tmp_path):
    # no source zip to re-import from (e.g. it really was deleted) — must
    # still not crash; the column is added but the stale row is left as-is
    # until the user re-imports themselves. Critically, the failed reimport
    # must NOT mark the migration as done: user_version has to stay behind
    # so a later launch (once a zip is available again) retries it, rather
    # than treating "we tried and failed" the same as "it's handled".
    db_path = tmp_path / "dict.sqlite3"
    _make_pre_word_type_db(db_path, "Old")
    dicts_dir = tmp_path / "dicts"
    dicts_dir.mkdir()
    d = Dictionary(str(db_path), str(dicts_dir))
    while d.get_status()["importing"]:
        time.sleep(0.02)
    assert d.get_status()["error"]

    entries = d.lookup(["古い"])
    assert entries[0]["glosses"] == "old"
    assert entries[0]["word_type"] == ""

    conn = sqlite3.connect(str(db_path))
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    conn.close()


def test_migrates_pre_word_type_database_reimports_cached_zip(tmp_path):
    # the common case: the dictionary zip is still sitting in dicts_dir
    # (never deleted after the original import) — migrating should
    # silently re-run the import against it, so already-imported entries
    # end up with the header correctly split out, with no user action
    db_path = tmp_path / "dict.sqlite3"
    _make_pre_word_type_db(db_path, "TestDict")  # matches make_dict_zip's title
    dicts_dir = tmp_path / "dicts"
    dicts_dir.mkdir()
    make_dict_zip(dicts_dir / "test.zip")

    d = Dictionary(str(db_path), str(dicts_dir))
    while d.get_status()["importing"]:
        time.sleep(0.02)
    assert d.get_status()["error"] is None

    # the pre-migration "古い" row came only from the hand-built old-schema
    # DB, not from make_dict_zip's fixture — re-importing "TestDict"
    # replaces its rows entirely, so this one is gone; that's expected
    # (the dictionary's own re-import semantics, unrelated to word_type)
    assert d.lookup(["古い"]) == []
    entries = d.lookup(["食べる"])
    assert "to eat" in entries[0]["glosses"]
    assert "• to live on" in entries[0]["glosses"]

    conn = sqlite3.connect(str(db_path))
    assert conn.execute("PRAGMA user_version").fetchone()[0] == _SCHEMA_VERSION
    conn.close()


def test_reimports_even_when_word_type_column_already_added(tmp_path):
    # regression: an earlier version of this migration added the
    # word_type column without reimporting anything into it. A
    # database that already has the (empty) column from that half-done
    # migration must still trigger the reimport — the column's mere
    # presence is not a reliable "already migrated" signal.
    db_path = tmp_path / "dict.sqlite3"
    _make_pre_word_type_db(db_path, "TestDict")
    conn = sqlite3.connect(str(db_path))
    conn.execute("ALTER TABLE terms ADD COLUMN word_type TEXT")
    conn.commit()
    conn.close()

    dicts_dir = tmp_path / "dicts"
    dicts_dir.mkdir()
    make_dict_zip(dicts_dir / "test.zip")

    d = Dictionary(str(db_path), str(dicts_dir))
    while d.get_status()["importing"]:
        time.sleep(0.02)
    assert d.get_status()["error"] is None
    entries = d.lookup(["食べる"])
    assert entries  # reimport actually happened, not skipped


def test_lookup_by_expression_with_meta(dic):
    entries = dic.lookup(["食べる"])
    assert entries[0]["reading"] == "たべる"
    assert "to eat" in entries[0]["glosses"]
    assert "• to live on" in entries[0]["glosses"]
    assert entries[0]["frequency"] == "500"
    assert entries[0]["pitch"] == [2]


def test_lookup_falls_back_to_reading(dic):
    entries = dic.lookup(["たべる"])
    assert entries and entries[0]["expression"] == "食べる"


def test_lookup_query_priority(dic):
    # first query with hits wins — a miss falls through to the next
    entries = dic.lookup(["みつからない", "する"])
    assert entries and entries[0]["expression"] == "する"


def test_lookup_no_hits(dic):
    assert dic.lookup(["存在しない単語"]) == []


def test_longest_prefix(dic):
    entries = dic.longest_prefix_lookup("言うとおりに")
    assert entries[0]["expression"] == "言う"
    assert entries[0]["matched"] == "言う"


def test_reimport_replaces_not_duplicates(dic):
    assert dic.start_import()
    while dic.get_status()["importing"]:
        time.sleep(0.02)
    assert dic.get_status()["term_count"] == 4


def test_import_rejects_non_dictionary_zip(tmp_path):
    dicts_dir = tmp_path / "dicts"
    dicts_dir.mkdir()
    with zipfile.ZipFile(dicts_dir / "bad.zip", "w") as z:
        z.writestr("readme.txt", "not a dictionary")
    d = Dictionary(str(tmp_path / "dict.sqlite3"), str(dicts_dir))
    d.start_import()
    while d.get_status()["importing"]:
        time.sleep(0.02)
    assert "index.json" in (d.get_status()["error"] or "")


# ---- gloss flattening -----------------------------------------------------

def sc(content):
    return [{"type": "structured-content", "content": content}]


def test_flatten_pos_tags_get_own_line():
    out = flatten_glosses(sc([
        {"tag": "div", "data": {"content": "sense-group"}, "content": [
            {"tag": "span", "data": {"content": "part-of-speech-info"},
             "content": "noun"},
            {"tag": "span", "data": {"content": "part-of-speech-info"},
             "content": "na-adj"},
            {"tag": "ul", "data": {"content": "glossary"}, "content": [
                {"tag": "li", "content": "anxiety"},
                {"tag": "li", "content": "worry"},
            ]},
        ]},
    ]))
    assert out.splitlines() == ["noun na-adj", "• anxiety", "• worry"]


def test_flatten_strips_ruby_annotations():
    out = flatten_glosses(sc([
        {"tag": "ruby", "content": ["言", {"tag": "rt", "content": "い"}]},
        "った",
    ]))
    assert out == "言った"


def test_flatten_strips_attribution():
    out = flatten_glosses(sc([
        {"tag": "ul", "content": [{"tag": "li", "content": "to say"}]},
        {"tag": "div", "data": {"content": "attribution"}, "content": [
            {"tag": "a", "href": "https://jmdict.org", "content": "JMdict"},
            " | ",
            {"tag": "a", "href": "https://tatoeba.org", "content": "Tatoeba"},
        ]},
    ]))
    assert "JMdict" not in out and "Tatoeba" not in out
    assert "• to say" in out


def test_flatten_plain_string_glosses():
    assert flatten_glosses(["to eat", "to devour"]) == "to eat\nto devour"


def test_flatten_extracts_pos_labels_when_requested():
    # opt-in via pos_out: the labels are excluded from the returned text
    # entirely rather than left inline as an ambiguous bare line
    pos = []
    out = flatten_glosses(sc([
        {"tag": "div", "data": {"content": "sense-group"}, "content": [
            {"tag": "span", "data": {"content": "part-of-speech-info"},
             "content": "noun"},
            {"tag": "span", "data": {"content": "part-of-speech-info"},
             "content": "na-adj"},
            {"tag": "ul", "data": {"content": "glossary"}, "content": [
                {"tag": "li", "content": "anxiety"},
            ]},
        ]},
    ]), pos)
    assert out.splitlines() == ["• anxiety"]
    assert pos == ["noun", "na-adj"]


def test_flatten_pos_extraction_omitted_by_default():
    # no pos_out given -> old inline behavior, unchanged (e.g. for direct
    # callers that still want the header inline)
    out = flatten_glosses(sc([
        {"tag": "span", "data": {"content": "part-of-speech-info"}, "content": "noun"},
        {"tag": "ul", "content": [{"tag": "li", "content": "anxiety"}]},
    ]))
    assert out.splitlines() == ["noun", "• anxiety"]


# ---- gloss capping ----------------------------------------------------------

def test_cap_glosses_under_limit_is_unchanged():
    text = "• one\n• two"
    assert _cap_glosses(text, max_senses=3) == text


def test_cap_glosses_truncates():
    text = "\n".join(f"• sense {i}" for i in range(6))
    out = _cap_glosses(text, max_senses=3)
    assert out.splitlines() == ["• sense 0", "• sense 1", "• sense 2", "…"]


def test_cap_glosses_handles_bare_lines_too():
    # cross-dictionary joins in _entries can produce several flat,
    # non-bulleted lines (one per simple-gloss row)
    text = "\n".join(f"gloss {i}" for i in range(5))
    out = _cap_glosses(text, max_senses=3)
    assert out.splitlines() == ["gloss 0", "gloss 1", "gloss 2", "…"]


def test_lookup_caps_many_senses(tmp_path):
    dicts_dir = tmp_path / "dicts"
    dicts_dir.mkdir()
    with zipfile.ZipFile(dicts_dir / "test.zip", "w") as z:
        z.writestr("index.json", json.dumps(
            {"title": "TestDict", "revision": "1", "format": 3}))
        many_senses = sc({
            "tag": "ul", "content": [
                {"tag": "li", "content": f"sense {i}"} for i in range(10)
            ],
        })
        z.writestr("term_bank_1.json", json.dumps([
            ["多義語", "たぎご", "n", "", 100, many_senses, 1, ""],
        ]))
    d = Dictionary(str(tmp_path / "dict.sqlite3"), str(dicts_dir))
    assert d.start_import()
    while d.get_status()["importing"]:
        time.sleep(0.02)
    entries = d.lookup(["多義語"])
    lines = entries[0]["glosses"].splitlines()
    assert len(lines) == 4  # 3 senses + the truncation marker
    assert lines[-1] == "…"
    assert entries[0]["word_type"] == ""


def test_lookup_extracts_word_type_from_pos_header(tmp_path):
    dicts_dir = tmp_path / "dicts"
    dicts_dir.mkdir()
    with zipfile.ZipFile(dicts_dir / "test.zip", "w") as z:
        z.writestr("index.json", json.dumps(
            {"title": "TestDict", "revision": "1", "format": 3}))
        content = sc([
            {"tag": "div", "data": {"content": "sense-group"}, "content": [
                {"tag": "span", "data": {"content": "part-of-speech-info"},
                 "content": "noun"},
                {"tag": "span", "data": {"content": "part-of-speech-info"},
                 "content": "na-adj"},
                {"tag": "ul", "data": {"content": "glossary"}, "content": [
                    {"tag": "li", "content": "anxiety"},
                    {"tag": "li", "content": "worry"},
                ]},
            ]},
        ])
        z.writestr("term_bank_1.json", json.dumps([
            ["不安", "ふあん", "n,adj-na", "", 100, content, 1, ""],
        ]))
    d = Dictionary(str(tmp_path / "dict.sqlite3"), str(dicts_dir))
    assert d.start_import()
    while d.get_status()["importing"]:
        time.sleep(0.02)
    entries = d.lookup(["不安"])
    assert entries[0]["word_type"] == "noun, na-adj"
    assert "noun" not in entries[0]["glosses"]
    assert "• anxiety" in entries[0]["glosses"]


def test_freq_value_shapes():
    assert _freq_value(42) == (42, "42")
    assert _freq_value("top-1k") == (None, "top-1k")
    assert _freq_value({"value": 7, "displayValue": "7th"}) == (7, "7th")
    assert _freq_value({"reading": "かな", "frequency": {"value": 3}}) == (3, "3")
