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


def test_game_defaults_to_empty_string(tmp_path):
    b = PendingCards(str(tmp_path))
    card = b.add("言葉", "ことば", "word", "これは言葉です")
    assert card["game"] == ""


def test_word_type_defaults_to_empty_string(tmp_path):
    b = PendingCards(str(tmp_path))
    card = b.add("言葉", "ことば", "word", "これは言葉です")
    assert card["word_type"] == ""


def test_word_type_stored_and_updated_on_dedupe(tmp_path):
    b = PendingCards(str(tmp_path))
    first = b.add("言葉", "ことば", "word", "これは言葉です", word_type="n")
    assert first["word_type"] == "n"
    second = b.add("言葉", "ことば", "word", "これは言葉です", word_type="n adj-na")
    assert b.count() == 1
    assert second["word_type"] == "n adj-na"


def test_game_stored_and_updated_on_dedupe(tmp_path):
    b = PendingCards(str(tmp_path))
    first = b.add("言葉", "ことば", "word", "これは言葉です", game="Game A")
    assert first["game"] == "Game A"
    second = b.add("言葉", "ことば", "word", "これは言葉です", game="Game B")
    assert b.count() == 1
    assert second["game"] == "Game B"


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


def test_remove_by_id(tmp_path):
    b = PendingCards(str(tmp_path))
    first = b.add("言葉", "ことば", "word", "これは言葉です")
    b.add("猫", "ねこ", "cat", "猫がいる")
    assert b.remove(first["id"]) is True
    assert b.count() == 1
    assert b.all()[0]["expression"] == "猫"


def test_remove_persists(tmp_path):
    b = PendingCards(str(tmp_path))
    first = b.add("言葉", "ことば", "word", "これは言葉です")
    b.remove(first["id"])
    assert PendingCards(str(tmp_path)).count() == 0


def test_remove_unknown_id_is_a_noop(tmp_path):
    b = PendingCards(str(tmp_path))
    b.add("言葉", "ことば", "word", "これは言葉です")
    assert b.remove("not-a-real-id") is False
    assert b.count() == 1


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
