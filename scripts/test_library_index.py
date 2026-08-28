"""Le module pur derriere la modale de choix de bibliotheque.

Aucun Qt, aucun sous-processus, aucun disque : on donne une charge utile JSON
et on verifie les enregistrements et leur classement. C'est ce qui rend les
regles d'ordre verifiables sans ouvrir de fenetre.

Run : python scripts/test_library_index.py
"""
from __future__ import annotations
import contextlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui import library_index as li  # noqa: E402
from ui.library_index import LibraryRecord, parse_index  # noqa: E402
from ui.library_index import (  # noqa: E402
    author_rank, filter_libraries, is_retired, norm_token, supports_arch,
)


def _payload(*libs) -> str:
    return json.dumps({"libraries": list(libs)})


def _lib(name, **latest):
    return {"name": name, "latest": latest}


def test_a_normal_payload_becomes_records():
    payload = _payload(_lib(
        "Adafruit AS7341", author="Adafruit", maintainer="Adafruit <i@a.com>",
        sentence="Arduino library for the AS7341 sensors",
        paragraph="Longer text", version="1.4.1", category="Sensors",
        architectures=["*"], types=["Contributed"],
        website="https://github.com/adafruit/Adafruit_AS7341",
        dependencies=[{"name": "Adafruit BusIO"}]))
    recs = parse_index(payload)
    assert len(recs) == 1
    r = recs[0]
    assert r.name == "Adafruit AS7341"
    assert r.author == "Adafruit"
    assert r.sentence == "Arduino library for the AS7341 sensors"
    assert r.paragraph == "Longer text"
    assert r.version == "1.4.1"
    assert r.category == "Sensors"
    assert r.architectures == ("*",)
    assert r.types == ("Contributed",)
    assert r.website.endswith("Adafruit_AS7341")
    assert r.dependencies == ("Adafruit BusIO",)


def test_an_entry_without_a_name_is_dropped():
    # Un enregistrement sans nom ne pourrait ni s'afficher ni se choisir :
    # le garder produirait une card vide et selectionnable.
    recs = parse_index(_payload(_lib(""), _lib("Servo")))
    assert [r.name for r in recs] == ["Servo"]


def test_a_missing_or_malformed_latest_is_not_fatal():
    recs = parse_index(json.dumps({"libraries": [
        {"name": "Sans latest"},
        {"name": "Latest pas un dict", "latest": "bonjour"},
    ]}))
    assert [r.name for r in recs] == ["Sans latest", "Latest pas un dict"]
    assert recs[0].author == "" and recs[0].architectures == ()


def test_dependencies_that_are_not_dicts_are_skipped():
    recs = parse_index(_payload(_lib(
        "X", dependencies=["pas un dict", {"name": "Bon"}, {"pas": "de nom"}])))
    assert recs[0].dependencies == ("Bon",)


def test_a_record_can_be_built_from_a_name_alone():
    # La liste courte affiche des noms venus du cache AVANT que l'index soit
    # charge : le dataclass doit accepter le nom seul.
    r = LibraryRecord(name="Adafruit AS7341")
    assert r.name == "Adafruit AS7341"
    assert r.author == "" and r.dependencies == ()


def _rec(name, **kw):
    return LibraryRecord(name=name, **kw)


def test_norm_token_strips_everything_that_is_not_alphanumeric():
    assert norm_token("Adafruit AS7341") == "adafruitas7341"
    assert norm_token("  DFRobot_AS7341 ") == "dfrobotas7341"
    assert norm_token("") == ""


def test_author_rank_puts_established_authors_first():
    assert author_rank("Adafruit") == 0
    assert author_rank("SparkFun Electronics") == 1
    assert author_rank("Quelqu'un") == 5      # inconnu -> dernier


def test_the_five_match_ranks_are_ordered():
    recs = [
        _rec("Zzz description", sentence="parle de servo quelque part"),
        _rec("Yyy", author="servo maker"),
        _rec("Un servo moteur"),          # requete contenue dans le nom
        _rec("Servo etendu"),             # nom commencant par
        _rec("Servo"),                    # nom exact
    ]
    assert [r.name for r in filter_libraries(recs, "servo")] == [
        "Servo", "Servo etendu", "Un servo moteur", "Yyy", "Zzz description"]


