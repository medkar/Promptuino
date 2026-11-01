"""Les puces que le projet utilise deja, injectees dans le CLASSEMENT (#64).

Sur un prompt de SUITE (<< arrondis la temperature a un chiffre apres la
virgule >>), le retrieval ne voyait que le prompt nu et injectait la
bibliotheque d'une AUTRE puce de la meme famille. `ui/project_chips.py` lit les
`#include` du sketch et en tire les numeros de piece que le corpus reconnait.

CE QUE CES TESTS VERROUILLENT, ET POURQUOI. La mecanique (extraire, aliaser,
filtrer) est la partie facile. Les deux gardes qui comptent sont ailleurs :
l'indice ne doit peser QUE sur le classement -- ni sur l'autorite de l'en-tete,
ni sur le texte envoye au modele. Coller l'indice au prompt (le reflexe) ferait
basculer 21 des 40 cas de la batterie C d'un en-tete hedge a un en-tete
imperatif, c'est-a-dire affirmer une bibliotheque que l'APP a devinee dans le
code plutot que l'utilisateur nommee. Ces deux-la ne sont pas des details
d'implementation, ce sont la decision.

Run: python scripts/test_project_chips.py
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ui.rag as rag
from ui.project_chips import chip_hint, chip_tokens_for_headers, headers_in_code

BME280 = "#include <Wire.h>\n#include <Adafruit_Sensor.h>\n#include <Adafruit_BME280.h>\nvoid setup() {}"


def test_headers_are_read_in_order_without_duplicates():
    code = "#include <Servo.h>\n#include <Wire.h>\n#include <Servo.h>"
    assert headers_in_code(code) == ["Servo.h", "Wire.h"], headers_in_code(code)


def test_a_quoted_include_is_not_a_library():
    """`#include "pitches.h"` designe un fichier du projet. L'admettre
    fabriquerait un jeton a partir du nom d'un fichier local."""
    assert headers_in_code('#include "pitches.h"') == []


def test_the_part_number_is_what_comes_out_not_the_file_name():
    """`Adafruit_BME280.h` -> `bme280`, pas `adafruit_bme280`.

    C'est le prefixe fabricant retire par `markers._header_slug`. Un jeton qui
    garderait le prefixe ne serait pas un jeton de signature du corpus, donc
    serait filtre juste apres -- l'indice serait vide et le correctif inerte."""
    assert chip_hint(BME280) == "bme280", chip_hint(BME280)


def test_a_header_that_names_another_component_is_resolved_through_the_alias():
    """`OneWire.h` et `DallasTemperature.h` designent tous deux le DS18B20.

    Aucune heuristique sur le nom de fichier ne donne ca : c'est la table
    d'alias derivee du registre (TODO #60) qui le sait. Sans elle, le projet
    DS18B20 -- celui qui portait 3 des 7 fautes -- n'aurait aucun indice."""
    code = "#include <OneWire.h>\n#include <DallasTemperature.h>"
    assert chip_hint(code) == "ds18b20", chip_hint(code)


def test_a_token_the_corpus_does_not_know_is_dropped():
    """Le filtre est ce qui separe la forme a ZERO faute de celle a quatre.

    `Wire.h` n'est le numero de piece d'aucune entree : le garder ne classerait
    rien (le boost lexical ne peut pas s'y accrocher) et deplacerait la moyenne
    de l'embedding -- exactement le defaut mesure au TODO #65."""
    assert chip_tokens_for_headers(["Wire.h"]) == []


def test_a_companion_header_never_names_a_chip():
    """LE defaut que la batterie C ne pouvait pas voir.

    `Adafruit_Sensor.h` est la base commune a toutes les libs Adafruit, et
    `SPI.h` a tout ce qui parle SPI : ni l'un ni l'autre ne prouve quoi que ce
    soit sur le materiel. La table d'alias, elle, repondait `bme280` et
    `microsd_card_module` -- un projet TSL2561 aurait recu l'indice << bme280 >>,
    la fausse puce que #64 existe precisement pour supprimer.

    Les trois projets de la batterie s'en sortaient PAR HASARD (leur compagnon
    aliasait vers la meme puce que leur en-tete proprietaire) : c'est un test
    unitaire qui l'a trouve, pas la mesure."""
    assert chip_tokens_for_headers(["Adafruit_Sensor.h"]) == []
    assert chip_tokens_for_headers(["SPI.h"]) == []
    mixte = chip_tokens_for_headers(["Adafruit_TSL2561_U.h", "Adafruit_Sensor.h"])
    assert mixte == ["tsl2561"], mixte


