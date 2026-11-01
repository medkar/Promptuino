"""Tests du modele de menu composant (ui/wiring/component_menu.py)."""
import sys
from pathlib import Path
from collections import namedtuple

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.component_menu import MenuEntry, menu_entries

_FakeAction = namedtuple("_FakeAction", ["id", "label"])
LABELS = {"edit": "Modifier ce composant…",
          "wrong_component": "Ce n'est pas le bon composant"}


def test_only_wrong_component_when_not_editable_no_actions():
    entries = menu_entries(editable=False, actions=[], labels=LABELS)
    assert [e.kind for e in entries] == ["wrong_component"]
    assert entries[0].label == "Ce n'est pas le bon composant"


def test_edit_first_when_editable():
    entries = menu_entries(editable=True, actions=[], labels=LABELS)
    assert [e.kind for e in entries] == ["edit", "wrong_component"]


def test_all_implicit_actions_listed_in_order():
    actions = [_FakeAction("led_series_value", "Résistance série…"),
               _FakeAction("servo_external_power", "Alimentation du servo…")]
    entries = menu_entries(editable=False, actions=actions, labels=LABELS)
    assert [e.kind for e in entries] == ["implicit", "implicit", "wrong_component"]
    assert entries[0].action_id == "led_series_value"
    assert entries[1].action_id == "servo_external_power"
    assert entries[0].label == "Résistance série…"


def test_wrong_component_always_last_and_present():
    actions = [_FakeAction("a", "A")]
    entries = menu_entries(editable=True, actions=actions, labels=LABELS)
    assert [e.kind for e in entries] == ["edit", "implicit", "wrong_component"]
    assert entries[-1].kind == "wrong_component"


TESTS = [
    test_only_wrong_component_when_not_editable_no_actions,
    test_edit_first_when_editable,
    test_all_implicit_actions_listed_in_order,
    test_wrong_component_always_last_and_present,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
