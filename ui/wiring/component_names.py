"""Short display name drawn inside a component box on the schematic.

Pure module: no Qt, no disk access, no import of the wiring layout package.

Two tables, split on a mechanical and testable criterion -- "does this string
change with the language?" -- rather than on "is this a part number?", which
would need a judgement call (LDR and GPS are not part numbers, yet they do not
translate either).

The box tells the user WHAT TO PICK UP from the kit, which is what is printed
on the board. The full translated label ("temperature sensor DS18B20") is not
lost: it is already shown in the wiring instructions next to the schematic.
"""
from __future__ import annotations

# Widest string a component body can hold. Calibrated on the narrowest body
# (112 px for the single-row assets; DIP bodies are 124 px) at the font-size
# the assets declare (8px).
#
# This is an ASSUMED PROXY, not a measurement: the assets declare
# `font-size:8px` with NO `font-family`, so the actual font is whatever the
# rendering engine picks on that machine. A QFontMetrics assertion in a test
# would give false confidence with a font that is not production's. Confirmed
# by eye in QA procedure J instead; if a name still overflows there, lower this
# number and the guard test will catch every offender at once.
MAX_CHARS = 13

# The ellipsis appended by the fallback truncation. Counted INSIDE MAX_CHARS:
# the rendered string never exceeds MAX_CHARS, ellipsis included.
_ELLIPSIS = "…"


