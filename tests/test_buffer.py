from vnlookup.buffer import PendingCards


def test_empty_when_no_file(tmp_path):
    b = PendingCards(str(tmp_path))
    assert b.count() == 0
    assert b.all() == []


def test_add_and_count(tmp_path):
    b = PendingCards(str(tmp_path))
    b.add("言葉", "ことば", "word", "これは言葉です")
    b.add("猫", "ねこ", "cat", "猫がいる")
    assert b.count() == 2
    assert {c["expression"] for c in b.all()} == {"言葉", "猫"}


def test_add_assigns_stable_string_id(tmp_path):
    b = PendingCards(str(tmp_path))
    card = b.add("言葉", "ことば", "word", "これは言葉です")
    assert isinstance(card["id"], str) and card["id"]


def test_dedupe_on_same_expression_reading_sentence(tmp_path):
    b = PendingCards(str(tmp_path))
    first = b.add("言葉", "ことば", "word", "これは言葉です")
    second = b.add("言葉", "ことば", "updated gloss", "これは言葉です")
    assert b.count() == 1
    assert first["id"] == second["id"]
    assert b.all()[0]["glosses"] == "updated gloss"


def test_different_sentence_is_a_new_card(tmp_path):
    b = PendingCards(str(tmp_path))
    b.add("言葉", "ことば", "word", "これは言葉です")
    b.add("言葉", "ことば", "word", "別の文です")
    assert b.count() == 2


def test_persistence_across_instances(tmp_path):
    b = PendingCards(str(tmp_path))
    b.add("言葉", "ことば", "word", "これは言葉です")
    b2 = PendingCards(str(tmp_path))
    assert b2.count() == 1
    assert b2.all()[0]["expression"] == "言葉"


def test_clear(tmp_path):
    b = PendingCards(str(tmp_path))
    b.add("言葉", "ことば", "word", "これは言葉です")
    b.clear()
    assert b.count() == 0
    assert PendingCards(str(tmp_path)).count() == 0


def test_corrupt_file_falls_back_to_empty(tmp_path):
    (tmp_path / "anki_buffer.json").write_text("{not json")
    b = PendingCards(str(tmp_path))
    assert b.all() == []
