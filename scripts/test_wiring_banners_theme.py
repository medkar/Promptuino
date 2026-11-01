"""Les bandeaux d'alerte du cablage suivent le THEME (2026-08-11).

Trois bandeaux codaient leurs couleurs en hexa LITTERAL au lieu des jetons
`ColorScheme` : l'avertissement « trop de moteurs detectes » de la modale
d'ambiguite, l'invite a regrouper de la modale VISUELLE debutant, et le
repli « illustration manquante » des deux modales d'aide L298N / A4988.

Le deuxieme n'est plus verifiable : la modale visuelle a ete supprimee le
2026-08-13 (une seule modale pour tous les modes) et le bandeau « regrouper
en moteur » n'existait que la. Ses deux tests sont partis avec elle plutot
que de rester verts au-dessus de rien.

Consequence : un bandeau clair restait clair en theme sombre — texte
sombre sur fond clair au milieu d'une fenetre noire. Le repli du L298N est
le cas le plus ironique : le placeholder cense EXPLIQUER qu'une image
manque etait lui-meme illisible au moment precis ou il apparaissait.

⚠️ La branche du placeholder n'est prise QUE si l'asset SVG est absent —
donc aucun test ne la traversait, et un `NameError` y a survecu a une
suite complete au vert. Le test la force en detournant `Path.exists`.

Run : python scripts/test_wiring_banners_theme.py
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from PyQt6.QtWidgets import QFrame, QLabel, QPushButton
from ui.theme import theme_manager
from ui.wiring.netlist import Component, Netlist, Pin

# Les dialogues restent references : les detruire pendant le teardown Qt
# statique crashe le process sous Windows (0xC0000409).
_VIVANTS: list = []


def _fond(qss: str) -> str:
    """Extrait la couleur de fond d'une feuille QSS (peu importe la forme
    `background:` / `background-color:`, avec ou sans espace)."""
    m = re.search(r"background(?:-color)?\s*:\s*([^;}\s]+)", qss)
    return m.group(1) if m else ""


def _avec_theme(sombre: bool, fabrique):
    """Construit un widget dans un theme donne et rend le widget."""
    if theme_manager.is_dark != sombre:
        theme_manager.toggle()
    w = fabrique()
    _VIVANTS.append(w)
    return w


def _modale_moteurs():
    """Modale AVANCEE avec 2 moteurs groupes et une limite a 1 : c'est la
    seule configuration qui fait apparaitre le bandeau d'avertissement."""
    from ui.wiring.ambiguity_dialog import AmbiguityDialog
    comps = []
    for ref, pwm, dirs in (("D1", "D9", ["D8", "D7"]),
                           ("D2", "D10", ["D11", "D12"])):
        comps.append(Component(
            ref=ref, type="led", pins=[Pin("A", pwm), Pin("K", "GND")],
            attributes={"_confidence": "low", "_grouped_pwm_pin": pwm,
                        "_grouped_dir_pins": dirs}))
    nl = Netlist(board_id="", components=comps)
    return AmbiguityDialog(comps, netlist=nl, motors_limit=1)


def test_the_motors_limit_banner_follows_the_theme():
    dlg_sombre = _avec_theme(True, _modale_moteurs)
    fond_sombre = _fond(dlg_sombre._warn_label.styleSheet())
    dlg_clair = _avec_theme(False, _modale_moteurs)
    fond_clair = _fond(dlg_clair._warn_label.styleSheet())
    assert fond_sombre and fond_clair, (fond_sombre, fond_clair)
    assert fond_sombre != fond_clair, (
        f"le bandeau garde {fond_sombre} dans les deux themes")


def test_the_motors_limit_banner_uses_no_literal_hex():
    """Un hexa litteral peut differer entre deux themes par accident (deux
    constantes ecrites a la main). Ce test verifie la CAUSE, pas l'effet."""
    dlg = _avec_theme(True, _modale_moteurs)
    from ui.theme import DARK
    fond = _fond(dlg._warn_label.styleSheet()).lower()
    assert fond == DARK.signal_warn.lower(), (
        f"fond={fond!r}, attendu le jeton signal_warn={DARK.signal_warn!r}")


