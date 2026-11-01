"""#82 : une lib de driver moteur ne s'injecte que si la puce est nommee.

Le defaut mesure (2026-08-31, `bench_motor_agnostic`) : 7 prompts moteur
generiques sur 18 injectaient une lib liee a une puce de driver — « deux
moteurs DC » recevait le SparkFun TB6612 a 0.605 DEVANT l'entree generique,
« un robot a deux roues » recevait L298N + Motor Shield sans meme `dc_motor`.
Le SLM obeit au contexte (#37), donc il codait pour une puce que l'utilisateur
n'a jamais mentionnee ; depuis que les noms de libs sont corriges (#83), ca
COMPILE — l'echec silencieux.

Le principe : le choix du driver appartient a la modale de cablage (les
ClarifyGroup excluent moteurs et drivers pour cette raison), et le code moteur
a une forme SANS lib — PWM + broches de direction — qui est celle que tout le
pipeline de cablage attend.

⚠️ **NE PAS generaliser aux autres familles.** Un ecran ou un capteur n'a pas
de forme sans lib : quelqu'un doit choisir une puce pour ecrire la premiere
ligne, et mieux vaut le mecanisme visible et corrigeable (retrieval + banniere
+ swap) que la memoire du SLM.

Ces tests suivent la convention des gardes RAG : ils REFUSENT de conclure si
le modele ONNX est indisponible (mesure invalide ≠ verte).
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import rag  # noqa: E402

_K = 3


def _libs(prompt: str) -> list[str]:
    assert rag._load(), ("modele ONNX indisponible : mesure impossible, on "
                         "refuse de conclure")
    return [e.get("id") for e in
            rag.retrieve_libs(prompt, k=_K, threshold=rag._CODEGEN_MIN_SCORE)]


# ── le jeu supprime, derive du registre ─────────────────────────────────

def test_the_suppressed_set_derives_from_the_registry():
    """Jamais ecrit a la main : une liste locale aurait oublie le prochain
    driver ajoute au registre — le trou que la checklist de CLAUDE.md existe
    pour empecher."""
    docs = rag._motor_driver_doc_ids()
    assert docs, "le registre doit fournir des documents de drivers"
    # Les deux libs du releve #82, et les pieges du meme genre.
    assert {"l298n", "sparkfun-tb6612", "grove-i2c-motor-driver",
            "adafruit-motorshield-v2"} <= docs, sorted(docs)
    # Les MOTEURS, eux, restent injectables : leur entree est la bonne
    # reponse a un prompt generique (dc_motor n'a d'ailleurs aucune lib).
    assert not ({"dc_motor", "servo", "stepper", "stepper_28byj48", "nema17"}
                & docs), sorted(docs)
    # ⚠️ Les deux drivers SANS forme nue sont exemptes -- ce sont les DEUX
    # SEULES caracterisations que le filtre initial a fait rougir (batch3 :
    # « driver 16 servos » doit retrouver pca9685, Servo.h plafonnant a 12
    # sorties ; batch7 : « driver de vibration haptique » -> drv2605). La
    # puce EST le besoin, meme statut que les ecrans.
    assert not ({"pca9685", "drv2605"} & docs), sorted(docs)
    # Et la liste d'exemption ne peut pas porter une faute de frappe : chacun
    # de ses ids est bien un document d'un composant motor_driver du registre.
    from ui.component_registry import REGISTRY
    comps = REGISTRY.values() if isinstance(REGISTRY, dict) else REGISTRY
    tous = {d for c in comps if c.function == "motor_driver"
            for d in c.documents}
    assert rag._NO_BARE_FORM_DRIVER_DOCS <= tous, (
        sorted(rag._NO_BARE_FORM_DRIVER_DOCS - tous))


# ── le comportement, aux parametres de l'app ────────────────────────────

def test_a_generic_motor_prompt_injects_no_driver_lib():
    """Le coeur du #82, dans les 4 langues du produit."""
    drivers = rag._motor_driver_doc_ids()
    for prompt in ("deux moteurs DC", "two DC motors forward and backward",
                   "dos motores DC", "due motori DC"):
        injecte = _libs(prompt)
        assert not (set(injecte) & drivers), (prompt, injecte)


