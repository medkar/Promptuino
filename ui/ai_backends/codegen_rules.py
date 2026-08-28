"""Hardware rules injected into the generation system prompt.

Decomposition of the old `_WIRING_ADDENDUM` (formerly static in base.py)
into three parts, one of which is conditional:

- P1 `_HARDWARE_RULE`        : universal rule (5V rail ~500 mA, external
  power for motors/relays/LED strips/solenoids). ALWAYS injected.
- P2 `_DISAMBIGUATION_RULE`  : "if outputs are ambiguous, do not default to
  motor -> prefer LEDs/GPIO". ALWAYS injected (targets prompts WITHOUT a
  motor keyword).
- P3 `_MOTOR_RULES`          : driver catalog + DC code pattern + example.
  Injected ONLY if `mentions_motor(prompt)`.

Gating is now real (Python): the phrase "apply ONLY when the prompt mentions
a motor" from the old addendum is removed (no longer needed).

`_MOTOR_GEN_KEYWORDS` lexicon: BROAD and DEDICATED to generation (separate
from `markers._MOTOR_KEYWORDS` to avoid polluting wiring disambiguation).
A false positive costs a few lines; a false negative produces bad motor
code -> we prefer broad. Common cross-language collisions ("car" FR
conjunction, "coche" FR for "tick/check") are deliberately EXCLUDED.
Matching is case/accent-insensitive and bounded by word boundaries
("fan" does not match "enfant").
"""
import re
import unicodedata


_HARDWARE_RULE = (
    "HARDWARE RULE (universal, applies to every program):\n"
    "The Arduino 5V rail is limited to ~500 mA. Any actuator that draws more\n"
    "(motors, relays, high-power LED strips, solenoids) MUST be powered by\n"
    "an EXTERNAL supply (battery / adapter), not the Arduino 5V pin."
)

_DISAMBIGUATION_RULE = (
    "DISAMBIGUATION RULE — when the prompt is ambiguous about what's\n"
    "connected (e.g. \"activate 3 outputs\", \"control these pins\", \"use\n"
    "D5/D6/D7\"), DO NOT default to motor. Default to the SIMPLEST safe\n"
    "interpretation : individual GPIO outputs with `digitalWrite` (and\n"
    "optional `analogWrite` for PWM pins) — i.e. think LEDs/voyants/\n"
    "indicators, NOT a motor + driver. The user can clarify their intent\n"
    "separately if they actually wanted a motor."
)

_SEP = "═" * 71

_MOTOR_RULES = (
    f"{_SEP}\n"
    "MOTOR RULES START — the program below drives a motor.\n"
    f"{_SEP}\n"
    "\n"
    "When driving a motor :\n"
    "- name the driver chip explicitly. Catalog : L298N / L293D / TB6612FNG /\n"
    "  DRV8833 (DC) ; A4988 / DRV8825 / ULN2003 (stepper).\n"
    "- describe each Arduino pin as connected to a SPECIFIC driver INPUT\n"
    "  (e.g. \"PWM to L298N ENA\", \"DIR to A4988 DIR\"), never to the motor\n"
    "  itself. The motor connects to the driver OUTPUTS (OUT1/OUT2 etc.).\n"
    "- NEVER write \"to motor base\" / \"transistor/driver\" / \"to motor pin\".\n"
    "- NEVER suggest the motor connects directly to an Arduino pin.\n"
    "\n"
    "DC motor code pattern (skip for stepper) — strict, even for 1 motor :\n"
    "Factor DC motor control through ONE parametrized helper :\n"
    "    void setMotor(uint8_t pwmPin, uint8_t in1Pin, uint8_t in2Pin, int speed);\n"
    "Call it once per motor with explicit pin constants. NEVER :\n"
    "- dispatch on a motor id like `if (motorNum == 1) { pwmPin = 5; ... }`\n"
    "  then `analogWrite(pwmPin, ...)` — local-variable indirection forbidden.\n"
    "- define separate per-motor functions (setMotor1Speed, setMotor2Speed)\n"
    "  when one parametrized helper covers every motor.\n"
    "- inline analogWrite/digitalWrite for the motor directly in loop().\n"
    "\n"
    "Correct DC motor example :\n"
    "  void setMotor(uint8_t pwmPin, uint8_t in1Pin, uint8_t in2Pin, int speed) {\n"
    "    digitalWrite(in1Pin, speed >= 0 ? HIGH : LOW);\n"
    "    digitalWrite(in2Pin, speed >= 0 ? LOW  : HIGH);\n"
    "    analogWrite(pwmPin, abs(speed));\n"
    "  }\n"
    "  // L298N powered by external battery (Arduino 5V cannot drive a motor).\n"
    "  setMotor(PIN_M1_PWM, PIN_M1_IN1, PIN_M1_IN2,  200);\n"
    "  setMotor(PIN_M2_PWM, PIN_M2_IN1, PIN_M2_IN2, -150);\n"
    "\n"
    f"{_SEP}\n"
    "MOTOR RULES END\n"
    f"{_SEP}"
)

