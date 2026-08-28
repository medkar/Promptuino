"""Parser for AI wiring markers + static fallback.

Marker format (see docs/WIRING_DIAGRAM.md §3):

    /* <<< fn-1_wiring >>>
    component: led ; ref: D1 ; color: red ; pins: A=D13, K=GND
    component: resistor ; ref: R1 ; value: 220 ; pins: A=D13, B=GND ; role: series
    <<< end >>> */

If the AI does not emit the block, `parse_fallback()` reconstructs an
approximate netlist from `pinMode`/`digitalWrite`/`analogRead`/`Servo`/etc.
"""
from __future__ import annotations

import re
from typing import Iterable

from .netlist import Component, Netlist, Pin, SEVERITY_INFO
from .categories import category_of
from ..hardware_modules import detect_module


# ─── AI markers ──────────────────────────────────────────────────────────
# Complete block: /* <<< fn-1_wiring >>> ... <<< end >>> */
# Tolerant to whitespace variations; case-insensitive for <<< end >>>.
_WIRING_BLOCK_RE = re.compile(
    r"/\*\s*<<<\s*fn-(?P<fid>\d+)_wiring\s*>>>"
    r"(?P<body>.*?)"
    r"<<<\s*end\s*>>>\s*\*/",
    re.IGNORECASE | re.DOTALL,
)


def _parse_kv_pairs(segment: str) -> dict[str, str]:
    """Split `a=1 ; b=2 ; pins: x=y, z=w` into dict[str, str].

    Tolerant to the ` ; `, `;`, `; ` delimiters and to whitespace around `=`.
    """
    out: dict[str, str] = {}
    for chunk in re.split(r"\s*;\s*", segment.strip()):
        if not chunk:
            continue
        if ":" in chunk:
            k, _, v = chunk.partition(":")
        elif "=" in chunk:
            k, _, v = chunk.partition("=")
        else:
            continue
        out[k.strip().lower()] = v.strip()
    return out


def _parse_pins_field(value: str) -> list[Pin]:
    """`A=D13, K=GND` -> [Pin(A, D13), Pin(K, GND)]."""
    pins: list[Pin] = []
    for chunk in re.split(r"\s*,\s*", value.strip()):
        if not chunk or "=" not in chunk:
            continue
        name, _, net = chunk.partition("=")
        pins.append(Pin(name=name.strip(), net=net.strip()))
    return pins


def _parse_component_line(line: str, fn_id: str) -> Component | None:
    """Parse a `component: ... ; pins: ...` line.

    Returns None if the line is unusable (missing component).
    """
    if "component" not in line.lower():
        return None
    kv = _parse_kv_pairs(line)
    ctype = kv.pop("component", "").strip()
    if not ctype:
        return None
    ref = kv.pop("ref", "").strip()
    pins_field = kv.pop("pins", "")
    pins = _parse_pins_field(pins_field) if pins_field else []
    # Everything left over is a free attribute (color, value, role, etc.).
    return Component(
        ref=ref or "?",
        type=ctype,
        pins=pins,
        attributes={k: v for k, v in kv.items()},
        fn_id=fn_id,
    )


def parse_wiring_blocks(code: str) -> dict[str, list[Component]]:
    """Extract the components declared per feature.

    Returns {fn_id: [Component, ...]}. fn_id of the form "fn-1", "fn-2".
    Duplicate refs within the block are preserved (the orchestrator
    re-numbers them as needed when integrating into the global netlist).
    """
    out: dict[str, list[Component]] = {}
    for m in _WIRING_BLOCK_RE.finditer(code):
        fid = f"fn-{m.group('fid')}"
        body = m.group("body")
        comps: list[Component] = []
        for line in body.splitlines():
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            c = _parse_component_line(line, fid)
            if c is not None:
                comps.append(c)
        if comps:
            out.setdefault(fid, []).extend(comps)
    return out


# ─── Fallback parser (regex over the Arduino code) ──────────────────────────
_PINMODE_RE       = re.compile(r"\bpinMode\s*\(\s*([A-Za-z0-9_]+)\s*,\s*(INPUT_PULLUP|INPUT|OUTPUT)\s*\)")
_DIGITAL_WRITE_RE = re.compile(r"\bdigitalWrite\s*\(\s*([A-Za-z0-9_]+)\s*,")
_DIGITAL_READ_RE  = re.compile(r"\bdigitalRead\s*\(\s*([A-Za-z0-9_]+)\s*\)")
_ANALOG_READ_RE   = re.compile(r"\banalogRead\s*\(\s*([A-Za-z0-9_]+)\s*\)")
_ANALOG_WRITE_RE  = re.compile(r"\banalogWrite\s*\(\s*([A-Za-z0-9_]+)\s*,")
_TONE_RE          = re.compile(r"\btone\s*\(\s*([A-Za-z0-9_]+)\s*[,)]")
_SERVO_ATTACH_RE  = re.compile(r"\.\s*attach\s*\(\s*([A-Za-z0-9_]+)\s*[,)]")
_WIRE_BEGIN_RE    = re.compile(r"\bWire\.begin\s*\(\s*\)")
_SPI_BEGIN_RE     = re.compile(r"\bSPI\.begin\s*\(\s*\)")
_LED_BUILTIN_RE   = re.compile(r"\bLED_BUILTIN\b")

# ─── const int / #define alias resolution ────────────────────────────────
# `const int POT = A0; analogRead(POT);` must be read as `analogRead(A0);`
# by the downstream regexes. We detect the aliases and substitute them in the
# code before any other parsing — simpler than threading an alias dict
# through each _normalize_pin_token().
_CONST_ALIAS_RE = re.compile(
    r"\bconst\s+(?:int|byte|uint8_t|short|unsigned\s+int)\s+"
    r"(\w+)\s*=\s*([A-Za-z0-9_]+)"
)
_DEFINE_RE = re.compile(r"#\s*define\s+(\w+)\s+([A-Za-z0-9_]+)")

# Meme chose SANS `const` : `int pinCapteur = A0;`. C'est du style Arduino
# courant, et c'est ce que le modele a ecrit en QA L1 (2026-08-10) -- l'alias
# n'etait pas resolu, `analogRead(pinCapteur)` restait illisible, netlist VIDE.
#
# Elargir ne peut PAS etre inconditionnel : le meme sketch contenait
# `int valeurLue = 0;`, une variable de donnee. L'aliaser vers D0 aurait
# reecrit tout le code. Deux garde-fous, tous deux necessaires :
#   - la declaration doit commencer une LIGNE, ce qui ecarte `for (int i = 0;`
#     et ses substitutions catastrophiques dans l'en-tete de boucle ;
#   - la variable doit REELLEMENT servir d'argument a une fonction de broche
#     (cf. `_pin_argument_names`). C'est le seul signal fiable qui distingue un
#     alias de broche d'une variable de donnee, et il ne devine rien : il lit
#     l'usage.
# Les chemins `const` et `#define` restent inchanges -- eux resolvent aussi des
# NON-broches (`#define DHT_TYPE DHT22`), que ce filtre rejetterait.
_BARE_ALIAS_RE = re.compile(
    r"^[ \t]*(?:static[ \t]+)?"
    r"(?:int|byte|uint8_t|short|unsigned[ \t]+int)[ \t]+"
    r"(\w+)[ \t]*=[ \t]*([A-Za-z0-9_]+)[ \t]*;",
    re.MULTILINE)


def _extract_const_aliases(code: str) -> dict[str, str]:
    """Returns `{var_name: value}` for `const int` and `#define`.

    Resolves:
    - values that are valid pin literals (A0-A5, D0-D13,
      0-13, LED_BUILTIN) -> normalized via `_normalize_pin_token`
    - values that are other identifiers (e.g. `DHT22`, `INPUT_PULLUP`)
      -> kept as-is
    - numeric literal values with a suffix (1000UL, etc.)
      -> ignored (not relevant to our detection)

    Why: `#define DHT_TYPE DHT22` must be substituted so the DHT regex
    (which requires a literal `DHT11/22/21` as 2nd arg) matches after
    resolution. Same for `INPUT_PULLUP` or any other Arduino token.
    """
    aliases: dict[str, str] = {}
    _IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
    for rx in (_CONST_ALIAS_RE, _DEFINE_RE):
        for m in rx.finditer(code):
            var, val = m.group(1), m.group(2)
            # 1) Try first as a pin token
            net = _normalize_pin_token(val)
            if net is not None:
                aliases[var] = net
                continue
            # 2) Otherwise, if the value is a pure identifier (letters,
            # digits, underscores, no suffix), keep it as-is
            # so the downstream regexes can match (e.g. DHT22).
            if _IDENT_RE.fullmatch(val):
                aliases[var] = val
    # Declarations SANS `const`, admises seulement si la variable sert vraiment
    # d'argument a une fonction de broche (cf. `_BARE_ALIAS_RE`). `setdefault` :
    # une declaration `const` de meme nom garde la main.
    used = _pin_argument_names(code)
    if used:
        for m in _BARE_ALIAS_RE.finditer(code):
            var, val = m.group(1), m.group(2)
            if var not in used:
                continue
            net = _normalize_pin_token(val)
            if net is not None:
                aliases.setdefault(var, net)
    return aliases


def _pin_argument_names(code: str) -> set[str]:
    """Noms passes en PREMIER argument d'une fonction de broche.

    Le seul signal fiable pour distinguer un alias de broche d'une variable de
    donnee, sans rien deviner sur le nom : on lit l'usage. `pinCapteur` apparait
    dans `analogRead(pinCapteur)`, `valeurLue` nulle part.
    """
    names: set[str] = set()
    for rx in (_PINMODE_RE, _DIGITAL_WRITE_RE, _DIGITAL_READ_RE,
               _ANALOG_READ_RE, _ANALOG_WRITE_RE, _TONE_RE,
               _SERVO_ATTACH_RE):
        for m in rx.finditer(code):
            tok = m.group(1)
            if tok and not tok[0].isdigit():
                names.add(tok)
    return names


def _resolve_aliases(code: str) -> str:
    """Substitute each `\\bVAR\\b` with its literal value (e.g. POT -> A0)."""
    aliases = _extract_const_aliases(code)
    if not aliases:
        return code
    for var, value in aliases.items():
        code = re.sub(rf"\b{re.escape(var)}\b", value, code)
    return code


# ─── Name/type inference from the code (bare pin) ────────────────────
# When a pin is captured by the generic heuristic (no signature or
# include), we try to infer a better type token + a human label from the
# code IDENTIFIERS (constants/variables) and the comments.
# Per-pin source, taking priority over the prompt. See spec 2026-06-14
# smart-bare-pin-component-naming.

# STRUCTURAL suffixes to strip from the humanized name (RELAY_PIN -> Relay).
# Deliberately minimal: only "pin"/"pins". We keep the meaning-bearing
# words (sensor, value...) -- otherwise "soundSensor" would become
# "Sound" instead of "Sound sensor". (The matching itself uses all the
# words via _split_identifier, not _humanize_identifier.)
_IDENT_NOISE_WORDS = {"pin", "pins"}
_RECV_ANALOG_RE = re.compile(
    r"\b([A-Za-z_]\w*)\s*=\s*analogRead\s*\(\s*([A-Za-z0-9_]+)\s*\)"
)


def _split_identifier(name: str) -> list[str]:
    """Split an identifier into lowercase words (camelCase / snake_case /
    digits). `soundSensor` -> ['sound','sensor'] ; `RELAY_PIN` ->
    ['relay','pin'] ; `pir2` -> ['pir']."""
    # Insert a separator at camelCase boundaries, then split on every
    # non-alphabetic character.
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    words = re.split(r"[^A-Za-z]+", spaced)
    return [w.lower() for w in words if w]


def _humanize_identifier(name: str) -> str:
    """Human name from an identifier: strips the structural words
    (`_PIN`/`_PINS`), capitalizes. `RELAY_PIN` -> 'Relay' ;
    `soundSensor` -> 'Sound sensor'. Never returns an empty string:
    if everything is noise, keeps the original words."""
    words = _split_identifier(name)
    kept = [w for w in words if w not in _IDENT_NOISE_WORDS]
    if not kept:
        kept = words   # everything was noise -> keep as-is (e.g. "pin")
    if not kept:
        return name
    return " ".join(kept).capitalize()


def _pin_to_identifiers(code: str) -> dict[str, list[str]]:
    """Returns `{net: [identifiers tied to this pin]}`.

    Two sources:
      - the aliases `const int X = A0;` / `#define X 7` (var -> net inverse);
      - the variable receiving an analog read
        `int ldrValue = analogRead(A0)` (or analogRead(ALIAS)).

    Operates on the ORIGINAL code (pre-alias) so as not to lose the names.
    """
    aliases = _extract_const_aliases(code)   # var -> net
    pin_to_names: dict[str, list[str]] = {}
    for var, net in aliases.items():
        pin_to_names.setdefault(net, []).append(var)
    for m in _RECV_ANALOG_RE.finditer(code):
        recv, arg = m.group(1), m.group(2)
        net = _normalize_pin_token(arg) or aliases.get(arg)
        if net:
            pin_to_names.setdefault(net, []).append(recv)
    return pin_to_names


def _code_excerpt_for_pin(code: str, net: str,
                          pin_to_names: dict[str, list[str]]) -> str:
    """Per-pin matching text from the code: words of the humanized
    identifiers tied to the pin + end-of-line comments of the lines
    referencing the pin (by identifier or by literal).

    Supports end-of-line // comments AND inline block comments
    /* ... */ (on a single line). Multi-line blocks are
    not handled."""
    parts: list[str] = []
    names = pin_to_names.get(net, [])
    for nm in names:
        parts.append(" ".join(_split_identifier(nm)))
    tokens = set(names) | {net}
    den = _denormalize(net)
    if den and not den.isdigit():
        # Exclude bare digits (D1 -> "1"): a comment on a line mentioning
        # that number (e.g. `if (i == 1) // ...`) would wrongly pollute the
        # excerpt. Analog nets ("A0") stay (distinctive).
        tokens.add(den)
    for line in code.splitlines():
        # Extract the comment text (// at end of line AND inline /* ... */);
        # `code_part` = the rest, where we check the pin reference.
        comment_chunks: list[str] = []
        code_part = line
        if "//" in code_part:
            idx = code_part.index("//")
            comment_chunks.append(code_part[idx + 2:])
            code_part = code_part[:idx]
        for bm in re.finditer(r"/\*(.*?)\*/", code_part):
            comment_chunks.append(bm.group(1))
        code_part = re.sub(r"/\*.*?\*/", " ", code_part)
        comment_text = " ".join(comment_chunks).strip()
        if not comment_text:
            continue
        if any(t and re.search(rf"\b{re.escape(t)}\b", code_part) for t in tokens):
            parts.append(comment_text)
    return " ".join(p for p in parts if p)


def _mutate_component(components: list[Component], c: Component,
                      new_type: str, pins: list[Pin]) -> None:
    """Reclassify `c` as `new_type`: replaces pins + attributes (high
    confidence) + ref re-prefixed via `_ref_prefix_for`. Per-type counter to
    avoid ref collisions (mirror of the buzzer pattern)."""
    n = sum(1 for x in components if x.type == new_type)
    c.type = new_type
    c.pins = pins
    c.attributes = {"_confidence": "high"}
    c.ref = f"{_ref_prefix_for(new_type)}{n + 1}"


# ─── Library detection / recognizable patterns ─────────────────────
# Identifies a component from its include + its declaration or usage
# pattern. The signal pins detected here are "claimed" and excluded from
# the downstream generic heuristic (otherwise Servo.attach(11) would be
# reclassified as a LED). Power pins (5V/GND/3V3/VIN) are not claimed —
# they are shared among all components.

# Includes
_INCLUDE_SERVO_RE = re.compile(r"#\s*include\s*[<\"]\s*Servo\.h\s*[>\"]")
_INCLUDE_DHT_RE   = re.compile(r"#\s*include\s*[<\"]\s*DHT\.h\s*[>\"]")
_INCLUDE_OLED_RE  = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_SSD1306\.h\s*[>\"]")
_INCLUDE_LCD_RE   = re.compile(r"#\s*include\s*[<\"]\s*LiquidCrystal_I2C\.h\s*[>\"]")
_INCLUDE_INA219_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_INA219\.h\s*[>\"]")
# I2C address as constructor argument: `Adafruit_INA219 ina219(0x41);`
_INA219_ADDR_RE    = re.compile(r"\bAdafruit_INA219\s+\w+\s*\(\s*(0x[0-9a-fA-F]+)\s*\)")
# Additional sensors / modules -- types not present in CATALOG,
# their rendering goes through `resolve_generic` of the dynamic catalog. All
# work on the pattern: detect the characteristic include +
# extract the variable pins from the constructor (or fixed I2C pins).
_INCLUDE_BME280_RE   = re.compile(r"#\s*include\s*[<\"]\s*(?:Adafruit_)?BME280\.h\s*[>\"]")
_INCLUDE_MPU_RE      = re.compile(r"#\s*include\s*[<\"]\s*(?:Adafruit_)?MPU6050\.h\s*[>\"]")
_INCLUDE_MPU9250_RE  = re.compile(r"#\s*include\s*[<\"]\s*MPU9250(?:_asukiaaa)?\.h\s*[>\"]")
_INCLUDE_RTC_RE      = re.compile(r"#\s*include\s*[<\"]\s*RTClib\.h\s*[>\"]")
_INCLUDE_NEOPIX_RE   = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_NeoPixel\.h\s*[>\"]")
_INCLUDE_NEWPING_RE  = re.compile(r"#\s*include\s*[<\"]\s*NewPing\.h\s*[>\"]")
_INCLUDE_CCS811_RE   = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_CCS811\.h\s*[>\"]")
_INCLUDE_ENCODER_RE  = re.compile(r"#\s*include\s*[<\"]\s*Encoder\.h\s*[>\"]")
_INCLUDE_MFRC522_RE  = re.compile(r"#\s*include\s*[<\"]\s*MFRC522\.h\s*[>\"]")
_INCLUDE_HX711_RE    = re.compile(r"#\s*include\s*[<\"]\s*HX711\.h\s*[>\"]")
_INCLUDE_INA226_RE   = re.compile(r"#\s*include\s*[<\"]\s*INA226_WE\.h\s*[>\"]")
_INA226_ADDR_RE      = re.compile(r"(0x[0-9a-fA-F]{2})")
_INCLUDE_SD_RE       = re.compile(r"#\s*include\s*[<\"]\s*SD\.h\s*[>\"]")
_SD_BEGIN_RE         = re.compile(r"\bSD\s*\.\s*begin\s*\(\s*([A-Za-z0-9_]+)\s*\)")
_INCLUDE_ONEBUTTON_RE = re.compile(r"#\s*include\s*[<\"]\s*OneButton\.h\s*[>\"]")
_INCLUDE_SF_TB6612_RE = re.compile(
    r"#\s*include\s*[<\"]\s*SparkFun_TB6612\.h\s*[>\"]")
# `Motor motor1 = Motor(AIN1, AIN2, PWMA, offsetA, STBY);` — la forme par
# affectation est deja normalisee en amont. Groupes : IN1, IN2, PWM, offset,
# STBY (l'offset est un sens de rotation, pas une broche).
_SF_MOTOR_DECL_RE = re.compile(
    r"\bMotor\s+\w+\s*\(\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*,"
    r"\s*([A-Za-z0-9_]+)\s*,\s*[A-Za-z0-9_]+\s*,\s*([A-Za-z0-9_]+)\s*\)")
_INCLUDE_GROVE_MOTOR_RE = re.compile(
    r"#\s*include\s*[<\"]\s*Grove_I2C_Motor_Driver\.h\s*[>\"]")
_INCLUDE_MOTORSHIELD_RE = re.compile(
    r"#\s*include\s*[<\"]\s*Adafruit_MotorShield\.h\s*[>\"]")
# `OneButton bouton(PIN, true);` — la forme par affectation est deja normalisee
# en amont (`_normalize_ctor_assignment`), donc une seule regex suffit.
_ONEBUTTON_DECL_RE   = re.compile(r"\bOneButton\s+\w+\s*\(\s*([A-Za-z0-9_]+)\s*[,)]")
# `scale.begin(DT, SCK);` — l'objet est declare SANS broches, elles arrivent
# ici. Un troisieme argument optionnel (gain) est tolere.
_HX711_BEGIN_RE = re.compile(
    r"\b\w+\s*\.\s*begin\s*\(\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*[,)]")
_INCLUDE_TFT_RE      = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_ILI9341\.h\s*[>\"]")
_INCLUDE_STEPPER_RE  = re.compile(r"#\s*include\s*[<\"]\s*Stepper\.h\s*[>\"]")
_INCLUDE_ACCELSTEPPER_RE = re.compile(r"#\s*include\s*[<\"]\s*AccelStepper\.h\s*[>\"]")
_INCLUDE_KEYPAD_RE   = re.compile(r"#\s*include\s*[<\"]\s*Keypad\.h\s*[>\"]")
_INCLUDE_IRREMOTE_RE = re.compile(r"#\s*include\s*[<\"]\s*IRremote\.h\s*[>\"]")
_INCLUDE_DS18B20_RE  = re.compile(r"#\s*include\s*[<\"]\s*DallasTemperature\.h\s*[>\"]")
_INCLUDE_TINYGPS_RE  = re.compile(r"#\s*include\s*[<\"]\s*TinyGPS(?:\+\+|Plus)?\.h\s*[>\"]")
_INCLUDE_LORA_RE     = re.compile(r"#\s*include\s*[<\"]\s*LoRa\.h\s*[>\"]")
_INCLUDE_MHZ19_RE    = re.compile(r"#\s*include\s*[<\"]\s*MHZ19\.h\s*[>\"]")

# FastLED / WS2812: addressable LED strip. addLeds<CHIPSET, DATA_PIN[, ORDER]>.
# The DATA pin is the 2nd template arg. We only wire clockless 1-wire
# chipsets; 2-wire SPI chipsets (APA102/SK9822) don't match -> placeholder.
_INCLUDE_FASTLED_RE = re.compile(r"#\s*include\s*[<\"]\s*FastLED\.h\s*[>\"]")

# HX711 (load-cell amplifier / scale). DT/SCK pins extracted from
# `scale.begin(dout, sck)` (not the constructor, which is bare).
_INCLUDE_HX711_RE = re.compile(r"#\s*include\s*[<\"]\s*HX711\.h\s*[>\"]", re.I)
_HX711_DECL_RE = re.compile(r"\bHX711\s+(\w+)\s*;")

# DFPlayer Mini (UART MP3 module). No pins of its own: it drives a
# SoftwareSerial. The header's presence relabels the generic uart_module as
# `dfplayer` (same RX/TX/VCC/GND pins).
_INCLUDE_DFPLAYER_RE = re.compile(
    r"#\s*include\s*[<\"]\s*DFRobotDFPlayerMini\.h\s*[>\"]", re.I)
_INCLUDE_FINGERPRINT_RE = re.compile(
    r"#\s*include\s*[<\"]\s*Adafruit_Fingerprint\.h\s*[>\"]", re.I)
_FASTLED_ADDLEDS_RE = re.compile(
    r"\baddLeds\s*<\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*[,>]"
)
_FASTLED_CLOCKLESS = {"ws2812", "ws2812b", "ws2811", "ws2813", "ws2815", "sk6812", "neopixel"}

# Color TFT ST7735 / ST7789 (SPI). Adafruit_ST77xx(CS, DC, RST) constructor;
# fixed SCK/SDA (hardware SPI D13/D11). MAX31855 thermocouple: (SCLK, CS, MISO).
_INCLUDE_ST7735_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_ST7735\.h\s*[>\"]", re.I)
_ST7735_DECL_RE = re.compile(r"Adafruit_ST7735\s+\w+\s*(?:=\s*Adafruit_ST7735\s*)?\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")
_INCLUDE_ST7789_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_ST7789\.h\s*[>\"]", re.I)
_ST7789_DECL_RE = re.compile(r"Adafruit_ST7789\s+\w+\s*(?:=\s*Adafruit_ST7789\s*)?\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")
_INCLUDE_MAX31855_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_MAX31855\.h\s*[>\"]", re.I)
_MAX31855_DECL_RE = re.compile(r"Adafruit_MAX31855\s+\w+\s*\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")

# MAX7219 LED matrix driven by LedControl. LedControl(DIN, CLK,
# CS, numDevices) constructor. We wire the first 3 signal pins; numDevices ignored.
_INCLUDE_LEDCONTROL_RE = re.compile(r"#\s*include\s*[<\"]\s*LedControl\.h\s*[>\"]", re.I)
# LedControl lc(DIN, CLK, CS, numDevices);  ou  ... = LedControl(DIN, CLK, CS, n);
_LEDCONTROL_DECL_RE = re.compile(
    r"LedControl\s+\w+\s*(?:=\s*LedControl\s*)?\(\s*"
    r"([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*[^)]+?\)"
)

# TM1637 (7-seg display) driven by TM1637Display(CLK, DIO).
_INCLUDE_TM1637_RE = re.compile(r"#\s*include\s*[<\"]\s*TM1637Display\.h\s*[>\"]", re.I)
_TM1637_DECL_RE = re.compile(
    r"TM1637Display\s+\w+\s*(?:=\s*TM1637Display\s*)?\(\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")

