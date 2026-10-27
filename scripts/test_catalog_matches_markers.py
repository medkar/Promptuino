"""Le catalogue doit nommer ses broches COMME `markers` les emet.

Contexte du defaut d'origine (2026-09-04, signale en test avec un etudiant).
Un BME280 -- une carte VMA335, alias corpus du BME280 -- apparaissait dans le
schema avec UN SEUL fil : GND. Ni l'alimentation, ni SDA, ni SCL.

La cause n'est ni dans la detection ni dans le routeur, elle est dans leur
DESACCORD. `markers` emettait `VCC / GND / SDA / SCL` ; l'entree catalogue
portait le brochage de la DATASHEET de la puce nue,
`GND / 3.3V / SDI/SDA / SCK/SCL / !CS / SDO/ADR`. Or le routage apparie les
broches par EGALITE DE NOM (`routing._name_to_pin_index`,
`router._I2C_PIN_NAMES`) : seul `GND` etait present des deux cotes, donc seul
`GND` recevait un fil. Les trois autres etaient perdues sans le moindre
message -- un schema faux presente comme certain, exactement ce que le reste
du pipeline de cablage s'interdit.

CLAUDE.md posait deja la regle (« `pin_labels` = ce que `markers` EMET, jamais
un brochage invente ») et `test_bare_component_pinouts` la verifiait -- mais
sur une liste FIGEE de huit types. Le BME280 n'y etait pas, le DS18B20 non
plus (`VDD / GND / DQ` contre `VCC / DATA / GND` : meme panne, meme symptome).
Ce fichier-ci fait le tour COMPLET, par execution, sans liste a tenir a jour.

CINQ balayages complementaires, parce qu'aucun ne voit tout seul -- et chacun
a ete ajoute apres avoir MESURE que le precedent laissait un trou :
  1. par EN-TETE : chaque entree du corpus donne un sketch minimal, on regarde
     ce que la detection produit (couvre le chemin d'alias d'en-tete du #60) ;
  2. par SOURCE : les appels `_add("type", [Pin("NOM", ...), ...])` de
     `markers.py`, lus a l'AST (couvre les detections qui exigent un
     constructeur, invisibles au balayage 1) ;
  3. par MUTATION : les composants que seul un PROMPT fait naitre (`_to_led`,
     `_to_relay`, sous-typage d'une entree analogique). Les balayages 1 et 2
     laissaient 55 types sur 158 hors couverture ; les exercer a trouve la
     `thermistor` et le `microphone` etiquetes « pin 0 »/« pin1 » par un import
     Fritzing jamais relu -- donc dessines SANS AUCUN FIL -- et le `ds1307`
     dont la broche `5V` nomme le NET et non la patte, jamais alimente ;
  4. par LITTERAUX : tout `Component(type=..., pins=[Pin("NOM", ...)])` de
     `ui/wiring/`, lu a l'AST. Le seul qui ne demande pas de savoir DECLENCHER
     le composant : il atteint les regles d'inference (pull-up,
     `battery_external`, `stepper_motor`, `nema17`) et les replis profonds. Il
     a trouve `module_generic`, dont l'unique broche `SIG` ne correspondait a
     rien ;
  5. par CONSTRUCTEUR DE DRIVER : les neuf drivers moteur, dont le brochage
     vient d'une fonction (`_build_dc_driver_pins`,
     `build_stepdir_driver_pins`) qu'aucun sketch ne declenche de facon
     fiable. On les appelle directement, ce qui couvre aussi le mode DEUX
     moteurs que le mode un moteur ne visite pas.

Apres ces cinq-la il restait DEUX defauts, trouves en exercant a la main le
reliquat : `st7735` et `st7789` portaient `SDA` sur leur 7e broche quand
`markers` emet `MOSI` (c'est du SPI) -- l'ecran sortait alimente et pilote,
mais sa ligne de donnees n'etait jamais tiree.

Ce qui RESTE hors de portee, et pourquoi c'est acceptable : les types qui ne
naissent d'aucun detecteur et n'existent que si l'utilisateur echange un
composant vers eux. `component_replace` fabrique alors leurs broches EN LISANT
`pin_labels`, donc le desaccord y est impossible par construction --
`test_replacing_a_component_cannot_disagree_with_the_catalog` garde cette
propriete plutot que d'exercer les types un par un.

Run : python scripts/test_catalog_matches_markers.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.wiring.layout.component_catalog import CATALOG
from ui.wiring.markers import extract_netlist


def _catalog_labels(type_id):
    """Les libelles du catalogue, dans l'ordre des broches 1..pin_count."""
    entry = CATALOG[type_id]
    return [entry.pin_labels[i + 1] for i in range(entry.pin_count)]


