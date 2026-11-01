"""Les commentaires ne sont pas du code : la detection ne les lit plus.

Regle utilisateur du **2026-08-31**, enoncee en QA AB1 : « le wiring est
etabli depuis le code, pas les commentaires, sinon ca n'a pas de sens ». Le
depouillement est fait UNE fois a l'entree d'`extract_netlist`
(`strip_comments`), pour que TOUTE la detection voie le meme code — une regle
par regex aurait laisse des trous.

Deux defauts reels l'ont imposee :
- gemma commente ses sketches broches-nues « (e.g., L298N ENA) », et
  l'extrait de code par broche incluait les commentaires : le nom de driver
  de la prose re-silenciait la modale avec un L298N que personne n'a demande
  (troisieme forme de code a defaire la QA AB1) ;
- #86 (c) : un constructeur COMMENTE (`// L298N motor(9, 7, 8);`) produisait
  un moteur et un driver entierement cables, `signature_detected=True` — une
  certitude affirmee depuis du code desactive.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.wiring.markers import extract_netlist, strip_comments  # noqa: E402

BOARD = "arduino_uno_r3"


# ── le depouilleur lui-meme ──────────────────────────────────────────────

def test_comments_go_code_stays():
    assert strip_comments("int a = 1; // fin") == "int a = 1; "
    assert strip_comments("/* bloc */ int a = 1;") == " int a = 1;"
    assert strip_comments("// ligne entiere\nint a;") == "\nint a;"


def test_a_string_is_never_read_as_a_comment():
    """`Serial.println("http://...")` porte un `//` DANS une chaine : le
    traiter en commentaire mangerait la fin de ligne, guillemet fermant
    compris, et les regex verraient du code casse."""
    src = 'Serial.println("http://x.com");'
    assert strip_comments(src) == src
    src2 = "char c = '/'; int b = 2;"
    assert strip_comments(src2) == src2
    # Guillemet ECHAPPE dans la chaine : le « // » qui suit est toujours
    # dans la chaine, pas un commentaire.
    src3 = 'String s = "a \\" // pas un com"; int d;'
    assert strip_comments(src3) == src3


def test_line_structure_survives_block_comments():
    """Des regex d'ancrage `^` en mode MULTILINE dependent de la structure de
    lignes (`_BARE_ALIAS_RE`) : un bloc multi-lignes est remplace par ses
    sauts de ligne, jamais supprime avec eux."""
    assert strip_comments("a;/*x\ny*/b;") == "a;\nb;"
    assert strip_comments("/*1\n2\n3*/int a;").count("\n") == 2


# ── ce que la detection ne voit plus ─────────────────────────────────────

def test_a_commented_out_constructor_creates_no_wired_motor():
    """#86 (c). Le constructeur est du code DESACTIVE : il ne cree plus de
    moteurs certains. L'`#include` reel, lui, reste du code — la boite
    placeholder honnete (non cablee) est le bon residu, pas un driver cable
    avec `signature_detected=True`."""
    code = ("#include <L298N.h>\n"
            "// L298N motor(9, 7, 8);\n"
            "void setup() {}\nvoid loop() {}\n")
    netlist = extract_netlist(code, BOARD, prompt="", context="")
    moteurs = [c for c in netlist.components if c.type == "dc_motor"]
    assert moteurs == [], [(c.ref, c.type) for c in netlist.components]
    certains = [c for c in netlist.components
                if c.attributes.get("signature_detected")]
    assert certains == [], [(c.ref, c.type) for c in certains]


def test_a_commented_out_include_creates_nothing_at_all():
    """`// #include <Servo.h>` contient litteralement `#include <Servo.h>` :
    sans depouillement, la regex d'include matchait au milieu du
    commentaire."""
    code = ("// #include <Servo.h>\n// Servo s;\n"
            "void setup() {}\nvoid loop() {}\n")
    netlist = extract_netlist(code, BOARD, prompt="", context="")
    assert netlist.components == [], \
        [(c.ref, c.type) for c in netlist.components]


def test_a_real_include_in_a_string_is_still_not_a_component():
    """Contre-epreuve du string-aware : un nom de header dans une CHAINE
    n'est pas un include non plus — mais la chaine, elle, survit au
    depouillement (c'est du code)."""
    code = ('void setup() { Serial.begin(9600); '
            'Serial.println("#include <Servo.h>"); }\n'
            "void loop() {}\n")
    netlist = extract_netlist(code, BOARD, prompt="", context="")
    servos = [c for c in netlist.components if c.type == "servo"]
    assert servos == [], [(c.ref, c.type) for c in netlist.components]


TESTS = [
    test_comments_go_code_stays,
    test_a_string_is_never_read_as_a_comment,
    test_line_structure_survives_block_comments,
    test_a_commented_out_constructor_creates_no_wired_motor,
    test_a_commented_out_include_creates_nothing_at_all,
    test_a_real_include_in_a_string_is_still_not_a_component,
]


def main() -> None:
    passed = failed = 0
    for t in TESTS:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL  {t.__name__}: {exc}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
