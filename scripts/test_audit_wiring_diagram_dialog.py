"""Audit 2026-11-06 : moteur de remplacement (component_replace), catalogue de
remplacement et menu de l'engrenage. Script autonome.

Run : python scripts/test_audit_wiring_diagram_dialog.py
"""
from __future__ import annotations

import os
import sys
import types
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules.setdefault("ui", ui_pkg)

from ui.wiring.netlist import Component, Pin, Netlist
from ui.wiring import component_replace as cr


def _pins(nl, ref):
    return {p.name: p.net for p in next(c for c in nl.components
                                        if c.ref == ref).pins}


# --- 1 : le role vient du NOM de la broche, pas de sa position --------------
def test_role_follows_pin_name_not_position():
    # `markers` emet VCC/DATA/GND, le catalogue ds18b20 est VCC/GND/DATA.
    ds = Component(ref="U1", type="ds18b20",
                   pins=[Pin("VCC", "5V"), Pin("DATA", "D2"), Pin("GND", "GND")],
                   attributes={"signature_detected": True})
    nl = Netlist(board_id="", components=[ds])
    res = cr.replace_component(nl, "U1", "dht22")
    assert res.ok
    got = _pins(res.netlist, "U1")
    assert got == {"VCC": "5V", "DATA": "D2", "GND": "GND"}, got


# --- 2 : deux broches de signal ne se partagent pas un seul net -------------
def test_signal_pins_are_not_all_wired_to_one_net():
    btn = Component(ref="B1", type="button",
                    pins=[Pin("A", "D2"), Pin("B", "GND")],
                    attributes={"category": "digital_in"})
    res = cr.replace_component(Netlist(board_id="", components=[btn]),
                               "B1", "encoder")
    assert res.ok
    got = _pins(res.netlist, "B1")
    assert got["CLK"] == "D2", got
    # la 2e broche de signal n'a pas de source : non cablee, jamais D2 en double
    assert got["DT"] != "D2", got


def test_two_source_signals_go_to_two_distinct_pins():
    gps = Component(ref="U1", type="gps_em406",
                    pins=[Pin("TXD", "D4"), Pin("RXD", "D3"),
                          Pin("VCC", "5V"), Pin("GND", "GND")],
                    attributes={})
    res = cr.replace_component(Netlist(board_id="", components=[gps]),
                               "U1", "dfplayer")
    got = _pins(res.netlist, "U1") if res.ok else {}
    if res.ok:
        sig = [got["RX"], got["TX"]]
        assert sorted(sig) == ["D3", "D4"], got


def test_signal_pin_never_falls_back_to_gnd():
    gps = Component(ref="U1", type="gps_em406",
                    pins=[Pin("TXD", "D4"), Pin("RXD", "D3"),
                          Pin("VCC", "5V"), Pin("GND", "GND")],
                    attributes={})
    res = cr.replace_component(Netlist(board_id="", components=[gps]),
                               "U1", "hc05")
    if res.ok:
        got = _pins(res.netlist, "U1")
        assert got["TXD"] != "GND" and got["RXD"] != "GND", got


# --- 3 : le solenoide n'est pas un pair d'echange d'une sortie nue ----------
def test_solenoid_is_not_swappable_from_a_led():
    assert cr.swap_refusal_reason("led", "solenoid") != ""
    from ui.wiring import replacement_catalog as rc
    assert rc.label_of("solenoid", "fr") is None


# --- 4 : libelles de l'engrenage dans la langue de l'interface --------------
def _actions(lang):
    from ui.wiring import implicit_actions as ia
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D7"), Pin("K", "GND")])
    sv = Component(ref="SV1", type="servo",
                   pins=[Pin("VCC", "5V"), Pin("GND", "GND"), Pin("SIG", "D9")])
    nl = Netlist(board_id="", components=[led, sv])
    return ([a.label for a in ia.available_actions(led, nl, lang=lang)]
            + [a.label for a in ia.available_actions(sv, nl, lang=lang)])


def test_gear_action_labels_are_localized():
    fr, en = _actions("fr"), _actions("en")
    es, it = _actions("es"), _actions("it")
    assert len({tuple(fr), tuple(en), tuple(es), tuple(it)}) == 4
    assert "batterie" not in " ".join(en).lower()
    assert "resistance serie" not in " ".join(en).lower()


# --- 5 : cible hors catalogue : on n'invente pas de noms de broches ---------
def test_uncataloged_target_does_not_keep_old_pin_names():
    btn = Component(ref="B1", type="button",
                    pins=[Pin("A", "D2"), Pin("B", "GND")],
                    attributes={"category": "digital_in"})
    res = cr.replace_component(Netlist(board_id="", components=[btn]),
                               "B1", "keypad")
    if res.ok:
        names = [p.name for p in next(c for c in res.netlist.components
                                      if c.ref == "B1").pins]
        assert "A" not in names and "B" not in names, names
        assert any(w.code == "replaced_pinout_unknown"
                   for w in res.netlist.warnings)


# --- 6 : les avertissements d'un compagnon retire disparaissent -------------
def test_warning_about_a_removed_sibling_is_dropped():
    from ui.wiring.inference import apply_rules
    led = Component(ref="D1", type="led",
                    pins=[Pin("A", "D7"), Pin("K", "GND")],
                    attributes={"category": "single_output"})
    nl = apply_rules(Netlist(board_id="", components=[led]))
    assert any(w.code == "led_series_resistor" for w in nl.warnings)
    res = cr.replace_component(nl, "D1", "relay")
    assert res.ok and res.removed_refs
    assert not any(set(w.refs) & set(res.removed_refs)
                   for w in res.netlist.warnings), res.netlist.warnings


TESTS = [
    test_role_follows_pin_name_not_position,
    test_signal_pins_are_not_all_wired_to_one_net,
    test_two_source_signals_go_to_two_distinct_pins,
    test_signal_pin_never_falls_back_to_gnd,
    test_solenoid_is_not_swappable_from_a_led,
    test_gear_action_labels_are_localized,
    test_uncataloged_target_does_not_keep_old_pin_names,
    test_warning_about_a_removed_sibling_is_dropped,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {ascii(e)}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