def _emitted_by_headers():
    """{type: [noms de broches]} atteints depuis un `#include` du corpus."""
    corpus = json.loads(
        (ROOT / "assets" / "rag" / "corpus.json").read_text(encoding="utf-8"))
    out = {}
    for entry in corpus:
        headers = entry.get("headers") or []
        if not headers:
            continue
        code = f"#include <{headers[0]}>\nvoid setup(){{}}\nvoid loop(){{}}"
        netlist = extract_netlist(code, "uno", prompt="")
        for comp in netlist.to_dict()["components"]:
            out.setdefault(comp["type"], []).append(
                ([p["name"] for p in comp["pins"] if p["net"]], headers[0]))
    return out


def _emitted_in_source():
    """{type: {(noms de broches), ...}} lus dans les `_add(...)` litteraux.

    Seuls les appels dont la liste de broches est ecrite en dur sont lisibles
    ainsi ; les quatre types construits dynamiquement (drivers pas-a-pas) sont
    couverts par leurs propres tests de signature.
    """
    tree = ast.parse((ROOT / "ui" / "wiring" / "markers.py")
                     .read_text(encoding="utf-8"))
    out = {}
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "_add"
                and len(node.args) >= 2):
            continue
        type_node, pins_node = node.args[0], node.args[1]
        if not (isinstance(type_node, ast.Constant)
                and isinstance(type_node.value, str)):
            continue
        if not isinstance(pins_node, ast.List) or not pins_node.elts:
            continue
        names = []
        for el in pins_node.elts:
            if (isinstance(el, ast.Call)
                    and isinstance(el.func, ast.Name) and el.func.id == "Pin"
                    and el.args and isinstance(el.args[0], ast.Constant)):
                names.append(el.args[0].value)
            else:
                names = None
                break
        if names:
            out.setdefault(type_node.value, set()).add(tuple(names))
    return out


# Balayage 3 : les types atteints par MUTATION (`_to_led`, `_to_relay`...),
# invisibles aux deux autres -- ni `#include`, ni liste de broches ecrite en
# dur. C'est cet angle mort qui a laisse passer la thermistance, le capteur de
# son et le DS1307 lors du premier correctif (2026-09-07). Chaque cas est un
# sketch minimal + le prompt qui declenche la mutation ; les brochages ne sont
# pas devines, ils sont MESURES par `extract_netlist`.
_ANALOG = "void setup(){}\nvoid loop(){int v=analogRead(A0);}"
_DIGITAL_OUT = "void setup(){pinMode(7,OUTPUT);}\nvoid loop(){digitalWrite(7,HIGH);}"
_DIGITAL_IN = "void setup(){pinMode(4,INPUT_PULLUP);}\nvoid loop(){int v=digitalRead(4);}"

