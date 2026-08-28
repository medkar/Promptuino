"""TODO #47 volet 1 — le detecteur reconnait-il l'exemple que l'app DONNE au modele ?

Le motif, formule pendant la QA d'aout apres l'avoir trouve QUATRE fois : *le
detecteur reconnaissait une ecriture que le modele ne produit pas*. A chaque
fois le corpus fournit au modele l'exemple officiel, le modele le recopie
fidelement, et le detecteur attend une forme plus ancienne. Le symptome est
toujours le meme et il est muet : rien ne distingue « ce sketch n'a aucun
composant » de « je n'ai rien su lire ».

Ce test mecanise la confrontation. Les deux sources sont dans le depot :
l'`example_code` de chaque entree du corpus, et le pipeline de cablage. Rien
n'est invente.

⚠️ Il tourne sur le PIPELINE COMPLET (`generate_wiring`), pas sur
`markers.parse_fallback`. Mesure faite le 2026-08-10 : sur `parse_fallback`
seul, 15 documents semblaient en desaccord ; l'inference en aval en comble 5
(elle ajoute le moteur derriere son driver, la resistance de LED, les
pull-ups). Tester la mauvaise couche aurait fait passer pour des trous des
choses qui marchent.

Run : python scripts/test_corpus_examples_are_detected.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui import rag
from ui.component_registry import (REGISTRY, SOFTWARE_ONLY_DOCUMENTS,
                                   registry)
from ui.wiring.wiring_pipeline import generate_wiring

BOARD = "arduino_uno_r3"

# ── La DETTE, nommee et bornee ───────────────────────────────────────────────
# Ces documents decrivent un composant a cabler, et leur exemple officiel n'est
# PAS reconnu : il tombe sur le placeholder universel (boite 4 broches non
# cablee) ou ne produit rien. Mesure exhaustive du 2026-08-10.
#
# Ils ne sont pas SILENCIEUX — chacun porte son avertissement
# (`unwired_unknown_component`, `presumed_i2c_wiring`), et c'est le travail
# d'honnetete de juillet qui paye. Mais l'entree du registre qui leur
# correspond porte un id que RIEN n'emettra jamais : ce sont des fantomes, du
# meme genre que le `bme280` debusque par le chantier registre.
#
# La liste est ici pour etre VUE et pour retrecir. Y ajouter une ligne doit
# etre un acte delibere ; c'est tout l'objet du test ci-dessous.
#
# ⚠️ Les quatre restants ne sont PAS quatre lacunes du detecteur — c'est ce que
# le balayage a appris de plus utile : deux ambiguites VOULUES que le prompt
# tranche (`dc_motor`, `l293d`), un chantier deja ouvert pour lui-meme
# (`drv8833` = TODO #9), et une DECISION a prendre (`onewire`). Chacun porte sa
# raison, ecrite a cote de lui.

# ── « On ne SAIT pas lire » n'est pas « on CHOISIT de ne pas dessiner » ──────
# Deux dettes de nature differente, deux listes. Confondre les deux, c'est
# perdre l'information la plus utile : ce qui reste a corriger.
#
# Ici : les documents que l'app RECONNAIT et qu'elle choisit de ne pas
# dessiner, en le disant. Chacun doit emettre son warning — verifie plus bas,
# sinon « delibere » ne serait qu'une facon elegante de dire « ignore ».
DELIBERATELY_NOT_DRAWN: dict[str, str] = {
    "adafruit-motorshield-v2": "shield_not_drawable — un shield se monte SUR "
                               "les broches de la carte : il n'y a aucun fil a "
                               "dessiner entre les deux. Le dessiner serait "
                               "dessiner quelque chose qui n'existe pas. "
                               "L'entree corpus est GARDEE (elle porte l'API "
                               "de la lib, donc le code reste juste) ; la "
                               "logique shields est le TODO #7",
}

UNDETECTED_EXAMPLES: dict[str, str] = {
    # --- Lot #69 (2026-08-27) : six pieces que le CODE SEUL ne peut pas
    # nommer, par construction. Ce ne sont PAS des lacunes : chacune est
    # reconnue des que le PROMPT donne sa reference, ce que verrouillent les
    # tests correspondants de `test_wiring_disambiguation.py`.
    #
    # ⚠️ Les dix capteurs MQ du meme lot, eux, sont ABSENTS de cette liste --
    # leur exemple ecrit `#define MQ137_PIN A0`, et le detecteur lit ce
    # numero. La difference tient a ce que le code REVELE, pas au lot.
    "mhz14a":                  "UART : SoftwareSerial(10,11) ne dit rien de la "
                               "puce au bout du fil. Sort en `uart_module`, le "
                               "filet honnete. Nomme des que le prompt ecrit "
                               "la reference",
    "mhz1311a":                "idem mhz14a",
    "rcwl0516":                "entree digitale nue : digitalRead(2) ne dit "
                               "rien de ce qui est branche. Sort en `button`, "
                               "le defaut. Nomme par le prompt (radar doppler, "
                               "micro-ondes, ou la reference)",
    "rcwl1005":                "lecture I2C brute via Wire, sans bibliotheque "
                               "dediee : aucune signature a guetter",
    "rcwl1605":                "idem rcwl1005",
    "jsn_sr04t":               "le motif trig/echo identifie un PROTOCOLE, pas "
                               "une piece -- HC-SR04, JSN-SR04T, AJ-SR04M et "
                               "HC-SR04P le partagent. Sort en `hcsr04`, ce qui "
                               "est JUSTE ; le prompt precise laquelle",
    # ⚠️ `dc_motor` et `l293d` NE SONT PAS des lacunes du detecteur, et c'est
    # une correction : le groupement PWM+direction marche, et avec un prompt
    # REALISTE (« Fais tourner un moteur DC avec un L298N ») la suggestion
    # `_prompt_suggested_type=dc_motor` est bien posee, avec le bon driver —
    # mesure, et verrouille par `test_a_grouped_motor_gets_its_suggestion`
    # dans `test_wiring_disambiguation.py`. Ils restent ici parce que le NOM
    # de l'entree corpus ne nomme aucune puce de driver, donc le code seul ne
    # tranche pas. C'est l'ambiguite VOULUE, pas un trou.
    "dc_motor":                "code seul : LED. Resolu des que le prompt nomme "
                               "le driver — ambiguite voulue, pas une lacune",
    "l293d":                   "idem dc_motor",
    "drv8833":                 "mode « in-in » : deux broches PWM, aucune broche "
                               "de direction — le groupement ne s'applique pas. "
                               "C'est le TODO #9, deja ouvert pour lui-meme",
    # (e) DEUX composants, UN SEUL en-tete — indecidable, pas une lacune
    "bmp180":                  "`bmp085` et `bmp180` declarent EXACTEMENT le meme "
                               "en-tete, `Adafruit_BMP085.h` (verifie le "
                               "2026-08-26) : les deux puces sont compatibles "
                               "registre a registre et partagent une lib. Aucun "
                               "detecteur lisant les #include ne peut les "
                               "distinguer ; le detecteur emet `bmp085`, ce qui "
                               "est defendable. Meme nature que dc_motor/l293d "
                               "ci-dessus : une ambiguite VOULUE, pas un trou. "
                               "L'engrenage laisse l'utilisateur trancher.",
    # (d) rien du tout
    "onewire":                 "aucun composant produit — un bus 1-Wire NU ne dit "
                               "pas que c'est un DS18B20 ; l'emettre demanderait "
                               "un marqueur de presomption, comme la broche "
                               "analogique nue. Decision a prendre, pas un oubli.",
    # QUATRE entrees sont SORTIES de cette liste le 2026-08-10, le jour meme du
    # balayage : `hx711`, `ina226-we`, `sd` et `onebutton`. Toutes les quatre
    # avaient deja leur catalogue, leur libelle x4, leur nom court et leur
    # identite au registre — seule la LECTURE DU CODE manquait. C'est
    # exactement ce que ce fichier sert a rendre visible : la difference entre
    # « on ne sait pas dessiner ce composant » et « on ne sait pas le lire ».
    # La dette est passee de 12 a 5 : hx711, ina226-we, sd, onebutton, mq135,
    # sparkfun-tb6612 et grove-i2c-motor-driver sont sortis le meme jour.
}

# Le registre le dit lui-meme : rien a brancher.
NOTHING_TO_WIRE = {c.id for c in REGISTRY if c.wiring == "none"}


def _documents_of_components() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for comp in registry():
        for doc in comp.documents:
            out.setdefault(doc, set()).add(comp.id)
    return out


def _wireable_entries():
    """(id, exemple, ids des composants decrits) pour chaque entree du corpus
    qui decrit quelque chose a brancher."""
    docs = _documents_of_components()
    for entry in rag.all_corpus_entries():
        cid = entry.get("id")
        example = (entry.get("example_code") or "").strip()
        if not example or cid in SOFTWARE_ONLY_DOCUMENTS:
            continue
        wanted = docs.get(cid)
        if not wanted or wanted <= NOTHING_TO_WIRE:
            continue
        yield cid, example, wanted


def _types_detected(example: str, prompt: str = "") -> set[str]:
    """Types produits, SUGGESTIONS COMPRISES.

    ⚠️ Corrige le 2026-08-10, apres m'etre trompe de couche une troisieme fois
    dans la meme journee. `markers` ne mute PAS un groupe PWM+direction en
    `dc_motor` : il laisse le type a `led` et attache
    `_prompt_suggested_type`, que `studio_view` applique ensuite sans modale.
    Ne regarder que `c.type` faisait passer pour des lacunes des cas que le
    pipeline traite exactement comme prevu."""
    nl = generate_wiring(example, BOARD, prompt=prompt)
    return ({c.type for c in nl.components}
            | {c.attributes.get("_prompt_suggested_type")
               for c in nl.components} - {None})


# ── Le garde ─────────────────────────────────────────────────────────────────

def test_every_official_example_is_detected():
    """LE test du chantier. Un document du corpus qui decrit un composant a
    cabler doit voir son exemple officiel reconnu — sinon l'app donne au modele
    un code qu'elle ne sait pas relire, et le schema est faux ou vide."""
    manques = []
    for cid, example, wanted in _wireable_entries():
        if cid in UNDETECTED_EXAMPLES or cid in DELIBERATELY_NOT_DRAWN:
            continue
        if not (_types_detected(example) & wanted):
            manques.append((cid, sorted(wanted), sorted(_types_detected(example))))
    assert not manques, (
        "exemple officiel non reconnu — soit corriger la detection, soit "
        f"l'inscrire dans UNDETECTED_EXAMPLES en connaissance de cause : {manques}")


