"""Détection des bundles d'affichage : TM1637, HT16K33, 74HC595."""
from __future__ import annotations
import os, sys
from pathlib import Path
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ui.wiring.markers import extract_netlist  # noqa: E402


def _of(nl, t):
    return [c for c in nl.components if c.type == t]


def _nets(c):
    return {p.name: p.net for p in c.pins}


def test_tm1637_literals():
    code = ("#include <TM1637Display.h>\n"
            "TM1637Display display(3, 4);\n"
            "void setup(){ display.setBrightness(5); }\n"
            "void loop(){ display.showNumberDec(42); }\n")
    nl = extract_netlist(code, board_id="uno")
    cs = _of(nl, "tm1637")
    assert len(cs) == 1, f"attendu 1 tm1637, {len(cs)}"
    n = _nets(cs[0])
    assert n.get("CLK") == "D3" and n.get("DIO") == "D4", n
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    print("  OK — tm1637 CLK/DIO")


def test_tm1637_constants():
    code = ("#include <TM1637Display.h>\n#define CLK 9\n#define DIO 8\n"
            "TM1637Display d(CLK, DIO);\nvoid setup(){} void loop(){}\n")
    nl = extract_netlist(code, board_id="uno")
    n = _nets(_of(nl, "tm1637")[0])
    assert n.get("CLK") == "D9" and n.get("DIO") == "D8", n
    print("  OK — tm1637 #define")


def test_ht16k33_i2c():
    code = ("#include <Adafruit_GFX.h>\n#include <Adafruit_LEDBackpack.h>\n"
            "Adafruit_8x8matrix matrix = Adafruit_8x8matrix();\n"
            "void setup(){ matrix.begin(0x70); }\n"
            "void loop(){ matrix.clear(); matrix.writeDisplay(); }\n")
    nl = extract_netlist(code, board_id="uno")
    cs = _of(nl, "ht16k33")
    assert len(cs) == 1, f"attendu 1 ht16k33, {len(cs)}"
    n = _nets(cs[0])
    assert n.get("SDA") == "A4" and n.get("SCL") == "A5", n
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    assert not _of(nl, "module_generic"), "module I2C parasite"
    print("  OK — ht16k33 I2C SDA/SCL")


def test_sr74hc595_lib():
    code = ("#include <ShiftRegister74HC595.h>\n"
            "ShiftRegister74HC595<1> sr(7, 8, 9);\n"
            "void setup(){} void loop(){ sr.set(0, HIGH); }\n")
    nl = extract_netlist(code, board_id="uno")
    cs = _of(nl, "sr74hc595")
    assert len(cs) == 1, f"attendu 1 sr74hc595, {len(cs)}"
    n = _nets(cs[0])
    assert n.get("DATA") == "D7", n
    assert n.get("CLK") == "D8", n
    assert n.get("LATCH") == "D9", n
    assert n.get("VCC") == "5V" and n.get("GND") == "GND", n
    print("  OK — sr74hc595 DATA/CLK/LATCH")


def test_sr74hc595_raw_shiftout_is_placeholder_or_absent():
    """shiftOut brut (sans lib) n'est PAS couvert : pas de sr74hc595 créé."""
    code = ("void setup(){ pinMode(7,OUTPUT); }\n"
            "void loop(){ digitalWrite(9,LOW); shiftOut(7,8,MSBFIRST,255); digitalWrite(9,HIGH); }\n")
    nl = extract_netlist(code, board_id="uno")
    assert not _of(nl, "sr74hc595"), "shiftOut brut ne doit pas créer de sr74hc595"
    print("  OK — shiftOut brut non couvert")


def test_sr74hc595_unwired_outputs_attribute():
    """Le 74HC595 marque ses sorties QA..QH comme broches non câblées."""
    code = ("#include <ShiftRegister74HC595.h>\n"
            "ShiftRegister74HC595<1> sr(7, 8, 9);\n"
            "void setup(){} void loop(){}\n")
    nl = extract_netlist(code, board_id="uno")
    sr = _of(nl, "sr74hc595")[0]
    assert sr.attributes.get("unwired_pins") == \
        ["QA", "QB", "QC", "QD", "QE", "QF", "QG", "QH"], sr.attributes
    print("  OK — sr74hc595 unwired_pins QA..QH")


def test_unwired_pins_drives_info_icon():
    """Un composant avec unwired_pins entre dans _compute_info_refs (icône attention)."""
    from ui.wiring.wiring_diagram_dialog import WiringDiagramDialog
    code = ("#include <ShiftRegister74HC595.h>\n"
            "ShiftRegister74HC595<1> sr(7, 8, 9);\n"
            "void setup(){} void loop(){}\n")
    nl = extract_netlist(code, board_id="uno")
    dlg = WiringDiagramDialog.__new__(WiringDiagramDialog)  # pas de QDialog.__init__
    dlg._netlist = nl
    refs = dlg._compute_info_refs()
    sr = _of(nl, "sr74hc595")[0]
    assert sr.ref in refs, f"{sr.ref} attendu dans info_refs {refs}"
    print("  OK — 74HC595 dans info_refs")