# Identical in all four languages: part numbers as printed on the board
# (DS18B20, MCP23017) and universal abbreviations (LDR, GPS, LED).
_UNIVERSAL_NAME: dict[str, str] = {
    "a4988": "A4988",
    "acs712": "ACS712",
    "adjd_s311": "ADJD-S311",
    "ads1115": "ADS1115",
    "adxl345": "ADXL345",
    "aht20": "AHT20",
    "amg8833": "AMG8833",
    "apds9960": "APDS9960",
    "as5600": "AS5600",
    # Brand plus a universal unit: identical in the four languages.
    "atlas_ph": "Atlas pH",
    "battery_external": "BAT",
    "bh1750": "BH1750",
    "bme280": "BME280",
    "bmp085": "BMP085",
    "bmp180": "BMP180",
    "bmp280": "BMP280",
    "bno055": "BNO055",
    "button": "BTN",
    "buzzer": "BUZ",
    "ccs811": "CCS811",
    "dfplayer": "DFPlayer",
    "dht11": "DHT11",
    "dht22": "DHT22",
    "drv2605": "DRV2605",
    "drv8825": "DRV8825",
    "drv8833": "DRV8833",
    "ds1307": "DS1307",
    "ds18b20": "DS18B20",
    "ds3231": "DS3231",
    "ds3234": "DS3234",
    # Universal sigle, same status as LDR: not a part number, but printed and
    # said the same way in all four languages.
    "force_sensor": "FSR",
    # Product names printed on the board, like Motor Shield below.
    "ftdi_basic": "FTDI Basic",
    "gps": "GPS",
    "ms5611": "MS5611",
    "gps_em406": "GPS EM-406",
    "gy-80": "GY-80",
    "gy-85": "GY-85",
    "gy-86": "GY-86",
    "gy-87": "GY-87",
    "grove_motor_driver": "Grove driver",
    "grove_oled_128x96": "Grove OLED",
    "esp8266": "ESP8266",
    "hc05": "HC-05",
    "hcsr04": "HC-SR04",
    # Two wiring ids, one chip: the box says what is printed on the board.
    "hmc5883": "HMC5883L",
    "hmc5883l": "HMC5883L",
    "hmc6352": "HMC6352",
    "ht16k33": "HT16K33",
    "hw-612": "HW-612",
    "hx711": "HX711",
    "ili9341": "ILI9341",
    # Universal sigle: "IMU" and "DOF" are used as-is in the four languages.
    "imu_6dof": "IMU 6DOF",
    "ina219": "INA219",
    "ina226": "INA226",
    "ina260": "INA260",
    "ina3221": "INA3221",
    "itg3200": "ITG-3200",
    # Loanword used as-is in fr/es/it: the string does not change with the
    # language, which is the table criterion.
    "joystick": "Joystick",
    "ky018": "KY-018",
    "l293d": "L293D",
    "l293d_module": "L293D Module",
    "l298n": "L298N",
    "l3g4200d": "L3G4200D",
    "lcd_i2c": "LCD",
    "ldr": "LDR",
    "led": "LED",
    # The MAX7219 is what is printed on the board; "LED matrix" is the
    # function, and belongs to the instructions, not to the box.
    "led_matrix": "MAX7219",
    # The family prefix is ours, not the chip's: the board says SX1276.
    "lora_sx1276": "SX1276",
    "lsm303": "LSM303",
    "mag3110": "MAG3110",
    "max17043": "MAX17043",
    "max1704x": "MAX1704x",
    "max30102": "MAX30102",
    "max31855": "MAX31855",
    "max6675": "MAX6675",
    "mcp23017": "MCP23017",
    "mcp41xxx": "MCP41xxx",
    "mcp42xxx": "MCP42xxx",
    "mcp4725": "MCP4725",
    "mcp9600": "MCP9600",
    "mcp9808": "MCP9808",
    "mfrc522": "MFRC522",
    "mhz19": "MH-Z19",
    "mq131": "MQ-131",
    "mq136": "MQ-136",
    "mq137": "MQ-137",
    "mq138": "MQ-138",
    "mq214": "MQ-214",
    "mq216": "MQ-216",
    "mq303a": "MQ-303A",
    "mq306a": "MQ-306A",
    "mq307a": "MQ-307A",
    "mq309a": "MQ-309A",
    "mhz14a": "MH-Z14A",
    "mhz1311a": "MH-Z1311A",
    "rcwl0516": "RCWL-0516",
    "rcwl1005": "RCWL-1005",
    "rcwl1605": "RCWL-1605",
    "jsn_sr04t": "JSN-SR04T",
    "mlx90614": "MLX90614",
    "mma8452q": "MMA8452Q",
    "module_generic": "MOD",
    # Product names, not functions to translate.
    "motor_shield_v2": "Motor Shield",
    "mpl3115a2": "MPL3115A2",
    "mpr121": "MPR121",
    "mpu6050": "MPU6050",
    "mpu9250": "MPU9250",
    "mq135": "MQ-135",
    "mq2": "MQ-2",
    "sim800l": "SIM800L",
    "nema17": "NEMA17",
    "neopixel": "NeoPixel",
    "nrf24l01": "nRF24L01",
    "oled_ssd1306": "OLED",
    "openlog": "OpenLog",
    "pca9685": "PCA9685",
    "pcd8544": "Nokia 5110",
    "pcf8574": "PCF8574",
    "pm25": "PMSA003I",
    "pn532": "PN532",
    "potentiometer": "POT",
    "resistor": "R",
    "scd30": "SCD30",
    # SparkFun product name, same status as Motor Shield above. "Sensor
    # Stick" alone was ambiguous in a kit -- SparkFun sold several sticks and
    # the box must say WHICH one to pick up; 9DOF is the identifying part.
    "sensor_stick_9dof": "9DOF Stick",
    "servo": "SRV",
    "sgp30": "SGP30",
    "sh1106": "SH1106",
    "sht15": "SHT15",
    "sht25": "SHT25",
    "si7021": "Si7021",
    "sr74hc595": "74HC595",
    "ssd1351": "SSD1351",
    "st7735": "ST7735",
    "st7789": "ST7789",
    "tb6612fng": "TB6612FNG",
    "tcs34725": "TCS34725",
    "tm1637": "TM1637",
    "tm1638": "TM1638",
    "tmp102": "TMP102",
    "uln2003": "ULN2003",
    "us100": "US-100",
    "vcnl4000": "VCNL4000",
    "veml6075": "VEML6075",
    "vl53l0x": "VL53L0X",
    "wiz820io": "WIZ820io",
    # ── Lot #2 "identite elargie" du 2026-08-19 (TODO #57, sous-chantier B) ──
    "tmp006": "TMP006",
    "tmp007": "TMP007",
    "si1145": "SI1145",
    "adt7410": "ADT7410",
    "ds3502": "DS3502",
    "fram": "FRAM",
    "mprls": "MPRLS",
    "hdc1008": "HDC1008",
    "adxl335": "ADXL335",
    "bluefruit_le": "Bluefruit LE",
    "spi_flash": "SPI Flash",
    "dotstar": "DotStar",
    "tsl2561": "TSL2561",
    "sharp_memory_display": "Memory LCD",
    "winc1500": "WINC1500",
    "tmp36": "TMP36",
    "flex_sensor": "Flex",
    "si4713": "SI4713",
    "ads7830": "ADS7830",
    "trellis": "Trellis",
    "ir_reflective_sensor": "QRE1113",
    # ── Lot #4 (2026-08-19) ──
    "mmc5603": "MMC5603",
    "hdc3021": "HDC3021",
    "ina228": "INA228",
    "opt4048": "OPT4048",
    "ina169": "INA169",
    "guva_s12sd": "GUVA-S12SD",
    "stspin220": "STSPIN220",
    "tmc2209": "TMC2209",
    "i2c_multiplexer": "TCA9548A",
    "lps28": "LPS28",
    # ── Lot #5 (2026-08-19) ──
    "eink_display": "E-Ink",
    "nau7802": "NAU7802",
    "sen5x": "SEN5x",
    "gc9a01": "GC9A01",
}

