"""Etape 2 de la checklist pour les composants importes de Fritzing (TODO #94).

Contexte. L'import en lot du 2026-08-19 (commit b9b1566, « 40 brochages
Fritzing de plus ») a fait l'etape 1 de la checklist « ajouter un composant »
de CLAUDE.md -- l'entree catalogue -- et AUCUNE des suivantes. Resultat mesure
le 2026-09-07 sur 15 prompts qui NOMMENT le composant : 0 reconnu sur 15. Un
solenoide sortait dessine en LED avec sa resistance serie, un capteur
d'humidite du sol en potentiometre 10 kΩ.

Ce fichier verrouille la detection des dix types repris, et surtout les
DECISIONS qui les entourent -- ce sont elles qu'une reprise distraite casserait
sans que rien ne rougisse.

Run : python scripts/test_imported_components_detection.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.wiring.layout.component_catalog import CATALOG
from ui.wiring.markers import (extract_netlist, _has_keyword,
                               _LDR_KEYWORDS, _BUZZER_KEYWORDS,
                               _SPEAKER_KEYWORDS, _JOYSTICK_KEYWORDS,
                               _POT_SUBTYPE_CANDIDATES,
                               _BTN_SUBTYPE_CANDIDATES)

_ANALOG = "void setup(){}\nvoid loop(){int v=analogRead(A0);}"
_INPUT = "void setup(){pinMode(4,INPUT_PULLUP);}\nvoid loop(){int v=digitalRead(4);}"
_TONE = "void setup(){}\nvoid loop(){tone(7, 440); delay(200); noTone(7);}"
_TWO_AXES = ("void setup(){}\nvoid loop(){int x=analogRead(A0);"
             "int y=analogRead(A1);}")


def _types(code, prompt):
    return [c["type"]
            for c in extract_netlist(code, "uno", prompt=prompt)
            .to_dict()["components"]]


def _component(code, prompt, type_id):
    for c in extract_netlist(code, "uno", prompt=prompt).to_dict()["components"]:
        if c["type"] == type_id:
            return c
    return None


def test_each_new_type_is_recognised_in_the_four_languages():
    """Le coeur du ticket : nommer le composant doit le faire apparaitre.

    Une langue par cas au minimum, comme l'exige l'etape 4 de la checklist.
    Avant ce chantier, les dix rendaient un potentiometre, un bouton ou une LED.
    """
    cas = {
        "tmp36": [(_ANALOG, "un capteur TMP36 sur A0"),
                  (_ANALOG, "a TMP36 sensor on A0")],
        "soil_moisture": [(_ANALOG, "capteur d'humidite du sol sur A0"),
                          (_ANALOG, "a soil moisture sensor on A0"),
                          (_ANALOG, "sensor de humedad del suelo en A0"),
                          (_ANALOG, "sensore di umidita del suolo su A0")],
        "force_sensor": [(_ANALOG, "un capteur de force sur A0"),
                         (_ANALOG, "a force sensor on A0"),
                         (_ANALOG, "un sensor de fuerza en A0"),
                         (_ANALOG, "un sensore di forza su A0")],
        "flex_sensor": [(_ANALOG, "un capteur de flexion sur A0"),
                        (_ANALOG, "a flex sensor on A0"),
                        (_ANALOG, "un sensor de flexion en A0"),
                        (_ANALOG, "un sensore di flessione su A0")],
        "speaker": [(_TONE, "un haut-parleur sur la broche 7"),
                    (_TONE, "a speaker on pin 7"),
                    (_TONE, "un altavoz en el pin 7"),
                    (_TONE, "un altoparlante sul pin 7")],
        "reed_switch": [(_INPUT, "un interrupteur reed sur la broche 4"),
                        (_INPUT, "a reed switch on pin 4"),
                        (_INPUT, "un interruptor reed en el pin 4"),
                        (_INPUT, "un interruttore reed sul pin 4")],
        "tilt_switch": [(_INPUT, "un capteur d'inclinaison sur la broche 4"),
                        (_INPUT, "a tilt switch on pin 4"),
                        (_INPUT, "un sensor de inclinacion en el pin 4"),
                        (_INPUT, "un sensore di inclinazione sul pin 4")],
        "slide_switch": [(_INPUT, "un interrupteur a glissiere sur la broche 4"),
                         (_INPUT, "a slide switch on pin 4"),
                         (_INPUT, "un interruptor deslizante en el pin 4"),
                         (_INPUT, "un interruttore a scorrimento sul pin 4")],
        "toggle_switch": [(_INPUT, "un interrupteur a bascule sur la broche 4"),
                          (_INPUT, "a toggle switch on pin 4"),
                          (_INPUT, "un interruptor de palanca en el pin 4"),
                          (_INPUT, "un interruttore a levetta sul pin 4")],
        "touch_sensor": [(_INPUT, "un capteur tactile sur la broche 4"),
                         (_INPUT, "a touch sensor on pin 4"),
                         (_INPUT, "un sensor tactil en el pin 4"),
                         (_INPUT, "un sensore tattile sul pin 4")],
        "joystick": [(_TWO_AXES, "un joystick sur A0 et A1"),
                     (_TWO_AXES, "a thumbstick"),
                     (_TWO_AXES, "una palanca de mando"),
                     (_TWO_AXES, "una levetta analogica")],
    }
    for type_id, prompts in cas.items():
        for code, prompt in prompts:
            obtenus = _types(code, prompt)
            assert type_id in obtenus, (
                f"{prompt!r} -> {obtenus} (attendu {type_id})")


def test_every_new_type_is_fully_wired_on_the_diagram():
    """Reconnaitre ne suffit pas : le schema doit porter les fils.

    C'est la lecon du #93 -- un desaccord de nom entre `markers` et le
    catalogue ne produit AUCUN fil et AUCUN message. Chaque type ajoute ici
    passe donc par le placement et le routage reels, pas par une comparaison
    de chaines.
    """
    from ui.wiring.layout.layout import place_scene
    from ui.wiring.layout.routing import route_wires

    board = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"
    cas = [
        ("tmp36", _ANALOG, "un capteur TMP36 sur A0"),
        ("soil_moisture", _ANALOG, "capteur d'humidite du sol sur A0"),
        ("force_sensor", _ANALOG, "un capteur de force sur A0"),
        ("flex_sensor", _ANALOG, "un capteur de flexion sur A0"),
        ("speaker", _TONE, "un haut-parleur sur la broche 7"),
        ("reed_switch", _INPUT, "un interrupteur reed sur la broche 4"),
        ("tilt_switch", _INPUT, "un capteur d'inclinaison sur la broche 4"),
        ("slide_switch", _INPUT, "un interrupteur a glissiere sur la broche 4"),
        ("toggle_switch", _INPUT, "un interrupteur a bascule sur la broche 4"),
        ("touch_sensor", _INPUT, "un capteur tactile sur la broche 4"),
        ("joystick", _TWO_AXES, "un joystick sur A0 et A1"),
    ]
    for type_id, code, prompt in cas:
        comps = extract_netlist(code, "uno", prompt=prompt).to_dict()["components"]
        comp = next((c for c in comps if c["type"] == type_id), None)
        assert comp is not None, f"{type_id} non detecte"
        catalog = [CATALOG[type_id].pin_labels[i + 1]
                   for i in range(CATALOG[type_id].pin_count)]
        orphelines = [p["name"] for p in comp["pins"] if p["name"] not in catalog]
        assert not orphelines, (
            f"{type_id} : broches emises absentes du catalogue {orphelines} — "
            f"elles ne recevront jamais de fil (catalogue {catalog})")
        routes = {w.net for w in route_wires(place_scene(comps, board), comps)}
        attendus = {p["net"] for p in comp["pins"] if p["net"]}
        assert not attendus - routes, (
            f"{type_id} : nets sans fil {sorted(attendus - routes)}")


def test_light_sensor_is_deliberately_absent():
    """Le type ECARTE, et la raison — sinon quelqu'un « completera » le lot.

    `_LDR_KEYWORDS` possede deja « light sensor » et « capteur de luminosite »,
    et ces prompts rendent `ldr`, ce qui est juste. Ajouter `light_sensor`
    fabriquerait la collision que la regle d'or de CLAUDE.md interdit : les
    deux types matcheraient, le double-hit ne deciderait rien, et on aurait
    REGRESSE un cas qui marchait.
    """
    assert "light_sensor" not in _POT_SUBTYPE_CANDIDATES, (
        "light_sensor ne doit pas etre un candidat : collision avec ldr")
    for prompt in ("un capteur de luminosite sur A0", "a light sensor on A0"):
        assert "ldr" in _types(_ANALOG, prompt), prompt


def test_the_bare_word_switch_belongs_to_nobody():
    """La condition pour que les cinq interrupteurs coexistent.

    « interrupteur » seul matcherait les cinq lexiques a la fois ; le
    double-hit ne decide rien, et on aurait ajoute cinq types sans rien
    reconnaitre de plus. Chaque lexique ne porte que ce qui le DISTINGUE.
    """
    for type_id in ("reed_switch", "tilt_switch", "slide_switch",
                    "toggle_switch", "touch_sensor"):
        mots = _BTN_SUBTYPE_CANDIDATES[type_id]
        nus = [m for m in mots if m.strip().lower() in
               ("interrupteur", "switch", "interruptor", "interruttore",
                "capteur", "sensor", "sensore")]
        assert not nus, f"{type_id} revendique un mot generique : {nus}"
    # Et le comportement qui en decoule : un mot nu ne mute rien.
    assert "button" in _types(_INPUT, "un interrupteur sur la broche 4")


def test_a_speaker_is_refined_from_the_buzzer_not_reclassified():
    """`tone()` designe un PROTOCOLE, pas une piece — d'ou un raffinement.

    Le premier essai ajoutait le haut-parleur aux candidats de sortie nue, et
    ne se declenchait jamais : `tone()` type deja la broche en buzzer avant
    toute reclassification. Meme raisonnement que pour l'ultrason.
    """
    assert "speaker" in _types(_TONE, "un haut-parleur sur la broche 7")
    assert "buzzer" in _types(_TONE, ""), "sans indice, le buzzer reste le defaut"
    assert "buzzer" in _types(_TONE, "un buzzer sur la broche 7")
    # Le prompt nomme les DEUX : on se tait plutot que de tirer au sort.
    assert "buzzer" in _types(_TONE, "un buzzer et un haut-parleur")
    # Les deux lexiques restent disjoints, sinon le silence ci-dessus
    # deviendrait la regle au lieu de l'exception.
    for mot in _SPEAKER_KEYWORDS:
        assert not _has_keyword(mot, _BUZZER_KEYWORDS), mot


def test_the_speaker_gets_its_series_resistor():
    """Electriquement necessaire, pas cosmetique.

    Un haut-parleur 8 Ω branche nu sur une broche tirerait environ 600 mA
    quand une broche Arduino en fournit 20. La resistance de 100 Ω est une
    condition de fonctionnement.
    """
    from ui.wiring.inference import apply_rules
    netlist = extract_netlist(_TONE, "uno", prompt="un haut-parleur sur la broche 7")
    apply_rules(netlist)
    resistances = [c for c in netlist.components if c.type == "resistor"]
    assert resistances, "aucune resistance serie posee sur le haut-parleur"
    assert resistances[0].attributes.get("value") == "100", resistances[0].attributes


def test_the_toggle_switch_leaves_its_second_throw_unwired():
    """Un inverseur a trois bornes, et le code n'en decrit que deux.

    Inventer un fil sur la seconde voie presenterait une devinette comme une
    lecture. Une broche dessinee sans fil est le cas normal (cf. le BME280 du
    #93, dont CSB et SDO restent libres).
    """
    comp = _component(_INPUT, "un interrupteur a bascule sur la broche 4",
                      "toggle_switch")
    assert comp is not None
    nets = {p["name"]: p["net"] for p in comp["pins"]}
    assert nets["COM"] == "D4", nets
    assert nets["L1"] == "GND", nets
    assert nets["L2"] == "", "la seconde voie ne doit PAS etre cablee"


def test_the_joystick_groups_and_stays_silent_when_unsure():
    """Il ne derive pas d'UNE broche : il en regroupe deux ou trois.

    D'ou une passe dediee. Et le corollaire, qui est la moitie qui compte :
    trois entrees analogiques voudraient dire un joystick PLUS un
    potentiometre, ou deux joysticks — rien ne dit lesquelles vont ensemble,
    donc on se tait.
    """
    comp = _component(_TWO_AXES, "un joystick sur A0 et A1", "joystick")
    assert comp is not None
    nets = {p["name"]: p["net"] for p in comp["pins"]}
    assert nets["HORZ"] == "A0" and nets["VERT"] == "A1", nets
    assert nets["SEL"] == "", "sans entree digitale, SEL reste libre"
    assert comp["attributes"].get("presumed_from_description") == "true", (
        "l'ordre des axes est DEVINE — le composant doit le declarer")

    trois_axes = ("void setup(){}\nvoid loop(){int x=analogRead(A0);"
                  "int y=analogRead(A1);int z=analogRead(A2);}")
    assert "joystick" not in _types(trois_axes, "un joystick sur A0 et A1"), (
        "trois entrees analogiques : on ne doit PAS deviner lesquelles vont "
        "ensemble")
    # Sans mention, deux potentiometres restent deux potentiometres.
    assert "joystick" not in _types(_TWO_AXES, "deux potentiometres")


def test_the_joystick_does_not_swallow_another_input():
    """Il consomme un bouton, donc il tourne APRES les sous-typages.

    Un « detecteur de mouvement » cite dans le meme prompt doit rester un PIR,
    pas devenir le clic du manche.
    """
    code = ("void setup(){pinMode(4,INPUT_PULLUP);}\n"
            "void loop(){int x=analogRead(A0);int y=analogRead(A1);"
            "int s=digitalRead(4);}")
    obtenus = _types(code, "un joystick et un detecteur de mouvement PIR "
                           "sur la broche 4")
    assert "joystick" in obtenus and "pir" in obtenus, obtenus
    # Et quand le bouton reste neutre, c'est bien le clic du manche.
    comp = _component(code, "un joystick avec son bouton", "joystick")
    assert comp is not None
    assert {p["name"]: p["net"] for p in comp["pins"]}["SEL"] == "D4"


def test_the_forbidden_bare_words_stay_out_of_the_new_lexicons():
    """Deux mots qui appartiennent a d'AUTRES composants deja detectes.

    « humidite » seul est celui du DHT11/22, qui mesure l'humidite de l'AIR ;
    « pression » seul est celui des barometres BMP/BME du corpus. Les laisser
    entrer ferait planter une sonde de terre ou un capteur de force sur des
    prompts qui parlent d'autre chose.
    """
    for type_id in ("soil_moisture", "force_sensor", "flex_sensor", "tmp36"):
        for mot in _POT_SUBTYPE_CANDIDATES[type_id]:
            nu = mot.strip().lower()
            assert nu not in ("humidite", "humidité", "humidity",
                              "pression", "pressure", "presion"), (
                f"{type_id} revendique le mot nu {mot!r}")


def test_a_software_header_is_not_a_component():
    """Un `#include` de generation de son n'est pas du materiel (QA AK2.1).

    Sur « joue une melodie sur un haut-parleur », le modele ecrit
    `#include <Tone.h>` ou `#include "pitches.h"` -- ce dernier vient de
    l'exemple OFFICIEL `toneMelody` d'Arduino, donc il le reproduit
    fidelement. Le repli « en-tete inconnu » fabriquait alors une boite
    fantome de 4 broches, non cablee, a cote du haut-parleur correctement
    dessine. Meme classe que `arduino_secrets.h` et `adalogo.h`.
    """
    for entete in ("<Tone.h>", '"pitches.h"', '"notes.h"', "<NewTone.h>",
                   "<toneAC.h>"):
        code = (f"#include {entete}\n"
                f"void setup(){{}}\nvoid loop(){{tone(7, 440);}}")
        types = _types(code, "un haut-parleur sur la broche 7")
        assert types == ["speaker"], (
            f"#include {entete} a fabrique un composant fantome : {types}")


def test_the_series_resistor_names_the_right_component():
    """La regle couvre le buzzer ET le haut-parleur : le message doit suivre.

    Signale en QA AK2.1 : l'avertissement disait « pour le BUZZER LS1 » devant
    un haut-parleur. La regle avait ete etendue au #94, pas son texte.
    """
    from ui.wiring.inference import apply_rules
    from ui.wiring.instructions import render_instructions

    attendus = {
        "speaker": {"fr": "haut-parleur", "en": "speaker",
                    "es": "altavoz", "it": "l'altoparlante"},
        "buzzer": {"fr": "buzzer", "en": "buzzer",
                   "es": "zumbador", "it": "cicalino"},
    }
    prompts = {"speaker": "un haut-parleur sur la broche 7",
               "buzzer": "un buzzer sur la broche 7"}
    for type_id, mots in attendus.items():
        netlist = apply_rules(extract_netlist(_TONE, "uno",
                                              prompt=prompts[type_id]))
        for langue, mot in mots.items():
            texte = render_instructions(netlist, lang=langue)
            ligne = next((l for l in texte.splitlines()
                          if "100" in l and "Ω" in l), "")
            assert mot in ligne, (
                f"[{langue}] {type_id} : « {mot} » absent de {ligne.strip()!r}")
        # Et l'autre type ne doit PAS y figurer.
        autre = "buzzer" if type_id == "speaker" else "haut-parleur"
        ligne = next((l for l in render_instructions(netlist, lang="fr").splitlines()
                      if "100" in l and "Ω" in l), "")
        assert autre not in ligne, f"{type_id} nomme {autre!r} : {ligne.strip()!r}"


def test_a_type_born_from_a_prompt_is_never_called_code_certain():
    """Garde DÉRIVÉE, pas une liste — c'est elle qui aurait évité le défaut.

    Signalé en QA AK2.1 (2026-09-07) : `tmp36` et `reed_switch` sortaient avec
    `signature_detected=True`, c'est-à-dire que l'app affirmait les avoir LUS
    DANS LE CODE alors qu'ils viennent du PROMPT. Onze types ajoutés au #94
    manquaient à `_BARE_PIN_TYPES`.

    Plutôt que de re-lister les onze, ce test dérive l'invariant : **tout type
    qui figure dans une table de candidats naît d'une broche nue requalifiée
    par le texte**, donc aucun ne peut être certain. Un futur candidat oublié
    fait rougir la suite sans qu'on ait à y penser.
    """
    from ui.wiring.markers import (_BARE_PIN_TYPES, _LED_RECLASSIF_CANDIDATES)

    nes_du_texte = (set(_POT_SUBTYPE_CANDIDATES) | set(_BTN_SUBTYPE_CANDIDATES)
                    | set(_LED_RECLASSIF_CANDIDATES))
    # `stepper` et `dc_motor` ont leur propre chemin de certitude (#84) : le
    # code peut les NOMMER par un constructeur, ils ne sont donc pas
    # intrinsèquement des déductions de broche nue.
    nes_du_texte -= {"stepper", "dc_motor", "servo"}
    manquants = sorted(nes_du_texte - _BARE_PIN_TYPES)
    assert not manquants, (
        f"Ces types naissent d'un PROMPT mais `_is_signature_detected` les "
        f"dirait lus dans le code : {manquants}")


def test_the_speaker_follows_the_buzzer_everywhere_the_rule_applies():
    """La règle, le PLACEMENT et l'ACTION vivent dans trois fichiers.

    Le #94 a étendu au haut-parleur la résistance série du buzzer — dans
    `inference` seulement. Il manquait `PAIRED_MAIN_TYPES` (`layout`), d'où une
    résistance qui flottait à l'écart au lieu de longer le composant, et
    l'action de l'engrenage (`implicit_actions`). Signalé en QA AK2.1 par
    « pourquoi ne pas avoir utilisé la résistance modélisée comme sur une
    LED ? ».
    """
    from ui.wiring.inference import _SERIES_RESISTOR_TYPES
    from ui.wiring.layout.layout import PAIRED_MAIN_TYPES
    from ui.wiring.implicit_actions import available_actions
    from ui.wiring.inference import apply_rules

    for type_id in _SERIES_RESISTOR_TYPES:
        assert type_id in PAIRED_MAIN_TYPES, (
            f"{type_id} reçoit une résistance série mais n'est pas apparié : "
            f"elle sera dessinée à l'écart de son composant")

    for type_id, prompt in (("speaker", "un haut-parleur sur la broche 7"),
                            ("buzzer", "un buzzer sur la broche 7")):
        netlist = apply_rules(extract_netlist(_TONE, "uno", prompt=prompt))
        comp = next((c for c in netlist.components if c.type == type_id), None)
        assert comp is not None, type_id
        ids = [a.id for a in available_actions(comp, netlist)]
        assert "buzzer_series_value" in ids, (
            f"{type_id} : l'engrenage n'offre pas de régler sa résistance "
            f"série ({ids})")


TESTS = [
    test_each_new_type_is_recognised_in_the_four_languages,
    test_every_new_type_is_fully_wired_on_the_diagram,
    test_light_sensor_is_deliberately_absent,
    test_the_bare_word_switch_belongs_to_nobody,
    test_a_speaker_is_refined_from_the_buzzer_not_reclassified,
    test_the_speaker_gets_its_series_resistor,
    test_the_toggle_switch_leaves_its_second_throw_unwired,
    test_the_joystick_groups_and_stays_silent_when_unsure,
    test_the_joystick_does_not_swallow_another_input,
    test_a_software_header_is_not_a_component,
    test_the_series_resistor_names_the_right_component,
    test_a_type_born_from_a_prompt_is_never_called_code_certain,
    test_the_speaker_follows_the_buzzer_everywhere_the_rule_applies,
    test_the_forbidden_bare_words_stay_out_of_the_new_lexicons,
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
