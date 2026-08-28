"""SIGNAL category taxonomy for component replacement.

Additive layer (does NOT affect the per-prompt disambiguation maps in
markers.py). The category = what the sketch does to the pin: it's the join
key between a detected MCU signal and the set of components proposable for
replacement (same electrical class).
"""
from __future__ import annotations

# Core categories (bare-pin signals / bus)
SINGLE_OUTPUT = "single_output"
ANALOG_IN = "analog_in"
DIGITAL_IN = "digital_in"
I2C = "i2c"
SPI = "spi"
UART = "uart"
# Fixed-pinout families (unique signature, intra-family replacement)
SERVO = "servo"
ULTRASONIC = "ultrasonic"
ONEWIRE_TEMP = "onewire_temp"
MOTOR_DC = "motor_dc"
MOTOR_STEPPER = "motor_stepper"
# Infrastructure / inferred companions: never proposed for replacement.
# ⚠️ RESERVE A CE QUE L'APP AJOUTE ELLE-MEME (TODO #62) : la resistance de
# limitation, la pile, le driver deduit d'un moteur. L'utilisateur ne les a pas
# choisis, donc lui proposer de les remplacer n'aurait pas de sens.
NON_REPLACEABLE = "non_replaceable"

# Composant QUE L'UTILISATEUR POSSEDE, mais dont le bus est proprietaire et qui
# n'a donc PAS de pair d'echange dans le catalogue (TM1637 CLK/DIO, HX711
# DT/SCK, registre a decalage...).
#
# ⛔ CE N'EST PAS LA MEME CHOSE QUE `NON_REPLACEABLE`, et les confondre etait le
# defaut du TODO #62 : ces types etaient ranges avec l'infrastructure au motif
# ecrit << bus proprietaires sans pair de swap >>, autrement dit << on ne leur a
# pas trouve d'equivalent, donc on a interdit le geste >>. Consequence : si le
# detecteur se trompait sur un TM1637, l'utilisateur n'avait AUCUN recours --
# precisement dans le cas ou l'app avait eu tort.
#
# Ce que la separation change concretement : l'engrenage s'ouvre, et le picker
# montre le type courant + les echappatoires inter-categories + la bibliotheque
# de l'utilisateur + la recherche. Une liste de pairs vide se dit par une liste
# vide, pas par un engrenage muet.
NO_SWAP_PEER = "no_swap_peer"

