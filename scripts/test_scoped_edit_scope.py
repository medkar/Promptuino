"""L'engrenage n'ouvre QUE le composant sur lequel on a cliqué.

Relevé en QA le 2026-08-29, trois fois de suite — c'est le défaut qui a le
plus résisté. Cliquer l'engrenage d'une LED ouvrait la modale avec, dans le
rail, le groupe moteur du schéma « sans raison ». Le rail n'avait rien créé :
il a rendu visible ce que la modale recevait déjà.

Trois causes distinctes, empilées :

1. la boucle de `_resolve_wiring_netlist` se terminait par un
   `else: unresolved.append(c)` qui embarquait **tout** composant sans
   résolution sauvegardée, mode scopé compris — alors que le commentaire de
   `is_scoped_target` juste au-dessus affirmait l'inverse ;
2. `scoped_sibling_refs` était calculé **avant** la pré-passe : la cible
   apparaissait encore groupée alors que la pré-passe s'apprêtait à la
   dégrouper, et la règle des frères moteurs embarquait le groupe voisin ;
3. les groupements défaits transmis à la modale (pour que « Regrouper en
   moteur » existe sur le chemin « Modifier les choix ») recréaient une ligne
   « moteurs » dans le rail — y compris en mode scopé, où elle n'a rien à
   faire.

Le scénario ci-dessous est celui de l'utilisateur, joué en entier : deux
groupes détectés, l'un déclaré moteur, l'autre dégroupé en trois LED, puis
l'engrenage sur une de ces LED.

⚠️ Une seule exception, volontaire et vérifiée ailleurs
(`test_scoped_edit_persistence.py`) : l'engrenage d'un moteur groupé amène
aussi ses **frères moteurs**. Les modifier séparément créerait deux pilotes là
où un pont en H double n'en demande qu'un.

NB : un seul StudioView par process — en construire plusieurs casse les cycles
de vie Qt (même contrainte que `test_scoped_edit_persistence.py`).
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

# Deux groupes de broches OUTPUT que le détecteur lit comme deux moteurs DC.
CODE = r"""
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
void moteurA(int v) {
  digitalWrite(IN1, HIGH); digitalWrite(IN2, LOW); analogWrite(ENA, v);
}
void moteurB(int v) {
  digitalWrite(IN3, HIGH); digitalWrite(IN4, LOW); analogWrite(ENB, v);
}
void loop() { moteurA(200); moteurB(150); }
"""

try:
    from PyQt6.QtWidgets import QApplication
    _HAS_QT = True
    # Reference gardee au niveau module : sans elle, l'app temporaire est
    # GC-ee et construire un QWidget ensuite crashe le process (0xC0000409).
    _APP = QApplication.instance() or QApplication([])
except Exception:
    _HAS_QT = False


def test_the_gear_on_a_led_shows_only_that_led():
    from ui.studio_view import StudioView
    from ui.wiring import ambiguity_dialog as ad
    import ui.declared_components as declared_components

    declared_components.set_registry([])
    sv = StudioView()
    vrai_exec = ad.AmbiguityDialog.exec

    # ── passe 1 : moteur 1 = oui, moteur 2 = non (-> 3 broches a reclasser)
    def exec_generation(self):
        self._toggle_motor_declared("D9", is_motor=False)
        refs = [c.ref for c in self._ambiguous
                if c.attributes.get("_grouped_pwm_pin")]
        self._on_shared_driver_toggled(refs, "l298n")
        for c in self._ambiguous:
            if not c.attributes.get("_grouped_pwm_pin"):
                self._chosen_type[c.ref] = "led"
        return self.DialogCode.Accepted

    ad.AmbiguityDialog.exec = exec_generation
    try:
        nl1 = sv._resolve_wiring_netlist(CODE, BOARD, "", "", {})
    finally:
        ad.AmbiguityDialog.exec = vrai_exec
    assert nl1 is not None, "modale de generation annulee a tort"
    leds = [c for c in nl1.components if c.type == "led"]
    assert len(leds) == 3, [(c.ref, c.type) for c in nl1.components]

    # ── passe 2 : l'engrenage sur UNE de ces LED ──────────────────────────
    observe: dict = {}

    def exec_engrenage(self):
        observe["recus"] = [c.ref for c in self._ambiguous]
        observe["lignes"] = [r._lbl_title.text() for r in self._rail_rows]
        observe["regrouper"] = len(self._regroup_buttons)
        return self.DialogCode.Rejected

    cible = leds[0].ref
    ad.AmbiguityDialog.exec = exec_engrenage
    try:
        sv._resolve_wiring_netlist(CODE, BOARD, "", "", {},
                                   force_remodal=True, scoped_to_ref=cible)
    finally:
        ad.AmbiguityDialog.exec = vrai_exec

    assert observe, "la modale de l'engrenage ne s'est pas ouverte"
    assert observe["recus"] == [cible], (
        "l'engrenage a embarque d'autres composants : %r" % (observe["recus"],))
    # Le RAIL est ce que l'utilisateur voit : une seule ligne, pas de groupe
    # moteur reconstitue a cote, pas de bouton « Regrouper en moteur ».
    assert len(observe["lignes"]) == 1, observe["lignes"]
    assert observe["regrouper"] == 0, observe["lignes"]


TESTS = [test_the_gear_on_a_led_shows_only_that_led]


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
    # Sous Windows + Qt offscreen, le teardown statique apres un vrai
    # StudioView crashe le process APRES les assertions. os._exit reflete les
    # assertions, pas le crash.
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
