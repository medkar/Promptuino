"""Routeur d'imbrication (TODO #88, 2026-08-31) : une demande de MODIFICATION
deguisee en ajout ouvre la modale sur << Modifier la bonne fonctionnalite >>.

Le defaut mesure : sur << le clignotement ne doit avoir lieu QUE SI
l'interrupteur est ferme >>, le contrat d'Ajout interdit au modele de toucher
au code existant -- il fabrique donc un SECOND clignotement garde pendant que
le premier reste inconditionnel (2 generations sur 2). Ca compile, et la
demande n'est pas satisfaite. Aucune regle d'assemblage ne peut rattraper ca
en aval : la demande n'est pas un ajout.

⛔ **La detection est CATEGORIELLE, jamais un score.** Le projet a deja
debranche un detecteur qui devinait par proximite semantique
(`rag._AUTO_AMBIGUITY_NET_ENABLED = False`, faux positifs incalibrables).
Deux conditions lexicales fermees : un MARQUEUR de modification (la porte),
puis un mot de contenu partage (qui ne decide rien, choisit seulement
LAQUELLE).

⚠️ **Le test qui compte est celui des FAUX POSITIFS** : un routeur qui
propose << Modifier >> sur des ajouts normaux serait une friction a chaque
generation -- exactement ce qui a tue le filet auto. La batterie ci-dessous
est deliberement plus fournie du cote des ajouts que des modifications.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.generation.add_router import (  # noqa: E402
    modification_target, prompt_asks_a_modification,
)
from ui.generation.feature_model import Feature  # noqa: E402

_F = [
    Feature(id="fn-1", prompt="fais clignoter une LED toutes les secondes",
            summary="Clignotement de la LED"),
    Feature(id="fn-2", prompt="lis la temperature d'un capteur DHT11 et affiche-la",
            summary="Lecture de temperature"),
    Feature(id="fn-3", prompt="joue une melodie sur le buzzer au demarrage",
            summary="Melodie de demarrage"),
]

# Des AJOUTS normaux, y compris ceux qui reutilisent le vocabulaire du projet
# (c'est le cas piegeux : un ajout parle forcement des memes composants).
_AJOUTS = (
    "ajoute une LED verte sur la broche 6",
    "fais clignoter une deuxieme LED sur la broche 7",
    "joue une note sur un buzzer tant que le bouton est appuye",
    "affiche la temperature sur un ecran OLED",
    "allume une LED rouge quand la luminosite descend sous 300",
    "ajoute un capteur de distance HC-SR04",
    "fais tourner un servo de 0 a 180 degres",
    "envoie la temperature sur le moniteur serie toutes les 2 secondes",
    "ajoute un bouton qui demarre la melodie",
    "mesure l'humidite avec le DHT11 et affiche-la aussi",
    "add a second LED on pin 9",
    "play a tone when the button is pressed",
    "anade un potenciometro para regular el brillo",
    "aggiungi un sensore di movimento PIR",
)


def test_no_false_positive_on_normal_additions():
    """LA garde. Un seul faux positif ici = une friction a chaque ajout."""
    fautifs = [p for p in _AJOUTS if modification_target(p, _F) is not None]
    assert not fautifs, fautifs


def test_a_conditional_addition_is_still_an_addition():
    """<< tant que le bouton est appuye >> REAGIT a un etat : c'est un ajout
    parfaitement normal, et le socle du #88 le gere. Le marqueur ne doit pas
    confondre << reagir a >> et << restreindre >>."""
    p = "joue une note sur un buzzer tant que le bouton est appuye"
    assert not prompt_asks_a_modification(p)
    assert modification_target(p, _F) is None


def test_restrictive_requests_are_routed_to_the_right_feature():
    for prompt, attendu in (
        ("le clignotement ne doit avoir lieu que si l'interrupteur est ferme", "fn-1"),
        ("fais clignoter la LED seulement quand il fait nuit", "fn-1"),
        ("n'affiche la temperature que si elle depasse 25 degres", "fn-2"),
    ):
        assert modification_target(prompt, _F) == attendu, prompt


def test_substitutive_and_imperative_requests_are_routed_too():
    for prompt, attendu in (
        ("au lieu de clignoter, la LED doit rester allumee", "fn-1"),
        ("modifie le clignotement pour qu'il soit deux fois plus rapide", "fn-1"),
        ("arrete de jouer la melodie au demarrage", "fn-3"),
    ):
        assert modification_target(prompt, _F) == attendu, prompt


def test_the_stem_bridges_the_noun_and_the_verb():
    """Le cas d'origine : la demande dit << le clignotement >>, la
    fonctionnalite dit << clignoter >>. Sans radical, aucun rattachement --
    et le routeur aurait rate precisement le cas qui l'a motive."""
    assert modification_target(
        "le clignotement ne doit avoir lieu que si l'interrupteur est ferme",
        _F) == "fn-1"


