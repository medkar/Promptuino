"""TODO #40 partie 2 (a) — une puce NOMMEE survit a la suppression du retrieval.

Le contexte, mesure le 2026-08-10 sur le corpus reel (91 entrees).

Quand le prompt nomme un part-number que le corpus ne connait pas, #37 COUPE le
retrieval semantique. Cette coupe est justifiee, et la mesure d'aujourd'hui la
confirme : ce qui remonte pour la puce inconnue n'est pas du bruit, c'est une
puce FONCTIONNELLEMENT VOISINE — AS7341 -> TCS34725 (0.522, un autre capteur de
couleur), VEML7700 -> BH1750 (0.575, un autre capteur de lux), ADS1220 -> HX711
(0.603, un autre ampli de cellule de charge). Exactement la substitution qui
compile et se trompe en silence.

Mais la coupe etait TROP LARGE : elle emportait aussi les puces que
l'utilisateur a NOMMEES lui-meme. Un seul filet les rattrapait,
`forced_libs_for_generation`, et il ne voit que les puces candidates d'un
`ClarifyGroup` cure : **62 des 91 entrees du corpus. Les 29 autres tombaient**,
dont servo, adafruit-neopixel, hx711, keypad, irremote, pir-motion-sensor,
tinygps-plus, l298n, nema17, onewire, pca9685.

Mesure a l'appui (4 prompts sur 7 construits a la main perdaient une puce
nommee) :
    « Lis un AS7341 et pilote un ruban WS2812 »        -> NeoPixel (0.890) perdu
    « Mesure avec un VEML7700 ... afficheur TM1637 »   -> TM1637   (0.674) perdu
    « Lis un AS7341 ... poids mesure par un HX711 »    -> HX711    (0.617) perdu
    « Lis un VEML7700 ... module LoRa SX1276 »         -> LoRa     (0.757) perdu

La regle posee ici n'est pas un seuil et ne devine rien : elle est LEXICALE et
categorielle, la meme que `prompt_names_a_chip` utilise deja — l'utilisateur a
ecrit le nom de sa puce, ou il ne l'a pas ecrit.

Run : python scripts/test_named_chip_survives_suppression.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui import rag
from ui.rag import build_lib_context, named_corpus_libs

# Entree ad hoc du registre, telle que `_apply_registry_results` la fabrique
# pour un part-number introuvable au corpus.
_AS7341 = {"id": "as7341", "name": "Adafruit AS7341",
           "headers": ["Adafruit_AS7341.h"], "keywords": ["as7341"],
           "example_code": "void setup(){/*ADHOC*/}", "api_signatures": {},
           "_registry": True}


def _ids(libs):
    return [l.get("id") for l in libs]


# ── Le seam pur ───────────────────────────────────────────────────────────────

def test_it_returns_the_entry_whose_part_number_is_written():
    libs = named_corpus_libs("lis la temperature avec un dht22")
    assert "dht-sensor-library" in _ids(libs), _ids(libs)


def test_it_returns_nothing_when_no_chip_is_named():
    """Un prompt qui DECRIT sans nommer ne doit rien forcer — c'est la
    difference categorielle sur laquelle tout ce chantier repose."""
    assert named_corpus_libs("mesure la distance avec un capteur a ultrasons") == []


def test_it_sees_a_chip_named_by_a_single_word_id():
    """`servo`, `keypad`, `lora`… n'ont aucun chiffre : ils passent par la
    branche « id d'un seul mot » de `_signature_tokens`. Ce sont precisement
    des entrees que le filet des ClarifyGroup ne rattrapait pas."""
    assert "servo" in _ids(named_corpus_libs("fais tourner un servo a 90 degres"))


def test_it_is_empty_on_an_empty_prompt():
    assert named_corpus_libs("") == []
    assert named_corpus_libs("   ") == []


# ── L'invariant dans build_lib_context ────────────────────────────────────────

def test_the_named_chip_survives_the_unknown_part_suppression():
    """LE test du chantier. Avant, `DHT` etait absent du contexte : la coupe du
    retrieval emportait une puce que l'utilisateur avait ecrite noir sur blanc."""
    ctx = build_lib_context(
        "lis un as7341 et affiche la temperature avec un dht22",
        forced_libs=[_AS7341])
    assert "Adafruit AS7341" in ctx
    assert "DHT.h" in ctx, "la puce NOMMEE par l'utilisateur a ete perdue"


def test_the_rescue_does_not_reopen_the_semantic_retrieval():
    """La coupe reste entiere pour ce qui n'est PAS nomme. TCS34725 est le
    voisin fonctionnel que la similarite remonte pour un AS7341 (0.522) : c'est
    lui qu'il ne faut jamais injecter, et il n'est nomme nulle part."""
    ctx = build_lib_context(
        "lis la couleur de la lumiere avec un as7341",
        forced_libs=[_AS7341])
    assert "TCS34725" not in ctx, ctx[:400]
    assert "Possibly relevant" not in ctx, "aucun bloc hedge sur ce chemin"


def test_the_rescued_chip_is_authoritative_not_hedged():
    """Une puce NOMMEE fait autorite (regle categorielle de #37). La rattraper
    dans un bloc hedge la presenterait comme une piste, alors que c'est la
    seule chose dont on soit certain sur ce prompt."""
    ctx = build_lib_context(
        "lis un as7341 et affiche la temperature avec un dht22",
        forced_libs=[_AS7341])
    assert "reference these exact APIs" in ctx
    assert "Possibly relevant" not in ctx


