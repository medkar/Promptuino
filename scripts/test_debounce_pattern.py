"""#90 : le motif d'anti-rebond est injecte quand la demande le reclame.

Le defaut, mesure le 2026-08-31 en QUATRE configurations (`gemma4:e2b`) :
demande seule 0/4, en ajout 3/5, apres consigne ciblee 4/5, apres fusion
5/5 -- le modele ecrit un anti-rebond qui compte ZERO appui. Toujours le
meme bug : une condition de front en TROP (`if (lastButtonState == HIGH)`)
sur une variable que le bloc precedent vient d'aligner, ce qui rend
l'increment inatteignable. Ca compile, le schema est juste, et rien ne le
dit -- un debutant qui demande << compte les appuis >> recoit un programme
qui ne compte rien.

Et le pipeline ne lui donnait AUCUN appui : la garde << composant de base >>
coupe le retrieval sur ces prompts (un bouton n'a besoin d'aucune
bibliotheque), et l'entree corpus `onebutton` n'a pas d'anti-rebond dans son
exemple.

Le remede suit EXACTEMENT le precedent du scanner I2C : injection
DETERMINISTE d'un exemple canonique, sans seuil, dans la branche AVANT la
garde -- qu'il contourne donc par construction, sans la modifier. La garde
repond a une autre question (<< ce composant a-t-il besoin d'une lib ? >>) et
reste entiere.

⚠️ Ce que ces tests verrouillent en priorite : le **taux de faux positifs**
du declencheur. Injecter un anti-rebond dans un prompt qui n'en a pas
besoin ajouterait du bruit a chaque generation -- et le cas benin est
VALIDE en QA AE1 (<< joue une note tant que le bouton est appuye >> lit un
ETAT, pas un evenement).
"""
from __future__ import annotations
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import rag  # noqa: E402
from ui.rag import _DEBOUNCE_PATTERN_REF, _prompt_needs_debounce  # noqa: E402

# Prompts qui reclament la detection d'un EVENEMENT d'appui.
_OUI = (
    "compte les appuis sur un bouton avec anti-rebond",
    "allume une LED quand le bouton a ete appuye 3 fois",
    "change de mode a chaque appui sur le bouton",
    "combien de fois le bouton a ete appuye",
    "count the button presses and light a LED after 3 presses",
    "cuenta las pulsaciones del boton",
    "conta le pressioni del pulsante",
)
# Prompts qui lisent un ETAT, ou qui ne parlent pas de bouton du tout.
_NON = (
    "allume la LED interne quand le bouton est appuye",
    "joue une note sur un buzzer tant que le bouton est appuye",
    "turn on the LED when the button is pressed",
    "the buzzer sounds while the button is pressed",
    "light the LED while the button is held",
    "fais clignoter une LED toutes les secondes",
    "lis la temperature d'un DHT11 et affiche-la",
    "compte le nombre de tours du moteur",
    "affiche la distance mesuree par un HC-SR04",
    "ajoute un bouton qui demarre la melodie",
)


def test_no_false_positive_on_state_reading_prompts():
    """LA garde. << tant que le bouton est appuye >> lit un ETAT : ce cas
    marche deja (QA AE1) et ne doit rien recevoir."""
    fautifs = [p for p in _NON if _prompt_needs_debounce(p)]
    assert not fautifs, fautifs


def test_it_fires_on_event_detection_prompts():
    manques = [p for p in _OUI if not _prompt_needs_debounce(p)]
    assert not manques, manques


def test_both_cue_groups_are_required():
    """Sans bouton, << compte le nombre de tours >> n'a rien a voir ; sans
    evenement, un bouton simple n'a pas besoin du motif."""
    assert not _prompt_needs_debounce("compte le nombre de passages")
    assert not _prompt_needs_debounce("un bouton sur la broche 2")
    assert _prompt_needs_debounce("compte les appuis du bouton")


# ── le motif lui-meme ────────────────────────────────────────────────────

