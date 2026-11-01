"""Changer de driver = changer de puce : l'offre de regeneration.

Constat C4 de la spec << certitude d'abord >>, mesure le 2026-08-29 : le choix
de driver etait persiste EN SILENCE (cle `::_driver`). Passer d'un L298N a un
DRV8833 changeait le schema et laissait le code en l'etat, sans que rien ne le
dise -- alors que la divergence est REELLE meme sans bibliotheque : le code
broches-nues d'un TB6612 a un STBY, celui d'un DRV8833 un SLEEP, celui d'un
L298N un ENA.

Le mecanisme d'offre existait deja pour les puces (`_pending_regen_swap`,
consomme a la fermeture du schema). Il ne pouvait simplement pas s'appliquer
aux drivers : `_chip_swap_regen_target` rendait `None` pour tous leurs
couples, faute de correspondance type -> corpus -- corrige a la tache 1.

⚠️ Un seul StudioView par process (contrainte Qt, cf.
`test_scoped_edit_persistence.py`), donc ce fichier enchaine ses passes sur la
meme instance, dans un ordre qui compte.
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

# Broches NUES : deux moteurs deduits par heuristique (niveau 3). C'est LA que
# le choix de driver se fait a la main, donc la que le swap doit s'offrir.
CODE = """
const int ENA = 3;
const int IN1 = 4;
const int IN2 = 5;
const int ENB = 9;
const int IN3 = 10;
const int IN4 = 11;
void setup() {
  pinMode(ENA, OUTPUT); pinMode(IN1, OUTPUT); pinMode(IN2, OUTPUT);
  pinMode(ENB, OUTPUT); pinMode(IN3, OUTPUT); pinMode(IN4, OUTPUT);
}
void moteurA(int v){ digitalWrite(IN1,HIGH); digitalWrite(IN2,LOW); analogWrite(ENA,v); }
void moteurB(int v){ digitalWrite(IN3,HIGH); digitalWrite(IN4,LOW); analogWrite(ENB,v); }
void loop(){ moteurA(200); moteurB(150); }
"""

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
    # Reference gardee au niveau module : sans elle l'app temporaire est GC-ee
    # et construire un QWidget ensuite crashe le process (0xC0000409).
    _APP = QApplication.instance() or QApplication([])
except Exception:
    _HAS_QT = False


class _Feature:
    """`_feature_for_chip_swap` ne lit qu'un `.id` quand il n'y en a qu'une
    seule : inutile de fabriquer une vraie Feature ici."""

    id = "fn-1"


def _arme(sv):
    """La regeneration armee, ou None. Lue par `getattr` comme le fait le code
    de production : l'attribut n'existe qu'une fois pose."""
    return getattr(sv, "_pending_regen_swap", None)


def _drivers(sv) -> list[str]:
    return [v for k, v in sv._wiring_resolutions.items()
            if k[1].endswith("::_driver")]


def test_changing_the_driver_offers_a_regeneration():
    from ui.studio_view import StudioView
    from ui.wiring import ambiguity_dialog as ad
    import ui.declared_components as declared_components

    declared_components.set_registry([])
    sv = StudioView()
    vrai_exec = ad.AmbiguityDialog.exec
    demandes: list = []
    sv._confirm_regen_after_swap = (
        lambda a, b: (demandes.append((a, b)), True)[1])

    def _choisir(driver, force=False):
        def _exec(self):
            refs = [c.ref for c in self._ambiguous
                    if c.attributes.get("_grouped_pwm_pin")]
            assert refs, "pre-condition : des moteurs groupes"
            self._on_shared_driver_toggled(refs, driver)
            return self.DialogCode.Accepted
        ad.AmbiguityDialog.exec = _exec
        try:
            sv._resolve_wiring_netlist(CODE, BOARD, "", "", {},
                                       force_remodal=force)
        finally:
            ad.AmbiguityDialog.exec = vrai_exec

    # ── 1. premier choix : rien ne CHANGE encore, donc aucune offre ───────
    _choisir("l298n")
    assert demandes == [], (
        "un premier choix n'est pas un changement : %r" % (demandes,))
    assert _arme(sv) is None
    assert _drivers(sv) and all(d == "l298n" for d in _drivers(sv)), \
        sv._wiring_resolutions

    # ── 2. on change, mais SANS fonctionnalite ────────────────────────────
    # Rien a regenerer, donc rien a proposer. Ce n'est pas un trou : l'offre
    # cible une fonctionnalite, et ce montage n'en a aucune.
    demandes.clear()
    _choisir("drv8833", force=True)
    assert demandes == [], (
        "sans fonctionnalite, il n'y a rien a regenerer : %r" % (demandes,))
    assert _arme(sv) is None
    assert all(d == "drv8833" for d in _drivers(sv)), sv._wiring_resolutions

    # ── 3. avec une fonctionnalite, l'offre part ──────────────────────────
    sv._features = [_Feature()]
    demandes.clear()
    _choisir("l298n", force=True)
    assert demandes, "changer de driver doit proposer la regeneration"
    assert demandes == [("drv8833", "l298n")], (
        "UNE seule offre, meme si les deux moteurs d'un pont en H double "
        "changent ensemble : %r" % (demandes,))
    assert _arme(sv) is not None, "l'acceptation doit armer la regeneration"
    assert _arme(sv)[1:] == ("drv8833", "l298n"), _arme(sv)
    assert all(d == "l298n" for d in _drivers(sv)), sv._wiring_resolutions

    # ── 4. on REFUSE : le schema suit, le code attend ─────────────────────
    sv._pending_regen_swap = None
    demandes.clear()
    sv._confirm_regen_after_swap = (
        lambda a, b: (demandes.append((a, b)), False)[1])
    _choisir("tb6612fng", force=True)
    assert demandes == [("l298n", "tb6612fng")], demandes
    assert _arme(sv) is None, "refuser ne doit RIEN regenerer"
    assert all(d == "tb6612fng" for d in _drivers(sv)), (
        "le schema suit le nouveau driver meme si le code n'est pas "
        "regenere -- meme tension assumee que pour les puces : %r"
        % (sv._wiring_resolutions,))


TESTS = [test_changing_the_driver_offers_a_regeneration]


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
