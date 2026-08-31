"""Bout en bout (compagnon Qt de test_wiring_diagram_dialog_i18n.py) : les
10 modales pedagogiques "en savoir plus" de la fin de
ui/wiring/wiring_diagram_dialog.py rendent-elles vraiment un texte
different en italien qu'en francais ?

Complement des gardes statiques (cle/langue/placeholder sur le dict) : ici
on CONSTRUIT chaque dialogue et on lit le texte reel des widgets, comme
test_ambiguity_i18n.py le fait pour AmbiguityDialog. Ca attrape ce que la
garde statique ne peut pas voir : un `.format(ref=...)` dont le nom de
placeholder ne correspond pas au `{ref}` du gabarit leverait un KeyError
ICI, pas dans le scan AST -- et une regression dans le CHOIX de la branche
de texte (ex : la prescription ENA/ENB du L298N selon PWM detecte ou pas)
ne se voit qu'en construisant reellement le dialogue.

3 classes creusees en profondeur (choisies pour la richesse de leur texte,
cf consigne de la tache) :
  - _LedSeriesValueDialog     : _CHOICES-driven (6 radios), formule loi d'Ohm
  - _MicrosteppingDialog : _CHOICES-driven (5 radios) + table HTML
  - _L298nJumperInfoDialog    : la plus grosse des 10 -- 2 colonnes, photo
    fallback, ET 4 branches de texte selon PWM detecte (ENA/ENB/les
    deux/aucun) -- seule classe dont le texte affiche depend d'une entree
    au-dela de `ref`.
Plus une passe large sur les 10 classes (titre seulement) pour ne laisser
aucune des 10 hors couverture.

Run : python scripts/test_wiring_diagram_dialog_i18n_qt.py
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# QApplication conservee au niveau module (meme motif que
# test_ambiguity_dropdown_smoke.py) : sans reference gardee, une app
# temporaire immediatement GC-ee puis la construction d'un QWidget plante
# le process (0xC0000409) sous Windows.
from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

from ui.i18n import lang_manager  # noqa: E402
from ui.wiring.netlist import Component, Pin  # noqa: E402
import ui.wiring.wiring_diagram_dialog as wdd  # noqa: E402


def _reset_lang():
    lang_manager.set_language("fr")


def _l298n_component(ena_net: str, enb_net: str) -> Component:
    return Component(ref="U1", type="l298n",
                      pins=[Pin("ENA", ena_net), Pin("ENB", enb_net)])


# ---------------------------------------------------------------------------
# _LedSeriesValueDialog
# ---------------------------------------------------------------------------

def test_led_series_dialog_title_and_body_differ_fr_it():
    from PyQt6.QtWidgets import QLabel
    lang_manager.set_language("fr")
    dlg_fr = wdd._LedSeriesValueDialog(None, ref="D1", current_value="220")
    lang_manager.set_language("it")
    dlg_it = wdd._LedSeriesValueDialog(None, ref="D1", current_value="220")

    assert dlg_fr.windowTitle() != dlg_it.windowTitle()
    assert "D1" in dlg_fr.windowTitle() and "D1" in dlg_it.windowTitle()

    texts_fr = {l.text() for l in dlg_fr.findChildren(QLabel)}
    texts_it = {l.text() for l in dlg_it.findChildren(QLabel)}
    assert texts_fr != texts_it
    # La formule loi d'Ohm (rich text, placeholders numeriques identiques
    # mais mots autour differents) doit vraiment avoir change de langue.
    assert any("loi d'Ohm" in t for t in texts_fr)
    assert any("legge di Ohm" in t for t in texts_it)
    _reset_lang()


def test_led_series_dialog_choices_differ_fr_it():
    from PyQt6.QtWidgets import QRadioButton
    lang_manager.set_language("fr")
    dlg_fr = wdd._LedSeriesValueDialog(None, ref="D1", current_value="220")
    lang_manager.set_language("it")
    dlg_it = wdd._LedSeriesValueDialog(None, ref="D1", current_value="220")

    radios_fr = {r.text() for r in dlg_fr.findChildren(QRadioButton)}
    radios_it = {r.text() for r in dlg_it.findChildren(QRadioButton)}
    assert len(radios_fr) == 6, radios_fr
    assert len(radios_it) == 6, radios_it
    assert radios_fr != radios_it
    assert any(t.startswith("220 Ω — équilibre standard") for t in radios_fr), radios_fr
    assert any(t.startswith("220 Ω — equilibrio standard") for t in radios_it), radios_it
    _reset_lang()


# ---------------------------------------------------------------------------
# _MicrosteppingDialog
# ---------------------------------------------------------------------------

def test_a4988_microstep_dialog_title_and_table_differ_fr_it():
    from PyQt6.QtWidgets import QLabel
    lang_manager.set_language("fr")
    dlg_fr = wdd._MicrosteppingDialog(None, ref="U1", current_value="1/4")
    lang_manager.set_language("it")
    dlg_it = wdd._MicrosteppingDialog(None, ref="U1", current_value="1/4")

    assert dlg_fr.windowTitle() != dlg_it.windowTitle()
    assert "U1" in dlg_fr.windowTitle() and "U1" in dlg_it.windowTitle()

    texts_fr = {l.text() for l in dlg_fr.findChildren(QLabel)}
    texts_it = {l.text() for l in dlg_it.findChildren(QLabel)}
    assert texts_fr != texts_it
    # La table HTML (steps/tour) est un QLabel a part : son en-tete doit
    # avoir change de langue, pas seulement les nombres qu'elle contient.
    assert any("Pas / tour" in t for t in texts_fr)
    assert any("Passi / giro" in t for t in texts_it)
    _reset_lang()


def test_a4988_microstep_dialog_choices_differ_fr_it():
    from PyQt6.QtWidgets import QRadioButton
    lang_manager.set_language("fr")
    dlg_fr = wdd._MicrosteppingDialog(None, ref="U1", current_value="1/4")
    lang_manager.set_language("it")
    dlg_it = wdd._MicrosteppingDialog(None, ref="U1", current_value="1/4")

    radios_fr = {r.text() for r in dlg_fr.findChildren(QRadioButton)}
    radios_it = {r.text() for r in dlg_it.findChildren(QRadioButton)}
    assert len(radios_fr) == 5, radios_fr
    assert len(radios_it) == 5, radios_it
    assert radios_fr != radios_it
    assert any(t.startswith("Pas complet") for t in radios_fr), radios_fr
    assert any(t.startswith("Passo intero") for t in radios_it), radios_it
    _reset_lang()


# ---------------------------------------------------------------------------
# _L298nJumperInfoDialog -- la plus grosse des 10, et la seule dont le
# texte affiche depend d'une entree (PWM detecte) au-dela de `ref`.
# ---------------------------------------------------------------------------

def test_l298n_dialog_title_and_columns_differ_fr_it():
    from PyQt6.QtWidgets import QLabel
    lang_manager.set_language("fr")
    dlg_fr = wdd._L298nJumperInfoDialog(
        None, ref="U1", l298n_component=_l298n_component("D5", "D6"))
    lang_manager.set_language("it")
    dlg_it = wdd._L298nJumperInfoDialog(
        None, ref="U1", l298n_component=_l298n_component("D5", "D6"))

    assert dlg_fr.windowTitle() != dlg_it.windowTitle(), (
        dlg_fr.windowTitle(), dlg_it.windowTitle())
    assert "U1" in dlg_fr.windowTitle() and "U1" in dlg_it.windowTitle()

    texts_fr = {l.text() for l in dlg_fr.findChildren(QLabel)}
    texts_it = {l.text() for l in dlg_it.findChildren(QLabel)}
    assert texts_fr != texts_it
    # Colonne 5V_EN : le scenario A/B doit etre reellement traduit, pas
    # seulement le titre de la colonne.
    assert any("Scénario A" in t for t in texts_fr)
    assert any("Scenario A" in t for t in texts_it)
    _reset_lang()


def test_l298n_dialog_all_four_pwm_branches_differ_fr_it():
    """Les 4 branches de _ena_enb_prescription (ENA seul / ENB seul / les
    deux / aucun) doivent chacune produire un texte reellement traduit --
    pas seulement la branche par defaut testee ci-dessus."""
    from PyQt6.QtWidgets import QLabel
    branches = {
        "both_pwm": ("D5", "D6"),
        "a_only":   ("D5", "5V"),
        "b_only":   ("5V", "D6"),
        "no_pwm":   ("5V", "5V"),
    }
    failures = []
    for name, (ena_net, enb_net) in branches.items():
        lang_manager.set_language("fr")
        dlg_fr = wdd._L298nJumperInfoDialog(
            None, ref="U1", l298n_component=_l298n_component(ena_net, enb_net))
        lang_manager.set_language("it")
        dlg_it = wdd._L298nJumperInfoDialog(
            None, ref="U1", l298n_component=_l298n_component(ena_net, enb_net))
        texts_fr = {l.text() for l in dlg_fr.findChildren(QLabel)}
        texts_it = {l.text() for l in dlg_it.findChildren(QLabel)}
        if texts_fr == texts_it:
            failures.append(name)
    _reset_lang()
    assert not failures, f"branches non traduites : {failures}"


def test_l298n_module_variant_prescription_differs_fr_it():
    """_L293dModuleJumperInfoDialog partage la meme logique de
    prescription que le L298N (cf `_ena_enb_prescription` des deux
    classes) mais avec ses propres cles `l293d_module_*` -- verifie
    separement pour ne pas laisser cette 7e classe hors couverture."""
    from PyQt6.QtWidgets import QLabel
    l293d_comp = Component(ref="U2", type="l293d_module",
                            pins=[Pin("ENA", "D5"), Pin("ENB", "5V")])
    lang_manager.set_language("fr")
    dlg_fr = wdd._L293dModuleJumperInfoDialog(
        None, ref="U2", l293d_component=l293d_comp)
    lang_manager.set_language("it")
    dlg_it = wdd._L293dModuleJumperInfoDialog(
        None, ref="U2", l293d_component=l293d_comp)

    assert dlg_fr.windowTitle() != dlg_it.windowTitle()
    texts_fr = {l.text() for l in dlg_fr.findChildren(QLabel)}
    texts_it = {l.text() for l in dlg_it.findChildren(QLabel)}
    assert texts_fr != texts_it
    _reset_lang()


# ---------------------------------------------------------------------------
# Passe large : les 10 classes se construisent sans exception et leur titre
# differe reellement entre fr et it (les 3 sections ci-dessus creusent deja
# 4 des 10 classes en profondeur -- ceci ferme la couverture sur les 6
# restantes sans dupliquer tout le detail).
# ---------------------------------------------------------------------------

def _all_ten_factories():
    l298n_comp = _l298n_component("D5", "D6")
    l293d_comp = Component(ref="U2", type="l293d_module",
                            pins=[Pin("ENA", "D5"), Pin("ENB", "5V")])
    return {
        "_ServoExternalPowerDialog": lambda: wdd._ServoExternalPowerDialog(
            None, ref="SV1", is_external=False),
        "_LedSeriesValueDialog": lambda: wdd._LedSeriesValueDialog(
            None, ref="D1", current_value="220"),
        "_BtnPullupDialog": lambda: wdd._BtnPullupDialog(
            None, ref="BTN1", is_external=False),
        "_DhtPullupDialog": lambda: wdd._DhtPullupDialog(
            None, ref="DHT1", has_pullup=True),
        "_Ds18b20PullupDialog": lambda: wdd._Ds18b20PullupDialog(
            None, ref="DS1", current_value="4.7k"),
        "_L298nJumperInfoDialog": lambda: wdd._L298nJumperInfoDialog(
            None, ref="U1", l298n_component=l298n_comp),
        "_L293dModuleJumperInfoDialog": lambda: wdd._L293dModuleJumperInfoDialog(
            None, ref="U2", l293d_component=l293d_comp),
        "_A4988VrefInfoDialog": lambda: wdd._A4988VrefInfoDialog(
            None, ref="U3"),
        "_BuzzerSeriesValueDialog": lambda: wdd._BuzzerSeriesValueDialog(
            None, ref="BZ1", current_value="100"),
        "_MicrosteppingDialog": lambda: wdd._MicrosteppingDialog(
            None, ref="U4", current_value="1/4"),
    }


def test_all_ten_dialogs_build_and_title_differs_fr_it():
    failures = []
    for name, factory in _all_ten_factories().items():
        lang_manager.set_language("fr")
        try:
            title_fr = factory().windowTitle()
        except Exception as e:
            failures.append((name, "fr build failed", repr(e)))
            continue
        lang_manager.set_language("it")
        try:
            title_it = factory().windowTitle()
        except Exception as e:
            failures.append((name, "it build failed", repr(e)))
            continue
        if not title_fr or not title_it or title_fr == title_it:
            failures.append((name, title_fr, title_it))
    _reset_lang()
    assert not failures, failures


TESTS = [
    test_led_series_dialog_title_and_body_differ_fr_it,
    test_led_series_dialog_choices_differ_fr_it,
    test_a4988_microstep_dialog_title_and_table_differ_fr_it,
    test_a4988_microstep_dialog_choices_differ_fr_it,
    test_l298n_dialog_title_and_columns_differ_fr_it,
    test_l298n_dialog_all_four_pwm_branches_differ_fr_it,
    test_l298n_module_variant_prescription_differs_fr_it,
    test_all_ten_dialogs_build_and_title_differs_fr_it,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    # Meme motif que test_ambiguity_i18n.py / test_ambiguity_dropdown_smoke.py :
    # detruire plusieurs QDialog pendant le teardown Qt statique plante le
    # process (0xC0000409) sous Windows APRES que les assertions ont deja
    # tranche. os._exit garde le code de sortie fidele aux assertions.
    os._exit(0 if passed == len(TESTS) else 1)
