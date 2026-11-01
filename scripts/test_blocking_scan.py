"""#89 : une fonctionnalite qui `delay()` fige la boucle ENTIERE, donc toutes
les autres (2026-08-31).

Trouve en jouant la QA AE2 du #88, sur un sketch reel, et PAS predit : la
procedure verifiait l'assemblage, le defaut est ailleurs. Projet a trois
fonctionnalites, assemblage EXACT, chaque bloc idiomatique -- et pourtant un
appui bref sur le bouton ne fait plus rien, parce que le clignotement fige la
carte 2 s a chaque tour.

Mesures qui ont decide du remede (gemma4:e2b, conditions de l'app) :
  - **6 fonctionnalites sur 8 bloquent** la boucle, mediane **2 000 ms**,
    et 3 sur 8 depassent 200 ms -- ce n'est pas un cas limite, et les trois
    plus lourdes (clignotement, affichage capteur, affichage LCD) sont les
    compagnons les plus naturels d'un bouton ;
  - la CONVERSION rend **3/3** un code qui compile, sans blocage restant ni
    attente active. Defaut frequent ET remede qui marche : les deux
    conditions pour meriter une offre.

Choix produit de l'utilisateur : **avertir + proposer la conversion**. Le
code par defaut reste en `delay()` (simple et lisible pour un debutant) ;
l'app ne parle QUE quand le conflit existe reellement.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.blocking_scan import (  # noqa: E402
    BLOCKING_THRESHOLD_MS, blocking_ms, find_conflict, non_blocking_directive,
    reads_an_input,
)
from ui.generation.feature_model import Feature  # noqa: E402


def _bouton():
    return Feature(id="fn-1", prompt="allume la LED quand le bouton est appuye",
                   loop_lines=["int etat = digitalRead(2);",
                               "if (etat == LOW) {",
                               "  digitalWrite(13, HIGH);", "}"])


def _clignotant(ms=1000):
    return Feature(id="fn-2", prompt="fais clignoter une LED",
                   loop_lines=["digitalWrite(6, HIGH);", f"delay({ms});",
                               "digitalWrite(6, LOW);", f"delay({ms});"])


# ── mesure du blocage ────────────────────────────────────────────────────

def test_blocking_ms_sums_the_literal_delays():
    assert blocking_ms(_clignotant(1000)) == 2000
    assert blocking_ms(_bouton()) == 0


def test_microseconds_count_but_stay_negligible():
    """Un HC-SR04 fait `delayMicroseconds(10)` : compte, mais ne doit pas
    faire franchir un seuil exprime en millisecondes."""
    f = Feature(id="x", prompt="p",
                loop_lines=["delayMicroseconds(10);", "delayMicroseconds(2);"])
    assert blocking_ms(f) == 0


def test_a_delay_in_setup_does_not_count():
    """`setup()` ne tourne qu'une fois : il ne degrade la reactivite de
    personne."""
    f = Feature(id="x", prompt="p", setup_lines=["delay(3000);"],
                loop_lines=["digitalWrite(6, HIGH);"])
    assert blocking_ms(f) == 0


def test_reading_an_input_is_what_makes_a_victim():
    assert reads_an_input(_bouton())
    assert not reads_an_input(_clignotant())
    assert reads_an_input(Feature(id="x", prompt="p",
                                  loop_lines=["int v = analogRead(A0);"]))


# ── le conflit ───────────────────────────────────────────────────────────

def test_the_real_case_from_qa_ae2():
    c = find_conflict([_bouton(), _clignotant()])
    assert c is not None
    assert (c.blocker_id, c.blocker_ms, c.victim_ids) == ("fn-2", 2000, ("fn-1",))


def test_a_lone_feature_is_never_a_conflict():
    """Un clignotement seul n'a personne a degrader : il MARCHE."""
    assert find_conflict([_clignotant()]) is None


def test_no_victim_no_conflict():
    """Deux fonctionnalites bloquantes mais aucune ne lit d'entree : rien a
    denoncer -- personne n'attend de reponse."""
    a, b = _clignotant(), _clignotant()
    b.id = "fn-3"
    assert find_conflict([a, b]) is None


def test_a_feature_is_not_its_own_victim():
    """Une fonctionnalite qui lit une entree ET se bloque elle-meme n'est
    pas en conflit : c'est son propre rythme, choisi."""
    f = Feature(id="fn-1", prompt="p",
                loop_lines=["int v = analogRead(A0);", "Serial.println(v);",
                            "delay(2000);"])
    autre = Feature(id="fn-2", prompt="p", loop_lines=["digitalWrite(6, HIGH);"])
    assert find_conflict([f, autre]) is None


def test_a_short_delay_stays_silent():
    """Sous le seuil, on se tait : un servo qui fait `delay(15)` entre deux
    pas ne casse la reactivite de personne."""
    court = Feature(id="fn-2", prompt="p",
                    loop_lines=["monServo.write(a);", "delay(15);"])
    assert blocking_ms(court) < BLOCKING_THRESHOLD_MS
    assert find_conflict([_bouton(), court]) is None


def test_the_worst_blocker_is_the_one_reported():
    petit = Feature(id="fn-2", prompt="p", loop_lines=["delay(300);"])
    gros = Feature(id="fn-3", prompt="p", loop_lines=["delay(5000);"])
    c = find_conflict([_bouton(), petit, gros])
    assert c is not None and c.blocker_id == "fn-3", c


