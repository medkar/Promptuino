"""Alias serigraphie -> lookup registre (spec 2026-08-20).

Run: python scripts/test_module_alias_lookup.py
"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Importer ui.studio_view charge PyQt6 : il faut une QApplication vivante,
# meme si aucun widget n'est construit ici (motif de test_chip_swap_regen.py).
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)


def _bare_view():
    """Vue sans __init__ : _registry_request n'a besoin que de ces deux tables.

    Elles sont REECRITES a chaque appel (cf. sa docstring), donc les
    initialiser a vide reproduit fidelement l'etat d'une vue reelle.
    """
    from ui import studio_view
    view = studio_view.StudioView.__new__(studio_view.StudioView)
    view._registry_aliases = {}
    view._registry_search_queries = {}
    return view


def _no_stored_preferences():
    """Vide les deux magasins de preferences EN MEMOIRE.

    `preferred_lib_for` lit `declared_components` puis `component_libs`, tous
    deux avec un registre memoire rempli au demarrage de l'app. Sans ce
    nettoyage, un test dependrait du component-libs.json de la machine.
    """
    from ui import component_libs, declared_components
    component_libs.set_registry({})
    declared_components.set_registry([])


def test_registry_request_adds_module_chip_token():
    """Un module dont la puce est lib_name-only ajoute LA PUCE aux tokens.

    Le token est l'IDENTITE (cle de cache, id d'entree corpus, nom de fiche,
    {part} affiche) ; le nom de bibliotheque n'est qu'une requete de
    recherche. Les confondre faisait dire a la banniere « reconnu comme
    ADAFRUIT BMP085 LIBRARY » (revue du 2026-08-20).
    """
    from ui import studio_view
    from ui import hardware_modules

    calls = {}
    _no_stored_preferences()

    def fake_chips(prompt, modules=None):
        calls["prompt"] = prompt
        return [("Adafruit TCA9548A Library", "tca9548a", "hw-617")]

    original = hardware_modules.module_chips_needing_lookup
    hardware_modules.module_chips_needing_lookup = fake_chips
    try:
        view = _bare_view()
        unknown, preferred, declared = \
            studio_view.StudioView._registry_request(view, "j'ai un HW-617")
    finally:
        hardware_modules.module_chips_needing_lookup = original

    assert "tca9548a" in unknown, unknown
    assert "adafruit tca9548a library" not in unknown, unknown
    assert preferred.get("tca9548a") == "Adafruit TCA9548A Library", preferred
    assert view._registry_search_queries.get("tca9548a") == \
        "Adafruit TCA9548A Library", view._registry_search_queries
    assert view._registry_aliases.get("tca9548a") == "hw-617", \
        view._registry_aliases


def test_registry_request_unchanged_without_module():
    """Sans module detecte, rien ne change et les deux tables restent vides."""
    from ui import studio_view
    from ui import hardware_modules

    original = hardware_modules.module_chips_needing_lookup
    hardware_modules.module_chips_needing_lookup = lambda p, modules=None: []
    try:
        view = _bare_view()
        unknown, preferred, declared = \
            studio_view.StudioView._registry_request(view, "allume une led")
    finally:
        hardware_modules.module_chips_needing_lookup = original

    assert unknown == [], unknown
    assert view._registry_aliases == {}, view._registry_aliases
    assert view._registry_search_queries == {}, view._registry_search_queries


def test_module_token_respects_max_unknown_tokens():
    """Le budget partage n'est pas contourne par la voie module."""
    from ui import studio_view
    from ui import hardware_modules
    from ui.registry_lookup import _MAX_UNKNOWN_TOKENS

    _no_stored_preferences()
    original = hardware_modules.module_chips_needing_lookup
    hardware_modules.module_chips_needing_lookup = \
        lambda p, modules=None: [("LibA", "chipa", "hw-1"),
                                 ("LibB", "chipb", "hw-1"),
                                 ("LibC", "chipc", "hw-1")]
    try:
        view = _bare_view()
        unknown, preferred, declared = \
            studio_view.StudioView._registry_request(view, "un module")
    finally:
        hardware_modules.module_chips_needing_lookup = original

    assert len(unknown) <= _MAX_UNKNOWN_TOKENS, unknown