def test_the_debt_list_is_not_stale():
    """L'echappatoire est gardee, meme discipline que SOFTWARE_ONLY_DOCUMENTS :
    une entree qui se met a marcher doit SORTIR de la liste, sinon la dette
    grossit sur le papier pendant qu'elle retrecit dans les faits — et plus
    personne ne sait ou on en est."""
    encore_casses = []
    for cid, example, wanted in _wireable_entries():
        if cid not in UNDETECTED_EXAMPLES:
            continue
        if _types_detected(example) & wanted:
            encore_casses.append(cid)
    assert not encore_casses, (
        "ces exemples sont DETECTES maintenant : les retirer de "
        f"UNDETECTED_EXAMPLES : {encore_casses}")


def test_every_debt_entry_names_a_real_corpus_document():
    ids = {e.get("id") for e in rag.all_corpus_entries()}
    inconnus = sorted((set(UNDETECTED_EXAMPLES) | set(DELIBERATELY_NOT_DRAWN))
                      - ids)
    assert not inconnus, f"documents inexistants dans la dette : {inconnus}"


def test_what_is_not_drawn_on_purpose_says_so():
    """« Delibere » ne doit pas devenir une facon elegante de dire « ignore ».
    Chaque entree de DELIBERATELY_NOT_DRAWN doit produire un avertissement —
    sinon l'utilisateur voit un schema vide sans un mot, ce que le volet 2 du
    chantier existe precisement pour empecher."""
    for cid in DELIBERATELY_NOT_DRAWN:
        entry = rag.corpus_entry(cid)
        nl = generate_wiring((entry.get("example_code") or "").strip(), BOARD)
        codes = [w.code for w in nl.warnings]
        assert "shield_not_drawable" in codes, (cid, codes)
        # Et surtout : AUCUN composant invente, ni boite muette du placeholder.
        assert not nl.components, [c.type for c in nl.components]
        assert "unwired_unknown_component" not in codes, codes
        # Ni le message generique du volet 2 en DOUBLE : deux explications qui
        # se contredisent valent moins qu'une seule qui dit vrai.
        assert "nothing_detected" not in codes, codes