# Changes with the language. Only components with no designation printed on
# the board land here.
_LOCALIZED_NAME: dict[str, dict[str, str]] = {
    "buttonpad": {"fr": "Pavé boutons", "en": "Button pad",
                  "es": "Matriz bot.", "it": "Matrice puls."},
    "dc_motor": {"fr": "Moteur CC", "en": "DC motor",
                 "es": "Motor CC", "it": "Motore CC"},
    "dip_switch": {"fr": "Interr. DIP", "en": "DIP switch",
                   "es": "Int. DIP", "it": "Int. DIP"},
    "encoder": {"fr": "Encodeur", "en": "Encoder",
                "es": "Encoder", "it": "Encoder"},
    "fingerprint": {"fr": "Empreinte", "en": "Fingerprint",
                    "es": "Huella", "it": "Impronta"},
    "flame_sensor": {"fr": "Flamme", "en": "Flame",
                     "es": "Llama", "it": "Fiamma"},
    "grove_3axis_accel": {"fr": "Grove accél.", "en": "Grove accel.",
                          "es": "Grove acel.", "it": "Grove accel."},
    "hall_sensor": {"fr": "Capteur Hall", "en": "Hall sensor",
                    "es": "Sensor Hall", "it": "Sensore Hall"},
    "ir_receiver": {"fr": "Récepteur IR", "en": "IR receiver",
                    "es": "Receptor IR", "it": "Ricevitore IR"},
    "keypad": {"fr": "Clavier", "en": "Keypad",
               "es": "Teclado", "it": "Tastiera"},
    "led_matrix_rgb_spi": {"fr": "Matrice RGB", "en": "RGB matrix",
                           "es": "Matriz RGB", "it": "Matrice RGB"},
    "rain_sensor": {"fr": "Pluie", "en": "Rain",
                    "es": "Lluvia", "it": "Pioggia"},
    "sound_detector": {"fr": "Son", "en": "Sound",
                       "es": "Sonido", "it": "Suono"},
    "water_flow_sensor": {"fr": "Débit eau", "en": "Water flow",
                          "es": "Flujo agua", "it": "Flusso acqua"},
    "light_sensor": {"fr": "Capt. lumière", "en": "Light sensor",
                     "es": "Sensor de luz", "it": "Sens. luce"},
    "load_cell": {"fr": "Cell. charge", "en": "Load cell",
                  "es": "Célula carga", "it": "Cella carico"},
    "microphone": {"fr": "Micro", "en": "Microphone",
                   "es": "Micrófono", "it": "Microfono"},
    "microsd_card_module": {"fr": "Carte microSD", "en": "microSD card",
                            "es": "Tarj. microSD", "it": "Sch. microSD"},
    "passive_buzzer": {"fr": "Buzzer passif", "en": "Pass. buzzer",
                       "es": "Zumb. pasivo", "it": "Cicalino pas."},
    "pir": {"fr": "Détecteur PIR", "en": "PIR sensor",
            "es": "Sensor PIR", "it": "Sensore PIR"},
    "reed_switch": {"fr": "ILS (reed)", "en": "Reed switch",
                    "es": "Interr. reed", "it": "Interr. reed"},
    "relay": {"fr": "Relais", "en": "Relay",
              "es": "Relé", "it": "Relè"},
    "rgb_led": {"fr": "LED RGB", "en": "RGB LED",
                "es": "LED RGB", "it": "LED RGB"},
    "sd_card": {"fr": "Carte SD", "en": "SD card",
                "es": "Tarjeta SD", "it": "Scheda SD"},
    "slide_switch": {"fr": "Int. gliss.", "en": "Slide switch",
                     "es": "Int. desliz.", "it": "Int. scorr."},
    "slider": {"fr": "Pot. gliss.", "en": "Slide pot",
               "es": "Pot. desliz.", "it": "Pot. scorr."},
    "soil_moisture": {"fr": "Humidité sol", "en": "Soil moisture",
                      "es": "Humedad suelo", "it": "Umidità suolo"},
    "solenoid": {"fr": "Solénoïde", "en": "Solenoid",
                 "es": "Solenoide", "it": "Solenoide"},
    "speaker": {"fr": "Haut-parleur", "en": "Speaker",
                "es": "Altavoz", "it": "Altoparlante"},
    "stepper_motor": {"fr": "Pas-à-pas", "en": "Stepper",
                      "es": "Paso a paso", "it": "Passo-passo"},
    # EN reads as a NOUN: "Therm. print." was parseable as an imperative verb
    # on a box that names an object.
    "thermal_printer": {"fr": "Impr. therm.", "en": "Thermal ptr.",
                        "es": "Impr. térm.", "it": "Stamp. term."},
    "thermistor": {"fr": "Thermistance", "en": "Thermistor",
                   "es": "Termistor", "it": "Termistore"},
    "tilt_switch": {"fr": "Int. inclin.", "en": "Tilt switch",
                    "es": "Interr. tilt", "it": "Interr. tilt"},
    "toggle_switch": {"fr": "Int. levier", "en": "Toggle switch",
                      "es": "Int. palanca", "it": "Int. a leva"},
    "touch_sensor": {"fr": "Capt. tactile", "en": "Touch sensor",
                     "es": "Sensor táctil", "it": "Sens. tattile"},
}

