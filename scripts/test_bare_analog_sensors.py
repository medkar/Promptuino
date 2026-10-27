"""Sept capteurs nus de plus sont reconnus au lieu d'un potentiometre (#98).

Contexte. Le #97 a supprime les bibliotheques fantomes injectees pour ces
composants ; il n'a rien change au DESSIN. Mesure du 2026-09-08, 20 prompts
qui NOMMENT le composant : **0 reconnu sur 20**. « un capteur de flamme sur
A0 » sortait dessine en potentiometre 10 kΩ -- avec la valeur de resistance
que ca implique -- et « un capteur a effet Hall » en bouton-poussoir.

Meme classe que le #94, un lot plus loin. Ce fichier verrouille les sept
types repris et surtout les DECISIONS qui les entourent : ce sont elles
qu'une reprise distraite casserait sans que rien ne rougisse.

Le ticket a ete livre en TROIS lots, parce que trois de ses sept types
demandaient un arbitrage qui n'est pas une ligne de lexique :
  - lot 1 : flamme, pluie, effet Hall, GUVA-S12SD ;
  - lot 2 : INA169 et ACS712, dont deux bornes se coupent EN SERIE dans le
    circuit mesure -- que l'app ne modelise pas ;
  - lot 3 : le capteur reflectif, dont la fiche importee decrivait un
    OPTO-COUPLEUR et non le module a trois fils du commerce.

Run : python scripts/test_bare_analog_sensors.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.wiring.layout.component_catalog import CATALOG
from ui.wiring.markers import (extract_netlist, _POT_SUBTYPE_CANDIDATES,
                               _BTN_SUBTYPE_CANDIDATES, _GUVA_KEYWORDS,
                               _HALL_SENSOR_KEYWORDS, _LDR_KEYWORDS)

_ANALOG = "void setup(){}\nvoid loop(){int v=analogRead(A0);}"
_INPUT = "void setup(){pinMode(4,INPUT_PULLUP);}\nvoid loop(){int v=digitalRead(4);}"

_NOUVEAUX = ("flame_sensor", "rain_sensor", "hall_sensor", "guva_s12sd",
             "ina169", "acs712", "ir_reflective_sensor")


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
    """Le coeur du ticket, premier lot. Avant, les quatre rendaient un
    potentiometre ou un bouton. Les trois autres types du ticket ont leurs
    propres tests plus bas -- leurs lexiques obeissent a d'autres regles."""
    cas = {
        "flame_sensor": [(_ANALOG, "un capteur de flamme sur A0"),
                         (_ANALOG, "a flame sensor on A0"),
                         (_ANALOG, "un sensor de llama en A0"),
                         (_ANALOG, "un sensore di fiamma su A0")],
        "rain_sensor": [(_ANALOG, "un capteur de pluie sur A0"),
                        (_ANALOG, "a rain sensor on A0"),
                        (_ANALOG, "un sensor de lluvia en A0"),
                        (_ANALOG, "un sensore di pioggia su A0")],
        "hall_sensor": [(_INPUT, "un capteur a effet Hall sur la broche 4"),
                        (_INPUT, "a hall sensor on pin 4"),
                        (_INPUT, "un sensor de efecto Hall en el pin 4"),
                        (_INPUT, "un sensore di Hall sul pin 4")],
        "guva_s12sd": [(_ANALOG, "un capteur UV GUVA-S12SD sur A0"),
                       (_ANALOG, "a GUVA-S12SD UV sensor on A0"),
                       (_ANALOG, "un sensor UV analogico GUVA en A0"),
                       (_ANALOG, "un sensore UV analogico GUVA su A0")],
    }
    for attendu, prompts in cas.items():
        for code, p in prompts:
            assert attendu in _types(code, p), f"{attendu} : {p!r}"


def test_the_line_follower_is_the_module_not_the_bare_chip():
    """Troisieme lot (#98), arbitrage utilisateur du 2026-09-08.

    La fiche importee decrivait la PUCE NUE : « A / C / E / K » est le
    brochage d'un OPTO-COUPLEUR -- anode et cathode d'une LED infrarouge,
    emetteur et collecteur d'un phototransistor. Ce qu'un debutant achete
    est un MODULE a trois fils.

    ⛔ Garder les quatre noms d'origine aurait fait sortir le composant sans
    AUCUN fil : le routage apparie par egalite de nom. C'est le defaut #93.
    """
    entree = CATALOG["ir_reflective_sensor"]
    assert entree.pin_count == 3, "le module a trois fils, pas quatre"
    labels = set((entree.pin_labels or {}).values())
    assert labels == {"VCC", "OUT", "GND"}, labels
    assert not (labels & {"A", "C", "E", "K"}), (
        "le brochage de la puce nue est revenu : aucun fil ne serait tire")
    for p in ("un capteur suiveur de ligne sur A0",
              "a line follower sensor on A0",
              "un sensor seguidor de linea en A0",
              "un sensore segui linea su A0",
              "un QRE1113 sur A0", "un TCRT5000 sur A0"):
        c = _component(_ANALOG, p, "ir_reflective_sensor")
        assert c, p
        assert {x["name"] for x in c["pins"]} == {"VCC", "OUT", "GND"}, p


