"""La reparation connait l'API des bibliotheques que le code inclut.

QA AB2 bis du #82 (2026-08-31) : « ca marche par intermittence ». Le code
genere etait propre cote bibliotheque SAUF un appel — `motor2.forward(2000)`,
une methode reelle appelee avec un argument qu'elle ne prend pas. La
reparation echouait sur ce correctif d'une ligne : elle recevait l'erreur et
le code, mais AUCUNE connaissance de l'API — elle devait DEVINER la
signature, et un modele 2B devine mal.

`rag.api_context_for_code` donne aux DEUX etages de reparation (`fix_code`,
premier essai, et `repair_code`, second) la meme verite que la generation a
recue : les blocs d'API du corpus pour les `#include` du code.

Mesure appariee (gemma4:e2b, arduino-cli, memes generations en echec,
reparation sans/avec API) : voir `bench_repair` dans le commit.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.ai_backends.base import AIBackend  # noqa: E402
from ui.rag import api_context_for_code  # noqa: E402

CODE_L298N = "#include <L298N.h>\nvoid setup() {}\nvoid loop() {}\n"


# ── le pont code -> API ──────────────────────────────────────────────────

def test_an_included_corpus_lib_yields_its_api_block():
    ctx = api_context_for_code(CODE_L298N)
    assert "void forward()" in ctx, ctx[:300]
    assert "Authoritative API" in ctx
    # L'exemple accompagne : c'est lui qui montre l'ARITE correcte en
    # contexte (forward() sans argument, forwardFor pour la duree).
    assert "Example:" in ctx


def test_an_unknown_header_yields_nothing():
    assert api_context_for_code("#include <MaLibInconnue.h>\n") == ""
    assert api_context_for_code("") == ""


def test_a_companion_header_does_not_drag_its_entry():
    """Seul le PREMIER en-tete d'une entree lui appartient — meme regle que
    `lib_by_header._from_corpus` : `Adafruit_GFX.h` sous `adafruit-ssd1306`
    est un COMPAGNON, l'associer affirmerait une correspondance fausse."""
    ctx = api_context_for_code("#include <Adafruit_GFX.h>\n")
    assert "SSD1306" not in ctx, ctx[:200]


def test_the_block_count_is_capped():
    code = ("#include <L298N.h>\n#include <Servo.h>\n"
            "#include <DHT.h>\n#include <TMC2209.h>\n")
    ctx = api_context_for_code(code, max_libs=2)
    assert ctx.count("### ") == 2, ctx.count("### ")


# ── les deux etages de reparation la recoivent ───────────────────────────

def test_the_first_repair_stage_gets_the_api():
    """`fix_code` est le PREMIER essai — le laisser aveugle pendant que le
    second voit l'API reviendrait a griller l'essai le moins couteux. Le
    message est compose dans `base`, partage par les trois backends."""
    msg = AIBackend._build_fix_user_message(None, CODE_L298N, "boom")
    assert "Authoritative API" in msg, msg[:300]
    assert "void forward()" in msg


def test_the_second_repair_stage_gets_the_api():
    sysp = AIBackend._build_repair_code_system(
        None, "Arduino Uno R3", "fr", code=CODE_L298N, errors="boom")
    assert "Authoritative API" in sysp, sysp[:300]


def test_the_audit_mode_stays_clean():
    """`errors` vide = l'outil manuel « Analyser / Réparer » sur du code qui
    COMPILE deja : rien a corriger cote signatures, le bloc n'a rien a y
    faire."""
    sysp = AIBackend._build_repair_code_system(
        None, "Arduino Uno R3", "fr", code=CODE_L298N, errors="")
    assert "Authoritative API" not in sysp


def test_code_without_corpus_lib_adds_nothing():
    msg = AIBackend._build_fix_user_message(
        None, "void setup(){}\nvoid loop(){}", "boom")
    assert "Authoritative API" not in msg


# ── Le TROISIEME etage : la reparation par fenetres ─────────────────────
# C'est le PREMIER maillon de la vraie chaine (arduino_cli), celui qui
# traite les erreurs a ligne connue -- une mauvaise arite l'est toujours.
# Les deux premiers correctifs de cette QA l'avaient RATE : l'injection
# vivait dans fix_code/repair_code, et les bancs testaient une
# reconstitution de la chaine au lieu de la chaine (les "restored" de
# l'utilisateur continuaient pendant que mes bancs etaient verts).

def test_the_window_repair_stage_gets_the_api():
    """La fenetre ne contient pas les `#include` : le bloc vient de
    l'appelant, en parametre."""
    msg = AIBackend._build_repair_region_user(
        None, "motor1.forward(2000);", "no matching function",
        api_context="Authoritative API ...\n- void forward()")
    assert "void forward()" in msg
    assert "signatures above win" in msg
    # Sans bloc : le message d'avant, inchange.
    nu = AIBackend._build_repair_region_user(
        None, "motor1.forward(2000);", "no matching function")
    assert "signatures above win" not in nu


def test_line_anchored_repair_passes_the_full_file_api():
    """Le maillon qui manquait : `line_anchored_repair` calcule le bloc sur
    le code COMPLET et le passe a CHAQUE fenetre. Verifie sur la vraie
    fonction, avec un backend-espion -- pas une reconstitution."""
    from ui.arduino_cli import line_anchored_repair

    code = ("#include <L298N.h>\n"
            "L298N motor1(9, 7, 8);\n"
            "void setup() {}\n"
            "void loop() {\n"
            "  motor1.forward(2000);\n"
            "}\n")
    erreur = ("sk.ino:5:24: error: no matching function for call to "
              "'L298N::forward(int)'")
    vus: list = []

    class _Espion:
        def repair_region(self, region, errors, language, board_name,
                          api_context=""):
            vus.append({"region": region, "api": api_context})
            return region      # aucun changement -> la fonction rend None

    line_anchored_repair(code, erreur, _Espion(), "fr", "Arduino Uno R3")
    assert vus, "le backend-espion n'a jamais ete appele"
    assert "void forward()" in vus[0]["api"], (
        "la fenetre doit recevoir l'API du FICHIER", vus[0]["api"][:200])
    assert "#include" not in vus[0]["region"], (
        "pre-condition du besoin : la fenetre ne voit pas les includes")


TESTS = [
    test_an_included_corpus_lib_yields_its_api_block,
    test_an_unknown_header_yields_nothing,
    test_a_companion_header_does_not_drag_its_entry,
    test_the_block_count_is_capped,
    test_the_first_repair_stage_gets_the_api,
    test_the_second_repair_stage_gets_the_api,
    test_the_audit_mode_stays_clean,
    test_code_without_corpus_lib_adds_nothing,
    test_the_window_repair_stage_gets_the_api,
    test_line_anchored_repair_passes_the_full_file_api,
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