# HT16K33 (I2C LED matrix, Adafruit backpack): address in begin(), no pins.
_INCLUDE_HT16K33_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_LEDBackpack\.h\s*[>\"]", re.I)

# ─── Fixed-pinout I2C sensors (SDA=A4, SCL=A5): address in begin(), no pins ─
# VL53L0X (ToF laser distance sensor), MAX30102 (heart-rate/SpO2),
# TCS34725 (RGB color sensor), BH1750 (ambient lux meter).
_INCLUDE_VL53L0X_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_VL53L0X\.h\s*[>\"]", re.I)
_INCLUDE_MAX30102_RE = re.compile(r"#\s*include\s*[<\"]\s*MAX3010[0-9]\.h\s*[>\"]", re.I)
_INCLUDE_TCS34725_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_TCS34725\.h\s*[>\"]", re.I)
_INCLUDE_BH1750_RE = re.compile(r"#\s*include\s*[<\"]\s*BH1750\.h\s*[>\"]", re.I)
# ADS1115 (16-bit I2C ADC converter), PCA9685 (16-channel servo/PWM I2C driver),
# SH1106 (I2C OLED display, detected on the header not the Adafruit_SH1106G class),
# AHT20 (I2C temperature/humidity sensor).
_INCLUDE_ADS1115_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_ADS1X15\.h\s*[>\"]", re.I)
_INCLUDE_PCA9685_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_PWMServoDriver\.h\s*[>\"]", re.I)
_INCLUDE_SH1106_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_SH110X\.h\s*[>\"]", re.I)
_INCLUDE_AHT20_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_AHTX0\.h\s*[>\"]", re.I)

# ─── batch4: fixed-pinout I2C sensors (SDA=A4/SCL=A5, address in begin) ───
_INCLUDE_BMP280_RE   = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_BMP280\.h\s*[>\"]", re.I)
_INCLUDE_APDS9960_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_APDS9960\.h\s*[>\"]", re.I)
_INCLUDE_MLX90614_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_MLX90614\.h\s*[>\"]", re.I)
_INCLUDE_SGP30_RE    = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_SGP30\.h\s*[>\"]", re.I)
_INCLUDE_SCD30_RE    = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_SCD30\.h\s*[>\"]", re.I)
# PN532 NFC: I2C with IRQ + RESET pins in the constructor (2-arg form).
_INCLUDE_PN532_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_PN532\.h\s*[>\"]", re.I)
_PN532_DECL_RE = re.compile(r"Adafruit_PN532\s+\w+\s*\(\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")
# ─── batch4: I2C expanders (output pins to be wired by the user) ──────
_INCLUDE_PCF8574_RE   = re.compile(r"#\s*include\s*[<\"]\s*PCF8574\.h\s*[>\"]", re.I)
_INCLUDE_MCP23017_RE  = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_MCP23X17\.h\s*[>\"]", re.I)
# ─── batch4: MAX6675 SPI thermocouple (SCK, CS, SO in the constructor) ──────
_INCLUDE_MAX6675_RE = re.compile(r"#\s*include\s*[<\"]\s*max6675\.h\s*[>\"]", re.I)
_MAX6675_DECL_RE = re.compile(r"MAX6675\s+\w+\s*\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")

# ─── batch5: fixed-pinout I2C sensors (SDA=A4/SCL=A5) ──────────────────
_INCLUDE_MCP9808_RE  = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_MCP9808\.h\s*[>\"]", re.I)
_INCLUDE_SI7021_RE   = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_Si7021\.h\s*[>\"]", re.I)
_INCLUDE_ADXL345_RE  = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_ADXL345_U\.h\s*[>\"]", re.I)
_INCLUDE_HMC5883_RE  = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_HMC5883_U\.h\s*[>\"]", re.I)
_INCLUDE_MCP4725_RE  = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_MCP4725\.h\s*[>\"]", re.I)
_INCLUDE_INA260_RE   = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_INA260\.h\s*[>\"]", re.I)
_INCLUDE_AS5600_RE   = re.compile(r"#\s*include\s*[<\"]\s*AS5600\.h\s*[>\"]", re.I)
_INCLUDE_VEML6075_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_VEML6075\.h\s*[>\"]", re.I)

# ─── batch6: 5 fixed-I2C sensors ────────────────────────────────────────
_INCLUDE_BNO055_RE   = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_BNO055\.h\s*[>\"]", re.I)
_INCLUDE_MCP9600_RE  = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_MCP9600\.h\s*[>\"]", re.I)
_INCLUDE_MAX17043_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_MAX1704X\.h\s*[>\"]", re.I)
_INCLUDE_AMG8833_RE  = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_AMG88xx\.h\s*[>\"]", re.I)
_INCLUDE_PM25_RE     = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_PM25AQI\.h\s*[>\"]", re.I)
# ─── batch6: nRF24L01 (SPI 3.3V, CE/CSN in the constructor) ─────────────────
_INCLUDE_RF24_RE = re.compile(r"#\s*include\s*[<\"]\s*RF24\.h\s*[>\"]", re.I)
_RF24_DECL_RE = re.compile(r"RF24\s+\w+\s*\(\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")

# ─── batch7 ──────────────────────────────────────────────────────────────
_INCLUDE_DRV2605_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_DRV2605\.h\s*[>\"]", re.I)
_INCLUDE_TM1638_RE  = re.compile(r"#\s*include\s*[<\"]\s*TM1638plus\.h\s*[>\"]", re.I)
_TM1638_DECL_RE = re.compile(r"TM1638plus\s+\w+\s*\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")
_INCLUDE_PCD8544_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_PCD8544\.h\s*[>\"]", re.I)
_PCD8544_DECL_RE = re.compile(r"Adafruit_PCD8544\s+\w+\s*(?:=\s*Adafruit_PCD8544\s*)?\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")
_INCLUDE_SSD1351_RE = re.compile(r"#\s*include\s*[<\"]\s*Adafruit_SSD1351\.h\s*[>\"]", re.I)
_SSD1351_DECL_RE = re.compile(r"Adafruit_SSD1351\s+\w+\s*(?:=\s*Adafruit_SSD1351\s*)?\(\s*[^,]+,\s*[^,]+,\s*&\w+\s*,\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")

# 74HC595 (shift register) driven by ShiftRegister74HC595<N>(DATA, CLK, LATCH).
_INCLUDE_SR595_RE = re.compile(r"#\s*include\s*[<\"]\s*ShiftRegister74HC595\.h\s*[>\"]", re.I)
_SR595_DECL_RE = re.compile(
    r"ShiftRegister74HC595\s*<\s*\d+\s*>\s+\w+\s*\(\s*([^,]+?)\s*,\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)")

# ─── Generic I2C fallback (safety net for off-catalog libs) ────────────────
_INCLUDE_ANY_RE = re.compile(r"#\s*include\s*[<\"]\s*([\w./+\-]+\.h)\s*[>\"]")
_INCLUDE_WIRE_RE = re.compile(r"#\s*include\s*[<\"]\s*Wire\.h\s*[>\"]")
_WIRE_ACTIVITY_RE = re.compile(r"\bWire\s*\.\s*(?:begin|beginTransmission|requestFrom)\b")

_VENDOR_PREFIXES = ("adafruit_", "sparkfun_", "seeed_", "dfrobot_", "grove_", "sodaq_")

# Pin count of an unrecognized-component placeholder ("module"-like, in line
# with the 4-pin I2C module). Arbitrary: the pins are not wired (empty net),
# so no functional impact.
_PLACEHOLDER_PIN_COUNT = 4

# Global constructor declaration: `MonCapteur capteur(5, 6);`. Used ONLY to
# report which pins an UNRECOGNIZED lib seems to use — `parse_fallback` sees
# pins through pinMode/digitalWrite/analogRead…, so pins passed only to a
# constructor are invisible to it and the placeholder ends up with no clue at
# all. We do NOT wire them (we don't know which pin does what): they go into
# the warning text, as information the user can act on.
_CTOR_DECL_RE = re.compile(
    r"^[ \t]*([A-Z][A-Za-z0-9_]*)[ \t]+[A-Za-z_]\w*[ \t]*\(([^)]*)\)[ \t]*;",
    re.MULTILINE)


# `Type nom = Type(args);` -> `Type nom(args);`. Les deux ecritures declarent
# le meme objet, mais TOUS les detecteurs a constructeur ne reconnaissent que la
# seconde : mesure du 2026-08-10, 6 signatures sur 8 (ili9341, mfrc522, encoder,
# neopixel, ir_receiver, dht) ne detectaient RIEN sur la forme par affectation
# -- schema entierement VIDE, sans le moindre avertissement. Or c'est l'ecriture
# des exemples officiels Adafruit, donc celle que le RAG fournit au modele et
# que le modele recopie.
#
# La retro-reference `\2` exige le MEME nom de type des deux cotes : `int x =
# foo(1);` n'est jamais touche. Les qualificateurs en tete sont absorbes, sinon
# `static Adafruit_X y = Adafruit_X(...)` passerait au travers.
_CTOR_ASSIGN_RE = re.compile(
    r"^([ \t]*(?:(?:static|const|volatile)[ \t]+)*)"   # qualificateurs
    r"([A-Za-z_]\w*)"                                  # type
    r"([ \t]+)([A-Za-z_]\w*)[ \t]*=[ \t]*"             # nom =
    r"\2[ \t]*\(",                                     # MEME type (
    re.MULTILINE)


# `#include <Foo.hpp>` / `<Foo.hh>` -> `#include <Foo.h>`. TOUTES les regex
# d'include du module figent `\.h` (une quarantaine), _INCLUDE_ANY_RE comprise —
# donc un en-tete `.hpp` etait invisible non seulement des detecteurs dedies,
# mais AUSSI du filet universel : aucune boite placeholder, aucun avertissement,
# netlist vide. Mesure du 2026-08-10 sur un sketch IRremote v4, dont l'en-tete
# est `IRremote.hpp` et que le corpus fournit a raison.
#
# Normaliser ici repare les quarante regex d'un coup. Portee limitee a la
# DETECTION (variable locale de `parse_fallback`) : le sketch compile garde son
# `.hpp`.
_INCLUDE_EXT_RE = re.compile(
    r"(#\s*include\s*[<\"]\s*[\w./+\-]+\.h)(?:pp|h)(\s*[>\"])")


def _normalize_include_extensions(code: str) -> str:
    """Ramene les extensions d'en-tete C++ a `.h` dans les directives include."""
    return _INCLUDE_EXT_RE.sub(r"\1\2", code)


def _normalize_ctor_assignment(code: str) -> str:
    """Ramene la forme par affectation a la forme de declaration directe.

    Applique AVANT tout le reste (phase 0 de `parse_fallback`), donc les
    detecteurs n'ont pas a connaitre les deux ecritures."""
    return _CTOR_ASSIGN_RE.sub(r"\1\2\3\4(", code)


def _constructor_pins_for(code: str, type_id: str) -> list[str]:
    """Nets found in the arguments of a constructor whose CLASS matches
    `type_id` (comparison on alphanumerics only: `LibInconnue` ↔ `libinconnue`).
    Empty list if the class is not instantiated or carries no pin literal."""
    target = re.sub(r"[^a-z0-9]", "", type_id.lower())
    if not target:
        return []
    nets: list[str] = []
    for m in _CTOR_DECL_RE.finditer(code):
        if re.sub(r"[^a-z0-9]", "", m.group(1).lower()) != target:
            continue
        for arg in m.group(2).split(","):
            net = _normalize_pin_token(arg.strip())
            if net is not None and net not in nets:
                nets.append(net)
    return nets

# Headers already covered by a dedicated signature + core/utility libs +
# common companions (GFX/Sensor). The generic fallback ignores them. Keep in
# sync with the _INCLUDE_*_RE above.
_KNOWN_HEADERS_LOWER = {
    # core / utilities / companions
    "arduino.h", "wire.h", "spi.h", "softwareserial.h", "eeprom.h",
    "math.h", "string.h", "stdio.h", "stdlib.h", "stdint.h", "onewire.h",
    "adafruit_gfx.h", "adafruit_sensor.h", "adafruit_busio.h",
    # libs with a dedicated signature
    "servo.h", "dht.h", "adafruit_ssd1306.h", "liquidcrystal_i2c.h",
    "bme280.h", "adafruit_bme280.h", "mpu6050.h", "adafruit_mpu6050.h",
    "mpu9250.h", "mpu9250_asukiaaa.h",
    "rtclib.h", "adafruit_neopixel.h", "newping.h", "adafruit_ccs811.h",
    "encoder.h", "mfrc522.h", "adafruit_ili9341.h", "stepper.h",
    "accelstepper.h", "keypad.h", "irremote.h", "dallastemperature.h",
    # TODO #47 : sans ces quatre lignes le placeholder universel se declenche
    # PAR-DESSUS le detecteur et l'utilisateur voit DEUX boites pour un seul
    # composant — la vraie, cablee, et une muette a 4 broches.
    "hx711.h", "ina226_we.h", "sd.h", "onebutton.h",
    "sparkfun_tb6612.h", "grove_i2c_motor_driver.h",
    "adafruit_motorshield.h",   # shield : reconnu pour etre EXPLIQUE, pas dessine
    "tinygps.h", "tinygps++.h", "tinygpsplus.h", "lora.h", "mhz19.h",
    "adafruit_ina219.h", "ledcontrol.h", "tm1637display.h",
    "adafruit_ledbackpack.h", "shiftregister74hc595.h",
    "adafruit_vl53l0x.h", "max30105.h", "max30102.h", "max30100.h",
    "adafruit_tcs34725.h", "bh1750.h",
    "adafruit_ads1x15.h", "adafruit_pwmservodriver.h",
    "adafruit_sh110x.h", "adafruit_ahtx0.h",
    "adafruit_bmp280.h", "adafruit_apds9960.h", "adafruit_mlx90614.h",
    "adafruit_sgp30.h", "adafruit_scd30.h", "adafruit_pn532.h",
    "adafruit_st7735.h", "adafruit_st7789.h", "adafruit_max31855.h",
    "pcf8574.h", "adafruit_mcp23x17.h", "max6675.h",
    "adafruit_mcp9808.h", "adafruit_si7021.h", "adafruit_adxl345_u.h",
    "adafruit_hmc5883_u.h", "adafruit_mcp4725.h", "adafruit_ina260.h",
    "as5600.h", "adafruit_veml6075.h",
    "adafruit_bno055.h", "adafruit_mcp9600.h", "adafruit_max1704x.h",
    "adafruit_amg88xx.h", "adafruit_pm25aqi.h", "rf24.h",
    "hx711.h", "dfrobotdfplayermini.h",
    "adafruit_fingerprint.h", "adafruit_drv2605.h", "tm1638plus.h",
    "adafruit_pcd8544.h", "adafruit_ssd1351.h",
}


# ─── En-têtes qui ne sont PAS des composants ────────────────────────────────
# Sans cette liste, un exemple officiel produit des boîtes fantômes dans le
# schéma : `arduino_secrets.h` (les identifiants Wi-Fi) devenait un composant,
# tout comme `adalogo.h` et `adaqrcode.h` — des BITMAPS du bandeau de
# l'imprimante thermique. Mesuré le 2026-08-26 : 8 types fantômes sur les
# exemples du corpus.
#
# Un en-tête de configuration, de données ou de système décrit quelque chose
# qu'on ne branche pas. Le filet « composant inconnu » existe pour ne rien
# perdre, mais dessiner une boîte pour `avr/power.h` n'est pas prudent — c'est
# faux.
_NON_COMPONENT_HEADERS = frozenset({
    "adalogo", "adaqrcode",        # bitmaps (Adafruit_Thermal)
    "arduino_secrets",             # identifiants Wi-Fi
    "bluefruitconfig",             # configuration (Bluefruit)
    "flash_config",                # configuration (SPI flash)
    "sdfat_adafruit_fork",         # système de fichiers, pas un composant
})
# Répertoires d'en-têtes SYSTÈME : `avr/power.h`, `util/delay.h`… Une règle de
# préfixe plutôt qu'une liste, parce que la famille est ouverte.
_SYSTEM_HEADER_DIRS = ("avr/", "util/", "sys/")


def _header_slug(header: str, default: str = "") -> str:
    """'Adafruit_ADS1015.h' -> 'ads1015'. Chemin, '.h' et préfixe fabricant
    retirés, minuscules — SANS appliquer les alias.

    ⚠️ Séparé de `_clean_lib_name` pour une raison mécanique : la table d'alias
    se construit EN APPELANT cette fonction sur les en-têtes du corpus. Si elle
    appelait `_clean_lib_name`, la construction de la table se rappellerait
    elle-même sans fin (le cache est encore vide à ce moment-là).
    """
    base = header.replace("\\", "/").rsplit("/", 1)[-1]
    if base.lower().endswith(".h"):
        base = base[:-2]
    low = base.lower()
    for pref in _VENDOR_PREFIXES:
        if low.startswith(pref):
            base = base[len(pref):]
            break
    base = base.strip()
    return base.lower() if base else default


def _is_non_component_header(header: str) -> bool:
    """Cet `#include` décrit-il autre chose qu'un composant à brancher ?"""
    norm = header.replace("\\", "/").lower()
    if norm.startswith(_SYSTEM_HEADER_DIRS):
        return True
    return _header_slug(header) in _NON_COMPONENT_HEADERS


_HEADER_ALIAS_CACHE: dict[str, str] | None = None


def _header_type_alias() -> dict[str, str]:
    """`{slug d'en-tête -> type canonique}`, DÉRIVÉ du corpus, jamais écrit à
    la main.

    Le défaut, mesuré le 2026-08-26 : le détecteur nommait le composant d'après
    le FICHIER d'en-tête. `<TCA9548A.h>` sortait en `tca9548a` alors que l'app
    connaît parfaitement ce composant sous `i2c_multiplexer` — entrée catalogue
    complète, identité au registre, libellé humain dans les 4 langues. **21
    exemples officiels du corpus** étaient dans ce cas ; ce n'était pas une
    lacune de détection mais un désaccord de NOM.

    La table se dérive de deux tables qui existent déjà et se répondent : le
    champ `headers` de chaque entrée corpus, et le champ `documents` du
    **registre de composants**, qui dit quel `Component` un document décrit.
    Rien n'est écrit à la main — une entrée corpus ajoutée demain apporte ses
    alias avec elle. Une table manuelle aurait dérivé, exactement comme les
    quatre mécanismes de jointure que le registre a remplacés en juillet.

    ⚠️ **Passer par le REGISTRE, pas par l'id du corpus.** Les deux coïncident
    presque toujours, mais pas toujours : le document `adafruit-ina3221`
    décrit le composant `ina3221`. Une première version aliasait vers l'id du
    corpus et faisait émettre `adafruit-ina3221`, un type que rien ne sait
    dessiner ni nommer. Le registre est la source de vérité de l'identité d'un
    composant ; le corpus est une table de documents.

    ⚠️ **Un slug qui EST déjà un type de composant n'est jamais aliasé.**
    `Adafruit_BMP085.h` est un en-tête de l'entrée `bmp180`, mais `bmp085` est
    aussi un composant à part entière — l'aliaser faisait disparaître le
    BMP085 au profit du BMP180. Mesuré : c'est la seule collision du corpus
    actuel, et cette garde la neutralise par construction.

    Import PARESSEUX de `ui.rag` : il ne coûte que la lecture du corpus (4 ms
    mesurées, l'encodeur ONNX n'est pas touché), mais le faire au niveau module
    créerait une dépendance d'import entre le détecteur de câblage et le RAG.
    """
    global _HEADER_ALIAS_CACHE
    if _HEADER_ALIAS_CACHE is None:
        from ..rag import all_corpus_entries
        from ..component_registry import REGISTRY
        doc_to_type = {doc: c.id for c in REGISTRY for doc in (c.documents or ())}
        known_types = {c.id for c in REGISTRY}
        table: dict[str, str] = {}
        for entry in all_corpus_entries():
            cid = entry.get("id")
            type_id = doc_to_type.get(cid)
            if not type_id:
                continue          # document purement logiciel, ou orphelin
            for header in (entry.get("headers") or []):
                slug = _header_slug(header)
                # Trois refus : rien à aliaser, l'alias serait l'identité, ou
                # le slug désigne DÉJÀ un composant (cf. `bmp085` ci-dessus).
                if not slug or slug == type_id or slug in known_types:
                    continue
                # `setdefault` : en cas de collision future, la première entrée
                # gagne — et `test_corpus_examples_are_detected` la signalera.
                table.setdefault(slug, type_id)
        _HEADER_ALIAS_CACHE = table
    return _HEADER_ALIAS_CACHE


def _clean_lib_name(header: str, default: str = "i2c_module") -> str:
    """'Adafruit_ADS1015.h' -> 'ads1015'. Strips path, '.h', vendor prefix,
    and lowercases. Returns `default` if nothing usable.

    Applies `_header_type_alias()` last, so a header the corpus already ties to
    a known component comes out under the component's canonical name rather
    than the file's."""
    slug = _header_slug(header)
    if not slug:
        return default
    return _header_type_alias().get(slug, slug)