def _compte(loop_body, delai=50):
    """Simule le motif sur 3 appuis nets de 200 ms (boucle a 1 ms)."""
    HIGH, LOW = 1, 0
    seq, t = [], 0
    for _ in range(3):
        for _ in range(300): seq.append((t, HIGH)); t += 1
        for _ in range(200): seq.append((t, LOW)); t += 1
    return loop_body(seq, HIGH, LOW, delai)


def _motif_injecte(seq, HIGH, LOW, delai):
    """Transcription FIDELE du motif de `_DEBOUNCE_PATTERN_REF`."""
    pressCount = 0
    buttonState, lastReading, lastDebounceTime = HIGH, HIGH, 0
    for t, reading in seq:
        if reading != lastReading:
            lastDebounceTime = t
        if t - lastDebounceTime > delai:
            if reading != buttonState:
                buttonState = reading
                if buttonState == LOW:
                    pressCount += 1
        lastReading = reading
    return pressCount


def test_the_injected_pattern_actually_counts():
    """Le coeur du ticket : le motif doit COMPTER. Toutes les variantes que
    le modele ecrivait de lui-meme comptaient 0 tout en ressemblant a un
    anti-rebond -- d'ou une verification par SIMULATION, jamais par la
    forme."""
    assert _compte(_motif_injecte) == 3


def test_the_pattern_has_no_extra_edge_condition():
    """L'erreur exacte du modele, verrouillee : une condition de front
    SUPPLEMENTAIRE sur la derniere lecture rend l'increment inatteignable
    (`buttonState` vient d'etre aligne juste au-dessus)."""
    ex = _DEBOUNCE_PATTERN_REF["example_code"]
    assert "lastButtonState == HIGH" not in ex, ex
    # ... et il porte bien les deux etages qui le rendent correct.
    assert "reading != lastReading" in ex
    assert "reading != buttonState" in ex
    assert "buttonState == LOW" in ex


def test_the_pattern_declares_no_library():
    """C'est un MOTIF, pas une bibliotheque : aucun `#include`, aucun
    en-tete. Le prendre pour une lib ferait mentir la banniere et le
    bandeau de composants."""
    assert _DEBOUNCE_PATTERN_REF["headers"] == []
    assert "#include" not in _DEBOUNCE_PATTERN_REF["example_code"]


# ── le fil jusqu'au contexte injecte ─────────────────────────────────────

def test_the_context_carries_the_pattern_and_bypasses_the_basic_guard():
    """Test de FIL : la garde << composant de base >> renvoie VIDE sur ces
    prompts (un bouton n'a besoin d'aucune lib). Le court-circuit vit dans
    la branche AVANT elle -- sans quoi rien ne serait injecte, ce qui etait
    l'etat mesure avant ce ticket."""
    from ui.rag import _prompt_is_basic_component
    p = "compte les appuis sur un bouton avec anti-rebond"
    # La garde matcherait bien ce prompt : c'est elle qu'on contourne.
    assert _prompt_is_basic_component(p), "le prompt ne teste plus la garde"
    ctx = rag.build_lib_context(p)
    assert "Anti-rebond" in ctx, ctx[:200]
    assert "reading != buttonState" in ctx, ctx[:400]


def test_a_state_reading_prompt_still_gets_nothing():
    """Le pendant : le cas benin de la QA AE1 ne doit RIEN recevoir."""
    ctx = rag.build_lib_context(
        "joue une note sur un buzzer tant que le bouton est appuye")
    assert "Anti-rebond" not in ctx, ctx[:200]


TESTS = [
    test_no_false_positive_on_state_reading_prompts,
    test_it_fires_on_event_detection_prompts,
    test_both_cue_groups_are_required,
    test_the_injected_pattern_actually_counts,
    test_the_pattern_has_no_extra_edge_condition,
    test_the_pattern_declares_no_library,
    test_the_context_carries_the_pattern_and_bypasses_the_basic_guard,
    test_a_state_reading_prompt_still_gets_nothing,
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