def test_mixed_budget_real_part_number_plus_module_chip():
    """Cas MIXTE : vrai part-number inconnu ET puce de module.

    C'est le cas que la contrainte projet revendique (« budget PARTAGE ») et
    que rien n'exercait : l'ancien test ne prouvait le partage qu'entre puces
    d'un meme module. Les deux origines doivent tenir dans le meme plafond.
    """
    from ui import studio_view
    from ui import hardware_modules
    from ui.registry_lookup import _MAX_UNKNOWN_TOKENS, \
        detect_unknown_part_tokens

    _no_stored_preferences()
    original = hardware_modules.module_chips_needing_lookup
    hardware_modules.module_chips_needing_lookup = \
        lambda p, modules=None: [("LibA", "chipa", "hw-1"),
                                 ("LibB", "chipb", "hw-1")]
    try:
        # 1 part-number inconnu + 1 puce de module = le plafond exactement.
        assert detect_unknown_part_tokens("un ZXQ9000") == ["zxq9000"]
        view = _bare_view()
        unknown, preferred, _ = studio_view.StudioView._registry_request(
            view, "un ZXQ9000 branche sur mon module")
        assert unknown == ["zxq9000", "chipa"], unknown
        assert len(unknown) <= _MAX_UNKNOWN_TOKENS, unknown
        # La seconde puce est SACRIFIEE, pas le part-number de l'utilisateur.
        assert "chipb" not in unknown, unknown
        assert view._registry_search_queries == {"chipa": "LibA"}, \
            view._registry_search_queries

        # 2 part-numbers inconnus saturent deja : la voie module n'ajoute rien
        # et n'ecrit aucun alias (sinon la banniere parlerait d'une puce que
        # personne n'a cherchee).
        view = _bare_view()
        unknown, preferred, _ = studio_view.StudioView._registry_request(
            view, "un ZXQ9000 et un WQP4242 sur mon module")
        assert len(unknown) <= _MAX_UNKNOWN_TOKENS, unknown
        assert "chipa" not in unknown and "chipb" not in unknown, unknown
        assert view._registry_aliases == {}, view._registry_aliases
    finally:
        hardware_modules.module_chips_needing_lookup = original


def test_user_library_preference_wins_over_module_lib_name():
    """I1 : « Changer de bibliotheque » doit survivre a une regeneration.

    `_preferred_libs_for_tokens` tourne AVANT que le token de module existe,
    donc la preference de l'utilisateur etait reecrasee sans condition a
    chaque generation -- et `_preference_was_overridden` annoncait ensuite que
    sa librairie etait « introuvable au registre », ce que rien n'avait
    verifie.
    """
    from ui import studio_view
    from ui import hardware_modules
    from ui import component_libs, declared_components

    original = hardware_modules.module_chips_needing_lookup
    hardware_modules.module_chips_needing_lookup = \
        lambda p, modules=None: [("Adafruit BMP085 Library", "bmp085",
                                  "gy-80")]
    declared_components.set_registry([])
    component_libs.set_registry({"bmp085": "SparkFun BMP180"})
    try:
        view = _bare_view()
        unknown, preferred, _ = studio_view.StudioView._registry_request(
            view, "mon GY-80")
        assert preferred.get("bmp085") == "SparkFun BMP180", preferred
        # La requete de recherche, elle, reste le nom VERIFIE : c'est ce qui
        # ramene la famille de libs de cette puce.
        assert view._registry_search_queries.get("bmp085") == \
            "Adafruit BMP085 Library", view._registry_search_queries
    finally:
        hardware_modules.module_chips_needing_lookup = original
        component_libs.set_registry({})


