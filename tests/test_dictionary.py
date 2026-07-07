import json
import time
import zipfile

import pytest
from vnlookup.dictionary import Dictionary, _freq_value, flatten_glosses


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


def test_freq_value_shapes():
    assert _freq_value(42) == (42, "42")
    assert _freq_value("top-1k") == (None, "top-1k")
    assert _freq_value({"value": 7, "displayValue": "7th"}) == (7, "7th")
    assert _freq_value({"reading": "かな", "frequency": {"value": 3}}) == (3, "3")
