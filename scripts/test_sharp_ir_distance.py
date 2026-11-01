"""Le telemetre infrarouge Sharp GP2Y0A (2026-09-09).

Contexte. Signale par l'utilisateur : la famille « distance » du pipeline de
clarification connaissait le HC-SR04, le VL53L0X et l'APDS9960 -- soit les
TROIS qui ne passent pas par une broche analogique. Le Sharp, qui est
precisement l'analogique de la famille et qui se trouve dans les kits
d'entree de gamme, n'existait nulle part : ni corpus, ni registre, ni
catalogue. Mesure avant : « un capteur de distance Sharp GP2Y0A21 sur A0 »
sortait dessine en potentiometre.

⚠️ CE FICHIER VERROUILLE SURTOUT DEUX CHOSES QU'UNE REPRISE DISTRAITE
CASSERAIT SANS QUE RIEN D'AUTRE NE ROUGISSE :

1. LES DEUX ECRITURES DE LA REFERENCE. La serigraphie des capteurs porte
   « 2Y0A21 F 81 » et « 2Y0A21 F 7X » -- PAS « GP2Y0A21 » (constate par
   l'utilisateur sur ses propres capteurs). Un debutant recopie ce qui est
   ecrit sur l'objet qu'il tient en main.

2. LE MODELE EST UN PARAMETRE, PAS UN TYPE. La bibliotheque `SharpIR`
   (qub1750ul) prend le modele au constructeur et en deduit la courbe de
   conversion tension -> distance -- courbe DIFFERENTE selon la portee
   (4-30, 10-80, 20-150 cm). Le CABLAGE, lui, est identique pour les trois
   (« the pin configuration is the same for all models », dit la fiche
   technique citee par l'exemple officiel). D'ou UN type de cablage et
   TROIS constantes dans le bloc d'API.

Run : python scripts/test_sharp_ir_distance.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.wiring.layout.component_catalog import CATALOG
from ui.wiring.markers import (extract_netlist, _SHARP_FAMILY_KEYWORDS,
                               _GP2Y0A21_KEYWORDS, _GP2Y0A41_KEYWORDS,
                               _GP2Y0A02_KEYWORDS, _GP2Y0A51_KEYWORDS,
                               _SHARP_DEFAULT_TYPE)

# Depuis l'eclatement du 2026-09-09, il n'y a plus UN type mais TROIS.
_SHARPS = ("gp2y0a21", "gp2y0a41", "gp2y0a02", "gp2y0a51",
           "gp2y0a60", "gp2y0a710")
_SHARP_IR_KEYWORDS = (_SHARP_FAMILY_KEYWORDS + _GP2Y0A21_KEYWORDS
                      + _GP2Y0A41_KEYWORDS + _GP2Y0A02_KEYWORDS
                      + _GP2Y0A51_KEYWORDS)


def _un_sharp(types) -> bool:
    """Un des trois modeles, peu importe lequel : la plupart de ces gardes
    portent sur la FAMILLE (la serigraphie est lue, la marque nue ne compte
    pas), pas sur le modele exact -- celui-la a ses propres tests."""
    return any(t in types for t in _SHARPS)

_ANALOG = "void setup(){}\nvoid loop(){int v=analogRead(A0);}"
_AVEC_LIB = (
    "#include <SharpIR.h>\n"
    "SharpIR capteur(SharpIR::GP2Y0A21YK0F, A0);\n"
    "void setup(){ Serial.begin(9600); }\n"
    "void loop(){ int d = capteur.getDistance(); Serial.println(d); }"
)


def _types(code, prompt=""):
    return [c.type for c in extract_netlist(code, "uno", prompt=prompt).components]


def _corpus():
    return json.loads((ROOT / "assets" / "rag" / "corpus.json")
                      .read_text(encoding="utf-8"))


def test_the_silkscreen_spelling_works_as_well_as_the_catalogue_one():
    """⛔ LE point signale par l'utilisateur, et le plus facile a perdre.

    Ses capteurs portent « 2Y0A21 F 81 » / « 2Y0A21 F 7X ». Le prefixe
    « GP » est dans le catalogue du fabricant, pas sur le boitier. Les deux
    formes doivent marcher, pour les TROIS modeles.
    """
    for ref in ("2Y0A21", "GP2Y0A21", "2Y0A41", "GP2Y0A41",
                "2Y0A02", "GP2Y0A02"):
        p = f"un capteur de distance {ref} sur A0"
        assert _un_sharp(_types(_ANALOG, p)), p
    # Et cote corpus, ou vit le boost lexical : les deux formes aussi.
    e = next(x for x in _corpus() if x["id"] == "sharpir")
    kws = {k.lower() for k in e["keywords"]}
    for ref in ("2y0a21", "gp2y0a21", "2y0a41", "gp2y0a41",
                "2y0a02", "gp2y0a02"):
        assert ref in kws, f"« {ref} » manque aux mots-cles du corpus"


def test_every_real_silkscreen_form_is_recognised():
    """⛔ Le motif, et pourquoi ce n'est PAS une affaire de longueur.

    Signale par l'utilisateur le 2026-09-09 : ajouter la fin de la
    serigraphie -- collee ou tiretee -- faisait perdre la reconnaissance,
    avec banniere ambre et code faux a la cle. La regle « 6 caracteres, ou 8
    avec GP » qu'on avait d'abord formulee est FAUSSE : `GP2Y0A21` et
    `GP2Y0A41SK` n'ont pas la meme longueur. Ce qui identifie le composant
    est `2Y0A` + DEUX CHIFFRES.

    MESURE AVANT correctif, sur ces 15 ecritures : 7 non reconnues, dont la
    reference COMPLETE de chaque datasheet et le code de date colle.
    """
    formes = ["2Y0A21", "GP2Y0A21", "GP2Y0A21YK0F", "2Y0A21YK0F",
              "2Y0A21 F 81", "2Y0A21-F81", "2Y0A21F81", "2Y0A21 F 7X",
              "GP2Y0A41SK0F", "2Y0A41", "GP2Y0A51SK", "2Y0A51",
              "GP2Y0A02YK0F", "2Y0A02", "gp2y0a21"]
    rates = [f for f in formes
             if not _un_sharp(_types(_ANALOG, f"un capteur de distance {f} sur A0"))]
    assert not rates, f"{len(rates)}/{len(formes)} ecritures non reconnues : {rates}"


def test_the_pattern_leaves_the_other_sharp_families_alone():
    """Le motif ne doit pas devenir un attrape-tout de la marque.

    `GP2Y1010AU0F` (capteur de POUSSIERE) commence par `2Y10` : hors motif.
    `GP2Y0A700K0F` (telemetre 1-5 m) rend `2Y0A70`, absent du lexique : donc
    rien, plutot qu'un faux positif silencieux.
    """
    from ui.wiring.markers import _canonicalize_sharp_models as canon
    assert canon("un GP2Y0A21YK0F") == "un 2Y0A21"
    assert canon("2Y0A21F81") == "2Y0A21"
    # Tiretee, la reference est deja canonique : le code de date se trouve
    # de l'autre cote d'une frontiere de mot, donc rien a reecrire.
    assert canon("2Y0A21-F81") == "2Y0A21-F81"
    assert canon("un GP2Y1010AU0F") == "un GP2Y1010AU0F", "la poussiere est intacte"
    assert "2Y0A70" in canon("un GP2Y0A700K0F")
    for p in ("un capteur de poussiere GP2Y1010AU0F sur A0",
              "a Sharp dust sensor on A0",
              "un capteur de distance GP2Y0A700K0F sur A0"):
        assert not _un_sharp(_types(_ANALOG, p)), p


def test_the_brand_alone_is_not_a_component():
    """⛔ Defaut introduit le 2026-09-08, mesure et corrige le 2026-09-09.

    « un capteur Sharp sur A0 » sortait en telemetre AVEC sa bibliotheque.
    Or Sharp fabrique aussi des capteurs de poussiere -- le GP2Y1010AU0F est
    lui-meme un capteur optique a INFRAROUGE --, des recepteurs IR, et
    l'ecran memoire qui est deja au corpus.

    ⚠️ « sharp ir » et « sharpir » sont exclus AUSSI, sur decision de
    l'utilisateur : c'est le nom de la BIBLIOTHEQUE, pas du composant. Le
    chemin code n'en depend pas -- `_INCLUDE_SHARPIR_RE` lit l'`#include`.
    """
    for mot in ("sharp", "sharp ir", "sharpir", "capteur sharp",
                "sensor sharp", "sensore sharp"):
        assert mot not in _SHARP_IR_KEYWORDS, (
            f"« {mot} » nomme la marque ou la bibliotheque, pas le composant")
    for p in ("un capteur Sharp sur A0", "un capteur Sharp IR sur A0",
              "a Sharp sensor on A0"):
        assert not _un_sharp(_types(_ANALOG, p)), p
    # ... mais la SIGNATURE, elle, reste le chemin sur.
    assert _un_sharp(_types(_AVEC_LIB))


def test_every_writing_behaves_the_SAME_all_the_way_down():
    """⛔ TROUVE EN QA (AR1, 2026-09-09), et c'est le vrai enseignement du
    lot : la detection de CABLAGE reconnaissait bien les quinze ecritures,
    mais deux autres mecanismes lisaient encore le prompt BRUT.

    Mesure du defaut : « 2Y0A21F81 » (code de date COLLE) partait au registre
    Arduino comme part-number inconnu ET declenchait la banniere « aucun
    composant reconnu » ; « 2Y0A21-F81 » partait au registre aussi ;
    « GP2Y0A21YK0F » passait -- uniquement parce qu'il figure en toutes
    lettres dans les mots-cles du corpus. L'exclusion tenait donc a une
    COINCIDENCE d'enumeration, pas a une regle.

    Trois ecritures du meme objet doivent donner le meme comportement, et
    c'est ce qu'on verrouille ici -- au niveau de chaque mecanisme, pas
    seulement du schema.
    """
    import contextlib, io as _io
    from ui.registry_lookup import detect_unknown_part_tokens
    from ui import rag
    for f in ("2Y0A21F81", "2Y0A21-F81", "2Y0A21 F 81", "GP2Y0A21YK0F",
              "2Y0A21", "GP2Y0A41SK0F", "GP2Y0A51SK"):
        p = f"lis la distance avec un capteur {f} sur A0"
        assert detect_unknown_part_tokens(p) == [], (
            f"« {f} » part au registre Arduino : l'app connait pourtant "
            f"cette famille, et la banniere ambre s'affiche pour rien")
        with contextlib.redirect_stdout(_io.StringIO()):
            _, ressemblance = rag._build_lib_context(p)
        assert not ressemblance, (
            f"« {f} » declenche « aucun composant reconnu » -- or "
            f"l'utilisateur a recopie ce qui est ecrit sur son capteur")
        assert _un_sharp(_types(_ANALOG, p)), f


def test_the_a51_has_its_own_library_and_its_own_box():
    """⛔ LA QUESTION OUVERTE D'HIER, REFERMEE -- et par une correction de MA
    mesure, pas par un arbitrage.

    J'avais affirme : « aucune bibliotheque ne gere le GP2Y0A51, index Arduino
    entier balaye, 9 914 bibliotheques, zero ». C'etait FAUX, et l'erreur
    etait de METHODE : j'avais balaye les METADONNEES du registre (nom,
    description), alors que la liste des modeles vit dans l'EN-TETE des
    sources. `SharpDistSensor` (DrGFreeman, architectures `*`) porte bien sa
    calibration -- verifie en installant la bibliotheque et en lisant son
    en-tete, puis en COMPILANT un sketch sur `arduino:avr:uno`.

    Rien de special n'a ete invente pour l'accueillir : `Component.documents`
    est un tuple ORDONNE dont le premier porte le defaut, mecanisme deja
    utilise par `ds18b20` (dallas-temperature, onewire) et `stepper_motor`.
    """
    from ui.component_registry import by_id
    from ui.wiring.layout.component_catalog import CATALOG
    # Il a un type, une boite, un brochage.
    assert "gp2y0a51" in CATALOG
    assert set((CATALOG["gp2y0a51"].pin_labels or {}).values()) == {"VCC", "GND", "OUT"}
    for p in ("mesure la distance avec un GP2Y0A51SK sur A0",
              "un capteur 2Y0A51 sur A0"):
        assert "gp2y0a51" in _types(_ANALOG, p), p
    # Sa bibliotheque est l'AUTRE, et c'est la seule qu'il ait.
    assert by_id("gp2y0a51").documents == ("sharpdistsensor",)
    # Les trois autres en ont DEUX, `sharpir` en tete -- l'ordre porte le
    # defaut. Les confondre ferait injecter la mauvaise par defaut.
    for t in ("gp2y0a21", "gp2y0a41", "gp2y0a02"):
        assert by_id(t).documents == ("sharpir", "sharpdistsensor"), t


def test_the_second_library_is_detected_from_its_setModel():
    """`SharpDistSensor` ne prend PAS le modele au constructeur : il se pose
    par `setModel(...)`. Le detecteur doit aller l'y chercher, sinon un sketch
    parfaitement explicite sort sous le mauvais modele."""
    code = ("#include <SharpDistSensor.h>\n"
            "SharpDistSensor capteur(A0, 5);\n"
            "void setup(){ Serial.begin(9600);\n"
            "  capteur.setModel(SharpDistSensor::GP2Y0A51SK0F_5V_DS); }\n"
            "void loop(){ unsigned int d = capteur.getDist(); }")
    types = _types(code)
    assert types == ["gp2y0a51"], types
    c = next(c for c in extract_netlist(code, "uno").components)
    assert [(x.name, x.net) for x in c.pins] == [
        ("VCC", "5V"), ("GND", "GND"), ("OUT", "A0")], c.pins
    # ✅ Les cinq constantes de cette bibliotheque ont desormais leur type.
    for const, attendu in (("GP2Y0A710K0F_5V_DS", "gp2y0a710"),
                           ("GP2Y0A60SZLF_5V", "gp2y0a60"),
                           ("GP2Y0A41SK0F_5V_DS", "gp2y0a41")):
        autre = code.replace("GP2Y0A51SK0F_5V_DS", const)
        c = next(c for c in extract_netlist(autre, "uno").components)
        assert c.type == attendu, (const, c.type)
        assert not c.attributes.get("presumed_from_description"), const
    # ⚠️ Un `setModel` que l'app ne connait pas retombe sur le defaut EN LE
    # DISANT, plutot que d'affirmer un modele qu'elle ne sait pas dessiner.
    autre = code.replace("GP2Y0A51SK0F_5V_DS", "GP2Y0AXXXX_5V")
    c = next(c for c in extract_netlist(autre, "uno").components)
    assert c.type == _SHARP_DEFAULT_TYPE
    assert c.attributes.get("presumed_from_description") == "true"


def test_the_sharp_entry_does_not_steal_the_ir_receiver():
    """⛔ REGRESSION QUE J'AI INTRODUITE au #104, trouvee en QA AP9.2.

    L'entree corpus `sharpdistsensor` ouvrait sur « Telemetre INFRAROUGE
    analogique Sharp ». L'empreinte etant la MOYENNE de ses jetons (#65), un
    mot fort en tete d'une description courte domine -- et elle sortait a
    **0,732** sur « recepteur infrarouge sur la broche 4 », devant
    `irremote`, qui n'etait JAMAIS retrouvee. L'app repondait « capteur de
    distance » a qui demandait un recepteur de telecommande.

    Deux corrections, et la seconde n'est pas celle qu'on croit :
      - ses mots-cles IR (« telemetre infrarouge courte portee », « short
        range IR distance sensor ») cedent la place a des formes ancrees sur
        la DISTANCE ;
      - sa description est reancree : « Mesure de DISTANCE… » d'abord, le mot
        infrarouge plus loin, et une phrase qui dit ce qu'elle N'EST PAS.

    ⚠️ ET UNE LECON DE METHODE, payee sur place : ajouter les bons mots-cles
    a `irremote` EN QUEUE de sa liste n'a RIEN change -- matrice bit a bit
    identique. L'encodeur tronque a 128 jetons, la description en consomme la
    moitie, et 83 mots les precedaient. Il a fallu les mettre EN TETE. C'est
    la lecon du #65 (« les traductions fr/es/it n'entraient jamais »), sur
    une autre entree.
    """
    import contextlib, io as _io
    from ui import rag
    for p_ in ("recepteur infrarouge sur la broche 4",
               "an infrared receiver on pin 4"):
        with contextlib.redirect_stdout(_io.StringIO()):
            libs = rag.retrieve_libs(p_)
        noms = [l.get("name") for l in (libs or [])]
        assert "IRremote" in noms, (p_, noms)
        if "SharpDistSensor" in noms:
            assert noms.index("IRremote") < noms.index("SharpDistSensor"), (
                f"{p_!r} : le capteur de DISTANCE passe devant la lib de "
                f"TELECOMMANDE -- {noms}")
    # ... et les Sharp restent trouvables par leur reference.
    for p_, attendu in (("un capteur 2Y0A60 sur A0", "SharpDistSensor"),
                        ("un GP2Y0A710K0F sur A0", "SharpDistSensor"),
                        ("un capteur 2Y0A21 sur A0", "SharpIR")):
        with contextlib.redirect_stdout(_io.StringIO()):
            libs = rag.retrieve_libs(p_)
        noms = [l.get("name") for l in (libs or [])]
        assert noms and noms[0] == attendu, (p_, noms)


def test_every_model_reaches_the_library_that_covers_it():
    """⛔ LE PIEGE DE LA CANONISATION, mesure le 2026-09-09.

    Le retrieval ne voit PAS la reference telle que l'utilisateur l'ecrit :
    elle est ramenee a `2Y0Ann` en amont. Les mots-cles du corpus doivent
    donc porter la forme CANONIQUE, sinon l'appariement lexical meurt --
    et il meurt en silence, en rendant l'autre bibliotheque.

    Mesure du defaut : « GP2Y0A60SZLF » retrouvait SharpDistSensor a 0,847,
    mais sa forme canonisee `2Y0A60` retrouvait **SharpIR a 0,522** -- la
    mauvaise bibliotheque, au niveau du bruit, pour un modele qu'elle ne
    gere pas.

    ⚠️ On teste la forme CANONIQUE, pas la forme ecrite : c'est celle-la qui
    atteint le retrieval, et c'est celle qu'on cassait.
    """
    import contextlib, io as _io
    from ui import rag
    attendu = {
        "2Y0A21": "SharpIR", "2Y0A41": "SharpIR", "2Y0A02": "SharpIR",
        "2Y0A51": "SharpDistSensor", "2Y0A60": "SharpDistSensor",
        "2Y0A710": "SharpDistSensor",
    }
    for ref, lib in attendu.items():
        p_ = f"mesure la distance avec un {ref} sur A0"
        with contextlib.redirect_stdout(_io.StringIO()):
            libs = rag.retrieve_libs(p_)
        noms = [l.get("name") for l in (libs or [])]
        assert noms and noms[0] == lib, (ref, noms)


def test_the_six_models_each_have_their_own_box():
    """Un objet qu'on tient en main = une entree. Six modeles, six types,
    six fiches -- et la PORTEE dans le libelle, parce que c'est elle qui
    distingue deux capteurs par ailleurs identiques."""
    from ui.component_registry import by_id
    from ui.wiring.layout.component_catalog import CATALOG
    from ui.wiring.instructions import _TYPE_LABEL
    from ui.wiring.component_names import _UNIVERSAL_NAME
    portees = {"gp2y0a21": "80", "gp2y0a41": "30", "gp2y0a02": "150",
               "gp2y0a51": "15", "gp2y0a60": "150", "gp2y0a710": "500"}
    for t, portee in portees.items():
        assert t in CATALOG, t
        assert set((CATALOG[t].pin_labels or {}).values()) == {"VCC", "GND", "OUT"}
        assert by_id(t) is not None, t
        assert _UNIVERSAL_NAME.get(t), t
        assert len(_UNIVERSAL_NAME[t]) <= 13, (t, _UNIVERSAL_NAME[t])
        for lg in ("fr", "en", "es", "it"):
            assert portee in _TYPE_LABEL[t][lg], (t, lg, _TYPE_LABEL[t][lg])
    # Les documents : SharpIR par defaut la ou elle gere, sinon l'autre.
    for t in ("gp2y0a21", "gp2y0a41", "gp2y0a02"):
        assert by_id(t).documents == ("sharpir", "sharpdistsensor"), t
    for t in ("gp2y0a51", "gp2y0a60", "gp2y0a710"):
        assert by_id(t).documents == ("sharpdistsensor",), t


def test_a_three_digit_model_is_not_truncated():
    """⛔ La regle « `2Y0A` + DEUX chiffres » etait incomplete : le A710 et le
    A700 en ont trois, et sortaient canonises en `2Y0A71` / `2Y0A70` -- des
    modeles qui n'existent pas.

    ⚠️ Le nombre de chiffres est AMBIGU en general, donc ce sont les DONNEES
    qui tranchent, pas la gourmandise de la regex : la lecture a trois
    chiffres n'est retenue que si elle designe un modele connu.
    """
    from ui.wiring.markers import _canonicalize_sharp_models as canon
    assert canon("GP2Y0A710K0F") == "2Y0A710"
    assert canon("GP2Y0A700K0F") == "2Y0A700"
    assert canon("GP2Y0A21YK0F") == "2Y0A21"
    # Code de date COLLE : la lecture a trois chiffres serait « 218 », qui
    # n'existe pas -> on retombe sur « 21 », qui existe.
    assert canon("2Y0A2181") == "2Y0A21"


def test_the_prompt_path_works_in_the_four_languages():
    """Broche analogique nue + le prompt qui nomme le composant."""
    for p in ("un telemetre infrarouge sur A0",
              "un capteur de distance infrarouge sur A0",
              "an IR distance sensor on A0",
              "an infrared distance sensor on A0",
              "un sensor de distancia infrarrojo en A0",
              "un sensore di distanza infrarosso su A0"):
        assert _un_sharp(_types(_ANALOG, p)), p


def test_the_library_signature_is_detected_on_its_own():
    """Le chemin qui compte le plus une fois le corpus en place.

    Quand le RAG a injecte la bibliotheque, le modele ecrit
    `#include <SharpIR.h>` et un constructeur -- il n'y a plus d'`analogRead`
    dans le sketch. Sans ce detecteur, le composant tombait dans le filet des
    en-tetes inconnus : boite a 4 broches NON CABLEE.
    """
    types = _types(_AVEC_LIB)
    assert _un_sharp(types), types
    # ⛔ ET IL EST SEUL. Sans `claimed_headers.add("sharpir.h")`, le filet des
    # includes inconnus ajoutait une BOITE FANTOME a 4 broches aux nets vides
    # -- le piege documente au TODO #84. Mesure du 2026-09-09 : le sketch
    # rendait `gp2y0a41` ET un `gp2y0a02` fantome. Le defaut est NE de
    # l'eclatement (avant, l'alias d'en-tete ne visait qu'un seul type) et
    # aucune assertion sur les broches ne pouvait le voir.
    assert len(types) == 1, f"une boite fantome accompagne le composant : {types}"
    c = next(c for c in extract_netlist(_AVEC_LIB, "uno").components
             if c.type in _SHARPS)
    assert [(p.name, p.net) for p in c.pins] == [
        ("VCC", "5V"), ("GND", "GND"), ("OUT", "A0")], c.pins
    # ✅ Depuis l'eclatement du 2026-09-09, la CONSTANTE du constructeur
    # decide du type emis -- c'est le code lui-meme qui dit quel modele, la
    # meilleure source possible. Le cablage, lui, reste identique.
    for modele, attendu in (("SharpIR::GP2Y0A41SK0F", "gp2y0a41"),
                            ("SharpIR::GP2Y0A02YK0F", "gp2y0a02"),
                            ("GP2Y0A21YK0F", "gp2y0a21")):
        code = _AVEC_LIB.replace("SharpIR::GP2Y0A21YK0F", modele)
        c = next((x for x in extract_netlist(code, "uno").components
                  if x.type in _SHARPS), None)
        assert c and c.type == attendu, (modele, c.type if c else None)
        assert [p.net for p in c.pins] == ["5V", "GND", "A0"], modele
    # ⚠️ Un entier nu (`SharpIR s(1, A0)`, que le modele de langage ecrit
    # parfois) ne nomme rien de lisible : on retombe sur le defaut, et on le
    # DIT. Nommer une supposition la rend corrigeable ; la taire l'enterre.
    code = _AVEC_LIB.replace("SharpIR::GP2Y0A21YK0F", "1")
    c = next(x for x in extract_netlist(code, "uno").components
             if x.type in _SHARPS)
    assert c.type == _SHARP_DEFAULT_TYPE
    assert c.attributes.get("presumed_from_description") == "true"


def test_the_catalog_agrees_with_what_markers_emits():
    """⛔ La condition du cablage (#93) : le routage apparie par EGALITE DE
    NOM. Ici les DEUX chemins doivent s'accorder avec la meme entree."""
    for t in _SHARPS:
        catalogue = set((CATALOG[t].pin_labels or {}).values())
        assert catalogue == {"VCC", "GND", "OUT"}, (t, catalogue)
    catalogue = {"VCC", "GND", "OUT"}
    for code, prompt in ((_AVEC_LIB, ""),
                         (_ANALOG, "un capteur 2Y0A21 sur A0")):
        c = next(c for c in extract_netlist(code, "uno", prompt=prompt).components
                 if c.type in _SHARPS)
        assert {p.name for p in c.pins} <= catalogue, (code[:20], c.pins)


def test_it_never_claims_to_have_read_a_guess_in_the_code():
    """Le type naissant AUSSI d'une broche nue requalifiee par le prompt, il
    est dans `_BARE_PIN_TYPES`.

    ⚠️ Le drapeau est porte par le TYPE, pas par l'instance : il ne sait pas
    dire « certain par la signature, presume par le prompt ». On tranche du
    cote SUR -- sous-estimer laisse l'engrenage ouvert et ne coute rien,
    surestimer presenterait une devinette comme une lecture.
    """
    for code, prompt in ((_ANALOG, "un capteur 2Y0A21 sur A0"),
                         (_AVEC_LIB, "")):
        c = next(c for c in extract_netlist(code, "uno", prompt=prompt).components
                 if c.type in _SHARPS)
        assert not c.attributes.get("signature_detected"), code[:20]


def test_no_new_keyword_steals_a_neighbour():
    """⛔ Deux mots NUS sont ecartes, et chacun pour une raison mesurable.

    « distance » appartient au `ClarifyGroup` distance, ou quatre puces se
    disputent le mot -- le revendiquer trancherait en silence. « infrarouge »
    appartient d'abord au RECEPTEUR de telecommande. Ne restent que la
    reference et les expressions ou les DEUX idees sont reunies.
    """
    for mot in ("distance", "infrarouge", "infrared", "ir", "sharp",
                "distancia", "distanza"):
        assert mot not in _SHARP_IR_KEYWORDS, f"« {mot} » nu est trop large"
    # Et a l'execution, les deux voisins gardent leur bien.
    assert not _un_sharp(_types(_ANALOG, "un capteur de distance sur A0"))
    _DI = "void setup(){pinMode(4,INPUT);}\nvoid loop(){digitalRead(4);}"
    for p in ("un recepteur infrarouge sur la broche 4",
              "an infrared receiver on pin 4"):
        assert not _un_sharp(_types(_DI, p)), p


def test_the_three_models_reach_the_language_model():
    """Se tromper de modele rend des distances FAUSSES QUI COMPILENT.

    C'est tout l'interet d'avoir mis la bibliotheque au corpus : les trois
    constantes doivent etre dans le bloc d'API, sinon le modele en invente
    une ou en choisit une au hasard.
    """
    e = next(x for x in _corpus() if x["id"] == "sharpir")
    sigs = " ".join(e["api_signatures"]["SharpIR"])
    for constante in ("GP2Y0A41SK0F", "GP2Y0A21YK0F", "GP2Y0A02YK0F"):
        assert constante in sigs, f"{constante} n'atteint pas le modele"
    # ⚠️ Ce sont les SEULES que la bibliotheque definit -- verifie dans son
    # en-tete, pas suppose. En inventer une quatrieme ne compilerait pas.
    assert "GP2Y0A02YK0F" in e["example_code"] or \
           "GP2Y0A21YK0F" in e["example_code"]
    assert e["headers"] == ["SharpIR.h"]
    assert e["arduino_lib_name"] == "SharpIR"


def test_it_joined_the_distance_family():
    """Sans ca, « un capteur de distance » vague ne pouvait pas se resoudre
    vers le Sharp -- et c'est celui d'un kit d'entree de gamme."""
    from ui.clarification_groups import match_group
    g = match_group("je veux mesurer une distance")
    assert g is not None
    ids = [c.corpus_id for c in g.candidates]
    assert "sharpir" in ids, ids
    svg = {c.corpus_id: c.svg_type for c in g.candidates}
    # ⚠️ Le `svg_type` doit etre un type REEL : depuis le 2026-09-09 il n'y
    # a plus de `sharp_ir` generique, et le groupe designe le plus courant.
    assert svg["sharpir"] == _SHARP_DEFAULT_TYPE, svg
    from ui.wiring.layout.component_catalog import CATALOG as _CAT
    assert svg["sharpir"] in _CAT, "le groupe pointe vers un type inexistant"


def test_the_embedding_matrix_still_lines_up_with_the_corpus():
    """La matrice accompagne le corpus PAR POSITION, et son propre test ne
    verifie que le NOMBRE de lignes : un desalignement passerait au vert en
    silence. L'entree a donc ete inseree EN FIN de fichier."""
    import numpy as np
    corpus = _corpus()
    matrice = np.load(ROOT / "assets" / "rag" / "embeddings.npy")
    assert matrice.shape[0] == len(corpus), (matrice.shape, len(corpus))
    assert corpus[-1]["id"] == "sharpdistsensor", (
        "l'entree n'est plus la derniere : soit elle a bouge, soit une autre "
        "a ete inseree apres elle sans reconstruire la matrice")


TESTS = [
    test_the_silkscreen_spelling_works_as_well_as_the_catalogue_one,
    test_every_real_silkscreen_form_is_recognised,
    test_the_pattern_leaves_the_other_sharp_families_alone,
    test_the_brand_alone_is_not_a_component,
    test_the_a51_has_its_own_library_and_its_own_box,
    test_the_second_library_is_detected_from_its_setModel,
    test_the_sharp_entry_does_not_steal_the_ir_receiver,
    test_every_model_reaches_the_library_that_covers_it,
    test_the_six_models_each_have_their_own_box,
    test_a_three_digit_model_is_not_truncated,
    test_every_writing_behaves_the_SAME_all_the_way_down,
    test_the_prompt_path_works_in_the_four_languages,
    test_the_library_signature_is_detected_on_its_own,
    test_the_catalog_agrees_with_what_markers_emits,
    test_it_never_claims_to_have_read_a_guess_in_the_code,
    test_no_new_keyword_steals_a_neighbour,
    test_the_three_models_reach_the_language_model,
    test_it_joined_the_distance_family,
    test_the_embedding_matrix_still_lines_up_with_the_corpus,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}", flush=True)
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}", flush=True)
    print(f"\n{passed}/{len(TESTS)} tests passed", flush=True)
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