_MUTATION_CASES = {
    "led": (_DIGITAL_OUT, "allume une LED sur la broche 7"),
    "relay": (_DIGITAL_OUT, "pilote un relais sur la broche 7"),
    "buzzer": ("void setup(){}\nvoid loop(){tone(7, 440);}",
               "fais sonner un buzzer sur la broche 7"),
    "potentiometer": (_ANALOG, "lis un potentiometre sur A0"),
    "thermistor": (_ANALOG, "lis une thermistance sur A0"),
    "microphone": (_ANALOG, "capteur de son sur A0"),
    "ldr": (_ANALOG, "lis une photoresistance LDR sur A0"),
    "pir": (_DIGITAL_IN, "detecteur de mouvement PIR sur la broche 4"),
    "button": (_DIGITAL_IN, "un bouton poussoir sur la broche 4"),
    "dht11": ("#include <DHT.h>\nDHT d(2, DHT11);\nvoid setup(){d.begin();}\n"
              "void loop(){}", ""),
    "dht22": ("#include <DHT.h>\nDHT d(2, DHT22);\nvoid setup(){d.begin();}\n"
              "void loop(){}", ""),
    "ds1307": ("#include <RTClib.h>\nRTC_DS1307 r;\nvoid setup(){r.begin();}\n"
               "void loop(){}", ""),
    "ds3231": ("#include <RTClib.h>\nRTC_DS3231 r;\nvoid setup(){r.begin();}\n"
               "void loop(){}", ""),
    "a4988": ("#include <AccelStepper.h>\n"
              "AccelStepper s(AccelStepper::DRIVER, 2, 3);\n"
              "void setup(){}\nvoid loop(){}", ""),
    "uln2003": ("#include <Stepper.h>\nStepper s(2048, 8, 10, 9, 11);\n"
                "void setup(){}\nvoid loop(){}", ""),
    # Ecrans SPI : leur brochage est construit dynamiquement, donc invisible
    # aux balayages 2 et 4, et leur en-tete n'ouvre pas le balayage 1. Ce sont
    # les deux derniers defauts trouves (7e broche « SDA » au catalogue quand
    # `markers` emet « MOSI ») ; sans ces deux cas, rien ne les garderait.
    "st7735": ("#include <Adafruit_ST7735.h>\nAdafruit_ST7735 tft(10, 9, 8);\n"
               "void setup(){}\nvoid loop(){}", ""),
    "st7789": ("#include <Adafruit_ST7789.h>\nAdafruit_ST7789 tft(10, 9, 8);\n"
               "void setup(){}\nvoid loop(){}", ""),
}


def _emitted_by_mutation():
    """{type: [noms de broches]} atteints par prompt plutot que par en-tete."""
    out = {}
    for type_id, (code, prompt) in _MUTATION_CASES.items():
        netlist = extract_netlist(code, "uno", prompt=prompt)
        for comp in netlist.to_dict()["components"]:
            if comp["type"] == type_id:
                out[type_id] = [p["name"] for p in comp["pins"] if p["net"]]
                break
    return out


def _emitted_by_component_literals():
    """Balayage 4 : tout `Component(type=..., pins=[Pin("NOM", ...)])` du paquet.

    Ni prompt ni en-tete a trouver : on lit la SOURCE, donc la couverture ne
    depend pas de savoir declencher le composant. C'est le seul balayage qui
    atteint les composants fabriques par les regles d'inference
    (`resistor` de pull-up, `battery_external`, `stepper_motor`, `nema17`) et
    les replis profonds -- et c'est lui qui a trouve `module_generic`, dont
    l'unique broche `SIG` ne correspondait a aucun libelle catalogue.

    Rend [(type, [noms], "fichier:ligne")].
    """
    out = []
    for chemin in sorted((ROOT / "ui" / "wiring").rglob("*.py")):
        source = chemin.read_text(encoding="utf-8")
        if "Pin(" not in source:
            continue
        for node in ast.walk(ast.parse(source)):
            if not (isinstance(node, ast.Call)
                    and getattr(node.func, "id", None) == "Component"):
                continue
            kw = {k.arg: k.value for k in node.keywords}
            type_node, pins_node = kw.get("type"), kw.get("pins")
            if not (isinstance(type_node, ast.Constant)
                    and isinstance(pins_node, ast.List)):
                continue
            noms = [el.args[0].value for el in pins_node.elts
                    if isinstance(el, ast.Call)
                    and getattr(el.func, "id", None) == "Pin"
                    and el.args and isinstance(el.args[0], ast.Constant)]
            if noms:
                out.append((type_node.value, noms,
                            f"{chemin.name}:{node.lineno}"))
    return out


