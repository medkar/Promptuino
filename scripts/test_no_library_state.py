"""« Ce composant ne demande AUCUNE bibliotheque » (TODO #51, 2026-08-27).

Le defaut que ce chantier supprime : l'affirmation n'etait representable dans
AUCUN des deux magasins, si bien que la card de la modale a du s'appeler
« Laisser l'app decider » -- qui veut dire l'inverse (rendre la main a la
devinette). Mesure d'origine :

  - `component_libs.load()` ECARTAIT les valeurs vides a la lecture, donc une
    preference « aucune » vivait la session puis disparaissait au redemarrage ;
  - `DeclaredComponent.lib` vide veut DEJA dire « a determiner », donc le meme
    vide ne pouvait pas dire aussi « aucune ».

⚠️ Ces tests ecrivent : ils detournent la CONSTANTE DE MODULE du chemin, jamais
un attribut d'instance -- sans quoi ils toucheraient le vrai
~/Documents/Promptuino de l'utilisateur (regle apprise a ses depens).

Run : python scripts/test_no_library_state.py
"""
from __future__ import annotations
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui import component_libs as cl
from ui import declared_components as dc
from ui.declared_components import DeclaredComponent
from ui.registry_lookup import no_library_directive, unknown_component_directive


class _Store:
    """Detourne le fichier ET la memoire, puis restaure tout."""

    def __enter__(self):
        self._dir = tempfile.TemporaryDirectory()
        self._old_path = cl._LIBRARY_PATH
        self._old_reg = cl.registry()
        self._old_loaded = cl._REGISTRY_LOADED
        self._old_declared = dc.registry()
        cl._LIBRARY_PATH = Path(self._dir.name) / "component-libs.json"
        cl.set_registry({})
        dc.set_registry([])
        return self

    def __exit__(self, *a):
        cl._LIBRARY_PATH = self._old_path
        cl.set_registry(self._old_reg)
        cl._REGISTRY_LOADED = self._old_loaded
        dc.set_registry(self._old_declared)
        self._dir.cleanup()
        return False

    def raw(self) -> dict:
        return json.loads(cl._LIBRARY_PATH.read_text(encoding="utf-8"))

    def write_v1(self, prefs: dict) -> None:
        cl._LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        cl._LIBRARY_PATH.write_text(
            json.dumps({"version": 1, "preferences": prefs}), encoding="utf-8")


def test_the_assertion_survives_a_restart():
    """LE DEFAUT D'ORIGINE, en une assertion.

    En v1 une preference « aucune » etait un texte vide, et `load()` jetait les
    textes vides : le choix vivait la session puis disparaissait. Ici on ecrit,
    on RELIT DEPUIS LE DISQUE, et l'affirmation est toujours la."""
    with _Store() as st:
        assert cl.set_no_library("ldr") is True
        cl.set_registry({})                       # on oublie la memoire
        cl.set_registry(cl.load())                # comme au demarrage
        assert cl.declares_no_library("ldr") is True


def test_a_v1_file_is_read_and_not_thrown_away():
    """LA MIGRATION, et c'est la partie qui pouvait faire le plus de degats.

    Le controle de version v1 etait `!= _SCHEMA_VERSION` : le jour du bump, il
    aurait jete EN SILENCE toutes les preferences deja faites. La v2 accepte
    les deux versions, et un fichier v1 n'a simplement aucune affirmation."""
    with _Store() as st:
        st.write_v1({"as7341": "Adafruit AS7341"})
        prefs = cl.load()
        assert prefs == {"as7341": "Adafruit AS7341"}, prefs
        cl.set_registry(prefs)
        assert cl.preference_for("as7341") == "Adafruit AS7341"
        assert cl.declares_no_library("as7341") is False


def test_the_three_states_are_distinct():
    """ABSENTE / AUCUNE / NOMMEE ne se confondent deux a deux dans aucun sens."""
    with _Store():
        cl.set_preference("bme280", "Adafruit BME280 Library")
        cl.set_no_library("ldr")
        # nommee
        assert cl.preference_for("bme280") == "Adafruit BME280 Library"
        assert cl.declares_no_library("bme280") is False
        # aucune
        assert cl.preference_for("ldr") == ""
        assert cl.declares_no_library("ldr") is True
        # absente
        assert cl.preference_for("inconnu") == ""
        assert cl.declares_no_library("inconnu") is False


def test_the_sentinel_never_escapes_as_a_library_NAME():
    """`preference_for` alimente des recherches au registre, des affichages et
    des comparaisons de noms. Laisser la sentinelle en sortir la ferait voyager
    partout comme si c'etait un nom de bibliotheque."""
    with _Store():
        cl.set_no_library("ldr")
        assert cl.preference_for("ldr") == ""
        assert cl.preferred_lib_for("ldr") == ""
        assert cl.NO_LIBRARY not in cl.registry().values() or \
            cl.registry()["ldr"] == cl.NO_LIBRARY   # elle vit DANS le magasin
        # ... mais on ne peut pas l'y mettre en la faisant passer pour un nom
        assert cl.set_preference("autre", cl.NO_LIBRARY) is False
        assert cl.preference_for("autre") == ""


def test_naming_a_library_cancels_the_assertion_and_the_reverse():
    """Les deux gestes se contredisent, donc le dernier gagne -- sinon un
    composant porterait a la fois une bibliotheque et l'affirmation qu'il n'en
    faut aucune."""
    with _Store():
        cl.set_no_library("x")
        cl.set_preference("x", "Servo")
        assert cl.declares_no_library("x") is False
        assert cl.preference_for("x") == "Servo"
        cl.set_no_library("x")
        assert cl.declares_no_library("x") is True
        assert cl.preference_for("x") == ""