# Declaration patterns to extract the variable pins (constructors)
_RTC_DS1307_RE   = re.compile(r"\bRTC_DS1307\s+\w+\s*;")
_RTC_DS3231_RE   = re.compile(r"\bRTC_DS3231\s+\w+\s*;")
# Adafruit_NeoPixel pixels(N, PIN, NEO_GRB + ...) ; pin = 2nd arg
_NEOPIX_DECL_RE  = re.compile(
    r"\bAdafruit_NeoPixel\s+\w+\s*\(\s*\w+\s*,\s*([A-Za-z0-9_]+)\s*[,)]"
)
# NewPing sonar(TRIG, ECHO, MAX_DIST)
_NEWPING_DECL_RE = re.compile(
    r"\bNewPing\s+\w+\s*\(\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*[,)]"
)
# Encoder enc(A_PIN, B_PIN)
_ENCODER_DECL_RE = re.compile(
    r"\bEncoder\s+\w+\s*\(\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*\)"
)
# MFRC522 mfrc522(SS_PIN, RST_PIN)
_MFRC522_DECL_RE = re.compile(
    r"\bMFRC522\s+\w+\s*\(\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*\)"
)
# Adafruit_ILI9341 tft(CS, DC, RST) (3 control pins, the rest on fixed SPI bus)
_TFT_DECL_RE = re.compile(
    r"\bAdafruit_ILI9341\s+\w+\s*\(\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*\)"
)
# Stepper s(STEPS_PER_REV, P1, P2, P3, P4) -- for 28BYJ-48 stepper on ULN2003.
# Note: the Stepper lib uses the order {1,3,2,4} (see Arduino docs). We capture
# them as-is and expose them as IN1..IN4 in the netlist.
_STEPPER_DECL_RE = re.compile(
    r"\bStepper\s+\w+\s*\(\s*\w+\s*,\s*"
    r"([A-Za-z0-9_]+)\s*,\s*"
    r"([A-Za-z0-9_]+)\s*,\s*"
    r"([A-Za-z0-9_]+)\s*,\s*"
    r"([A-Za-z0-9_]+)\s*\)"
)
# AccelStepper s(AccelStepper::DRIVER, STEP, DIR) or AccelStepper s(1, STEP, DIR)
# -- STEP/DIR mode for A4988 / DRV8825 / TMC2208-type drivers (NEMA17).
# We ONLY capture this mode here; the FULL4WIRE mode (interface 4/8) is already
# covered by _STEPPER_DECL_RE via Stepper.h for the 28BYJ-48.
_ACCELSTEPPER_DRIVER_DECL_RE = re.compile(
    r"\bAccelStepper\s+\w+\s*\(\s*"
    r"(?:AccelStepper::DRIVER|1)\s*,\s*"
    r"([A-Za-z0-9_]+)\s*,\s*"
    r"([A-Za-z0-9_]+)\s*\)"
)
# A4988 manual step (fallback if AccelStepper.h is not used): common
# pattern in Arduino tutorials -- PIN_STEP/PIN_DIR/PIN_ENABLE constants +
# digitalWrite + delayMicroseconds in a loop. STEP/DIR are
# mandatory; ENABLE optional (otherwise ENA -> GND by default like
# AccelStepper). Covers the most widespread naming variants
# (PIN_STEP / STEP_PIN / stepPin / step_pin) and the
# `const T name = N` declarations as well as `#define name N`.
_A4988_MANUAL_STEP_RE = re.compile(
    r"(?:const\s+\w+|int|uint8_t|byte|long|#\s*define)\s+"
    r"(?:PIN_STEP|STEP_PIN|stepPin|step_pin)\b"
    r"\s*(?:=|\s)\s*(\d+)"
)
_A4988_MANUAL_DIR_RE = re.compile(
    r"(?:const\s+\w+|int|uint8_t|byte|long|#\s*define)\s+"
    r"(?:PIN_DIR|DIR_PIN|dirPin|dir_pin)\b"
    r"\s*(?:=|\s)\s*(\d+)"
)
_A4988_MANUAL_EN_RE = re.compile(
    r"(?:const\s+\w+|int|uint8_t|byte|long|#\s*define)\s+"
    r"(?:PIN_ENABLE|ENABLE_PIN|enablePin|PIN_EN|EN_PIN|enable_pin)\b"
    r"\s*(?:=|\s)\s*(\d+)"
)
# Confirmation heuristic: >=1 delayMicroseconds() (typical STEP
# pulse) OR a textual mention of an A4988/DRV8825/TMC2208 driver or
# of a NEMA17. Used to avoid false positives on variables named
# STEP_PIN that would not be a stepper (rare but possible).
_A4988_MANUAL_CONFIRM_RE = re.compile(
    r"\bdelayMicroseconds\s*\(|"
    r"\bA4988\b|\bDRV8825\b|\bTMC2208\b|"
    r"\bNEMA[\s_-]*17\b|\bpas[\s_-]a[\s_-]pas\b",
    re.IGNORECASE,
)
# Keypad matrix : byte rowPins[ROWS] = {9, 8, 7, 6}; byte colPins[COLS] = {5, 4, 3, 2};
# Naming convention: `rowPins` / `colPins` (canonical in Arduino tutorials).
_KEYPAD_ROW_PINS_RE = re.compile(
    r"\bbyte\s+rowPins\s*\[[^\]]*\]\s*=\s*\{\s*([^}]+)\}"
)
_KEYPAD_COL_PINS_RE = re.compile(
    r"\bbyte\s+colPins\s*\[[^\]]*\]\s*=\s*\{\s*([^}]+)\}"
)
# IRrecv irrecv(11) or IRrecv irrecv(RECV_PIN, ENABLE_LED_FEEDBACK)
_IRRECV_DECL_RE = re.compile(
    r"\bIRrecv\s+\w+\s*\(\s*([A-Za-z0-9_]+)\s*[,)]"
)
# IRremote v4 : plus de constructeur, un objet GLOBAL fourni par la lib.
#   IrReceiver.begin(IR_RECEIVE_PIN, ENABLE_LED_FEEDBACK);
# C'est l'ecriture de l'exemple officiel, donc celle du corpus, donc celle que
# le modele produit. Sans elle, un sketch IRremote v4 ne donnait AUCUN
# composant (mesure 2026-08-10, QA K1). L'ancienne forme reste reconnue : les
# deux versions de la lib circulent.
_IRRECEIVER_BEGIN_RE = re.compile(
    r"\bIrReceiver\s*\.\s*begin\s*\(\s*([A-Za-z0-9_]+)\s*[,)]"
)
# OneWire oneWire(2) -> DATA pin of the DS18B20.
_ONEWIRE_DECL_RE = re.compile(
    r"\bOneWire\s+\w+\s*\(\s*([A-Za-z0-9_]+)\s*\)"
)
# SoftwareSerial gpsSerial(RX, TX) -- shared between TinyGPS and MH-Z19. We
# capture all the declarations and distribute them to the libs present
# in document order. RX/TX are from the Arduino's point of view: RX=4 -> we
# wire the module's TX to D4, and TX=3 -> we wire the module's RX
# to D3 (standard crossover).
_SOFTWARE_SERIAL_DECL_RE = re.compile(
    r"\bSoftwareSerial\s+\w+\s*\(\s*([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*\)"
)
# LoRa.setPins(SS, RST, DIO0) -- optional SPI pins; default otherwise
# (NSS=10, NRESET=9, DIO0=2).
_LORA_SETPINS_RE = re.compile(
    r"\bLoRa\s*\.\s*setPins\s*\(\s*([A-Za-z0-9_]+)\s*,\s*"
    r"([A-Za-z0-9_]+)\s*,\s*([A-Za-z0-9_]+)\s*\)"
)
# MQ-135 (analog gas sensor): heuristic detection on the variable /
# define name. Covers `#define MQ135_PIN A0`, `const int MQ_PIN = A0`,
# `int gas_value = analogRead(A0)`, etc. Group 1 = the suggestive name,
# group 2 = the analog pin. Case-insensitive.
_MQ135_DEFINE_RE = re.compile(
    r"#\s*define\s+(MQ\d*\w*|GAS_\w*|CO2_\w*|AIR_\w*|AIRQ\w*)\s+(A\d+)",
    re.IGNORECASE,
)
_MQ135_CONST_RE = re.compile(
    r"(?:const\s+int|int|byte)\s+(MQ\d*\w*|gas\w*|co2\w*|air\w*)\s*=\s*(A\d+)",
    re.IGNORECASE,
)

# La reference MQ que porte le nom de la constante : `MQ137_PIN` -> `mq137`.
# Le suffixe optionnel est une lettre COLLEE au numero (MQ303A, MQ306A) ; le
# `_PIN`, `_SENSOR`... qui suit est ecarte par le `(?:_|$)`, sans quoi
# `MQ2_PIN` sortirait « mq2_p ».
_MQ_PART_RE = re.compile(r"^MQ[-_ ]?(\d+[A-Z]?)(?:_|$)", re.IGNORECASE)

# ⚠️ On ne reconnait QUE les references qui ont une identite au registre.
# Fabriquer un type depuis le code seul (« mq9999 ») donnerait un type de
# cablage sans fiche, sans nom court et sans libelle traduit — precisement ce
# que la garde 7 de `test_component_registry` interdit. Pour tout le reste, le
# repli sur `mq135` dit au moins « capteur de gaz », ce qui reste vrai.
#
# Construit depuis le registre plutot qu'ecrit a la main : c'est ce qui fait
# qu'ajouter une piece MQ au registre suffit a la rendre detectable, sans
# qu'aucune liste ne derive ici. Garde :
# `test_mq_tout_type_emis_a_une_identite_au_registre`.
def _mq_known_parts() -> frozenset[str]:
    from ..component_registry import registry
    return frozenset(c.id for c in registry()
                     if re.fullmatch(r"mq\d+[a-z]?", c.id))


_MQ_KNOWN_PARTS = _mq_known_parts()


def _mq_type_for(identifier: str) -> str:
    """Type MQ deduit du nom de la constante, `mq135` par defaut."""
    m = _MQ_PART_RE.match((identifier or "").strip())
    if m is None:
        return "mq135"
    candidat = "mq" + m.group(1).lower()
    return candidat if candidat in _MQ_KNOWN_PARTS else "mq135"

# Declaration / usage patterns
_SERVO_ATTACH_NAMED_RE = re.compile(r"\b(\w+)\s*\.\s*attach\s*\(\s*([A-Za-z0-9_]+)\s*[,)]")
_DHT_DECLARE_RE = re.compile(r"\bDHT\s+\w+\s*\(\s*([A-Za-z0-9_]+)\s*,\s*(DHT11|DHT22|DHT21)\s*\)")
# `display.begin(SSD1306_SWITCHCAPVCC, 0x3C)`: capture the I2C address
_OLED_BEGIN_ADDR_RE = re.compile(r"\.\s*begin\s*\(\s*SSD1306_\w+\s*,\s*(0x[0-9a-fA-F]+)\s*\)")
# `LiquidCrystal_I2C lcd(0x27, 16, 2)`: address in 1st arg
_LCD_DECLARE_ADDR_RE = re.compile(r"\bLiquidCrystal_I2C\s+\w+\s*\(\s*(0x[0-9a-fA-F]+)\s*,")
# HC-SR04: pulseIn(ECHO, ...) + sequence digitalWrite(TRIG,HIGH);
# delayMicroseconds; digitalWrite(TRIG,LOW) (the 10us trigger pulse).
_PULSE_IN_RE = re.compile(r"\bpulseIn\s*\(\s*([A-Za-z0-9_]+)\s*,")
_HCSR04_TRIG_PULSE_RE = re.compile(
    r"digitalWrite\s*\(\s*(\w+)\s*,\s*HIGH\s*\)\s*;\s*"
    r"delayMicroseconds\s*\(\s*\d+\s*\)\s*;\s*"
    r"digitalWrite\s*\(\s*\1\s*,\s*LOW\s*\)"
)
# Buzzer: `tone(N, ...)` is the only Arduino call dedicated to the piezo.
_TONE_CALL_RE = re.compile(r"\btone\s*\(\s*([A-Za-z0-9_]+)\s*[,)]")

# Shared pins / non-signal pins
_POWER_NETS = {"5V", "3V3", "GND", "VIN"}

# ─── fn_id assignment by prompt lookup (pure Python, no AI markers) ──
# The source of truth for "which feature generated this component":
# the prompt that mentions its pin. We iterate `prompts_by_fn` (provided by
# the studio from the prompt history of each function) and associate
# each component with the first prompt that mentions its signal pin.
#
# Advantage: no dependency on the `<<< fn-N >>>` markers -- we align
# with the "full-Python wiring without AI markers" goal.
# Limitation: if the prompt does not explicitly mention the pin (the AI
# made it up), fn_id stays "" -- disambiguation then falls back on the
# global prompt. That's the acceptable edge case -- the modal will display
# "No explicit mention in your prompt".


def _assign_fn_ids(components: list[Component],
                   prompts_by_fn: dict[str, str] | None) -> None:
    """Assigns `component.fn_id` by finding which prompt in
    `prompts_by_fn` mentions the component's signal pin. Pure
    Python -- no dependency on AI markers in the code."""
    if not prompts_by_fn:
        return

    for c in components:
        if c.fn_id:
            continue
        for pin in c.pins:
            if pin.net in _POWER_NETS:
                continue
            for fn_id, fn_prompt in prompts_by_fn.items():
                if find_pin_excerpt(fn_prompt, pin.net):
                    c.fn_id = fn_id
                    break
            if c.fn_id:
                break


