"""Les bus I2C et SPI suivent LA carte (Mega : D20/D21, D50-D52).

Vu le 2026-11-07 en rendant le schema d'un LCD I2C + BME280 sur Mega : les
detecteurs ecrivent SDA=A4 / SCL=A5 en dur (brochage Uno), donc le SCL du LCD
partait sur l'entree analogique A5 de la Mega et le BME280 n'avait aucun fil
I2C. Le correctif de l'audit (alias du routeur) ne pouvait pas suffire : c'est
le NET qui disait A5. Puis, une fois le net juste, le fil SCL vers l'en-tete
ne se tracait plus : la sortie de SDA partait par le haut en recouvrant la
broche SCL.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.wiring.markers import extract_netlist  # noqa: E402

LCD_BME = """#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#include <Adafruit_BME280.h>
LiquidCrystal_I2C lcd(0x27, 16, 2);
Adafruit_BME280 bme;
void setup(){ lcd.init(); bme.begin(); }
void loop(){ lcd.print(bme.readTemperature()); delay(1000); }
"""


def _i2c_nets(board):
    nl = extract_netlist(LCD_BME, board)
    return sorted({p.net for c in nl.components for p in c.pins
                   if p.name in ("SDA", "SCL")}), nl


def test_mega_wires_i2c_on_d20_d21():
    nets, _ = _i2c_nets("arduino_mega_2560")
    assert nets == ["D20", "D21"], nets


def test_leonardo_wires_i2c_on_d2_d3():
    nets, _ = _i2c_nets("arduino_leonardo")
    assert nets == ["D2", "D3"], nets


def test_uno_and_nano_keep_a4_a5():
    for board in ("arduino_uno_r3", "arduino_nano", "arduino_uno_r4"):
        nets, _ = _i2c_nets(board)
        assert nets == ["A4", "A5"], (board, nets)


def test_only_pins_named_sda_scl_move():
    """Le remappage ne touche que les broches I2C : une broche sur A4 qui ne
    s'appelle pas SDA reste sur A4."""
    from ui.wiring.markers import _remap_i2c_to_board
    from ui.wiring.netlist import Netlist, Component, Pin
    nl = Netlist(board_id="arduino_mega_2560")
    nl.add_component(Component(ref="R1", type="potentiometer",
                               pins=[Pin("W", "A4"), Pin("VCC", "5V")]))
    nl.add_component(Component(ref="U1", type="lcd_i2c",
                               pins=[Pin("SDA", "A4"), Pin("SCL", "A5")]))
    _remap_i2c_to_board(nl, "arduino_mega_2560")
    assert nl.by_ref("R1").pins[0].net == "A4"
    assert [p.net for p in nl.by_ref("U1").pins] == ["D20", "D21"]


def test_an_analog_read_on_a4_next_to_i2c_is_kept_on_mega():
    """Les modules I2C reservaient A4/A5 AVANT que la carte soit consultee :
    sur Mega, un `analogRead(A4)` voisin disparaissait du schema."""
    code = LCD_BME.replace("void loop(){", "void loop(){ int v = analogRead(A4);")
    nl = extract_netlist(code, "arduino_mega_2560", prompt="potentiometre sur A4")
    sur_a4 = [(c.type, p.name) for c in nl.components for p in c.pins if p.net == "A4"]
    assert sur_a4 and all(n not in ("SDA", "SCL") for _, n in sur_a4), sur_a4


def test_the_mega_diagram_draws_every_i2c_wire():
    from ui.wiring.layout.pipeline import analyze_netlist, render_netlist
    nl = analyze_netlist(LCD_BME, "arduino_mega_2560")
    svg, md = render_netlist(nl, "arduino_mega_2560")
    assert svg, "schema vide"
    assert "incomplet" not in md, md[:400]


RFID = """#include <SPI.h>
#include <MFRC522.h>
#include <Servo.h>
MFRC522 rfid(10, 9);
Servo s;
void setup(){ SPI.begin(); rfid.PCD_Init(); s.attach(6); }
void loop(){ if (rfid.PICC_IsNewCardPresent()) { s.write(90); } }
"""


def _broches(code, board):
    nl = extract_netlist(code, board)
    return {(c.type, p.name): p.net for c in nl.components for p in c.pins}


def test_spi_follows_the_board():
    """Le MFRC522 avait MISO/MOSI/SCK sur D12/D11/D13 en dur, y compris sur
    une Mega, ou le SPI est sur D50/D51/D52."""
    mega = _broches(RFID, "arduino_mega_2560")
    assert (mega[("mfrc522", "MISO")], mega[("mfrc522", "MOSI")],
            mega[("mfrc522", "SCK")]) == ("D50", "D51", "D52"), mega
    assert mega[("mfrc522", "SDA")] == "D10", "SS reste ou le code l'a mis"
    uno = _broches(RFID, "arduino_uno_r3")
    assert (uno[("mfrc522", "MISO")], uno[("mfrc522", "MOSI")],
            uno[("mfrc522", "SCK")]) == ("D12", "D11", "D13"), uno


def test_mfrc522_irq_is_left_free():
    """IRQ est une SORTIE du module : elle etait cablee a la masse."""
    for board in ("arduino_uno_r3", "arduino_mega_2560"):
        assert _broches(RFID, board)[("mfrc522", "IRQ")] == "", board


def test_the_mega_rfid_diagram_draws_every_wire():
    """D50 sortait par le bas en recouvrant D51 (double rangee du bas) : son
    fil ne se tracait pas."""
    from ui.wiring.layout.pipeline import analyze_netlist, render_netlist
    nl = analyze_netlist(RFID, "arduino_mega_2560")
    svg, md = render_netlist(nl, "arduino_mega_2560")
    assert svg and "incomplet" not in md, md[:400]


def test_an_exit_never_runs_over_another_pin():
    from ui.wiring.routing.occupancy import board_pin_exit_side
    bbox = (0, 0, 100, 100)
    # broche pres du bas, une autre juste dessous : le bas est ecarte
    assert board_pin_exit_side(50, 80, bbox, [(50, 90)]) != "bottom"
    assert board_pin_exit_side(50, 80, bbox, []) == "bottom"
    # tout bloque : le plus proche, comme avant
    autour = [(50, 90), (50, 10), (10, 80), (90, 80)]
    assert board_pin_exit_side(50, 80, bbox, autour) == "bottom"



TESTS = [test_mega_wires_i2c_on_d20_d21, test_leonardo_wires_i2c_on_d2_d3,
         test_uno_and_nano_keep_a4_a5, test_only_pins_named_sda_scl_move,
         test_an_analog_read_on_a4_next_to_i2c_is_kept_on_mega,
         test_the_mega_diagram_draws_every_i2c_wire,
         test_spi_follows_the_board, test_mfrc522_irq_is_left_free,
         test_the_mega_rfid_diagram_draws_every_wire,
         test_an_exit_never_runs_over_another_pin]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t(); print("PASS", t.__name__)
        except Exception as e:  # noqa: BLE001
            failed += 1; print("FAIL", t.__name__, repr(e)[:300])
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    raise SystemExit(1 if failed else 0)