# ── la consigne de conversion ────────────────────────────────────────────

def test_the_directive_forbids_the_busy_wait():
    """Sans cette interdiction, le modele remplace `delay` par
    `while (millis() - t < N) {}` -- qui bloque tout autant."""
    d = non_blocking_directive().lower()
    assert "millis" in d
    assert "busy-wait" in d or "busy wait" in d
    # Le comportement ET les durees doivent etre preserves : une conversion
    # qui change le rythme ne serait plus la meme fonctionnalite.
    assert "behavior" in d and "timings" in d


# ── le fil jusqu'a l'offre ───────────────────────────────────────────────

def test_the_offer_fires_once_and_a_refusal_is_remembered():
    """Test de FIL : un detecteur juste qui ne parle jamais (ou qui parle a
    chaque generation) ne vaut rien. On conduit la VRAIE methode du studio,
    la boite de dialogue detournee."""
    from PyQt6.QtWidgets import QApplication, QMessageBox
    global _APP
    _APP = QApplication.instance() or QApplication([])
    import ui.studio_view as sv

    v = sv.StudioView()
    v._features = [_bouton(), _clignotant()]
    v._gen_busy = None
    v._beginner_running = False
    vus, lances = [], []

    def _faux_exec(self):
        vus.append(self.windowTitle())
        return 0                      # aucun bouton cliqué == refus

    orig_exec = QMessageBox.exec
    orig_launch = sv.StudioView._launch_generation
    QMessageBox.exec = _faux_exec
    sv.StudioView._launch_generation = (
        lambda self, *a, **k: lances.append(a))
    try:
        v._offer_non_blocking_rewrite()
        assert len(vus) == 1, vus              # proposée une fois
        assert not lances, lances              # refus -> aucune régénération
        v._offer_non_blocking_rewrite()
        assert len(vus) == 1, vus              # refus mémorisé : plus rien
    finally:
        QMessageBox.exec = orig_exec
        sv.StudioView._launch_generation = orig_launch


def test_the_message_names_no_component():
    """QA AF1 (2026-08-31) : la premiere redaction disait << un appui bref sur
    un BOUTON peut etre ignore >> -- faux des que la victime est un capteur
    analogique. Le message ne doit nommer AUCUN composant : les seuls noms
    qui y figurent viennent des libelles des fonctionnalites de
    l'utilisateur, via {feature} et {victims}."""
    import re
    from ui.i18n import lang_manager
    interdits = ("bouton", "button", "boton", "pulsante", "pulsador",
                 "led", "buzzer", "capteur", "sensor", "servo")
    for lang in ("fr", "en", "es", "it"):
        lang_manager.set_language(lang)
        corps = lang_manager.current.blocking_offer_body.lower()
        for mot in interdits:
            assert not re.search(rf"\b{mot}", corps), (lang, mot)
        # ... et il porte bien les trois valeurs CALCULEES.
        for champ in ("{feature}", "{victims}", "{sec}"):
            assert champ in lang_manager.current.blocking_offer_body, (lang, champ)
    lang_manager.set_language("fr")


def test_a_refusal_does_not_leak_into_the_next_project():
    """QA AF1 : les ids de fonctionnalites sont PAR PROJET (`fn-1`, `fn-2`…),
    donc la fonctionnalite bloquante du projet suivant porte le meme id --
    un refus memorise faisait taire l'offre dans un projet ou l'utilisateur
    n'avait jamais rien refuse. Meme classe de defaut que la banniere du #61
    qui survivait au changement de projet."""
    from PyQt6.QtWidgets import QApplication
    global _APP
    _APP = QApplication.instance() or QApplication([])
    import ui.studio_view as sv

    v = sv.StudioView()
    v._blocking_offer_declined = {"fn-2"}
    v._dirty = False
    v._current_project = None
    v._begin_inline_new_project()
    assert v._blocking_offer_declined == set(), v._blocking_offer_declined


def test_the_other_project_entry_point_resets_it_too():
    """`load_project` est l'AUTRE porte (ouvrir un projet existant). Elle
    demande un vrai Project sur disque, donc on verifie la remise a zero
    dans sa source -- meme motif que les gardes de source du #44."""
    import inspect
    import ui.studio_view as sv
    src = inspect.getsource(sv.StudioView.load_project)
    assert "_blocking_offer_declined = set()" in src, \
        "load_project ne remet pas les refus a zero"


TESTS = [
    test_the_message_names_no_component,
    test_a_refusal_does_not_leak_into_the_next_project,
    test_the_other_project_entry_point_resets_it_too,
    test_blocking_ms_sums_the_literal_delays,
    test_microseconds_count_but_stay_negligible,
    test_a_delay_in_setup_does_not_count,
    test_reading_an_input_is_what_makes_a_victim,
    test_the_real_case_from_qa_ae2,
    test_a_lone_feature_is_never_a_conflict,
    test_no_victim_no_conflict,
    test_a_feature_is_not_its_own_victim,
    test_a_short_delay_stays_silent,
    test_the_worst_blocker_is_the_one_reported,
    test_the_directive_forbids_the_busy_wait,
    test_the_offer_fires_once_and_a_refusal_is_remembered,
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