def test_no_code_means_no_hint():
    """Chaine vide = << ne change rien >>. C'est ce qui rend le correctif
    inoffensif a la PREMIERE generation, sans aucun test d'action."""
    assert chip_hint("") == ""
    assert chip_hint("void setup() { pinMode(13, OUTPUT); }") == ""
    assert chip_hint(None) == ""


def test_a_broken_store_returns_no_hint_instead_of_raising():
    """Un magasin casse ne doit pas empecher une generation."""
    saved = rag.corpus_signature_tokens
    rag.corpus_signature_tokens = lambda: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        assert chip_tokens_for_headers(["Adafruit_BME280.h"]) == []
    finally:
        rag.corpus_signature_tokens = saved


# ── Les deux gardes qui portent la DECISION ────────────────────────────────

def test_the_hint_does_not_make_the_header_authoritative():
    """LA garde. `prompt_names_a_chip` doit continuer de lire le texte de
    l'UTILISATEUR, jamais le texte enrichi.

    Mesure du 2026-08-26 : coller l'indice au prompt basculerait 21 des 40 cas
    de la batterie C de l'en-tete hedge a l'en-tete imperatif. Or la regle est
    categorielle -- << l'utilisateur a nomme une puce, ou pas >> -- et ici
    c'est l'app qui l'a lue dans le code."""
    if not rag._load():
        print("   (modele ONNX indisponible : garde non concluante, ignoree)")
        return
    prompt = "affiche la temperature en degres Celsius"
    hedge = rag.build_lib_context(prompt, ranking_hint="bme280")
    colle = rag.build_lib_context(prompt + "\n" + "bme280")
    assert hedge, "rien injecte : la garde ne prouverait rien"
    assert rag._HEDGED_HEADER in hedge, "l'indice a rendu l'en-tete imperatif"
    assert rag._HEDGED_HEADER not in colle, (
        "le contre-exemple ne bascule plus : la garde ne teste plus rien")


def test_the_hint_never_reaches_the_model():
    """L'indice est un signal de RECHERCHE. S'il atterrissait dans le prompt,
    le modele lirait un nom de puce que l'utilisateur n'a pas ecrit.

    ⚠️ Le prompt doit etre un qui INJECTE vraiment : une premiere redaction
    utilisait << fais clignoter une LED >>, que la garde << composant de base >>
    renvoie vide -- le test passait sans rien prouver."""
    if not rag._load():
        print("   (modele ONNX indisponible : garde non concluante, ignoree)")
        return
    out = rag.augment_user_prompt("affiche la temperature en degres Celsius",
                                  ranking_hint="ds18b20")
    assert "Relevant Arduino libraries" in out or "Possibly relevant" in out, (
        "aucun bloc injecte : la garde ne prouverait rien")
    assert "ds18b20" not in out.lower(), "l'indice a fuite dans le prompt"


def test_the_hint_defaults_to_off_for_every_existing_caller():
    """Valeur par defaut vide des deux cotes : aucun appelant existant ne
    change de comportement du seul fait que le parametre existe."""
    import inspect
    for fn in (rag.build_lib_context, rag.augment_user_prompt,
               rag._build_lib_context):
        p = inspect.signature(fn).parameters["ranking_hint"]
        assert p.default == "", (fn.__name__, p.default)


TESTS = [
    test_headers_are_read_in_order_without_duplicates,
    test_a_quoted_include_is_not_a_library,
    test_the_part_number_is_what_comes_out_not_the_file_name,
    test_a_header_that_names_another_component_is_resolved_through_the_alias,
    test_a_token_the_corpus_does_not_know_is_dropped,
    test_a_companion_header_never_names_a_chip,
    test_no_code_means_no_hint,
    test_a_broken_store_returns_no_hint_instead_of_raising,
    test_the_hint_does_not_make_the_header_authoritative,
    test_the_hint_never_reaches_the_model,
    test_the_hint_defaults_to_off_for_every_existing_caller,
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
