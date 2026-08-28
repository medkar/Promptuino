"""Catalog: mapping netlist types to SVG assets + labels.

The placer needs to know:
- Which SVG to load for a type ('led' -> single-row 2pins)
- Which labels to apply to the pins ('led' -> {1: 'A', 2: 'K'})
- Which name to display at the center ('led' -> 'LED')

If a type is not in the catalog, the placer can fall back to a
procedural fallback (generates the SVG on the fly) — that's for Phase 6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# Directory of component assets
_ASSETS_ROOT = Path(__file__).resolve().parent.parent.parent.parent / "assets" / "wiring" / "components"


@dataclass(frozen=True)
class CatalogEntry:
    """Description of a component type in the catalog."""
    asset_path: Path             # absolute path of the SVG
    is_dip: bool                 # True if DIP (2 sides), False if single-row
    pin_count: int
    name: str                    # name to display at the center
    pin_labels: dict[int, str]   # {pin_index: label}, order 1..pin_count
    is_horizontal: bool = False  # True if the component is laid across (2 pins
                                  # on the same row, different cols) — used
                                  # for paired resistors (LED+R, button+R...)
                                  # that span the central groove of the BB.
    render_scale: float = 1.0    # Scale factor applied to the render. <1 shrinks
                                  # the component (original SVG size too large
                                  # for educational use, e.g. NEMA17). The scale
                                  # is applied both to the render transform
                                  # AND to the pin positions returned by the loader.
    pin_roles: dict[int, str] = field(default_factory=dict)  # {index: role}
    # roles: signal, vcc, gnd, sda, scl, sck, miso, mosi, cs, rx, tx,
    # trig, echo, data, out_a, out_b. Empty -> derived via _default_roles.
    pin_display_labels: dict[int, str] = field(default_factory=dict)
    # Optional VISUAL-ONLY labels drawn on the schematic (e.g. LED: anode/cathode
    # instead of the internal A/K). Empty -> display falls back to pin_labels.
    # Kept separate so the INTERNAL pin names (used by component_replace ->
    # Pin.name and by the instruction/routing matching) stay stable.

    @property
    def display_pin_labels(self) -> dict[int, str]:
        """Labels shown on the diagram (visual only); falls back to pin_labels."""
        return self.pin_display_labels or self.pin_labels


def _single_row(n: int) -> Path:
    return _ASSETS_ROOT / "single-row" / f"{n}pins.svg"


def _horizontal(n: int) -> Path:
    return _ASSETS_ROOT / "horizontal" / f"{n}pins.svg"


def _dip(n: int) -> Path:
    return _ASSETS_ROOT / "dip" / f"{n}pins.svg"


def _external(name: str) -> Path:
    return _ASSETS_ROOT / "external" / f"{name}.svg"



# Catalog of types known in the current netlist (cf. existing layout.py).
# Each entry: type_id (string used in the netlist) -> CatalogEntry.
CATALOG: dict[str, CatalogEntry] = {
    "led": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="LED",
        pin_labels={1: "A", 2: "K"},          # internal names (replace/instructions)
        pin_display_labels={1: "anode", 2: "cathode"},  # shown on the diagram
        pin_roles={1: "signal", 2: "gnd"},
    ),
    "resistor": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="R",
        pin_labels={1: "A", 2: "B"},   # addendum convention + v1 inference
    ),
    "button": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="BTN",
        pin_labels={1: "A", 2: "B"},
        pin_roles={1: "signal", 2: "gnd"},
    ),
    "buzzer": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="BUZ",
        pin_labels={1: "+", 2: "-"},
        pin_roles={1: "signal", 2: "gnd"},
    ),
    "potentiometer": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="POT",
        pin_labels={1: "A", 2: "W", 3: "B"},
        pin_roles={1: "vcc", 2: "signal", 3: "gnd"},
    ),
    "servo": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="SRV",
        pin_labels={1: "VCC", 2: "GND", 3: "SIG"},
        pin_roles={1: "vcc", 2: "gnd", 3: "signal"},
    ),
    "dht11": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="DHT11",
        pin_labels={1: "VCC", 2: "DATA", 3: "GND"},
        pin_roles={1: "vcc", 2: "data", 3: "gnd"},
    ),
    "dht22": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="DHT22",
        pin_labels={1: "VCC", 2: "DATA", 3: "GND"},
        pin_roles={1: "vcc", 2: "data", 3: "gnd"},
    ),
    "hcsr04": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="HC-SR04",
        pin_labels={1: "VCC", 2: "TRIG", 3: "ECHO", 4: "GND"},
        pin_roles={1: "vcc", 2: "trig", 3: "echo", 4: "gnd"},
    ),
    "led_matrix": CatalogEntry(
        asset_path=_single_row(5),
        is_dip=False, pin_count=5,
        name="MAX7219",
        pin_labels={1: "VCC", 2: "GND", 3: "DIN", 4: "CLK", 5: "CS"},
        pin_roles={1: "vcc", 2: "gnd", 3: "data", 4: "sck", 5: "cs"},
    ),
    "tm1637": CatalogEntry(
        name="TM1637", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "CLK", 4: "DIO"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sck", 4: "data"},
    ),
    "ht16k33": CatalogEntry(
        name="HT16K33", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "vl53l0x": CatalogEntry(
        name="VL53L0X", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "max30102": CatalogEntry(
        name="MAX30102", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "tcs34725": CatalogEntry(
        name="TCS34725", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "bh1750": CatalogEntry(
        name="BH1750", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "ads1115": CatalogEntry(
        name="ADS1115", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "pca9685": CatalogEntry(
        name="PCA9685", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "sh1106": CatalogEntry(
        name="SH1106", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "aht20": CatalogEntry(
        name="AHT20", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "bmp280": CatalogEntry(
        name="BMP280", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "apds9960": CatalogEntry(
        name="APDS9960", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "mlx90614": CatalogEntry(
        name="MLX90614", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "sgp30": CatalogEntry(
        name="SGP30", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "scd30": CatalogEntry(
        name="SCD30", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "pn532": CatalogEntry(
        name="PN532", asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL", 5: "IRQ", 6: "RST"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl", 5: "signal", 6: "signal"},
    ),
    # I2C expanders: DIP that physically EXPOSES the output pins
    # (P0-P7 / A0-A7+B0-B7) in addition to the I2C bus, so they are
    # drawn. The 4 connected ones (VCC/GND/SDA/SCL) are at the head (positions
    # 1-4); the outputs follow and remain unwired (cf. unwired_pins
    # in markers.py -> attention icon + textual warning). Same principle
    # as sr74hc595 (DIP listing its outputs QA-QH).
    "pcf8574": CatalogEntry(
        name="PCF8574", asset_path=_dip(12),
        is_dip=True, pin_count=12,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL",
                    5: "P0", 6: "P1", 7: "P2", 8: "P3",
                    9: "P4", 10: "P5", 11: "P6", 12: "P7"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl",
                   5: "signal", 6: "signal", 7: "signal", 8: "signal",
                   9: "signal", 10: "signal", 11: "signal", 12: "signal"},
    ),
    "mcp23017": CatalogEntry(
        name="MCP23017", asset_path=_dip(20),
        is_dip=True, pin_count=20,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL",
                    5: "A0", 6: "A1", 7: "A2", 8: "A3",
                    9: "A4", 10: "A5", 11: "A6", 12: "A7",
                    13: "B0", 14: "B1", 15: "B2", 16: "B3",
                    17: "B4", 18: "B5", 19: "B6", 20: "B7"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl",
                   5: "signal", 6: "signal", 7: "signal", 8: "signal",
                   9: "signal", 10: "signal", 11: "signal", 12: "signal",
                   13: "signal", 14: "signal", 15: "signal", 16: "signal",
                   17: "signal", 18: "signal", 19: "signal", 20: "signal"},
    ),
    "max6675": CatalogEntry(name="MAX6675", asset_path=_single_row(5), is_dip=False,
        pin_count=5, pin_labels={1: "VCC", 2: "GND", 3: "SCK", 4: "CS", 5: "SO"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sck", 4: "cs", 5: "data"}),
    "mcp9808": CatalogEntry(
        name="MCP9808", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "si7021": CatalogEntry(
        name="Si7021", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "adxl345": CatalogEntry(
        name="ADXL345", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "hmc5883l": CatalogEntry(
        name="HMC5883L", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "mcp4725": CatalogEntry(
        name="MCP4725", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "ina260": CatalogEntry(
        name="INA260", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "as5600": CatalogEntry(
        name="AS5600", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "veml6075": CatalogEntry(
        name="VEML6075", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "bno055": CatalogEntry(
        name="BNO055", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "mcp9600": CatalogEntry(
        name="MCP9600", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "max17043": CatalogEntry(
        name="MAX17043", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "amg8833": CatalogEntry(
        name="AMG8833", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "pm25": CatalogEntry(
        name="PMSA003I", asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"},
    ),
    "nrf24l01": CatalogEntry(
        name="nRF24L01", asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        pin_labels={1: "VCC", 2: "GND", 3: "CE", 4: "CSN",
                    5: "SCK", 6: "MOSI", 7: "MISO"},
        pin_roles={1: "vcc", 2: "gnd", 3: "signal", 4: "cs",
                   5: "sck", 6: "mosi", 7: "miso"},
    ),
    "fingerprint": CatalogEntry(name="Fingerprint", asset_path=_single_row(4),
        is_dip=False, pin_count=4, pin_labels={1: "VCC", 2: "GND", 3: "TX", 4: "RX"},
        pin_roles={1: "vcc", 2: "gnd", 3: "tx", 4: "rx"}),
    "drv2605": CatalogEntry(name="DRV2605", asset_path=_single_row(4),
        is_dip=False, pin_count=4, pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sda", 4: "scl"}),
    "tm1638": CatalogEntry(name="TM1638", asset_path=_single_row(5),
        is_dip=False, pin_count=5, pin_labels={1: "VCC", 2: "GND", 3: "STB", 4: "CLK", 5: "DIO"},
        pin_roles={1: "vcc", 2: "gnd", 3: "signal", 4: "sck", 5: "data"}),
    "pcd8544": CatalogEntry(name="Nokia 5110", asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        pin_labels={1: "VCC", 2: "GND", 3: "CLK", 4: "DIN", 5: "DC", 6: "CS", 7: "RST"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sck", 4: "mosi", 5: "signal", 6: "cs", 7: "signal"}),
    "ssd1351": CatalogEntry(name="SSD1351", asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        pin_labels={1: "VCC", 2: "GND", 3: "CS", 4: "DC", 5: "RST", 6: "SCK", 7: "MOSI"},
        pin_roles={1: "vcc", 2: "gnd", 3: "cs", 4: "signal", 5: "signal", 6: "sck", 7: "mosi"}),
    "st7735": CatalogEntry(name="ST7735", asset_path=_single_row(7), is_dip=False,
        pin_count=7, pin_labels={1: "VCC", 2: "GND", 3: "CS", 4: "DC", 5: "RST", 6: "SCK", 7: "SDA"},
        pin_roles={1: "vcc", 2: "gnd", 3: "cs", 6: "sck", 7: "data"}),
    "st7789": CatalogEntry(name="ST7789", asset_path=_single_row(7), is_dip=False,
        pin_count=7, pin_labels={1: "VCC", 2: "GND", 3: "CS", 4: "DC", 5: "RST", 6: "SCK", 7: "SDA"},
        pin_roles={1: "vcc", 2: "gnd", 3: "cs", 6: "sck", 7: "data"}),
    "max31855": CatalogEntry(name="MAX31855", asset_path=_single_row(5), is_dip=False,
        pin_count=5, pin_labels={1: "VCC", 2: "GND", 3: "SCLK", 4: "CS", 5: "MISO"},
        pin_roles={1: "vcc", 2: "gnd", 3: "sck", 4: "cs", 5: "data"}),
    "hx711": CatalogEntry(name="HX711", asset_path=_single_row(4), is_dip=False,
        pin_count=4, pin_labels={1: "VCC", 2: "GND", 3: "DT", 4: "SCK"},
        pin_roles={1: "vcc", 2: "gnd", 3: "data", 4: "sck"}),
    "dfplayer": CatalogEntry(name="DFPlayer", asset_path=_single_row(4), is_dip=False,
        pin_count=4, pin_labels={1: "VCC", 2: "GND", 3: "RX", 4: "TX"},
        pin_roles={1: "vcc", 2: "gnd"}),
    "lcd_i2c": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="LCD",
        pin_labels={1: "GND", 2: "VCC", 3: "SDA", 4: "SCL"},
        pin_roles={1: "gnd", 2: "vcc", 3: "sda", 4: "scl"},
    ),
    "oled_ssd1306": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="OLED",
        pin_labels={1: "GND", 2: "VCC", 3: "SCL", 4: "SDA"},
        pin_roles={1: "gnd", 2: "vcc", 3: "scl", 4: "sda"},
    ),
    "module_generic": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="MOD",
        pin_labels={1: "1", 2: "2"},
    ),
    # Simple DC motor (2 wires). Placed off-BB like the stepper: it
    # connects to the OUT1/OUT2 outputs of the driver (L298N) via wires, not
    # on the breadboard. Created by the ambiguity modal (option
    # "Moteur DC") which then delegates to the inference rule to
    # add the L298N + battery_external.
    "dc_motor": CatalogEntry(
        asset_path=_external("dc_motor"),
        is_dip=False, pin_count=2,
        name="DC Motor",
        pin_labels={1: "M+", 2: "M-"},
        pin_roles={1: "out_a", 2: "out_b"},
    ),
    # ULN2003: driver for 28BYJ-48 stepper. Off-BB (breakout module
    # with typical red PCB). 10 pins exposed: 6 on the Arduino side (VCC=
    # battery, GND, IN1-4) + 4 on the motor side (OUT1-4 to the stepper).
    # COM (red wire of the stepper) shares the BAT_5V rail with the driver's VCC.
    "uln2003": CatalogEntry(
        asset_path=_external("uln2003"),
        is_dip=False, pin_count=11,
        name="ULN2003",
        # Pin 11 = JST_PWR: 5th hole of the JST connector on the ULN2003.
        # Physically connected to the driver's VCC, but exposed as a
        # distinct pin in the netlist so that a dedicated net (not BAT_5V)
        # connects stepper.COM <-> uln2003.JST_PWR without an external wire to
        # the BB. Empty label so as not to silkscreen it (the JST hole is
        # already visible on the SVG, no need for extra text).
        pin_labels={1: "VCC", 2: "GND", 3: "IN1", 4: "IN2", 5: "IN3",
                    6: "IN4", 7: "OUT1", 8: "OUT2", 9: "OUT3", 10: "OUT4",
                    11: "JST_PWR"},
    ),
    # 28BYJ-48 stepper itself: physical motor off-BB, connected to the
    # ULN2003 via 5 wires (red COM + 4 phases). Created by the inference
    # rule when a ULN2003 is detected.
    "stepper_motor": CatalogEntry(
        asset_path=_external("stepper_motor"),
        is_dip=False, pin_count=5,
        name="STEPPER",
        pin_labels={1: "COM", 2: "A", 3: "B", 4: "C", 5: "D"},
        pin_roles={1: "coil_com", 2: "coil_a", 3: "coil_b", 4: "coil_c", 5: "coil_d"},
    ),
    # NEMA17 bipolar stepper (standard CNC/3D printers size). Off-BB,
    # typically connected to an A4988 via 4 wires (1A/1B = coil A, 2A/2B
    # = coil B). The SVG shows a 45° plunging view with a cubic body
    # and 6 output wires; only the 4 central ones are routed (the 2
    # outer ones are visual, representing the unipolar center taps
    # not used in bipolar).
    "nema17": CatalogEntry(
        asset_path=_external("nema17"),
        is_dip=False, pin_count=4,
        name="NEMA17",
        pin_labels={1: "1A", 2: "1B", 3: "2A", 4: "2B"},
        # Original SVG 153x241 — too bulky compared to the
        # other motors (stepper 127x144, dc 60x92). Scale at 0.6 = 92x145,
        # proportions similar to the 28BYJ-48 stepper.
        render_scale=0.6,
        pin_roles={1: "coil_a1", 2: "coil_a2", 3: "coil_b1", 4: "coil_b2"},
    ),
    # DRV8833 low-voltage dual H-bridge driver (Last Minute Engineers /
    # Pololu / similar). 2x6 module = DIP-12 on breadboard. No
    # dedicated ENA/PWM: PWM the IN directly. VCC shared logic+motor
    # (DRV8833 supports 2.7-10.8V). Pinout:
    #   left: SLEEP, OUT1, OUT2, OUT3, OUT4, FAULT
    #   right: IN1, IN2, VCC, GND, IN3, IN4
    # OUT1/OUT2 = motor A, OUT3/OUT4 = motor B (same on the IN side).
    "drv8833": CatalogEntry(
        asset_path=_dip(12),
        is_dip=True, pin_count=12,
        name="DRV8833",
        pin_labels={
            1: "SLEEP", 2: "OUT1",  3: "OUT2",  4: "OUT3",
            5: "OUT4",  6: "FAULT", 7: "IN1",   8: "IN2",
            9: "VCC",   10: "GND",  11: "IN3",  12: "IN4",
        },
    ),
    # TB6612FNG dual H-bridge driver (SparkFun breakout) placed on breadboard.
    # 2x8 pins module compatible with DIP-16. Modern successor of the L298N for
    # small DC motors (higher efficiency, more compact). Pinout:
    #   left: VM, VCC, GND, AO1, AO2, BO2, BO1, GND
    #   right: PWMA, AIN2, AIN1, STBY, BIN1, BIN2, PWMB, GND
    # STBY HIGH = enabled. 3 GND pins (3/8/9) — same net.
    "tb6612fng": CatalogEntry(
        asset_path=_dip(16),
        is_dip=True, pin_count=16,
        name="TB6612FNG",
        pin_labels={
            1: "VM",   2: "VCC",  3: "GND",  4: "AO1",
            5: "AO2",  6: "BO2",  7: "BO1",  8: "GND",
            9: "GND",  10: "PWMB", 11: "BIN2", 12: "BIN1",
            13: "STBY", 14: "AIN1", 15: "AIN2", 16: "PWMA",
        },
    ),
    # A4988 stepper driver (Pololu/Allegro) placed directly on breadboard.
    # 2x8 pins breakout module compatible with DIP-16. Microstepping driver for
    # bipolar steppers (e.g. NEMA17). Pinout:
    #   left: ENA, MS1, MS2, MS3, RST, SLP, STEP, DIR
    #   right: VMOT, GND_motor, 2B, 2A, 1A, 1B, VDD, GND_logic
    # MS1/MS2/MS3: microstepping mode selection (full, 1/2, 1/4, 1/8, 1/16).
    # 2 GND pins (9 and 15) — same net but distinct positions.
    "a4988": CatalogEntry(
        asset_path=_dip(16),
        is_dip=True, pin_count=16,
        name="A4988",
        pin_labels={
            1: "ENA",  2: "MS1",  3: "MS2",  4: "MS3",
            5: "RST",  6: "SLP",  7: "STEP", 8: "DIR",
            9: "GND",  10: "VDD", 11: "1B",  12: "1A",
            13: "2A",  14: "2B",  15: "GND", 16: "VMOT",
        },
    ),
    # Bare L293D DIP-16: classic H-bridge placed directly on breadboard.
    # Pinout: 1=ENA, 2=IN1, 3=OUT1, 4-5=GND (motor return), 6=OUT2, 7=IN2,
    # 8=VS (motor +9-24V), 9=ENB, 10=IN3, 11=OUT3, 12-13=GND, 14=OUT4,
    # 15=IN4, 16=VCC (logic 5V). Note: 4 visual GND pins (4/5/12/13)
    # but same net; the router only uses one (first match).
    "sr74hc595": CatalogEntry(
        asset_path=_dip(16),
        is_dip=True, pin_count=16,
        name="74HC595",
        pin_labels={1: "QB", 2: "QC", 3: "QD", 4: "QE", 5: "QF", 6: "QG",
                    7: "QH", 8: "GND", 9: "QH2", 10: "MR", 11: "CLK", 12: "LATCH",
                    13: "OE", 14: "DATA", 15: "QA", 16: "VCC"},
        pin_roles={8: "gnd", 11: "sck", 12: "cs", 14: "data", 16: "vcc"},
    ),
    "l293d": CatalogEntry(
        asset_path=_dip(16),
        is_dip=True, pin_count=16,
        name="L293D",
        pin_labels={
            1: "ENA",  2: "IN1", 3: "OUT1", 4: "GND", 5: "GND",
            6: "OUT2", 7: "IN2", 8: "VS",
            9: "ENB", 10: "IN3", 11: "OUT3", 12: "GND", 13: "GND",
            14: "OUT4", 15: "IN4", 16: "VCC",
        },
    ),
    # L293D module breakout: same IC but on a small blue PCB (off-BB).
    # 13 pins exposed (not IN5/IN6/IN7 of the chip, just the useful H-bridge).
    # Green 6-pin terminal block on the left (A-/A+/B-/B+/GND/VIN), black 6-pin
    # header on the right (VCC/GND/IN1-4), EN1/EN2 PWM jumper at the bottom-right.
    "l293d_module": CatalogEntry(
        asset_path=_external("l293d_module"),
        is_dip=False, pin_count=13,
        name="L293D Module",
        pin_labels={
            1: "ENA", 2: "IN1", 3: "IN2", 4: "VCC",
            5: "VS",  6: "GND", 7: "OUT1", 8: "OUT2",
            9: "IN3", 10: "IN4", 11: "ENB", 12: "OUT3", 13: "OUT4",
        },
    ),
    # L298N: H-bridge driver for DC motor. Off-BB (breakout module
    # with typical green PCB + central heatsink). 8 user-visible pins:
    # ENA (PWM speed), IN1/IN2 (direction), VCC (logic 5V Arduino), VS
    # (motor power, battery), GND, OUT1/OUT2 (to the motor). Created by the
    # inference rule when a dc_motor is detected (the motor NEVER
    # connects directly to the Arduino, the driver is mandatory).
    "l298n": CatalogEntry(
        asset_path=_external("l298n"),
        is_dip=False, pin_count=13,
        name="L298N",
        pin_labels={1: "ENA",  2: "IN1",  3: "IN2",  4: "VCC",
                    5: "VS",   6: "GND",  7: "OUT1", 8: "OUT2",
                    9: "IN3",  10: "IN4", 11: "ENB", 12: "OUT3", 13: "OUT4"},
    ),
    # External battery: alternative to the Arduino power supply for power-hungry
    # components (servo for example). Placed off-BB, above the Arduino.
    "battery_external": CatalogEntry(
        asset_path=_external("battery"),
        is_dip=False, pin_count=2,
        name="BAT",
        pin_labels={1: "+", 2: "-"},
    ),

    # ─── Vignettes dediees (TODO #41 partie 2) ─────────────────────────────
    # Ces huit types etaient dessines en rectangle blanc par `resolve_generic`.
    # Ils gardent EXACTEMENT la meme geometrie -- la vignette est le generique
    # du meme nombre de broches, avec un glyphe reconnaissable a l interieur.
    #
    # Les `pin_labels` sont ceux que `markers` EMET reellement (mesures sur un
    # sketch de chaque type, verrouillees par
    # `test_catalog_labels_are_the_ones_markers_emits`), jamais un brochage
    # invente : la regle de #41 est de ne jamais en fabriquer un.
    #
    # `pin_roles` est laisse VIDE a dessein, pas par oubli : `resolve_generic`
    # ne le renseignait pas non plus, donc `_default_roles` deduisait les roles
    # des libelles. Le renseigner ici changerait le routage de composants qui
    # marchent aujourd hui -- l equivalence a ete mesuree sans lui (rendu
    # identique octet pour octet, avec et sans entree catalogue).
    "relay": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="Relais",
        pin_labels={1: "VCC", 2: "GND", 3: "IN"},
    ),
    "pir": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="PIR",
        pin_labels={1: "VCC", 2: "OUT", 3: "GND"},
    ),
    "ldr": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="LDR",
        pin_labels={1: "VCC", 2: "OUT", 3: "GND"},
    ),
    "ir_receiver": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="IR",
        pin_labels={1: "OUT", 2: "GND", 3: "VCC"},
    ),
    "neopixel": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="NeoPixel",
        pin_labels={1: "VCC", 2: "DIN", 3: "GND"},
    ),
    "encoder": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="Encodeur",
        pin_labels={1: "VCC", 2: "GND", 3: "CLK", 4: "DT"},
    ),
    "mfrc522": CatalogEntry(
        asset_path=_single_row(8),
        is_dip=False, pin_count=8,
        name="MFRC522",
        pin_labels={1: "VCC", 2: "RST", 3: "GND", 4: "IRQ",
                    5: "MISO", 6: "MOSI", 7: "SCK", 8: "SDA"},
    ),
    "ili9341": CatalogEntry(
        asset_path=_single_row(8),
        is_dip=False, pin_count=8,
        name="ILI9341",
        pin_labels={1: "VCC", 2: "GND", 3: "CS", 4: "RESET",
                    5: "DC", 6: "MOSI", 7: "SCK", 8: "LED"},
    ),

    # ── Lot Fritzing du 2026-08-19 (TODO #54 / #41) ───────────────────────────
    # Brochages relevés sur les fiches `.fzp` de github.com/fritzing/fritzing-parts
    # via `scripts/fritzing_import.py`, puis relus un par un. Ces cinq composants
    # existaient déjà au registre avec leur identité ET leur bibliothèque : il ne
    # leur manquait QUE d'être dessinables.
    #
    # ⚠️ Fiche du MODULE, jamais de la puce nue. `core/DS1307.fzp` est le DIP-8 et
    # nomme ses broches « X1 - Crystal » ou « Vbat - Backup Supply » ; c'est la
    # fiche du breakout ZS-042 qui donne le brochage utile. Les deux sont des
    # données justes, une seule est celle que l'utilisateur a en main.
    #
    # Validation indépendante du procédé : HC-SR04 était déjà au catalogue,
    # écrit à la main, et Fritzing en donne exactement les mêmes quatre broches
    # dans le même ordre.
    "ds18b20": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="DS18B20",
        pin_labels={1: "VDD", 2: "GND", 3: "DQ"},
        pin_roles={1: "vcc", 2: "gnd", 3: "data"},
    ),
    "hmc5883": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="HMC5883L",
        pin_labels={1: "GND", 2: "VCC", 3: "SDA", 4: "SCL"},
        pin_roles={1: "gnd", 2: "vcc", 3: "sda", 4: "scl"},
    ),
    "bmp085": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="BMP085",
        pin_labels={1: "VCC", 2: "GND", 3: "EOC", 4: "XCLR",
                    5: "SCL", 6: "SDA"},
        pin_roles={1: "vcc", 2: "gnd", 3: "signal", 4: "signal",
                   5: "scl", 6: "sda"},
    ),
    "ds3231": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="DS3231",
        pin_labels={1: "GND", 2: "VCC", 3: "SDA", 4: "SCL",
                    5: "SQW", 6: "32K"},
        pin_roles={1: "gnd", 2: "vcc", 3: "sda", 4: "scl",
                   5: "signal", 6: "signal"},
    ),
    "mpu6050": CatalogEntry(
        asset_path=_single_row(8),
        is_dip=False, pin_count=8,
        name="MPU6050",
        pin_labels={1: "VCC", 2: "GND", 3: "SCL", 4: "SDA",
                    5: "XDA", 6: "XCL", 7: "AD0", 8: "INT"},
        pin_roles={1: "vcc", 2: "gnd", 3: "scl", 4: "sda",
                   5: "signal", 6: "signal", 7: "signal", 8: "signal"},
    ),

    # ── Lot Fritzing #2 du 2026-08-19 (TODO #54 / #41 / #57) ─────────────────
    # Meme procede que le lot du meme jour : brochages releves sur les fiches
    # `.fzp` du DEPOT COMPLET (clone local, 2569 fiches — l API tronquait les
    # resultats et avait fait sous-estimer la couverture reelle a 10/72 au lieu
    # de 46/72). Chaque candidat verifie contre le piege « puce nue vs module »
    # avant inclusion ; ecartes de ce lot : `sd_card` (le candidat trouve est un
    # CONNECTEUR de carte SD brut, pas le module SPI cable par les debutants),
    # `gps` (le seul candidat est un module Trimble professionnel non generique),
    # `buttonpad` (96 broches, brochage matriciel brut, non dessinable), et
    # `mpu9250`/`openlog`/`wiz820io` (9 ou 11 broches) -- au moment de ce lot,
    # aucun asset ne pouvait les dessiner. Depuis, TODO #58 (2026-08-20) a
    # etendu la rangee simple aux impairs 9/11/13 : la contrainte qui les
    # avait ecartes n'existe plus, mais leurs brochages n'ont pas ete releves
    # -- candidats pour un lot futur, pas ajoutes ici.
    "acs712": CatalogEntry(
        asset_path=_single_row(5),
        is_dip=False, pin_count=5,
        name="ACS712",
        pin_labels={1: "IP+", 2: "IP-", 3: "5V", 4: "VO", 5: "GND"},
        pin_roles={1: "signal", 2: "signal", 3: "vcc", 4: "signal", 5: "gnd"},
    ),
    "adjd_s311": CatalogEntry(
        asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        name="ADJD-S311",
        pin_labels={1: "SCL", 2: "SDA", 3: "CLK", 4: "SLP", 5: "GND", 6: "LED", 7: "VCC"},
        pin_roles={1: "scl", 2: "sda", 3: "signal", 4: "signal", 5: "gnd", 6: "signal", 7: "vcc"},
    ),
    "bme280": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="BME280",
        pin_labels={1: "GND", 2: "3.3V", 3: "SDI/SDA", 4: "SCK/SCL", 5: "!CS", 6: "SDO/ADR"},
        pin_roles={1: "gnd", 2: "vcc", 3: "sda", 4: "scl", 5: "cs", 6: "signal"},
    ),
    "bmp180": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="BMP180",
        pin_labels={1: "VCC", 2: "GND", 3: "SCL", 4: "SDA"},
        pin_roles={1: "vcc", 2: "gnd", 3: "scl", 4: "sda"},
    ),
    "ds1307": CatalogEntry(
        asset_path=_single_row(5),
        is_dip=False, pin_count=5,
        name="DS1307",
        pin_labels={1: "5V", 2: "GND", 3: "SQW", 4: "SCL", 5: "SDA"},
        pin_roles={1: "vcc", 2: "gnd", 3: "signal", 4: "scl", 5: "sda"},
    ),
    "ds3234": CatalogEntry(
        asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        name="DS3234",
        pin_labels={1: "SS", 2: "MOSI", 3: "MISO", 4: "SCLK", 5: "INT/SQW", 6: "VCC", 7: "GND"},
        pin_roles={1: "cs", 2: "mosi", 3: "miso", 4: "sck", 5: "signal", 6: "vcc", 7: "gnd"},
    ),
    "force_sensor": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="FSR",
        pin_labels={1: "Pin 1", 2: "Pin 2"},
        pin_roles={1: "signal", 2: "signal"},
    ),
    "ftdi_basic": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="FTDI Basic",
        pin_labels={1: "DTR", 2: "RXI", 3: "TXO", 4: "POWER", 5: "CTS", 6: "GND"},
        pin_roles={1: "signal", 2: "rx", 3: "tx", 4: "vcc", 5: "signal", 6: "gnd"},
    ),
    "grove_oled_128x96": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="Grove OLED",
        pin_labels={1: "GND", 2: "VCC", 3: "SDA", 4: "SCL"},
        pin_roles={1: "gnd", 2: "vcc", 3: "sda", 4: "scl"},
    ),
    "hc05": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="HC-05",
        pin_labels={1: "State", 2: "TXD", 3: "RXD", 4: "VCC", 5: "Key", 6: "GND"},
        pin_roles={1: "signal", 2: "tx", 3: "rx", 4: "vcc", 5: "signal", 6: "gnd"},
    ),
    "hmc6352": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="HMC6352",
        pin_labels={1: "GND", 2: "VCC", 3: "SDA", 4: "SCL"},
        pin_roles={1: "gnd", 2: "vcc", 3: "sda", 4: "scl"},
    ),
    "itg3200": CatalogEntry(
        asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        name="ITG-3200",
        pin_labels={1: "VCC", 2: "VLOGIC", 3: "GND", 4: "INT", 5: "CLKIN", 6: "SDA", 7: "SCL"},
        pin_roles={1: "vcc", 2: "vcc", 3: "gnd", 4: "signal", 5: "signal", 6: "sda", 7: "scl"},
    ),
    "joystick": CatalogEntry(
        asset_path=_single_row(5),
        is_dip=False, pin_count=5,
        name="Joystick",
        pin_labels={1: "GND", 2: "SEL", 3: "HORZ", 4: "VERT", 5: "VCC"},
        pin_roles={1: "gnd", 2: "signal", 3: "signal", 4: "signal", 5: "vcc"},
    ),
    "l3g4200d": CatalogEntry(
        asset_path=_single_row(8),
        is_dip=False, pin_count=8,
        name="L3G4200D",
        pin_labels={1: "GND", 2: "VCC", 3: "SCL", 4: "SDA", 5: "SDO", 6: "CS", 7: "INT2", 8: "INT1"},
        pin_roles={1: "gnd", 2: "vcc", 3: "scl", 4: "sda", 5: "signal", 6: "cs", 7: "signal", 8: "signal"},
    ),
    "light_sensor": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="Light Sensor",
        pin_labels={1: "GND", 2: "VCC", 3: "SIG"},
        pin_roles={1: "gnd", 2: "vcc", 3: "signal"},
    ),
    "load_cell": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="Load Cell",
        pin_labels={1: "B", 2: "R", 3: "W"},
        pin_roles={1: "signal", 2: "signal", 3: "signal"},
    ),
    "lsm303": CatalogEntry(
        asset_path=_single_row(8),
        is_dip=False, pin_count=8,
        name="LSM303",
        pin_labels={1: "SCL_M", 2: "SDA_M", 3: "DRDY", 4: "SA0", 5: "VCC", 6: "GND", 7: "INT2", 8: "INT1"},
        pin_roles={1: "scl", 2: "sda", 3: "signal", 4: "signal", 5: "vcc", 6: "gnd", 7: "signal", 8: "signal"},
    ),
    "mag3110": CatalogEntry(
        asset_path=_single_row(8),
        is_dip=False, pin_count=8,
        name="MAG3110",
        pin_labels={1: "CAP-A", 2: "CAP-R", 3: "GND", 4: "INT1", 5: "SCL", 6: "SDA", 7: "VDD", 8: "VDDIO"},
        pin_roles={1: "signal", 2: "signal", 3: "gnd", 4: "signal", 5: "scl", 6: "sda", 7: "vcc", 8: "vcc"},
    ),
    "max1704x": CatalogEntry(
        asset_path=_single_row(8),
        is_dip=False, pin_count=8,
        name="MAX1704X",
        pin_labels={1: "ALT", 2: "CELL", 3: "CTG", 4: "GND", 5: "QST", 6: "SCL", 7: "SDA", 8: "VDD"},
        pin_roles={1: "signal", 2: "signal", 3: "signal", 4: "gnd", 5: "signal", 6: "scl", 7: "sda", 8: "vcc"},
    ),
    "mcp41xxx": CatalogEntry(
        asset_path=_single_row(8),
        is_dip=False, pin_count=8,
        name="MCP41xxx",
        pin_labels={1: "A", 2: "B", 3: "CS", 4: "DI", 5: "GND", 6: "SCK", 7: "VCC", 8: "W"},
        pin_roles={1: "signal", 2: "signal", 3: "cs", 4: "mosi", 5: "gnd", 6: "sck", 7: "vcc", 8: "signal"},
    ),
    "mcp42xxx": CatalogEntry(
        asset_path=_dip(14),
        is_dip=True, pin_count=14,
        name="MCP42xxx",
        pin_labels={1: "A0", 2: "A1", 3: "B0", 4: "B1", 5: "CS", 6: "DI", 7: "DO", 8: "GND", 9: "RST", 10: "SCK", 11: "SHTDWN", 12: "VCC", 13: "W0", 14: "W1"},
        pin_roles={1: "signal", 2: "signal", 3: "signal", 4: "signal", 5: "cs", 6: "mosi", 7: "miso", 8: "gnd", 9: "signal", 10: "sck", 11: "signal", 12: "vcc", 13: "signal", 14: "signal"},
    ),
    "microphone": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="Microphone",
        pin_labels={1: "pin1", 2: "pin2"},
        pin_roles={1: "signal", 2: "signal"},
    ),
    "mma8452q": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="MMA8452Q",
        pin_labels={1: "3.3V", 2: "SDA", 3: "SCL", 4: "I2", 5: "I1", 6: "GND"},
        pin_roles={1: "vcc", 2: "sda", 3: "scl", 4: "signal", 5: "signal", 6: "gnd"},
    ),
    "mpl3115a2": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="MPL3115A2",
        pin_labels={1: "INT2", 2: "INT1", 3: "SDA", 4: "SCL", 5: "VCC", 6: "GND"},
        pin_roles={1: "signal", 2: "signal", 3: "sda", 4: "scl", 5: "vcc", 6: "gnd"},
    ),
    "mpr121": CatalogEntry(
        asset_path=_dip(18),
        is_dip=True, pin_count=18,
        name="MPR121",
        pin_labels={1: "ADDR", 2: "~IRQ", 3: "SCL", 4: "SDA", 5: "ELE11", 6: "ELE10", 7: "ELE9", 8: "ELE8", 9: "ELE7", 10: "ELE6", 11: "ELE5", 12: "ELE4", 13: "ELE3", 14: "ELE2", 15: "ELE1", 16: "ELE0", 17: "3.3V", 18: "GND"},
        pin_roles={1: "signal", 2: "signal", 3: "scl", 4: "sda", 5: "signal", 6: "signal", 7: "signal", 8: "signal", 9: "signal", 10: "signal", 11: "signal", 12: "signal", 13: "signal", 14: "signal", 15: "signal", 16: "signal", 17: "vcc", 18: "gnd"},
    ),
    "reed_switch": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="Reed Switch",
        pin_labels={1: "pin 1", 2: "pin 2"},
        pin_roles={1: "signal", 2: "signal"},
    ),
    "sht15": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="SHT15",
        pin_labels={1: "VCC", 2: "GND", 3: "SCL", 4: "SDA"},
        pin_roles={1: "vcc", 2: "gnd", 3: "scl", 4: "sda"},
    ),
    "sht25": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="SHT25",
        pin_labels={1: "VCC", 2: "SCL", 3: "SDA", 4: "GND"},
        pin_roles={1: "vcc", 2: "scl", 3: "sda", 4: "gnd"},
    ),
    "slide_switch": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="Slide Switch",
        pin_labels={1: "OFF", 2: "ON"},
        pin_roles={1: "signal", 2: "signal"},
    ),
    "slider": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="Slider",
        pin_labels={1: "A", 2: "E", 3: "S"},
        pin_roles={1: "signal", 2: "signal", 3: "signal"},
    ),
    "soil_moisture": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="Soil Moisture",
        pin_labels={1: "VCC", 2: "GND", 3: "SIG"},
        pin_roles={1: "vcc", 2: "gnd", 3: "signal"},
    ),
    "solenoid": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="Solenoid",
        pin_labels={1: "pin1", 2: "pin2"},
        pin_roles={1: "signal", 2: "signal"},
    ),
    "speaker": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="Speaker",
        pin_labels={1: "+", 2: "-"},
        pin_roles={1: "signal", 2: "gnd"},
    ),
    "thermal_printer": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="Thermal Ptr.",
        pin_labels={1: "RXD", 2: "TXD", 3: "GND", 4: "VH"},
        pin_roles={1: "rx", 2: "tx", 3: "gnd", 4: "vcc"},
    ),
    "thermistor": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="Thermistor",
        pin_labels={1: "pin 0", 2: "pin 1"},
        pin_roles={1: "signal", 2: "signal"},
    ),
    "tilt_switch": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="Tilt Switch",
        pin_labels={1: "1", 2: "2"},
        pin_roles={1: "signal", 2: "signal"},
    ),
    "tmp102": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="TMP102",
        pin_labels={1: "V+", 2: "SDA", 3: "SCL", 4: "GND", 5: "ALERT", 6: "ADD0"},
        pin_roles={1: "vcc", 2: "sda", 3: "scl", 4: "gnd", 5: "signal", 6: "signal"},
    ),
    "toggle_switch": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="Toggle Switch",
        pin_labels={1: "L1", 2: "COM", 3: "L2"},
        pin_roles={1: "signal", 2: "signal", 3: "signal"},
    ),
    "us100": CatalogEntry(
        asset_path=_single_row(5),
        is_dip=False, pin_count=5,
        name="US-100",
        pin_labels={1: "VCC", 2: "TRIG", 3: "ECHO", 4: "GND", 5: "GND-2"},
        pin_roles={1: "vcc", 2: "signal", 3: "signal", 4: "gnd", 5: "gnd"},
    ),
    "vcnl4000": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="VCNL4000",
        pin_labels={1: "GND", 2: "IR+", 3: "IR-", 4: "SCL", 5: "SDA", 6: "VDD"},
        pin_roles={1: "gnd", 2: "signal", 3: "signal", 4: "scl", 5: "sda", 6: "vcc"},
    ),

    # DRV8825 : meme empreinte DIP-16 que le driver frere A4988 (verifie sur la
    # fiche Fritzing du breakout, 2026-08-19 — les deux partagent le meme
    # brochage physique, base des cartes RepRap/Pololu). Etiquettes RACCOURCIES
    # dans le meme style que a4988 : la fiche Fritzing les donnait verbeuses
    # ("GROUND ST/ MT", "VOLTAGE ST/ MT"), signalees par l'outil d'import comme
    # possible puce nue — verification faite, c'est bien le meme brochage de
    # breakout que A4988, seulement plus explicite sur les 4 sorties moteur.
    "drv8825": CatalogEntry(
        asset_path=_dip(16),
        is_dip=True, pin_count=16,
        name="DRV8825",
        pin_labels={
            1: "ENA",  2: "MS1",  3: "MS2",  4: "MS3",
            5: "RST",  6: "SLP",  7: "STEP", 8: "DIR",
            9: "GND",  10: "VDD", 11: "1B",  12: "1A",
            13: "2A",  14: "2B",  15: "GND", 16: "VMOT",
        },
    ),

    # ── Lot #2 « identité élargie » du 2026-08-19 (TODO #57, sous-chantier B).
    # Brochages réels tirés de fiches Fritzing `.fzp` (contrib/), dédoublonnés
    # par l'outil d'import. À cette époque, `sharp_memory_display` et
    # `winc1500` n'avaient PAS d'entrée ici (9 et 13 broches — non dessinables
    # par `resolve_generic`). Depuis, TODO #58 (2026-08-20) a étendu la rangée
    # simple aux impairs 9/11/13 et leur a donné une entrée plus bas dans ce
    # fichier.
    "tmp006": CatalogEntry(
        asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        name="TMP006",
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL", 5: "DRDY", 6: "ADDR1", 7: "ADDR0"},
    ),
    "tmp007": CatalogEntry(
        asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        name="TMP007",
        pin_labels={1: "VCC", 2: "GND", 3: "SDA", 4: "SCL", 5: "ALERT", 6: "ADDR1", 7: "ADDR0"},
    ),
    "si1145": CatalogEntry(
        asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        name="SI1145",
        pin_labels={1: "+5V", 2: "+3V3", 3: "INT", 4: "LED", 5: "SCL", 6: "SDA", 7: "GND"},
    ),
    "adt7410": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="ADT7410",
        pin_labels={1: "VCC", 2: "CT", 3: "INT", 4: "SDA", 5: "SCL", 6: "GND"},
    ),
    "ds3502": CatalogEntry(
        asset_path=_dip(10),
        is_dip=True, pin_count=10,
        name="DS3502",
        pin_labels={
            1: "V+", 2: "VCC", 3: "SCL", 4: "SDA", 5: "RL",
            6: "RW", 7: "RH", 8: "A0", 9: "A1", 10: "GND",
        },
    ),
    "fram": CatalogEntry(
        asset_path=_single_row(8),
        is_dip=False, pin_count=8,
        name="FRAM",
        pin_labels={1: "VCC", 2: "WP", 3: "SCL", 4: "SDA", 5: "A2", 6: "A1", 7: "A0", 8: "GND"},
    ),
    "mprls": CatalogEntry(
        asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        name="MPRLS",
        pin_labels={1: "VIN", 2: "3.3V", 3: "EOC", 4: "RESET", 5: "SDA", 6: "SCL", 7: "GND"},
    ),
    "hdc1008": CatalogEntry(
        asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        name="HDC1008",
        pin_labels={1: "VDD", 2: "GND", 3: "SCL", 4: "SDA", 5: "RDY", 6: "A1", 7: "A0"},
    ),
    "adxl335": CatalogEntry(
        asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        name="ADXL335",
        pin_labels={1: "VIN", 2: "+3V3", 3: "GND", 4: "ZOUT", 5: "YOUT", 6: "XOUT", 7: "ST"},
    ),
    "bluefruit_le": CatalogEntry(
        asset_path=_single_row(8),
        is_dip=False, pin_count=8,
        name="Bluefruit LE",
        pin_labels={
            1: "DFU", 2: "GND", 3: "RTS", 4: "VIN",
            5: "RXI", 6: "TXO", 7: "CTS", 8: "MODE",
        },
    ),
    "spi_flash": CatalogEntry(
        asset_path=_single_row(7),
        is_dip=False, pin_count=7,
        name="SPI Flash",
        pin_labels={1: "3.3V", 2: "VIN", 3: "SCK", 4: "MISO", 5: "MOSI", 6: "SS", 7: "GND"},
    ),
    "dotstar": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="DotStar",
        pin_labels={1: "DI", 2: "+5V", 3: "GND", 4: "CO", 5: "CI", 6: "DO"},
    ),
    "tsl2561": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="TSL2561",
        pin_labels={1: "GND", 2: "SCL", 3: "SDA", 4: "3.3V"},
    ),
    "tmp36": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="TMP36",
        pin_labels={1: "+Vs", 2: "Vout", 3: "GND"},
    ),
    "flex_sensor": CatalogEntry(
        asset_path=_single_row(2),
        is_dip=False, pin_count=2,
        name="Flex",
        pin_labels={1: "Pin 1", 2: "Pin 2"},
    ),
    "si4713": CatalogEntry(
        asset_path=_dip(12),
        is_dip=True, pin_count=12,
        name="SI4713",
        pin_labels={
            1: "ANT", 2: "RIN", 3: "LIN", 4: "VIN", 5: "GND", 6: "+3V3",
            7: "GP2", 8: "GP1", 9: "SDA", 10: "SCL", 11: "CS", 12: "RST",
        },
    ),
    "ads7830": CatalogEntry(
        asset_path=_dip(16),
        is_dip=True, pin_count=16,
        name="ADS7830",
        pin_labels={
            1: "VCC", 2: "A0", 3: "A1", 4: "A2", 5: "A3", 6: "A4", 7: "A5", 8: "A6",
            9: "A7", 10: "SDA", 11: "SCL", 12: "REF", 13: "ADDR0", 14: "ADDR1", 15: "GND", 16: "COM",
        },
    ),
    "trellis": CatalogEntry(
        asset_path=_single_row(5),
        is_dip=False, pin_count=5,
        name="Trellis",
        pin_labels={1: "VCC", 2: "INT", 3: "SDA", 4: "SCL", 5: "GND"},
    ),
    # A/C = anode/cathode de la LED IR emettrice, E/K = emetteur/collecteur du
    # phototransistor recepteur — 2 composants optiques dans un seul boitier,
    # fiche Fritzing core (QRE1113/QRD1114, memes 4 broches).
    "ir_reflective_sensor": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="QRE1113",
        pin_labels={1: "A", 2: "C", 3: "E", 4: "K"},
    ),

    # ── Lot #4 (2026-08-19). À cette époque, `stspin220` et `tmc2209`
    # n'avaient PAS d'entrée ici (13 et 15 broches annoncées — en réalité un
    # artefact du dé-doublonnage de l'outil d'import, pas le vrai brochage).
    # Depuis, TODO #58 (2026-08-20) leur a donné une entrée plus bas dans ce
    # fichier : 14 et 16 broches réelles (deux GND physiques), en DIP.
    "mmc5603": CatalogEntry(
        asset_path=_single_row(5),
        is_dip=False, pin_count=5,
        name="MMC5603",
        pin_labels={1: "VCC", 2: "3.3V", 3: "SCL", 4: "SDA", 5: "GND"},
    ),
    "hdc3021": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="HDC3021",
        pin_labels={1: "VCC", 2: "!RESET", 3: "ALERT", 4: "SDA", 5: "SCL", 6: "GND"},
    ),
    "ina228": CatalogEntry(
        asset_path=_single_row(8),
        is_dip=False, pin_count=8,
        name="INA228",
        pin_labels={
            1: "VCC", 2: "VIN+", 3: "VBUS", 4: "VIN-",
            5: "ALERT", 6: "SCL", 7: "SDA", 8: "GND",
        },
    ),
    "opt4048": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="OPT4048",
        pin_labels={1: "VCC", 2: "SCL", 3: "SDA", 4: "INT", 5: "ADDR", 6: "GND"},
    ),
    "ina169": CatalogEntry(
        asset_path=_single_row(5),
        is_dip=False, pin_count=5,
        name="INA169",
        pin_labels={1: "VIN-", 2: "VIN+", 3: "VCC", 4: "GND", 5: "OUT"},
    ),
    "guva_s12sd": CatalogEntry(
        asset_path=_single_row(3),
        is_dip=False, pin_count=3,
        name="GUVA-S12SD",
        pin_labels={1: "5V", 2: "Out", 3: "GND"},
    ),
    "i2c_multiplexer": CatalogEntry(
        asset_path=_dip(22),
        is_dip=True, pin_count=22,
        name="TCA9548A",
        pin_labels={
            1: "VCC", 2: "VCCIO", 3: "RESET", 4: "SDA", 5: "SCL", 6: "0SDA",
            7: "0SCL", 8: "1SDA", 9: "1SCL", 10: "2SDA", 11: "2SCL",
            12: "3SDA", 13: "3SCL", 14: "4SDA", 15: "4SCL", 16: "5SDA",
            17: "5SCL", 18: "6SDA", 19: "6SCL", 20: "7SDA", 21: "7SCL", 22: "GND",
        },
    ),
    "lps28": CatalogEntry(
        asset_path=_single_row(6),
        is_dip=False, pin_count=6,
        name="LPS28",
        pin_labels={1: "VCC", 2: "3.3V", 3: "SDA", 4: "SCL", 5: "INT", 6: "GND"},
    ),

    # ── Lot #5 (2026-08-19). À cette époque, `eink_display` et `gc9a01`
    # n'avaient PAS d'entrée ici (13 et 11 broches — non dessinables).
    # Depuis, TODO #58 (2026-08-20) leur a donné une entrée plus bas dans ce
    # fichier.
    "nau7802": CatalogEntry(
        asset_path=_dip(10),
        is_dip=True, pin_count=10,
        name="NAU7802",
        pin_labels={
            1: "VCC", 2: "AVDD", 3: "B+", 4: "B-", 5: "A+",
            6: "A-", 7: "SCL", 8: "SDA", 9: "DRDY", 10: "GND",
        },
    ),
    "sen5x": CatalogEntry(
        asset_path=_single_row(4),
        is_dip=False, pin_count=4,
        name="SEN5x",
        pin_labels={1: "VCC", 2: "SCL", 3: "SDA", 4: "GND"},
    ),

    # ── Bonus du même lot : brochage réel pour `touch_sensor`, déjà au
    # registre depuis 2026-08-12 mais `wiring="unknown"` faute de fiche
    # sourcée à l'époque. Fiche Fritzing AT42QT1010 (module momentané à un
    # seul pad), cohérente avec la description existante « TTP223 ou
    # équivalent » — LEDA est la sortie de rétroaction LED, pas une broche
    # d'alimentation.
    "touch_sensor": CatalogEntry(
        asset_path=_single_row(5),
        is_dip=False, pin_count=5,
        name="Touch",
        pin_labels={1: "LEDA", 2: "VDD", 3: "OUT", 4: "GND", 5: "CAPPAD"},
    ),

    # ── TODO #58 (2026-08-20) : les six composants que #57 avait laisses non
    # dessinables. Brochages releves sur les fiches Fritzing reelles par
    # scripts/fritzing_import.py.
    #
    # `stspin220` et `tmc2209` ne sont PAS impairs : ce sont des StepStick a
    # deux rangees, avec DEUX broches GND physiques (14 et 16 connecteurs
    # reels). Le "nombre impair" annonces au TODO etait un artefact du
    # de-doublonnage par libelle de l'outil d'import.
    "sharp_memory_display": CatalogEntry(
        asset_path=_single_row(9),
        is_dip=False, pin_count=9,
        name="Memory LCD",
        pin_labels={
            1: "VIN", 2: "3.3V", 3: "EXTIN", 4: "DISP", 5: "EXTMODE",
            6: "CS", 7: "MOSI", 8: "SCLK", 9: "GND",
        },
    ),
    "gc9a01": CatalogEntry(
        asset_path=_single_row(11),
        is_dip=False, pin_count=11,
        name="GC9A01",
        pin_labels={
            1: "VIN", 2: "+3V3", 3: "CARDCS", 4: "LITE", 5: "MISO", 6: "MOSI",
            7: "TFTRST", 8: "TFTDC", 9: "TFTCS", 10: "SCK", 11: "GND",
        },
    ),
    "winc1500": CatalogEntry(
        asset_path=_single_row(13),
        is_dip=False, pin_count=13,
        name="WINC1500",
        pin_labels={
            1: "+5V", 2: "GND", 3: "SCK", 4: "MISO", 5: "MOSI", 6: "CS",
            7: "EN", 8: "IRQ", 9: "RST", 10: "WAKE", 11: "CFG",
            12: "RXD", 13: "TXD",
        },
    ),
    "eink_display": CatalogEntry(
        asset_path=_single_row(13),
        is_dip=False, pin_count=13,
        name="E-Ink",
        pin_labels={
            1: "VIN", 2: "3.3V", 3: "SCLK", 4: "MISO", 5: "MOSI", 6: "DISPCS",
            7: "DC", 8: "SRAMCS", 9: "SDCS", 10: "RESET", 11: "BUSY",
            12: "ENABLE", 13: "GND",
        },
    ),
    "stspin220": CatalogEntry(
        asset_path=_dip(14),
        is_dip=True, pin_count=14,
        name="STSPIN220",
        pin_labels={
            1: "VMOTOR", 2: "VDD", 3: "OUTA1", 4: "OUTA2", 5: "OUTB1",
            6: "OUTB2", 7: "DIR", 8: "STEP", 9: "MS1", 10: "MS2",
            11: "ENABLE", 12: "RESET", 13: "GND", 14: "GND",
        },
    ),
    "tmc2209": CatalogEntry(
        asset_path=_dip(16),
        is_dip=True, pin_count=16,
        name="TMC2209",
        pin_labels={
            1: "VMOTOR", 2: "VDD", 3: "DIR", 4: "STEP", 5: "MS1", 6: "MS2",
            7: "DIAG", 8: "INDEX", 9: "UART", 10: "ENABLE", 11: "OUT2B",
            12: "OUT2A", 13: "OUT1A", 14: "OUT1B", 15: "GND", 16: "GND",
        },
    ),
}


def lookup(type_id: str) -> CatalogEntry | None:
    """Return the catalog entry for a type, or None if unknown.

    Single resolution point: builtin catalog first, then the user-declared
    library (`custom:` types). layout.py and the router see an ordinary
    CatalogEntry either way.
    """
    entry = CATALOG.get(type_id)
    if entry is not None:
        return entry
    return _declared_entry(type_id)


def _declared_entry(type_id: str) -> CatalogEntry | None:
    """CatalogEntry built from a user declaration, or None (unknown id, or a
    pin count the layout cannot draw). Reads the in-memory registry, never the
    disk: this module stays pure and tests stay deterministic."""
    from ...declared_components import TYPE_PREFIX, find_by_type
    if not type_id.startswith(TYPE_PREFIX):
        return None
    decl = find_by_type(type_id)
    if decl is None:
        return None
    n = len(decl.pins)
    factory_info = _GENERIC_BY_PIN_COUNT.get(n)
    if factory_info is None:
        return None
    factory, is_dip = factory_info
    asset_path = factory(n)
    if not asset_path.exists():
        return None
    return CatalogEntry(
        asset_path=asset_path,
        is_dip=is_dip,
        pin_count=n,
        name=decl.name,
        pin_labels={i + 1: p.label for i, p in enumerate(decl.pins)},
        pin_roles={i + 1: p.role for i, p in enumerate(decl.pins)},
    )


# ─── Electrical roles of the pins ───────────────────────────────────────

_VCC_LABELS = {"VCC", "5V", "3V3", "3.3V", "V+", "+"}
_GND_LABELS = {"GND", "-", "G"}


def _default_roles(pin_labels: dict[int, str]) -> dict[int, str]:
    """Infer conservative roles from the labels when pin_roles is empty:
    VCC/5V -> vcc, GND -> gnd, everything else -> signal."""
    out: dict[int, str] = {}
    for idx, label in pin_labels.items():
        up = (label or "").strip().upper()
        if up in _VCC_LABELS:
            out[idx] = "vcc"
        elif up in _GND_LABELS:
            out[idx] = "gnd"
        else:
            out[idx] = "signal"
    return out


def role_of(type_id: str, pin_index: int) -> str | None:
    """Role of the pin_index pin (1-based) of the type. Explicit pin_roles if
    present, otherwise derived from the labels. None if type/index unknown."""
    entry = lookup(type_id)          # was CATALOG.get(type_id)
    if entry is None:
        return None
    roles = entry.pin_roles or _default_roles(entry.pin_labels)
    return roles.get(pin_index)


# ─── Generic dispatcher: SVG by pin count ──────────────────────
# Allows rendering a component whose `type` is not in CATALOG by
# choosing the SVG asset from `pin_count`:
# - 2-8 pins (plus the odd 9, 11, 13 added by TODO #58, 2026-08-20):
#   single-row/{N}pins.svg (typically a module / sensor)
# - 10-40 pins (even): dip/{N}pins.svg (typically a DIP IC)
#
# For ambiguities (pin_count = 4, 6, 8 or a DIP asset also exists),
# we prefer single-row -- the most frequent use case (HC-SR04, LCD I2C
# 4 pins, etc.). The user can always add an explicit entry
# in CATALOG for a type they want to force as DIP.

# pin_count -> (factory_fn, is_dip)
_GENERIC_BY_PIN_COUNT: dict[int, tuple] = {
    n: (_single_row, False) for n in [*range(2, 9), 9, 11, 13]
}
_GENERIC_BY_PIN_COUNT.update({
    n: (_dip, True) for n in range(10, 41, 2)
})


def resolve_generic(type_id: str,
                     pins: list[dict] | list) -> CatalogEntry | None:
    """Build a generic CatalogEntry for an unknown type by
    choosing the SVG asset according to the number of pins provided in the
    netlist. Returns None if no asset is available.

    `pins`: list of the component's pins on the netlist side (dict form
    `{"name", "net"}` or `Pin` object). Used to determine pin_count and
    to build `pin_labels` positionally (1st pin -> pin-1 of the SVG).
    """
    pin_count = len(pins) if pins else 0
    factory_info = _GENERIC_BY_PIN_COUNT.get(pin_count)
    if factory_info is None:
        return None
    factory, is_dip = factory_info
    asset_path = factory(pin_count)
    if not asset_path.exists():
        return None
    # Positional mapping: extract the name of each pin from the netlist
    # (Pin object with .name attribute OR dict {"name": ...}).
    pin_labels: dict[int, str] = {}
    for i, p in enumerate(pins):
        if isinstance(p, dict):
            label = p.get("name") or str(i + 1)
        else:
            label = getattr(p, "name", None) or str(i + 1)
        pin_labels[i + 1] = label
    return CatalogEntry(
        asset_path=asset_path,
        is_dip=is_dip,
        pin_count=pin_count,
        # Fallback name only: the renderer resolves the curated short name
        # from `component_names` first, and truncates whatever lands here to
        # the real budget. So no blind cut at 10 characters, which used to
        # produce mid-word stumps like "IR_RECEIVE" and "LORA_SX127".
        name=type_id.replace("_", " "),
        pin_labels=pin_labels,
    )


# Horizontal variant of the resistor — used only when the R is
# paired with a main component (LED+R series, button+R pullup, dht+R pullup,
# buzzer+R series). The placement lays it across the central groove, pin 1
# on col 'd' and pin 2 on col 'g' (or reversed depending on mirror).
RESISTOR_HORIZONTAL = CatalogEntry(
    asset_path=_horizontal(2),
    is_dip=False, pin_count=2,
    is_horizontal=True,
    name="R",
    pin_labels={1: "A", 2: "B"},   # convention addendum + v1 inference
)


# ─── External battery voltage ranges ──────────────────────────────────
# Admissible voltage (Vmin, Vmax) for each (motor, driver) combination.
# The motor imposes the lower bound (= operating voltage), the driver
# imposes the upper bound (= max voltage supported by the H-bridge / interface).
# For a servo powered directly (no driver), key = ("servo", None).
#
# Sources:
#  - L298N        : VS  = 5–46 V (datasheet ST L298)
#  - L293D (DIP)  : VS2 = 4.5–36 V (datasheet TI L293)
#  - L293D module : 9–24 V (easyelecmodule PCB breakout, more restrictive
#                   than the chip because of the auxiliary components: flyback
#                   diodes, filtering cap, possible regulator)
#  - TB6612FNG    : VM  = 2.5–13.5 V (datasheet Toshiba)
#  - DRV8833      : VM  = 2.7–10.8 V (datasheet TI)
#  - ULN2003      : V+  = 5–30 V but 28BYJ-48 (5V stepper) limits to ~12 V
#  - A4988        : VMOT = 8–35 V (datasheet Allegro), NEMA17 typically 12 V
#  - Servo SG90/MG996R standard : 4.8–6 V
BATTERY_VOLTAGE_RANGES: dict[tuple[str, str | None], tuple[float, float]] = {
    # Direct servo (no driver)
    ("servo", None):                (4.8, 6.0),
    # DC motor + driver
    ("dc_motor", "l298n"):          (5.0, 46.0),
    ("dc_motor", "l293d"):          (4.5, 36.0),
    ("dc_motor", "l293d_module"):   (9.0, 24.0),
    ("dc_motor", "tb6612fng"):      (2.5, 13.5),
    ("dc_motor", "drv8833"):        (2.7, 10.8),
    # Stepper 28BYJ-48 + ULN2003 (practical range: 5 V nominal, 12 V max)
    ("stepper_motor", "uln2003"):   (5.0, 12.0),
    # NEMA17 + A4988
    ("nema17", "a4988"):            (8.0, 35.0),
}


def voltage_range_for_load(motor_type: str,
                            driver_type: str | None
                            ) -> tuple[float, float] | None:
    """Voltage range (Vmin, Vmax) for a (motor, driver) pair, or None
    if undocumented. driver_type=None for direct servo."""
    return BATTERY_VOLTAGE_RANGES.get((motor_type, driver_type))


def _format_voltage(v: float) -> str:
    """Display 5.0 -> '5', 4.8 -> '4.8', 13.5 -> '13.5'."""
    if v == int(v):
        return str(int(v))
    return f"{v:g}"


def format_voltage_range(vmin: float, vmax: float) -> str:
    """Display format: '5 – 12 V' or '4.8 – 6 V'."""
    return f"{_format_voltage(vmin)} – {_format_voltage(vmax)} V"
