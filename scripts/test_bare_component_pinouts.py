"""Brochage catalogue des huit composants dessines en rectangle generique.

Historique. Ces huit types ont recu une entree catalogue (`pin_count` +
`pin_labels`) le 2026-08-08, en meme temps qu'un glyphe dedie. Les GLYPHES ont
ete retires le 2026-08-10 (decision utilisateur : pas de dessin particulier sur
ces composants) ; les ENTREES CATALOGUE restent, parce qu'elles ne dessinent
rien -- elles corrigent le brochage. Sans elles, l'engrenage reconstruit une
approximation generique : un relais y repassait de 3 broches (VCC/GND/IN) a 2.

Ce fichier remplace `test_wiring_vignettes.py` et n'en garde que les invariants
qui survivent au retrait des glyphes.

Run : python scripts/test_bare_component_pinouts.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.component_registry import by_id
from ui.wiring.layout.component_catalog import CATALOG
from ui.wiring.markers import extract_netlist

_GENERIC = ROOT / "assets" / "wiring" / "components" / "single-row"

# Sketch minimal qui declenche chaque detection, + le prompt eventuel.
# Les brochages attendus ont ete MESURES via extract_netlist, pas devines.
_CASES = {
    "relay": (
        "void setup(){pinMode(7, OUTPUT);}\nvoid loop(){digitalWrite(7, HIGH);}",
        "pilote un relais sur la broche 7"),
    "pir": (
        "void setup(){pinMode(4, INPUT);}\nvoid loop(){int v = digitalRead(4);}",
        "detecteur de mouvement PIR sur la broche 4"),
    "ldr": (
        "void setup(){}\nvoid loop(){int v = analogRead(A0);}",
        "lis une photoresistance LDR sur A0"),
    "ir_receiver": (
        "#include <IRremote.h>\nIRrecv irrecv(11);\nvoid setup(){}\nvoid loop(){}", ""),
    "neopixel": (
        "#include <Adafruit_NeoPixel.h>\nAdafruit_NeoPixel strip(16, 6, NEO_GRB);\n"
        "void setup(){}\nvoid loop(){}", ""),
    "encoder": (
        "#include <Encoder.h>\nEncoder enc(2, 3);\nvoid setup(){}\nvoid loop(){}", ""),
    "mfrc522": (
        "#include <MFRC522.h>\nMFRC522 rfid(10, 9);\nvoid setup(){}\nvoid loop(){}", ""),
    "ili9341": (
        "#include <Adafruit_ILI9341.h>\nAdafruit_ILI9341 tft(10, 9, 8);\n"
        "void setup(){}\nvoid loop(){}", ""),
}

TYPES = tuple(_CASES)


def _emitted_pins(type_id):
    """Ce que markers emet reellement pour ce type : [(nom, net), ...]."""
    code, prompt = _CASES[type_id]
    nl = extract_netlist(code, "uno", prompt=prompt)
    comps = [c for c in nl.components if c.type == type_id]
    assert len(comps) == 1, f"{type_id}: {[c.type for c in nl.components]}"
    return [(p.name, p.net) for p in comps[0].pins]


def test_each_type_has_a_catalog_entry():
    """C'est l'entree catalogue, pas le dessin, qui donne le vrai brochage a
    l'engrenage. La retirer ferait retomber le relais a 2 broches."""
    for t in TYPES:
        entry = CATALOG.get(t)
        assert entry is not None, f"{t} n a pas d entree catalogue"
        assert entry.asset_path.exists(), (t, entry.asset_path)


def test_the_drawing_is_the_plain_generic_one():
    """Garde-fou de la decision du 2026-08-10 : pas de glyphe particulier sur
    ces composants. Un asset dedie qui reapparaitrait ici serait un retour en
    arriere silencieux."""
    for t in TYPES:
        entry = CATALOG[t]
        expected = _GENERIC / f"{entry.pin_count}pins.svg"
        assert entry.asset_path == expected, (
            f"{t}: asset {entry.asset_path.name} au lieu du generique "
            f"{expected.name}")


def test_catalog_labels_are_the_ones_markers_emits():
    """Un brochage INVENTE produirait un schema faux presente comme certain.
    Les libelles viennent du detecteur, jamais d'une datasheet recopiee."""
    for t in TYPES:
        emitted = [name for name, _net in _emitted_pins(t)]
        entry = CATALOG[t]
        catalog = [entry.pin_labels[i + 1] for i in range(entry.pin_count)]
        assert catalog == emitted, f"{t}: catalogue {catalog} != emis {emitted}"


def test_the_registry_knows_them():
    """`wiring="known"` veut dire « le catalogue connait ce composant », pas
    « il a un dessin dedie » : `led`, `button` et `servo` sont known avec un
    asset generique depuis toujours. L'onglet Composants affiche alors le
    NOMBRE DE BROCHES, qui reste exact apres le retrait des glyphes."""
    for t in TYPES:
        comp = by_id(t)
        assert comp is not None, f"{t} absent du registre"
        assert comp.wiring == "known", f"{t}: wiring={comp.wiring}"


TESTS = [
    test_each_type_has_a_catalog_entry,
    test_the_drawing_is_the_plain_generic_one,
    test_catalog_labels_are_the_ones_markers_emits,
    test_the_registry_knows_them,
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
