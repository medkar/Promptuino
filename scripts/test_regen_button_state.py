"""L'etat du bouton « Modifier les composants » du schema.

⚠️ **LE CRITERE A CHANGE LE 2026-08-29, et ce fichier avec lui.**

Ce bouton s'appelait « Modifier les choix » et rouvrait la modale
d'AMBIGUITE : son etat suivait `collect_re_editable`, c'est-a-dire les seuls
composants incertains. Deux manques, signales en QA :

- on ne pouvait pas revenir sur un composant reconnu AVEC CERTITUDE, alors
  que son engrenage, lui, le permet depuis toujours ;
- avec deux fonctionnalites ambigues generees a la suite, la premiere cessait
  d'etre joignable par ce bouton.

Il ouvre desormais TOUS les composants corrigibles du schema
(`collect_all_editable`), et son etat suit la meme regle. `collect_re_editable`
n'avait plus d'appelant : supprimee plutot que laissee a ressembler a du code
vivant.

Ce que le TODO #53 avait etabli et qui RESTE vrai : un bouton ne doit pas
promettre une action qu'il ne rend pas. Le critere a change, pas la regle --
il est grise quand le schema n'offre rien a modifier.

⚠️ Reste aussi, et pour une raison qui n'a rien a voir avec le bouton : le
peel-off servo. Un servo nomme dans le prompt est resolu en SILENCE et
n'atteint jamais la modale ; `studio_view` doit UTILISER
`is_silently_resolved_servo` et non le recopier.

Run : python scripts/test_regen_button_state.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Qt est requis : `collect_all_editable` s'appuie sur `gear_menu_editable`,
# qui vit dans le module de la fenetre du schema.
from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

from ui.wiring.ambiguity_dialog import (  # noqa: E402
    apply_saved_resolution, collect_all_editable, collect_ambiguous,
    is_silently_resolved_servo,
)
from ui.wiring.layout.pipeline import analyze_netlist  # noqa: E402

# Deux sorties digitales nues : le detecteur ne peut pas savoir si ce sont des
# LED, des buzzers ou des relais -> deux composants `_confidence == "low"`.
CODE_AMBIGU = """
const int PIN_A = 3;
const int PIN_B = 5;
void setup() { pinMode(PIN_A, OUTPUT); pinMode(PIN_B, OUTPUT); }
void loop() { digitalWrite(PIN_A, HIGH); delay(500); digitalWrite(PIN_B, LOW); }
"""

# Un servo via `Servo.h` : signature UNIQUE, donc reconnu sans ambiguite.
CODE_CERTAIN = """
#include <Servo.h>
Servo s;
void setup() { s.attach(9); }
void loop() { s.write(90); delay(1000); s.write(0); delay(1000); }
"""


def test_an_ambiguous_sketch_has_components_to_edit():
    n = analyze_netlist(CODE_AMBIGU, "uno")
    assert collect_all_editable(n), "deux sorties nues sont modifiables"


def test_a_recognized_component_is_editable_TOO():
    """LE changement du 2026-08-29. Un servo reconnu par sa signature n'a
    aucune ambiguite a lever -- l'ancien bouton le laissait donc hors de
    portee. Mais il porte un engrenage dans le schema, donc il est
    modifiable, donc il doit etre dans cette liste."""
    n = analyze_netlist(CODE_CERTAIN, "uno")
    trouves = collect_all_editable(n)
    assert trouves, "un servo reconnu doit rester modifiable"
    assert any(c.type == "servo" for c in trouves), \
        [(c.ref, c.type) for c in trouves]


def test_resolving_does_not_empty_the_criterion():
    """Contre-epreuve du piege du #53, retournee.

    L'ancien critere se VIDAIT a la resolution (elle efface
    `_confidence == "low"`), ce qui obligeait a re-analyser le code a chaque
    fois. Le nouveau ne depend pas de l'incertitude : une fois les choix
    faits, les composants restent modifiables -- c'est exactement ce que
    l'utilisateur demandait.
    """
    n = analyze_netlist(CODE_AMBIGU, "uno")
    avant = collect_ambiguous(n)
    assert len(avant) == 2, f"pre-condition : 2 ambigus, vu {len(avant)}"
    for c in list(avant):
        apply_saved_resolution(c, "buzzer", n)
    assert not collect_ambiguous(n), "resoudre efface bien `_confidence=low`"
    assert len(collect_all_editable(n)) >= 2, \
        "les composants resolus doivent rester modifiables"


def test_infrastructure_stays_out():
    """Resistance de limitation, pile, driver deduit : l'utilisateur ne les a
    pas choisis, il n'a pas a les corriger (regle du TODO #62)."""
    n = analyze_netlist(CODE_AMBIGU, "uno")
    for c in collect_ambiguous(n):
        apply_saved_resolution(c, "led", n)   # ajoute des R serie
    types = {c.type for c in collect_all_editable(n)}
    assert "resistor" not in types, types


def test_servo_predicate_is_shared_with_the_resolver():
    """Garde de derive : le resolveur doit UTILISER le predicat, pas le recopier.

    `studio_view` a longtemps ecrit le test en clair. Si quelqu'un le reecrit a
    la main, le bouton et le clic se remettront a diverger — c'est exactement
    ce que le #53 corrige.
    """
    src = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")
    assert "is_silently_resolved_servo(c)" in src, (
        "studio_view doit appeler is_silently_resolved_servo"
    )
    assert '_prompt_suggested_type") == "servo"' not in src, (
        "le predicat servo est recopie a la main dans studio_view"
    )


def test_predicate_reads_the_annotation():
    n = analyze_netlist(CODE_AMBIGU, "uno")
    c = collect_ambiguous(n)[0]
    assert not is_silently_resolved_servo(c)
    c.attributes["_prompt_suggested_type"] = "servo"
    assert is_silently_resolved_servo(c)
    c.attributes["_prompt_suggested_type"] = "dc_motor"
    assert not is_silently_resolved_servo(c), (
        "un moteur DC suggere par le prompt reste re-editable : le resolveur "
        "ne le pele pas, il l'applique ET le persiste"
    )


def test_the_four_languages_have_the_disabled_tooltip():
    from ui.wiring.wiring_diagram_dialog import _DIALOG_LABELS
    entry = _DIALOG_LABELS.get("btn_regenerate_none")
    assert entry is not None, "cle du libelle grise absente"
    for code in ("fr", "en", "es", "it"):
        assert entry.get(code, "").strip(), f"libelle grise manquant en {code}"


TESTS = [
    test_an_ambiguous_sketch_has_components_to_edit,
    test_a_recognized_component_is_editable_TOO,
    test_resolving_does_not_empty_the_criterion,
    test_infrastructure_stays_out,
    test_servo_predicate_is_shared_with_the_resolver,
    test_predicate_reads_the_annotation,
    test_the_four_languages_have_the_disabled_tooltip,
]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            print(f"  ERR  {t.__name__}: {type(e).__name__}: {e}")
    total = len(TESTS)
    print(f"\n{total - failed}/{total} test(s) au vert")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
