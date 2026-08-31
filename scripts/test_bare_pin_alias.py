"""QA L1 (2026-08-10) : `int pinCapteur = A0;` — sans `const` — laissait la
netlist VIDE.

Mesure d'origine. `_CONST_ALIAS_RE` exige le mot-cle `const`. Le modele, lui,
ecrit couramment du style Arduino sans const :

    int pinCapteur = A0;
    valeurLue = analogRead(pinCapteur);

L'alias n'etait pas resolu, `analogRead(pinCapteur)` restait illisible pour
`_normalize_pin_token`, aucun composant n'etait extrait. `static int`, `byte`
et `uint8_t` sans const tombaient pareil.

Elargir ne pouvait PAS etre inconditionnel : le meme sketch contenait
`int valeurLue = 0;`, une variable de DONNEE. L'aliaser vers D0 aurait reecrit
tout le code. Deux garde-fous, et ce sont eux que ces tests protegent :
  - la declaration doit commencer une ligne (ecarte `for (int i = 0;`) ;
  - la variable doit servir d'argument a une fonction de broche — le seul
    signal qui distingue un alias de broche d'une variable de donnee sans rien
    deviner sur son nom.

Run : python scripts/test_bare_pin_alias.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.markers import _extract_const_aliases, extract_netlist

# Le sketch REEL genere pour « Lis un capteur sur A0 et affiche la valeur ».
USER_SKETCH = """int pinCapteur = A0;
int valeurLue = 0;

void setup() {
\tSerial.begin(9600);
\tSerial.println("Systeme pret.");
}

void loop() {
\tvaleurLue = analogRead(pinCapteur);
\tSerial.print("Valeur du capteur : ");
\tSerial.println(valeurLue);
\tdelay(500);
}
"""


def test_the_real_sketch_yields_its_component():
    nl = extract_netlist(USER_SKETCH, "arduino_uno_r3",
                         prompt="Lis un capteur sur A0 et affiche la valeur")
    types = [c.type for c in nl.components]
    assert types == ["potentiometer"], types or "VIDE"


def test_the_data_variable_is_NOT_aliased():
    """Le garde-fou qui compte. `valeurLue = 0` est une variable de donnee ;
    l'aliaser vers D0 substituerait `valeurLue` partout dans le code."""
    aliases = _extract_const_aliases(USER_SKETCH)
    assert aliases == {"pinCapteur": "A0"}, aliases


def test_the_presumed_marker_survives():
    """L1 teste que la supposition est ANNONCEE : reparer la detection ne doit
    pas la faire passer pour une certitude."""
    nl = extract_netlist(USER_SKETCH, "arduino_uno_r3",
                         prompt="Lis un capteur sur A0 et affiche la valeur")
    comp = nl.components[0]
    assert comp.attributes.get("presumed_analog") == "true"
    assert "presumed_analog_component" in [w.code for w in nl.warnings]


def test_every_bare_declaration_type_resolves():
    for decl in ("int p = A0;", "static int p = A0;", "byte p = A0;",
                 "uint8_t p = A0;", "short p = A0;", "unsigned int p = A0;"):
        code = decl + "\nvoid setup(){}\nvoid loop(){int v = analogRead(p);}"
        assert _extract_const_aliases(code) == {"p": "A0"}, decl


def test_a_for_loop_header_is_never_aliased():
    """`for (int i = 2; ...)` : aliaser `i` reecrirait l'en-tete de boucle en
    `for (D2 = 2; D2 < 5; D2++)`. La contrainte de debut de ligne l'ecarte."""
    code = ("void setup(){ for (int i = 2; i < 5; i++) { pinMode(i, OUTPUT); } }"
            "\nvoid loop(){}")
    assert _extract_const_aliases(code) == {}


def test_an_unused_declaration_is_ignored():
    """Meme au debut d'une ligne, une variable qui ne sert jamais de broche
    n'est pas un alias."""
    code = ("int seuil = 500;\nvoid setup(){}\n"
            "void loop(){ if (analogRead(A0) > seuil) {} }")
    assert _extract_const_aliases(code) == {}