def test_the_generic_entry_takes_the_lead_it_deserved():
    """« deux moteurs DC » : `dc_motor` etait TROISIEME derriere deux libs de
    puces. Le filtre ne doit pas seulement retirer les drivers, il doit
    laisser l'entree generique passer — c'est elle qui montre au SLM la forme
    en broches nues."""
    assert "dc_motor" in _libs("deux moteurs DC")


def test_a_named_chip_still_injects_its_lib():
    """Nommer la puce reste le geste qui debloque tout — meme critere lexical
    que le boost et que l'en-tete imperatif."""
    for prompt, attendu in (("2 moteurs DC avec un L298N", "l298n"),
                            ("un moteur pas a pas avec un DRV8825", "drv8825")):
        assert attendu in _libs(prompt), (prompt, _libs(prompt))


def test_the_project_hint_unlocks_the_project_driver():
    """#64 : un prompt de suite sur un projet L298N garde sa lib. Le hint est
    concatene au prompt par `_build_lib_context` AVANT `retrieve_libs`, donc
    le meme test lexical le voit — verifie ici par la VRAIE plomberie."""
    contexte = rag.build_lib_context("augmente la vitesse du moteur",
                                     ranking_hint="l298n")
    assert "l298n" in contexte.lower() or "L298N" in contexte, contexte[:400]


def test_a_product_named_in_full_words_still_injects():
    """La limite du test lexical, corrigee : « Grove I2C Motor Driver » n'a
    comme tokens de signature que `l298` et `0x0f`, le « Adafruit Motor
    Shield » n'en a AUCUN. Ecrire leur nom en toutes lettres doit compter
    comme les nommer — 4 cas « decrit precis » du banc passaient de correct a
    wrong sans ce passe-droit."""
    assert "grove-i2c-motor-driver" in _libs(
        "deux moteurs avec le Grove I2C motor driver")
    assert "adafruit-motorshield-v2" in _libs(
        "piloter deux moteurs DC avec un shield Adafruit")


def test_naming_a_category_is_not_naming_a_product():
    """« un pont en H » nomme une CATEGORIE. La debloquer reviendrait a
    choisir une puce sur un mot generique — le defaut qu'on supprime."""
    drivers = rag._motor_driver_doc_ids()
    injecte = _libs("un robot a deux roues avec un pont en H")
    assert not (set(injecte) & drivers), injecte


# ── le test produit, unitaire ───────────────────────────────────────────

def test_the_product_test_requires_all_distinctive_words():
    """« motor »/« driver » ne discriminent rien dans une famille qui ne
    contient QUE des drivers de moteur ; « grove », « adafruit », « shield »
    si. Et singulier/pluriel sont replies (« motors » nomme autant que
    « motor »)."""
    grove = {"arduino_lib_name": "Grove I2C Motor Driver v1.3"}
    shield = {"arduino_lib_name": "Adafruit Motor Shield V2 Library"}
    assert rag._prompt_names_product(
        grove, "deux moteurs avec le grove i2c motor driver")
    assert not rag._prompt_names_product(
        grove, "mon capteur grove et deux moteurs"), \
        "grove SEUL ne suffit pas : il faut aussi i2c"
    assert rag._prompt_names_product(
        shield, "drive two dc motors with an adafruit shield")
    assert rag._prompt_names_product(
        shield, "piloter deux moteurs dc avec un shield adafruit"), \
        "le francais ecrit « moteurs », pas « motor » : le mot de categorie " \
        "ne doit pas etre exige"
    assert not rag._prompt_names_product(shield, "deux moteurs dc")
    assert not rag._prompt_names_product(
        {"arduino_lib_name": ""}, "n'importe quoi"), \
        "une entree sans nom de lib n'a pas de nom de produit a matcher"


TESTS = [
    test_the_suppressed_set_derives_from_the_registry,
    test_a_generic_motor_prompt_injects_no_driver_lib,
    test_the_generic_entry_takes_the_lead_it_deserved,
    test_a_named_chip_still_injects_its_lib,
    test_the_project_hint_unlocks_the_project_driver,
    test_a_product_named_in_full_words_still_injects,
    test_naming_a_category_is_not_naming_a_product,
    test_the_product_test_requires_all_distinctive_words,
]


def main() -> None:
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