def _emitted_by_driver_builders():
    """Balayage 5 : les brochages de driver, construits par une FONCTION.

    Ni `_add` litteral ni `Component(...)` : ces neuf drivers recoivent leurs
    broches d'un constructeur dedie, appele depuis la modale d'ambiguite ou le
    swap de driver. Aucun sketch ne les declenche de facon fiable -- on appelle
    donc les constructeurs directement, ce qui couvre AUSSI le mode deux
    moteurs, que le mode un moteur ne visite pas.
    """
    from ui.wiring.inference import _build_dc_driver_pins
    from ui.wiring.markers import build_stepdir_driver_pins

    moteur_a = {"control_pin": "D9", "n_out1": "NET_A1", "n_out2": "NET_A2",
                "aux_dir_pins": ["D7", "D8"]}
    moteur_b = {"control_pin": "D10", "n_out1": "NET_B1", "n_out2": "NET_B2",
                "aux_dir_pins": ["D5", "D6"]}
    out = []
    for driver in ("l298n", "l293d", "l293d_module", "tb6612fng", "drv8833"):
        out.append((driver, [p.name for p in _build_dc_driver_pins(driver, moteur_a)],
                    "1 moteur"))
        out.append((driver,
                    [p.name for p in _build_dc_driver_pins(driver, moteur_a, moteur_b)],
                    "2 moteurs"))
    for driver in ("a4988", "drv8825", "tmc2209", "stspin220"):
        out.append((driver,
                    [p.name for p in build_stepdir_driver_pins(driver, "D2", "D3")],
                    "step/dir"))
    return out


def _report(faults):
    lignes = []
    for type_id, emitted, origine in faults:
        catalog = _catalog_labels(type_id)
        orphelines = [n for n in emitted if n not in catalog]
        lignes.append(
            f"\n  {type_id} ({origine})"
            f"\n    emis      : {list(emitted)}"
            f"\n    catalogue : {catalog}"
            f"\n    jamais cablees (aucun libelle catalogue de ce nom) : "
            f"{orphelines}")
    return "".join(lignes)


def test_every_emitted_pin_has_a_catalog_label_via_headers():
    """Balayage 1 : tout type atteint par un `#include` du corpus.

    Un type sans entree catalogue n'est PAS un defaut : il est dessine par
    `resolve_generic`, qui fabrique ses libelles depuis le composant lui-meme
    -- il ne peut pas etre en desaccord avec la detection.
    """
    faults = []
    for type_id, cas in _emitted_by_headers().items():
        if type_id not in CATALOG:
            continue
        catalog = _catalog_labels(type_id)
        for emitted, header in cas:
            if any(n not in catalog for n in emitted):
                faults.append((type_id, emitted, f"<{header}>"))
                break
    assert not faults, (
        "Des broches emises n'ont aucun libelle catalogue du meme nom : elles "
        "ne recevront JAMAIS de fil." + _report(faults))


def test_every_emitted_pin_has_a_catalog_label_in_source():
    """Balayage 2 : les brochages ecrits en dur dans `markers.py`.

    Rattrape ce que le balayage par en-tete ne peut pas voir -- une detection
    qui exige un constructeur (`OneWire ow(2)` pour le DS18B20) ne se declenche
    pas sur un sketch reduit a son `#include`.
    """
    faults = []
    for type_id, variantes in _emitted_in_source().items():
        if type_id not in CATALOG:
            continue
        catalog = _catalog_labels(type_id)
        for emitted in variantes:
            if any(n not in catalog for n in emitted):
                faults.append((type_id, emitted, "markers.py"))
                break
    assert not faults, (
        "Des broches emises n'ont aucun libelle catalogue du meme nom : elles "
        "ne recevront JAMAIS de fil." + _report(faults))