def _detect_libraries(
    code: str, original_code: str | None = None,
) -> tuple[list[Component], set[str]]:
    """Detects the components recognizable by their signature (include +
    declaration or usage pattern). Returns `(components, claimed_pins)`.

    `claimed_pins` is the set of SIGNAL nets (e.g. `D11`, `D2`) already
    assigned to a component; power pins (5V/GND/...) are not claimed
    because they are shared. The downstream generic heuristic (parse_fallback
    phase 2) must ignore claimed to avoid an erroneous reclassification.

    `original_code` is the code BEFORE `_resolve_aliases`. Needed for the
    detectors that depend on the constant names (e.g. `PIN_STEP` ->
    A4988 manual) because aliasing substitutes them with their literal value
    (`PIN_STEP` -> `D3`). If not provided, we fall back on `code` (backward
    compat for call sites that do not provide the original).

    Coverage: Servo, DHT11/22, OLED SSD1306 (I2C), LCD I2C, INA219 (I2C), HC-SR04, buzzer.
    """
    if original_code is None:
        original_code = code
    components: list[Component] = []
    claimed: set[str] = set()
    # Headers "consumed" by a wired detection (FastLED, named UART): the
    # placeholder net skips them, which avoids double-rendering (wired
    # component + placeholder of the same header) without blinding the
    # placeholder to uncovered cases (e.g. 2-wire FastLED chipset -> stays placeholder).
    claimed_headers: set[str] = set()

    def _add(ctype: str, pins: list[Pin], attrs: dict | None = None) -> None:
        """Adds a component with an auto-numbered ref + claims the signal pins."""
        prefix = _ref_prefix_for(ctype)
        n = sum(1 for c in components if c.ref.startswith(prefix)) + 1
        components.append(Component(
            ref=f"{prefix}{n}", type=ctype, fn_id="", inferred=True,
            pins=pins, attributes=(attrs or {}),
        ))
        for p in pins:
            if p.net not in _POWER_NETS:
                claimed.add(p.net)

    # ─── Servo ────────────────────────────────────────────────────────────
    if _INCLUDE_SERVO_RE.search(code):
        for m in _SERVO_ATTACH_NAMED_RE.finditer(code):
            net = _normalize_pin_token(m.group(2))
            if net is None or net in claimed:
                continue
            _add("servo", [Pin("VCC", "5V"), Pin("GND", "GND"), Pin("SIG", net)])

    # ─── DHT11 / DHT22 ────────────────────────────────────────────────────
    if _INCLUDE_DHT_RE.search(code):
        for m in _DHT_DECLARE_RE.finditer(code):
            net = _normalize_pin_token(m.group(1))
            if net is None or net in claimed:
                continue
            ctype = "dht22" if m.group(2) in ("DHT22", "DHT21") else "dht11"
            _add(ctype, [Pin("VCC", "5V"), Pin("DATA", net), Pin("GND", "GND")])

    # ─── OLED SSD1306 (I2C — fixed pins A4/A5 on Uno) ────────────────────
    if _INCLUDE_OLED_RE.search(code):
        addr_m = _OLED_BEGIN_ADDR_RE.search(code)
        addr = addr_m.group(1) if addr_m else "0x3C"
        _add("oled_ssd1306",
             [Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5")],
             {"address": addr})

    # ─── LCD I2C (fixed pins A4/A5 on Uno) ───────────────────────────────
    if _INCLUDE_LCD_RE.search(code):
        addr_m = _LCD_DECLARE_ADDR_RE.search(code)
        addr = addr_m.group(1) if addr_m else "0x27"
        _add("lcd_i2c",
             [Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5")],
             {"address": addr})

    # ─── INA219 (I2C current/voltage sensor: A4/A5 + measurement terminals VIN+/VIN-) ─
    if _INCLUDE_INA219_RE.search(code):
        addr_m = _INA219_ADDR_RE.search(code)
        addr = addr_m.group(1) if addr_m else "0x40"
        _add("ina219",
             [Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5"),
              Pin("VIN+", ""), Pin("VIN-", "")],
             {"address": addr})

    # ─── INA226 (I2C current sensor, lib INA226_WE) ─────────────────────
    # TODO #47 : l'exemple officiel tombait sur le FILET I2C — câblage
    # « présumé », alors que la lib est parfaitement identifiable. Un filet qui
    # se déclenche là où une signature existe, c'est de l'honnêteté payée trop
    # cher : on annonçait une supposition sur un cas qu'on savait lire.
    if _INCLUDE_INA226_RE.search(code):
        addr_m = _INA226_ADDR_RE.search(code)
        _add("ina226",
             [Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5"),
              Pin("VIN+", ""), Pin("VIN-", "")],
             {"address": addr_m.group(1) if addr_m else "0x40"})

    # ─── Carte SD (SPI : CS variable, MOSI/MISO/SCK fixes) ──────────────
    # TODO #43 + #47. Le brochage est déterministe : CS vient de
    # `SD.begin(cs)`, le reste est câblé dans la puce. L'identifiant émis est
    # `sd_card`, celui que le registre et `_TYPE_LABEL` portaient déjà — c'est
    # la question que #43 laissait ouverte, tranchée en écrivant la détection
    # comme il le demandait. Avant, seul le placeholder répondait, sous le type
    # `sd` dérivé du nom de l'en-tête.
    if _INCLUDE_SD_RE.search(code):
        cs_m = _SD_BEGIN_RE.search(code)
        cs = _normalize_pin_token(cs_m.group(1)) if cs_m else "D10"
        if cs is not None and cs not in claimed:
            _add("sd_card",
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("MISO", "D12"), Pin("MOSI", "D11"),
                  Pin("SCK", "D13"), Pin("CS", cs)])

    # ─── Bouton piloté par la lib OneButton ─────────────────────────────
    # TODO #47 : c'est un bouton-poussoir ordinaire, deja entierement catalogue
    # — seul le fait qu'il soit declare par une bibliotheque le rendait
    # invisible. Le 2e argument du constructeur est `activeLow` : vrai (defaut)
    # = bouton entre la broche et GND avec INPUT_PULLUP, donc le meme cablage
    # que celui deduit d'un `pinMode(.., INPUT_PULLUP)`.
    if _INCLUDE_ONEBUTTON_RE.search(code):
        for m in _ONEBUTTON_DECL_RE.finditer(code):
            pin = _normalize_pin_token(m.group(1))
            if pin is None or pin in claimed:
                continue
            _add("button", [Pin("1", pin), Pin("2", "GND")],
                 {"pull": "internal"})

    # ─── TB6612FNG via la lib SparkFun ──────────────────────────────────
    # TODO #47 : le driver EST au catalogue (DIP-16, brochage complet), mais
    # l'exemple officiel le declare par des objets `Motor(...)` — donc
    # placeholder muet jusqu'ici. Les deux moteurs partagent UN driver
    # (canaux A et B), ce que les arguments disent explicitement.
    # Cote moteur (AO1/AO2/BO1/BO2), on ne cable RIEN : le code ne dit pas ce
    # qu'il y a au bout, et inventer un moteur serait une devinette.
    if _INCLUDE_SF_TB6612_RE.search(code):
        canaux = {}
        for m in _SF_MOTOR_DECL_RE.finditer(code):
            pins = [_normalize_pin_token(m.group(i)) for i in (1, 2, 3, 4)]
            if any(p is None for p in pins):
                continue
            canaux["A" if "A" not in canaux else "B"] = pins
        if canaux:
            a = canaux.get("A") or [None] * 4
            b = canaux.get("B") or [None] * 4
            stby = a[3] or b[3] or ""
            _add("tb6612fng",
                 [Pin("VM", "BAT_5V"), Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("AO1", ""), Pin("AO2", ""), Pin("BO2", ""),
                  Pin("BO1", ""), Pin("GND", "GND"), Pin("GND", "GND"),
                  Pin("PWMB", b[2] or ""), Pin("BIN2", b[1] or ""),
                  Pin("BIN1", b[0] or ""), Pin("STBY", stby),
                  Pin("AIN1", a[0] or ""), Pin("AIN2", a[1] or ""),
                  Pin("PWMA", a[2] or "")])

    # ─── Grove I2C Motor Driver ─────────────────────────────────────────
    # TODO #47 : driver moteur pilote entierement par I2C — aucune broche de
    # commande cote Arduino, d'ou l'absence de tout indice pour les
    # heuristiques de broche nue. La signature de la lib suffit.
    if _INCLUDE_GROVE_MOTOR_RE.search(code):
        _add("grove_motor_driver",
             [Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5")])

    # ─── HC-SR04 (pulseIn + 10us trigger pulse) ──────────────────────────
    echo_m = _PULSE_IN_RE.search(code)
    trig_m = _HCSR04_TRIG_PULSE_RE.search(code)
    if echo_m and trig_m:
        echo_net = _normalize_pin_token(echo_m.group(1))
        trig_net = _normalize_pin_token(trig_m.group(1))
        if echo_net and trig_net and echo_net != trig_net \
                and echo_net not in claimed and trig_net not in claimed:
            _add("hcsr04",
                 [Pin("VCC", "5V"), Pin("TRIG", trig_net),
                  Pin("ECHO", echo_net), Pin("GND", "GND")])

    # ─── BME280 (I2C T/P/H sensor, off-catalog -> dispatcher) ─────────
    if _INCLUDE_BME280_RE.search(code):
        _add("bme280",
             [Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5")])

    # ─── MPU6050 (I2C accelerometer/gyroscope, off-catalog) ────────────
    if _INCLUDE_MPU_RE.search(code):
        _add("mpu6050",
             [Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5")])

    # ─── MPU9250 (I2C 9-axis IMU, accel+gyro+magneto interne) ──────────
    if _INCLUDE_MPU9250_RE.search(code):
        _add("mpu9250",
             [Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5")])

    # ─── RTC DS1307 / DS3231 (I2C 4 pins) ────────────────────────────────
    if _INCLUDE_RTC_RE.search(code):
        ctype = ("ds3231" if _RTC_DS3231_RE.search(code)
                 else "ds1307" if _RTC_DS1307_RE.search(code)
                 else None)
        if ctype is not None:
            _add(ctype,
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("SDA", "A4"), Pin("SCL", "A5")])

    # ─── CCS811 (I2C air-quality sensor) ────────────────────────────────
    if _INCLUDE_CCS811_RE.search(code):
        _add("ccs811",
             [Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5")])

    # ─── NeoPixel: 3 pins (DIN from the constructor, VCC, GND) ───────────────
    if _INCLUDE_NEOPIX_RE.search(code):
        for m in _NEOPIX_DECL_RE.finditer(code):
            net = _normalize_pin_token(m.group(1))
            if net is None or net in claimed:
                continue
            _add("neopixel",
                 [Pin("VCC", "5V"), Pin("DIN", net), Pin("GND", "GND")])

    # ─── FastLED / WS2812: same type as NeoPixel (1-wire DATA strip) ─────
    if _INCLUDE_FASTLED_RE.search(code):
        for m in _FASTLED_ADDLEDS_RE.finditer(code):
            if m.group(1).lower() not in _FASTLED_CLOCKLESS:
                continue  # 2-wire SPI chipset (APA102...) -> placeholder
            net = _normalize_pin_token(m.group(2))
            if net is None or net in claimed:
                continue
            _add("neopixel",
                 [Pin("VCC", "5V"), Pin("DIN", net), Pin("GND", "GND")])
            claimed_headers.add("fastled.h")

    # ─── MAX7219 LED matrix (LedControl): 5 pins VCC/GND/DIN/CLK/CS ──────
    if _INCLUDE_LEDCONTROL_RE.search(code):
        for m in _LEDCONTROL_DECL_RE.finditer(code):
            din = _normalize_pin_token(m.group(1))
            clk = _normalize_pin_token(m.group(2))
            cs = _normalize_pin_token(m.group(3))
            if None in (din, clk, cs) or din in claimed or clk in claimed or cs in claimed:
                continue
            _add("led_matrix",
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("DIN", din), Pin("CLK", clk), Pin("CS", cs)])
            claimed_headers.add("ledcontrol.h")

    # ─── TM1637 (7-seg display): VCC/GND/CLK/DIO ──────────────────────
    if _INCLUDE_TM1637_RE.search(code):
        for m in _TM1637_DECL_RE.finditer(code):
            clk = _normalize_pin_token(m.group(1))
            dio = _normalize_pin_token(m.group(2))
            if None in (clk, dio) or clk in claimed or dio in claimed:
                continue
            _add("tm1637", [Pin("VCC", "5V"), Pin("GND", "GND"),
                            Pin("CLK", clk), Pin("DIO", dio)])
            claimed_headers.add("tm1637display.h")

    # ─── HT16K33 (I2C LED matrix, Adafruit backpack): fixed I2C pinout ───
    if _INCLUDE_HT16K33_RE.search(code):
        _add("ht16k33", [Pin("VCC", "5V"), Pin("GND", "GND"),
                         Pin("SDA", "A4"), Pin("SCL", "A5")])
        claimed_headers.add("adafruit_ledbackpack.h")

    # ─── VL53L0X (ToF laser distance sensor, I2C): fixed I2C pinout ────
    if _INCLUDE_VL53L0X_RE.search(code):
        _add("vl53l0x", [Pin("VCC", "5V"), Pin("GND", "GND"),
                         Pin("SDA", "A4"), Pin("SCL", "A5")])
        claimed_headers.add("adafruit_vl53l0x.h")

    # ─── MAX30102 (heart-rate/SpO2 sensor, I2C): fixed I2C pinout ─────────
    if _INCLUDE_MAX30102_RE.search(code):
        _add("max30102", [Pin("VCC", "5V"), Pin("GND", "GND"),
                          Pin("SDA", "A4"), Pin("SCL", "A5")])
        claimed_headers.add("max30105.h")
        claimed_headers.add("max30102.h")
        claimed_headers.add("max30100.h")

    # ─── TCS34725 (RGB color sensor, I2C): fixed I2C pinout ─────────
    if _INCLUDE_TCS34725_RE.search(code):
        _add("tcs34725", [Pin("VCC", "5V"), Pin("GND", "GND"),
                          Pin("SDA", "A4"), Pin("SCL", "A5")])
        claimed_headers.add("adafruit_tcs34725.h")

    # ─── BH1750 (ambient lux meter, I2C): fixed I2C pinout ────────────────
    if _INCLUDE_BH1750_RE.search(code):
        _add("bh1750", [Pin("VCC", "5V"), Pin("GND", "GND"),
                        Pin("SDA", "A4"), Pin("SCL", "A5")])
        claimed_headers.add("bh1750.h")

    # ─── ADS1115 (16-bit ADC converter, I2C): fixed I2C pinout ───────
    if _INCLUDE_ADS1115_RE.search(code):
        _add("ads1115", [Pin("VCC", "5V"), Pin("GND", "GND"),
                         Pin("SDA", "A4"), Pin("SCL", "A5")])
        claimed_headers.add("adafruit_ads1x15.h")

    # ─── PCA9685 (16-channel servo/PWM driver, I2C): fixed I2C pinout ────────────
    if _INCLUDE_PCA9685_RE.search(code):
        _add("pca9685", [Pin("VCC", "5V"), Pin("GND", "GND"),
                         Pin("SDA", "A4"), Pin("SCL", "A5")])
        claimed_headers.add("adafruit_pwmservodriver.h")

    # ─── SH1106 (OLED display, I2C): fixed I2C pinout ───────────────────────
    if _INCLUDE_SH1106_RE.search(code):
        _add("sh1106", [Pin("VCC", "5V"), Pin("GND", "GND"),
                        Pin("SDA", "A4"), Pin("SCL", "A5")])
        claimed_headers.add("adafruit_sh110x.h")

    # ─── AHT20 (temperature/humidity sensor, I2C): fixed I2C pinout ──────
    if _INCLUDE_AHT20_RE.search(code):
        _add("aht20", [Pin("VCC", "5V"), Pin("GND", "GND"),
                       Pin("SDA", "A4"), Pin("SCL", "A5")])
        claimed_headers.add("adafruit_ahtx0.h")

    # ─── batch4: 5 fixed-pinout I2C sensors ──────────────────────────
    for _re, _ctype, _hdr in (
            (_INCLUDE_BMP280_RE,   "bmp280",   "adafruit_bmp280.h"),
            (_INCLUDE_APDS9960_RE, "apds9960", "adafruit_apds9960.h"),
            (_INCLUDE_MLX90614_RE, "mlx90614", "adafruit_mlx90614.h"),
            (_INCLUDE_SGP30_RE,    "sgp30",    "adafruit_sgp30.h"),
            (_INCLUDE_SCD30_RE,    "scd30",    "adafruit_scd30.h")):
        if _re.search(code):
            _add(_ctype, [Pin("VCC", "5V"), Pin("GND", "GND"),
                          Pin("SDA", "A4"), Pin("SCL", "A5")])
            claimed_headers.add(_hdr)

    # ─── batch4: PN532 NFC (fixed I2C + IRQ/RST extracted from the constructor) ─
    if _INCLUDE_PN532_RE.search(code):
        for m in _PN532_DECL_RE.finditer(code):
            irq = _normalize_pin_token(m.group(1))
            rst = _normalize_pin_token(m.group(2))
            if None in (irq, rst) or irq in claimed or rst in claimed:
                continue
            _add("pn532", [Pin("VCC", "5V"), Pin("GND", "GND"),
                           Pin("SDA", "A4"), Pin("SCL", "A5"),
                           Pin("IRQ", irq), Pin("RST", rst)])
            claimed_headers.add("adafruit_pn532.h")
            break

    # ─── batch4: I2C expanders with unwired pins (unwired_pins) ───
    if _INCLUDE_PCF8574_RE.search(code):
        _add("pcf8574", [Pin("VCC", "5V"), Pin("GND", "GND"),
                         Pin("SDA", "A4"), Pin("SCL", "A5")],
             {"unwired_pins": [f"P{i}" for i in range(8)]})
        claimed_headers.add("pcf8574.h")

    if _INCLUDE_MCP23017_RE.search(code):
        _add("mcp23017", [Pin("VCC", "5V"), Pin("GND", "GND"),
                          Pin("SDA", "A4"), Pin("SCL", "A5")],
             {"unwired_pins": [f"A{i}" for i in range(8)] + [f"B{i}" for i in range(8)]})
        claimed_headers.add("adafruit_mcp23x17.h")

    # ─── batch4: MAX6675 SPI thermocouple (SCK/CS/SO extracted) ───────────
    if _INCLUDE_MAX6675_RE.search(code):
        for m in _MAX6675_DECL_RE.finditer(code):
            sck = _normalize_pin_token(m.group(1))
            cs = _normalize_pin_token(m.group(2))
            so = _normalize_pin_token(m.group(3))
            if None in (sck, cs, so) or sck in claimed or cs in claimed or so in claimed:
                continue
            _add("max6675", [Pin("VCC", "5V"), Pin("GND", "GND"),
                             Pin("SCK", sck), Pin("CS", cs), Pin("SO", so)])
            claimed_headers.add("max6675.h")

    # ─── batch5: 8 fixed-pinout I2C sensors ──────────────────────────
    for _re, _ctype, _hdr in (
            (_INCLUDE_MCP9808_RE,  "mcp9808",  "adafruit_mcp9808.h"),
            (_INCLUDE_SI7021_RE,   "si7021",   "adafruit_si7021.h"),
            (_INCLUDE_ADXL345_RE,  "adxl345",  "adafruit_adxl345_u.h"),
            (_INCLUDE_HMC5883_RE,  "hmc5883l", "adafruit_hmc5883_u.h"),
            (_INCLUDE_MCP4725_RE,  "mcp4725",  "adafruit_mcp4725.h"),
            (_INCLUDE_INA260_RE,   "ina260",   "adafruit_ina260.h"),
            (_INCLUDE_AS5600_RE,   "as5600",   "as5600.h"),
            (_INCLUDE_VEML6075_RE, "veml6075", "adafruit_veml6075.h")):
        if _re.search(code):
            _add(_ctype, [Pin("VCC", "5V"), Pin("GND", "GND"),
                          Pin("SDA", "A4"), Pin("SCL", "A5")])
            claimed_headers.add(_hdr)

    # ─── batch6: 5 fixed-pinout I2C sensors ──────────────────────────
    for _re, _ctype, _hdr in (
            (_INCLUDE_BNO055_RE,   "bno055",   "adafruit_bno055.h"),
            (_INCLUDE_MCP9600_RE,  "mcp9600",  "adafruit_mcp9600.h"),
            (_INCLUDE_MAX17043_RE, "max17043", "adafruit_max1704x.h"),
            (_INCLUDE_AMG8833_RE,  "amg8833",  "adafruit_amg88xx.h"),
            (_INCLUDE_PM25_RE,     "pm25",     "adafruit_pm25aqi.h")):
        if _re.search(code):
            _add(_ctype, [Pin("VCC", "5V"), Pin("GND", "GND"),
                          Pin("SDA", "A4"), Pin("SCL", "A5")])
            claimed_headers.add(_hdr)

    # ─── batch6: nRF24L01 (SPI 3.3V) — mfrc522 model ──────────────────
    if _INCLUDE_RF24_RE.search(code):
        for m in _RF24_DECL_RE.finditer(code):
            ce  = _normalize_pin_token(m.group(1))
            csn = _normalize_pin_token(m.group(2))
            if None in (ce, csn) or ce in claimed or csn in claimed:
                continue
            _add("nrf24l01",
                 [Pin("VCC", "3V3"), Pin("GND", "GND"),
                  Pin("CE", ce), Pin("CSN", csn),
                  Pin("SCK", "D13"), Pin("MOSI", "D11"), Pin("MISO", "D12")])
            claimed_headers.add("rf24.h")
            break

    # ─── batch7: DRV2605 haptic (fixed-I2C) ───────────────────────────
    if _INCLUDE_DRV2605_RE.search(code):
        _add("drv2605", [Pin("VCC", "5V"), Pin("GND", "GND"),
                         Pin("SDA", "A4"), Pin("SCL", "A5")])
        claimed_headers.add("adafruit_drv2605.h")

    # ─── batch7: TM1638 (display+buttons, 3 GPIO STB/CLK/DIO) ─────────
    if _INCLUDE_TM1638_RE.search(code):
        for m in _TM1638_DECL_RE.finditer(code):
            stb = _normalize_pin_token(m.group(1))
            clk = _normalize_pin_token(m.group(2))
            dio = _normalize_pin_token(m.group(3))
            if None in (stb, clk, dio) or stb in claimed or clk in claimed or dio in claimed:
                continue
            _add("tm1638", [Pin("VCC", "5V"), Pin("GND", "GND"),
                            Pin("STB", stb), Pin("CLK", clk), Pin("DIO", dio)])
            claimed_headers.add("tm1638plus.h")
            break

    # ─── batch7: Nokia 5110 / PCD8544 (soft SPI LCD, 3.3V) ──────────────
    if _INCLUDE_PCD8544_RE.search(code):
        for m in _PCD8544_DECL_RE.finditer(code):
            clk = _normalize_pin_token(m.group(1))
            din = _normalize_pin_token(m.group(2))
            dc  = _normalize_pin_token(m.group(3))
            cs  = _normalize_pin_token(m.group(4))
            rst = _normalize_pin_token(m.group(5))
            if None in (clk, din, dc, cs, rst):
                continue
            _add("pcd8544", [Pin("VCC", "3V3"), Pin("GND", "GND"),
                             Pin("CLK", clk), Pin("DIN", din), Pin("DC", dc),
                             Pin("CS", cs), Pin("RST", rst)])
            claimed_headers.add("adafruit_pcd8544.h")
            break

    # ─── batch7: SSD1351 (color OLED hard SPI, CS/DC/RST extracted) ────
    if _INCLUDE_SSD1351_RE.search(code):
        for m in _SSD1351_DECL_RE.finditer(code):
            cs  = _normalize_pin_token(m.group(1))
            dc  = _normalize_pin_token(m.group(2))
            rst = _normalize_pin_token(m.group(3))
            if None in (cs, dc, rst) or cs in claimed or dc in claimed or rst in claimed:
                continue
            _add("ssd1351", [Pin("VCC", "5V"), Pin("GND", "GND"),
                             Pin("CS", cs), Pin("DC", dc), Pin("RST", rst),
                             Pin("SCK", "D13"), Pin("MOSI", "D11")])
            claimed_headers.add("adafruit_ssd1351.h")
            break

    # ─── Color TFT ST7735 / ST7789 (SPI): CS/DC/RST extracted + fixed SPI ─
    for _re, _ctype, _hdr, _decl in (
            (_INCLUDE_ST7735_RE, "st7735", "adafruit_st7735.h", _ST7735_DECL_RE),
            (_INCLUDE_ST7789_RE, "st7789", "adafruit_st7789.h", _ST7789_DECL_RE)):
        if _re.search(code):
            for m in _decl.finditer(code):
                cs = _normalize_pin_token(m.group(1))
                dc = _normalize_pin_token(m.group(2))
                rst = _normalize_pin_token(m.group(3))
                if None in (cs, dc, rst) or cs in claimed or dc in claimed or rst in claimed:
                    continue
                _add(_ctype, [Pin("VCC", "5V"), Pin("GND", "GND"), Pin("CS", cs),
                              Pin("DC", dc), Pin("RST", rst),
                              Pin("SCK", "D13"), Pin("MOSI", "D11")])
                claimed_headers.add(_hdr)

    # ─── MAX31855 (SPI thermocouple): SCLK/CS/MISO extracted ─────────────
    if _INCLUDE_MAX31855_RE.search(code):
        for m in _MAX31855_DECL_RE.finditer(code):
            sclk = _normalize_pin_token(m.group(1))
            cs = _normalize_pin_token(m.group(2))
            miso = _normalize_pin_token(m.group(3))
            if None in (sclk, cs, miso) or sclk in claimed or cs in claimed or miso in claimed:
                continue
            _add("max31855", [Pin("VCC", "5V"), Pin("GND", "GND"),
                              Pin("SCLK", sclk), Pin("CS", cs), Pin("MISO", miso)])
            claimed_headers.add("adafruit_max31855.h")

    # ─── HX711 (load cell / scale): DT/SCK from begin() ──────
    # The `HX711 scale;` constructor is bare; the pins are passed to
    # `scale.begin(dout, sck)`.
    if _INCLUDE_HX711_RE.search(code):
        for dm in _HX711_DECL_RE.finditer(code):
            var = dm.group(1)
            bm = re.search(
                rf"\b{re.escape(var)}\s*\.\s*begin\s*\(\s*([^,]+?)\s*,\s*([^,)]+?)\s*\)",
                code)
            if not bm:
                continue
            dt = _normalize_pin_token(bm.group(1))
            sck = _normalize_pin_token(bm.group(2))
            if None in (dt, sck) or dt in claimed or sck in claimed:
                continue
            _add("hx711", [Pin("VCC", "5V"), Pin("GND", "GND"),
                           Pin("DT", dt), Pin("SCK", sck)])
            claimed_headers.add("hx711.h")

    # ─── 74HC595 (shift register, lib): DATA/CLK/LATCH + VCC/GND ────
    if _INCLUDE_SR595_RE.search(code):
        for m in _SR595_DECL_RE.finditer(code):
            data = _normalize_pin_token(m.group(1))
            clk = _normalize_pin_token(m.group(2))
            latch = _normalize_pin_token(m.group(3))
            if None in (data, clk, latch) or data in claimed or clk in claimed or latch in claimed:
                continue
            _add("sr74hc595", [Pin("VCC", "5V"), Pin("GND", "GND"),
                               Pin("DATA", data), Pin("CLK", clk), Pin("LATCH", latch)],
                 {"unwired_pins": ["QA", "QB", "QC", "QD", "QE", "QF", "QG", "QH"]})
            claimed_headers.add("shiftregister74hc595.h")

    # ─── NewPing: library alternative for HC-SR04 ──────────────
    if _INCLUDE_NEWPING_RE.search(code):
        for m in _NEWPING_DECL_RE.finditer(code):
            trig = _normalize_pin_token(m.group(1))
            echo = _normalize_pin_token(m.group(2))
            if trig is None or echo is None or trig in claimed or echo in claimed:
                continue
            # Reuse the "hcsr04" type from CATALOG (same physical part).
            _add("hcsr04",
                 [Pin("VCC", "5V"), Pin("TRIG", trig),
                  Pin("ECHO", echo), Pin("GND", "GND")])

    # ─── Rotary encoder (CLK, DT) ───────────────────────────────────────
    if _INCLUDE_ENCODER_RE.search(code):
        for m in _ENCODER_DECL_RE.finditer(code):
            clk = _normalize_pin_token(m.group(1))
            dt  = _normalize_pin_token(m.group(2))
            if clk is None or dt is None or clk in claimed or dt in claimed:
                continue
            _add("encoder",
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("CLK", clk), Pin("DT", dt)])

    # ─── MFRC522 (RFID, SPI: variable SS and RST, fixed MOSI/MISO/SCK) ──
    if _INCLUDE_MFRC522_RE.search(code):
        for m in _MFRC522_DECL_RE.finditer(code):
            ss  = _normalize_pin_token(m.group(1))
            rst = _normalize_pin_token(m.group(2))
            if ss is None or rst is None or ss in claimed or rst in claimed:
                continue
            # 8 pins: VCC, RST, GND, IRQ (NC), MISO=D12, MOSI=D11, SCK=D13, SDA(SS)
            _add("mfrc522",
                 [Pin("VCC", "3V3"), Pin("RST", rst), Pin("GND", "GND"),
                  Pin("IRQ", "GND"), Pin("MISO", "D12"), Pin("MOSI", "D11"),
                  Pin("SCK", "D13"), Pin("SDA", ss)])

    # ─── HX711 (load-cell amplifier) ────────────────────────────────────
    # TODO #47: found by the corpus sweep of 2026-08-10 — the OFFICIAL example
    # the app hands to the model produced NOTHING at all. Nothing to guess
    # here: `HX711.h` is a unique signature, and the two pins are named by
    # `begin(DT, SCK)` (the constructor takes none — that is exactly the form
    # the detector missed, cf. the four occurrences of this motif in the
    # August QA). VCC/GND are fixed.
    if _INCLUDE_HX711_RE.search(code):
        for m in _HX711_BEGIN_RE.finditer(code):
            dt  = _normalize_pin_token(m.group(1))
            sck = _normalize_pin_token(m.group(2))
            if dt is None or sck is None or dt in claimed or sck in claimed:
                continue
            _add("hx711",
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("DT", dt), Pin("SCK", sck)])

    # ─── ULN2003 driver for 28BYJ-48 stepper (standard Stepper lib) ─────
    # The ULN2003 driver is on the BB (10 exposed pins: VCC=BAT, GND,
    # IN1-4 on the Arduino side + OUT1-4 on the motor side). The 28BYJ-48
    # motor itself is off-BB, its 4 phases connected to OUT1-4 via internal
    # nets that the inference rule wires cleanly (also adds
    # the stepper_motor + battery_external).
    if _INCLUDE_STEPPER_RE.search(code):
        for m in _STEPPER_DECL_RE.finditer(code):
            pins_in = [_normalize_pin_token(m.group(i)) for i in (1, 2, 3, 4)]
            if any(p is None or p in claimed for p in pins_in):
                continue
            # Placeholders for the OUTs (the rule fills them with the same
            # internal nets as the stepper_motor phases).
            _add("uln2003",
                 [Pin("VCC", "BAT_5V"), Pin("GND", "GND"),
                  Pin("IN1", pins_in[0]), Pin("IN2", pins_in[1]),
                  Pin("IN3", pins_in[2]), Pin("IN4", pins_in[3]),
                  Pin("OUT1", ""), Pin("OUT2", ""),
                  Pin("OUT3", ""), Pin("OUT4", "")])

    # ─── A4988 driver for NEMA17 (AccelStepper lib, DRIVER mode) ────────
    # The A4988 driver is a DIP-16 placed on the BB. Arduino side: STEP, DIR,
    # VDD (5V), GND. Motor side: VMOT (battery), 1A/1B/2A/2B (the 4
    # terminals of the NEMA17 coils, tied via internal nets that the
    # inference rule fills with the pins of the added nema17).
    if _INCLUDE_ACCELSTEPPER_RE.search(code):
        for m in _ACCELSTEPPER_DRIVER_DECL_RE.finditer(code):
            step_pin = _normalize_pin_token(m.group(1))
            dir_pin = _normalize_pin_token(m.group(2))
            if (step_pin is None or dir_pin is None
                    or step_pin in claimed or dir_pin in claimed):
                continue
            # Control pins wired explicitly (vs floating):
            # - MS1/MS2/MS3 -> GND by default = "Full step" mode (full
            #   step). Mutable via the a4988_microstepping gear.
            # - ENA -> GND: driver always enabled (active LOW). On the
            #   official Pololu an internal pulldown is enough but on the
            #   clones it's not guaranteed -> explicit.
            # - RST -> 5V: never in reset (active LOW). No internal
            #   bridge on the standard green Pololu.
            # - SLP -> 5V: never in sleep (active LOW). Same.
            _add("a4988",
                 [Pin("STEP", step_pin), Pin("DIR", dir_pin),
                  Pin("VDD", "5V"), Pin("GND", "GND"),
                  Pin("VMOT", "BAT_5V"),
                  Pin("ENA", "GND"),
                  Pin("RST", "5V"), Pin("SLP", "5V"),
                  Pin("MS1", "GND"), Pin("MS2", "GND"), Pin("MS3", "GND"),
                  Pin("1A", ""), Pin("1B", ""),
                  Pin("2A", ""), Pin("2B", "")])

    # A4988 manual step (without AccelStepper.h): detection on the
    # PIN_STEP / PIN_DIR / PIN_ENABLE naming convention (and variants). We only
    # trigger if AccelStepper is not used -- otherwise the previous block
    # already created the component. See inference.py which automatically adds
    # a NEMA17 + battery_external on every detected A4988.
    #
    # IMPORTANT: matches on `original_code` (before aliasing) because
    # `_resolve_aliases` substitutes the constant NAME (PIN_STEP)
    # with its literal value (D3), making identification impossible
    # on the aliased code passed to `_detect_libraries`.
    if not _INCLUDE_ACCELSTEPPER_RE.search(original_code):
        step_m = _A4988_MANUAL_STEP_RE.search(original_code)
        dir_m = _A4988_MANUAL_DIR_RE.search(original_code)
        if (step_m is not None and dir_m is not None
                and _A4988_MANUAL_CONFIRM_RE.search(original_code)):
            step_pin = _normalize_pin_token(step_m.group(1))
            dir_pin = _normalize_pin_token(dir_m.group(1))
            if (step_pin is not None and dir_pin is not None
                    and step_pin not in claimed
                    and dir_pin not in claimed):
                # ENABLE optional: if declared and the pin is valid and not claimed,
                # wire it to the corresponding Arduino pin; otherwise
                # ENA -> GND (default behavior of the AccelStepper
                # pattern, functionally equivalent when the
                # code forces ENABLE LOW in setup()).
                ena_pin = "GND"
                en_m = _A4988_MANUAL_EN_RE.search(original_code)
                if en_m is not None:
                    candidate = _normalize_pin_token(en_m.group(1))
                    if candidate is not None and candidate not in claimed:
                        ena_pin = candidate
                _add("a4988",
                     [Pin("STEP", step_pin), Pin("DIR", dir_pin),
                      Pin("VDD", "5V"), Pin("GND", "GND"),
                      Pin("VMOT", "BAT_5V"),
                      Pin("ENA", ena_pin),
                      Pin("RST", "5V"), Pin("SLP", "5V"),
                      Pin("MS1", "GND"), Pin("MS2", "GND"), Pin("MS3", "GND"),
                      Pin("1A", ""), Pin("1B", ""),
                      Pin("2A", ""), Pin("2B", "")])

    # ─── TFT ILI9341 (SPI, variable CS/DC/RST) ──────────────────────────
    if _INCLUDE_TFT_RE.search(code):
        for m in _TFT_DECL_RE.finditer(code):
            cs  = _normalize_pin_token(m.group(1))
            dc  = _normalize_pin_token(m.group(2))
            rst = _normalize_pin_token(m.group(3))
            if any(v is None or v in claimed for v in (cs, dc, rst)):
                continue
            _add("ili9341",
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("CS", cs), Pin("RESET", rst), Pin("DC", dc),
                  Pin("MOSI", "D11"), Pin("SCK", "D13"), Pin("LED", "5V")])

    # ─── Keypad matrix (extracts rowPins / colPins) ───────────────────────
    if _INCLUDE_KEYPAD_RE.search(code):
        row_m = _KEYPAD_ROW_PINS_RE.search(code)
        col_m = _KEYPAD_COL_PINS_RE.search(code)
        if row_m is not None and col_m is not None:
            def _parse_pin_list(s: str) -> list[str]:
                out = []
                for tok in re.split(r"\s*,\s*", s.strip()):
                    n = _normalize_pin_token(tok)
                    if n is not None:
                        out.append(n)
                return out
            rows = _parse_pin_list(row_m.group(1))
            cols = _parse_pin_list(col_m.group(1))
            if rows and cols and not any(p in claimed for p in rows + cols):
                pins = [Pin(f"ROW{i+1}", n) for i, n in enumerate(rows)]
                pins += [Pin(f"COL{i+1}", n) for i, n in enumerate(cols)]
                _add("keypad", pins,
                     {"rows": str(len(rows)), "cols": str(len(cols))})

    # ─── IR receiver (TSOP38xx / VS1838) ─────────────────────────────────
    if _INCLUDE_IRREMOTE_RE.search(code):
        # Les deux ecritures de la lib : constructeur (v2/v3) et objet global
        # `IrReceiver` (v4). Une seule des deux est presente dans un sketch
        # donne ; les parcourir toutes les deux evite d'avoir a deviner la
        # version depuis l'en-tete.
        for rx in (_IRRECV_DECL_RE, _IRRECEIVER_BEGIN_RE):
            for m in rx.finditer(code):
                net = _normalize_pin_token(m.group(1))
                if net is None or net in claimed:
                    continue
                _add("ir_receiver",
                     [Pin("OUT", net), Pin("GND", "GND"), Pin("VCC", "5V")])

    # ─── DS18B20 (OneWire temperature, DATA pin + 4.7k pull-up recommended) ──
    # The 4.7k R between DATA and VCC is added by the inference rule
    # `_apply_ds18b20_pullups` (similar to the DHT22 pattern).
    if _INCLUDE_DS18B20_RE.search(code):
        for m in _ONEWIRE_DECL_RE.finditer(code):
            net = _normalize_pin_token(m.group(1))
            if net is None or net in claimed:
                continue
            _add("ds18b20",
                 [Pin("VCC", "5V"), Pin("DATA", net), Pin("GND", "GND")])

    # ─── SoftwareSerial: pool shared between TinyGPS++ and MH-Z19 ─────────
    # We collect all the declarations in document order and
    # distribute them: 1st unclaimed instance -> 1st UART lib present
    # (TinyGPS or MHZ19), 2nd instance -> 2nd lib if still present.
    soft_serials: list[tuple[str, str]] = []
    for m in _SOFTWARE_SERIAL_DECL_RE.finditer(code):
        rx = _normalize_pin_token(m.group(1))
        tx = _normalize_pin_token(m.group(2))
        if rx is not None and tx is not None \
                and rx not in claimed and tx not in claimed:
            soft_serials.append((rx, tx))

    def _take_soft_serial() -> tuple[str, str] | None:
        return soft_serials.pop(0) if soft_serials else None

    # TinyGPS++: GPS module via SoftwareSerial. SoftwareSerial(RX_arduino,
    # TX_arduino); the module's TX wires to RX_arduino, and vice versa.
    if _INCLUDE_TINYGPS_RE.search(code):
        pair = _take_soft_serial()
        if pair is not None:
            rx_ardu, tx_ardu = pair
            _add("gps",
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("TX", rx_ardu), Pin("RX", tx_ardu)])

    # MH-Z19 (UART CO2 sensor). Same UART pattern as GPS.
    if _INCLUDE_MHZ19_RE.search(code):
        pair = _take_soft_serial()
        if pair is not None:
            rx_ardu, tx_ardu = pair
            _add("mhz19",
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("TX", rx_ardu), Pin("RX", tx_ardu)])

    # DFPlayer Mini (UART MP3 module): drives a bare SoftwareSerial. Same pins
    # as the generic uart_module (VCC/GND + crossed TX/RX), but dedicated type
    # `dfplayer` -> no duplicate uart_module, header claimed to avoid the
    # `dfrobotdfplayermini` placeholder.
    if _INCLUDE_DFPLAYER_RE.search(code):
        pair = _take_soft_serial()
        if pair is not None:
            rx_ardu, tx_ardu = pair
            _add("dfplayer",
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("TX", rx_ardu), Pin("RX", tx_ardu)])
        claimed_headers.add("dfrobotdfplayermini.h")

    # Fingerprint sensor (UART): drives a SoftwareSerial, like DFPlayer.
    if _INCLUDE_FINGERPRINT_RE.search(code):
        pair = _take_soft_serial()
        if pair is not None:
            rx_ardu, tx_ardu = pair
            _add("fingerprint",
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("TX", rx_ardu), Pin("RX", tx_ardu)])
        claimed_headers.add("adafruit_fingerprint.h")

    # ─── Generic UART: one module per remaining SoftwareSerial instance ──
    # After the known UART libs (GPS, MH-Z19) have consumed the pool.
    # Covers the HC-05/HC-06 declared as a bare SoftwareSerial (without a lib) and any
    # unknown UART lib. Name: taken from the single unknown #include if not
    # ambiguous, otherwise "uart_module".
    if soft_serials:
        existing = {c.type for c in components}
        unknown_headers: list[str] = []
        for inc in _INCLUDE_ANY_RE.finditer(code):
            h = inc.group(1)
            base = h.replace("\\", "/").rsplit("/", 1)[-1].lower()
            if base in _KNOWN_HEADERS_LOWER or base in claimed_headers:
                continue
            if _clean_lib_name(h, default="uart_module") in existing:
                continue
            unknown_headers.append(h)
        single_named = len(soft_serials) == 1 and len(unknown_headers) == 1
        # Accepted limits (very rare cases): if N>=2 SS instances AND N>=2
        # unknown includes, we create N uart_module but claim no
        # header -> the includes can also appear as placeholders
        # (ambiguous: which SS for which lib?). And an unknown non-UART header
        # (e.g. fastled.h falling into APA102) can name the module wrongly. We
        # keep the conservative behavior: naming only if 1 SS + 1
        # unknown include, otherwise "uart_module".
        for rx_ardu, tx_ardu in soft_serials:
            if single_named:
                ctype = _clean_lib_name(unknown_headers[0], default="uart_module")
                base = unknown_headers[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
                claimed_headers.add(base)
            else:
                ctype = "uart_module"
            _add(ctype,
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("TX", rx_ardu), Pin("RX", tx_ardu)])

    # ─── LoRa SX1276/1278 (SPI + 3 controls: NSS, NRESET, DIO0) ────────
    # Lib default: NSS=D10, NRESET=D9, DIO0=D2. Override via LoRa.setPins().
    if _INCLUDE_LORA_RE.search(code):
        setp_m = _LORA_SETPINS_RE.search(code)
        if setp_m is not None:
            nss   = _normalize_pin_token(setp_m.group(1)) or "D10"
            nrst  = _normalize_pin_token(setp_m.group(2)) or "D9"
            dio0  = _normalize_pin_token(setp_m.group(3)) or "D2"
        else:
            nss, nrst, dio0 = "D10", "D9", "D2"
        if not any(p in claimed for p in (nss, nrst, dio0)):
            _add("lora_sx1276",
                 [Pin("VCC", "3V3"), Pin("GND", "GND"),
                  Pin("NSS", nss), Pin("NRESET", nrst), Pin("DIO0", dio0),
                  Pin("MOSI", "D11"), Pin("MISO", "D12"), Pin("SCK", "D13")])

    # ─── MQ-135 (analog gas sensor): heuristic detection on name ─────
    # Looks for `#define MQ135_PIN A0` or `const int gas_value = A0`. The A
    # pin is CLAIMED to prevent it from being reclassified as a potentiometer
    # by parse_fallback.
    #
    # ⚠️ Sur `original_code`, PAS sur `code` (TODO #47, 2026-08-10). Ce
    # detecteur s'appuie sur le NOM de la constante, et la phase 0 de
    # `parse_fallback` resout justement les alias : `const int MQ135_PIN = A0;`
    # devient `const int A0 = A0;`. L'etape d'avant effacait la seule chose sur
    # laquelle celle-ci travaille — l'exemple officiel du corpus sortait en
    # potentiometre. C'est le motif du chantier sous une forme inattendue : ce
    # n'est pas le modele qui ecrivait autrement, c'est nous qui reecrivions
    # son code avant de le lire.
    for rx in (_MQ135_DEFINE_RE, _MQ135_CONST_RE):
        m = rx.search(original_code or code)
        if m is None:
            continue
        net = _normalize_pin_token(m.group(2))
        if net is None or net in claimed:
            continue
        # La REFERENCE ecrite dans le code decide du type (2026-08-27).
        # `m.group(1)` porte le nom de la constante — `MQ137_PIN` — donc le
        # numero de la piece, et il etait CAPTURE puis jete : la ligne
        # posait « mq135 » en dur. Mesure d'avant correctif : un
        # `#define MQ2_PIN A0` dessinait un MQ-135, alors que le MQ-2 est le
        # capteur de gaz le plus courant des kits debutants et qu'il a une
        # identite au registre depuis toujours. Ce n'etait pas une signature
        # manquante, c'etait une signature lue puis perdue.
        _add(_mq_type_for(m.group(1)),
             [Pin("VCC", "5V"), Pin("AOUT", net), Pin("GND", "GND")])
        break

    # ─── Buzzer (tone()) ─────────────────────────────────────────────────
    for m in _TONE_CALL_RE.finditer(code):
        net = _normalize_pin_token(m.group(1))
        if net is None or net in claimed:
            continue
        _add("buzzer", [Pin("+", net), Pin("-", "GND")])
        break  # one buzzer is enough (rare to have several)

    # ─── Generic I2C fallback (SAFETY NET — MUST stay last) ──────────
    # Every unknown #include, in an I2C sketch, becomes a visible 4-pin
    # module (instead of being ignored). Covers future I2C sensors without
    # a dedicated signature. Precedence: runs after all the detectors +
    # excludes _KNOWN_HEADERS_LOWER -> no duplicates.
    #
    # This wiring is PRESUMED, not read from the code: we only know the sketch
    # talks I2C, not that THIS lib does, nor on which pins. `presumed_wiring`
    # keeps it out of `_is_signature_detected` (never presented as code-certain)
    # and raises the `presumed_i2c_wiring` warning + unlocks the gear so the
    # user can correct it (revue 2026-07-29).
    if _INCLUDE_WIRE_RE.search(code) or _WIRE_ACTIVITY_RE.search(code):
        existing_types = {c.type for c in components}
        for inc in _INCLUDE_ANY_RE.finditer(code):
            base = inc.group(1).replace("\\", "/").rsplit("/", 1)[-1].lower()
            if base in _KNOWN_HEADERS_LOWER or base in claimed_headers:
                continue
            # Un en-tete de config/donnees/systeme n'est pas un composant.
            if _is_non_component_header(inc.group(1)):
                continue
            type_id = _clean_lib_name(inc.group(1))
            if type_id in existing_types:
                continue
            existing_types.add(type_id)
            _add(type_id,
                 [Pin("VCC", "5V"), Pin("GND", "GND"),
                  Pin("SDA", "A4"), Pin("SCL", "A5")],
                 {"presumed_wiring": True, "header": inc.group(1)})

    # ─── UNIVERSAL net: placeholder for every unrecognized #include ──────
    # MUST stay VERY LAST (after the I2C fallback). Without a Wire gate:
    # every include outside core libs/signatures that produced NO component
    # (neither catalog, nor signature, nor I2C module above) becomes a generic
    # UN-wired box (pins with empty net "" -> no wire: the router
    # skips orphan nets). Marked `unrecognized` for the warning
    # (extract_netlist) and the future "click to specify the component".
    existing_types = {c.type for c in components}
    for inc in _INCLUDE_ANY_RE.finditer(code):
        header = inc.group(1)
        base = header.replace("\\", "/").rsplit("/", 1)[-1].lower()
        if base in _KNOWN_HEADERS_LOWER or base in claimed_headers:
            continue
        # Idem : pas de boite fantome pour `arduino_secrets.h` ou `avr/power.h`.
        if _is_non_component_header(header):
            continue
        type_id = _clean_lib_name(header, default="module")
        if type_id in existing_types:
            continue
        existing_types.add(type_id)
        attrs = {"unrecognized": True, "header": header}
        # Indice utile SANS inventer de câblage : les broches passées au
        # constructeur de cette lib inconnue. On ne les relie pas (impossible de
        # savoir quelle broche fait quoi) — elles partent dans le warning.
        ctor_pins = _constructor_pins_for(code, type_id)
        if ctor_pins:
            attrs["constructor_pins"] = ctor_pins
        _add(type_id,
             [Pin(str(i + 1), "") for i in range(_PLACEHOLDER_PIN_COUNT)],
             attrs)

    return components, claimed


def _normalize_pin_token(tok: str) -> str | None:
    """Converts a token (e.g. `13`, `LED_BUILTIN`, `A0`, `D2`) into a standard net.

    Raw numbers are mapped to Dn for digital pins (0..13).
    Analog pins are recognized as-is (A0..A5).
    Unknown identifiers (variables) are ignored.
    """
    if tok == "LED_BUILTIN":
        return "D13"
    if re.fullmatch(r"[0-9]+", tok):
        n = int(tok)
        if 0 <= n <= 13:
            return f"D{n}"
        return None
    if re.fullmatch(r"[Aa][0-5]", tok):
        return tok.upper()
    if re.fullmatch(r"[Dd]\d+", tok):
        return tok.upper()
    return None


def _classify_pin_role(code: str, pin_token: str) -> str:
    """Guesses the usage type: 'output' / 'input' / 'analog' / 'pwm'.

    Simple heuristic: if pinMode(... , INPUT_PULLUP|INPUT) → input,
    else if digitalWrite/analogWrite → output, else → unknown.
    """
    for m in _PINMODE_RE.finditer(code):
        if m.group(1) == pin_token:
            mode = m.group(2)
            if mode in ("INPUT", "INPUT_PULLUP"):
                return "input"
            return "output"
    if _DIGITAL_WRITE_RE.search(code) and any(
        g.group(1) == pin_token for g in _DIGITAL_WRITE_RE.finditer(code)
    ):
        return "output"
    if _ANALOG_WRITE_RE.search(code) and any(
        g.group(1) == pin_token for g in _ANALOG_WRITE_RE.finditer(code)
    ):
        return "pwm"
    if _ANALOG_READ_RE.search(code) and any(
        g.group(1) == pin_token for g in _ANALOG_READ_RE.finditer(code)
    ):
        return "analog"
    if _DIGITAL_READ_RE.search(code) and any(
        g.group(1) == pin_token for g in _DIGITAL_READ_RE.finditer(code)
    ):
        return "input"
    return "unknown"


def _has_input_pullup(code: str, pin_token: str) -> bool:
    for m in _PINMODE_RE.finditer(code):
        if m.group(1) == pin_token and m.group(2) == "INPUT_PULLUP":
            return True
    return False


def parse_fallback(
    code: str,
    board_id: str | None = None,
    prompt: str = "",
    context: str = "",
) -> tuple[list[Component], bool]:
    """Reconstructs an approximate netlist from the source code.

    Returns (components, fallback_used). When no pin is detected,
    components = [] and fallback_used = False (nothing to infer).

    Args:
      code     : complete .ino source.
      board_id : catalog id (e.g. "arduino_uno_r3"). Optional for
                 backward compat; used by Strategy 4 of the DC motor
                 grouping (hardware fallback via boards.json capabilities).
      prompt   : user prompt. Optional for backward compat; used
                 by S4 as a guardrail (triggers only if
                 'motor' + chip mentioned).
      context  : content of the project context file. Same usage as prompt.

    Internal pipeline:
      0. Resolution of the const int / #define aliases (POT -> A0, etc.)
      1. Rich library detection (Servo, DHT, ...) via `_detect_libraries`
         which claims the pins involved.
      2. Generic heuristic on the non-claimed pins.
    """
    if not code.strip():
        return [], False

    # Phase 0a: normalisations d'ECRITURE, AVANT que `original_code` ne soit
    # fige pour que les detecteurs travaillant sur la version non aliasee en
    # beneficient aussi. Deux formes que le modele produit legitimement et que
    # personne ne reconnaissait (cf. les deux helpers).
    code = _normalize_include_extensions(code)
    code = _normalize_ctor_assignment(code)

    # Phase 0: resolve the aliases (const int POT = A0; analogRead(POT) -> A0)
    original_code = code
    code = _resolve_aliases(code)

    # Phase 1: rich libraries (pins captured here are excluded from the generic pass).
    # `original_code` lets the detectors that depend on the constant names
    # (e.g. A4988 manual via `PIN_STEP`) match before aliasing
    # substitutes them with their literal value.
    lib_components, claimed_pins = _detect_libraries(code, original_code)

    pins_seen: dict[str, str] = {}   # pin_token -> role
    for rx in (_PINMODE_RE, _DIGITAL_WRITE_RE, _DIGITAL_READ_RE,
               _ANALOG_READ_RE, _ANALOG_WRITE_RE, _TONE_RE,
               _SERVO_ATTACH_RE):
        for m in rx.finditer(code):
            tok = m.group(1)
            net = _normalize_pin_token(tok)
            if net is None or net in claimed_pins:
                continue
            role = _classify_pin_role(code, tok)
            # Servo attach -> role pwm/output
            if rx is _SERVO_ATTACH_RE and role == "unknown":
                role = "output"
            if rx is _TONE_RE and role == "unknown":
                role = "output"
            pins_seen.setdefault(net, role)

    # Pins resolved via S2 (helper params=pins) and S3 (motorNum dispatch).
    # Needed for the typical case of factored code like
    # `setMotor(uint8_t pwmPin, ...)` where the calls pass pin literals
    # that are not attached to any direct `pinMode(LITERAL, OUTPUT)` (e.g.
    # init via a loop `for (i=0; i<N; i++) pinMode(outs[i], OUTPUT);`).
    # Without this injection, pins_seen stays empty -> 0 components -> silent
    # schematic. Idempotent: setdefault preserves the already-resolved roles.
    s2_pwm, s2_digital, _ = _resolve_indirect_writes(code)
    s3_pwm, s3_digital, _ = _resolve_local_dispatch_writes(code)
    for net in (s2_pwm | s3_pwm):
        if net in claimed_pins:
            continue
        pins_seen.setdefault(net, "pwm")
    for net in (s2_digital | s3_digital):
        if net in claimed_pins:
            continue
        pins_seen.setdefault(net, "output")

    # LED_BUILTIN: usually lit in Blink, we guess output.
    if _LED_BUILTIN_RE.search(code):
        pins_seen.setdefault("D13", "output")

    components: list[Component] = []

    # Simple heuristic: output -> LED, input -> button, analog -> pot.
    counters = {"led": 0, "button": 0, "pot": 0, "module": 0}

    for net in sorted(pins_seen.keys(), key=_sort_pin_key):
        role = pins_seen[net]
        # PWM (analogWrite) is a special case of OUTPUT (digital
        # output with a variable duty cycle). For the components
        # of our catalog (LED dimming, frequency buzzer), it's
        # equivalent to output; so we treat it the same.
        if role in ("output", "pwm"):
            counters["led"] += 1
            ref = f"D{counters['led']}"
            # Generic OUTPUT = ambiguous (LED? buzzer? relay?). We
            # classify it as a LED by default but mark confidence low so
            # the next layer (disambiguation or modal UI) can reclassify
            # or confirm it. NO colour is set: nothing in the code can
            # tell us one, and only the prompt can (cf the `color`
            # annotation in the disambiguation step).
            components.append(Component(
                ref=ref, type="led", fn_id="",
                pins=[Pin("A", net), Pin("K", "GND")],
                attributes={"_confidence": "low"},
                inferred=True,
            ))
        elif role == "input":
            counters["button"] += 1
            ref = f"S{counters['button']}"
            components.append(Component(
                ref=ref, type="button", fn_id="",
                pins=[Pin("A", net), Pin("B", "GND")],
                attributes={
                    "momentary": "true",
                    "pull": "internal" if _has_input_pullup(code, _denormalize(net)) else "external",
                },
                inferred=True,
            ))
        elif role == "analog":
            counters["pot"] += 1
            ref = f"P{counters['pot']}"
            components.append(Component(
                ref=ref, type="potentiometer", fn_id="",
                pins=[Pin("A", "5V"), Pin("W", net), Pin("B", "GND")],
                # `analogRead(A0)` says NOTHING about what is wired to the pin.
                # A 10k pot is the most common thing in a beginner kit, so it
                # stays the default -- but it is a GUESS, and `presumed_analog`
                # is what makes it say so (4th safety net, missed by the
                # 2026-07-29 honesty review). Cleared below as soon as the code
                # or the prompt corroborates a type.
                attributes={"value": "10k", "presumed_analog": "true"},
                inferred=True,
            ))
        else:
            counters["module"] += 1
            ref = f"U{counters['module']}"
            # module_generic is the catch-all: we couldn't classify
            # the pin (no pinMode, no digitalWrite/Read, no analogRead/Write,
            # no tone, no Servo.attach). It's ambiguous by definition -> low.
            components.append(Component(
                ref=ref, type="module_generic", fn_id="",
                pins=[Pin("SIG", net)],
                attributes={"label": "?", "_confidence": "low"},
                inferred=True,
            ))

    # Phase 3: grouping of pins forming a single circuit. For now
    # only the bidirectional DC motor (1 PWM + 1-2 digitals for
    # direction). Without this grouping, the AI generating a complete H-bridge
    # code (PWM + IN1 + IN2) produces 3 distinct ambiguous LEDs in the modal,
    # which would force the user to confirm 3 times and create 3 dc_motor.
    _group_dc_motor_pins(components, code,
                          board_id=board_id, prompt=prompt, context=context)

    return lib_components + components, True


def _group_dc_motor_pins(
    components: list[Component],
    code: str,
    board_id: str | None = None,
    prompt: str = "",
    context: str = "",
) -> None:
    """Detects the "1 PWM pin + 1-2 digital-only pins" pattern among the
    ambiguous LEDs and merges it into a single ambiguous component marked as
    a bidirectional DC motor candidate. Mutates `components` in place.

    Trigger conditions:
    - exactly 1 ambiguous LED whose pin is called by analogWrite()
    - 1 or 2 ambiguous LEDs whose pin is called by digitalWrite() but
      NOT analogWrite() (= fixed or variable direction, never PWM)
    - no other ambiguous LED (otherwise the grouping could swallow
      real LEDs -- we prefer to miss the grouping than to get it wrong)

    Result:
    - we keep ONE single LED (the one on the PWM pin, which represents the
      group), annotated with:
        attributes["_grouped_pwm_pin"] = "D6"
        attributes["_grouped_dir_pins"] = ["D7", "D8"]
    - the ambiguous LEDs on the direction pins are REMOVED from the list

    The ambiguity modal (ui/wiring/ambiguity_dialog.py) detects these flags
    and offers a 2-option dialog (Yes it's a DC motor / No it's
    something else) instead of the 4 classic choices. If the user chooses No,
    the grouping is cancelled and N separate ambiguous LEDs are recreated.

    Note: we FORCE no driver choice. The pattern only detects
    "these pins form a circuit TOGETHER" -- the DC Motor choice + the
    driver model goes through the modal as before.

    We classify the pins ourselves (not _classify_pin_role which returns
    "output" as soon as a pinMode OUTPUT is found, without checking whether the pin
    is also PWM). `code` is expected post-_resolve_aliases (= pins in
    D6/D7/A0 form already resolved).
    """
    # 1. Collect the ambiguous LEDs indexed by pin.
    leds_by_net: dict[str, Component] = {}
    for c in components:
        if c.type != "led" or c.attributes.get("_confidence") != "low":
            continue
        sig = c.pin("A")
        if sig is not None:
            leds_by_net[sig.net] = c

    # 2. Classify each pin: "pwm" if it has at least 1 analogWrite,
    #    "digital" if it has ONLY digitalWrite, ignored otherwise.
    #    We normalize the regex tokens (6 -> D6) to match the indexed
    #    nets (which are normalized nets like "D6"/"A0"). Raw case
    #    without aliases: analogWrite(6, ...) gives token "6" which must
    #    match net "D6".
    pwm_nets: set[str] = set()
    for g in _ANALOG_WRITE_RE.finditer(code):
        n = _normalize_pin_token(g.group(1))
        if n:
            pwm_nets.add(n)
    digital_nets: set[str] = set()
    for g in _DIGITAL_WRITE_RE.finditer(code):
        n = _normalize_pin_token(g.group(1))
        if n:
            digital_nets.add(n)

    # 2b. Indirect call resolution: if the user defined a utility
    #     function like `setMotor(uint8_t pwmPin, uint8_t in1Pin, ...)` that
    #     calls `analogWrite(pwmPin, ...)` and `digitalWrite(in1Pin, ...)`,
    #     the regexes above just extract the parameter names and don't
    #     normalize. We scan each user function to identify
    #     the PWM/digital params, then look at the calls to the function
    #     to propagate to the concrete args. Classic case: 2 DC motor
    #     code that factors its control via 1 shared setMotor function.
    #     `indirect_groups` also captures the groupings directly from
    #     the calls (1 call = 1 motor), more precise than proximity.
    indirect_pwm, indirect_digital, indirect_groups = \
        _resolve_indirect_writes(code)
    pwm_nets.update(indirect_pwm)
    # Mark digital ONLY if the pin is not already PWM (priority: a
    # param used in both = it's a PWM, the digital just serves to
    # handle direction beyond the PWM command).
    for n in indirect_digital:
        if n not in pwm_nets:
            digital_nets.add(n)

    # 2c. Resolution of dispatch via local variables: if the user has a
    #     helper that takes a logical identifier (motorNum) then dispatches
    #     internally via `if (motorNum == X) { pwmPin = PIN; ... }`, strategies
    #     1 and 2 miss (analogWrite(pwmPin, ...) has a VAR as
    #     first arg, and pwmPin is not a parameter of the fn).
    #     Strategy 3 scans the fns to reconcile var -> literal_pin
    #     assigned in the body, hardware-agnostic. Also captures the
    #     groups per branch (= 1 if = 1 motor), more precise than proximity.
    dispatch_pwm, dispatch_digital, dispatch_groups = \
        _resolve_local_dispatch_writes(code)
    pwm_nets.update(dispatch_pwm)
    for n in dispatch_digital:
        if n not in pwm_nets:
            digital_nets.add(n)
    # Merge dispatch_groups into indirect_groups (priority is code order,
    # indirect first then dispatch as a complement if not already present).
    indirect_groups_pwms = {g[0] for g in indirect_groups}
    indirect_groups = list(indirect_groups) + [
        g for g in dispatch_groups if g[0] not in indirect_groups_pwms
    ]

    # 2d. Strategy 4 (hardware fallback): if S1+S2+S3 classified nothing
    #     as PWM but we have >=3 ambiguous LEDs on the same fn AND the prompt
    #     mentions 'motor' + a driver chip, we fall back on the hardware
    #     truth (boards.json capabilities) to classify each pin as
    #     PWM or digital. Strict guardrail: without prompt confirmation, we
    #     touch nothing -- risk of arbitrarily classifying real LEDs
    #     as motor PWM. Hardware-agnostic: works for any
    #     catalog board that exposes pwm_capable_pins().
    if (not pwm_nets and len(leds_by_net) >= 3
            and board_id
            and _has_keyword(prompt, _MOTOR_KEYWORDS)
            and _detect_driver_in_text(prompt) is not None):
        from .boards import load_board
        board = load_board(board_id)
        if board is not None:
            board_pwm = board.pwm_capable_pins()
            if board_pwm:
                s4_pwm, s4_digital = _resolve_pwm_capable_fallback(
                    leds_by_net, board_pwm)
                pwm_nets.update(s4_pwm)
                # Mark digital ONLY if not already PWM (a param used
                # in both = it's a PWM, see same logic as S2/S3).
                for n in s4_digital:
                    if n not in pwm_nets:
                        digital_nets.add(n)

    pwm_pins: list[str] = []
    digital_pins: list[str] = []
    for net in leds_by_net:
        if net in pwm_nets:
            pwm_pins.append(net)
        elif net in digital_nets:
            digital_pins.append(net)
        # else: OUTPUT pin without any write -> odd, we ignore (= leave
        # as a separate ambiguous LED, current behavior).

    # 3. Simple case: 1 PWM + 1-2 digital + no other ambiguous LED.
    if len(pwm_pins) == 1 and len(digital_pins) in (1, 2):
        if len(pwm_pins) + len(digital_pins) == len(leds_by_net):
            _create_motor_group(components, leds_by_net,
                                 pwm_pins[0], digital_pins)
            return
        # Otherwise: unclassified LEDs -> abstain (see ambiguous mixed case).
        return

    # 4. Multi-motor case (N PWM + ~N*1-2 digital): try 2 strategies
    #    to group the pins into N motors.
    #    a) By Arduino function: if each user void func() { ... }
    #       contains 1 PWM + 1-2 ambiguous digital, it's 1 motor.
    #    b) Fallback by numeric proximity: for each PWM, take
    #       the 1-2 digitals closest in pin number (typical
    #       case: "everything in setup/loop" code with const PIN_ENA=5,
    #       PIN_IN1=4, PIN_IN2=7 -> motor1, PIN_ENB=6, PIN_IN3=8,
    #       PIN_IN4=9 -> motor2).
    if len(pwm_pins) >= 2 and len(digital_pins) >= len(pwm_pins):
        groups = _scan_user_functions_for_motors(
            code, pwm_pins, digital_pins)
        # Priority to indirect_groups (= deduced from the calls of a user
        # utility fn, 1 call = 1 motor). Much more precise than
        # proximity when the code factors several motors via 1
        # setMotor(pwm, in1, in2, ...) helper.
        if (not groups or len(groups) != len(pwm_pins)) and indirect_groups:
            # Filter the groups to those matching the set of ambiguous
            # pins (= in pwm_pins / digital_pins). An indirect pin
            # may have been classified as non-ambiguous elsewhere.
            pwm_set = set(pwm_pins)
            dig_set = set(digital_pins)
            filtered: list[tuple[str, list[str]]] = []
            for pwm_pin, dirs in indirect_groups:
                if pwm_pin not in pwm_set:
                    continue
                dirs_f = [d for d in dirs if d in dig_set]
                if dirs_f:
                    filtered.append((pwm_pin, dirs_f))
            if len(filtered) == len(pwm_pins):
                groups = filtered
        if not groups or len(groups) != len(pwm_pins):
            groups = _proximity_based_motor_grouping(pwm_pins, digital_pins)
        if groups and len(groups) == len(pwm_pins):
            # Verify that ALL the ambiguities are covered.
            covered = set()
            for pwm, dirs in groups:
                covered.add(pwm)
                covered.update(dirs)
            if covered == set(leds_by_net):
                for pwm, dirs in groups:
                    _create_motor_group(components, leds_by_net, pwm, dirs)


def _create_motor_group(components: list[Component],
                         leds_by_net: dict[str, Component],
                         pwm_pin: str, dir_pins: list[str]) -> None:
    """Annotates the PWM LED with the grouped flags and removes the LEDs of
    the dir pins. Helper extracted to handle 1 or N groups."""
    main_led = leds_by_net[pwm_pin]
    main_led.attributes["_grouped_pwm_pin"] = pwm_pin
    main_led.attributes["_grouped_dir_pins"] = list(dir_pins)
    for dir_pin in dir_pins:
        try:
            components.remove(leds_by_net[dir_pin])
        except ValueError:
            pass   # already removed (defensive)


# Captures the body of an Arduino function: `void NAME() { ... }`. We
# just match the header and balance the braces by hand to handle the
# nested blocks (if/for) that contain their own '{}'.
_FUNCTION_HEADER_RE = re.compile(
    r"\bvoid\s+(\w+)\s*\(([^)]*)\)\s*\{")


def _iter_user_functions(code: str):
    """Generator over the user functions `void NAME(params) { body }`.

    Yields (name, params_list, body, body_start_offset). `params_list` is the
    list of parameter names in order (after stripping the type like
    'uint8_t pin'). Balances the braces by hand to handle the nested
    blocks in the body.
    """
    for m in _FUNCTION_HEADER_RE.finditer(code):
        name = m.group(1)
        params_raw = m.group(2).strip()
        # Extract the name (= last alphanum token) of each parameter.
        # E.g. "uint8_t pwmPin" -> "pwmPin", "int speed" -> "speed".
        # Tolerates pointers/refs (`int& x`, `int *x`) by splitting on the
        # last non-identifier char.
        params: list[str] = []
        for raw in params_raw.split(","):
            raw = raw.strip()
            if not raw:
                continue
            mname = re.search(r"([A-Za-z_]\w*)\s*$", raw)
            if mname:
                params.append(mname.group(1))
        start = m.end()
        depth = 1
        i = start
        while i < len(code) and depth > 0:
            ch = code[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        body = code[start:i - 1] if depth == 0 else code[start:]
        yield name, params, body, start


def _resolve_indirect_writes(
        code: str) -> tuple[set[str], set[str], list[tuple[str, list[str]]]]:
    """Resolves the analogWrite/digitalWrite done via parameters of user
    utility functions. Returns:
      - pwm_nets : pins resolved as PWM
      - digital_nets : pins resolved as digital (= not PWM)
      - groups : list (pwm_pin, [dir_pins]) deduced DIRECTLY from the
        calls (1 call = 1 complete group). More precise than the
        proximity_based fallback because the user themselves groups the pins per
        call: setMotor(PIN_M1_PWM, PIN_M1_IN1, PIN_M1_IN2, ...).

    Typical case handled: 2-motor code factored via 1 shared helper --

        void setMotor(uint8_t pwmPin, uint8_t in1Pin, uint8_t in2Pin, ...) {
            analogWrite(pwmPin, speed);
            digitalWrite(in1Pin, HIGH);
            digitalWrite(in2Pin, LOW);
        }
        ...
        setMotor(PIN_M1_PWM, PIN_M1_IN1, PIN_M1_IN2, 100, true);
        setMotor(PIN_M2_PWM, PIN_M2_IN3, PIN_M2_IN4, 200, false);

    Without this resolution, _ANALOG_WRITE_RE extracts "pwmPin" which does not
    normalize to a pin (= None) -> empty pwm_nets -> the
    multi-motor grouping fails and each pin stays a separate ambiguous LED.

    Algo:
      1. For each user function (except setup/loop), identify the params
         called by analogWrite (-> PWM) or digitalWrite (-> digital).
      2. For each call `NAME(arg0, arg1, ...)`: gather the PWM pin
         (arg matching the PWM param) + its digital pins. Dedup by
         pwm_pin (multiple calls with the same pwm = same motor).
    """
    pwm: set[str] = set()
    digital: set[str] = set()
    # Map pwm_pin -> ordered set of dir_pins (preserve discovery
    # order = order of the params in the call = canonical IN1/IN2 order).
    pwm_to_dirs: dict[str, list[str]] = {}
    for name, params, body, _start in _iter_user_functions(code):
        if name in ("setup", "loop") or not params:
            continue
        # Identify PWM / digital params in the body.
        pwm_idx: list[int] = []
        digital_idx: list[int] = []
        for i, pname in enumerate(params):
            esc = re.escape(pname)
            if re.search(rf"\banalogWrite\s*\(\s*{esc}\s*,", body):
                pwm_idx.append(i)
            elif re.search(rf"\bdigitalWrite\s*\(\s*{esc}\s*,", body):
                digital_idx.append(i)
        if not pwm_idx and not digital_idx:
            continue
        # Find the calls to `name(...)` in the complete code (outside the body
        # of the function itself: to avoid re-resolving recursive
        # calls, we skip the positions WITHIN the body of `name`).
        call_re = re.compile(rf"\b{re.escape(name)}\s*\(([^)]*)\)")
        for cm in call_re.finditer(code):
            # Skip if the call is the function header (= the definition).
            # Heuristic: if right before the name there is "void" or a type,
            # it's the definition.
            preceding = code[max(0, cm.start() - 16):cm.start()]
            if re.search(r"\b(void|int|float|bool|char|byte|uint\w*)\s*$",
                          preceding):
                continue
            args = [a.strip() for a in cm.group(1).split(",")]
            # Resolve the args for this call.
            call_pwm: list[str] = []
            call_dirs: list[str] = []
            for idx in pwm_idx:
                if idx < len(args):
                    n = _normalize_pin_token(args[idx])
                    if n:
                        pwm.add(n)
                        call_pwm.append(n)
            for idx in digital_idx:
                if idx < len(args):
                    n = _normalize_pin_token(args[idx])
                    if n:
                        digital.add(n)
                        call_dirs.append(n)
            # Aggregate by pwm_pin: 1 pwm + its dir_pins form 1 motor
            # group. If the call has 0 PWM or several, we can't group.
            if len(call_pwm) == 1 and call_dirs:
                main_pwm = call_pwm[0]
                bucket = pwm_to_dirs.setdefault(main_pwm, [])
                for d in call_dirs:
                    if d not in bucket and d != main_pwm:
                        bucket.append(d)
    # Convert to an ordered list (pwm sorted for determinism of the test sort).
    groups = sorted(pwm_to_dirs.items(), key=lambda kv: _pin_sort_key(kv[0]))
    return pwm, digital, [(p, ds) for p, ds in groups]


def _find_enclosing_block(text: str, pos: int) -> tuple[int, int]:
    """Returns (start, end) of the nearest `{...}` enclosing `pos`.
    Walks backward to find the unclosed `{`, then forward for its
    matching `}`. Returns (-1, -1) if no enclosing block is found.
    `start` is just after the `{`, `end` is just before the `}`.
    """
    depth = 0
    open_pos = -1
    for i in range(pos, -1, -1):
        ch = text[i]
        if ch == "}":
            depth += 1
        elif ch == "{":
            if depth == 0:
                open_pos = i + 1
                break
            depth -= 1
    if open_pos == -1:
        return (-1, -1)
    depth = 1
    for i in range(open_pos, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return (open_pos, i)
    return (open_pos, len(text))


def _resolve_local_dispatch_writes(
        code: str
        ) -> tuple[set[str], set[str], list[tuple[str, list[str]]]]:
    """Strategy 3: resolves the analogWrite/digitalWrite that go through
    LOCAL VARIABLES assigned in if/else if/switch case branches. Complements
    _resolve_indirect_writes (which only covers the
    helper-receives-pins-as-params pattern).

    Typical case (after _resolve_aliases which already substituted the consts):

        void setMotor(uint8_t motorNum, int speed) {
            uint8_t pwmPin, in1Pin, in2Pin;
            if (motorNum == 1) {
                pwmPin = 5;        // ex-PIN_M1_PWM (substituted by alias)
                in1Pin = 2;
                in2Pin = 3;
            } else if (motorNum == 2) {
                pwmPin = 6;
                in1Pin = 4;
                in2Pin = 7;
            }
            analogWrite(pwmPin, speed);
            digitalWrite(in1Pin, HIGH);
            digitalWrite(in2Pin, LOW);
        }

    Algo:
      1. For each user function, identify the LOCAL vars (= 1st arg
         not normalizable as a pin) used in analogWrite/digitalWrite.
      2. For each assignment `pwm_var = LITERAL`, find the nearest
         enclosing block (= if/else/case branch). Inside THAT block,
         look for the `dir_var = LITERAL` assignments. A block with 1 PWM
         + N dirs = 1 motor group (= the pwm<->dirs correspondence is
         certain since it's a structural branch, not proximity).
      3. The pwm/digital set aggregates all the pins seen, for the
         proximity fallback grouping if the branch-based one doesn't cover everything.

    Hardware-agnostic: works on any board (Uno, Mega,
    Nano, Uno R4, etc.) since it's purely a code analysis, not
    a board catalog lookup.

    Returns (pwm_set, digital_set, groups). `groups` is the list of
    (pwm_pin, [dir_pins]) deduced per branch -- taking priority over the
    proximity fallback. Empty sets/list if nothing found.
    """
    pwm_set: set[str] = set()
    digital_set: set[str] = set()
    groups: list[tuple[str, list[str]]] = []
    for _name, _params, body, _start in _iter_user_functions(code):
        # Identify the local vars used in analogWrite/digitalWrite.
        pwm_vars: set[str] = set()
        digital_vars: set[str] = set()
        for m in _ANALOG_WRITE_RE.finditer(body):
            tok = m.group(1)
            if _normalize_pin_token(tok) is None:
                pwm_vars.add(tok)
        for m in _DIGITAL_WRITE_RE.finditer(body):
            tok = m.group(1)
            if _normalize_pin_token(tok) is None:
                digital_vars.add(tok)
        if not pwm_vars and not digital_vars:
            continue
        # PWM wins in case of conflict (var used in both).
        digital_vars -= pwm_vars

        # For each pwm_var, find the assignments and extract groups
        # branch by branch. Dedup by pwm_pin to avoid duplicates if
        # the user assigns pwmPin = 5 several times (rare).
        seen_pwm_in_group: set[str] = set()
        for var in pwm_vars:
            assign_rx = re.compile(rf"\b{re.escape(var)}\s*=\s*(\w+)")
            for m in assign_rx.finditer(body):
                val = _normalize_pin_token(m.group(1))
                if val is None:
                    continue
                pwm_set.add(val)
                if val in seen_pwm_in_group:
                    continue
                # Enclosing block = the structural branch (if/else/case body).
                # If no block (assignment at the top-level of the fn) we take
                # the entire fn body.
                blk_start, blk_end = _find_enclosing_block(body, m.start())
                if blk_start == -1:
                    branch_text = body
                else:
                    branch_text = body[blk_start:blk_end]
                # Collect the dir_var assignments WITHIN this branch.
                branch_dirs: list[str] = []
                for dvar in digital_vars:
                    dvar_rx = re.compile(rf"\b{re.escape(dvar)}\s*=\s*(\w+)")
                    for dm in dvar_rx.finditer(branch_text):
                        dval = _normalize_pin_token(dm.group(1))
                        if dval is None:
                            continue
                        digital_set.add(dval)
                        if dval not in branch_dirs and dval != val:
                            branch_dirs.append(dval)
                if branch_dirs:
                    groups.append((val, branch_dirs))
                    seen_pwm_in_group.add(val)

        # Catch-all: digital_var assignments outside PWM branches (in case
        # a dir is assigned in a separate fn). Just adds to digital_set.
        for var in digital_vars:
            assign_rx = re.compile(rf"\b{re.escape(var)}\s*=\s*(\w+)")
            for m in assign_rx.finditer(body):
                val = _normalize_pin_token(m.group(1))
                if val is not None:
                    digital_set.add(val)

    # Sort by pin for determinism.
    groups = sorted(groups, key=lambda kv: _pin_sort_key(kv[0]))
    return pwm_set, digital_set, groups


def _resolve_pwm_capable_fallback(
        leds_by_net: dict[str, "Component"],
        board_pwm_pins: set[str],
        ) -> tuple[set[str], set[str]]:
    """Strategy 4 of the DC motor grouping (hardware fallback).

    When S1+S2+S3 classified nothing (typical: fragile SLM code with
    generic pin names `PIN1, PIN2, PIN3` or opaque indirection
    without a recognizable pattern), we fall back on the hardware truth:
    an OUTPUT pin capable of PWM on the board (per boards.json)
    is presumed PWM, otherwise digital.

    Hardware-agnostic: works for any catalog board
    as soon as `Board.pwm_capable_pins()` exists (Uno R3, Nano, Mega 2560,
    Uno R4, Leonardo, future additions).

    Caller-side guardrail: triggers only if the prompt
    confirms the "motor" + driver intent (see block 2d of
    `_group_dc_motor_pins`). Without prompt confirmation, do not call
    this function — risk of arbitrarily classifying real LEDs
    as motor PWM.
    """
    pwm: set[str] = set()
    digital: set[str] = set()
    for net in leds_by_net:
        if net in board_pwm_pins:
            pwm.add(net)
        else:
            digital.add(net)
    return pwm, digital


def _pin_sort_key(net: str) -> int:
    """Sort key for pin nets. D5 -> 5, A0 -> 100, etc. For the
    numeric proximity grouping."""
    if net.startswith("D") and net[1:].isdigit():
        return int(net[1:])
    if net.startswith("A") and net[1:].isdigit():
        return 100 + int(net[1:])   # analog pins after digital
    return 999


def _proximity_based_motor_grouping(
        pwm_pins: list[str],
        digital_pins: list[str],
        ) -> list[tuple[str, list[str]]]:
    """Fallback: associates each PWM with the 1-2 closest digitals
    in pin number. Resolves the typical case where everything is in setup/loop
    without separate user functions (so matching by fn is impossible).

    Strategy: sorts the PWMs by pin#. For each PWM, takes the 2
    digitals (among those not yet claimed) closest in numeric
    distance. If we have exactly 2N digitals, each PWM gets 2 dirs; if
    we have fewer, each PWM gets what's left (min 1).
    """
    if not pwm_pins or not digital_pins:
        return []
    sorted_pwms = sorted(pwm_pins, key=_pin_sort_key)
    remaining = set(digital_pins)
    # Distribute evenly: nb_dirs_per_motor = floor(N_digital / N_pwm).
    # But we cap at 2 (an H-bridge rarely takes more than 2 dirs).
    base_dirs = min(2, len(digital_pins) // len(pwm_pins))
    if base_dirs < 1:
        return []
    groups: list[tuple[str, list[str]]] = []
    for pwm in sorted_pwms:
        if not remaining:
            break
        pwm_n = _pin_sort_key(pwm)
        # Sort the remaining digitals by distance to the current PWM.
        candidates = sorted(
            remaining, key=lambda d: abs(_pin_sort_key(d) - pwm_n))
        take = candidates[:base_dirs]
        groups.append((pwm, sorted(take, key=_pin_sort_key)))
        remaining -= set(take)
    return groups


def _scan_user_functions_for_motors(
        code: str,
        pwm_pins: list[str],
        digital_pins: list[str],
        ) -> list[tuple[str, list[str]]]:
    """Detects the user Arduino functions that contain 1 PWM + 1-2
    digital pins among the ambiguities. Returns [(pwm_pin, [dir_pins])].

    Does NOT claim which pin belongs to which motor outside
    the analyzed functions: if an ambiguous pin appears in
    no function matching the pattern, it is not in the
    returned list (the caller decides to abandon the global grouping).
    """
    pwm_set = set(pwm_pins)
    digital_set = set(digital_pins)
    groups: list[tuple[str, list[str]]] = []
    for m in _FUNCTION_HEADER_RE.finditer(code):
        # Balance the braces to find the end of the body.
        start = m.end()
        depth = 1
        i = start
        while i < len(code) and depth > 0:
            ch = code[i]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            i += 1
        body = code[start:i - 1]
        # Collect the ambiguous pins used in this body.
        pwm_used: set[str] = set()
        digital_used: set[str] = set()
        for g in _ANALOG_WRITE_RE.finditer(body):
            n = _normalize_pin_token(g.group(1))
            if n in pwm_set:
                pwm_used.add(n)
        for g in _DIGITAL_WRITE_RE.finditer(body):
            n = _normalize_pin_token(g.group(1))
            if n in digital_set:
                digital_used.add(n)
        # Match pattern: 1 PWM + 1-2 digital.
        if len(pwm_used) == 1 and len(digital_used) in (1, 2):
            pwm = next(iter(pwm_used))
            # Verify that another fn has not already claimed this pwm.
            if any(g[0] == pwm for g in groups):
                continue
            groups.append((pwm, sorted(digital_used)))
    return groups


def _denormalize(net: str) -> str:
    """`D13` -> `13`, `A0` -> `A0` (to match the original token from the code)."""
    if net.startswith("D") and net[1:].isdigit():
        return net[1:]
    return net


def _sort_pin_key(net: str) -> tuple[int, int]:
    """Stable sort: Dn first by increasing n, then An by increasing n."""
    if net.startswith("D") and net[1:].isdigit():
        return (0, int(net[1:]))
    if net.startswith("A") and net[1:].isdigit():
        return (1, int(net[1:]))
    return (2, 0)


# ─── Prompt + context disambiguation ─────────────────────────────────────
# The generic fallback classifies every OUTPUT as a LED by default, which misses
# buzzers. This layer re-reads the text (priority context > prompt) to
# detect semantic clues and reclassify the ambiguous components.
# Multilingual coverage (FR/EN/ES/IT) to stay aligned with the UI.

_LED_KEYWORDS = (
    # FR ("lumière" deliberately ABSENT -- collision with LDR
    # "capteur de lumière". "clignote*": very common beginner phrasing
    # ("fais clignoter"), no risk -- only a LED blinks here.)
    "led", "leds", "diode", "diodes", "del", "voyant", "voyants",
    "lampe", "lampes", "clignote", "clignoter", "clignotant", "clignotante",
    # EN
    "lamp", "lamps", "light", "lights", "indicator", "blink", "blinking",
    # ES
    "diodo", "diodos", "luz", "parpadea", "parpadear",
    # IT
    "lampadina", "lampadine", "luce", "lampeggia", "lampeggiante",
)
_BUZZER_KEYWORDS = (
    # FR ("bip"/"bips": "ça fait bip", "un bip" -- no collision.)
    "buzzer", "buzzers", "piezo", "piezos", "alarme", "alarmes",
    "klaxon", "sirene", "sonnerie", "biper", "beep", "bip", "bips",
    # EN
    "beeper", "siren",
    # ES
    "alarma", "sirena", "zumbador",
    # IT
    "cicalino", "allarme", "sirena",
)
# "DC motor" keywords — when the prompt mentions a motor on an ambiguous
# pin, we reclassify LED -> dc_motor (possibly with a driver
# detected in the same excerpt). Deliberately broad to cover the
# common beginner phrasings.
_MOTOR_KEYWORDS = (
    # FR
    "moteur", "moteurs", "motorisation",
    # EN
    "motor", "motors",
    # ES
    "motor", "motores",
    # IT
    "motore", "motori",
)
# Servo PWM: ambiguous with PWM LED. The prompt matching allows
# reclassifying a detected PWM LED as a servo. Typical case: code that
# does `analogWrite(D9, value)` without `#include Servo.h` (rare but
# possible in a basic demo) or explicit disambiguation via the prompt.
_SERVO_KEYWORDS = (
    # FR
    "servo", "servos", "servomoteur", "servomoteurs", "asservi",
    "asservissement", "angle", "angles",
    # EN
    "servomotor", "servomotors",
    # ES
    "servomotor", "ángulo", "angulo",
    # IT
    "servomotore", "servomotori", "angolo",
)
# Relay (all-or-nothing actuator on a digital output). 3-pin module
# VCC/GND/IN. Specific words to avoid false positives (no generic "on"/
# "off").
_RELAY_KEYWORDS = (
    # FR
    "relais", "relai",
    # EN
    "relay", "relays",
    # ES
    "relé", "rele", "relés", "reles",
    # IT
    "relè",
)
# PIR motion detector (digital input). 3-pin module VCC/OUT/GND.
# Specific words only: the bare words "mouvement"/"motion" are
# DISCARDED (too generic, see CLAUDE.md discipline "multi-word expressions")
# -- they would trigger a false positive on a prompt like "when there is
# movement, turn on the LED". The multi-word forms cover all the real cases.
# Same for "presence"/"présence"/"presencia"/"presenza" (bare words discarded):
# "verifie la presence de tension" must not match. Only multi-word forms
# kept (e.g. "detecteur de presence", "presence sensor").
_PIR_KEYWORDS = (
    # FR
    "pir",
    "détecteur de mouvement", "detecteur de mouvement",
    "détecteur de présence", "detecteur de presence",
    # EN
    "motion sensor", "pir sensor", "presence sensor",
    # ES
    "sensor de movimiento", "sensor de presencia",
    # IT
    "sensore di movimento", "rilevatore di presenza",
)
# Radar Doppler RCWL-0516 (2026-08-27). Voisin DANGEREUX du PIR : les deux
# sont des capteurs de mouvement sur une entree digitale nue. Ce lexique est
# donc volontairement ETROIT et ne reprend AUCUN des mots de `_PIR_KEYWORDS` —
# sinon les deux se disputeraient le vocabulaire le plus courant du corpus
# debutant, et `_choose_type_from_text` trancherait au hasard de l'ordre.
#
# ⛔ Et le mot « radar » TOUT SEUL est exclu, en francais surtout : un
# « radar de recul » est un capteur a ULTRASONS, pas un radar. D'ou des
# expressions multi-mots, jamais le mot nu — la regle que CLAUDE.md pose pour
# tous les lexiques, ici avec un contre-exemple concret.
_RCWL_KEYWORDS = (
    # La reference, dans les orthographes qu'on lit sur la carte
    "rcwl-0516", "rcwl0516", "rcwl 0516",
    # FR
    "radar doppler", "doppler", "micro-ondes", "microondes",
    "detecteur radar", "détecteur radar", "capteur radar",
    # EN
    "microwave radar", "doppler radar", "microwave sensor",
    "microwave motion",
    # ES
    "radar de microondas", "sensor de microondas",
    # IT
    "radar a microonde", "sensore a microonde",
)
# Explicit potentiometer. On an analog pin the default is already
# potentiometer, so this lexicon mainly serves the conflict filter
# (if the context says "potentiometre" and the prompt says "ldr", we keep
# potentiometer by hardware priority).
_POT_KEYWORDS = (
    # FR
    "potentiometre", "potentiometres", "potentiomètre", "potentiomètres",
    "potar", "potars",
    # EN
    "potentiometer", "potentiometers",
    # ES
    "potenciometro", "potenciómetro", "potenciómetros",
    # IT
    "potenziometro", "potenziometri",
)
# Photoresistor / light sensor (LDR). On an analog pin,
# allows distinguishing a light sensor from the default potentiometer.
# Explicit words only -- we avoid "lumiere" alone which matches
# `_LED_KEYWORDS` (collision on a digital pin, but here we're on an
# analog pin so in practice no conflict -- a guardrail
# nonetheless by discipline).
_LDR_KEYWORDS = (
    # FR (variants with/without accents -- school keyboards)
    "ldr", "photorésistance", "photoresistance", "photo-résistance",
    "photo-resistance", "luminosité", "luminosite",
    "capteur de lumière", "capteur de lumiere",
    "capteur lumière", "capteur lumiere",
    "capteur de luminosité", "capteur de luminosite",
    # EN
    "photoresistor", "photo-resistor", "photo resistor",
    "light sensor", "brightness",
    # ES
    "fotorresistencia", "sensor de luz", "luminosidad",
    # IT
    "fotoresistenza", "sensore di luce", "luminosità", "luminosita",
)
# KY-018 photoresistor MODULE: same function as a bare LDR but a 3-pin
# breakout (silkscreen GND / VCC / S). Distinguished from `ldr` ONLY by its
# part number -- NO generic light words here (those stay with _LDR_KEYWORDS,
# otherwise every "capteur de lumière" would wrongly become a KY-018). When
# BOTH match ("capteur de lumière KY-018"), the `_refine` rule makes ky018 win
# (it IS a photoresistor). Part number is identical across languages.
_KY018_KEYWORDS = (
    "ky-018", "ky018", "ky 018",
)
# Temperature sensor (NTC thermistor, or sometimes LM35 on direct
# analog). On an analog pin, allows distinguishing from the default
# potentiometer. NB: DHT11/22 have their own detector via `#include DHT.h`.
_TEMP_SENSOR_KEYWORDS = (
    # FR ("thermomètre": everyday word missing whereas "thermistance"
    # /"température" were already there.)
    "thermistance", "thermistances", "ntc", "capteur de température",
    "capteur température", "capteur thermique", "lm35",
    "température", "temperature", "thermomètre", "thermometre",
    # EN
    "thermistor", "thermistors", "temperature sensor",
    "thermal sensor", "thermometer",
    # ES
    "termistor", "sensor de temperatura", "temperatura", "termómetro",
    # IT
    "termistore", "sensore di temperatura", "termometro",
)
# Microphone / sound sensor on an analog pin. Allows distinguishing
# from the default potentiometer.
_SOUND_SENSOR_KEYWORDS = (
    # FR
    "microphone", "microphones", "capteur de son",
    "capteur son", "capteur sonore",
    # EN
    "mic", "sound sensor", "audio sensor",
    # ES
    "micrófono", "sensor de sonido",
    # IT
    "microfono", "microfoni", "sensore sonoro", "sensore di suono",
)
# Button matrix / keypad. Typical case: pins wired as
# INPUT/OUTPUT and scanned manually (without `#include Keypad.h`, which
# would already have resolved via the dedicated detector).
_KEYPAD_KEYWORDS = (
    # FR
    "clavier", "claviers", "keypad", "keypads", "matrice de boutons",
    "matrice boutons", "matrice clavier", "touches",
    # EN
    "keyboard matrix", "button matrix", "key matrix",
    # ES
    "teclado", "teclados", "matriz de botones",
    # IT
    "tastierino", "tastierini", "matrice di pulsanti",
)
# Stepper / stepper motor. Complements the existing
# `_A4988_MANUAL_CONFIRM_RE` matching by exposing a lexicon reusable
# by the disambiguation pipeline (cohesion with the other types).
_STEPPER_KEYWORDS = (
    # FR ("28byj": canonical model of the beginner kit, also matches
    # "28byj-48" via the word boundary; zero false positives.)
    "pas-à-pas", "pas a pas", "pas-a-pas", "pap", "stepper", "steppers",
    "nema17", "nema 17", "nema", "28byj",
    # EN
    "step motor", "stepping motor",
    # ES
    "paso a paso", "motor paso a paso",
    # IT
    "passo passo", "motore passo-passo",
)
_LED_COLOR_KEYWORDS = {
    "red":    ("rouge", "rouges", "red", "rojo", "rojos", "rosso", "rossi"),
    "green":  ("vert", "verts", "verte", "vertes", "green", "verde", "verdi"),
    "blue":   ("bleu", "bleus", "bleue", "bleues", "blue", "azul", "azules", "blu"),
    "yellow": ("jaune", "jaunes", "yellow", "amarillo", "amarillos", "giallo"),
    "white":  ("blanc", "blanche", "blancs", "white", "blanco", "blancos", "bianco", "bianchi"),
    "orange": ("orange", "oranges", "naranja", "naranjas", "arancione"),
}
# DC drivers explicitly detectable in the user prompt/document (= 1 name
# = 1 precise chip). We exclude L293D for Phase A: it has 2 variants (bare DIP
# vs breakout module) that the user will need to specify via the ambiguity modal
# (Phase B). The names here must be enough to disambiguate without a modal.
_MOTOR_DRIVER_KEYWORDS = {
    "l298n":        ("l298n", "l298"),
    # L293D variants: breakout module (typical Arduino kit) vs bare DIP
    # chip. Order matters: we test the "L293D module" phrases first
    # before the plain "L293D" to avoid pre-checking the bare chip when
    # the user specified "module".
    "l293d_module": ("l293d module", "l293d_module", "l293d breakout",
                     "module l293d", "shield l293d", "l293d shield"),
    "l293d":        ("l293d",),
    "tb6612fng":    ("tb6612fng", "tb6612"),
    "drv8833":      ("drv8833",),
}


def _has_keyword(text: str, keywords) -> bool:
    """True if one of the keywords appears as a complete word (case-insensitive)."""
    if not text:
        return False
    for kw in keywords:
        if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE):
            return True
    return False


def _detect_driver_in_text(text: str) -> str | None:
    """Looks for a catalog DC driver name in a text fragment
    (per-pin excerpt of the prompt). First match wins in dict order
    (L293D module variants before bare L293D, see the dict's docstring).
    """
    if not text:
        return None
    for driver_type, kws in _MOTOR_DRIVER_KEYWORDS.items():
        if _has_keyword(text, kws):
            return driver_type
    return None


def _detect_suggested_dc_driver(prompt: str, context: str) -> str | None:
    """Looks for a DC driver name explicitly mentioned in the user prompt
    or the context document. Returns the catalog type
    (`l298n` / `tb6612fng` / `drv8833`) or None if nothing detected.

    NEVER looks at the AI-generated code: the code is identical for all
    DC drivers (analogWrite + digitalWrite), so a driver mention
    in the code = arbitrary AI choice, not info about the user's
    hardware. Only the data provided by the user (prompt + doc)
    counts.

    First match wins (dict order). If the user mentions 2 different
    drivers, we take the first in catalog order; the modal
    (Phase B) will handle this refinement case.
    """
    full_text = "\n".join(s for s in (prompt, context) if s)
    return _detect_driver_in_text(full_text)


def find_pin_excerpt(prompt: str, net: str, context: str = "",
                    max_len: int = 160) -> str | None:
    """Looks in `prompt` then in `context` for the line that mentions
    pin `net` and returns it (without the initial bullet marker). Returns None
    if the pin is mentioned nowhere.

    Covers: `D7`, `broche 7`, `broche numérique 7`, `broche numéro 7`,
    `broche n° 7`, `pin 7`, `GPIO 7` (digital) and their analog
    equivalents (`A0`, `broche A0`, etc.).

    This function is shared between disambiguation (per-pin scoping)
    and the ambiguity modal (excerpt shown to the user).
    """
    if not net:
        return None
    if net.startswith("D") and net[1:].isdigit():
        n = net[1:]
        pattern = (
            rf"\b(?:D{n}"
            rf"|broche\s+(?:numérique\s+|numéro\s+|n°\s*)?{n}"
            rf"|pin\s+(?:numéro\s+|n°\s*)?{n}"
            rf"|GPIO\s*{n})\b"
        )
    elif net.startswith("A") and net[1:].isdigit():
        n = net[1:]
        pattern = (
            rf"\b(?:{net}"
            rf"|broche\s+(?:analogique\s+|numéro\s+|n°\s*)?A?{n}"
            rf"|pin\s+(?:numéro\s+|n°\s*)?A?{n})\b"
        )
    else:
        return None

    for source in (prompt, context):
        if not source:
            continue
        m = re.search(pattern, source, re.IGNORECASE)
        if m is None:
            continue
        line_start = source.rfind("\n", 0, m.start()) + 1
        line_end = source.find("\n", m.end())
        if line_end == -1:
            line_end = len(source)
        excerpt = source[line_start:line_end].strip()
        excerpt = re.sub(r"^[-*•·]\s*", "", excerpt)
        if len(excerpt) > max_len:
            excerpt = excerpt[:max_len - 1].rstrip() + "…"
        return excerpt
    return None


def _choose_type_from_text(
    excerpt: str, prompt: str, context: str,
    candidates: dict[str, tuple],
) -> str | None:
    """Chooses the target type by crossing excerpt (per-pin of the prompt) +
    context (user hardware file).

    Cascade -- hardware prevails over the prompt:
    1. If exactly ONE type matches in the `context` (BOM) → that type
       wins. The context is more stable than the prompt (explicit
       hardware declarations), so we give it priority.
    2. Otherwise, if exactly ONE type matches in the `excerpt`, we
       apply it EXCEPT if the context mentions another incompatible
       type (the hardware contradicts the prompt → we don't decide,
       the user will be sent to the modal).
    3. Otherwise (silent on both sides, or ambiguous conflict on the context side)
       → None.

    `candidates`: `{"target_type": keywords_tuple, ...}`. Including the
    "neutral" type (e.g. `"led": _LED_KEYWORDS`) allows detecting the case
    where the hardware insists on that type against a prompt suggestion
    (= rejection of the change).

    `prompt` is passed for API symmetry but is not
    used directly -- the prompt matching always goes through
    the `excerpt` (per-pin scoping via `find_pin_excerpt`) to avoid
    contamination between ambiguous components.
    """
    del prompt   # API symmetry; per-pin scoping is done via excerpt
    def _matches(text):
        if not text:
            return set()
        return {t for t, kws in candidates.items() if _has_keyword(text, kws)}

    def _refine(hits):
        """Collapse the linguistic specificity hierarchies:
        `stepper` or `servo` are sub-types of `dc_motor` (the user
        can write "moteur pas-a-pas" which matches both). If the specific
        one is present, we remove the generic one."""
        if "stepper" in hits and "dc_motor" in hits:
            hits = hits - {"dc_motor"}
        if "servo" in hits and "dc_motor" in hits:
            hits = hits - {"dc_motor"}
        # KY-018 (module nommé) est une photorésistance : si les mots
        # génériques de lumière ET le numéro de pièce matchent, le module
        # spécifique gagne (sinon double-hit => aucune décision).
        if "ky018" in hits and "ldr" in hits:
            hits = hits - {"ldr"}
        return hits

    context_hits = _refine(_matches(context))
    excerpt_hits = _refine(_matches(excerpt))

    def _winner(hits):
        return next(iter(hits)) if len(hits) == 1 else None

    context_w = _winner(context_hits)
    excerpt_w = _winner(excerpt_hits)

    # Case 1: the context says `dc_motor` (generic) and the excerpt specifies
    # a sub-type (stepper/servo) -> the sub-type wins (the user
    # wrote "moteur" in the BOM then "moteur pas-a-pas" in the prompt).
    if context_w == "dc_motor" and excerpt_w in ("stepper", "servo"):
        return excerpt_w

    # Case 2: context decides alone -> hardware priority.
    if context_w is not None:
        return context_w

    # Case 3: context silent/ambiguous, excerpt decides -> verify
    # there is no conflict with an ambiguous context (>=2 hits where the
    # winner is not included).
    if excerpt_w is not None:
        if context_hits and excerpt_w not in context_hits:
            return None   # silent conflict: the modal will take over
        return excerpt_w

    return None


# Reclassification candidates for an ambiguous LED (from the fallback).
# Including `led` lets the hardware impose "it stays a LED" against
# a contradictory prompt suggestion.
_LED_RECLASSIF_CANDIDATES = {
    "led":      _LED_KEYWORDS,
    "buzzer":   _BUZZER_KEYWORDS,
    "servo":    _SERVO_KEYWORDS,
    "stepper":  _STEPPER_KEYWORDS,
    "dc_motor": _MOTOR_KEYWORDS,
    "relay":    _RELAY_KEYWORDS,
}
# Sub-type candidates for an ambiguous potentiometer (analog pin
# classified by default). A deduced sub-type (ldr/thermistor/microphone),
# from the code in priority or from the prompt/context, MUTATES the component in the
# potentiometer loop of `_disambiguate_with_prompt` (rendered via
# resolve_generic, same nets as the pot).
_POT_SUBTYPE_CANDIDATES = {
    "potentiometer": _POT_KEYWORDS,
    "ldr":           _LDR_KEYWORDS,
    "ky018":         _KY018_KEYWORDS,
    "thermistor":    _TEMP_SENSOR_KEYWORDS,
    "microphone":    _SOUND_SENSOR_KEYWORDS,
}
# Sub-type candidates for an ambiguous digital input (button by
# default). `button` is the "neutral" anchor: we map it to _KEYPAD_KEYWORDS
# not because a keypad IS a button, but so that a mention
# "clavier"/"keypad" makes the neutral type `button` win in
# _choose_type_from_text and thus BLOCKS a wrongful PIR mutation. Only `pir`
# actually mutates; a `button` hit leaves the component unchanged.
_BTN_SUBTYPE_CANDIDATES = {
    "button":   _KEYPAD_KEYWORDS,
    "pir":      _PIR_KEYWORDS,
    "rcwl0516": _RCWL_KEYWORDS,
}


# ── Deduit par son NOM, ou par une description ? (2026-08-27) ─────────────
# Un lexique melange deux natures de mots : la REFERENCE de la piece
# (« rcwl-0516 ») et sa DESCRIPTION (« radar doppler »). Quand c'est la
# description qui a gagne, l'app a choisi un numero de piece que l'utilisateur
# n'a JAMAIS ecrit -- c'est une devinette, et le projet ne presente pas une
# devinette comme une lecture.
#
# ⚠️ La regle est ETROITE, et la mesure du 2026-08-27 dit pourquoi : 9 des 14
# types candidats n'ont AUCUNE reference (led, buzzer, servo, dc_motor, relay,
# potentiometer, ldr, microphone, button, pir). Une LED n'a pas de numero a
# donner ; la deduire de « allume une LED » est le mieux qu'on puisse faire, et
# l'en avertir mettrait « pas sur » sur presque chaque schema de debutant. On
# n'avertit donc QUE si le type deduit POSSEDE une reference et qu'on ne l'a
# pas eue.
def _looks_like_a_part_reference(keyword: str) -> bool:
    """Un mot-cle qui designe une PIECE (chiffres + lettres) plutot qu'un
    usage. « rcwl-0516 », « ky-018 », « ntc » -> non (pas de chiffre)."""
    k = re.sub(r"[-_ ]", "", (keyword or "").lower())
    return len(k) >= 4 and bool(re.search(r"\d", k)) and bool(re.search(r"[a-z]", k))


def _matched_by_reference(text: str, keywords) -> bool:
    refs = tuple(k for k in keywords if _looks_like_a_part_reference(k))
    return bool(refs) and _has_keyword(text, refs)


def _type_has_a_reference(keywords) -> bool:
    return any(_looks_like_a_part_reference(k) for k in keywords)


def _subtype_for_pin(c: "Component", sig_pin: "Pin",
                     candidates: "dict[str, tuple]",
                     code: str, prompt: str, context: str,
                     prompts_by_fn: "dict[str, str] | None",
                     pin_to_names: "dict[str, list[str]]") -> "str | None":
    """Resolves a pin's sub-type by cascade: the CODE in priority
    (identifiers/comments tied to the pin), otherwise the per-pin prompt +
    the context. Returns the winning type from `candidates` or None.

    Shared by the potentiometer and digital-input reclassification
    loops (same cascade; the LED loop has its own extended logic and
    does not use this helper)."""
    code_excerpt = _code_excerpt_for_pin(code, sig_pin.net, pin_to_names)
    gagnant = (
        _choose_type_from_text(code_excerpt, "", "", candidates)
        if code_excerpt else None
    )
    texte = code_excerpt or ""
    if gagnant is None:
        fn_specific_prompt = ""
        if prompts_by_fn and c.fn_id and c.fn_id in prompts_by_fn:
            fn_specific_prompt = prompts_by_fn[c.fn_id]
        excerpt = (
            find_pin_excerpt(fn_specific_prompt, sig_pin.net, "")
            or find_pin_excerpt(prompt, sig_pin.net, context)
            or ""
        )
        gagnant = _choose_type_from_text(excerpt, prompt, context, candidates)
        texte = excerpt or ""
    if gagnant is None:
        return None, False
    kws = candidates.get(gagnant, ())
    # « Presume » seulement si le type A une reference et qu'on ne l'a pas
    # lue : sinon la mention serait un reproche adresse a une LED, qui n'a
    # aucun numero a donner. Le CONTEXTE (fichier materiel de l'utilisateur)
    # compte comme une source au meme titre que le prompt.
    presume = (_type_has_a_reference(kws)
               and not _matched_by_reference(texte, kws)
               and not _matched_by_reference(context or "", kws))
    return gagnant, presume


# MH-Z14A et MH-Z1311A : deux capteurs de CO2 NDIR distincts du MH-Z19 deja
# connu. Lexiques VOLONTAIREMENT reduits a la REFERENCE, sans le moindre mot de
# description -- le vocabulaire generique du CO2 appartient au `mhz19`, qui est
# detecte par SA signature (`MHZ19.h`) et n'a pas a se le faire disputer.
#
# ⚠️ Consequence VOULUE : ces deux-la ne s'obtiennent qu'en ecrivant leur
# reference. Ils ne declenchent donc jamais l'aveu `presumed_from_description`,
# et c'est coherent -- il n'y a rien a avouer quand l'utilisateur a nomme sa
# piece lui-meme.
_MHZ14A_KEYWORDS = ("mh-z14a", "mhz14a", "mh z14a", "mh-z14", "mhz14")
_MHZ1311A_KEYWORDS = ("mh-z1311a", "mhz1311a", "mh z1311a",
                      "mh-z1311", "mhz1311")

# Pieces UART qu'un prompt peut NOMMER sur un module serie encore generique.
_UART_PART_KEYWORDS = {
    "mhz14a": _MHZ14A_KEYWORDS,
    "mhz1311a": _MHZ1311A_KEYWORDS,
}


def _name_generic_serial_from_reference(components: list, prompt: str,
                                        context: str) -> None:
    """Nomme un module serie GENERIQUE quand le prompt donne sa reference.

    Trois formes de generique existent, mesurees le 2026-08-27 : un
    `SoftwareSerial` nu sort en `uart_module`, et un include inconnu donne un
    type nomme d'apres la BIBLIOTHEQUE (`MHZCO2.h` -> `mhzco2`) qui n'a aucune
    identite au registre. La cible n'est donc pas un type precis mais le fait
    d'etre un module serie SANS identite -- sinon ce correctif ne marcherait
    que sur la moitie des sketches.

    ⛔ Un composant que le CODE identifie n'est jamais touche. `MHZ19.h` sort
    en `mhz19`, qui EST au registre : meme si le prompt dit << MH-Z14A >>, on
    ne remplace pas une signature lue par une mention. Le code prevaut sur le
    prompt pour le TYPE, c'est la regle du projet.

    ⛔ Et on n'agit que s'il y a EXACTEMENT un module generique et EXACTEMENT
    une reference. Deux modules et une reference : impossible de savoir lequel
    est nomme, donc on se tait plutot que de tirer au sort.
    """
    from ..component_registry import registry
    connus = {c.id for c in registry()}
    generiques = [c for c in components
                  if c.pin("TX") is not None and c.pin("RX") is not None
                  and c.type not in connus]
    if len(generiques) != 1:
        return
    texte = f"{prompt or ''}\n{context or ''}"
    trouves = {t for t, kws in _UART_PART_KEYWORDS.items()
               if _has_keyword(texte, kws)}
    if len(trouves) != 1:
        return
    cible = generiques[0]
    _mutate_component(components, cible, trouves.pop(), list(cible.pins))


# JSN-SR04T : telemetre a ultrasons ETANCHE, sonde deportee. Lexique reduit a
# la REFERENCE, meme discipline que les MH-Z -- << mesure la distance >> et
# << ultrason >> appartiennent au HC-SR04, qui est le defaut legitime.
_JSN_SR04T_KEYWORDS = ("jsn-sr04t", "jsnsr04t", "jsn sr04t", "sr04t",
                       "jsn-sr04", "jsnsr04")

# Pieces qui partagent le PROTOCOLE trig/echo du HC-SR04.
_ULTRASONIC_PART_KEYWORDS = {"jsn_sr04t": _JSN_SR04T_KEYWORDS}


def _refine_ultrasonic_from_reference(components: list, prompt: str,
                                      context: str) -> None:
    """Precise un ultrason que le prompt NOMME.

    ⚠️ CE CAS N'EST PAS CELUI DES MH-Z, et la difference decide du droit
    d'agir. `MHZ19.h` nomme une PUCE : le code identifie la piece, et le
    prompt ne doit pas la contredire. Ici le detecteur reconnait la sequence
    d'impulsion de 10 us -- un PROTOCOLE, que le HC-SR04, le JSN-SR04T,
    l'AJ-SR04M et le HC-SR04P partagent tous. Le code ne dit donc PAS laquelle
    c'est, et le prompt a le droit de le preciser sans rien contredire.
    (Verifie le 2026-08-27 : un sketch ultrason canonique sort en `hcsr04`
    quel que soit le prompt.)

    Le cablage est IDENTIQUE -- VCC / TRIG / ECHO / GND -- donc les broches ne
    bougent pas. Seul le nom change, et c'est tout ce qu'on sait de plus.

    ⛔ Comme ailleurs : un seul ultrason et une seule reference, sinon on se
    tait plutot que de tirer au sort.
    """
    cibles = [c for c in components if c.type == "hcsr04"]
    if len(cibles) != 1:
        return
    texte = f"{prompt or ''}\n{context or ''}"
    trouves = {t for t, kws in _ULTRASONIC_PART_KEYWORDS.items()
               if _has_keyword(texte, kws)}
    if len(trouves) != 1:
        return
    cible = cibles[0]
    _mutate_component(components, cible, trouves.pop(), list(cible.pins))


def _disambiguate_with_prompt(components: list[Component],
                                prompt: str, context: str,
                                prompts_by_fn: dict[str, str] | None = None,
                                code: str = "") -> None:
    """Reclassifies the ambiguous components by crossing with prompt + context.

    Target: generic LEDs from the fallback (each OUTPUT pin was
    classified as a LED by default). Components coming from an explicit lib
    (Servo, DHT, OLED, LCD, HC-SR04, buzzer via tone()) are NOT touched
    -- they are considered high-confidence detections.

    Rules:
    - If the text mentions "buzzer" (and not "LED") -> reclassify LED -> buzzer
    - If the text mentions a LED color ("rouge", "blue", ...) ->
      annotate c.attributes["color"]

    Mutates the list in place. No return.
    """
    if not (prompt or context or code):
        return

    # Counter of existing buzzers so as not to collide refs after
    # reclassification (e.g. add B2 if B1 already exists).
    n_buzzer = sum(1 for c in components if c.type == "buzzer")

    # DC driver mentioned globally in the prompt/doc (= Phase A). Serves
    # as a fallback for the GROUPED components (= DC motor candidates) when
    # the prompt does not explicitly mention the pin (e.g. "2 DC motors
    # with L298N" without naming the pins). The upstream grouping already confirmed
    # the PWM+digital pattern = DC motor, so we can conclude with
    # confidence type=dc_motor + driver=<global>.
    global_driver = _detect_suggested_dc_driver(prompt, context)

    # Global "LED" confirmation: if the prompt/context explicitly mentions
    # "led" and NO competing type (buzzer/servo/stepper/motor), the
    # ambiguous LEDs WITHOUT a per-pin excerpt are confirmed as LED. Covers the case
    # "Add a led that blinks": the prompt names no pin (the AI
    # chooses the pin, often 13/LED_BUILTIN), so the per-pin scoping can
    # match nothing -- but the type is globally non-ambiguous, no point
    # opening the modal. If a competing type is also mentioned (e.g.
    # "a led and a buzzer"), we don't know which pin is what -> we leave
    # the LED ambiguous (the modal will decide).
    _global_text = f"{prompt}\n{context}"
    _global_hits = {
        t for t, kws in _LED_RECLASSIF_CANDIDATES.items()
        if _has_keyword(_global_text, kws)
    }
    global_led_only = _global_hits == {"led"}

    # Map net -> code identifiers (priority deduction source,
    # per-pin). Empty if `code` not provided (backward compat).
    pin_to_names = _pin_to_identifiers(code) if code else {}

    for c in components:
        if c.type != "led" or not c.inferred:
            continue   # not a generic LED from the fallback

        # PER-PIN SCOPING: we look ONLY at the prompt line that
        # mentions this component's pin. Otherwise, "blue LED on 13"
        # would contaminate all the ambiguous LEDs at once
        # (D7 would become a blue LED by accident).
        # PER-FN SCOPING: if the component has an fn_id and we have its
        # specific prompt, we use it in priority -- otherwise the current prompt
        # (= iterate prompt) does not contain the component's context
        # (e.g. after iterate, the "blue LED on 13" is in the
        # original prompt of fn-1, not in the iterate prompt).
        a_pin = c.pin("A") or (c.pins[0] if c.pins else None)
        if a_pin is None:
            continue

        # Source 1 (priority): the code (identifiers + comments).
        code_excerpt = _code_excerpt_for_pin(code, a_pin.net, pin_to_names)
        # context intentionally empty here: the code prevails with no possible
        # hardware conflict (the context/excerpt cascade of _choose_type_from_text
        # then falls back on the code_excerpt alone).
        target_type = (
            _choose_type_from_text(code_excerpt, "", "",
                                   _LED_RECLASSIF_CANDIDATES)
            if code_excerpt else None
        )

        # Source 2: per-pin prompt (+ context), existing behavior.
        fn_specific_prompt = ""
        if prompts_by_fn and c.fn_id and c.fn_id in prompts_by_fn:
            fn_specific_prompt = prompts_by_fn[c.fn_id]
        prompt_excerpt = (
            find_pin_excerpt(fn_specific_prompt, a_pin.net, "")
            or find_pin_excerpt(prompt, a_pin.net, context)
        )

        if target_type is None and not prompt_excerpt:
            # No per-pin mention (neither code nor prompt) -> global fallback
            # (existing case: global DC driver, or global "led" without a pin).
            if (global_driver is not None
                    and c.attributes.get("_grouped_pwm_pin")):
                c.attributes["_prompt_suggested_type"] = "dc_motor"
                c.attributes["_prompt_suggested_driver"] = global_driver
            elif global_led_only and not c.attributes.get("_grouped_pwm_pin"):
                c.attributes["_confidence"] = "medium"
            continue

        if target_type is None:
            target_type = _choose_type_from_text(
                prompt_excerpt, prompt, context, _LED_RECLASSIF_CANDIDATES,
            )

        excerpt = code_excerpt or prompt_excerpt or ""

        # The colour is looked up in the code excerpt AND, failing that, in the
        # prompt excerpt -- deliberately NOT through the `or` cascade above.
        # That cascade exists so the CODE prevails when deciding the TYPE (a
        # documented decision: no possible hardware conflict). But the code
        # practically never names a colour, only the user does; sharing the
        # cascade meant "LED rouge sur la broche 9" was silently dropped as
        # soon as the pin had any code excerpt at all. Found 2026-07-30 while
        # removing the hardcoded `color="red"` default -- the default was
        # masking it, so `test_e2e_led_color_still_works` was passing on the
        # default rather than on the annotation it claimed to cover.
        # Code first, so an explicit `greenLed` identifier still wins.
        def _color_in(text: str) -> str | None:
            return next(
                (color for color, kws in _LED_COLOR_KEYWORDS.items()
                 if _has_keyword(text, kws)),
                None,
            )

        color_in_excerpt = _color_in(code_excerpt) or _color_in(prompt_excerpt)

        if target_type == "buzzer":
            c.type = "buzzer"
            c.pins = [Pin("+", a_pin.net), Pin("-", "GND")]
            c.attributes = {"_confidence": "high"}
            n_buzzer += 1
            c.ref = f"B{n_buzzer}"
        elif target_type == "relay":
            _mutate_component(
                components, c, "relay",
                [Pin("VCC", "5V"), Pin("GND", "GND"), Pin("IN", a_pin.net)],
            )
        elif target_type == "dc_motor":
            c.attributes["_prompt_suggested_type"] = "dc_motor"
            driver_in_excerpt = _detect_driver_in_text(excerpt)
            if driver_in_excerpt:
                c.attributes["_prompt_suggested_driver"] = driver_in_excerpt
        elif target_type == "servo":
            c.attributes["_prompt_suggested_type"] = "servo"
        elif target_type == "stepper":
            c.attributes["_prompt_suggested_type"] = "stepper"
        elif target_type == "led" and color_in_excerpt:
            c.attributes["color"] = color_in_excerpt
            c.attributes["_confidence"] = "high"
        elif target_type == "led":
            c.attributes["_confidence"] = "medium"
        elif color_in_excerpt:
            c.attributes["color"] = color_in_excerpt
            c.attributes["_confidence"] = "medium"
        # Otherwise: ambiguous or silent -> stays "low"

    # Potentiometer loop: on an analog pin the fallback classifies as
    # potentiometer by default. An analog sub-type (ldr/thermistor/
    # microphone) deduced from the code (priority) or from the prompt/context MUTATES
    # the component (rendered via resolve_generic, same nets as the pot).
    for c in components:
        if c.type != "potentiometer" or not c.inferred:
            continue
        # Signal pin to the Arduino: "W" (wiper) by fallback
        # convention, otherwise fall back on the first pin whose net is
        # an analog pin (starts with "A" followed by a digit).
        sig_pin = c.pin("W")
        if sig_pin is None:
            sig_pin = next(
                (p for p in c.pins
                 if p.net and len(p.net) >= 2
                 and p.net[0] == "A" and p.net[1:].isdigit()),
                None,
            )
        if sig_pin is None:
            continue

        subtype, presume = _subtype_for_pin(
            c, sig_pin, _POT_SUBTYPE_CANDIDATES,
            code, prompt, context, prompts_by_fn, pin_to_names,
        )

        if subtype == "potentiometer":
            # The code or the prompt NAMED a potentiometer: the default is
            # corroborated, so it is no longer a guess. (`_mutate_component`
            # wipes `attributes` wholesale, so the other sub-types drop the
            # marker on their own -- only this branch has to clear it.)
            c.attributes.pop("presumed_analog", None)

        if subtype and subtype != "potentiometer":
            # Real mutation: same nets as the pot (5V / signal / GND),
            # rendered via resolve_generic. KY-018 keeps its own silkscreen
            # order (GND / VCC / S, top->bottom); the other analog sub-types
            # use the generic VCC / OUT / GND.
            if subtype == "ky018":
                pins = [Pin("GND", "GND"), Pin("VCC", "5V"),
                        Pin("S", sig_pin.net)]
            else:
                pins = [Pin("VCC", "5V"), Pin("OUT", sig_pin.net),
                        Pin("GND", "GND")]
            _mutate_component(components, c, subtype, pins)
            if presume:
                c.attributes["presumed_from_description"] = "true"

    # Module serie generique que le prompt NOMME par sa reference.
    _name_generic_serial_from_reference(components, prompt, context)
    # Ultrason que le prompt precise : le protocole trig/echo ne
    # distingue pas les pieces qui le partagent.
    _refine_ultrasonic_from_reference(components, prompt, context)

    # Digital-input loop: the fallback classifies an input as a button by
    # default. A specific code/prompt clue (PIR) mutates it.
    for c in components:
        if c.type != "button" or not c.inferred:
            continue
        sig_pin = c.pin("A") or (c.pins[0] if c.pins else None)
        if sig_pin is None:
            continue

        subtype, presume = _subtype_for_pin(
            c, sig_pin, _BTN_SUBTYPE_CANDIDATES,
            code, prompt, context, prompts_by_fn, pin_to_names,
        )

        if subtype == "pir":
            _mutate_component(
                components, c, "pir",
                [Pin("VCC", "5V"), Pin("OUT", sig_pin.net), Pin("GND", "GND")],
            )
            if presume:
                c.attributes["presumed_from_description"] = "true"
        elif subtype == "rcwl0516":
            # Radar Doppler : trois fils utiles, comme le PIR. Le module
            # porte aussi 3V3 et CDS, que rien ne relie ici -- on ne cable
            # que ce dont on est sur.
            _mutate_component(
                components, c, "rcwl0516",
                [Pin("VIN", "5V"), Pin("OUT", sig_pin.net), Pin("GND", "GND")],
            )
            if presume:
                c.attributes["presumed_from_description"] = "true"


# ─── Complete pipeline ─────────────────────────────────────────────────────
# Detector mode: "python" (default, pure static detection from the
# code + prompt + context) or "ai_markers" (legacy, parses the
# `<<< fn-N_wiring >>>` markers when present). Keep "python" to free
# ourselves from the marker dependency -- small models often forgot
# to emit them.
WIRING_DETECTOR_MODE = "python"


# types deduced from a bare pin: intrinsically ambiguous, never code-certain
_BARE_PIN_TYPES = {"led", "buzzer", "relay", "button", "potentiometer",
                   "ldr", "ky018", "thermistor", "microphone", "pir",
                   "rcwl0516", "module_generic"}


def _is_signature_detected(c: "Component") -> bool:
    """True = type from a unique code signature. False for the
    bare-pin deductions (confidence 'low' OR intrinsically deduced type) and
    for the safety-net components (unknown include -> placeholder, or PRESUMED
    I2C wiring): those are guesses, never code-certain."""
    if c.attributes.get("_confidence") == "low":
        return False
    if c.attributes.get("unrecognized") or c.attributes.get("presumed_wiring"):
        return False
    return c.type not in _BARE_PIN_TYPES


def _warn_unrenderable_components(nl) -> None:
    """Warning pour tout composant que le rendu ne saura pas dessiner.

    `layout` retombe sur `resolve_generic`, qui choisit le SVG selon le nombre
    de broches (2-8 single-row, plus les impairs 9/11/13 depuis TODO #58
    2026-08-20 ; 10-40 pair DIP) ; hors de ces plages il renvoie None et le
    composant est simplement SAUTÉ — il disparaissait du schéma sans log ni
    message (revue 2026-07-29). On prédit le cas ici, au niveau qui porte les
    warnings, sans toucher au pipeline de rendu."""
    from .layout.component_catalog import lookup, resolve_generic
    for c in nl.components:
        try:
            if lookup(c.type) is not None:
                continue
            if resolve_generic(c.type, c.pins) is not None:
                continue
        except Exception:
            continue        # jamais casser l'analyse pour un warning
        name = c.type
        nl.add_warning(
            code="undrawable_component",
            severity=SEVERITY_INFO,
            message=f"Composant « {name} » ({len(c.pins)} broches) non "
                    f"dessinable : absent du schéma.",
            refs=[c.ref],
            params={"name": name, "pins": str(len(c.pins))},
        )


# En-têtes qui n'impliquent AUCUN matériel à brancher : le langage, les bus
# eux-mêmes (un sketch qui n'a que `Wire.h` est un scanner I2C, il n'a
# légitimement rien à câbler), et les bibliothèques purement logicielles.
# ⚠️ `onewire.h` n'y est PAS, alors qu'il figure dans le groupe « core /
# utilities / companions » de `_KNOWN_HEADERS_LOWER` : un bus 1-Wire a bien du
# matériel au bout. C'est précisément ce classement qui empêchait le
# placeholder universel de se déclencher — un en-tête déclaré « connu » qui
# n'émet rien crée un angle mort que le filet ne peut pas voir.
_NO_HARDWARE_HEADERS = {
    "arduino.h", "wire.h", "spi.h", "softwareserial.h", "eeprom.h",
    "math.h", "string.h", "stdio.h", "stdlib.h", "stdint.h", "avr/pgmspace.h",
    "arduinojson.h", "pubsubclient.h", "ntpclient.h", "wifi.h", "ethernet.h",
    "wifinina.h", "esp8266wifi.h", "timelib.h",
}


def _warn_shield_not_drawable(nl, code: str) -> bool:
    """Un SHIELD est reconnu, et on explique pourquoi il n'est pas dessine.

    Decision 2026-08-10 : les shields restent hors perimetre (TODO #7), mais
    l'etat d'avant etait le pire des deux mondes — une boite muette a 4 broches
    sortie du placeholder universel, qui laissait croire a un composant a
    cabler dont on ignorait le brochage. Or on ne l'ignore pas : un shield **ne
    se cable pas**, il se monte sur les headers. Dessiner des fils vers lui
    serait dessiner quelque chose qui n'existe pas physiquement.

    On ne produit donc AUCUN composant — et on dit pourquoi. C'est la meme
    discipline que les filets de juillet : ne jamais presenter une devinette
    comme une certitude, et ne jamais se taire non plus.

    Le corpus garde son entree (decision utilisateur) : elle porte l'API de la
    bibliotheque, donc le CODE reste juste. La retirer aurait laisse le RAG
    remonter un driver moteur VOISIN — la substitution qui compile et se trompe
    en silence, mesuree ailleurs le meme jour."""
    if not _INCLUDE_MOTORSHIELD_RE.search(code or ""):
        return False
    nl.add_warning(
        code="shield_not_drawable",
        severity=SEVERITY_INFO,
        message="Shield moteur détecté : un shield se monte sur les broches "
                "de la carte, il n'y a pas de câblage à dessiner.",
        params={"name": "Adafruit Motor Shield V2"},
    )
    return True


def _warn_nothing_detected(nl, code: str) -> None:
    """Netlist VIDE alors que le code inclut une bibliothèque matérielle.

    TODO #47 volet 2. Le silence était le pire symptôme du chantier : rien ne
    distinguait « ce sketch n'a aucun composant » de « je n'ai rien su lire ».
    Les autres filets parlent tous (`unwired_unknown_component`,
    `presumed_i2c_wiring`, `presumed_analog_component`) ; il ne restait que ce
    cas-là, et c'est celui où l'utilisateur voit un schéma entièrement blanc.

    Mesuré sur les 91 exemples du corpus : DEUX produisent une netlist vide,
    `onewire` (qui doit avertir) et `eeprom` (qui ne doit pas — mémoire
    intégrée au microcontrôleur, rien à brancher). La règle les sépare
    exactement, sans seuil ni heuristique.

    On ne crie pas sur un sketch qui n'a légitimement rien à câbler : un blink
    sur la LED interne produit un composant (donc ne passe pas ici), et un
    scanner I2C n'a que `Wire.h`, qui est exempté."""
    if nl.components:
        return
    for header in _INCLUDE_ANY_RE.findall(code or ""):
        if header.strip().lower() not in _NO_HARDWARE_HEADERS:
            nl.add_warning(
                code="nothing_detected",
                severity=SEVERITY_INFO,
                message="Aucun composant n'a pu être déduit de ce code, alors "
                        f"qu'il utilise « {header} ».",
                params={"header": header},
            )
            return


def tag_component_category(c: "Component", *, signature_detected: bool) -> None:
    """Tags a component with its signal category (from its type) and the
    signature_detected flag (True = type from a unique code signature
    Servo.h/I2C lib/FastLED; False = deduced from a bare pin). Drives the
    replacement filtering (category) and the divergence warning."""
    c.attributes["category"] = category_of(c.type)
    c.attributes["signature_detected"] = bool(signature_detected)


def fuse_modules(nl: Netlist, prompt: str, context: str) -> None:
    """Fusionne les puces d'un module NOMME en une seule boite.

    Garde par la declaration : si le prompt/contexte nomme un module ET qu'au
    moins UNE de ses puces est detectee comme composant, on remplace cette/ces
    puce(s) par UNE boite module (4 broches I2C partagees). C'est physiquement
    une seule carte : meme si le code n'utilise qu'une de ses puces (ex. boussole
    = magneto seul), on affiche la boite du module. Sans nom de module : no-op
    (deux cartes reellement separees restent deux boites). Mute `nl` en place."""
    module = detect_module(f"{prompt}\n{context}")
    if module is None:
        return
    present = [c for c in nl.components if c.type in module.chips]
    if len(present) < 1:
        return
    nl.components = [c for c in nl.components if c.type not in module.chips]
    nl.add_component(Component(
        ref=nl.next_ref("U"),
        type=module.id,
        fn_id="",
        inferred=True,
        pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
              Pin("SDA", "A4"), Pin("SCL", "A5")],
        attributes={"_module": module.id},
    ))


def extract_netlist(code: str, board_id: str,
                    prompt: str = "", context: str = "",
                    prompts_by_fn: dict[str, str] | None = None) -> Netlist:
    """Builds a Netlist from the Arduino code and the user prompt.

    Args:
        code     : complete .ino source.
        board_id : catalog id (e.g. "arduino_uno_r3").
        prompt   : user prompt in natural language. Used by the
                   disambiguation layer (`_disambiguate_with_prompt`)
                   to resolve the fallback ambiguities (e.g. distinguish
                   LED/buzzer on a generic OUTPUT).
        context  : content of the attached project context file (BOM, specs,
                   etc.). The most explicit source -- priority over the prompt.

    Strategy depending on `WIRING_DETECTOR_MODE`:
      - "python"     : static detection only (code + prompt + context).
                       The `<<< fn-N_wiring >>>` markers are ignored, even
                       if the AI emits them out of habit. This is the default mode
                       to free ourselves from the marker dependency.
      - "ai_markers" : (legacy) if blocks are present, they take
                       priority. The static detector serves as a fallback.

    Colliding refs (e.g. R1 added by inference and R1 already present)
    are renumbered automatically.
    """
    nl = Netlist(board_id=board_id, metadata={"source": "static"})

    # Scan prompt + user doc for an explicit DC driver name.
    # Result (or None) stored globally -- the inference rule will use it
    # to choose the driver instead of the L298N fallback. We NEVER look at
    # the generated code (see docstring of _detect_suggested_dc_driver).
    suggested = _detect_suggested_dc_driver(prompt, context)
    if suggested is not None:
        nl.metadata["_suggested_dc_driver"] = suggested

    if WIRING_DETECTOR_MODE == "ai_markers":
        # Legacy mode: AI markers take priority, otherwise Python fallback.
        blocks = parse_wiring_blocks(code)
        if blocks:
            nl.metadata["source"] = "ai_markers"
            for fid, comps in blocks.items():
                for c in comps:
                    if c.ref == "?" or nl.by_ref(c.ref) is not None:
                        c.ref = nl.next_ref(_ref_prefix_for(c.type))
                    # `module_generic` = AI's admission of uncertainty, we
                    # mark it ambiguous to bring up the modal.
                    if c.type == "module_generic":
                        c.attributes["_confidence"] = "low"
                    nl.add_component(c)
            # Tagging category + signature_detected on all the components.
            for c in nl.components:
                tag_component_category(
                    c, signature_detected=_is_signature_detected(c)
                )
            return nl

    # "python" mode (default) or no marker in legacy mode:
    # static detector + prompt/context disambiguation.
    # board_id + prompt + context propagated to parse_fallback for
    # Strategy 4 of the DC motor grouping (hardware-fallback via boards.json
    # capabilities, triggered only if the prompt mentions 'motor' + chip).
    inferred, used = parse_fallback(
        code, board_id=board_id, prompt=prompt, context=context,
    )
    if used:
        # Assign fn_id by lookup in the provided prompts (pure Python,
        # no dependency on AI markers in the code).
        _assign_fn_ids(inferred, prompts_by_fn)
        # Disambiguation layer: crosses the ambiguous components (OUTPUT pin
        # classified as LED by default) with the clues from the prompt and the
        # context file. Per-fn when fn_id is known. Mutates the list in place.
        _disambiguate_with_prompt(inferred, prompt, context, prompts_by_fn,
                                  code=code)
        nl.metadata["source"] = "fallback"
        nl.add_warning(
            code="wiring_inferred",
            severity=SEVERITY_INFO,
            # Repli si le gabarit traduit manque : garder la MEME phrase que
            # `instructions._WARNING_TEMPLATES["wiring_inferred"]`, sans la
            # parenthese sur les marqueurs IA (detail d'implementation retire
            # le 2026-08-10).
            message="Le cablage a ete deduit du code et peut etre inexact. "
                    "Tu peux demander de l'aide dans le chat.",
            params={},
        )
        for c in inferred:
            if nl.by_ref(c.ref) is not None:
                c.ref = nl.next_ref(_ref_prefix_for(c.type))
            nl.add_component(c)
    # Warnings des FILETS DE SÉCURITÉ (hors de la branche `fallback` : ils
    # valent pour toutes les sources — revue 2026-07-29). Un composant que le
    # détecteur a produit « faute de mieux » doit le DIRE, sinon une boîte non
    # câblée ou un câblage deviné passent pour du certain.
    for c in nl.components:
        header = c.attributes.get("header", c.type)
        name = header[:-2] if header.lower().endswith(".h") else header
        if c.attributes.get("unrecognized"):
            ctor_pins = c.attributes.get("constructor_pins") or []
            if ctor_pins:
                pins_str = ", ".join(ctor_pins)
                nl.add_warning(
                    code="unwired_unknown_component_pins",
                    severity=SEVERITY_INFO,
                    message=f"Composant « {name} » détecté mais câblage non "
                            f"déduit. Broches vues dans le code : {pins_str}.",
                    refs=[c.ref],
                    params={"name": name, "pins": pins_str},
                )
            else:
                nl.add_warning(
                    code="unwired_unknown_component",
                    severity=SEVERITY_INFO,
                    message=f"Composant « {name} » détecté mais câblage non déduit.",
                    refs=[c.ref],
                    params={"name": name},
                )
        elif c.attributes.get("presumed_wiring"):
            nl.add_warning(
                code="presumed_i2c_wiring",
                severity=SEVERITY_INFO,
                message=f"Câblage I2C présumé pour « {name} ».",
                refs=[c.ref],
                params={"name": name},
            )
        elif c.attributes.get("presumed_from_description"):
            # On a choisi un numero de piece que l'utilisateur n'a jamais
            # ecrit : sa description y ressemblait. Le dire, plutot que de
            # laisser croire que la reference a ete lue quelque part.
            nl.add_warning(
                code="presumed_from_description",
                severity=SEVERITY_INFO,
                message=(f"« {name} » a été déduit de ta description, pas "
                         f"d'une référence exacte — vérifie que c'est bien "
                         f"ce composant."),
                refs=[c.ref],
                params={"name": name},
            )
        elif c.attributes.get("presumed_analog"):
            # Nothing in the code or the prompt corroborated the default: say
            # so, rather than draw a fully-wired 10k pot as if it had been read
            # from the sketch.
            sig = c.pin("W")
            pin_net = sig.net if sig is not None else ""
            nl.add_warning(
                code="presumed_analog_component",
                severity=SEVERITY_INFO,
                message=f"Composant analogique présumé sur {pin_net}.",
                refs=[c.ref],
                params={"pin": pin_net},
            )
    # Composant que le rendu ne saura PAS dessiner (aucun SVG pour ce nombre de
    # broches) : il disparaissait du schéma sans la moindre trace côté layout.
    # On le dit ici, au niveau qui porte les warnings.
    _warn_unrenderable_components(nl)
    # Un shield explique DEJA pourquoi il n'y a rien a dessiner : ajouter
    # « aucun composant n'a pu etre deduit » par-dessus serait une seconde
    # explication qui contredit la premiere.
    if not _warn_shield_not_drawable(nl, code):
        _warn_nothing_detected(nl, code)
    # Tagging category + signature_detected on all the components.
    for c in nl.components:
        tag_component_category(
            c, signature_detected=_is_signature_detected(c)
        )
    # Warning (text) for the components that have pins to wire by hand
    # (register/expander outputs whose load depends on the circuit: 74HC595).
    for c in nl.components:
        pins = c.attributes.get("unwired_pins")
        if pins:
            pins_str = ", ".join(pins)
            nl.add_warning(
                code="unwired_component_pins",
                severity=SEVERITY_INFO,
                message=f"Broches à câbler manuellement : {pins_str}.",
                refs=[c.ref],
                params={"pins": pins_str},
            )
    # Fusion des modules nommes (HW-612...) : plusieurs puces I2C d'une meme
    # carte -> une seule boite. Garde par le nom de module dans prompt/contexte.
    fuse_modules(nl, prompt, context)
    return nl


def _ref_prefix_for(ctype: str) -> str:
    return {
        "led":           "D",
        "resistor":      "R",
        "button":        "S",
        "potentiometer": "P",
        "buzzer":        "BZ",
        "servo":         "SV",
        "dht22":         "U",
        "dht11":         "U",
        "hcsr04":        "U",
        "lcd_i2c":       "U",
        "oled_ssd1306":  "U",
        "relay":         "K",
        "ldr":           "LDR",
        "ky018":         "LDR",
        "thermistor":    "TH",
        "microphone":    "MIC",
        "pir":           "PIR",
        "led_matrix":    "MX",
        "tm1637":        "U",
        "ht16k33":       "U",
        "vl53l0x":       "U",
        "max30102":      "U",
        "tcs34725":      "U",
        "bh1750":        "U",
        "ads1115":       "U",
        "pca9685":       "U",
        "sh1106":        "U",
        "aht20":         "U",
        "st7735":        "U",
        "st7789":        "U",
        "max31855":      "U",
        "hx711":         "U",
        "dfplayer":      "U",
        "sr74hc595":     "U",
        "bmp280": "U", "apds9960": "U", "mlx90614": "U",
        "sgp30": "U", "scd30": "U", "pn532": "U",
        "pcf8574": "U", "mcp23017": "U", "max6675": "U",
        "mcp9808": "U", "si7021": "U", "adxl345": "U", "hmc5883l": "U",
        "mcp4725": "U", "ina260": "U", "as5600": "U", "veml6075": "U",
        "bno055": "U", "mcp9600": "U", "max17043": "U",
        "amg8833": "U", "pm25": "U", "nrf24l01": "U",
        "fingerprint": "U", "drv2605": "U", "tm1638": "U",
        "pcd8544": "U", "ssd1351": "U",
        "module_generic": "U",
    }.get(ctype, "U")