def test_sr74hc595_unwired_warning_in_text():
    """Les broches non câblées génèrent un warning rendu dans la description texte."""
    from ui.wiring.instructions import _render_warning_message
    code = ("#include <ShiftRegister74HC595.h>\n"
            "ShiftRegister74HC595<1> sr(7, 8, 9);\n"
            "void setup(){} void loop(){}\n")
    nl = extract_netlist(code, board_id="uno")
    ws = [w for w in nl.warnings if w.code == "unwired_component_pins"]
    assert ws, f"warning attendu, codes={[w.code for w in nl.warnings]}"
    assert "QA" in ws[0].params.get("pins", ""), ws[0].params
    # localized render (not the raw message): the template must resolve {pins}
    txt = _render_warning_message(ws[0], "fr")
    assert "QA" in txt and "QH" in txt, txt
    print("  OK — warning unwired_component_pins rendu en texte")


def test_i2c_instructions_name_the_hole_the_wire_reaches():
    """QA 2026-08-08 : le schéma reliait SDA/SCL aux connecteurs DÉDIÉS de la
    carte, pendant que le texte disait A4/A5 — deux trous distincts et
    éloignés sur un Uno (SDA en (244,70), A4 en (46,290)), pourtant le même
    net.

    C'est le routeur qui choisit : `_I2C_PHYSICAL_PINS_FOR_BUS` donne à chaque
    consommateur un trou physique distinct et prend le connecteur dédié en
    premier. Nommer les DEUX est vrai quel que soit son choix.
    """
    from ui.wiring.instructions import render_instructions
    code = ("#include <Wire.h>\n#include <Adafruit_SSD1306.h>\n"
            "Adafruit_SSD1306 display(128, 64, &Wire, -1);\n"
            "void setup(){ display.begin(SSD1306_SWITCHCAPVCC, 0x3C); }\n"
            "void loop(){}\n")
    nl = extract_netlist(code, board_id="uno")
    for lang, word in (("fr", "ou"), ("en", "or"), ("es", "o"), ("it", "o")):
        md = render_instructions(nl, mode="simple", lang=lang)
        assert f"**SDA** ({word} **A4**)" in md, (lang, md[:400])
        assert f"**SCL** ({word} **A5**)" in md, (lang, md[:400])


def test_a_plain_analog_pin_on_a4_is_not_renamed_sda():
    """Garde-fou de l'alias : il est indexé sur le nom de broche DU COMPOSANT,
    pas sur le net. Une entrée analogique câblée sur A4 doit rester « A4 » —
    l'appeler SDA serait faux."""
    from ui.wiring.instructions import render_instructions
    nl = extract_netlist("void setup(){}\nvoid loop(){ int v = analogRead(A4); }\n",
                         board_id="uno", prompt="lis un potentiometre sur A4")
    md = render_instructions(nl, mode="simple", lang="fr")
    assert "**A4**" in md, md[:300]
    assert "SDA" not in md, md[:300]


def test_rag_retrieval_three_bundles():
    """Le retrieval RAG fait ressortir chaque nouveau bundle pour son prompt."""
    from ui.rag import retrieve_libs
    probes = {
        "afficheur 7 segments": "tm1637",
        "7 segment display": "tm1637",
        "matrice LED I2C backpack": "ht16k33",
        "registre a decalage 74HC595": "sr74hc595",
        "shift register 74hc595": "sr74hc595",
    }
    for q, expected in probes.items():
        r = retrieve_libs(q, k=5)
        ids = [(x.get("id") if isinstance(x, dict) else x) for x in r]
        assert expected in ids, f"{q!r} -> {ids} (attendu {expected})"
    print("  OK — retrieval tm1637 / ht16k33 / sr74hc595")


TESTS = [test_tm1637_literals, test_tm1637_constants, test_ht16k33_i2c,
         test_sr74hc595_lib, test_sr74hc595_raw_shiftout_is_placeholder_or_absent,
         test_sr74hc595_unwired_outputs_attribute, test_unwired_pins_drives_info_icon,
         test_sr74hc595_unwired_warning_in_text,
         test_rag_retrieval_three_bundles,
         test_i2c_instructions_name_the_hole_the_wire_reaches,
         test_a_plain_analog_pin_on_a4_is_not_renamed_sda]


def main():
    passed = failed = 0
    for t in TESTS:
        try:
            t(); print(f"PASS  {t.__name__}"); passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}"); failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.stdout.flush(); os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