# catalog type (or runtime-derived type) -> category
CATEGORY_OF_TYPE: dict[str, str] = {
    # single_output
    "led": SINGLE_OUTPUT,
    "buzzer": SINGLE_OUTPUT,
    "relay": SINGLE_OUTPUT,
    "neopixel": SINGLE_OUTPUT,  # LED strip: single DIN pin (markers.py:694)
    # analog_in
    "potentiometer": ANALOG_IN,
    "ldr": ANALOG_IN,
    "thermistor": ANALOG_IN,
    "microphone": ANALOG_IN,
    "mq135": ANALOG_IN,       # gas sensor: analog AOUT pin (markers.py:986)
    # digital_in
    "button": DIGITAL_IN,
    "pir": DIGITAL_IN,
    "ir_receiver": DIGITAL_IN,  # IR receiver: digital OUT pin (markers.py:876)
    "keypad": DIGITAL_IN,       # keypad matrix: digital ROW/COL pins (markers.py:867)
    "encoder": DIGITAL_IN,      # rotary encoder: digital CLK+DT pins (markers.py:728)
    # i2c
    "lcd_i2c": I2C,
    "oled_ssd1306": I2C,
    "module_generic": I2C,  # generic I2C fallback by construction (markers 2026-06-08, Wire sketch)
    "bme280": I2C,     # T/P/H sensor: SDA=A4 SCL=A5 (markers.py:662)
    "mpu6050": I2C,    # accelerometer/gyroscope: SDA=A4 SCL=A5 (markers.py:668)
    "ina219": I2C,     # current/voltage sensor: SDA=A4 SCL=A5 (markers.py:642)
    "ina226": I2C,     # idem ina219, lib INA226_WE (detection ajoutee, TODO #47)
    "grove_motor_driver": I2C,  # pilote entierement par I2C (TODO #47)
    "ccs811": I2C,     # air quality sensor: SDA=A4 SCL=A5 (markers.py:684)
    # spi
    "mfrc522": SPI,
    "sd_card": SPI,    # CS depuis SD.begin(), MOSI/MISO/SCK fixes (TODO #43/#47)
    "ili9341": SPI,
    "lora_sx1276": SPI,
    # uart
    "uart_module": UART,
    "gps": UART,    # GPS module via SoftwareSerial TX/RX (markers.py:911)
    "mhz19": UART,  # CO2 sensor via SoftwareSerial TX/RX (markers.py:920)
    # fixed families
    "servo": SERVO,
    "hcsr04": ULTRASONIC,
    # groups single-data-wire temp/humidity sensors (proprietary DHT + DS18B20 Dallas); best-effort substitution assumed
    "dht11": ONEWIRE_TEMP,
    "dht22": ONEWIRE_TEMP,
    "ds18b20": ONEWIRE_TEMP,
    "dc_motor": MOTOR_DC,
    "stepper_motor": MOTOR_STEPPER,
    "nema17": MOTOR_STEPPER,
    # infrastructure / inferred companions (not proposable)
    "resistor": NON_REPLACEABLE,
    "battery_external": NON_REPLACEABLE,
    "l298n": NON_REPLACEABLE,
    "l293d": NON_REPLACEABLE,
    "l293d_module": NON_REPLACEABLE,
    "uln2003": NON_REPLACEABLE,
    "a4988": NON_REPLACEABLE,
    "drv8825": NON_REPLACEABLE,  # same DIP-16 family as a4988 (TODO #57 pilot, 2026-08-19)
    "tb6612fng": NON_REPLACEABLE,
    "drv8833": NON_REPLACEABLE,
    # ─── Detector bundles #19 (categorized 2026-06-18, cf. spec) ────────────
    # Category derived from the pins ACTUALLY emitted by markers.py.
    # i2c: VCC/GND/SDA=A4/SCL=A5
    "ht16k33": I2C, "vl53l0x": I2C, "max30102": I2C, "tcs34725": I2C,
    "bh1750": I2C, "ads1115": I2C, "pca9685": I2C, "sh1106": I2C, "aht20": I2C,
    "bmp280": I2C, "apds9960": I2C, "sgp30": I2C, "scd30": I2C, "mcp23017": I2C,
    "mcp9808": I2C, "si7021": I2C, "hmc5883l": I2C, "mcp4725": I2C, "ina260": I2C,
    "as5600": I2C, "veml6075": I2C, "bno055": I2C, "mcp9600": I2C, "max17043": I2C,
    "amg8833": I2C, "drv2605": I2C,
    "pn532": I2C,   # + IRQ/RST: extras dropped by the swap engine
    "pm25": I2C,    # I2C variant PMSA003I (emitted pins SDA/SCL), not the UART PMS5003
    # spi
    "ssd1351": SPI, "st7735": SPI, "st7789": SPI, "max31855": SPI, "pcd8544": SPI,
    # uart (VCC/GND/TX/RX via SoftwareSerial)
    "dfplayer": UART, "fingerprint": UART,
    # Bus proprietaires SANS pair d'echange. Classes NON_REPLACEABLE le
    # 2026-06-18, RECLASSES le 2026-08-26 (TODO #62) : ils appartiennent a
    # l'utilisateur, donc ils restent corrigeables meme sans pair.
    "led_matrix": NO_SWAP_PEER,   # MAX7219 DIN/CLK/CS
    "tm1637": NO_SWAP_PEER,       # CLK/DIO 2-wire
    "tm1638": NO_SWAP_PEER,       # STB/CLK/DIO
    "hx711": NO_SWAP_PEER,        # DT/SCK 2-wire (strain gauge bridge)
    "sr74hc595": NO_SWAP_PEER,    # DATA/CLK/LATCH (shift register)

    # ─── Lot #2 "identite elargie" du 2026-08-19 (TODO #57, sous-chantier B).
    # Aucun de ces types n'est emis par markers.py (pas de detection cablage
    # pour ce lot) : jamais proposes en pratique par le moteur de swap. Cette
    # section satisfait juste le garde-fou test_every_catalog_type_has_a_category
    # -- affectee par la forme electrique reelle du brochage Fritzing.
    "tmp006": I2C, "tmp007": I2C, "si1145": I2C, "adt7410": I2C,
    "ds3502": I2C, "fram": I2C, "mprls": I2C, "hdc1008": I2C,
    "tsl2561": I2C, "trellis": I2C, "si4713": I2C, "ads7830": I2C,
    "spi_flash": SPI,
    "bluefruit_le": UART,  # RXI/TXO : variante UART du module (il en existe aussi une SPI)
    "tmp36": ANALOG_IN, "flex_sensor": ANALOG_IN,
    # ADXL335 (3 sorties analogiques X/Y/Z distinctes) et DotStar (protocole
    # LED proprietaire 2 fils, comme le NeoPixel) : aucune forme de swap peer
    # dans les categories existantes -- meme traitement que tm1637/hx711 ci-dessus.
    "adxl335": NO_SWAP_PEER, "dotstar": NO_SWAP_PEER,
    # A/C/E/K : deux composants optiques distincts dans un boitier, meme
    # raisonnement que adxl335/dotstar ci-dessus.
    "ir_reflective_sensor": NO_SWAP_PEER,

    # ── Lot #4 (2026-08-19). stspin220/tmc2209 n'avaient pas d'entree
    # catalogue a cette epoque. Depuis, TODO #58 (2026-08-20) leur en a
    # donne une (14 et 16 broches reelles, avec GND×2) et une categorie
    # ci-dessous.
    "mmc5603": I2C, "hdc3021": I2C, "ina228": I2C, "opt4048": I2C,
    "i2c_multiplexer": I2C, "lps28": I2C,
    "ina169": ANALOG_IN, "guva_s12sd": ANALOG_IN,

    # ── Lot #5 (2026-08-19). eink_display/gc9a01 n'avaient pas d'entree
    # catalogue a cette epoque (non dessinables). Depuis, TODO #58
    # (2026-08-20) leur en a donnee une (13 broches, rangee simple) et une
    # categorie ci-dessous.
    "nau7802": I2C, "sen5x": I2C,

    # ── TODO #58 (2026-08-20). Obligatoire des qu'un type a une entree
    # catalogue (test_every_catalog_type_has_a_category).
    # Les quatre premiers sont des peripheriques SPI (SCK/MOSI/CS visibles
    # dans leur brochage) ; les deux drivers pas-a-pas rejoignent leurs
    # freres a4988/drv8825, deja NON_REPLACEABLE.
    "sharp_memory_display": SPI, "gc9a01": SPI,
    "winc1500": SPI, "eink_display": SPI,
    "stspin220": NON_REPLACEABLE, "tmc2209": NON_REPLACEABLE,
}


def category_of(type_id: str) -> str | None:
    """Category of a type, or None if the type is unknown to the taxonomy."""
    return CATEGORY_OF_TYPE.get(type_id)


def candidates_in(category: str) -> list[str]:
    """All types proposable for replacement within a category.
    NON_REPLACEABLE always returns [] (infrastructure never proposed)."""
    if category == NON_REPLACEABLE:
        return []
    return sorted(t for t, c in CATEGORY_OF_TYPE.items() if c == category)  # sorted alphabetically by type


# ─── Merge of the curated Fritzing Tier-1 catalog (SP3) ─────────────────
# Strictly one-way import (replacement_catalog imports nothing from here)
# to avoid any cycle. The entries broaden the variety proposable for
# replacement; known collisions already SKIP on the table side.
from .replacement_catalog import merge_into as _merge_replacement_catalog
_merge_replacement_catalog(CATEGORY_OF_TYPE)