def test_const_declarations_still_win():
    """Le chemin `const` est inchange et prioritaire : lui resout AUSSI des
    non-broches (`#define DHT_TYPE DHT22`), que le filtre par usage
    rejetterait."""
    code = ("const int p = A1;\nint p2 = A0;\n"
            "#define DHT_TYPE DHT22\n"
            "void setup(){}\nvoid loop(){ analogRead(p); analogRead(p2); }")
    aliases = _extract_const_aliases(code)
    assert aliases["p"] == "A1"
    assert aliases["p2"] == "A0"
    assert aliases["DHT_TYPE"] == "DHT22"


# ── Declarateurs multiples sur une meme ligne (2026-08-29) ──────────────

_CODE_L298N_UNE_LIGNE = """
#include <L298N.h>
const int EN_A = 9, IN1_A = 7, IN2_A = 8;
L298N motorA(EN_A, IN1_A, IN2_A);
void setup() { motorA.setSpeed(200); }
void loop() { motorA.forward(); }
"""


def test_a_multi_declarator_line_aliases_them_all():
    """`const int EN = 9, IN1 = 7, IN2 = 8;` -- du C idiomatique.

    `_CONST_ALIAS_RE` ne capturait que le PREMIER declarateur, donc seul `EN`
    etait resolu. Trouve le 2026-08-29 en verifiant les sketches d'une
    procedure de QA, pas par un test.
    """
    from ui.wiring.markers import _extract_const_aliases
    alias = _extract_const_aliases("const int EN_A = 9, IN1_A = 7, IN2_A = 8;")
    assert alias.get("EN_A") == "D9", alias
    assert alias.get("IN1_A") == "D7", alias
    assert alias.get("IN2_A") == "D8", alias


def test_the_unresolved_pins_brought_back_the_phantom_box():
    """LA consequence, et la raison pour laquelle ce n'est pas un detail.

    Sans ses trois broches, la detection de signature du L298N abandonne,
    l'`#include` reste non reclame, et le filet << include inconnu >> pose une
    boite VIDE -- exactement le pin fantome que le chantier << certitude
    d'abord >> (#85) existe pour supprimer.
    """
    from ui.wiring import inference
    from ui.wiring.markers import extract_netlist
    netlist = extract_netlist(_CODE_L298N_UNE_LIGNE, "arduino_uno_r3",
                              prompt="", context="")
    fantomes = [c.ref for c in netlist.components
                if c.attributes.get("unrecognized")]
    assert fantomes == [], (
        "boite fantome : %r" % [(c.ref, c.type) for c in netlist.components])
    inference.apply_rules(netlist)
    moteurs = [c for c in netlist.components if c.type == "dc_motor"]
    assert len(moteurs) == 1, [(c.ref, c.type) for c in netlist.components]


def test_a_function_call_is_not_read_as_a_declarator_list():
    """Non-regression du filtre. `const int n = f(a, b);` a bien deux virgules
    mais aucun declarateur : les parentheses sont exclues de la liste, donc
    `a` et `b` ne deviennent pas des alias de broche."""
    from ui.wiring.markers import _extract_const_aliases
    alias = _extract_const_aliases("const int n = f(a, b);")
    assert "a" not in alias and "b" not in alias, alias


def test_a_data_constant_on_the_same_line_stays_out():
    """Le filtre des VALEURS n'a pas bouge : 500 n'est pas une broche, et le
    voisinage d'une vraie broche ne le rend pas eligible."""
    from ui.wiring.markers import _extract_const_aliases
    alias = _extract_const_aliases("const int SEUIL = 500, CAPTEUR = A0;")
    assert alias.get("CAPTEUR") == "A0", alias
    assert "SEUIL" not in alias, alias


