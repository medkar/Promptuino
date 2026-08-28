"""Tests standalone pour les heuristiques chat (intent generation + off-scope).

Run : python scripts/test_chat_heuristics.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.chat.chat_heuristics import (
    is_generation_intent, is_off_scope, is_correction_intent,
)


# Intent generation FR
def test_gen_fr_fais_clignoter():
    assert is_generation_intent("fais clignoter une LED")

def test_gen_fr_ecris_moi():
    assert is_generation_intent("ecris-moi un timer non bloquant")

def test_gen_fr_code_moi():
    assert is_generation_intent("code-moi un servo qui oscille")

def test_gen_fr_genere():
    assert is_generation_intent("genere du code pour DHT11")

def test_gen_fr_cree():
    assert is_generation_intent("cree une fonction de blink")

# QA D2.3 (2026-08-08) : « ajoute … » n'etait PAS reconnu, alors qu'Ajouter est
# l'une des trois actions de l'atelier. Trou preexistant (rien a voir avec la
# garde « comment … ? »), comble a la demande.
def test_gen_fr_ajoute():
    assert is_generation_intent("ajoute une LED qui clignote")
    assert is_generation_intent("ajoute-moi un bouton")
    assert is_generation_intent("ajouter un capteur de temperature")

def test_gen_en_add():
    assert is_generation_intent("add an LED that blinks")
    assert is_generation_intent("add the servo control")

def test_gen_es_it_add():
    assert is_generation_intent("anade un LED que parpadee")
    assert is_generation_intent("añade un LED que parpadee")
    assert is_generation_intent("agrega un boton")
    assert is_generation_intent("aggiungi un LED lampeggiante")

def test_gen_add_stays_a_question_when_asked_as_one():
    # La garde « comment … ? » prime : on EXPLIQUE, on ne redirige pas.
    assert not is_generation_intent("comment ajouter une LED ?")
    assert not is_generation_intent("how do I add an LED ?")

def test_gen_en_add_needs_an_article():
    # Meme prudence que make/write : « add » nu est trop large pour ne pas
    # ramasser des phrases qui ne demandent aucun code.
    assert not is_generation_intent("add 5 to the counter value")
    assert not is_generation_intent("I get add overflow warnings")

def test_gen_fr_negative_question():
    assert not is_generation_intent("comment marche PWM ?")

def test_gen_fr_negative_explain():
    assert not is_generation_intent("explique-moi le code")

# QA D2 (2026-08-08) : une question « comment ... ? » n'est PAS une demande de
# code, meme quand elle contient un verbe de production. « comment je fais si
# l'app se trompe de composant ? » etait redirigee vers le prompt de
# generation, donc JAMAIS repondue -- et « comment je fais » est la tournure la
# plus naturelle en francais pour demander de l'aide. Le faux positif etait
# frequent, pas marginal, contrairement a ce que supposait le docstring.

def test_gen_how_to_question_is_not_a_request():
    assert not is_generation_intent(
        "comment je fais si l'app se trompe de composant ?")
    assert not is_generation_intent("comment faire clignoter une LED ?")
    assert not is_generation_intent("how do I make a LED blink?")
    assert not is_generation_intent("cómo hago para crear un sketch?")
    assert not is_generation_intent("come faccio a scrivere un programma?")

def test_gen_a_polite_request_still_redirects():
    # Garde contre la SUR-correction : « peux-tu ecrire ... ? » finit par un
    # point d'interrogation mais reste une DEMANDE. Seule l'ouverture par un
    # adverbe interrogatif fait la question -- pas la ponctuation.
    assert is_generation_intent("peux-tu ecrire un programme qui clignote ?")
    assert is_generation_intent("fais clignoter une LED")
    assert is_generation_intent("genere un sketch pour un servo")

def test_correction_how_to_question_is_not_a_request():
    # Meme cause, symptome plus doux : « comment modifier un composant faux »
    # declenchait le bouton « Corriger dans Studio » sous une reponse purement
    # informative.
    assert not is_correction_intent("comment modifier un composant faux")
    assert not is_correction_intent("how do I fix a wrong component?")
    # Mais une vraie demande de correction reste detectee.
    assert is_correction_intent("corrige le code, la LED ne clignote pas")

# Intent generation EN/ES/IT
def test_gen_en_make_blink():
    assert is_generation_intent("make an LED blink on D5")

def test_gen_en_write():
    assert is_generation_intent("write me a debounce function")

def test_gen_en_generate():
    assert is_generation_intent("generate code for a servo sweep")

def test_gen_es_escribe():
    assert is_generation_intent("escribe un timer no bloqueante")

def test_gen_es_haz():
    assert is_generation_intent("haz parpadear el LED rojo")

def test_gen_it_scrivi():
    assert is_generation_intent("scrivi un blink semplice")

def test_gen_it_fai():
    assert is_generation_intent("fai lampeggiare il LED")

# Intent generation NEGATIVES (false-positive regression tests)
def test_gen_en_make_sure_negative():
    # "make sure" must not trigger code generation intent
    assert not is_generation_intent("make sure the resistor is 220 ohms")

def test_gen_en_write_to_serial_negative():
    # "write to Serial" is an Arduino API usage question, not code gen
    assert not is_generation_intent("how do you write to Serial?")

def test_gen_en_wire_write_negative():
    # Method call mention, not gen request
    assert not is_generation_intent("Wire.write(data) is hanging")

def test_gen_en_build_error_negative():
    # Compile error question
    assert not is_generation_intent("build error in Arduino IDE")

# Off-scope detection
def test_offscope_meteo():
    assert is_off_scope("quel temps fera-t-il a Paris ?")

def test_offscope_capitale():
    assert is_off_scope("quelle est la capitale de l'Italie ?")

def test_offscope_recette():
    assert is_off_scope("donne-moi une recette de gateau")

def test_offscope_wikipedia():
    assert is_off_scope("cherche sur Wikipedia")

def test_offscope_google():
    assert is_off_scope("fais une recherche Google")

def test_offscope_netflix():
    assert is_off_scope("quel film regarder sur Netflix")

def test_offscope_film_resistor_negative():
    # Real electronic component
    assert not is_off_scope("thin film resistor characteristics")

def test_offscope_film_capacitor_negative():
    assert not is_off_scope("film capacitor vs ceramic")

# Off-scope NEGATIVES (Arduino-related = in scope)
def test_in_scope_dht11():
    assert not is_off_scope("comment marche le DHT11 ?")

def test_in_scope_servo():
    assert not is_off_scope("explique-moi le servo")

def test_in_scope_pwm():
    assert not is_off_scope("c'est quoi PWM ?")

def test_in_scope_temperature_sensor():
    assert not is_off_scope("comment lire la temperature avec ce capteur ?")

# Edge cases
def test_empty_string():
    assert not is_generation_intent("")
    assert not is_off_scope("")

def test_just_whitespace():
    assert not is_generation_intent("   \n  ")
    assert not is_off_scope("   ")


# Intent correction (sibling of is_generation_intent)
def test_correction_fr_corrige():
    assert is_correction_intent("corrige le delai du blink")

def test_correction_fr_modifie():
    assert is_correction_intent("modifie la broche de la LED en D9")

def test_correction_fr_change_mid_sentence():
    assert is_correction_intent("est-ce que tu peux changer la frequence ?")

def test_correction_fr_remplace():
    assert is_correction_intent("remplace le servo par un moteur")

def test_correction_en_fix():
    assert is_correction_intent("fix the blink rate, it's too fast")

def test_correction_en_modify():
    assert is_correction_intent("modify the pin to D6")

def test_correction_es_modifica():
    assert is_correction_intent("modifica el pin del LED")

def test_correction_it_cambia():
    assert is_correction_intent("cambia la frequenza del lampeggio")

def test_correction_case_insensitive():
    assert is_correction_intent("CORRIGE ce bug")

# Negatives (false-positive regressions)
def test_correction_neutral_question_negative():
    assert not is_correction_intent("comment marche un pull-up ?")

def test_correction_generation_only_negative():
    # "ecris-moi" is generation intent, not correction
    assert not is_correction_intent("ecris-moi un code de blink")

def test_correction_update_word_negative():
    # "update" alone is too noisy -> intentionally excluded from the lexicon
    assert not is_correction_intent("an update is available for the IDE")

def test_correction_empty_negative():
    assert not is_correction_intent("")
    assert not is_correction_intent("   \n  ")


TESTS = [
    test_gen_fr_fais_clignoter, test_gen_fr_ecris_moi, test_gen_fr_code_moi,
    test_gen_fr_genere, test_gen_fr_cree, test_gen_fr_negative_question,
    test_gen_fr_negative_explain,
    test_gen_fr_ajoute, test_gen_en_add, test_gen_es_it_add,
    test_gen_add_stays_a_question_when_asked_as_one,
    test_gen_en_add_needs_an_article,
    test_gen_how_to_question_is_not_a_request,
    test_gen_a_polite_request_still_redirects,
    test_correction_how_to_question_is_not_a_request,
    test_gen_en_make_blink, test_gen_en_write, test_gen_en_generate,
    test_gen_es_escribe, test_gen_es_haz,
    test_gen_it_scrivi, test_gen_it_fai,
    # False-positive regression tests
    test_gen_en_make_sure_negative, test_gen_en_write_to_serial_negative,
    test_gen_en_wire_write_negative, test_gen_en_build_error_negative,
    test_offscope_meteo, test_offscope_capitale, test_offscope_recette,
    test_offscope_wikipedia, test_offscope_google, test_offscope_netflix,
    test_offscope_film_resistor_negative, test_offscope_film_capacitor_negative,
    test_in_scope_dht11, test_in_scope_servo, test_in_scope_pwm,
    test_in_scope_temperature_sensor,
    test_empty_string, test_just_whitespace,
    # Intent correction
    test_correction_fr_corrige, test_correction_fr_modifie,
    test_correction_fr_change_mid_sentence, test_correction_fr_remplace,
    test_correction_en_fix, test_correction_en_modify,
    test_correction_es_modifica, test_correction_it_cambia,
    test_correction_case_insensitive,
    test_correction_neutral_question_negative,
    test_correction_generation_only_negative,
    test_correction_update_word_negative,
    test_correction_empty_negative,
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
