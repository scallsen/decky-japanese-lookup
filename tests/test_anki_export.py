from vnlookup.anki_export import stable_id


def test_stable_id_deterministic():
    assert stable_id("vnlookup-deck", "Mining") == stable_id("vnlookup-deck", "Mining")


def test_stable_id_differs_by_name():
    assert stable_id("vnlookup-deck", "Mining") != stable_id("vnlookup-deck", "Other")


def test_stable_id_differs_by_salt():
    assert stable_id("vnlookup-deck", "Mining") != stable_id("vnlookup-model", "Mining")


def test_stable_id_is_positive_int():
    value = stable_id("vnlookup-deck", "Mining")
    assert isinstance(value, int)
    assert value > 0