# ── QA AC1 (2026-08-31) : pinMode(INPUT) au service d'un analogRead ─────
# Le sketch reel genere pour « un servo commande par un potentiometre » :
# gemma ecrit `#define POT_PIN 3` puis `pinMode(POT_PIN, INPUT)` (boilerplate
# inerte, analogRead ignore pinMode) puis `analogRead(POT_PIN)`. Deux defauts
# distincts, payes ensemble : la boucle pinMode de `_classify_pin_role`
# gagnait avant le test analogRead (le potentiometre devenait un BOUTON), et
# `analogRead(3)` lit le canal A3 sur Uno, jamais D3 -- le composant etait
# dessine sur une broche ou rien n'est branche.

_POT_BOILERPLATE = """#define POT_PIN 3
void setup() { pinMode(POT_PIN, INPUT); }
void loop() { int v = analogRead(POT_PIN); }
"""


def test_pinmode_input_serving_an_analogread_is_a_pot_not_a_button():
    nl = extract_netlist(_POT_BOILERPLATE, "arduino_uno_r3")
    types = [c.type for c in nl.components]
    assert types == ["potentiometer"], types


def test_an_analogread_alias_lands_on_the_analog_channel():
    """Le remap vit dans la TABLE d'alias (`_extract_const_aliases`), pas dans
    une passe locale : substitution, identifiants par broche et passe
    generique doivent voir le meme net."""
    aliases = _extract_const_aliases(_POT_BOILERPLATE)
    assert aliases == {"POT_PIN": "A3"}, aliases
    nl = extract_netlist(_POT_BOILERPLATE, "arduino_uno_r3")
    pot = nl.components[0]
    assert [p.net for p in pot.pins] == ["5V", "A3", "GND"], pot.pins


def test_a_literal_analogread_lands_on_the_analog_channel():
    code = "void loop() { int v = analogRead(3); }"
    nl = extract_netlist(code, "arduino_uno_r3")
    pot = next(c for c in nl.components if c.type == "potentiometer")
    assert [p.net for p in pot.pins] == ["5V", "A3", "GND"], pot.pins


def test_identifiers_follow_the_remapped_net():
    """Un remap local (premiere version du correctif) detachait les
    identifiants du composant : `pin_to_names` restait indexe sur D3 pendant
    que le composant partait sur A3, et le sous-typage par identifiant
    (`LDR_PIN` -> ldr) mourait en silence."""
    code = ("#define LDR_PIN 3\n"
            "void setup() { pinMode(LDR_PIN, INPUT); }\n"
            "void loop() { int v = analogRead(LDR_PIN); }\n")
    nl = extract_netlist(code, "arduino_uno_r3")
    types = [c.type for c in nl.components]
    assert types == ["ldr"], types


def test_a_real_digital_input_is_still_a_button():
    code = ("#define BTN_PIN 4\n"
            "void setup() { pinMode(BTN_PIN, INPUT); }\n"
            "void loop() { int v = digitalRead(BTN_PIN); }\n")
    nl = extract_netlist(code, "arduino_uno_r3")
    btn = next(c for c in nl.components if c.type == "button")
    assert any(p.net == "D4" for p in btn.pins), btn.pins


TESTS = [
    test_the_real_sketch_yields_its_component,
    test_the_data_variable_is_NOT_aliased,
    test_the_presumed_marker_survives,
    test_every_bare_declaration_type_resolves,
    test_a_for_loop_header_is_never_aliased,
    test_an_unused_declaration_is_ignored,
    test_const_declarations_still_win,
    test_a_multi_declarator_line_aliases_them_all,
    test_the_unresolved_pins_brought_back_the_phantom_box,
    test_a_function_call_is_not_read_as_a_declarator_list,
    test_a_data_constant_on_the_same_line_stays_out,
    test_pinmode_input_serving_an_analogread_is_a_pot_not_a_button,
    test_an_analogread_alias_lands_on_the_analog_channel,
    test_a_literal_analogread_lands_on_the_analog_channel,
    test_identifiers_follow_the_remapped_net,
    test_a_real_digital_input_is_still_a_button,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
