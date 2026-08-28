"""Test standalone du matching semantique etendu pour la disambiguation
de cablage (Fonctionnalite 2, etapes 1+2 du pipeline cascade).

Couvre :
- Les 7 nouveaux lexiques FR/EN/ES/IT (servo, pot, LDR, temp, sound,
  keypad, stepper) -- detection du keyword sur les 4 langues
- Le helper `_choose_type_from_text` (cascade context > prompt + conflit)
- Les annotations end-to-end via `analyze_netlist` (LED -> servo,
  potentiometre -> subtype, etc.)
- Non-regression sur les cas existants (LED -> buzzer, LED -> motor)

Run : python scripts/test_wiring_disambiguation.py
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.markers import (
    _has_keyword,
    _choose_type_from_text,
    _LED_KEYWORDS, _BUZZER_KEYWORDS, _MOTOR_KEYWORDS,
    _SERVO_KEYWORDS, _POT_KEYWORDS, _LDR_KEYWORDS, _KY018_KEYWORDS,
    _TEMP_SENSOR_KEYWORDS, _SOUND_SENSOR_KEYWORDS,
    _KEYPAD_KEYWORDS, _STEPPER_KEYWORDS,
    _LED_RECLASSIF_CANDIDATES, _POT_SUBTYPE_CANDIDATES,
    _BTN_SUBTYPE_CANDIDATES, _PIR_KEYWORDS,
    _split_identifier, _humanize_identifier,
    _pin_to_identifiers, _code_excerpt_for_pin,
    _ref_prefix_for,
)
from ui.wiring.markers import _LED_COLOR_KEYWORDS
from ui.wiring.instructions import render_instructions, _LED_COLOR_LABEL
from ui.wiring.layout.pipeline import analyze_netlist
from ui.wiring.instructions import _label


# ─── 1. Tests lexiques FR/EN/ES/IT ───────────────────────────────────────

def test_servo_keywords_multilang():
    assert _has_keyword("commande un servo a 90 degres", _SERVO_KEYWORDS)
    assert _has_keyword("control the servomotor", _SERVO_KEYWORDS)
    assert _has_keyword("controla el servomotor", _SERVO_KEYWORDS)
    assert _has_keyword("controlla il servomotore", _SERVO_KEYWORDS)
    assert _has_keyword("regle l'angle a 45", _SERVO_KEYWORDS)
    assert not _has_keyword("allume une LED rouge", _SERVO_KEYWORDS)


def test_pot_keywords_multilang():
    assert _has_keyword("tourne le potentiometre", _POT_KEYWORDS)
    assert _has_keyword("read the potentiometer", _POT_KEYWORDS)
    assert _has_keyword("lee el potenciometro", _POT_KEYWORDS)
    assert _has_keyword("leggi il potenziometro", _POT_KEYWORDS)
    assert _has_keyword("regle le potar", _POT_KEYWORDS)
    assert not _has_keyword("allume une LED", _POT_KEYWORDS)


def test_ldr_keywords_multilang():
    assert _has_keyword("capteur de lumiere sur A0", _LDR_KEYWORDS)
    assert _has_keyword("LDR connectee a A0", _LDR_KEYWORDS)
    assert _has_keyword("light sensor on A0", _LDR_KEYWORDS)
    assert _has_keyword("sensor de luz", _LDR_KEYWORDS)
    assert _has_keyword("sensore di luce", _LDR_KEYWORDS)
    assert _has_keyword("mesure la luminosite", _LDR_KEYWORDS)


def test_ky018_keywords():
    assert _has_keyword("branche un ky-018 sur A0", _KY018_KEYWORDS)
    assert _has_keyword("module KY018", _KY018_KEYWORDS)
    assert _has_keyword("capteur ky 018", _KY018_KEYWORDS)
    # Les mots génériques de lumière NE matchent PAS ky018 (ils restent LDR)
    assert not _has_keyword("capteur de lumiere sur A0", _KY018_KEYWORDS)


def test_temp_sensor_keywords_multilang():
    assert _has_keyword("mesure la temperature", _TEMP_SENSOR_KEYWORDS)
    assert _has_keyword("thermistance NTC", _TEMP_SENSOR_KEYWORDS)
    assert _has_keyword("read the thermistor", _TEMP_SENSOR_KEYWORDS)
    assert _has_keyword("medir la temperatura", _TEMP_SENSOR_KEYWORDS)
    assert _has_keyword("misura la temperatura", _TEMP_SENSOR_KEYWORDS)
    assert _has_keyword("LM35 sur A1", _TEMP_SENSOR_KEYWORDS)


def test_sound_sensor_keywords_multilang():
    assert _has_keyword("capteur de son", _SOUND_SENSOR_KEYWORDS)
    assert _has_keyword("un microphone sur A0", _SOUND_SENSOR_KEYWORDS)
    assert _has_keyword("sound sensor", _SOUND_SENSOR_KEYWORDS)
    assert _has_keyword("sensor de sonido", _SOUND_SENSOR_KEYWORDS)
    assert _has_keyword("microfono", _SOUND_SENSOR_KEYWORDS)
    assert _has_keyword("sensore sonoro", _SOUND_SENSOR_KEYWORDS)


def test_keypad_keywords_multilang():
    assert _has_keyword("un clavier matriciel", _KEYPAD_KEYWORDS)
    assert _has_keyword("keypad 4x4", _KEYPAD_KEYWORDS)
    assert _has_keyword("keyboard matrix", _KEYPAD_KEYWORDS)
    assert _has_keyword("teclado 4x4", _KEYPAD_KEYWORDS)
    assert _has_keyword("tastierino", _KEYPAD_KEYWORDS)
    assert _has_keyword("matrice de boutons", _KEYPAD_KEYWORDS)


def test_stepper_keywords_multilang():
    assert _has_keyword("moteur pas-a-pas", _STEPPER_KEYWORDS)
    assert _has_keyword("NEMA17 sur A4988", _STEPPER_KEYWORDS)
    assert _has_keyword("stepper motor", _STEPPER_KEYWORDS)
    assert _has_keyword("paso a paso", _STEPPER_KEYWORDS)
    assert _has_keyword("motore passo-passo", _STEPPER_KEYWORDS)
    assert _has_keyword("step motor", _STEPPER_KEYWORDS)


# ─── Code-based deduction helpers ────────────────────────────────────────

def test_split_identifier_camel_snake_digits():
    assert _split_identifier("soundSensor") == ["sound", "sensor"]
    assert _split_identifier("RELAY_PIN") == ["relay", "pin"]
    assert _split_identifier("ldrValue") == ["ldr", "value"]
    assert _split_identifier("pir2") == ["pir"]
    assert _split_identifier("x") == ["x"]


def test_humanize_identifier_strips_pin_suffix():
    assert _humanize_identifier("RELAY_PIN") == "Relay"
    assert _humanize_identifier("soundSensor") == "Sound sensor"
    assert _humanize_identifier("flowMeterPin") == "Flow meter"
    assert _humanize_identifier("ldr") == "Ldr"
    # Tout-suffixe : ne pas renvoyer une chaine vide
    assert _humanize_identifier("pin") == "Pin"


def test_pin_to_identifiers_const_and_recv_var():
    code = (
        "const int soundSensor = A0;\n"
        "#define RELAY_PIN 7\n"
        "void loop() { int ldrValue = analogRead(A1); }\n"
    )
    m = _pin_to_identifiers(code)
    assert "soundSensor" in m.get("A0", [])
    assert "RELAY_PIN" in m.get("D7", [])
    assert "ldrValue" in m.get("A1", [])


def test_code_excerpt_for_pin_identifier_and_comment():
    code = (
        "const int soundSensor = A0;\n"
        "void loop() { analogRead(A0); // capteur de son principal\n }\n"
    )
    p2n = _pin_to_identifiers(code)
    exc = _code_excerpt_for_pin(code, "A0", p2n)
    assert "sound sensor" in exc.lower()
    assert "capteur de son" in exc.lower()


def test_code_excerpt_no_sensor_keyword_when_anonymous_var():
    code = "void loop() { int v = analogRead(A0); }\n"
    p2n = _pin_to_identifiers(code)
    exc = _code_excerpt_for_pin(code, "A0", p2n)
    # "v" -> "v", aucun mot-cle de capteur ; pas de commentaire
    assert "capteur" not in exc.lower()


def test_code_excerpt_digital_no_false_comment_match():
    """Un commentaire sur une ligne mentionnant un petit chiffre ne doit pas
    polluer l'extrait d'une broche digitale (D1 -> '1')."""
    code = (
        "void setup(){ pinMode(1, OUTPUT); }\n"
        "void loop(){ if (count == 1) { } // relais de la pompe\n"
        "  digitalWrite(1, HIGH); }\n"
    )
    p2n = _pin_to_identifiers(code)
    exc = _code_excerpt_for_pin(code, "D1", p2n)
    assert "relais" not in exc.lower(), f"false comment match: {exc!r}"


# ─── 2. Tests _choose_type_from_text (cascade) ───────────────────────────

def test_choose_context_wins_alone():
    """Context tranche tout seul quand un seul type matche."""
    res = _choose_type_from_text(
        excerpt="active la broche 9",
        prompt="active la broche 9",
        context="j'ai un servo SG90",
        candidates=_LED_RECLASSIF_CANDIDATES,
    )
    assert res == "servo", f"expected servo, got {res}"


def test_choose_excerpt_wins_when_context_silent():
    """Excerpt tranche quand context silencieux."""
    res = _choose_type_from_text(
        excerpt="active le buzzer sur D7",
        prompt="active le buzzer sur D7",
        context="",
        candidates=_LED_RECLASSIF_CANDIDATES,
    )
    assert res == "buzzer", f"expected buzzer, got {res}"


def test_choose_context_overrules_prompt():
    """Conflit context (LED) vs prompt (motor) -> rien (None) car le
    matériel insiste sur LED."""
    res = _choose_type_from_text(
        excerpt="fais tourner le moteur sur D5",
        prompt="fais tourner le moteur sur D5",
        context="j'ai 3 LEDs rouges",
        candidates=_LED_RECLASSIF_CANDIDATES,
    )
    # Context says "led" alone -> returns "led" (= no mutation)
    assert res == "led", f"expected led (material wins), got {res}"


def test_choose_context_ambigu_falls_back_to_prompt():
    """Context mentionne plusieurs types (>= 2) -> on tombe sur prompt."""
    res = _choose_type_from_text(
        excerpt="fais tourner le moteur sur D5",
        prompt="fais tourner le moteur sur D5",
        context="j'ai 3 LEDs ET un moteur DC",
        candidates=_LED_RECLASSIF_CANDIDATES,
    )
    # Context contient {led, dc_motor} >= 2 -> step 2 (excerpt) = motor
    # Conflict check : motor est dans context_hits -> pas de conflit
    assert res == "dc_motor", f"expected dc_motor, got {res}"


def test_choose_silent_returns_none():
    """Ni context ni prompt ne matchent -> None."""
    res = _choose_type_from_text(
        excerpt="active la broche 7",
        prompt="active la broche 7",
        context="",
        candidates=_LED_RECLASSIF_CANDIDATES,
    )
    assert res is None, f"expected None, got {res}"


def test_choose_excerpt_ambigu_returns_none():
    """Excerpt mentionne plusieurs types -> None (pas de tranche unique)."""
    res = _choose_type_from_text(
        excerpt="la LED clignote et le buzzer sonne",
        prompt="la LED clignote et le buzzer sonne",
        context="",
        candidates=_LED_RECLASSIF_CANDIDATES,
    )
    assert res is None, f"expected None, got {res}"


def test_choose_pot_subtype_ldr():
    """LDR case via 'lumière'."""
    res = _choose_type_from_text(
        excerpt="capteur de lumiere sur A0",
        prompt="capteur de lumiere sur A0",
        context="",
        candidates=_POT_SUBTYPE_CANDIDATES,
    )
    assert res == "ldr", f"expected ldr, got {res}"


def test_choose_pot_subtype_ky018():
    """KY-018 nommé -> ky018 ; collision avec mots de lumière -> ky018 gagne."""
    # Numéro de pièce seul
    assert _choose_type_from_text(
        excerpt="branche un ky-018 sur A0", prompt="branche un ky-018 sur A0",
        context="", candidates=_POT_SUBTYPE_CANDIDATES) == "ky018"
    # Collision : "capteur de lumière" + "ky-018" -> ky018 (plus spécifique)
    assert _choose_type_from_text(
        excerpt="capteur de lumiere ky-018 sur A0",
        prompt="capteur de lumiere ky-018 sur A0",
        context="", candidates=_POT_SUBTYPE_CANDIDATES) == "ky018"
    # Mots génériques seuls -> ldr (non régressé)
    assert _choose_type_from_text(
        excerpt="capteur de lumiere sur A0", prompt="capteur de lumiere sur A0",
        context="", candidates=_POT_SUBTYPE_CANDIDATES) == "ldr"


def test_choose_pot_subtype_thermistor():
    """Cas thermistor via 'temperature'."""
    res = _choose_type_from_text(
        excerpt="lis la temperature sur A0",
        prompt="lis la temperature sur A0",
        context="",
        candidates=_POT_SUBTYPE_CANDIDATES,
    )
    assert res == "thermistor", f"expected thermistor, got {res}"


def test_choose_pot_subtype_microphone():
    """Cas microphone via 'microphone'."""
    res = _choose_type_from_text(
        excerpt="lis le microphone sur A0",
        prompt="lis le microphone sur A0",
        context="",
        candidates=_POT_SUBTYPE_CANDIDATES,
    )
    assert res == "microphone", f"expected microphone, got {res}"


# ─── 3. Tests end-to-end via analyze_netlist ─────────────────────────────

CODE_PWM = """
const int PIN = 9;
void setup() { pinMode(PIN, OUTPUT); }
void loop() { analogWrite(PIN, 128); delay(1000); }
"""

CODE_ANALOG = """
void setup() {}
void loop() { int v = analogRead(A0); delay(50); }
"""

def _find_led(netlist):
    return next((c for c in netlist.components if c.type == "led"), None)


def _find_buzzer(netlist):
    return next((c for c in netlist.components if c.type == "buzzer"), None)


def test_e2e_led_to_servo_annotation():
    nl = analyze_netlist(CODE_PWM, "uno_r3",
                          prompt="commande un servo sur la broche 9")
    led = _find_led(nl)
    assert led is not None
    sug = led.attributes.get("_prompt_suggested_type")
    assert sug == "servo", f"expected servo, got {sug}"


def test_e2e_led_to_stepper_annotation():
    nl = analyze_netlist(CODE_PWM, "uno_r3",
                          prompt="commande un moteur pas-a-pas sur la broche 9")
    led = _find_led(nl)
    assert led is not None
    sug = led.attributes.get("_prompt_suggested_type")
    assert sug == "stepper", f"expected stepper, got {sug}"


def test_e2e_led_to_buzzer_mutation():
    """Non-regression : LED -> buzzer mute toujours quand le prompt
    explicite (cas existant avant l'extension)."""
    nl = analyze_netlist(CODE_PWM, "uno_r3",
                          prompt="active le buzzer sur la broche 9")
    buzzer = _find_buzzer(nl)
    assert buzzer is not None, "expected buzzer mutation"


def test_e2e_led_to_motor_annotation():
    """Non-regression : LED -> dc_motor annotation toujours active."""
    nl = analyze_netlist(CODE_PWM, "uno_r3",
                          prompt="fais tourner le moteur sur la broche 9")
    led = _find_led(nl)
    assert led is not None
    sug = led.attributes.get("_prompt_suggested_type")
    assert sug == "dc_motor", f"expected dc_motor, got {sug}"


def test_e2e_potentiometer_to_ldr():
    nl = analyze_netlist(CODE_ANALOG, "uno_r3",
                          prompt="lis le capteur de lumiere sur A0")
    ldr = _find_by_type(nl, "ldr")
    assert ldr is not None, "expected pot -> ldr mutation"
    nets = {p.name: p.net for p in ldr.pins}
    assert nets.get("OUT") == "A0", f"expected OUT=A0, got {nets}"
    assert nets.get("VCC") == "5V" and nets.get("GND") == "GND"
    assert _find_by_type(nl, "potentiometer") is None


def test_e2e_potentiometer_to_ky018():
    nl = analyze_netlist(CODE_ANALOG, "uno_r3",
                          prompt="lis le capteur ky-018 sur A0")
    ky = _find_by_type(nl, "ky018")
    assert ky is not None, "expected pot -> ky018 mutation"
    nets = {p.name: p.net for p in ky.pins}
    # Pinout KY-018 propre : GND / VCC / S (S = broche analogique)
    assert nets.get("S") == "A0", f"expected S=A0, got {nets}"
    assert nets.get("VCC") == "5V" and nets.get("GND") == "GND"
    assert _find_by_type(nl, "ldr") is None
    assert _find_by_type(nl, "potentiometer") is None


def test_e2e_potentiometer_to_thermistor():
    nl = analyze_netlist(CODE_ANALOG, "uno_r3",
                          prompt="lis la temperature sur A0")
    assert _find_by_type(nl, "thermistor") is not None
    assert _find_by_type(nl, "potentiometer") is None


def test_e2e_potentiometer_to_microphone():
    nl = analyze_netlist(CODE_ANALOG, "uno_r3",
                          prompt="lis le microphone sur A0")
    mic = _find_by_type(nl, "microphone")
    assert mic is not None
    nets = {p.name: p.net for p in mic.pins}
    assert nets.get("OUT") == "A0", f"expected OUT=A0, got {nets}"
    assert nets.get("VCC") == "5V" and nets.get("GND") == "GND"
    assert _find_by_type(nl, "potentiometer") is None


def test_e2e_potentiometer_explicit_no_subtype():
    """'potentiometre' explicite -> reste potentiometre (pas de mutation)."""
    nl = analyze_netlist(CODE_ANALOG, "uno_r3",
                          prompt="lis le potentiometre sur A0")
    assert _find_by_type(nl, "potentiometer") is not None


def test_e2e_material_wins_conflict():
    """Materiel = 'LDR seule', prompt = 'potentiometre' -> ldr (materiel
    l'emporte) et mute."""
    nl = analyze_netlist(CODE_ANALOG, "uno_r3",
                          prompt="lis le potentiometre sur A0",
                          context="J'ai une LDR")
    assert _find_by_type(nl, "ldr") is not None
    assert _find_by_type(nl, "potentiometer") is None


def test_e2e_material_blocks_motor_when_only_leds():
    """Materiel = '3 LEDs seulement', prompt = 'moteur' -> reste LED."""
    nl = analyze_netlist(CODE_PWM, "uno_r3",
                          prompt="fais tourner le moteur sur D9",
                          context="3 LEDs rouges")
    led = _find_led(nl)
    assert led is not None
    sug = led.attributes.get("_prompt_suggested_type")
    assert sug is None, f"expected no suggestion (material blocks), got {sug}"


def test_e2e_context_only_servo():
    """Context tout seul (prompt silencieux) tranche pour servo."""
    nl = analyze_netlist(CODE_PWM, "uno_r3",
                          prompt="active la broche 9",
                          context="composant : servo SG90")
    led = _find_led(nl)
    assert led is not None
    sug = led.attributes.get("_prompt_suggested_type")
    assert sug == "servo", f"expected servo from context, got {sug}"


def test_e2e_context_only_ldr_via_bom():
    """Context BOM = LDR seul, prompt vague -> mutation ldr."""
    nl = analyze_netlist(CODE_ANALOG, "uno_r3",
                          prompt="lis la valeur sur A0",
                          context="materiel : 1 LDR")
    assert _find_by_type(nl, "ldr") is not None


def test_e2e_analog_subtype_from_code_identifier():
    """Le nom de constante 'soundSensor' suffit a muter pot -> microphone,
    SANS prompt."""
    code = (
        "const int soundSensor = A0;\n"
        "void loop() { int v = analogRead(soundSensor); }\n"
    )
    nl = analyze_netlist(code, "uno_r3")
    mic = _find_by_type(nl, "microphone")
    assert mic is not None, "expected pot -> microphone from code identifier"
    nets = {p.name: p.net for p in mic.pins}
    assert nets.get("OUT") == "A0"


def test_e2e_generic_analog_stays_pot():
    """Identifiant neutre + pas de prompt -> reste potentiometre."""
    nl = analyze_netlist(CODE_ANALOG, "uno_r3")
    assert _find_by_type(nl, "potentiometer") is not None


def test_e2e_led_color_still_works():
    """Non-regression couleur : 'LED rouge' annote color=red."""
    nl = analyze_netlist(CODE_PWM, "uno_r3",
                          prompt="allume une LED rouge sur la broche 9")
    led = _find_led(nl)
    assert led is not None
    assert led.attributes.get("color") == "red"


def test_e2e_led_without_named_color_has_none():
    """L'autre moitie du contrat (2026-07-30) : aucune couleur nommee =>
    AUCUNE couleur annotee. Le detecteur posait `color=red` en dur sur toute
    sortie generique, si bien que les instructions de cablage disaient « LED
    rouge » pour une LED dont personne ne connaissait la couleur -- et que
    n'importe quelle valeur inattendue tombant sur le repli devenait une LED
    rouge. Le code ne peut PAS connaitre la couleur ; seul le prompt peut."""
    for prompt in (None, "allume une LED sur la broche 9",
                   "fais clignoter une diode"):
        nl = analyze_netlist(CODE_PWM, "uno_r3", prompt=prompt)
        led = _find_led(nl)
        assert led is not None, prompt
        assert not led.attributes.get("color"), (prompt,
                                                 led.attributes.get("color"))


def test_led_color_label_covers_every_detected_color():
    """Garde de derive : toute couleur que markers sait DETECTER doit avoir un
    libelle dans les 4 langues. Sinon la couleur remonte en anglais brut dans
    une instruction francaise (ce que faisait « LED red D1 » avant 2026-07-30)."""
    assert set(_LED_COLOR_LABEL) == set(_LED_COLOR_KEYWORDS), (
        set(_LED_COLOR_KEYWORDS) ^ set(_LED_COLOR_LABEL))
    for color, labels in _LED_COLOR_LABEL.items():
        for lg in ("fr", "en", "es", "it"):
            assert labels.get(lg), (color, lg)


def test_led_instruction_color_agnostic_then_localized():
    """L'instruction de cablage ne parle de couleur que si l'utilisateur en a
    nomme une, et alors dans SA langue (adjectif avant le nom en anglais,
    apres ailleurs)."""
    import re
    nl_plain = analyze_netlist(CODE_PWM, "uno_r3",
                               prompt="allume une LED sur la broche 9")
    for lg in ("fr", "en", "es", "it"):
        txt = render_instructions(nl_plain, "simple", lg).lower()
        # Limites de MOT : « red » est un sous-mot de « required », « wired »…
        for word in ("red", "rouge", "rosso", "roja"):
            assert not re.search(rf"\b{word}\b", txt), (lg, word)

    nl_blue = analyze_netlist(CODE_PWM, "uno_r3",
                              prompt="allume une LED bleue sur la broche 9")
    expected = {"fr": "bleue", "en": "blue", "es": "azul", "it": "blu"}
    for lg, word in expected.items():
        txt = render_instructions(nl_blue, "simple", lg)
        assert word in txt.lower(), (lg, word, txt[:200])
    # Anglais : l'adjectif precede le nom.
    assert "blue LED" in render_instructions(nl_blue, "simple", "en")
    # Et la couleur nommee pilote toujours la resistance serie (330 Ω pour une
    # bleue, contre 220 par defaut) -- le vrai gain fonctionnel du correctif.
    r = next(c for c in nl_blue.components if c.type == "resistor")
    assert r.attributes.get("value") == "330", r.attributes


# ─── 4. Confirmation globale "LED" sans broche nommee (bug 2026-06-02) ────
# Prompt "Ajoute une led qui clignote" : le mot "led" est present mais aucune
# broche n'est nommee (l'IA choisit la pin, souvent 13/LED_BUILTIN). Le
# scoping per-pin ne peut pas matcher -> la LED restait ambigue (low) et la
# modale d'ambiguite s'ouvrait a tort en mode int/avance.

def test_e2e_global_led_no_pin_resolves():
    """'led' mentionne globalement sans broche -> LED confirmee (pas low),
    donc plus de modale a tort."""
    nl = analyze_netlist(CODE_PWM, "uno_r3",
                          prompt="Ajoute une led qui clignote")
    led = _find_led(nl)
    assert led is not None
    conf = led.attributes.get("_confidence")
    assert conf != "low", f"LED encore ambigue (low), attendu medium/high : {conf}"


def test_e2e_global_no_type_stays_ambiguous():
    """Non-regression : prompt vague sans type ('active la sortie') -> la
    LED reste ambigue (low) -> modale legitime."""
    nl = analyze_netlist(CODE_PWM, "uno_r3",
                          prompt="active la sortie")
    led = _find_led(nl)
    assert led is not None
    conf = led.attributes.get("_confidence")
    assert conf == "low", f"attendu low (ambigu), got {conf}"


def test_e2e_global_led_plus_competing_stays_ambiguous():
    """Non-regression : 'une led et un buzzer' sans broche -> on ne sait pas
    quelle pin est quoi -> la LED reste ambigue (low)."""
    nl = analyze_netlist(CODE_PWM, "uno_r3",
                          prompt="ajoute une led et un buzzer")
    led = _find_led(nl)
    assert led is not None
    conf = led.attributes.get("_confidence")
    assert conf == "low", f"attendu low (types concurrents), got {conf}"


# ─── Enrichissement lexiques (2026-06-11) ───────────────────────────────

def test_enriched_beginner_phrasings():
    """Formulations debutant ajoutees le 2026-06-11 -- doivent matcher."""
    assert _has_keyword("fais clignoter une sortie sur D5", _LED_KEYWORDS)
    assert _has_keyword("I want it to blink", _LED_KEYWORDS)
    assert _has_keyword("hacer parpadear el led", _LED_KEYWORDS)
    assert _has_keyword("voglio che lampeggia", _LED_KEYWORDS)
    assert _has_keyword("je veux que ca fasse bip", _BUZZER_KEYWORDS)
    assert _has_keyword("mets un thermometre sur A0", _TEMP_SENSOR_KEYWORDS)
    assert _has_keyword("a thermometer on A0", _TEMP_SENSOR_KEYWORDS)
    assert _has_keyword("controle un 28BYJ-48", _STEPPER_KEYWORDS)
    # Garde-fou anti-faux-positif : "clignote" ne doit pas faire matcher
    # un prompt purement moteur comme une LED.
    assert not _has_keyword("controle un moteur", _LED_KEYWORDS)


# ─── Couche 2 : garde de coherence lexiques <-> candidats ────────────────

def test_disambiguation_candidates_have_keywords():
    """Every type listed as a disambiguation candidate MUST point to a
    non-empty keyword set. Prevents adding an ambiguous component (candidate)
    while forgetting its keywords -> silent hole. (cf. CLAUDE.md checklist
    'Definition of done for a new component'.)"""
    for label, candidates in (
        ("_LED_RECLASSIF_CANDIDATES", _LED_RECLASSIF_CANDIDATES),
        ("_POT_SUBTYPE_CANDIDATES", _POT_SUBTYPE_CANDIDATES),
        ("_BTN_SUBTYPE_CANDIDATES", _BTN_SUBTYPE_CANDIDATES),
    ):
        for type_id, kws in candidates.items():
            assert kws, f"{label}['{type_id}'] : lexique vide/manquant"
            assert len(tuple(kws)) >= 1, (
                f"{label}['{type_id}'] : aucun mot-clé"
            )


# ─── Labels and prefixes for new type tokens ─────────────────────────────

def test_new_token_labels_multilang():
    assert _label("ldr", "fr") == "photorésistance (LDR)"
    assert _label("ldr", "en") == "LDR (photoresistor)"
    assert _label("thermistor", "es") == "termistor"
    assert _label("microphone", "fr") == "capteur de son"
    assert _label("relay", "it") == "relè"
    assert _label("pir", "en") == "PIR motion sensor"


def test_new_token_ref_prefixes():
    assert _ref_prefix_for("relay") == "K"
    assert _ref_prefix_for("ldr") == "LDR"
    assert _ref_prefix_for("thermistor") == "TH"
    assert _ref_prefix_for("microphone") == "MIC"
    assert _ref_prefix_for("pir") == "PIR"


# ─── 5. Source code as priority deduction source + relay ──────────────────

CODE_DIGITAL_OUT = """
#define RELAY_PIN 7
void setup() { pinMode(RELAY_PIN, OUTPUT); }
void loop() { digitalWrite(RELAY_PIN, HIGH); delay(1000); }
"""


def _find_by_type(nl, t):
    return next((c for c in nl.components if c.type == t), None)


def test_e2e_relay_from_code_identifier():
    """Le nom de constante 'RELAY_PIN' suffit a muter LED -> relay, SANS prompt."""
    nl = analyze_netlist(CODE_DIGITAL_OUT, "uno_r3")
    relay = _find_by_type(nl, "relay")
    assert relay is not None, "expected relay mutation from code identifier"
    nets = {p.name: p.net for p in relay.pins}
    assert nets.get("IN") == "D7", f"expected IN=D7, got {nets}"
    assert nets.get("VCC") == "5V" and nets.get("GND") == "GND"


def test_e2e_relay_from_prompt():
    """Mutation LED -> relay via le prompt (pin nommee, identifiant neutre)."""
    code = (
        "void setup(){ pinMode(8, OUTPUT); }\n"
        "void loop(){ digitalWrite(8, HIGH); }\n"
    )
    nl = analyze_netlist(code, "uno_r3", prompt="active le relais sur D8")
    relay = _find_by_type(nl, "relay")
    assert relay is not None, "expected relay mutation from prompt"
    nets = {p.name: p.net for p in relay.pins}
    assert nets.get("IN") == "D8", f"expected IN=D8, got {nets}"
    assert nets.get("VCC") == "5V" and nets.get("GND") == "GND"


def test_e2e_code_identifier_beats_silence_buzzer():
    """Identifiant 'buzzerPin' -> buzzer sans prompt (code prioritaire)."""
    code = (
        "#define buzzerPin 9\n"
        "void setup(){ pinMode(buzzerPin, OUTPUT); }\n"
        "void loop(){ digitalWrite(buzzerPin, HIGH); }\n"
    )
    nl = analyze_netlist(code, "uno_r3")
    assert _find_by_type(nl, "buzzer") is not None


def test_e2e_generic_output_stays_led():
    """Identifiant neutre + pas de prompt -> reste LED (defaut inchange)."""
    code = (
        "#define outPin 5\n"
        "void setup(){ pinMode(outPin, OUTPUT); }\n"
        "void loop(){ digitalWrite(outPin, HIGH); }\n"
    )
    nl = analyze_netlist(code, "uno_r3")
    assert _find_by_type(nl, "led") is not None
    assert _find_by_type(nl, "relay") is None


# ─── 6. Entree digitale : button -> pir (Task 5) ─────────────────────────

def test_pir_keywords_multilang():
    assert _has_keyword("detecteur de mouvement sur D2", _PIR_KEYWORDS)
    assert _has_keyword("PIR motion sensor", _PIR_KEYWORDS)
    assert _has_keyword("sensor de movimiento", _PIR_KEYWORDS)
    assert _has_keyword("sensore di movimento", _PIR_KEYWORDS)
    assert not _has_keyword("appuie sur le bouton", _PIR_KEYWORDS)


def test_e2e_pir_from_code_identifier():
    code = (
        "#define pirPin 2\n"
        "void setup(){ pinMode(pirPin, INPUT); }\n"
        "void loop(){ int m = digitalRead(pirPin); }\n"
    )
    nl = analyze_netlist(code, "uno_r3")
    pir = _find_by_type(nl, "pir")
    assert pir is not None, "expected button -> pir from code identifier"
    nets = {p.name: p.net for p in pir.pins}
    assert nets.get("OUT") == "D2"
    assert nets.get("VCC") == "5V" and nets.get("GND") == "GND"


def test_e2e_pir_from_prompt():
    code = (
        "void setup(){ pinMode(3, INPUT); }\n"
        "void loop(){ digitalRead(3); }\n"
    )
    nl = analyze_netlist(code, "uno_r3",
                          prompt="detecteur de mouvement sur D3")
    pir = _find_by_type(nl, "pir")
    assert pir is not None
    nets = {p.name: p.net for p in pir.pins}
    assert nets.get("OUT") == "D3", f"expected OUT=D3, got {nets}"
    assert nets.get("VCC") == "5V" and nets.get("GND") == "GND"


def test_e2e_generic_input_stays_button():
    code = (
        "#define inPin 4\n"
        "void setup(){ pinMode(inPin, INPUT_PULLUP); }\n"
        "void loop(){ digitalRead(inPin); }\n"
    )
    nl = analyze_netlist(code, "uno_r3")
    assert _find_by_type(nl, "button") is not None
    assert _find_by_type(nl, "pir") is None


def test_pir_presence_multiword_only():
    # forme multi-mots reconnue
    assert _has_keyword("détecteur de présence sur D2", _PIR_KEYWORDS)
    assert _has_keyword("presence sensor on D2", _PIR_KEYWORDS)
    assert _has_keyword("sensor de presencia en D2", _PIR_KEYWORDS)
    # bare "presence"/"présence" must NO LONGER match (false positive avoided)
    assert not _has_keyword("verifie la presence de tension sur D3", _PIR_KEYWORDS)
    assert not _has_keyword("en présence de l'utilisateur, allume la LED", _PIR_KEYWORDS)


# ─── 7. Commentaires bloc /* ... */ en ligne (Task 6) ───────────────────

def test_code_excerpt_block_comment():
    """Un commentaire bloc /* ... */ en ligne est lu comme source."""
    code = "void loop(){ int t = analogRead(A2); /* thermistance */ }\n"
    p2n = _pin_to_identifiers(code)
    exc = _code_excerpt_for_pin(code, "A2", p2n)
    assert "thermistance" in exc.lower(), f"got {exc!r}"


def test_e2e_thermistor_from_block_comment():
    """End-to-end : /* thermistance */ sur une lecture analogique -> mutation
    pot -> thermistor (sans prompt)."""
    code = "void loop(){ int t = analogRead(A2); /* thermistance */ }\n"
    nl = analyze_netlist(code, "uno_r3")
    assert _find_by_type(nl, "thermistor") is not None, "expected thermistor from block comment"
    assert _find_by_type(nl, "potentiometer") is None


def test_hx711_detected_from_its_official_example():
    """TODO #47. Cas (a) de la checklist : signature UNIQUE (`HX711.h`), donc
    aucun lexique — mais encore faut-il lire la forme que le modele ECRIT.

    Trouve par le balayage du corpus du 2026-08-10 : le HX711 avait deja son
    entree catalogue (VCC/GND/DT/SCK), son libelle x4, son nom court et son
    identite au registre. TOUT etait declare. Seule la lecture du code
    manquait, donc il ne pouvait JAMAIS apparaitre sur un schema.

    Le piege est le meme que les quatre de la QA d'aout : l'objet se declare
    SANS broches (`HX711 scale;`), elles arrivent par `begin(DT, SCK)`. Un
    detecteur ecrit sur le constructeur n'aurait rien vu."""
    code = ("#include <HX711.h>\n"
            "HX711 scale;\n"
            "void setup(){ scale.begin(3, 2); }\n"
            "void loop(){ long raw = scale.read(); delay(200); }\n")
    nl = analyze_netlist(code, "uno_r3")
    c = _find_by_type(nl, "hx711")
    assert c is not None, [x.type for x in nl.components]
    nets = {p.name: p.net for p in c.pins}
    assert nets == {"VCC": "5V", "GND": "GND", "DT": "D3", "SCK": "D2"}, nets
    # Lu dans le code, donc affirme comme tel — pas un filet.
    assert c.attributes.get("signature_detected") is True
    for marqueur in ("unrecognized", "presumed_wiring", "presumed_analog"):
        assert marqueur not in c.attributes, marqueur


def test_hx711_pins_come_from_begin_not_from_a_guess():
    """Broches differentes -> nets differents. Sans ca, le test precedent
    passerait sur un detecteur qui code les broches en dur."""
    code = ("#include <HX711.h>\n"
            "HX711 balance;\n"
            "void setup(){ balance.begin(A1, 7); }\n"
            "void loop(){}\n")
    c = _find_by_type(analyze_netlist(code, "uno_r3"), "hx711")
    assert c is not None
    nets = {p.name: p.net for p in c.pins}
    assert nets["DT"] == "A1" and nets["SCK"] == "D7", nets


def test_ina226_is_read_not_presumed():
    """TODO #47. L'exemple officiel tombait sur le FILET I2C : cablage
    « presume », alors que `INA226_WE.h` est une signature parfaitement
    identifiable. Un filet qui se declenche la ou une signature existe, c'est
    de l'honnetete payee trop cher — on annoncait une supposition sur un cas
    qu'on savait lire."""
    code = ("#include <Wire.h>\n#include <INA226_WE.h>\n"
            "INA226_WE ina226 = INA226_WE(0x40);\n"
            "void setup(){ Wire.begin(); ina226.init(); }\nvoid loop(){}\n")
    nl = analyze_netlist(code, "uno_r3")
    c = _find_by_type(nl, "ina226")
    assert c is not None, [x.type for x in nl.components]
    assert "presumed_wiring" not in c.attributes
    assert "presumed_i2c_wiring" not in [w.code for w in nl.warnings]
    # Et PLUS de boite fantome a cote : sans reclamer l'en-tete, le placeholder
    # universel se declenchait par-dessus et l'utilisateur voyait DEUX boites.
    assert _find_by_type(nl, "ina226_we") is None


def test_sd_card_is_detected_and_emits_the_curated_id():
    """TODO #43 + #47. Le brochage est deterministe : CS vient de
    `SD.begin(cs)`, MOSI/MISO/SCK sont cables dans la puce. L'identifiant est
    `sd_card` — celui que le registre et `_TYPE_LABEL` portaient deja ; #43
    laissait la question ouverte « jusqu'a ce qu'on ecrive la detection »,
    c'est fait."""
    code = ("#include <SPI.h>\n#include <SD.h>\n"
            "const int chipSelect = 4;\n"
            "void setup(){ SD.begin(chipSelect); }\nvoid loop(){}\n")
    nl = analyze_netlist(code, "uno_r3")
    c = _find_by_type(nl, "sd_card")
    assert c is not None, [x.type for x in nl.components]
    nets = {p.name: p.net for p in c.pins}
    assert nets["CS"] == "D4", nets
    assert nets["MOSI"] == "D11" and nets["MISO"] == "D12" and nets["SCK"] == "D13"
    assert _find_by_type(nl, "sd") is None, "la boite fantome du placeholder"


def test_onebutton_is_a_plain_push_button():
    """TODO #47. C'est un bouton-poussoir ordinaire, deja entierement
    catalogue — seul le fait d'etre declare par une bibliotheque le rendait
    invisible. `activeLow=true` = bouton entre la broche et GND avec
    INPUT_PULLUP, donc le meme cablage qu'un `pinMode(.., INPUT_PULLUP)`."""
    code = ("#include <OneButton.h>\n"
            "#define PIN_INPUT 2\n"
            "OneButton button(PIN_INPUT, true);\n"
            "void setup(){}\nvoid loop(){ button.tick(); }\n")
    nl = analyze_netlist(code, "uno_r3")
    c = _find_by_type(nl, "button")
    assert c is not None, [x.type for x in nl.components]
    assert {p.net for p in c.pins} == {"D2", "GND"}, [(p.name, p.net) for p in c.pins]
    assert _find_by_type(nl, "onebutton") is None


def test_a_grouped_motor_gets_its_suggestion():
    """TODO #47. Le balayage a d'abord signale `dc_motor` et `l293d` comme des
    lacunes : FAUX, et c'est la troisieme fois de la journee que je me trompe
    de couche.

    `markers` ne MUTE PAS un groupe PWM+direction en `dc_motor`. Il laisse le
    type a `led` et attache `_prompt_suggested_type`, que `studio_view`
    applique ensuite SANS modale. Ne regarder que `c.type` fait passer pour un
    trou un pipeline qui fonctionne exactement comme prevu.

    Ce test verrouille le vrai contrat : groupement + prompt nommant le driver
    -> suggestion posee, avec le bon driver."""
    code = ("const int ENA = 6;\nconst int IN1 = 7;\nconst int IN2 = 8;\n"
            "void setup(){ pinMode(ENA,OUTPUT); pinMode(IN1,OUTPUT); "
            "pinMode(IN2,OUTPUT); }\n"
            "void loop(){ digitalWrite(IN1,HIGH); digitalWrite(IN2,LOW); "
            "analogWrite(ENA,200); }\n")
    nl = analyze_netlist(code, "uno_r3",
                         prompt="Fais tourner un moteur DC avec un L298N")
    groupes = [c for c in nl.components
               if c.attributes.get("_grouped_pwm_pin")]
    assert groupes, [c.type for c in nl.components]
    c = groupes[0]
    assert c.attributes["_grouped_pwm_pin"] == "D6"
    assert c.attributes["_grouped_dir_pins"] == ["D7", "D8"]
    assert c.attributes.get("_prompt_suggested_type") == "dc_motor"
    assert c.attributes.get("_prompt_suggested_driver") == "l298n"


def test_without_a_driver_named_the_motor_stays_ambiguous():
    """Le pendant, et la raison pour laquelle `dc_motor` reste dans la dette :
    le code SEUL ne dit pas qu'il y a un moteur au bout. L'ambiguite est
    VOULUE — c'est la modale ou le prompt qui tranche, pas une devinette."""
    code = ("const int ENA = 6;\nconst int IN1 = 7;\nconst int IN2 = 8;\n"
            "void setup(){ pinMode(ENA,OUTPUT); }\n"
            "void loop(){ digitalWrite(IN1,HIGH); analogWrite(ENA,200); }\n")
    nl = analyze_netlist(code, "uno_r3")
    for c in nl.components:
        assert c.attributes.get("_prompt_suggested_type") != "dc_motor"


def test_two_unwired_pins_of_one_component_are_not_a_conflict():
    """Faux positif trouve pendant #47. Deux broches NON CABLEES du meme
    composant partagent le net vide et se denoncaient l'une l'autre :
    « Pin  utilisee par plusieurs composants : U1, U1. » — nom de broche vide,
    meme composant deux fois, en severite ERREUR. Un INA219 le declenchait par
    ses seuls terminaux de mesure."""
    code = ("#include <Adafruit_INA219.h>\n"
            "Adafruit_INA219 ina219;\n"
            "void setup(){ ina219.begin(); }\nvoid loop(){}\n")
    nl = analyze_netlist(code, "uno_r3")
    assert "pin_double_use" not in [w.code for w in nl.warnings], \
        [(w.code, w.message) for w in nl.warnings]


def test_but_a_real_double_use_still_speaks():
    """Le garde du garde : en retirant le faux positif on ne doit pas avoir
    rendu le detecteur muet. Deux composants DIFFERENTS sur la meme broche."""
    from ui.wiring.inference import detect_conflicts
    from ui.wiring.netlist import Component, Netlist, Pin
    nl = Netlist(board_id="uno_r3")
    nl.add_component(Component(ref="U1", type="led", pins=[Pin("A", "D5")]))
    nl.add_component(Component(ref="U2", type="button", pins=[Pin("1", "D5")]))
    detect_conflicts(nl)
    assert "pin_double_use" in [w.code for w in nl.warnings]


# ─── Detecteur MQ : le numero ECRIT dans le code decide (2026-08-27) ──────
# Le detecteur matchait deja `#define MQ<n>_PIN A<x>` et CAPTURAIT le numero,
# puis le jetait pour poser « mq135 » en dur. Mesure du jour, avant correctif :
# `#define MQ2_PIN A0` dessinait un MQ-135 -- et le MQ-2 est le capteur de gaz
# le plus courant des kits debutants, present au registre depuis toujours.
# Ce n'est donc PAS une signature manquante, c'est une signature lue puis
# perdue.

def _mq_code(piece: str, pin: str = "A0") -> str:
    return (f"#define {piece}_PIN {pin}\n"
            f"void setup(){{}}\n"
            f"void loop(){{ int v = analogRead({piece}_PIN); }}\n")


def test_mq_le_numero_ecrit_dans_le_code_decide_du_type():
    """La reference que le code ECRIT est celle qu'on dessine."""
    for piece, attendu in (("MQ2", "mq2"), ("MQ131", "mq131"),
                           ("MQ137", "mq137"), ("MQ135", "mq135")):
        nl = analyze_netlist(_mq_code(piece), "uno_r3")
        types = [c.type for c in nl.components]
        assert attendu in types, f"{piece} -> {types}, attendu {attendu}"


def test_mq_un_numero_INCONNU_du_registre_retombe_sur_mq135():
    """Le repli reste, et il est deliberement etroit.

    Un `#define MQ9999_PIN` ne doit PAS fabriquer un type « mq9999 » : ce
    serait un type de cablage sans identite au registre, ce que la garde 7 de
    `test_component_registry` interdit -- et un nom court, un libelle x4 et
    une fiche manqueraient tous. On reconnait ce qu'on connait ; pour le
    reste, le MQ-135 generique dit au moins << capteur de gaz >>.
    """
    nl = analyze_netlist(_mq_code("MQ9999"), "uno_r3")
    types = [c.type for c in nl.components]
    assert "mq135" in types, types
    assert not any(t.startswith("mq9") for t in types), types


def test_mq_un_nom_generique_reste_sur_mq135():
    """`const int gas_sensor = A1` ne nomme aucune reference : le defaut
    tient, et c'est bien le comportement d'avant qu'on preserve ici."""
    code = ("const int gas_sensor = A1;\nvoid setup(){}\n"
            "void loop(){ int v = analogRead(gas_sensor); }\n")
    nl = analyze_netlist(code, "uno_r3")
    assert "mq135" in [c.type for c in nl.components]


def test_mq_le_brochage_ne_change_pas_avec_la_reference():
    """Toutes ces pieces ont le meme brochage a trois fils : VCC, AOUT, GND.
    Changer le TYPE ne doit rien changer au cablage -- sinon le correctif
    deplacerait un fil en croyant corriger un nom."""
    nl = analyze_netlist(_mq_code("MQ137", "A3"), "uno_r3")
    mq = _find_by_type(nl, "mq137")
    assert mq is not None, [c.type for c in nl.components]
    nets = {p.name: p.net for p in mq.pins}
    assert nets == {"VCC": "5V", "AOUT": "A3", "GND": "GND"}, nets


def test_mq_tout_type_emis_a_une_identite_au_registre():
    """Garde de derive, dans l'esprit de la garde 7 : la table des references
    reconnues ne doit contenir que des composants qui EXISTENT."""
    from ui.component_registry import registry
    from ui.wiring.markers import _MQ_KNOWN_PARTS
    ids = {c.id for c in registry()}
    orphelins = sorted(_MQ_KNOWN_PARTS - ids)
    assert not orphelins, f"references MQ sans identite au registre : {orphelins}"


# ─── RCWL-0516 : le radar Doppler, voisin dangereux du PIR (2026-08-27) ───
# Une entree digitale nue sort en `button` par defaut ; seul le PROMPT peut
# dire ce qui est branche (`digitalRead(2)` ne dit rien). Cas (b) de la
# checklist, sur le modele exact de `pir`.

def _rcwl_code(pin: int = 2) -> str:
    return (f"const int radarPin = {pin};\n"
            f"void setup(){{ pinMode(radarPin, INPUT); }}\n"
            f"void loop(){{ int m = digitalRead(radarPin); }}\n")


def test_rcwl_keywords_multilang():
    from ui.wiring.markers import _RCWL_KEYWORDS as K
    assert _has_keyword("un RCWL-0516 sur la broche 2", K)
    assert _has_keyword("capteur radar doppler", K)              # FR
    assert _has_keyword("detecteur a micro-ondes", K)            # FR
    assert _has_keyword("microwave radar sensor", K)             # EN
    assert _has_keyword("sensor de radar de microondas", K)      # ES
    assert _has_keyword("sensore radar a microonde", K)          # IT


def test_rcwl_le_prompt_le_distingue_du_bouton_dans_les_quatre_langues():
    for phrase in ("un RCWL-0516 sur la broche 2",
                   "capteur radar doppler sur la broche 2",
                   "microwave radar sensor on pin 2",
                   "sensor de radar de microondas en el pin 2",
                   "sensore radar a microonde sul pin 2"):
        nl = analyze_netlist(_rcwl_code(), "uno_r3", prompt=phrase)
        c = _find_by_type(nl, "rcwl0516")
        assert c is not None, f"{phrase!r} -> {[x.type for x in nl.components]}"
        nets = {p.name: p.net for p in c.pins}
        assert nets == {"VIN": "5V", "OUT": "D2", "GND": "GND"}, nets


def test_rcwl_sans_mention_la_broche_reste_un_bouton():
    """Sans rien dans le prompt, on ne devine pas : le defaut tient."""
    nl = analyze_netlist(_rcwl_code(), "uno_r3", prompt="")
    assert _find_by_type(nl, "rcwl0516") is None
    assert _find_by_type(nl, "button") is not None


def test_rcwl_un_prompt_qui_ne_NOMME_PAS_la_broche_ne_tranche_pas():
    """Comportement VOULU, et il surprend : mentionner le composant ne
    suffit pas, il faut nommer sa BROCHE.

    `_choose_type_from_text` ignore explicitement le prompt global
    (`del prompt`) et ne lit que l'extrait scope a la broche, via
    `find_pin_excerpt`. C'est ce qui empeche un mot lache dans un prompt de
    contaminer TOUS les composants ambigus d'un sketch qui en a plusieurs.

    Fige ici parce que le piege s'est referme en ecrivant ces tests : le
    premier jet disait << detecte les mouvements avec un RCWL-0516 >>, sans
    broche, et concluait a tort que la detection ne marchait pas.
    """
    nl = analyze_netlist(_rcwl_code(), "uno_r3",
                         prompt="detecte les mouvements avec un RCWL-0516")
    assert _find_by_type(nl, "rcwl0516") is None
    assert _find_by_type(nl, "button") is not None


def test_rcwl_n_est_PAS_declenche_par_le_vocabulaire_du_PIR():
    """LA garde de ce lot, et la raison pour laquelle le lexique est etroit.

    Le RCWL-0516 et le PIR sont tous deux des capteurs de MOUVEMENT. Si le
    lexique du radar avait repris << capteur de mouvement >>, il aurait
    dispute au PIR le vocabulaire le plus courant du corpus debutant -- et
    `_choose_type_from_text` aurait rendu None sur le double-hit, donc perdu
    les DEUX.

    ⛔ En francais, << radar >> TOUT SEUL est un piege supplementaire : un
    << radar de recul >> est un capteur a ULTRASONS. D'ou des expressions
    multi-mots (<< radar doppler >>, << micro-ondes >>), jamais le mot nu.

    ⚠️ CHAQUE phrase NOMME la broche. Sans ca le test passerait a vide : le
    scoping par broche (test precedent) suffirait a le rendre vert, quel que
    soit le lexique -- et il ne prouverait plus rien du tout.
    """
    for phrase in ("un capteur de mouvement sur la broche 2",
                   "un detecteur de presence sur la broche 2",
                   "a motion sensor on pin 2",
                   "un sensor de movimiento en el pin 2",
                   "un radar de recul sur la broche 2"):
        nl = analyze_netlist(_rcwl_code(), "uno_r3", prompt=phrase)
        assert _find_by_type(nl, "rcwl0516") is None, (
            f"{phrase!r} a declenche le radar : collision avec le PIR "
            f"ou piege du mot << radar >> seul")


# --- JSN-SR04T : un PROTOCOLE partage, precise par la reference --------
_ULTRASON = ("const int trigPin = 9;\n"
             "const int echoPin = 10;\n"
             "void setup(){ pinMode(trigPin, OUTPUT); pinMode(echoPin, INPUT); }\n"
             "void loop(){\n"
             "  digitalWrite(trigPin, LOW); delayMicroseconds(2);\n"
             "  digitalWrite(trigPin, HIGH); delayMicroseconds(10);\n"
             "  digitalWrite(trigPin, LOW);\n"
             "  long d = pulseIn(echoPin, HIGH);\n}\n")


def test_ultrason_le_defaut_reste_le_hcsr04():
    """Sans reference, le HC-SR04 est le defaut legitime -- c'est celui
    des kits. On ne devine pas l'etanche."""
    for p in ("mesure la distance", "un capteur a ultrasons etanche"):
        nl = analyze_netlist(_ULTRASON, "uno_r3", prompt=p)
        assert _find_by_type(nl, "hcsr04") is not None, \
            (p, [c.type for c in nl.components])


def test_ultrason_la_reference_precise_la_piece():
    """Le detecteur reconnait la sequence d'impulsion de 10 us, donc un
    PROTOCOLE -- partage par le HC-SR04, le JSN-SR04T, l'AJ-SR04M et le
    HC-SR04P. Le code ne dit PAS laquelle c'est, et le prompt a donc le
    droit de le preciser sans rien contredire.

    ⚠️ A ne pas confondre avec le cas MH-Z, ou `MHZ19.h` nomme une PUCE :
    la, le code identifie la piece et le prompt ne doit pas la contredire.
    """
    nl = analyze_netlist(_ULTRASON, "uno_r3",
                         prompt="mesure la distance avec un JSN-SR04T")
    c = _find_by_type(nl, "jsn_sr04t")
    assert c is not None, [x.type for x in nl.components]
    # Le cablage est IDENTIQUE : on precise le nom, on ne recable pas.
    assert {p.name: p.net for p in c.pins} == {
        "VCC": "5V", "TRIG": "D9", "ECHO": "D10", "GND": "GND"}


def test_ultrason_le_sketch_MINIMAL_ne_declenche_rien_et_c_est_voulu():
    """Fige une lecon de la QA : un trig/echo SANS la sequence d'impulsion
    de 10 us n'est PAS un ultrason pour le detecteur.

    C'est une signature PRECISE, pas une lacune -- le premier sketch de
    test l'omettait, sortait en LED, et a fait croire a un defaut du
    detecteur pendant tout un echange.
    """
    minimal = ("const int trigPin=9, echoPin=10;\n"
               "void setup(){ pinMode(trigPin,OUTPUT); pinMode(echoPin,INPUT); }\n"
               "void loop(){ digitalWrite(trigPin,HIGH); long d=pulseIn(echoPin,HIGH); }\n")
    nl = analyze_netlist(minimal, "uno_r3", prompt="un JSN-SR04T")
    assert _find_by_type(nl, "hcsr04") is None
    assert _find_by_type(nl, "jsn_sr04t") is None


# ─── MH-Z14A / MH-Z1311A : nommer un module serie generique (2026-08-27) ──
# Trois formes de generique coexistent, MESUREES : un SoftwareSerial nu sort en
# `uart_module`, et un include inconnu donne un type nomme d'apres la
# BIBLIOTHEQUE (`MHZCO2.h` -> `mhzco2`), qui n'a aucune identite au registre.

_SS_NU = ("#include <SoftwareSerial.h>\nSoftwareSerial co2(10,11);\n"
          "void setup(){ co2.begin(9600); }\nvoid loop(){}\n")
_SS_LIB = ("#include <SoftwareSerial.h>\n#include <MHZCO2.h>\n"
           "SoftwareSerial co2(10,11);\n"
           "void setup(){ co2.begin(9600); }\nvoid loop(){}\n")
_SS_Z19 = ("#include <SoftwareSerial.h>\n#include <MHZ19.h>\n"
           "SoftwareSerial co2(10,11);\n"
           "void setup(){ co2.begin(9600); }\nvoid loop(){}\n")


def test_mhz_un_module_serie_nu_prend_la_reference_du_prompt():
    nl = analyze_netlist(_SS_NU, "uno_r3", prompt="un MH-Z14A sur les broches 10 et 11")
    c = _find_by_type(nl, "mhz14a")
    assert c is not None, [x.type for x in nl.components]
    # Le cablage serie NE bouge pas : on renomme, on ne recable pas.
    assert {p.name: p.net for p in c.pins} == {
        "VCC": "5V", "GND": "GND", "TX": "D10", "RX": "D11"}


def test_mhz_un_type_nomme_d_apres_la_LIB_est_aussi_une_cible():
    """`MHZCO2.h` sort en `mhzco2`, un type sans identite au registre. Viser
    le seul `uart_module` n'aurait couvert que la moitie des sketches."""
    nl = analyze_netlist(_SS_LIB, "uno_r3", prompt="un MH-Z1311A")
    assert _find_by_type(nl, "mhz1311a") is not None, \
        [x.type for x in nl.components]


def test_mhz_le_CODE_prevaut_sur_le_prompt():
    """`MHZ19.h` identifie la piece ; le prompt ne remplace pas une signature
    lue par une mention. Regle du projet, pas un detail de ce lot."""
    nl = analyze_netlist(_SS_Z19, "uno_r3", prompt="un MH-Z14A")
    assert _find_by_type(nl, "mhz19") is not None
    assert _find_by_type(nl, "mhz14a") is None


def test_mhz_le_vocabulaire_generique_du_CO2_ne_suffit_PAS():
    """Les lexiques sont reduits a la REFERENCE : << capteur de CO2 >>
    appartient au `mhz19`, qui est detecte par sa signature. Sans cette
    retenue, ce lot lui aurait dispute son vocabulaire le plus courant."""
    nl = analyze_netlist(_SS_NU, "uno_r3",
                         prompt="un capteur de CO2 sur les broches 10 et 11")
    assert _find_by_type(nl, "uart_module") is not None
    assert _find_by_type(nl, "mhz14a") is None


def test_mhz_deux_modules_series_pour_une_reference_ne_tranchent_pas():
    """On ne sait pas LEQUEL est nomme : on se tait plutot que de tirer au
    sort. Le filet `uart_module` dit deja << peripherique serie non
    identifie >>, ce qui reste vrai."""
    code = ("#include <SoftwareSerial.h>\nSoftwareSerial a(10,11);\n"
            "SoftwareSerial b(6,7);\n"
            "void setup(){ a.begin(9600); b.begin(9600); }\nvoid loop(){}\n")
    nl = analyze_netlist(code, "uno_r3", prompt="un MH-Z14A quelque part")
    assert [c.type for c in nl.components] == ["uart_module", "uart_module"]


def test_mhz_nomme_par_sa_reference_n_avoue_rien():
    """Coherence avec le mecanisme d'aveu : ces lexiques n'ont QUE des
    references, donc il n'y a jamais rien a avouer -- l'utilisateur a nomme
    sa piece lui-meme."""
    nl = analyze_netlist(_SS_NU, "uno_r3", prompt="un MH-Z14A sur les broches 10 et 11")
    assert not [w for w in nl.warnings
                if w.code == "presumed_from_description"]


def _aveux(nl):
    return [w for w in nl.warnings if w.code == "presumed_from_description"]


def test_rcwl_nomme_par_sa_reference_ne_declenche_aucun_aveu():
    """L'utilisateur a ecrit << RCWL-0516 >> : rien n'a ete devine."""
    nl = analyze_netlist(_rcwl_code(), "uno_r3",
                         prompt="un RCWL-0516 sur la broche 2")
    assert _find_by_type(nl, "rcwl0516") is not None
    assert not _aveux(nl), [w.message for w in _aveux(nl)]


def test_rcwl_deduit_d_une_DESCRIPTION_l_avoue():
    """Le lexique accepte << radar doppler >>, ce qui est commode -- mais
    l'app a alors choisi un NUMERO DE PIECE que personne n'a ecrit. Elle le
    dit, au lieu de laisser croire que la reference a ete lue quelque part.
    """
    nl = analyze_netlist(_rcwl_code(), "uno_r3",
                         prompt="capteur radar doppler sur la broche 2")
    c = _find_by_type(nl, "rcwl0516")
    assert c is not None
    assert c.attributes.get("presumed_from_description") == "true"
    aveux = _aveux(nl)
    assert len(aveux) == 1, [w.message for w in nl.warnings]
    # `markers` pose l'ID du type ; c'est `instructions` qui le rend lisible,
    # et dans les QUATRE langues. Sans ca l'aveu disait << rcwl0516 >> a
    # l'utilisateur -- un slug interne, pour parler du composant dont on lui
    # demande justement de verifier l'identite.
    assert aveux[0].params["name"] == "rcwl0516"
    from ui.wiring.instructions import _render_warning_message
    for lang in ("fr", "en", "es", "it"):
        rendu = _render_warning_message(aveux[0], lang)
        assert "RCWL-0516" in rendu, (lang, rendu)
        assert "rcwl0516" not in rendu, (lang, rendu)


def test_un_type_SANS_reference_n_avoue_jamais_rien():
    """LA borne de ce mecanisme, et la mesure qui l'a fixee.

    9 des 14 types candidats n'ont AUCUNE reference : led, buzzer, servo,
    dc_motor, relay, potentiometer, ldr, microphone, button, pir. Une LED n'a
    pas de numero a donner ; la deduire de << allume une LED >> est le mieux
    qu'on puisse faire. Avertir la-dessus mettrait << pas sur >> sur presque
    chaque schema de debutant -- du bruit constant, qui finirait par ne plus
    rien vouloir dire.
    """
    nl = analyze_netlist(_rcwl_code(), "uno_r3",
                         prompt="un detecteur de mouvement PIR sur la broche 2")
    pir = _find_by_type(nl, "pir")
    assert pir is not None
    assert "presumed_from_description" not in pir.attributes
    assert not _aveux(nl)


def test_l_aveu_disparait_quand_on_declare_le_composant():
    """L'aveu est un filet d'honnetete : il rejoint SAFETY_NET_ATTRS et
    SAFETY_NET_WARNING_CODES, donc decrire soi-meme le composant l'efface.
    Sans ca, le schema contredirait la correction a l'instant ou elle est
    faite -- le defaut exact de la QA L4 du 2026-08-10."""
    from ui.wiring.netlist import SAFETY_NET_ATTRS, SAFETY_NET_WARNING_CODES
    assert "presumed_from_description" in SAFETY_NET_ATTRS
    assert "presumed_from_description" in SAFETY_NET_WARNING_CODES


def test_rcwl_le_pir_garde_son_vocabulaire():
    """Non-regression dans l'autre sens : le PIR doit continuer de gagner sur
    ses propres mots, sinon ce lot lui aurait pris son terrain."""
    nl = analyze_netlist(_rcwl_code(), "uno_r3",
                         prompt="un detecteur de mouvement PIR sur la broche 2")
    assert _find_by_type(nl, "pir") is not None, [c.type for c in nl.components]


# ─── Registre des tests ──────────────────────────────────────────────────

TESTS = [
    test_rcwl_keywords_multilang,
    test_rcwl_le_prompt_le_distingue_du_bouton_dans_les_quatre_langues,
    test_rcwl_un_prompt_qui_ne_NOMME_PAS_la_broche_ne_tranche_pas,
    test_rcwl_sans_mention_la_broche_reste_un_bouton,
    test_rcwl_n_est_PAS_declenche_par_le_vocabulaire_du_PIR,
    test_rcwl_le_pir_garde_son_vocabulaire,
    # JSN-SR04T : un protocole partage, precise par la reference.
    test_ultrason_le_defaut_reste_le_hcsr04,
    test_ultrason_la_reference_precise_la_piece,
    test_ultrason_le_sketch_MINIMAL_ne_declenche_rien_et_c_est_voulu,
    # MH-Z14A / MH-Z1311A sur un module serie generique.
    test_mhz_un_module_serie_nu_prend_la_reference_du_prompt,
    test_mhz_un_type_nomme_d_apres_la_LIB_est_aussi_une_cible,
    test_mhz_le_CODE_prevaut_sur_le_prompt,
    test_mhz_le_vocabulaire_generique_du_CO2_ne_suffit_PAS,
    test_mhz_deux_modules_series_pour_une_reference_ne_tranchent_pas,
    test_mhz_nomme_par_sa_reference_n_avoue_rien,
    # L'aveu quand la piece a ete deduite d'une description.
    test_rcwl_nomme_par_sa_reference_ne_declenche_aucun_aveu,
    test_rcwl_deduit_d_une_DESCRIPTION_l_avoue,
    test_un_type_SANS_reference_n_avoue_jamais_rien,
    test_l_aveu_disparait_quand_on_declare_le_composant,
    test_mq_le_numero_ecrit_dans_le_code_decide_du_type,
    test_mq_un_numero_INCONNU_du_registre_retombe_sur_mq135,
    test_mq_un_nom_generique_reste_sur_mq135,
    test_mq_le_brochage_ne_change_pas_avec_la_reference,
    test_mq_tout_type_emis_a_une_identite_au_registre,
    test_hx711_detected_from_its_official_example,
    test_hx711_pins_come_from_begin_not_from_a_guess,
    test_ina226_is_read_not_presumed,
    test_sd_card_is_detected_and_emits_the_curated_id,
    test_onebutton_is_a_plain_push_button,
    test_a_grouped_motor_gets_its_suggestion,
    test_without_a_driver_named_the_motor_stays_ambiguous,
    test_two_unwired_pins_of_one_component_are_not_a_conflict,
    test_but_a_real_double_use_still_speaks,
    # Lexiques
    test_servo_keywords_multilang,
    test_pot_keywords_multilang,
    test_ldr_keywords_multilang,
    test_ky018_keywords,
    test_temp_sensor_keywords_multilang,
    test_sound_sensor_keywords_multilang,
    test_keypad_keywords_multilang,
    test_stepper_keywords_multilang,
    # _choose_type_from_text
    test_choose_context_wins_alone,
    test_choose_excerpt_wins_when_context_silent,
    test_choose_context_overrules_prompt,
    test_choose_context_ambigu_falls_back_to_prompt,
    test_choose_silent_returns_none,
    test_choose_excerpt_ambigu_returns_none,
    test_choose_pot_subtype_ldr,
    test_choose_pot_subtype_ky018,
    test_choose_pot_subtype_thermistor,
    test_choose_pot_subtype_microphone,
    # End-to-end
    test_e2e_led_to_servo_annotation,
    test_e2e_led_to_stepper_annotation,
    test_e2e_led_to_buzzer_mutation,
    test_e2e_led_to_motor_annotation,
    test_e2e_potentiometer_to_ldr,
    test_e2e_potentiometer_to_ky018,
    test_e2e_potentiometer_to_thermistor,
    test_e2e_potentiometer_to_microphone,
    test_e2e_potentiometer_explicit_no_subtype,
    test_e2e_material_wins_conflict,
    test_e2e_material_blocks_motor_when_only_leds,
    test_e2e_context_only_servo,
    test_e2e_context_only_ldr_via_bom,
    test_e2e_led_color_still_works,
    test_e2e_led_without_named_color_has_none,
    test_led_color_label_covers_every_detected_color,
    test_led_instruction_color_agnostic_then_localized,
    # Confirmation globale "LED" sans broche (bug 2026-06-02)
    test_e2e_global_led_no_pin_resolves,
    test_e2e_global_no_type_stays_ambiguous,
    test_e2e_global_led_plus_competing_stays_ambiguous,
    # Enrichment 2026-06-11 + consistency guard (layer 2)
    test_enriched_beginner_phrasings,
    test_disambiguation_candidates_have_keywords,
    # Helpers de deduction depuis le code
    test_split_identifier_camel_snake_digits,
    test_humanize_identifier_strips_pin_suffix,
    test_pin_to_identifiers_const_and_recv_var,
    test_code_excerpt_for_pin_identifier_and_comment,
    test_code_excerpt_no_sensor_keyword_when_anonymous_var,
    test_code_excerpt_digital_no_false_comment_match,
    # Labels + prefixes for new tokens (Task 2)
    test_new_token_labels_multilang,
    test_new_token_ref_prefixes,
    # Source code prioritaire + relay (Task 3)
    test_e2e_relay_from_code_identifier,
    test_e2e_relay_from_prompt,
    test_e2e_code_identifier_beats_silence_buzzer,
    test_e2e_generic_output_stays_led,
    # Mutation analogique reelle ldr/thermistor/microphone (Task 4)
    test_e2e_analog_subtype_from_code_identifier,
    test_e2e_generic_analog_stays_pot,
    # Mutation entree digitale button -> pir (Task 5)
    test_pir_keywords_multilang,
    test_e2e_pir_from_code_identifier,
    test_e2e_pir_from_prompt,
    test_e2e_generic_input_stays_button,
    test_pir_presence_multiword_only,
    # Commentaires bloc /* ... */ en ligne (Task 6)
    test_code_excerpt_block_comment,
    test_e2e_thermistor_from_block_comment,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            raise
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
