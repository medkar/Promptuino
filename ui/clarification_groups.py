"""Multi-family ambiguity groups for clarification BEFORE generation.

When a vague prompt matches a group (>=2 components that do the same thing,
with different wiring/lib), we ask the user which chip via
`LibClarificationDialog`, then force the chosen lib into the RAG context
(cf. `rag.detect_lib_ambiguity`).

CURATED approach — explicit keywords → ordered candidates (+ most common first),
mirroring the wiring disambiguation lexicons (`markers._*_KEYWORDS`). The RAG's
auto-by-scores remains a SAFETY NET for prompts not covered here.

Each `ClarifyCandidate` carries:
  - `corpus_id`: join to corpus.json (for `forced_libs`);
  - `label`    : short chip-name-oriented label, shown in the modal;
  - `svg_type` : catalog type hint for a future real SVG (or None →
                 generic placeholder).

Extensibility: adding a component to a family = ONE line in the right
group (single-candidate groups tolerated, dormant until the 2nd). Forcing function:
`scripts/test_clarification_groups.py` checks that every `corpus_id` exists in
corpus.json + lists the uncovered components of the ambiguous categories.

⚠️ DELIBERATELY out of scope: GPIO-controlled motors/drivers (L298N, L293D,
DRV8833, TB6612, A4988…) — resolved by motor detection + the WIRING ambiguity
modal, downstream. Do not create a GPIO "motor" group here (double modal).
EXCEPTION — I2C-controlled motor drivers DO get a group ("moteur_i2c"): unlike
GPIO drivers (identical analogWrite/digitalWrite code regardless of the chip),
each I2C board needs its specific library injected into the generation context,
which ONLY this curated path provides. Its keywords are kept I2C-specific so the
plain GPIO "moteur DC" prompt keeps its current (no-modal) path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ClarifyCandidate:
    corpus_id: str
    label: str
    svg_type: str | None = None


@dataclass(frozen=True)
class ClarifyGroup:
    key: str
    keywords: tuple[str, ...]
    candidates: tuple[ClarifyCandidate, ...]


def _c(corpus_id: str, label: str, svg_type: str | None = None) -> ClarifyCandidate:
    return ClarifyCandidate(corpus_id, label, svg_type)


# Order = from MOST specific to MOST general: `match_group` returns the 1st
# group whose keyword matches. Pairs with overlapping keywords
# MUST respect this order (e.g. "co2" before "qualité de l'air"; "thermocouple"
# and "sans contact" before "température"; "7 segments" before "écran").
CLARIFY_GROUPS: tuple[ClarifyGroup, ...] = (
    # ── CO₂ (subset of air quality → declared before) ───────────
    ClarifyGroup(
        "co2",
        ("co2", "co₂", "dioxyde de carbone", "carbon dioxide", "dioxido de carbono",
         "anidride carbonica", "ppm co2"),
        (_c("scd30", "SCD30 (NDIR)"), _c("mhz19", "MH-Z19 (NDIR)"),
         _c("adafruit-ccs811", "CCS811 (eCO2)"), _c("sgp30", "SGP30 (eCO2)")),
    ),
    # ── Air quality / gas ────────────────────────────────────────────
    ClarifyGroup(
        "air_quality",
        ("qualite de l'air", "qualite air", "qualité de l'air", "qualité air",
         "pollution", "capteur de gaz", "capteur gaz", "air quality", "gas sensor",
         "calidad del aire", "sensor de gas", "qualita dell'aria", "sensore di gas",
         "cov", "voc", "particules", "pm2.5", "pm25"),
        (_c("mq135", "MQ-135"), _c("adafruit-ccs811", "CCS811"),
         _c("sgp30", "SGP30"), _c("scd30", "SCD30"),
         _c("mhz19", "MH-Z19"), _c("pm25", "PMSA003I (PM2.5)")),
    ),
    # ── Thermocouple / high temperature (before "température") ─────────────
    ClarifyGroup(
        "thermocouple",
        ("thermocouple", "type k", "type-k", "haute temperature", "haute température",
         "four", "thermocouples", "termopar", "termocoppia"),
        (_c("max6675", "MAX6675 (type K)"), _c("max31855", "MAX31855"),
         _c("mcp9600", "MCP9600 (I2C)")),
    ),
    # ── Non-contact / infrared temperature (before "température") ────────
    ClarifyGroup(
        "ir_temp",
        ("sans contact", "sans-contact", "infrarouge", "temperature sans contact",
         "température sans contact", "non-contact", "non contact temperature",
         "infrared temperature", "camera thermique", "caméra thermique",
         "thermal camera", "sin contacto", "senza contatto"),
        (_c("mlx90614", "MLX90614 (point)"), _c("amg8833", "AMG8833 (caméra 8×8)")),
    ),
    # ── Humidity (keywords disjoint from "température") ───────────────────
    ClarifyGroup(
        "humidite",
        ("humidite", "humidité", "hygrometrie", "hygrométrie", "humidity",
         "humedad", "umidita", "umidità"),
        (_c("dht-sensor-library", "DHT22", "dht22"),
         _c("adafruit-bme280", "BME280/VMA335", "bme280"),
         _c("aht20", "AHT20"), _c("si7021", "Si7021")),
    ),
    # ── Pressure / barometer / altitude ───────────────────────────────────
    ClarifyGroup(
        "pression",
        ("pression", "barometre", "baromètre", "barometrique", "barométrique",
         "altitude", "pressure", "barometric", "altimeter", "presion", "presión",
         "pressione", "altimetro"),
        (_c("bmp280", "BMP280"), _c("adafruit-bme280", "BME280/VMA335 (+ humidité)", "bme280")),
    ),
    # ── Temperature (ambient) ─────────────────────────────────────────────
    ClarifyGroup(
        "temperature",
        ("temperature", "température", "thermometre", "thermomètre",
         "capteur de temperature", "capteur de température", "temperature sensor",
         "thermometer", "temperatura", "termometro", "termómetro"),
        (_c("dht-sensor-library", "DHT22 (+ humidité)", "dht22"),
         _c("dallas-temperature", "DS18B20 (1-Wire)", "ds18b20"),
         _c("adafruit-bme280", "BME280/VMA335 (+ pression/humidité)", "bme280"),
         _c("aht20", "AHT20 (+ humidité)"),
         _c("si7021", "Si7021 (+ humidité)"),
         _c("mcp9808", "MCP9808 (haute précision)")),
    ),
    # ── LED matrix (keywords disjoint from "écran") ───────────────────
    ClarifyGroup(
        "matrice_led",
        ("matrice de led", "matrice led", "matrice à led", "matrice de leds",
         "led matrix", "matriz de led", "matriz led", "matrice di led",
         "dot matrix", "8x8"),
        (_c("led_matrix", "MAX7219 (SPI)"), _c("ht16k33", "HT16K33 (I2C)")),
    ),
    # ── 7-segment display (before "écran": shares "afficheur") ────────
    ClarifyGroup(
        "sept_segments",
        ("7 segments", "sept segments", "afficheur 7 segments", "afficheur numerique",
         "afficheur numérique", "digits", "7-segment", "seven segment",
         "siete segmentos", "sette segmenti"),
        (_c("tm1637", "TM1637"), _c("ht16k33", "HT16K33 (backpack)"),
         _c("tm1638", "TM1638 (LED&KEY)"), _c("led_matrix", "MAX7219")),
    ),
    # ── Screen / display (general) ───────────────────────────────────────
    ClarifyGroup(
        "ecran",
        ("ecran", "écran", "afficheur", "display", "oled", "lcd", "tft",
         "pantalla", "schermo", "visualizzazione"),
        (_c("adafruit-ssd1306", "OLED SSD1306 (I2C)", "oled_ssd1306"),
         _c("sh1106", "OLED SH1106 (I2C)"),
         _c("liquidcrystal-i2c", "LCD I2C 16×2", "lcd_i2c"),
         _c("pcd8544", "Nokia 5110 (LCD)"),
         _c("adafruit-ili9341", "TFT ILI9341", "ili9341"),
         _c("st7735", "TFT ST7735"),
         _c("st7789", "TFT ST7789"),
         _c("ssd1351", "OLED RGB SSD1351"),
         _c("tm1638", "TM1638 (LED&KEY)")),
    ),
    # ── Distance / proximity ──────────────────────────────────────────────
    ClarifyGroup(
        "distance",
        ("distance", "telemetre", "télémètre", "proximite", "proximité",
         "capteur de distance", "distance sensor", "rangefinder", "proximity",
         "distancia", "distanza", "obstacle"),
        (_c("newping", "HC-SR04 (ultrason)", "hcsr04"),
         _c("vl53l0x", "VL53L0X (laser ToF)"),
         _c("apds9960", "APDS9960 (proximité courte)")),
    ),
    # ── Luminosity / light (sensor — NOT bare "lumière"/"light") ─────────
    ClarifyGroup(
        "luminosite",
        ("luminosite", "luminosité", "capteur de lumiere", "capteur de lumière",
         "lux", "light sensor", "ambient light", "light level", "niveau de lumiere",
         "niveau de lumière", "sensor de luz", "sensore di luce"),
        (_c("bh1750", "BH1750 (lux)"), _c("ldr", "LDR (photorésistance)", "ldr")),
    ),
    # ── Color ───────────────────────────────────────────────────────────
    ClarifyGroup(
        "couleur",
        ("capteur de couleur", "capteur couleur", "couleur", "color sensor",
         "colour", "rgb sensor", "sensor de color", "sensore di colore"),
        (_c("adafruit-tcs34725", "TCS34725"), _c("apds9960", "APDS9960")),
    ),
    # ── UV (1 candidate today → dormant, declared for extensibility) ─
    ClarifyGroup(
        "uv",
        ("ultraviolet", "rayons uv", "indice uv", "uv index", "uv sensor",
         "radiacion uv", "raggi uv"),
        (_c("veml6075", "VEML6075"),),
    ),
    # ── Accelerometer / gyroscope / IMU / motion ───────────────────────
    ClarifyGroup(
        "imu",
        ("accelerometre", "accéléromètre", "gyroscope", "gyro", "imu", "centrale inertielle",
         "inclinaison", "mouvement", "accelerometer", "tilt", "motion sensor",
         "acelerometro", "giroscopio", "accelerometro"),
        (_c("adafruit-mpu6050", "MPU6050 (accel+gyro)"),
         _c("mpu9250", "MPU9250 (9 axes)"),
         _c("adxl345", "ADXL345 (accel)"),
         _c("bno055", "BNO055 (9 axes fusionnés)")),
    ),
    # ── Compass / magnetometer ───────────────────────────────────────────
    ClarifyGroup(
        "boussole",
        ("boussole", "compass", "magnetometre", "magnétomètre", "champ magnetique",
         "champ magnétique", "magnetometer", "brujula", "brújula", "bussola"),
        (_c("hmc5883l", "HMC5883L"), _c("bno055", "BNO055 (9 axes)")),
    ),
    # ── Angle / rotation (input) ─────────────────────────────────────────
    ClarifyGroup(
        "angle",
        ("encodeur", "encodeur rotatif", "encoder", "rotary encoder", "capteur d'angle",
         "angle sensor", "position angulaire", "codificador", "encoder rotativo"),
        (_c("encoder", "Encodeur rotatif (incrémental)"),
         _c("as5600", "AS5600 (magnétique absolu)")),
    ),
    # ── RFID / NFC ────────────────────────────────────────────────────────
    ClarifyGroup(
        "rfid",
        ("rfid", "nfc", "badge", "lecteur de carte", "tag rfid", "card reader",
         "lector rfid", "lettore rfid"),
        (_c("mfrc522", "MFRC522 (RC522)"), _c("pn532", "PN532")),
    ),
    # ── Current / voltage / power ─────────────────────────────────────
    ClarifyGroup(
        "courant",
        ("courant", "consommation", "mesure de tension", "puissance electrique",
         "puissance électrique", "current sensor", "power monitor", "voltage monitor",
         "consumo", "medir corriente", "misura di corrente", "wattmetre", "wattmètre"),
        (_c("adafruit-ina219", "INA219"), _c("ina226-we", "INA226"),
         _c("ina260", "INA260"), _c("adafruit-ina3221", "INA3221 (3 voies)")),
    ),
    # ── I/O expander (port expander) ───────────────────────────────────
    ClarifyGroup(
        "io_expander",
        ("expandeur", "port expander", "expanseur", "broches supplementaires",
         "broches supplémentaires", "io expander", "gpio expander", "expansor",
         "expander di io"),
        (_c("pcf8574", "PCF8574"), _c("mcp23017", "MCP23017 (16 broches)")),
    ),
    # ── Clock / time ───────────────────────────────────────────────────
    ClarifyGroup(
        "horloge",
        ("horloge", "rtc", "heure", "date et heure", "temps reel", "temps réel",
         "real time clock", "clock module", "reloj", "orologio"),
        (_c("rtclib", "RTC DS3231 / DS1307 (module)"),
         _c("ntpclient", "NTP (heure réseau / WiFi)")),
    ),
    # ── Wireless / radio ──────────────────────────────────────────────────
    ClarifyGroup(
        "sans_fil",
        ("longue portee", "longue portée", "radio", "transmission sans fil",
         "liaison sans fil", "wireless link", "long range", "rf module",
         "radiofrecuencia", "senza fili"),
        (_c("lora", "LoRa (SX127x)"), _c("nrf24l01", "nRF24L01")),
    ),
    # ── Data storage (borderline, requested) ─────────────────────────
    ClarifyGroup(
        "stockage",
        ("carte sd", "enregistrer des donnees", "enregistrer des données",
         "stocker des donnees", "stocker des données", "data logging", "datalogger",
         "sd card", "save data", "almacenar datos", "memorizzare dati"),
        (_c("sd", "Carte SD / microSD"), _c("eeprom", "EEPROM interne (MCU)")),
    ),
    # ── Play a sound (audio output — borderline, requested) ─────────────────
    # OUTPUT-ORIENTED keywords (jouer/play + audio/musique/mp3): we avoid
    # bare "son"/"sound" and "capteur de son" (= microphone, handled at wiring).
    ClarifyGroup(
        "audio_out",
        ("jouer un son", "joue un son", "jouer de la musique", "musique", "mp3",
         "haut-parleur", "play sound", "play a sound", "play music", "audio",
         "speaker", "reproducir sonido", "riprodurre suono"),
        (_c("dfplayer", "DFPlayer Mini (MP3, haut-parleur)"),
         _c("buzzer", "Buzzer / piézo (bips, mélodies simples)", "buzzer")),
    ),
    # ── I2C-controlled motor driver (EXCEPTION to the "no motor group" rule;
    #    see module docstring). Triggered by the keywords below OR by the
    #    motor-word + I2C/Grove cue co-occurrence (see _is_i2c_motor). A plain
    #    GPIO "moteur DC" prompt has no cue -> does NOT trigger (no double modal).
    ClarifyGroup(
        "moteur_i2c",
        ("moteur i2c", "moteur en i2c", "driver moteur i2c", "moteur dc i2c",
         "i2c motor", "i2c motor driver", "motor i2c", "motore i2c",
         "grove motor", "grove i2c motor", "motor shield i2c", "shield moteur i2c"),
        (_c("grove-i2c-motor-driver", "Grove I2C Motor Driver (L298, 0x0F)"),
         _c("adafruit-motorshield-v2", "Adafruit Motor Shield V2 (I2C)")),
    ),
)


_GROUP_BY_KEY = {g.key: g for g in CLARIFY_GROUPS}

# I2C-motor co-occurrence: the curated keywords above can't enumerate every
# phrasing ("deux moteurs DC en i2c", "moteur ... driver i2c", "moteur grove",
# "shield grove"…). A motor word + an I2C/Grove cue is a robust, language-light
# signal for the I2C motor family. A plain GPIO "moteur DC" (no cue) stays out.
_MOTOR_WORDS = ("moteur", "moteurs", "motor", "motors", "motore", "motori")
_I2C_MOTOR_CUES = ("i2c", "i²c", "0x0f", "grove", "seeed")


def _mentions_motor(text: str) -> bool:
    return any(re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE)
               for w in _MOTOR_WORDS)


def _is_i2c_motor(text: str) -> bool:
    """True if the prompt mentions a motor AND an I2C/Grove cue → routes
    natural phrasings to the `moteur_i2c` family even when no exact keyword
    phrase matched. Plain GPIO "moteur DC" has no cue → returns False."""
    if not text or not _mentions_motor(text):
        return False
    t = text.lower()
    return any(cue in t for cue in _I2C_MOTOR_CUES)


def _has_keyword(text: str, keywords: tuple[str, ...]) -> bool:
    """True if one of the keywords appears as a complete word/expression
    (case-insensitive). Same convention as `markers._has_keyword`."""
    if not text:
        return False
    for kw in keywords:
        if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE):
            return True
    return False


def match_group(prompt: str) -> ClarifyGroup | None:
    """First group (declaration order = specific→general) whose
    keyword matches the prompt, or None."""
    if not prompt or not prompt.strip():
        return None
    for g in CLARIFY_GROUPS:
        if _has_keyword(prompt, g.keywords):
            return g
    # Robust I2C-motor fallback (motor word + I2C/Grove cue), no exact phrase.
    if _is_i2c_motor(prompt):
        return _GROUP_BY_KEY.get("moteur_i2c")
    return None


def match_all_groups(prompt: str) -> list[ClarifyGroup]:
    """ALL the groups (declaration order) whose keyword matches the prompt.

    Serves MULTI-FAMILY clarification: a prompt « température + écran »
    matches `temperature` AND `ecran`. Unlike `match_group` (1st
    only), we return them all. The de-duplication of concepts with overlapping
    keywords but designating the SAME need (e.g. « co2 » also matches
    `air_quality`, which shares SCD30/MH-Z19…) is done DOWNSTREAM by
    `rag.detect_lib_ambiguities` (disjoint candidates) — here we only do the
    raw lexical matching."""
    if not prompt or not prompt.strip():
        return []
    matched = [g for g in CLARIFY_GROUPS if _has_keyword(prompt, g.keywords)]
    # Robust I2C-motor fallback (motor word + I2C/Grove cue), no exact phrase.
    i2c = _GROUP_BY_KEY.get("moteur_i2c")
    if i2c is not None and i2c not in matched and _is_i2c_motor(prompt):
        matched.append(i2c)
    return matched


def functions_of_component(type_id: str) -> set[str]:
    """Cles des familles fonctionnelles auxquelles ce composant appartient.
    Robuste a l'espace d'identifiants : matche le TYPE WIRING (svg_type sinon
    corpus_id) OU le corpus_id. Vide si aucune (composant generique)."""
    return {g.key for g in CLARIFY_GROUPS
            if any(type_id in ((c.svg_type or c.corpus_id), c.corpus_id)
                   for c in g.candidates)}


_WIRING_TYPE_CACHE: dict[str, str] | None = None


def _wiring_type_by_document() -> dict[str, str]:
    """`{id de document corpus -> id du composant}`, DERIVE du registre.

    Le registre porte deja cette correspondance (`Component.documents`) : c'est
    la meme table que `markers._header_type_alias` exploite pour nommer une
    boite d'apres ce que l'app connait plutot que d'apres un nom de fichier.
    La lire ici evite d'ecrire a la main six equivalences qui derivteraient.
    """
    global _WIRING_TYPE_CACHE
    if _WIRING_TYPE_CACHE is None:
        from .component_registry import REGISTRY
        _WIRING_TYPE_CACHE = {doc: c.id for c in REGISTRY
                              for doc in (c.documents or ())}
    return _WIRING_TYPE_CACHE


def candidates_of_function(key: str) -> list[str]:
    """Types WIRING des candidats d'une famille, dans l'ordre du groupe.
    Vide si la cle n'existe pas.

    ⚠️ LE REPLI SUR `corpus_id` ETAIT UN BUG (TODO #67). Sept candidats n'ont
    pas de `svg_type`, et le repli sortait alors leur identifiant de CORPUS --
    `adafruit-mpu6050`, `adafruit-ccs811`, `ina226-we`... -- comme s'il
    s'agissait d'un type de cablage. Aucun n'en est un : ils n'ont donc aucune
    categorie, et le moteur de remplacement les refusait. 13 choix morts,
    proposes a l'utilisateur.

    Le registre connaissait pourtant la reponse : `adafruit-mpu6050` est le
    document du composant `mpu6050`, qui EST un type de cablage. Six des sept
    se resolvent ainsi ; le septieme, `adafruit-ina3221`, designe un composant
    qui n'a reellement aucun dessin, et le predicat `can_replace_with` l'ecarte
    en aval.
    """
    for g in CLARIFY_GROUPS:
        if g.key == key:
            par_doc = _wiring_type_by_document()
            return [(c.svg_type or par_doc.get(c.corpus_id) or c.corpus_id)
                    for c in g.candidates]
    return []


def functions_in_prompt(prompt: str) -> list[str]:
    """Cles des familles fonctionnelles matchees par le prompt (via les
    memes mots-cles que la clarification)."""
    return [g.key for g in match_all_groups(prompt)]


def corpus_id_of_type(type_id: str) -> str | None:
    """corpus_id d'un type WIRING (inverse de 'svg_type or corpus_id'). None si
    le type n'appartient a aucune famille fonctionnelle."""
    for g in CLARIFY_GROUPS:
        for c in g.candidates:
            if type_id in ((c.svg_type or c.corpus_id), c.corpus_id):
                return c.corpus_id
    return None
