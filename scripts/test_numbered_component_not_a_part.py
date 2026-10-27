"""Un composant NUMEROTE n'est pas une reference de piece.

Contexte du defaut d'origine (2026-09-04, signale en test avec un etudiant).
Un prompt qui disait simplement « led2 » declenchait tout le pipeline
hors-corpus : `detect_unknown_part_tokens` voyait un token de forme
part-number (>= 4 caracteres, chiffres ET lettres, inconnu du corpus), donc
l'app interrogeait le registre Arduino, installait une bibliotheque sans
rapport, en fabriquait une entree corpus ad hoc, et affichait la banniere
ambre annoncant a l'utilisateur quelle bibliotheque avait servi pour son
« composant ». La generation n'a pas utilise cette bibliotheque -- mais elle
aurait pu, et le message etait faux dans tous les cas.

`_is_indexed_designator` ecarte ces tokens. Ce fichier verrouille les deux
moities de la regle, et surtout la seconde : qu'elle n'ecarte RIEN de reel.

Run : python scripts/test_numbered_component_not_a_part.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.registry_lookup import (_is_indexed_designator,
                                detect_unknown_part_tokens)


def test_numbered_components_are_not_looked_up():
    """Le defaut signale, dans les quatre langues.

    La regle ne consulte aucun lexique -- c'est precisement ce qui lui permet
    de valoir pour « bouton2 » comme pour « pulsante2 » sans table a tenir.
    """
    cas = [
        ("fais clignoter led1 et led2 en alternance", "fr"),
        ("allume la led2 quand on appuie sur bouton2", "fr"),
        ("blink led2 then led3", "en"),
        ("enciende led2 con el pulsador1", "es"),
        ("accendi led2 con il pulsante2", "it"),
        ("le moteur3 tourne quand capteur2 detecte", "fr"),
        ("servo1 a 90 degres puis servo2 a 0", "fr"),
    ]
    for prompt, langue in cas:
        trouves = detect_unknown_part_tokens(prompt)
        assert not trouves, (
            f"[{langue}] {prompt!r} -> {trouves} : un composant numerote a "
            f"declenche la recherche au registre")


def test_real_part_numbers_still_get_looked_up():
    """La regle ne doit pas fermer la porte qu'elle protege.

    Sans ces cas, la faire passer suffirait a ne plus jamais rien chercher.
    """
    cas = {
        "utilise un capteur AS7341": "as7341",
        "je branche un ZXQ-9000": "zxq9000",
        "un servo SG90": "sg90",
        # ⚠️ « HC-SR04 » a ete RETIRE de cette liste le 2026-09-10, et le
        # remplacer par un MAX-31865 n'est pas un contournement : le HC-SR04
        # est un composant que l'application CONNAIT -- fiche au registre,
        # document corpus `newping`, type de cablage. L'envoyer chercher une
        # bibliotheque au registre Arduino n'avait aucun sens ; il n'y allait
        # que parce que `_signature_tokens` ne joignait pas les tirets,
        # defaut corrige le meme jour. Cette liste doit contenir des
        # references REELLEMENT inconnues, sinon elle verrouille un defaut.
        "un capteur MAX-31865": "max31865",
        "un driver TMC2226": "tmc2226",
    }
    for prompt, attendu in cas.items():
        trouves = detect_unknown_part_tokens(prompt)
        assert attendu in trouves, (
            f"{prompt!r} -> {trouves} : la reference {attendu!r} n'est plus "
            f"cherchee au registre")


def test_the_rule_discards_no_real_reference_of_the_corpus():
    """La moitie qui compte : mesurer plutot que citer des exemples.

    C'est cette verification qui autorise une regle de FORME. Elle balaie tout
    `corpus.json` -- ids, noms de bibliotheques, en-tetes, mots-cles,
    descriptions -- et exige que chaque token de la forme « racine + un
    chiffre » soit un nom de broche, une grandeur mesuree ou un nom de
    bibliotheque, JAMAIS un numero de piece. Mesure du 2026-09-04 : 18 tokens
    concernes, aucun numero de piece.

    Si un futur ajout au corpus introduit une vraie reference de cette forme,
    ce test rougit et la regle doit etre revue -- pas contournee au cas par
    cas.
    """
    corpus = json.loads(
        (ROOT / "assets" / "rag" / "corpus.json").read_text(encoding="utf-8"))
    tokens = set()
    for entry in corpus:
        textes = [entry.get("id"), entry.get("lib_name"), entry.get("name"),
                  entry.get("description")]
        textes += list(entry.get("headers") or [])
        textes += [str(k) for k in (entry.get("keywords") or [])]
        for texte in textes:
            if texte:
                tokens |= set(re.findall(r"[a-z0-9]+", str(texte).lower()))

    # Vocabulaire attendu : broches de driver, grandeurs mesurees, APIs,
    # bibliotheques versionnees. Mesure exhaustive, pas un echantillon.
    autorises = {
        "ain1", "ain2", "bin1", "bin2", "pin1", "pin2", "pin3", "pin4",
        "eco2", "spo2", "sno2", "ahtx0", "atan2", "crc8",
        "serial1", "serial2", "ethernet3", "ethernetudp3",
    }
    concernes = {t for t in tokens if _is_indexed_designator(t)}
    inattendus = sorted(concernes - autorises)
    assert not inattendus, (
        "Des tokens du corpus ont la forme « composant numerote » sans etre "
        "dans la liste connue. Si l'un d'eux est une VRAIE reference de piece, "
        f"la regle de _is_indexed_designator est fausse : {inattendus}")


def test_a_two_digit_index_is_deliberately_not_caught():
    """La limite est un CHOIX mesure, pas un oubli -- qu'on ne « corrige » pas.

    Elargir la regle a deux chiffres attraperait « led10 », mais ferait
    tomber du meme coup des references bien reelles a deux chiffres. Le test
    fixe les deux cotes pour qu'un futur elargissement soit une decision
    visible et non un effet de bord.
    """
    assert not _is_indexed_designator("led10"), (
        "limite connue : un index a deux chiffres n'est pas reconnu")
    for reference in ("sg90", "nema17", "hcsr04", "esp32", "mhz19"):
        assert not _is_indexed_designator(reference), (
            f"{reference} est une vraie reference a deux chiffres")
    for designateur in ("led2", "servo1", "bouton2", "pulsante2", "capteur2"):
        assert _is_indexed_designator(designateur), (
            f"{designateur} est un composant numerote")



def test_a_component_the_app_knows_is_never_looked_up():
    """⛔ TROUVE EN QA (AP1, 2026-09-10). « lis un capteur UV GUVA-S12SD sur
    A0 » partait au registre Arduino sous DEUX references inconnues --
    `s12sd` ET `guvas12sd` -- avec la banniere ambre annoncant deux
    composants inconnus. Pour un composant que l'app connait parfaitement :
    type de cablage, entree catalogue, fiche au registre.

    DEUX causes, mesurees :
      1. `detect_unknown_part_tokens` ne consultait que le CORPUS, et un
         composant SANS BIBLIOTHEQUE n'y a pas d'entree. **34** composants du
         registre etaient dans ce cas -- `acs712`, `ina169`, `tmp36`,
         `ky018`, `us100`, `qre1113`, `ttp223`, `hc05`...
      2. un FRAGMENT de reference tiretee (`s12sd`) survivait a l'exclusion
         de sa forme jointe. Un morceau de reference n'est pas une reference.

    ⚠️ La question est CATEGORIELLE -- « l'application connait-elle ce
    composant ? » -- donc rien a calibrer.
    """
    connus = [
        "lis un capteur UV GUVA-S12SD sur A0",   # les deux causes a la fois
        "lis un capteur de courant ACS712 sur A0",
        "un capteur INA169 sur A0",
        "un capteur TMP36 sur A0",
        "un module TTP223 sur la broche 4",
        "un capteur QRE1113 sur A0",
        "un telemetre US-100",
        "une carte GY-85",
    ]
    for p in connus:
        trouves = detect_unknown_part_tokens(p)
        assert not trouves, (
            f"{p!r} -> {trouves} : l'app connait ce composant, elle n'a rien "
            f"a demander au registre Arduino (et la banniere ambre s'affiche "
            f"pour rien)")


def test_a_hyphen_fragment_is_not_a_reference():
    """Le second defaut d'AP1, isole : « GUVA-S12SD » produit `guva`,
    `s12sd` ET `guvas12sd`. Exclure la forme jointe sans exclure ses
    fragments laissait `s12sd` partir seul au registre."""
    for p in ("un GUVA-S12SD", "un HC-SR04", "un NEO-6M", "une GY-85"):
        assert not detect_unknown_part_tokens(p), p
    # ... mais une reference tiretee VRAIMENT inconnue part bien, entiere.
    assert detect_unknown_part_tokens("un ZXQ-9000") == ["zxq9000"]
    assert detect_unknown_part_tokens("un MAX-31865") == ["max31865"]


TESTS = [
    test_a_component_the_app_knows_is_never_looked_up,
    test_a_hyphen_fragment_is_not_a_reference,
    test_numbered_components_are_not_looked_up,
    test_real_part_numbers_still_get_looked_up,
    test_the_rule_discards_no_real_reference_of_the_corpus,
    test_a_two_digit_index_is_deliberately_not_caught,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
