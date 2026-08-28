"""QA G6 (2026-08-08) : le mode n'est qu'un AFFICHAGE — le pipeline
« composant hors-corpus » doit tourner a l'identique dans les trois modes.

Le chemin DEBUTANT (`_on_generate_and_send`) n'appelait pas du tout le
registre : ni `detect_unknown_part_tokens`, ni le worker. Un debutant nommant
une puce inconnue recevait donc du code ecrit contre un `#include` INVENTE,
sans banniere ni le moindre avertissement -- et c'est le mode de ceux qui
nomment un capteur au hasard. Ca contredisait en plus l'invariant ecrit dans
CLAUDE.md : « le prompt envoye a l'IA est identique entre modes ».

Ce fichier teste la STRUCTURE du chemin (le declencheur est-il branche ?)
plutot que la generation elle-meme : il n'y a ni reseau ni backend ici.

Run : python scripts/test_registry_all_modes.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)   # ref module-level
from ui.fonts import setup_fonts
setup_fonts(_APP)

from ui import studio_view as SV
from ui.session import session

session._save = lambda: None

SRC = (ROOT / "ui" / "studio_view.py").read_text(encoding="utf-8")


def _beginner_source() -> str:
    """Source de `_on_generate_and_send` + `_continue_beginner_generation`."""
    start = SRC.index("def _on_generate_and_send")
    end = SRC.index("def _on_beg_gen_done")
    return SRC[start:end]


def test_the_beginner_path_asks_the_registry():
    body = _beginner_source()
    assert "_registry_request" in body, (
        "le chemin debutant n'interroge pas le registre -- une puce "
        "hors-corpus y passerait sans recherche ni banniere")
    assert "RegistryLookupWorker" in body, (
        "la recherche doit passer par le worker : l'installation est reseau")


def test_the_beginner_path_aborts_on_a_failed_install():
    body = _beginner_source()
    assert "install_failed" in body, (
        "sans la lib telechargee il n'y a ni en-tetes reels ni exemple : "
        "livrer quand meme fait perdre du temps au debutant")


def test_the_beginner_path_forwards_what_the_lookup_produced():
    body = _beginner_source()
    assert "extra_directive=orphan_directive" in body, (
        "la consigne UNKNOWN COMPONENT doit atteindre le prompt")
    assert "declared_component_forced=declared_component_forced" in body


def test_the_trigger_is_shared_not_duplicated():
    """C'est la DUPLICATION qui avait laisse les deux chemins diverger :
    l'arbitrage vit dans un seul endroit."""
    assert SRC.count("def _registry_request") == 1
    # Les deux chemins l'appellent...
    assert SRC.count("self._registry_request(") == 2
    # ... et plus personne ne refait la detection dans son coin.
    assert SRC.count("detect_unknown_part_tokens(") == 1, (
        "un appel hors de `_registry_request` = une 3e copie qui divergera")


def test_the_registry_journal_is_not_wiped_by_the_loader():
    """`_start_gen_loader` EFFACE le journal. L'appeler apres la recherche
    emporterait les lignes « [REGISTRY] … » juste avant qu'on les lise."""
    body = _beginner_source()
    assert "if self._gen_loader_journal is None:" in body, (
        "le loader doit etre conditionnel apres la recherche registre")


def test_both_modes_agree_on_the_request():
    """Meme prompt -> meme demande au registre, quel que soit le mode."""
    v = SV.StudioView()
    seen = {}
    for mode in ("beginner", "intermediate", "advanced"):
        v._on_mode_changed(mode)
        seen[mode] = v._registry_request("lis la couleur avec un AS7341")
    assert seen["beginner"] == seen["intermediate"] == seen["advanced"], seen
    tokens, _preferred, _declared = seen["beginner"]
    assert tokens == ["as7341"], tokens


def test_a_hand_picked_library_reaches_the_generation():
    """QA I4 (2026-08-08) : une librairie choisie a la main doit atteindre le
    contexte de generation, sinon le choix est DECORATIF.

    C'est la raison pour laquelle « modifier un composant » cree une entree
    perso quelle que soit sa provenance : le declencheur « composant declare »
    porte la preference jusqu'au lookup, alors qu'une preference posee sur une
    fiche curee n'atteindrait personne -- le RAG passe par le corpus, et la
    detection de part-number exclut justement ses puces."""
    import ui.declared_components as DC
    DC.set_registry([DC.DeclaredComponent(
        id="veml7700", name="VEML7700", headers=(), pins=(),
        lib="Adafruit VEML7700 Library", keywords=("VEML7700",))])
    try:
        v = SV.StudioView()
        tokens, preferred, _declared = v._registry_request(
            "mesure la luminosite avec un VEML7700")
        assert "veml7700" in tokens, tokens
        assert preferred.get("veml7700") == "Adafruit VEML7700 Library", \
            preferred
    finally:
        DC.set_registry([])


def test_the_preference_beats_a_cache_that_disagrees():
    """... et elle bat le cache. Sans ca, la librairie corrigee a la main
    serait ignoree au profit de la devinette memorisee, et aucune UI ne permet
    de purger ce cache : la correction serait inoperante A VIE."""
    import ui.registry_lookup as RL
    RL.set_cache_for_tests({"veml7700": {
        "lib_name": "DevLab_VEML7700",
        "entry": {"id": "veml7700", "name": "DevLab_VEML7700",
                  "arduino_lib_name": "DevLab_VEML7700"},
        "alternatives": []}})
    try:
        # config_file=None : aucune recherche possible, donc si le cache
        # repondait malgre la preference on le verrait a `status == "found"`.
        res = RL.lookup_component("veml7700", None,
                                  preferred_lib="Adafruit VEML7700 Library")
        assert res.status != "found" or res.lib_name == \
            "Adafruit VEML7700 Library", (res.status, res.lib_name)
        assert any("préférence" in l or "preference" in l for l in res.log), \
            res.log
    finally:
        RL.set_cache_for_tests({})


TESTS = [
    test_the_beginner_path_asks_the_registry,
    test_the_beginner_path_aborts_on_a_failed_install,
    test_the_beginner_path_forwards_what_the_lookup_produced,
    test_the_trigger_is_shared_not_duplicated,
    test_the_registry_journal_is_not_wiped_by_the_loader,
    test_both_modes_agree_on_the_request,
    test_a_hand_picked_library_reaches_the_generation,
    test_the_preference_beats_a_cache_that_disagrees,
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