def test_the_two_reported_components_are_fully_wired():
    """Le defaut d'origine, verifie de bout en bout plutot que sur les noms.

    Les deux balayages ci-dessus comparent des CHAINES ; celui-ci fait tourner
    le placement et le routage et compte les fils reellement produits. Sans
    lui, un futur changement du routeur pourrait casser le cablage tout en
    laissant les libelles d'accord.
    """
    from ui.wiring.layout.layout import place_scene
    from ui.wiring.layout.routing import route_wires

    board = ROOT / "assets" / "wiring" / "boards" / "arduino" / "uno_r3.svg"
    cas = {
        "bme280": "#include <Wire.h>\n#include <Adafruit_BME280.h>\n"
                  "Adafruit_BME280 b;\nvoid setup(){b.begin();}\nvoid loop(){}",
        "ds18b20": "#include <OneWire.h>\n#include <DallasTemperature.h>\n"
                   "OneWire ow(2);\nDallasTemperature s(&ow);\n"
                   "void setup(){s.begin();}\nvoid loop(){}",
    }
    for type_id, code in cas.items():
        comps = extract_netlist(code, "uno", prompt="").to_dict()["components"]
        comp = next((c for c in comps if c["type"] == type_id), None)
        assert comp is not None, f"{type_id} non detecte"
        scene = place_scene(comps, board)
        routes = {w.net for w in route_wires(scene, comps)}
        attendus = {p["net"] for p in comp["pins"] if p["net"]}
        manquants = sorted(attendus - routes)
        assert not manquants, (
            f"{type_id} : nets sans aucun fil {manquants} "
            f"(attendus {sorted(attendus)}, routes {sorted(routes)})")


def test_every_emitted_pin_has_a_catalog_label_by_mutation():
    """Balayage 3 : les types que seul un PROMPT fait apparaitre.

    Ni `#include`, ni liste ecrite en dur -- ces composants naissent d'une
    mutation (`_to_led`, `_to_relay`...). L'angle mort etait reel : il cachait
    une thermistance et un capteur de son etiquetes « pin 0 »/« pin1 » par
    l'import Fritzing, donc dessines sans AUCUN fil, et un DS1307 dont
    l'alimentation n'etait jamais tiree parce que le catalogue l'appelait
    « 5V » quand `markers` emet « VCC ».
    """
    faults = []
    for type_id, emitted in _emitted_by_mutation().items():
        if type_id not in CATALOG:
            continue
        catalog = _catalog_labels(type_id)
        if any(n not in catalog for n in emitted):
            faults.append((type_id, emitted, "mutation"))
    assert not faults, (
        "Des broches emises n'ont aucun libelle catalogue du meme nom : elles "
        "ne recevront JAMAIS de fil." + _report(faults))


def test_the_mutation_sweep_actually_reaches_its_types():
    """Un cas qui ne declenche plus rien rendrait le balayage 3 muet.

    Sans ce garde-fou, il suffirait qu'un detecteur change pour que la
    couverture retombe en silence -- et une garde qui ne verifie plus rien est
    pire que pas de garde, elle rassure.
    """
    atteints = set(_emitted_by_mutation())
    manquants = sorted(set(_MUTATION_CASES) - atteints)
    assert not manquants, (
        f"Ces cas ne produisent plus leur composant : {manquants}. Corriger "
        f"le sketch ou le prompt, ne PAS retirer le cas.")


def test_every_emitted_pin_has_a_catalog_label_in_component_literals():
    """Balayage 4 : les `Component(...)` de tout `ui/wiring/`.

    Le seul qui ne demande pas de savoir DECLENCHER le composant -- il lit la
    source. Il couvre les composants fabriques par les regles d'inference
    (resistance de pull-up, pile externe, moteurs) et les replis profonds.
    """
    faults = []
    for type_id, emitted, origine in _emitted_by_component_literals():
        if type_id not in CATALOG:
            continue
        catalog = _catalog_labels(type_id)
        if any(n not in catalog for n in emitted):
            faults.append((type_id, emitted, origine))
    assert not faults, (
        "Des broches emises n'ont aucun libelle catalogue du meme nom : elles "
        "ne recevront JAMAIS de fil." + _report(faults))


def test_every_emitted_pin_has_a_catalog_label_in_driver_builders():
    """Balayage 5 : les neuf drivers, dont le brochage vient d'une fonction.

    Les quatre autres balayages ne les voient pas : leurs broches ne sont ni
    ecrites en dur ni produites par un `#include`. On appelle les
    constructeurs, ce qui couvre en prime le mode DEUX moteurs.
    """
    faults = []
    for type_id, emitted, contexte in _emitted_by_driver_builders():
        if type_id not in CATALOG:
            continue
        catalog = _catalog_labels(type_id)
        if any(n not in catalog for n in emitted):
            faults.append((type_id, emitted, contexte))
    assert not faults, (
        "Des broches emises n'ont aucun libelle catalogue du meme nom : elles "
        "ne recevront JAMAIS de fil." + _report(faults))


