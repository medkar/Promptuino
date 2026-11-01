"""#85 : bannir une lib (swap de puce vers cible NUE) FILTRE au lieu de couper.

Le defaut, mesure le 2026-08-31 avant le correctif :
- ban « servo » + prompt qui ecrit « servo » -> le sauvetage des puces
  nommees (`named_corpus_libs`) reinjectait la lib bannie en bloc IMPERATIF.
  Le swap etait annule des que le prompt nommait la puce.
- ban sans remplacant -> `_apply_lib_overrides` rendait [] et
  `_build_lib_context` sautait TOUT le retrieval : une feature servo+capteur
  perdait aussi le contexte du capteur, sans rapport avec le swap.

Le correctif : les bans descendent en parametre (`banned_libs`) jusqu'a
`_build_lib_context` et `retrieve_libs`, porte UNIQUE qui les ecarte de
toutes les injections (retrieval, sauvetage nomme, forced residuel). Un ban
est INCONDITIONNEL : nommer la puce ne la ramene pas — le swap est
posterieur au prompt, c'est lui la decision (asymetrie voulue avec le filtre
driver de #82, qui a un passe-droit « nomme »).

Les tests qui passent par l'encodeur suivent la convention des gardes RAG :
ils REFUSENT de conclure si le modele ONNX est indisponible.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import rag  # noqa: E402

_SERVO_PROMPT = "un servo qui suit le potentiometre"
_OLED_PROMPT = "affiche la temperature sur un ecran OLED"


# ── branche forcee (lexicale, sans encodeur) ────────────────────────────

def test_the_named_rescue_leak_is_real_without_the_ban():
    """Caracterisation de la fuite que le filtre tue : forced_libs=[] (ban
    sans remplacant, ancien contrat) + prompt qui nomme la puce -> la lib
    revenait par le sauvetage des puces nommees, en bloc imperatif."""
    ctx, _ = rag._build_lib_context(_SERVO_PROMPT, forced_libs=[])
    assert "### Servo" in ctx, ctx[:200]
    assert "reference these exact APIs" in ctx, ctx[:200]


def test_the_ban_closes_the_named_rescue_gate():
    ctx, _ = rag._build_lib_context(_SERVO_PROMPT, forced_libs=[],
                                    banned_libs=frozenset({"servo"}))
    assert "### Servo" not in ctx, ctx[:200]


def test_the_ban_also_filters_a_residual_forced_entry():
    """Defense de la porte unique : meme une entree encore presente dans
    forced_libs (appelant pas a jour, chemin registre...) ne passe pas."""
    entry = rag.corpus_entry("servo")
    assert entry is not None
    ctx, _ = rag._build_lib_context(_SERVO_PROMPT,
                                    forced_libs=[dict(entry)],
                                    banned_libs=frozenset({"servo"}))
    assert "### Servo" not in ctx, ctx[:200]


def test_augment_user_prompt_threads_banned_libs():
    """Le parametre traverse l'enveloppe publique : sans lui, le fil
    studio_view -> augment_user_prompt -> build_lib_context serait coupe au
    milieu sans qu'aucun test unitaire du RAG ne le voie."""
    out = rag.augment_user_prompt(_SERVO_PROMPT, forced_libs=[],
                                  banned_libs=frozenset({"servo"}))
    assert "### Servo" not in out, out[:200]
    control = rag.augment_user_prompt(_SERVO_PROMPT, forced_libs=[])
    assert "### Servo" in control, control[:200]


# ── branche retrieval (encodeur requis) ─────────────────────────────────

def _require_model():
    assert rag._load(), ("modele ONNX indisponible : mesure impossible, on "
                         "refuse de conclure")


def test_retrieve_libs_skips_banned_ids():
    _require_model()
    named = "affiche du texte sur un ecran OLED ssd1306"
    ids = [e.get("id") for e in rag.retrieve_libs(
        named, k=3, threshold=rag._CODEGEN_MIN_SCORE)]
    assert "adafruit-ssd1306" in ids, ids  # temoin : nomme -> present
    ids_ban = [e.get("id") for e in rag.retrieve_libs(
        named, k=3, threshold=rag._CODEGEN_MIN_SCORE,
        banned_ids=frozenset({"adafruit-ssd1306"}))]
    assert "adafruit-ssd1306" not in ids_ban, ids_ban


def test_ban_only_lets_unrelated_retrieval_run():
    """Le coeur du #85 : ban sans remplacant -> le retrieval TOURNE (l'ancien
    contrat coupait tout). La lib bannie est absente, le reste revient."""
    _require_model()
    ctx = rag.build_lib_context(
        _OLED_PROMPT, banned_libs=frozenset({"adafruit-ssd1306"}))
    assert ctx, "le retrieval doit tourner et injecter quelque chose"
    assert "### Adafruit SSD1306" not in ctx, ctx[:300]


TESTS = [
    test_the_named_rescue_leak_is_real_without_the_ban,
    test_the_ban_closes_the_named_rescue_gate,
    test_the_ban_also_filters_a_residual_forced_entry,
    test_augment_user_prompt_threads_banned_libs,
    test_retrieve_libs_skips_banned_ids,
    test_ban_only_lets_unrelated_retrieval_run,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
