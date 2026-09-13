from vnlookup.anki_export import TEMPLATE_VERSION, stable_id


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


def test_model_salt_changes_with_template_version():
    # a bumped TEMPLATE_VERSION must mint a new model id, not collide with
    # whatever's already in a user's collection under the old template
    old = stable_id("vnlookup-model-v1", "Basic")
    current = stable_id(f"vnlookup-model-v{TEMPLATE_VERSION}", "Basic")
    assert TEMPLATE_VERSION != 1
    assert old != current