def test_lookup_component_search_query_defaults_to_token():
    """Le nouveau parametre ne change rien pour les appelants existants."""
    from ui import registry_lookup

    seen = []

    def fake_search(query, config_file):
        seen.append(query)
        return [], ""

    orig_search = registry_lookup._search_registry
    registry_lookup.set_cache_for_tests({})
    registry_lookup._search_registry = fake_search
    try:
        # Sans search_query -> on cherche le token lui-meme.
        r = registry_lookup.lookup_component("as7341", "cfg")
        assert seen == ["as7341"], seen
        assert r.token == "as7341", r.token
        # Avec search_query -> on cherche la requete, l'IDENTITE ne bouge pas.
        seen.clear()
        r = registry_lookup.lookup_component(
            "bmp085", "cfg", search_query="Adafruit BMP085 Library")
        assert seen == ["Adafruit BMP085 Library"], seen
        assert r.token == "bmp085", r.token
    finally:
        registry_lookup._search_registry = orig_search
        registry_lookup.set_cache_for_tests(None)


def test_lookup_result_identity_is_the_chip_not_the_library():
    """L'entree corpus ad hoc et la cle de cache portent l'identite PUCE.

    Le token est l'`id` de l'entree injectee au modele, la cle du cache et le
    nom de la fiche de l'onglet « Composants ». Avec le nom de bibliotheque,
    la fiche devinee « Adafruit Bmp085 Library » ne se dedoublonnait pas avec
    la fiche curee « BMP085 » (_dedup_key replie sur adafruitbmp085library).
    """
    from ui import registry_lookup
    from ui import arduino_cli

    put = {}

    def fake_search(query, config_file):
        return [{"name": "Adafruit BMP085 Library",
                 "latest": {"author": "Adafruit", "sentence": "BMP085 driver",
                            "paragraph": ""}}], ""

    orig_search = registry_lookup._search_registry
    orig_run = arduino_cli._run
    orig_installed = arduino_cli._installed_libs
    orig_put = registry_lookup._cache_put
    registry_lookup.set_cache_for_tests({})
    registry_lookup._search_registry = fake_search
    arduino_cli._run = lambda cmd, **kw: (0, "")
    arduino_cli._installed_libs = lambda cfg: {
        "Adafruit BMP085 Library": {"install_dir": str(ROOT / "scripts"),
                                    "headers": ["Adafruit_BMP085.h"]}}
    registry_lookup._cache_put = \
        lambda token, lib, entry, alts: put.update({"token": token})
    try:
        r = registry_lookup.lookup_component(
            "bmp085", "cfg", search_query="Adafruit BMP085 Library")
    finally:
        registry_lookup._search_registry = orig_search
        arduino_cli._run = orig_run
        arduino_cli._installed_libs = orig_installed
        registry_lookup._cache_put = orig_put
        registry_lookup.set_cache_for_tests(None)

    assert r.status == "found", (r.status, r.log)
    assert r.lib_name == "Adafruit BMP085 Library", r.lib_name
    assert r.entry["id"] == "bmp085", r.entry
    assert r.entry["keywords"] == ["bmp085"], r.entry
    assert put.get("token") == "bmp085", put


def test_unavailable_module_chip_is_not_reported_as_unknown():
    """C3 : « pas cherche » ne doit jamais se lire « pas trouve ».

    Sans carte selectionnee (ou sans arduino-cli), `lookup_component` rend
    « unavailable ». Le classer dans `missing` injectait la directive UNKNOWN
    COMPONENT pour une puce parfaitement connue et affichait « aucune
    librairie trouvee au registre » alors que rien n'avait ete cherche.
    """
    from ui import studio_view
    from ui.registry_lookup import RegistryLookupResult

    class _Banner:
        def __init__(self):
            self.body = None

        def show_nudge(self, body, action="", second=""):
            self.body = body

    view = studio_view.StudioView.__new__(studio_view.StudioView)
    view._registry_aliases = {"bmp085": "gy-80"}
    view._on_rag_status = lambda line: None
    view._registry_banner = _Banner()
    res = [RegistryLookupResult(token="bmp085", status="unavailable")]
    forced, directive = studio_view.StudioView._apply_registry_results(
        view, ["something"], res, "")

    assert directive == "", directive
    assert view._registry_unknown == [], view._registry_unknown
    assert view._registry_banner.body, "la banniere doit dire ce qui s'est passe"
    body = view._registry_banner.body
    assert "GY-80" in body and "BMP085" in body, body