_DEFAULT_LANG = "fr"


def fit(text: str) -> str:
    """Truncate `text` to MAX_CHARS, ellipsis included, so the rendered string
    never overflows the component body."""
    text = (text or "").strip()
    if len(text) <= MAX_CHARS:
        return text
    # rstrip so we never render "Mon capteur …" with a space before the
    # ellipsis when the cut happens to land on a word boundary.
    return text[:MAX_CHARS - 1].rstrip() + _ELLIPSIS


def _curated_name(component_type: str, lang: str) -> str:
    """Curated name for this type, "" when neither table knows it.

    Resolution order: universal table (a part number, identical in every
    language), then localized table. Both are curated to fit the box, so
    nothing coming out of here is ever truncated.
    """
    key = (component_type or "").strip()
    universal = _UNIVERSAL_NAME.get(key)
    if universal:
        return universal
    localized = _LOCALIZED_NAME.get(key)
    if localized:
        return localized.get(lang) or localized[_DEFAULT_LANG]
    return ""


def short_name(component_type: str, lang: str = _DEFAULT_LANG,
               fallback: str = "") -> str:
    """Name to DRAW inside the box of `component_type`.

    Curated name when there is one, else `fallback` (the catalog entry's own
    name -- a user-declared component carries a name typed by the user, which
    we cannot curate). The fallback is always truncated: a net that overflowed
    the day it is used would be no net at all.
    """
    return _curated_name(component_type, lang) or fit(fallback)


def full_name(component_type: str, lang: str = _DEFAULT_LANG,
              fallback: str = "") -> str:
    """Same name, NOT truncated -- what to show on hover.

    Differs from `short_name` only on the fallback path, which is exactly the
    case where the box had to elide and the user cannot read the whole name
    (QA J3, 2026-08-10). For a curated type the two are equal, and the caller
    is expected to skip the tooltip rather than repeat the visible text.
    """
    return _curated_name(component_type, lang) or (fallback or "").strip()


def known_types() -> set[str]:
    """Every type this module can name. Used by the guard test."""
    return set(_UNIVERSAL_NAME) | set(_LOCALIZED_NAME)