def test_a_marker_without_a_target_proposes_nothing():
    """Marqueur present mais aucun mot de contenu partage : on sait qu'il
    s'agit d'une modification, pas de QUOI. On ne propose rien plutot que de
    designer une fonctionnalite au hasard."""
    p = "le ventilateur ne doit tourner que si la pression monte"
    assert prompt_asks_a_modification(p)
    assert modification_target(p, _F) is None


def test_a_tie_proposes_nothing():
    """Deux fonctionnalites egalement plausibles : proposer la premiere de la
    liste serait un tirage au sort presente comme une deduction."""
    jumelles = [Feature(id="a", prompt="fais clignoter une LED", summary=""),
                Feature(id="b", prompt="fais clignoter une LED", summary="")]
    assert modification_target(
        "la LED ne doit clignoter que si le bouton est appuye", jumelles) is None


def test_no_features_no_proposal():
    assert modification_target("ne clignote que si x", []) is None


# ── le fil jusqu'a la modale ─────────────────────────────────────────────

def test_the_modal_opens_on_modify_with_the_right_feature_checked():
    """Test de FIL : un routeur qui calcule juste mais ne change rien a
    l'ecran ne sert a rien. On construit la VRAIE modale."""
    from PyQt6.QtWidgets import QApplication, QLabel
    global _APP
    _APP = QApplication.instance() or QApplication([])
    from ui.generation.gen_modal import GenerationModal, CORRECT

    prompt = "le clignotement ne doit avoir lieu que si l'interrupteur est ferme"
    cible = modification_target(prompt, _F)
    m = GenerationModal(_F, prompt, None, default_override=CORRECT,
                        preselect_target_id=cible, modification_hint=True)
    assert m._rb[CORRECT].isChecked(), "« Modifier » doit etre preselectionne"
    assert [fid for cb, fid in m._feat_cbs if cb.isChecked()] == ["fn-1"]
    # La presélection est EXPLIQUEE : muette, elle passerait pour arbitraire.
    textes = [l.text() for l in m.findChildren(QLabel)]
    assert any("Modifier" in t and "Ajouter" in t for t in textes), textes


def test_a_normal_addition_leaves_the_modal_on_add():
    from PyQt6.QtWidgets import QApplication, QLabel
    global _APP
    _APP = QApplication.instance() or QApplication([])
    from ui.generation.gen_modal import GenerationModal, ADD

    prompt = "ajoute une LED verte sur la broche 6"
    assert modification_target(prompt, _F) is None
    m = GenerationModal(_F, prompt, None)
    assert m._rb[ADD].isChecked(), "un ajout normal reste sur « Ajouter »"
    textes = [l.text() for l in m.findChildren(QLabel)]
    assert not any("Modifier" in t and "Ajouter" in t for t in textes), textes


def test_the_hint_exists_in_all_four_languages():
    from ui.i18n import lang_manager
    vus = set()
    for lang in ("fr", "en", "es", "it"):
        lang_manager.set_language(lang)
        t = lang_manager.current.gen_modal_looks_like_modif
        assert t and len(t) > 30, (lang, t)
        vus.add(t)
    assert len(vus) == 4, "une langue recopie une autre"
    lang_manager.set_language("fr")


TESTS = [
    test_no_false_positive_on_normal_additions,
    test_a_conditional_addition_is_still_an_addition,
    test_restrictive_requests_are_routed_to_the_right_feature,
    test_substitutive_and_imperative_requests_are_routed_too,
    test_the_stem_bridges_the_noun_and_the_verb,
    test_a_marker_without_a_target_proposes_nothing,
    test_a_tie_proposes_nothing,
    test_no_features_no_proposal,
    test_the_modal_opens_on_modify_with_the_right_feature_checked,
    test_a_normal_addition_leaves_the_modal_on_add,
    test_the_hint_exists_in_all_four_languages,
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