def test_every_line_follower_reference_is_known_everywhere():
    """⛔ TROUVE EN QA (AP8, 2026-09-10) : « un capteur TCRT5000 sur A0 »
    sortait avec une banniere -- « librairie TCRT5000 trouvee au registre
    Arduino et utilisee » -- puis une boite NON CABLEE aux broches nommees
    1, 2, 3, 4.

    Cause : j'avais mis `tcrt5000` dans le lexique de CABLAGE au #98 sans
    l'ajouter aux mots-cles du REGISTRE. Le composant etait donc dessine ET
    traite comme une reference inconnue : recherche au registre Arduino,
    installation d'une bibliotheque tierce, `#include` inconnu du detecteur,
    et le filet des en-tetes inconnus posait une boite a 4 broches vides
    par-dessus.

    ⚠️ Le meme balayage a montre l'ecart INVERSE : `qrd1114` etait au
    REGISTRE et absent du LEXIQUE -- il sortait donc en potentiometre. Les
    deux tables doivent nommer les memes references, dans les deux sens.
    """
    from ui.component_registry import by_id
    from ui.registry_lookup import detect_unknown_part_tokens
    from ui.wiring.markers import _IR_REFLECTIVE_KEYWORDS
    kws = {k.lower() for k in by_id("ir_reflective_sensor").keywords}
    for ref in ("qre1113", "qrd1114", "tcrt5000"):
        assert ref in kws, f"« {ref} » manque aux mots-cles du REGISTRE"
        assert ref in _IR_REFLECTIVE_KEYWORDS, f"« {ref} » manque au LEXIQUE"
        p = f"un capteur {ref.upper()} sur A0"
        assert not detect_unknown_part_tokens(p), (
            f"{p!r} part au registre Arduino : l'app connait ce composant")
        assert "ir_reflective_sensor" in _types(_ANALOG, p), p


def test_the_ir_receiver_is_a_component_not_a_button():
    """⛔ TROUVE EN QA (AP9, 2026-09-10) : « allume une LED avec une
    telecommande, recepteur infrarouge sur la broche 4 » sortait dessine en
    BOUTON.

    Le recepteur IR avait pourtant TOUT -- entree catalogue 3 broches,
    categorie `digital_in`, libelle et nom court ×4 langues -- mais il
    n'etait candidat d'AUCUNE table de sous-typage : il ne naissait que
    d'une signature (`IRrecv`), donc jamais d'une broche nue. Exactement le
    trou du #94, sur un composant qu'on croyait couvert.

    ⚠️ Le mot « infrarouge » NU lui appartient : le lexique du suiveur de
    ligne l'ecrit depuis le #98, et cette table le lui rend enfin. Les deux
    ne se croisent pas -- le suiveur est ANALOGIQUE, le recepteur DIGITAL.
    """
    _DI = ("void setup(){pinMode(4,INPUT);}\n"
           "void loop(){int v=digitalRead(4);}")
    for p in ("recepteur infrarouge sur la broche 4",
              "allume une LED avec une telecommande, recepteur infrarouge sur la broche 4",
              "an infrared receiver on pin 4",
              "un mando a distancia en el pin 4",
              "un telecomando sul pin 4"):
        assert "ir_receiver" in _types(_DI, p), p
    # Trois fils utiles, comme le PIR.
    c = _component(_DI, "recepteur infrarouge sur la broche 4", "ir_receiver")
    assert {x["name"] for x in c["pins"]} == {"VCC", "OUT", "GND"}, c["pins"]
    # Il ne mange pas le bouton nu, ni le suiveur de ligne (analogique).
    assert "ir_receiver" not in _types(_DI, "un bouton sur la broche 4")
    assert "ir_receiver" not in _types(_ANALOG, "un capteur suiveur de ligne sur A0")