def test_the_debt_stays_bounded():
    """Un chiffre, pour que la dette se lise d'un coup d'oeil et qu'une
    aggravation se voie.

    Historique : 12 au balayage du 2026-08-10, sept corriges le jour meme et le
    shield sorti dans DELIBERATELY_NOT_DRAWN -> 4 sur 85.

    Le 2026-08-26, #60 a fait grimper le manque a 21 sur 124 en ajoutant 46
    entrees au corpus. **20 des 21 ont ete REPAREES, pas tolerees** : le
    detecteur nommait le composant d'apres le FICHIER d'en-tete (`tca9548a`
    plutot que `i2c_multiplexer`), et `markers._header_type_alias()` derive
    desormais la correspondance du registre. La dette ne gagne donc qu'UNE
    entree, `bmp180`, et c'est une ambiguite indecidable, pas une lacune.

    ⚠️ Le plafond est ABSOLU a dessein, pas proportionnel : une dette qui aurait
    le droit de grandir avec le corpus cesserait d'etre une dette. Le relever
    demande de justifier chaque entree ajoutee, ici comme au-dessus.

    5 -> 11 le 2026-08-27 (#69), et la justification tient en une phrase :
    ces six exemples ne PEUVENT PAS nommer leur piece, parce que le code
    qu'ils montrent ne la nomme pas non plus.

      - `mhz14a`, `mhz1311a` : `SoftwareSerial(10, 11)` ne dit rien de la
        puce au bout du fil. Aucune signature ne peut exister.
      - `rcwl0516` : `digitalRead(2)` ne dit rien de ce qui est branche.
      - `rcwl1005`, `rcwl1605` : lecture I2C brute via `Wire`, sans
        bibliotheque dediee -- rien a guetter.
      - `jsn_sr04t` : le motif trig/echo identifie un PROTOCOLE que quatre
        pieces partagent. Le detecteur rend `hcsr04`, ce qui est JUSTE ;
        c'est la liste qui compte cela comme un manque.

    ⛔ Aucune ne reste MUETTE pour autant : chacune est nommee des que le
    prompt donne sa reference, et `test_wiring_disambiguation.py` le
    verrouille piece par piece. La dette porte sur ce que le CODE revele,
    pas sur ce que l'app sait faire.

    ⚠️ Contre-exemple utile dans le MEME lot : les dix capteurs MQ ne sont
    PAS ici. Leur exemple ecrit `#define MQ137_PIN A0`, le detecteur lit ce
    numero, et ils sont reconnus par le code seul. La difference tient a ce
    que le code montre, jamais a l'origine du lot.
    """
    total = sum(1 for _ in _wireable_entries())
    assert len(UNDETECTED_EXAMPLES) <= 11, len(UNDETECTED_EXAMPLES)
    assert total >= 82, f"le corpus a maigri ? {total}"