def _modale_l298n(asset_absent: bool):
    """Modale d'aide L298N. `asset_absent=True` force le repli placeholder en
    detournant `Path.exists` — la branche qu'aucun test ne traversait."""
    from ui.wiring import wiring_diagram_dialog as wdd
    comp = Component(ref="U1", type="l298n",
                     pins=[Pin("ENA", "D9"), Pin("IN1", "D8")],
                     attributes={})
    if not asset_absent:
        return wdd._L298nJumperInfoDialog(None, ref="U1", l298n_component=comp)
    vrai_exists = Path.exists

    def faux_exists(self):
        if self.suffix == ".svg" and "docs" in self.parts:
            return False
        return vrai_exists(self)

    Path.exists = faux_exists
    try:
        return wdd._L298nJumperInfoDialog(None, ref="U1",
                                          l298n_component=comp)
    finally:
        Path.exists = vrai_exists


def test_the_missing_asset_placeholder_does_not_raise():
    """LA garde du NameError. `ASSET_PLACEHOLDER_NAME` a ete reference sans
    etre defini : la suite entiere est restee au vert parce que l'asset
    existe et que la branche n'est jamais prise."""
    dlg = _avec_theme(True, lambda: _modale_l298n(asset_absent=True))
    from ui.wiring.wiring_diagram_dialog import ASSET_PLACEHOLDER_NAME
    reperes = dlg.findChildren(QLabel, ASSET_PLACEHOLDER_NAME)
    assert reperes, "le placeholder n'a pas ete construit"


def test_the_missing_asset_placeholder_follows_the_theme():
    from ui.wiring.wiring_diagram_dialog import ASSET_PLACEHOLDER_NAME
    dlg_sombre = _avec_theme(True, lambda: _modale_l298n(asset_absent=True))
    qss_sombre = dlg_sombre.styleSheet()
    dlg_clair = _avec_theme(False, lambda: _modale_l298n(asset_absent=True))
    qss_clair = dlg_clair.styleSheet()
    for q in (qss_sombre, qss_clair):
        assert f"QLabel#{ASSET_PLACEHOLDER_NAME}" in q, (
            "le placeholder n'est style nulle part")
    assert qss_sombre != qss_clair, "le placeholder ne suit pas le theme"


def test_no_literal_hex_left_in_those_two_files():
    """Garde de source : le prochain bandeau ne doit pas re-coder un hexa.
    Bornee aux `setStyleSheet` (le HTML inline et les QColor de rendu SVG
    sont d'autres mecanismes, hors sujet ici)."""
    fichiers = ("ui/wiring/ambiguity_dialog.py",
                "ui/wiring/wiring_diagram_dialog.py")
    fautifs = []
    for rel in fichiers:
        texte = (ROOT / rel).read_text(encoding="utf-8", errors="replace")
        for m in re.finditer(r"setStyleSheet\((.{0,600}?)\)\s*$",
                             texte, re.M | re.S):
            bloc = m.group(1)
            for hexa in re.findall(r"#[0-9a-fA-F]{6}\b", bloc):
                ligne = texte[:m.start()].count("\n") + 1
                fautifs.append(f"{rel}:{ligne} -> {hexa}")
    assert not fautifs, f"hexa litteral dans un setStyleSheet : {fautifs}"


TESTS = [
    test_the_motors_limit_banner_follows_the_theme,
    test_the_motors_limit_banner_uses_no_literal_hex,
    test_the_missing_asset_placeholder_does_not_raise,
    test_the_missing_asset_placeholder_follows_the_theme,
    test_no_literal_hex_left_in_those_two_files,
]

if __name__ == "__main__":
    etait_sombre = theme_manager.is_dark
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    if theme_manager.is_dark != etait_sombre:
        theme_manager.toggle()
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