def test_replacing_a_component_cannot_disagree_with_the_catalog():
    """Le remplacement (engrenage) est sur PAR CONSTRUCTION -- et doit le rester.

    33 types du catalogue ne naissent d'aucun detecteur : ils n'existent que
    si l'utilisateur echange un composant vers eux. `component_replace`
    fabrique alors ses broches EN LISANT `pin_labels`, donc les deux ne
    peuvent pas diverger -- c'est ce qui autorise a ne pas les exercer un par
    un. Le jour ou ce chemin ecrirait des noms de broches en dur, cet argument
    tomberait et il faudrait les couvrir autrement : ce test rougit alors.
    """
    source = (ROOT / "ui" / "wiring" / "component_replace.py").read_text(
        encoding="utf-8")
    arbre = ast.parse(source)
    lit_le_catalogue = any(
        isinstance(n, ast.Attribute) and n.attr == "pin_labels"
        for n in ast.walk(arbre))
    assert lit_le_catalogue, (
        "component_replace ne lit plus `pin_labels` : les types atteignables "
        "seulement par remplacement ne sont plus couverts par construction")

    noms_en_dur = [
        n.args[0].value for n in ast.walk(arbre)
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "Pin"
        and n.args and isinstance(n.args[0], ast.Constant)
        and isinstance(n.args[0].value, str)]
    assert not noms_en_dur, (
        f"component_replace ecrit des noms de broches en dur {noms_en_dur} : "
        f"le remplacement peut desormais contredire le catalogue")


def test_a_display_map_covers_every_pin():
    """`pin_display_labels` remplace TOUT ou RIEN -- jamais a moitie.

    `display_pin_labels` retombe sur `pin_labels` seulement quand la table est
    VIDE ; une table partielle laisserait des broches sans libelle a dessiner.
    """
    for type_id, entry in sorted(CATALOG.items()):
        if not entry.pin_display_labels:
            continue
        manquants = [i + 1 for i in range(entry.pin_count)
                     if not entry.pin_display_labels.get(i + 1)]
        assert not manquants, (
            f"{type_id} : pin_display_labels ne couvre pas les broches "
            f"{manquants} sur {entry.pin_count}")


def test_a_component_may_have_pins_nobody_wires():
    """Une broche dessinee sans fil est NORMALE, et doit le rester.

    La carte que l'utilisateur tient a six pattes ; n'en dessiner que quatre
    parce que le code n'en pilote que quatre le tromperait (retour
    utilisateur, 2026-09-07). Le BME280 en a donc six, dont `CSB` et `SDO`
    libres -- exactement comme le MPU6050 depuis toujours.

    Ce test existe pour empecher la « correction » inverse : quelqu'un qui
    verrait deux broches sans fil et raboterait l'entree catalogue pour
    « faire propre » recasserait la fidelite au materiel.
    """
    for type_id, attendues in (("bme280", {"CSB", "SDO"}),
                               ("mpu6050", {"XDA", "XCL", "AD0", "INT"})):
        labels = set(_catalog_labels(type_id))
        assert attendues <= labels, (
            f"{type_id} : broches physiques disparues du catalogue "
            f"{sorted(attendues - labels)}")


TESTS = [
    test_every_emitted_pin_has_a_catalog_label_via_headers,
    test_every_emitted_pin_has_a_catalog_label_in_source,
    test_every_emitted_pin_has_a_catalog_label_by_mutation,
    test_the_mutation_sweep_actually_reaches_its_types,
    test_every_emitted_pin_has_a_catalog_label_in_component_literals,
    test_every_emitted_pin_has_a_catalog_label_in_driver_builders,
    test_replacing_a_component_cannot_disagree_with_the_catalog,
    test_the_two_reported_components_are_fully_wired,
    test_a_display_map_covers_every_pin,
    test_a_component_may_have_pins_nobody_wires,
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