def test_the_line_follower_does_not_swallow_the_ir_receiver():
    """⛔ « infrarouge » NU appartient d'abord au RECEPTEUR infrarouge.

    Ce sont deux composants sans rapport ; le mot n'est qualifiant que dans
    « reflectif », « suiveur de ligne », « evitement d'obstacle ».
    """
    from ui.wiring.markers import _IR_REFLECTIVE_KEYWORDS
    for mot in ("infrarouge", "infrared", "infrarrojo", "infrarosso", "ir"):
        assert mot not in _IR_REFLECTIVE_KEYWORDS, (
            f"« {mot} » nu revendique aussi le recepteur infrarouge")
    _IR_RX = ("void setup(){pinMode(4,INPUT);}\n"
              "void loop(){int v=digitalRead(4);}")
    for p in ("un recepteur infrarouge sur la broche 4",
              "an infrared receiver on pin 4"):
        assert "ir_reflective_sensor" not in _types(_IR_RX, p), p


def test_the_line_follower_regained_its_swap_peers():
    """Il etait `NO_SWAP_PEER`, au motif que la PUCE NUE reunit deux
    composants optiques. Le catalogue decrit desormais le module, qui se lit
    a l'`analogRead` comme n'importe quel capteur analogique -- donc
    l'engrenage cesse de s'ouvrir sur une liste vide."""
    from ui.wiring.categories import category_of, ANALOG_IN
    assert category_of("ir_reflective_sensor") == ANALOG_IN
    from ui.wiring.component_replace import replace_component
    nl = extract_netlist(_ANALOG, "uno", prompt="un potentiometre sur A0")
    ref = next(c.ref for c in nl.components if c.type == "potentiometer")
    res = replace_component(nl, ref, "ir_reflective_sensor")
    assert res.ok, res.reason
    c = next(c for c in nl.components if c.ref == ref)
    assert [p.name for p in c.pins] == ["VCC", "OUT", "GND"]


def test_the_catalog_agrees_with_what_markers_emits():
    """⛔ La condition du cablage, pas une regle de style (#93).

    Le routage apparie les broches par EGALITE DE NOM. Un libelle qui ne
    correspond a rien ne produit AUCUN fil et AUCUN message -- un schema faux
    presente comme certain. C'est exactement ce que portait le GUVA-S12SD :
    la fiche importee disait « 5V / Out / GND », ou « 5V » nomme le NET et
    non la broche, et ou « Out » n'est meme pas « OUT ».
    """
    cas = {"flame_sensor": (_ANALOG, "un capteur de flamme sur A0"),
           "rain_sensor": (_ANALOG, "un capteur de pluie sur A0"),
           "hall_sensor": (_INPUT, "un capteur a effet Hall sur la broche 4"),
           "guva_s12sd": (_ANALOG, "un capteur GUVA-S12SD sur A0")}
    for t, (code, p) in cas.items():
        c = _component(code, p, t)
        assert c, t
        emis = {p_["name"] for p_ in c["pins"]}
        catalogue = set((CATALOG[t].pin_labels or {}).values())
        assert emis <= catalogue, (
            f"{t} : {emis - catalogue} n'existe pas au catalogue {catalogue} "
            f"-- ces broches ne recevraient aucun fil, en silence")


def test_the_gear_builds_the_real_pinout_now():
    """LE defaut que l'entree catalogue corrige, mesure avant correctif.

    `component_replace` ne fabrique un brochage qu'en LISANT `pin_labels` :
    sans entree, il garde les broches du composant qu'il remplace. Mesure du
    2026-09-08 : remplacer un potentiometre par un capteur Hall rendait une
    boite « Capteur Hall » aux broches nommees « A / W / B ». Les nets
    etaient bons, les libelles mentaient.
    """
    from ui.wiring.component_replace import replace_component
    # ⚠️ Chacun part de son PAIR de categorie -- le Hall est une entree
    # digitale depuis ce ticket, donc il ne se substitue pas a un
    # potentiometre : c'est un refus CORRECT, pas un echec du brochage.
    cas = [("flame_sensor", _ANALOG, "un potentiometre sur A0", "potentiometer"),
           ("rain_sensor", _ANALOG, "un potentiometre sur A0", "potentiometer"),
           ("hall_sensor", _INPUT, "un bouton sur la broche 4", "button")]
    for cible, code, p, depart in cas:
        nl = extract_netlist(code, "uno", prompt=p)
        ref = next(c.ref for c in nl.components if c.type == depart)
        res = replace_component(nl, ref, cible)
        assert res.ok, f"{depart} -> {cible} refuse : {res.reason}"
        c = next(c for c in nl.components if c.ref == ref)
        noms = [p_.name for p_ in c.pins]
        assert noms == ["VCC", "OUT", "GND"], f"{cible} : {noms}"


