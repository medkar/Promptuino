"""TODO #46 — un composant nomme par un MOT (sans chiffre) doit compter.

Le constat, mesure pendant la QA K1 : « Fais defiler un arc-en-ciel sur un
ruban NeoPixel » remontait HT16K33 (0.643), MAX7219 (0.622) et TM1637 (0.595).
`adafruit-neopixel` n'y etait PAS, alors que le prompt le nomme — et le contrat
affiche a l'utilisateur est « nomme ton composant et ca marchera ».

La cause : `_signature_tokens` ne retient un jeton que s'il fait ≥4 caracteres
ET contient un chiffre, plus l'id de l'entree s'il tient en UN SEUL mot. Pour
cette entree : `ws2812`, `sk6812`… mais pas `neopixel`, et l'id
`adafruit-neopixel` est composite donc rejete. Le seul mot que l'utilisateur
ecrit est precisement celui qui ne declenche rien.

POURQUOI UNE TABLE A LA MAIN. Deux generalisations ont ete mesurees sur les 91
documents et ecartees : « tous les jetons uniques du corpus » (+452 jetons,
mais `button`, `search`, `network`, `config`…) et « les jetons du NOM seul »
(27 entrees, mais `full`, `array`, `rate`, et surtout `sparkfun` — un nom de
FABRICANT qui pointerait vers UN driver moteur precis). Les deux se reglent sur
un echantillon, exactement ce qui a tue le filet d'ambiguite automatique en
juin 2026. Une table explicite ne devine rien et se relit.

Run : python scripts/test_rag_extra_tokens.py
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui import rag


def _tokens_of(blob: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", (blob or "").lower()))


def _entry_blob(entry: dict) -> str:
    return (entry.get("name", "") + " "
            + " ".join(entry.get("keywords", []) or []) + " "
            + (entry.get("description") or ""))


# ── La garde qui rend la table sure ──────────────────────────────────────────

def test_extra_tokens_are_unique_in_the_corpus():
    """LE garde-fou. Un jeton porte par DEUX entrees booste la mauvaise moitie
    du temps, avec +0.30 et un en-tete imperatif au bout. `dallastemperature`
    a ete ecarte a ce titre pendant l'ecriture : il vit aussi dans `onewire`."""
    fautifs = []
    for cid, tokens in rag._EXTRA_SIGNATURE_TOKENS.items():
        for tok in tokens:
            porteurs = [e.get("id") for e in rag.all_corpus_entries()
                        if tok in _tokens_of(_entry_blob(e))]
            if porteurs != [cid]:
                fautifs.append((tok, porteurs))
    assert not fautifs, f"jetons non uniques : {fautifs}"


def test_every_extra_token_names_a_real_corpus_entry():
    ids = {e.get("id") for e in rag.all_corpus_entries()}
    inconnus = sorted(set(rag._EXTRA_SIGNATURE_TOKENS) - ids)
    assert not inconnus, inconnus


def test_no_extra_token_would_already_be_found():
    """Une entree qui ne sert a rien est une entree qu'on relira sans savoir
    pourquoi elle est la. Un jeton deja distinctif (chiffre, ou id d'un seul
    mot) n'a rien a faire dans la table."""
    inutiles = []
    for cid, tokens in rag._EXTRA_SIGNATURE_TOKENS.items():
        for tok in tokens:
            if len(tok) >= 4 and any(c.isdigit() for c in tok):
                inutiles.append((cid, tok, "contient un chiffre"))
            elif tok == cid:
                inutiles.append((cid, tok, "est deja l'id"))
    assert not inutiles, inutiles


def test_the_table_stays_small_enough_to_be_read():
    """Elle doit rester une liste qu'on relit, pas une regle deguisee. Si elle
    grossit, c'est le signe qu'il faut mesurer une generalisation — et se
    souvenir que les deux tentees ont ete ecartees SUR MESURE."""
    assert len(rag._EXTRA_SIGNATURE_TOKENS) <= 12, len(rag._EXTRA_SIGNATURE_TOKENS)


# ── L'effet, mesure ──────────────────────────────────────────────────────────

def test_the_measured_hole_is_closed():
    """Le cas exact de la QA K1."""
    prompt = ("Fais defiler un arc-en-ciel sur un ruban NeoPixel de 16 LED "
              "branche sur la broche 6")
    ids = [l.get("id") for l in
           rag.retrieve_libs(prompt, k=3, threshold=rag._CODEGEN_MIN_SCORE)]
    assert ids and ids[0] == "adafruit-neopixel", ids