def test_unavailable_without_alias_is_untouched():
    """Le classement `unavailable` -> `missing` des AUTRES chemins ne bouge pas.

    Le correctif C3 est borne aux tokens de module : un vrai part-number qui
    n'a pas pu etre cherche garde le comportement anterieur (hors perimetre).
    """
    from ui import studio_view
    from ui.registry_lookup import RegistryLookupResult

    class _Banner:
        def show_nudge(self, body, action="", second=""):
            self.body = body

    view = studio_view.StudioView.__new__(studio_view.StudioView)
    view._registry_aliases = {}
    view._on_rag_status = lambda line: None
    view._registry_banner = _Banner()
    res = [RegistryLookupResult(token="zxq9000", status="unavailable")]
    forced, directive = studio_view.StudioView._apply_registry_results(
        view, ["something"], res, "")

    assert "zxq9000" in directive, directive
    assert view._registry_unknown == ["ZXQ9000"], view._registry_unknown


def test_module_banner_keys_exist_in_all_languages():
    from ui.i18n import TRANSLATIONS
    keys = ("registry_module_lib_found",
            "registry_module_lib_not_found",
            "registry_module_install_failed",
            "registry_module_lib_unavailable")
    for code, s in TRANSLATIONS.items():
        for k in keys:
            assert getattr(s, k, ""), f"{code}: cle '{k}' manquante/vide"


def test_module_banner_keys_name_both_alias_and_chip():
    """Le gabarit doit nommer CE QUE L'UTILISATEUR A TAPE et ce qui a ete
    cherche : sans les deux champs, la traduction passe pour ses mots."""
    from ui.i18n import TRANSLATIONS
    for code, s in TRANSLATIONS.items():
        found = getattr(s, "registry_module_lib_found", "")
        assert "{alias}" in found and "{part}" in found and "{lib}" in found, \
            f"{code}: registry_module_lib_found doit porter alias, part et lib"
        nf = getattr(s, "registry_module_lib_not_found", "")
        assert "{alias}" in nf and "{part}" in nf, \
            f"{code}: registry_module_lib_not_found doit porter alias et part"
        bad = getattr(s, "registry_module_install_failed", "")
        assert "{alias}" in bad and "{part}" in bad and "{lib}" in bad, \
            f"{code}: registry_module_install_failed doit porter alias, part et lib"
        na = getattr(s, "registry_module_lib_unavailable", "")
        assert "{alias}" in na and "{part}" in na, \
            f"{code}: registry_module_lib_unavailable doit porter alias et part"


def test_module_not_found_keeps_the_documentation_hint():
    """Meme conseil que son equivalent generique : joindre une doc aide.

    L'omission venait du plan (texte prescrit verbatim) et n'avait aucune
    raison d'etre : le conseil vaut autant quand la puce a ete nommee par
    l'alias de sa carte.
    """
    from ui.i18n import TRANSLATIONS
    hints = {"fr": ".md/.txt", "en": ".md/.txt", "es": ".md/.txt",
             "it": ".md/.txt"}
    for code, s in TRANSLATIONS.items():
        nf = getattr(s, "registry_module_lib_not_found", "")
        assert hints[code] in nf, f"{code}: {nf}"


TESTS = [test_registry_request_adds_module_chip_token,
         test_registry_request_unchanged_without_module,
         test_module_token_respects_max_unknown_tokens,
         test_mixed_budget_real_part_number_plus_module_chip,
         test_user_library_preference_wins_over_module_lib_name,
         test_lookup_component_search_query_defaults_to_token,
         test_lookup_result_identity_is_the_chip_not_the_library,
         test_unavailable_module_chip_is_not_reported_as_unknown,
         test_unavailable_without_alias_is_untouched,
         test_module_banner_keys_exist_in_all_languages,
         test_module_banner_keys_name_both_alias_and_chip,
         test_module_not_found_keeps_the_documentation_hint]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
