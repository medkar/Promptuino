"""TODO #87 : le selecteur de micro-pas suit le DRIVER, avec la table du
DRV8825 lue sur la doc Pololu (carrier #2133) -- pas celle de l'A4988.

Le piege que ce chantier verrouille, cite verbatim par Pololu : << The mode
selection pin inputs corresponding to 1/16-step on the A4988 result in
1/32-step microstepping on the DRV8825. >> Memes broches cablees, distance
parcourue differente -- ca compile et ca tourne dans les deux cas, aucune
compilation ne le signalera jamais. Avant ce chantier, la molette
n'existait que pour l'A4988 (un seul elif) : apres un swap vers un DRV8825
elle disparaissait, et le reglage n'etait plus rattrapable depuis le
schema.

TMC2209 et STSPIN220 restent SANS molette : leurs micro-pas ne se reglent
pas par MS1-3 cables (UART pour le premier).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.netlist import Component, Netlist, Pin  # noqa: E402
from ui.wiring import implicit_actions as ia  # noqa: E402


def _driver(dtype: str, ms=("GND", "GND", "GND")) -> Component:
    return Component(
        ref="U1", type=dtype,
        pins=[Pin("STEP", "D3"), Pin("DIR", "D4"),
              Pin("MS1", ms[0]), Pin("MS2", ms[1]), Pin("MS3", ms[2])],
        attributes={})


def _action(comp: Component):
    nl = Netlist(board_id="arduino_uno_r3", components=[comp])
    acts = ia.available_actions(comp, nl)
    return acts, nl


# ── tables ───────────────────────────────────────────────────────────────

def test_the_a4988_table_is_unchanged():
    # Caracterisation : la table Allegro historique ne bouge pas -- et
    # (1,1,1) y vaut 1/16, la moitie du piege.
    assert ia.A4988_MICROSTEP_TABLE == {
        "full": (0, 0, 0), "1/2": (1, 0, 0), "1/4": (0, 1, 0),
        "1/8": (1, 1, 0), "1/16": (1, 1, 1)}


def test_the_drv8825_table_matches_pololu():
    # Table LUE sur pololu.com/product/2133 (MODE0/1/2 -> MS1/2/3) : le
    # 1/16 vaut (0,0,1) -- PAS le (1,1,1) de l'A4988 -- et le 1/32
    # canonique est (1,0,1).
    assert ia.DRV8825_MICROSTEP_TABLE == {
        "full": (0, 0, 0), "1/2": (1, 0, 0), "1/4": (0, 1, 0),
        "1/8": (1, 1, 0), "1/16": (0, 0, 1), "1/32": (1, 0, 1)}


def test_the_trap_same_wiring_different_mode():
    """MS1=MS2=MS3=HIGH : 1/16 sur A4988, 1/32 sur DRV8825 (Pololu,
    verbatim). C'est LE cas du ticket -- l'ecart qu'aucune compilation ne
    signale, desormais AFFICHE par la molette au lieu d'etre cache."""
    a4988 = _driver("a4988", ms=("5V", "5V", "5V"))
    acts, _ = _action(a4988)
    assert acts and acts[0].value == "1/16", acts
    drv = _driver("drv8825", ms=("5V", "5V", "5V"))
    acts, _ = _action(drv)
    assert acts and acts[0].value == "1/32", acts


def test_the_two_extra_encodings_read_as_thirty_second():
    # Pololu liste TROIS encodages pour 1/32 ; on ecrit le canonique mais
    # on doit lire les trois.
    for ms in (("5V", "GND", "5V"), ("GND", "5V", "5V"), ("5V", "5V", "5V")):
        drv = _driver("drv8825", ms=ms)
        acts, _ = _action(drv)
        assert acts and acts[0].value == "1/32", (ms, acts)


# ── la molette suit le driver ────────────────────────────────────────────