def test_none_of_them_claims_to_be_read_in_the_code():
    """Honnetete : ces types naissent d'une broche NUE que le prompt
    requalifie. `signature_detected` veut dire « lu dans le code » -- sans
    leur entree dans `_BARE_PIN_TYPES`, l'app affirmerait les avoir lus."""
    cas = [("flame_sensor", _ANALOG, "un capteur de flamme sur A0"),
           ("rain_sensor", _ANALOG, "un capteur de pluie sur A0"),
           ("hall_sensor", _INPUT, "un capteur a effet Hall sur la broche 4"),
           ("guva_s12sd", _ANALOG, "un capteur GUVA-S12SD sur A0")]
    for t, code, p in cas:
        c = _component(code, p, t)
        assert c and not c.get("signature_detected"), t


def test_hall_is_a_digital_input_not_an_analog_one():
    """Le module courant (A3144, KY-003) sort en tout-ou-rien.

    Le mettre parmi les sous-types du potentiometre l'aurait rendu
    introuvable sur le `digitalRead` qui est son cas normal.
    """
    assert "hall_sensor" in _BTN_SUBTYPE_CANDIDATES
    assert "hall_sensor" not in _POT_SUBTYPE_CANDIDATES
    for t in ("flame_sensor", "rain_sensor", "guva_s12sd"):
        assert t in _POT_SUBTYPE_CANDIDATES, t
        assert t not in _BTN_SUBTYPE_CANDIDATES, t


def test_no_new_keyword_collides_with_an_existing_lexicon():
    """⛔ Le double-hit ne decide RIEN : deux types qui matchent = aucun.

    Deux pieges reels, verifies plutot que supposes :
    - « uv light sensor » CONTIENT « light sensor », qui appartient a la LDR.
      L'ajouter aurait fait reconnaitre MOINS qu'avant.
    - « hall » NU est un mot ordinaire en francais et en espagnol (« le hall
      d'entree »), et un mot anglais courant.
    """
    assert not any("light sensor" in k for k in _GUVA_KEYWORDS), (
        "un mot-cle du GUVA contient un mot-cle de la LDR : double-hit")
    assert "hall" not in _HALL_SENSOR_KEYWORDS, (
        "« hall » nu matcherait « le hall d'entree »")
    # Et la garde a l'execution : la phrase ordinaire ne doit rien declencher.
    assert "hall_sensor" not in _types(
        _INPUT, "un bouton dans le hall d'entree sur la broche 4")
    # La LDR reste reconnue par son propre lexique, inchange.
    assert "light sensor" in _LDR_KEYWORDS
    assert "ldr" in _types(_ANALOG, "a light sensor on A0")


def test_no_new_type_swallows_a_neighbour():
    """Chaque lexique ne doit reconnaitre QUE son composant.

    Le balayage croise est ce qui attrape un mot trop large -- « capteur de
    feu » qui avalerait la flamme ET le capteur de temperature, par exemple.
    """
    cas = [("flame_sensor", _ANALOG, "un capteur de flamme sur A0"),
           ("rain_sensor", _ANALOG, "un capteur de pluie sur A0"),
           ("guva_s12sd", _ANALOG, "un capteur GUVA-S12SD sur A0")]
    for attendu, code, p in cas:
        types = _types(code, p)
        autres = [t for t in _NOUVEAUX if t != attendu and t in types]
        assert not autres, f"{p!r} fait aussi naitre {autres}"


def test_the_two_current_sensors_are_recognised_by_their_part_number():
    """Second lot (#98). Le lexique est REFERENCE UNIQUEMENT, et ce n'est pas
    de la prudence -- c'est la seule redaction possible :

    - « capteur de courant » NU est interdit depuis le #97 : un INA219 en
      porte le nom, mais il est en I2C et a une bibliotheque.
    - « capteur de courant ANALOGIQUE » ne servirait a rien : les DEUX le
      sont, donc les deux matcheraient, et le double-hit ne decide rien.
    """
    for t, prompts in {
        "ina169": ["un capteur de courant INA169 sur A0",
                   "an INA169 current sensor on A0",
                   "un sensor de corriente INA169 en A0",
                   "un sensore di corrente INA169 su A0"],
        "acs712": ["un capteur de courant ACS712 sur A0",
                   "an ACS712 current sensor on A0",
                   "un sensor de corriente ACS712 en A0",
                   "un sensore di corrente ACS712 su A0"],
    }.items():
        for p in prompts:
            assert t in _types(_ANALOG, p), f"{t} : {p!r}"
    # ⛔ Le mot nu ne doit toujours RIEN declencher.
    for p in ("un capteur de courant sur A0", "a current sensor on A0"):
        types = _types(_ANALOG, p)
        assert "ina169" not in types and "acs712" not in types, (
            f"{p!r} -> {types} : le mot nu appartient aussi a l'INA219, qui "
            f"est en I2C et a une bibliotheque")


