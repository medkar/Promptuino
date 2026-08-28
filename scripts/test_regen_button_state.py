"""« Modifier les choix » ne reste plus actif quand il n'y a rien a modifier
(TODO #53).

Le bouton du schema etait TOUJOURS cliquable. Sur un schema sans composant
ambigu, `_on_regenerate_clicked` re-resolvait avec `force_remodal=True`,
`collect_ambiguous` rendait une liste VIDE, aucune modale ne s'ouvrait, et le
clic se terminait sur un re-rendu identique : un bouton qui promet une action
qu'il ne rend pas.

Ce que ces tests verrouillent, et pourquoi chaque piege merite le sien :

1. Le critere repond OUI quand il y a de l'ambigu, NON quand il n'y en a pas.
2. `collect_re_editable` doit lire une netlist FRAICHEMENT ANALYSEE. Mesure du
   2026-08-17 : resoudre efface `_confidence == "low"`, donc interroger la
   netlist RESOLUE que la fenetre detient repondrait « rien a modifier » a tous
   les coups et griserait le bouton en permanence — l'inverse exact du but.
3. Le peel-off servo : un servo nomme dans le prompt est resolu en silence et
   n'atteint jamais la modale. Il est donc ambigu ET non re-editable ; sans ce
   cas, le bouton resterait actif sur un sketch dont la seule ambiguite est un
   servo, c'est-a-dire le bug d'origine sous un autre visage.
4. Le predicat servo est PARTAGE avec `studio_view._resolve_wiring_netlist`.
   Deux copies ecrites a la main derivraient, et la derive rendrait le bouton
   menteur precisement dans le cas 3.

Run : python scripts/test_regen_button_state.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.wiring.ambiguity_dialog import (
    apply_saved_resolution, collect_ambiguous, collect_re_editable,
    is_silently_resolved_servo,
)
from ui.wiring.layout.pipeline import analyze_netlist

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


def test_ambiguous_sketch_has_choices_to_edit():
    n = analyze_netlist(CODE_AMBIGU, "uno")
    assert collect_re_editable(n), (
        "deux sorties nues doivent etre re-editables"
    )


def test_unambiguous_sketch_has_nothing_to_edit():
    n = analyze_netlist(CODE_CERTAIN, "uno")
    assert not collect_re_editable(n), (
        "un servo detecte par signature n'a rien a re-decider"
    )


def test_resolving_empties_the_criterion_so_it_needs_a_FRESH_netlist():
    """Le piege central du #53, mesure plutot que suppose.

    Si le critere lisait la netlist que la fenetre detient (deja resolue), il
    repondrait « rien » systematiquement.
    """
    n = analyze_netlist(CODE_AMBIGU, "uno")
    avant = collect_re_editable(n)
    assert avant, "pre-condition : il y a bien de l'ambigu avant resolution"
    for c in list(avant):
        apply_saved_resolution(c, "buzzer", n)
    assert not collect_re_editable(n), (
        "resoudre efface `_confidence=low` : c'est PRECISEMENT pourquoi le "
        "critere doit re-analyser le code au lieu de lire la netlist resolue"
    )


def test_prompt_named_servo_is_ambiguous_but_NOT_re_editable():
    """Le peel-off servo doit etre predit, sinon le bouton ment.

    On annote une sortie nue comme le fait le detecteur quand le prompt nomme
    un servo : elle reste `_confidence == "low"` (donc dans `collect_ambiguous`)
    mais le resolveur la pele avant la modale.
    """
    n = analyze_netlist(CODE_AMBIGU, "uno")
    amb = collect_ambiguous(n)
    assert len(amb) == 2, f"pre-condition : 2 ambigus, vu {len(amb)}"
    for c in amb:
        c.attributes["_prompt_suggested_type"] = "servo"
    assert collect_ambiguous(n), "toujours ambigus au sens du detecteur"
    assert not collect_re_editable(n), (
        "un servo nomme dans le prompt n'atteint jamais la modale : le bouton "
        "doit etre grise"
    )


def test_partial_servo_annotation_keeps_the_others_editable():
    n = analyze_netlist(CODE_AMBIGU, "uno")
    amb = collect_ambiguous(n)
    amb[0].attributes["_prompt_suggested_type"] = "servo"
    restants = collect_re_editable(n)
    assert len(restants) == 1, f"1 attendu, vu {len(restants)}"
    assert restants[0].ref == amb[1].ref


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
    test_ambiguous_sketch_has_choices_to_edit,
    test_unambiguous_sketch_has_nothing_to_edit,
    test_resolving_empties_the_criterion_so_it_needs_a_FRESH_netlist,
    test_prompt_named_servo_is_ambiguous_but_NOT_re_editable,
    test_partial_servo_annotation_keeps_the_others_editable,
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
