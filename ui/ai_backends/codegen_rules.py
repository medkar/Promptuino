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

# ⚠️ **Le bloc MOTOR est en DEUX variantes depuis le 2026-08-31**, et c'est
# une mesure A/B qui l'a impose (QA AB2 du #82, gemma4:e2b, 6 generations par
# bras) : sans ce bloc 0/6 chimeres, avec lui 3/6 — sur « 2 moteurs DC avec
# un L298N », le RAG injecte l'API de la BIBLIOTHEQUE sous en-tete imperatif
# pendant que le pattern ci-dessous ordonne le helper broches-nues « strict,
# even for 1 motor ». Le modele epissait les deux (`motor1.digitalWrite(...)`),
# le code ne compilait pas, et la reparation derivait vers le `setMotor`
# qu'on lui ordonnait. Ce conflit n'avait que deux jours : l'entree corpus
# L298N date du #83.
#
# La partie PROSE (nommer le driver, decrire chaque broche vers une entree du
# driver, jamais « to motor pin ») vaut dans les deux mondes. Le PATTERN
# broches-nues cede la place a la bibliotheque quand elle est injectee — et
# la contre-consigne est EXPLICITE : sans elle, le biais d'entrainement du
# modele (les tutoriels L298N en ligne sont massivement en broches nues)
# reprend le dessus meme sans le pattern.
_MOTOR_PROSE = (
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
)

_MOTOR_CODE_PATTERN = (
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
)

_MOTOR_LIB_LEADS = (
    "Motor control code pattern :\n"
    "A motor-driver LIBRARY context is provided below — drive the motors\n"
    "through THAT library's API only (constructor + its methods).\n"
    "- do NOT write a bare-pin setMotor() helper ;\n"
    "- do NOT call analogWrite/digitalWrite for the motors ;\n"
    "- do NOT invent methods on the library objects : use only the API\n"
    "  signatures listed in the library context.\n"
    "\n"
)

_MOTOR_END = (
    f"{_SEP}\n"
    "MOTOR RULES END\n"
    f"{_SEP}"
)

_MOTOR_RULES = _MOTOR_PROSE + _MOTOR_CODE_PATTERN + _MOTOR_END
_MOTOR_RULES_LIB = _MOTOR_PROSE + _MOTOR_LIB_LEADS + _MOTOR_END

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


def _names_motor_driver_lib(text: str) -> bool:
    """Le prompt nomme-t-il un driver moteur a BIBLIOTHEQUE ? (cf. rag)

    Import tardif et garde : `rag` charge le corpus ; si quoi que ce soit
    echoue, on degrade vers l'ancien comportement (pattern broches-nues) —
    une erreur d'import ne doit pas changer la forme du prompt systeme.
    """
    try:
        from ..rag import prompt_names_motor_driver_lib
        return prompt_names_motor_driver_lib(text)
    except Exception:
        return False


def build_wiring_addendum(text: str) -> str:
    """Assembles the hardware addendum: P1 + P2 always, + P3 if motor.

    Always returns a non-empty string (P1 + P2 are unconditional) —
    callers do not need a `if addendum:` guard.

    ⚠️ P3 a DEUX variantes (mesure A/B du 2026-08-31, cf. le commentaire de
    `_MOTOR_PROSE`) : quand le prompt nomme un driver dont le corpus porte
    une bibliotheque, le RAG l'injecte imperativement et c'est ELLE qui
    pilote — le pattern broches-nues devenait une consigne contradictoire
    (3/6 chimeres qui ne compilaient pas).
    """
    parts = [_HARDWARE_RULE, _DISAMBIGUATION_RULE]
    if mentions_motor(text):
        parts.append(_MOTOR_RULES_LIB if _names_motor_driver_lib(text)
                     else _MOTOR_RULES)
    return "\n\n".join(parts)