def test_at_equal_rank_an_established_author_wins_then_the_shortest_name():
    recs = [
        _rec("Servo zzzz", author="Inconnu"),
        _rec("Servo aaaaaaaa", author="Adafruit"),
        _rec("Servo bb", author="Inconnu"),
    ]
    # Tous au rang 1 (nom commencant par « servo ») : Adafruit d'abord, puis
    # le nom le plus court.
    assert [r.name for r in filter_libraries(recs, "servo")] == [
        "Servo aaaaaaaa", "Servo bb", "Servo zzzz"]


def test_the_final_tiebreak_is_the_name_itself():
    recs = [
        _rec("Servoz", author="Inconnu"),
        _rec("Servoa", author="Inconnu"),
        _rec("Servob", author="Inconnu"),
    ]
    # Meme rang (1, nom commencant par), meme author_rank (auteur inconnu) et
    # meme longueur de nom (6) : il ne reste que le nom lui-meme pour
    # departager. Sans ce dernier critere, `sorted` (stable) retomberait sur
    # l'ordre d'entree, qui n'a aucune raison de rester le meme d'une frappe a
    # l'autre — l'affichage se reordonnerait tout seul.
    assert [r.name for r in filter_libraries(recs, "servo")] == [
        "Servoa", "Servob", "Servoz"]


def test_a_record_matching_nothing_is_excluded():
    recs = [_rec("Servo"), _rec("OLED", sentence="ecran")]
    assert [r.name for r in filter_libraries(recs, "servo")] == ["Servo"]


def test_an_empty_query_matches_nothing():
    # Le champ vide est un ETAT de la modale (liste courte), pas une recherche
    # qui rendrait les 9 824 entrees.
    assert filter_libraries([_rec("Servo")], "   ") == []


def test_filter_returns_every_match_the_cap_is_a_display_concern():
    recs = [_rec(f"Servo {i}") for i in range(200)]
    assert len(filter_libraries(recs, "servo")) == 200


def test_supports_arch_reads_what_the_registry_declares():
    assert supports_arch(_rec("X", architectures=("*",)), "avr") is True
    assert supports_arch(_rec("X", architectures=("avr",)), "avr") is True
    assert supports_arch(_rec("X", architectures=("esp32",)), "avr") is False
    assert supports_arch(_rec("X", architectures=("AVR",)), "avr") is True


def test_an_unknown_board_never_produces_a_verdict():
    # Regle d'honnetete : sans carte selectionnee on ne revendique RIEN. Rendre
    # False ici afficherait « incompatible » sur une ignorance.
    assert supports_arch(_rec("X", architectures=("esp32",)), "") is True
    assert supports_arch(_rec("X", architectures=()), "avr") is True


def test_is_retired_reads_the_registry_type():
    assert is_retired(_rec("X", types=("Retired",))) is True
    assert is_retired(_rec("X", types=("retired",))) is True
    assert is_retired(_rec("X", types=("Contributed",))) is False
    assert is_retired(_rec("X")) is False


@contextlib.contextmanager
def _fake_cli(ret=0, out="", available=True, raises=None):
    """Detourne arduino_cli au niveau MODULE (jamais un attribut d'instance) —
    meme technique que scripts/test_unknown_component_registry.py."""
    from ui import arduino_cli
    import ui.registry_lookup as rl
    old_run, old_avail = arduino_cli._run, arduino_cli.is_available
    calls = []

    def fake_run(cmd, *a, **k):
        calls.append(list(cmd))
        if raises is not None:
            raise raises
        return ret, out

    arduino_cli._run = fake_run
    arduino_cli.is_available = lambda: available
    try:
        yield rl, calls
    finally:
        arduino_cli._run, arduino_cli.is_available = old_run, old_avail


def test_fetch_index_asks_for_the_light_payload():
    with _fake_cli(out='{"libraries": []}') as (rl, calls):
        rl.fetch_library_index("dummy.yaml")
    # --omit-releases-details divise la charge utile par six (11,9 Mo contre
    # 70,6 Mo, mesure 2026-08-12) : son absence n'est pas cosmetique.
    assert "--omit-releases-details" in calls[0]
    # Aucune requete positionnelle : arduino-cli sort en erreur sur une chaine
    # vide passee en argument.
    assert "search" == calls[0][2] and calls[0][3].startswith("--")