def test_the_dial_follows_the_driver():
    acts_a, _ = _action(_driver("a4988"))
    assert [a.id for a in acts_a] == ["stepper_microstepping"]
    assert [v for v, _l in acts_a[0].choices] == \
        ["full", "1/2", "1/4", "1/8", "1/16"]
    acts_d, _ = _action(_driver("drv8825"))
    assert [a.id for a in acts_d] == ["stepper_microstepping"]
    assert [v for v, _l in acts_d[0].choices] == \
        ["full", "1/2", "1/4", "1/8", "1/16", "1/32"]


def test_uart_and_stspin_drivers_get_no_dial():
    # Leurs micro-pas ne se reglent pas par MS cables -- pas de molette,
    # plutot que des libelles A4988 faux et plausibles.
    for dtype in ("tmc2209", "stspin220"):
        acts, _ = _action(_driver(dtype))
        assert acts == [], (dtype, acts)


# ── ecriture ─────────────────────────────────────────────────────────────

def test_setting_sixteenth_on_a_drv8825_wires_its_own_bits():
    drv = _driver("drv8825")
    nl = Netlist(board_id="arduino_uno_r3", components=[drv])
    ia.apply_action(drv, "stepper_microstepping", nl, value="1/16")
    assert [drv.pin(n).net for n in ("MS1", "MS2", "MS3")] == \
        ["GND", "GND", "5V"]
    ia.apply_action(drv, "stepper_microstepping", nl, value="1/32")
    assert [drv.pin(n).net for n in ("MS1", "MS2", "MS3")] == \
        ["5V", "GND", "5V"]


def test_setting_sixteenth_on_an_a4988_still_wires_all_high():
    a4988 = _driver("a4988")
    nl = Netlist(board_id="arduino_uno_r3", components=[a4988])
    ia.apply_action(a4988, "stepper_microstepping", nl, value="1/16")
    assert [a4988.pin(n).net for n in ("MS1", "MS2", "MS3")] == \
        ["5V", "5V", "5V"]


# ── la modale suit aussi ─────────────────────────────────────────────────

def test_the_dialog_offers_thirty_second_only_for_the_drv8825():
    from PyQt6.QtWidgets import QApplication, QRadioButton
    # Reference gardee au niveau module : une QApplication locale serait
    # GC-ee et construire un QWidget ensuite crashe le process (0xC0000409)
    # -- piege memorise, et pourtant reecrit ici a la premiere passe (le
    # crash natif avale meme le tampon stdout : zero sortie, exit code
    # illisible a travers un pipe).
    global _APP
    _APP = QApplication.instance() or QApplication([])
    from ui.wiring import wiring_diagram_dialog as wdd
    dlg_a = wdd._MicrosteppingDialog(None, ref="U1", current_value="full",
                                     driver_type="a4988")
    dlg_d = wdd._MicrosteppingDialog(None, ref="U1", current_value="full",
                                     driver_type="drv8825")
    n_a = len(dlg_a.findChildren(QRadioButton))
    n_d = len(dlg_d.findChildren(QRadioButton))
    assert (n_a, n_d) == (5, 6), (n_a, n_d)
    labels_d = [rb.text() for rb in dlg_d.findChildren(QRadioButton)]
    assert any("1/32" in t for t in labels_d), labels_d
    assert "DRV8825" in dlg_d.windowTitle(), dlg_d.windowTitle()
    assert "A4988" in dlg_a.windowTitle(), dlg_a.windowTitle()


TESTS = [
    test_the_a4988_table_is_unchanged,
    test_the_drv8825_table_matches_pololu,
    test_the_trap_same_wiring_different_mode,
    test_the_two_extra_encodings_read_as_thirty_second,
    test_the_dial_follows_the_driver,
    test_uart_and_stspin_drivers_get_no_dial,
    test_setting_sixteenth_on_a_drv8825_wires_its_own_bits,
    test_setting_sixteenth_on_an_a4988_still_wires_all_high,
    test_the_dialog_offers_thirty_second_only_for_the_drv8825,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