def test_it_rescues_even_when_the_registry_found_nothing():
    """`forced_libs=[]` = le registre n'a rien trouve. Le contexte etait alors
    VIDE : le modele devait ecrire le code du WS2812 de memoire, alors que le
    corpus le documente. C'est le cas ou le rattrapage vaut le plus cher."""
    ctx = build_lib_context("lis un as7341 et pilote un ruban ws2812",
                            forced_libs=[])
    assert "Adafruit NeoPixel" in ctx, "contexte vide alors que WS2812 est nomme"
    assert "reference these exact APIs" in ctx


def test_nothing_named_and_nothing_forced_still_yields_an_empty_context():
    """Le contrat de `forced_libs=[]` (registre bredouille, rien de nomme a
    cote) est INCHANGE : contexte vide, et le modele recoit la directive
    UNKNOWN COMPONENT. Le rattrapage ne doit pas le remplir de rien."""
    assert build_lib_context("lis la couleur avec un as7341",
                             forced_libs=[]) == ""


def test_the_rescued_chip_is_not_duplicated():
    """Si la lib forcee EST celle que le prompt nomme, un seul bloc."""
    dht = rag.corpus_entry("dht-sensor-library")
    assert dht is not None
    ctx = build_lib_context("affiche la temperature du dht22",
                            forced_libs=[dht])
    assert ctx.count("### DHT sensor library") == 1, ctx


def test_the_plain_retrieval_path_is_untouched():
    """Aucun `forced_libs` -> le rattrapage ne s'applique pas et le retrieval
    normal garde exactement son comportement (y compris l'en-tete imperatif du
    a `prompt_names_a_chip`)."""
    ctx = build_lib_context("affiche la temperature du dht22")
    assert "DHT.h" in ctx
    assert "reference these exact APIs" in ctx


# ── La taille du contexte : la mesure que le TODO exige ───────────────────────

def test_the_rescue_stays_within_the_measured_budget():
    """#40 impose de MESURER, pas de supposer. Mesures du 2026-08-10, meme
    regle de trois que la partie 1 (4 caracteres ~ 1 token, fenetre 8192) et
    avec une entree registre realiste (exemple officiel tronque a 3500 car.) :

        forcé seul, rien de nommé ................  993 tokens  (12 %)
        + 1 puce nommée (DHT22) ..................  1275 tokens (16 %)
        + 2 puces nommées (DHT22 + SSD1306) ......  1810 tokens (22 %)
        + 4 puces nommées ........................  2235 tokens (27 %)
        + 6 puces nommées (prompt extrême) .......  2889 tokens (35 %)

    Reference de la partie 1 : 2402 tokens (29 %). Le rattrapage ne depasse ce
    budget que sur un prompt qui NOMME six puces — auquel cas les six ont ete
    ecrites par l'utilisateur, et l'alternative (les jeter) est precisement le
    defaut que ce chantier corrige.

    Le plafond ci-dessous est large a dessein : il n'existe pour attraper
    qu'une seule regression, celle ou le rattrapage se mettrait a injecter des
    entrees que le prompt ne nomme pas."""
    ctx = build_lib_context(
        "lis un as7341, affiche la temperature du dht22 sur un ecran ssd1306",
        forced_libs=[_AS7341])
    approx_tokens = len(ctx) // 4
    assert approx_tokens < 2400, f"{approx_tokens} tokens (mesuré : 1810)"
    # Et les deux puces nommees sont bien la (sinon le budget serait tenu par
    # un rattrapage qui ne rattrape rien).
    assert "DHT.h" in ctx and "SSD1306" in ctx


def test_the_rescue_never_injects_a_chip_the_prompt_does_not_name():
    """La seule facon dont le budget ci-dessus pourrait deraper : ramener des
    entrees non nommees. On le verifie sur le corpus ENTIER plutot que sur un
    plafond de taille — c'est la propriete, la taille n'en est que le symptome."""
    prompt = "lis un as7341 et affiche la temperature du dht22"
    tokens = set(__import__("re").findall(r"[a-z0-9]+", prompt.lower()))
    for lib in named_corpus_libs(prompt):
        assert rag._signature_tokens(lib) & tokens, lib.get("id")


TESTS = [
    test_it_returns_the_entry_whose_part_number_is_written,
    test_it_returns_nothing_when_no_chip_is_named,
    test_it_sees_a_chip_named_by_a_single_word_id,
    test_it_is_empty_on_an_empty_prompt,
    test_the_named_chip_survives_the_unknown_part_suppression,
    test_the_rescue_does_not_reopen_the_semantic_retrieval,
    test_the_rescued_chip_is_authoritative_not_hedged,
    test_it_rescues_even_when_the_registry_found_nothing,
    test_nothing_named_and_nothing_forced_still_yields_an_empty_context,
    test_the_rescued_chip_is_not_duplicated,
    test_the_plain_retrieval_path_is_untouched,
    test_the_rescue_stays_within_the_measured_budget,
    test_the_rescue_never_injects_a_chip_the_prompt_does_not_name,
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