# ── Ce que le detecteur emet doit exister pour un humain ─────────────────────

def test_no_detected_type_is_nameless():
    """Guard 7 (`test_component_registry`) confronte `_TYPE_LABEL` au registre :
    une table contre une autre table. Aucun des deux n'est pilote par ce que le
    detecteur PRODUIT — c'est l'angle mort par lequel six types sont passes.

    Ici on part des faits. Un type reellement emis sans libelle humain s'affiche
    dans les instructions sous son identifiant brut, et reste introuvable dans
    l'onglet « Composants » — exactement le defaut que le chantier registre de
    juillet a corrige pour huit autres types."""
    from ui.wiring.instructions import _TYPE_LABEL
    from ui.component_registry import (NON_COMPONENT_CATALOG_TYPES,
                                       NON_COMPONENT_WIRING_TYPES)
    # Les types nes du placeholder portent le nom du `#include` : ils n'ont pas
    # a etre nommes, ils n'existent que le temps que la detection manque. On
    # les tolere EXACTEMENT sur la dette declaree ci-dessus, pas au-dela.
    tolere = set()
    for cid, example, _w in _wireable_entries():
        if cid in UNDETECTED_EXAMPLES:
            tolere |= _types_detected(example)

    sans_nom = set()
    for _cid, example, _w in _wireable_entries():
        for t in _types_detected(example):
            if (t not in _TYPE_LABEL and t not in tolere
                    and t not in NON_COMPONENT_CATALOG_TYPES
                    and t not in NON_COMPONENT_WIRING_TYPES):
                sans_nom.add(t)
    assert not sans_nom, (
        "types emis par le detecteur et jamais nommes a l'utilisateur : "
        f"{sorted(sans_nom)}")


TESTS = [
    test_every_official_example_is_detected,
    test_the_debt_list_is_not_stale,
    test_every_debt_entry_names_a_real_corpus_document,
    test_what_is_not_drawn_on_purpose_says_so,
    test_the_debt_stays_bounded,
    test_no_detected_type_is_nameless,
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