def test_the_series_terminals_are_drawn_and_explained():
    """⛔ LA decision du second lot, arbitree par l'utilisateur le 2026-09-08.

    Ces deux bornes ne vont PAS a la carte : elles se coupent EN SERIE dans
    le circuit dont on mesure le courant, que l'app ne modelise pas. Trois
    choses doivent tenir ensemble :
      1. les CINQ broches sont dessinees -- « en vrai il a 6 pattes, n'en
         mettre que 4 induit un debutant en erreur » (2026-09-07) ;
      2. les deux bornes de mesure restent SANS FIL ;
      3. un info l'explique, sinon elles passent pour un oubli.
    """
    from ui.wiring.instructions import render_instructions
    attendu = {"ina169": ("VIN+", "VIN-"), "acs712": ("IP+", "IP-")}
    for t, bornes in attendu.items():
        nl = extract_netlist(_ANALOG, "uno",
                             prompt=f"un capteur de courant {t} sur A0")
        c = next(c for c in nl.components if c.type == t)
        # 1. les cinq broches existent au catalogue
        assert CATALOG[t].pin_count == 5, t
        labels = set((CATALOG[t].pin_labels or {}).values())
        assert set(bornes) <= labels, f"{t} : {bornes} absentes de {labels}"
        # 2. le detecteur n'en cable que trois -- les bornes de mesure non
        cablees = {p.name for p in c.pins}
        assert cablees == {"VCC", "OUT", "GND"}, f"{t} : {cablees}"
        assert not (cablees & set(bornes)), (
            f"{t} : une borne de mesure a recu un fil vers la carte")
        # 3. et l'info le dit, dans les quatre langues
        codes = [w.code for w in nl.warnings]
        assert "current_sensor_series_terminals" in codes, f"{t} : {codes}"
        for lg in ("fr", "en", "es", "it"):
            md = render_instructions(nl, "simple", lang=lg)
            assert bornes[0] in md, f"{t}/{lg} : les bornes ne sont pas dites"


def test_the_note_shows_in_the_default_mode():
    """Le mode par defaut de la modale est « simple ».

    Le reflexe aurait ete de ranger ce texte dans `_EXPLANATIONS`, qui est le
    mecanisme prevu pour la pedagogie -- mais `_render_step` ne le rend qu'en
    mode DETAILLE. L'information serait restee cachee a l'utilisateur qui en
    a le plus besoin. D'ou un warning, visible dans les deux modes.
    """
    from ui.wiring.instructions import render_instructions, _EXPLANATIONS
    nl = extract_netlist(_ANALOG, "uno", prompt="un capteur ACS712 sur A0")
    for mode in ("simple", "detailed"):
        assert "IP+" in render_instructions(nl, mode, lang="fr"), mode
    assert not any("series_terminal" in k for k in _EXPLANATIONS), (
        "range dans `_EXPLANATIONS`, le message disparaitrait du mode simple")


TESTS = [
    test_each_new_type_is_recognised_in_the_four_languages,
    test_the_two_current_sensors_are_recognised_by_their_part_number,
    test_the_series_terminals_are_drawn_and_explained,
    test_the_note_shows_in_the_default_mode,
    test_the_line_follower_is_the_module_not_the_bare_chip,
    test_every_line_follower_reference_is_known_everywhere,
    test_the_ir_receiver_is_a_component_not_a_button,
    test_the_line_follower_does_not_swallow_the_ir_receiver,
    test_the_line_follower_regained_its_swap_peers,
    test_the_catalog_agrees_with_what_markers_emits,
    test_the_gear_builds_the_real_pinout_now,
    test_none_of_them_claims_to_be_read_in_the_code,
    test_hall_is_a_digital_input_not_an_analog_one,
    test_no_new_keyword_collides_with_an_existing_lexicon,
    test_no_new_type_swallows_a_neighbour,
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