def test_fetch_index_returns_empty_when_the_cli_is_unavailable():
    with _fake_cli(available=False) as (rl, calls):
        assert rl.fetch_library_index("dummy.yaml") == ""
    assert calls == []


def test_fetch_index_returns_empty_without_a_config_file():
    with _fake_cli() as (rl, calls):
        assert rl.fetch_library_index(None) == ""
    assert calls == []


def test_fetch_index_returns_empty_on_non_zero_exit():
    with _fake_cli(ret=1, out="boom") as (rl, _):
        assert rl.fetch_library_index("dummy.yaml") == ""


def test_fetch_index_survives_a_timeout():
    import subprocess
    with _fake_cli(raises=subprocess.TimeoutExpired("cmd", 180)) as (rl, _):
        assert rl.fetch_library_index("dummy.yaml") == ""


def test_the_index_starts_empty_and_says_so():
    li.set_index([])
    li._LOADED = False           # etat d'un processus qui vient de demarrer
    assert li.index() == []
    assert li.is_loaded() is False


def test_setting_the_index_marks_it_loaded():
    li.set_index([_rec("Servo")])
    assert li.is_loaded() is True
    assert [r.name for r in li.index()] == ["Servo"]


def test_an_empty_index_can_still_be_loaded():
    # Un registre vide est un RESULTAT (aucune lib trouvee), pas un « pas
    # encore charge » : confondre les deux relancerait le chargement en boucle.
    li.set_index([])
    assert li.is_loaded() is True


def test_callers_cannot_mutate_the_stored_index():
    li.set_index([_rec("Servo")])
    got = li.index()
    got.append(_rec("Intrus"))
    assert [r.name for r in li.index()] == ["Servo"]


def test_parse_index_survives_output_that_is_not_json():
    assert parse_index("bonjour") == []


def test_parse_index_survives_a_libraries_field_that_is_not_a_list():
    assert parse_index(json.dumps({"libraries": "pas une liste"})) == []


def test_parse_index_survives_a_missing_libraries_field():
    assert parse_index(json.dumps({"autre": 1})) == []


def test_parse_index_drops_entries_that_are_not_dicts():
    payload = json.dumps({"libraries": ["chaine", 42, _lib("Servo")]})
    assert [r.name for r in parse_index(payload)] == ["Servo"]


def test_parse_index_survives_an_empty_payload():
    assert parse_index("") == []


TESTS = [
    test_a_normal_payload_becomes_records,
    test_an_entry_without_a_name_is_dropped,
    test_a_missing_or_malformed_latest_is_not_fatal,
    test_dependencies_that_are_not_dicts_are_skipped,
    test_a_record_can_be_built_from_a_name_alone,
    test_norm_token_strips_everything_that_is_not_alphanumeric,
    test_author_rank_puts_established_authors_first,
    test_the_five_match_ranks_are_ordered,
    test_at_equal_rank_an_established_author_wins_then_the_shortest_name,
    test_the_final_tiebreak_is_the_name_itself,
    test_a_record_matching_nothing_is_excluded,
    test_parse_index_survives_output_that_is_not_json,
    test_parse_index_survives_a_libraries_field_that_is_not_a_list,
    test_parse_index_survives_a_missing_libraries_field,
    test_parse_index_drops_entries_that_are_not_dicts,
    test_parse_index_survives_an_empty_payload,
    test_an_empty_query_matches_nothing,
    test_filter_returns_every_match_the_cap_is_a_display_concern,
    test_supports_arch_reads_what_the_registry_declares,
    test_an_unknown_board_never_produces_a_verdict,
    test_is_retired_reads_the_registry_type,
    test_fetch_index_asks_for_the_light_payload,
    test_fetch_index_returns_empty_when_the_cli_is_unavailable,
    test_fetch_index_returns_empty_without_a_config_file,
    test_fetch_index_returns_empty_on_non_zero_exit,
    test_fetch_index_survives_a_timeout,
    test_the_index_starts_empty_and_says_so,
    test_setting_the_index_marks_it_loaded,
    test_an_empty_index_can_still_be_loaded,
    test_callers_cannot_mutate_the_stored_index,
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
