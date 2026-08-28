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


TESTS = [
    test_the_real_sketch_yields_its_component,
    test_the_data_variable_is_NOT_aliased,
    test_the_presumed_marker_survives,
    test_every_bare_declaration_type_resolves,
    test_a_for_loop_header_is_never_aliased,
    test_an_unused_declaration_is_ignored,
    test_const_declarations_still_win,
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