# Broad lexicon dedicated to generation (already normalized: lowercase, no accents).
# Deduplicated (motor/robot/pompa shared across languages appear only once).
# Word-boundary matching -> no false positives from substrings.
# FR collisions excluded: "car", "coche".
_MOTOR_GEN_KEYWORDS = (
    # FR
    "moteur", "moteurs", "motorisation", "motorise", "motorisee",
    "ventilateur", "ventilateurs", "ventilo",
    "helice", "helices", "roue", "roues", "voiture", "voitures",
    "pompe", "pompes", "treuil",
    # EN
    "motor", "motors", "motorized", "fan", "fans",
    "propeller", "propellers", "wheel", "wheels", "pump", "pumps",
    # ES
    "motores", "ventilador", "ventiladores", "rueda", "ruedas", "bomba",
    # IT
    "motore", "motori", "ventola", "ventilatore", "elica",
    "ruota", "ruote", "pompa",
    # commun multi-langue
    "robot", "robots",
    # stepper (mono- et multi-mots)
    "stepper", "steppers", "pas a pas", "paso a paso", "passo passo",
    # chips driver
    "l298n", "l293d", "tb6612fng", "tb6612", "drv8833",
    "a4988", "drv8825", "uln2003",
)


def _normalize(text: str) -> str:
    """Lowercase + accent stripping (NFKD -> ASCII) for case/accent-insensitive matching."""
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = decomposed.encode("ascii", "ignore").decode("ascii")
    return stripped.lower()


# Main regex: \b boundaries on both sides (avoids false positives in common
# words — e.g. "fan" inside "enfant").
_MOTOR_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in _MOTOR_GEN_KEYWORDS) + r")\b"
)

# Secondary regex: "motor/moteur/..." keywords as a camelCase SUFFIX
# (e.g. setMotor, driveMotor, servomoteur). No left boundary — only the
# right boundary is required to avoid matching "motorizacion" mid-word.
# Limitation: forms where the root is a PREFIX followed by other letters
# (e.g. `motorSpeed`, `MOTOR_SPEED`) are NOT detected (no right boundary).
# Limited to multilingual roots of "motor" (very low false-positive risk
# as a camelCase suffix, unlike "fan" inside "enfant").
_MOTOR_CORE = ("motor", "motors", "moteur", "moteurs", "motore", "motori",
               "motores")
_MOTOR_SUFFIX_RE = re.compile(
    r"(?:" + "|".join(re.escape(k) for k in _MOTOR_CORE) + r")\b"
)


def mentions_motor(text: str) -> bool:
    """True if `text` mentions a motor / rotary actuator / driver chip
    (broad FR/EN/ES/IT lexicon). None or empty -> False.

    Also detects camelCase identifiers where the root is a SUFFIX
    (e.g. `setMotor`, `driveMotor`, `servomoteur`) via `_MOTOR_SUFFIX_RE`.
    Limitation: forms where the root is a PREFIX followed by other letters
    (e.g. `motorSpeed`, `MOTOR_SPEED`) are NOT detected (no right boundary
    after the root).
    """
    if not text:
        return False
    normalized = _normalize(text)
    return bool(_MOTOR_RE.search(normalized) or _MOTOR_SUFFIX_RE.search(normalized))


def build_wiring_addendum(text: str) -> str:
    """Assembles the hardware addendum: P1 + P2 always, + P3 if motor.

    Always returns a non-empty string (P1 + P2 are unconditional) —
    callers do not need a `if addendum:` guard.
    """
    parts = [_HARDWARE_RULE, _DISAMBIGUATION_RULE]
    if mentions_motor(text):
        parts.append(_MOTOR_RULES)
    return "\n\n".join(parts)