def test_a_named_screen_beats_the_clock_it_used_to_lose_to():
    """« Affiche l'heure sur un ecran LiquidCrystal I2C » remontait `rtclib`
    SEUL : le mot « heure » gagnait contre le nom du composant."""
    ids = [l.get("id") for l in rag.retrieve_libs(
        "Affiche l'heure sur un ecran LiquidCrystal I2C",
        k=3, threshold=rag._CODEGEN_MIN_SCORE)]
    assert ids and ids[0] == "liquidcrystal-i2c", ids


def test_a_piezo_finds_the_buzzer():
    ids = [l.get("id") for l in rag.retrieve_libs(
        "Joue une melodie sur un piezo", k=3,
        threshold=rag._CODEGEN_MIN_SCORE)]
    assert "buzzer" in ids, ids


def test_the_known_traps_still_boost_nothing():
    """Les mots generiques que les deux generalisations ecartees auraient
    fait booster. Aucun ne doit devenir un declencheur."""
    pieges = ("button", "search", "network", "internet", "config", "http",
              "array", "camera", "rate", "shift", "register", "buttons",
              "sparkfun", "full", "echo", "ping")
    tous = {t for toks in rag._EXTRA_SIGNATURE_TOKENS.values() for t in toks}
    assert not (tous & set(pieges)), tous & set(pieges)


def test_the_controls_are_untouched():
    """Extrait de la batterie AVANT/APRES : 26 prompts sur 29 n'ont pas bouge.
    Ceux-ci sont ceux qu'une regression casserait en premier."""
    attendu = {
        "Affiche la temperature du dht22 sur un ecran ssd1306": "dht-sensor-library",
        "Fais tourner un servo de 0 a 180 degres": "servo",
        "Lis un badge rfid mfrc522 et ouvre une gache": "mfrc522",
        "Mesure le courant avec un ina219": "adafruit-ina219",
    }
    for prompt, premier in attendu.items():
        ids = [l.get("id") for l in rag.retrieve_libs(
            prompt, k=3, threshold=rag._CODEGEN_MIN_SCORE)]
        assert ids and ids[0] == premier, (prompt, ids)


# ── Ce qui reste ouvert, ecrit plutot que decouvert ──────────────────────────

def test_a_short_named_prompt_still_loses_to_the_floor():
    """LIMITE MESUREE, non corrigee. « Allume un anneau neopixel en bleu » :
    le boost s'applique et `adafruit-neopixel` sort TOP-1 a 0.46, avec 0.21
    d'ecart sur le suivant — ce n'est pas du bruit, c'est un vainqueur net.
    Mais le plancher `_CODEGEN_MIN_SCORE` vaut 0.50 et le bloque.

    On ne touche PAS au plancher : c'est une constante calibree en juin 2026
    sur une batterie de prompts reels, et la baisser rouvrirait l'injection de
    libs au hasard sur de la prose generique. Ce test EXISTE pour que la limite
    soit ecrite et retrouvee, pas pour la deplorer — s'il devient faux un jour,
    c'est que quelqu'un a touche au plancher et doit le savoir."""
    p = "Allume un anneau neopixel en bleu"
    brut = rag.retrieve_libs(p, k=5, threshold=0.0, relative_gate=0)
    assert brut and brut[0].get("id") == "adafruit-neopixel", brut[:2]
    assert brut[0]["_score"] < rag._CODEGEN_MIN_SCORE, brut[0]["_score"]
    assert not rag.retrieve_libs(p, k=3, threshold=rag._CODEGEN_MIN_SCORE)


def test_an_accented_french_word_cannot_trigger():
    """AUTRE LIMITE, trouvee en ecrivant la table : la tokenisation coupe sur
    les accents, donc « photoresistance » ecrit avec un accent ne peut pas
    servir de declencheur. Le repliement d'accents existe ailleurs
    (`declared_components.match_prompt`) ; l'apporter ici toucherait aussi
    `prompt_names_a_chip` et merite sa propre mesure."""
    assert re.findall(r"[a-z0-9]+", "photorésistance") == ["photor", "sistance"]
    assert "photoresistor" in rag._EXTRA_SIGNATURE_TOKENS["ldr"]


TESTS = [
    test_extra_tokens_are_unique_in_the_corpus,
    test_every_extra_token_names_a_real_corpus_entry,
    test_no_extra_token_would_already_be_found,
    test_the_table_stays_small_enough_to_be_read,
    test_the_measured_hole_is_closed,
    test_a_named_screen_beats_the_clock_it_used_to_lose_to,
    test_a_piezo_finds_the_buzzer,
    test_the_known_traps_still_boost_nothing,
    test_the_controls_are_untouched,
    test_a_short_named_prompt_still_loses_to_the_floor,
    test_an_accented_french_word_cannot_trigger,
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