def test_clearing_is_NOT_the_same_gesture_as_asserting():
    """La distinction que la modale ne pouvait pas exprimer avant ce ticket :
    effacer rend le composant a la devinette de l'app, affirmer lui interdit
    de chercher."""
    with _Store():
        cl.set_no_library("ldr")
        cl.clear_preference("ldr")
        assert cl.declares_no_library("ldr") is False
        assert cl.preference_for("ldr") == ""


def test_the_declared_card_OWNS_its_component():
    """Meme regle de source que `preferred_lib_for` : une fiche declaree
    repond pour elle-meme, y compris pour dire NON. Les deux lecteurs doivent
    lire la meme source, sinon l'app pourrait a la fois nommer une
    bibliotheque et affirmer qu'il n'en faut aucune."""
    with _Store():
        cl.set_preference("grove moisture sensor", "Une Lib Devinee")
        dc.set_registry([DeclaredComponent(
            id="g", name="Grove Moisture Sensor", headers=(), pins=(),
            lib="", no_lib=True)])
        assert cl.no_library_for("grove moisture sensor") is True
        assert cl.preferred_lib_for("grove moisture sensor") == ""


def test_a_declared_card_without_the_flag_still_means_to_determine():
    """Non-regression du sens HISTORIQUE du vide : `lib` vide sans le drapeau
    veut toujours dire « a determiner », et ne doit pas retomber sur le
    fichier (regle anterieure, documentee dans `preferred_lib_for`)."""
    with _Store():
        cl.set_preference("machin", "Une Lib Devinee")
        dc.set_registry([DeclaredComponent(
            id="m", name="Machin", headers=(), pins=(), lib="")])
        assert cl.no_library_for("machin") is False
        assert cl.preferred_lib_for("machin") == ""


def test_the_file_round_trips_both_maps():
    with _Store() as st:
        cl.set_preference("a", "Lib A")
        cl.set_no_library("b")
        raw = st.raw()
        assert raw["version"] == 2, raw
        assert raw["preferences"] == {"a": "Lib A"}, raw
        assert raw["no_library"] == ["b"], raw


def test_a_corrupted_file_naming_a_token_twice_prefers_the_assertion():
    """Un fichier edite a la main peut mettre le meme jeton des deux cotes.
    « Aucune » gagne, parce que c'est le geste le plus recent dans tous les
    chemins qui ecrivent ici -- l'honorer ne peut donc pas ressusciter
    quelque chose de deja abandonne."""
    with _Store() as st:
        cl._LIBRARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        cl._LIBRARY_PATH.write_text(json.dumps({
            "version": 2, "preferences": {"z": "Lib Z"}, "no_library": ["z"]}),
            encoding="utf-8")
        prefs = cl.load()
        cl.set_registry(prefs)
        assert cl.declares_no_library("z") is True
        assert cl.preference_for("z") == ""


# ── Ce que le MODELE recoit ────────────────────────────────────────────────

def test_the_two_directives_say_OPPOSITE_things():
    """LA QUESTION QUE LE TICKET POSAIT, et la raison d'un second texte.

    `forced_libs=[]` etait DEJA pris par « rien trouve au registre », qui
    s'accompagne d'un aveu d'ignorance. Reutiliser cet aveu pour une
    affirmation ferait ecrire au modele du code timide pour un composant
    parfaitement maitrise."""
    aucune = no_library_directive(["ldr"]).lower()
    inconnu = unknown_component_directive(["ldr"]).lower()
    assert "no library needed" in aucune
    assert "unknown component" in inconnu
    # L'aveu d'ignorance n'a rien a faire dans l'affirmation...
    assert "unknown" not in aucune, aucune
    assert "not in any known" not in aucune, aucune
    # ... et l'affirmation dit ce qu'il FAUT faire, pas seulement quoi eviter.
    assert "core arduino functions" in aucune, aucune
    for f in ("digitalread", "analogread", "analogwrite"):
        assert f in aucune, (f, aucune)


def test_both_directives_still_forbid_borrowing_another_chip_library():
    """Le seul point commun, et il ne doit pas se perdre : c'est la panne
    silencieuse que tout ce pipeline existe pour supprimer."""
    for txt in (no_library_directive(["x"]), unknown_component_directive(["x"])):
        assert "different" in txt.lower() or "another" in txt.lower(), txt


def test_no_tokens_means_no_directive():
    assert no_library_directive([]) == ""


TESTS = [
    test_the_assertion_survives_a_restart,
    test_a_v1_file_is_read_and_not_thrown_away,
    test_the_three_states_are_distinct,
    test_the_sentinel_never_escapes_as_a_library_NAME,
    test_naming_a_library_cancels_the_assertion_and_the_reverse,
    test_clearing_is_NOT_the_same_gesture_as_asserting,
    test_the_declared_card_OWNS_its_component,
    test_a_declared_card_without_the_flag_still_means_to_determine,
    test_the_file_round_trips_both_maps,
    test_a_corrupted_file_naming_a_token_twice_prefers_the_assertion,
    test_the_two_directives_say_OPPOSITE_things,
    test_both_directives_still_forbid_borrowing_another_chip_library,
    test_no_tokens_means_no_directive,
]


def main() -> int:
    for t in TESTS:
        t()
        print(f"  OK {t.__name__}")
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
