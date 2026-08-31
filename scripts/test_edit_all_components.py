"""« Modifier les composants » ouvre TOUT le schéma, pas les seules ambiguïtés.

Demandé le 2026-08-29. Le bouton s'appelait « Modifier les choix » et rouvrait
la modale d'AMBIGUÏTÉ : il ne montrait donc que les composants incertains.
Deux manques :

- un composant reconnu **avec certitude** n'y était jamais joignable, alors
  que son engrenage le permet depuis toujours ;
- avec deux fonctionnalités ambiguës générées à la suite, la première cessait
  d'être atteignable par ce bouton.

Les trois portes ont désormais chacune leur population, et ce fichier vérifie
qu'elles ne se confondent pas :

| porte | ce que le rail contient |
|---|---|
| ouverture automatique du schéma | les composants **ambigus** — c'est une question |
| engrenage → « Modifier ce composant… » | **ce composant seul** |
| « Modifier les composants » | **tout ce qui porte un engrenage** |

⚠️ Le critère de la 3ᵉ porte est `gear_menu_editable`, celui-là même qui
décide des engrenages du schéma — jamais une seconde règle écrite à côté, qui
finirait par diverger.

NB : un seul StudioView par process (contrainte Qt, cf.
`test_scoped_edit_persistence.py`), donc ce fichier enchaîne ses portes sur la
même instance.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BOARD = "arduino_uno_r3"

# Deux sorties nues (deux ambiguïtés) PLUS un servo reconnu par sa signature.
# Le servo est le témoin : l'ancien bouton ne le montrait jamais.
CODE = """
#include <Servo.h>
Servo monServo;
const int S1 = 4;
const int S2 = 5;

void setup() {
  pinMode(S1, OUTPUT);
  pinMode(S2, OUTPUT);
  monServo.attach(9);
}
void loop() {
  digitalWrite(S1, HIGH); delay(200); digitalWrite(S1, LOW);
  digitalWrite(S2, HIGH); delay(200); digitalWrite(S2, LOW);
  monServo.write(90);
}
"""

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
    # Reference gardee au niveau module : sans elle, l'app temporaire est
    # GC-ee et construire un QWidget ensuite crashe le process (0xC0000409).
    _APP = QApplication.instance() or QApplication([])
except Exception:
    _HAS_QT = False


def test_the_three_doors_show_three_different_populations():
    from ui.studio_view import StudioView
    from ui.wiring import ambiguity_dialog as ad
    import ui.declared_components as declared_components

    declared_components.set_registry([])
    sv = StudioView()
    vrai_exec = ad.AmbiguityDialog.exec
    vu: dict = {}

    def _espion(cle, reponse):
        def _exec(self):
            vu[cle] = {
                "refs": [c.ref for c in self._ambiguous],
                "types": [c.type for c in self._ambiguous],
                "lignes": len(self._rail_rows),
            }
            if reponse is self.DialogCode.Accepted:
                for c in self._ambiguous:
                    self._chosen_type.setdefault(c.ref, "relay")
            return reponse
        return _exec

    # ── porte 1 : ouverture automatique -> les AMBIGUS seulement ─────────
    ad.AmbiguityDialog.exec = _espion("auto",
                                      ad.AmbiguityDialog.DialogCode.Accepted)
    try:
        nl = sv._resolve_wiring_netlist(CODE, BOARD, "", "", {})
    finally:
        ad.AmbiguityDialog.exec = vrai_exec
    assert nl is not None, "modale de generation annulee a tort"
    assert "auto" in vu, "aucune modale a l'ouverture"
    assert set(vu["auto"]["types"]) == {"led"}, vu["auto"]["types"]
    assert len(vu["auto"]["refs"]) == 2, vu["auto"]["refs"]

    servo = next((c for c in nl.components if c.type == "servo"), None)
    assert servo is not None, [(c.ref, c.type) for c in nl.components]

    # ── porte 2 : l'engrenage -> CE composant seul ──────────────────────
    ad.AmbiguityDialog.exec = _espion("engrenage",
                                      ad.AmbiguityDialog.DialogCode.Rejected)
    try:
        sv._resolve_wiring_netlist(CODE, BOARD, "", "", {},
                                   force_remodal=True,
                                   scoped_to_ref=servo.ref)
    finally:
        ad.AmbiguityDialog.exec = vrai_exec
    assert vu["engrenage"]["refs"] == [servo.ref], vu["engrenage"]["refs"]
    assert vu["engrenage"]["lignes"] == 1, vu["engrenage"]["lignes"]

    # ── porte 3 : « Modifier les composants » -> TOUT ────────────────────
    ad.AmbiguityDialog.exec = _espion("tous",
                                      ad.AmbiguityDialog.DialogCode.Rejected)
    try:
        sv._resolve_wiring_netlist(CODE, BOARD, "", "", {}, force_remodal=True)
    finally:
        ad.AmbiguityDialog.exec = vrai_exec

    types = vu["tous"]["types"]
    assert "servo" in types, (
        "le composant RECONNU doit etre joignable ici -- c'est tout l'objet "
        "du changement : %r" % (types,))
    assert len(vu["tous"]["refs"]) >= 3, vu["tous"]["refs"]
    assert vu["tous"]["lignes"] == len(vu["tous"]["refs"]), vu["tous"]
    # Et l'infrastructure reste dehors : la resistance serie d'une LED n'est
    # pas un choix de l'utilisateur (regle du TODO #62).
    assert "resistor" not in types, types

    # ── la garde qui tient tout : les trois portes different ─────────────
    assert len(vu["engrenage"]["refs"]) < len(vu["auto"]["refs"]) \
        < len(vu["tous"]["refs"]), {k: v["refs"] for k, v in vu.items()}


TESTS = [test_the_three_doors_show_three_different_populations]


def main() -> None:
    if not _HAS_QT:
        print("SKIP (PyQt6 absent)")
        os._exit(0)
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception as exc:
            print(f"FAIL {t.__name__}: {exc}")
            failed += 1
    print("OK" if not failed else f"{failed} failed")
    # Teardown Qt statique apres un vrai StudioView : os._exit reflete les
    # assertions, pas un crash de destruction.
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
