"""La regle de la taille de contexte, LA MEME pour Ollama et LM Studio.

Decisions de l'auteur du 2026-11-06 : un curseur de 16 384 au maximum du
modele (pas seulement des puissances de 2), aucune valeur sous ce que
Promptuino demande, et un modele dont le maximum est plus petit est dit
INUTILISABLE, en precisant que son contexte est trop petit.

Mesures du meme jour : Ollama applique la valeur exacte (20 000 -> 20 000) ;
LM Studio arrondit au multiple de 256 superieur (20 000 -> 20 224).

Run: python scripts/test_contexte.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.contexte as cx  # noqa: E402


def test_the_floor_is_the_one_the_author_chose():
    assert cx.CTX_PROMPTUINO == 16384
    from ui.lmstudio_models import CTX_PROMPTUINO as ancien
    assert ancien == cx.CTX_PROMPTUINO, "deux constantes pourraient diverger"


def test_a_model_below_the_floor_is_unusable_an_unknown_one_is_not():
    assert not cx.utilisable(8192)
    assert cx.utilisable(16384) and cx.utilisable(131072)
    assert cx.utilisable(None), "on ne declare pas inutilisable sur une ignorance"


def test_the_range_goes_from_the_floor_to_the_models_maximum():
    assert cx.plage(131072) == (16384, 131072)
    assert cx.plage(20000) == (16384, 19456), "le haut tombe sur un pas entier"
    assert cx.plage(None) == (16384, cx.MAX_INCONNU)


def test_a_value_is_brought_back_into_the_range_on_a_step():
    assert cx.ramener(8192, 131072) == 16384, "jamais sous le plancher"
    assert cx.ramener(20001, 131072) == 19456, "sur un pas de 1 024"
    assert cx.ramener(10**9, 131072) == 131072, "jamais au-dela du modele"
    assert cx.ramener("n'importe quoi", 131072) == 16384


def test_lm_studios_rounding_is_not_a_difference():
    """Mesure : 20 000 demandes -> 20 224 charges. Comparer a l'egalite
    afficherait « different du reglage » juste apres avoir charge."""
    assert cx.accorde(20224, 20000)
    assert cx.accorde(16384, 16384)
    assert not cx.accorde(32768, 16384)
    assert not cx.accorde(16384, 32768)
    assert not cx.accorde(None, 16384)


TESTS = [
    test_the_floor_is_the_one_the_author_chose,
    test_a_model_below_the_floor_is_unusable_an_unknown_one_is_not,
    test_the_range_goes_from_the_floor_to_the_models_maximum,
    test_a_value_is_brought_back_into_the_range_on_a_step,
    test_lm_studios_rounding_is_not_a_difference,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
