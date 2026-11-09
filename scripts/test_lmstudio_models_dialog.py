"""La fenetre << Modeles LM Studio >> et le bouton << Charger >> de la page
(TODO #121).

Aucun reseau, aucune ecriture de configuration : les fonctions du module pur
sont remplacees le temps de chaque test, et la page lit le modele CHOISI dans
sa liste deroulante, jamais `ai_config.lmstudio_model = ...` (qui ecrirait le
fichier de l'utilisateur).

Run: python scripts/test_lmstudio_models_dialog.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtWidgets import QApplication, QPushButton  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

import ui.lmstudio_models as lm  # noqa: E402
import ui.lmstudio_models_dialog as dlgmod  # noqa: E402
from ui.i18n import TRANSLATIONS, lang_manager  # noqa: E402

# ⛔ JAMAIS les vrais serveurs : « Charger » libere d'abord les AUTRES modeles
# (2026-11-06) -- non remplacee, cette etape dechargerait ceux de
# l'utilisateur. Remplacee pour TOUT le fichier ; `_LIBERATIONS` note les
# demandes, `_A_LIBERER` dit ce que la fausse liberation rend.
import ui.memoire_modeles as _mm  # noqa: E402
_LIBERATIONS: list = []
_A_LIBERER: list = []
_mm.liberer_autres = lambda moteur, modele, url: (
    _LIBERATIONS.append((moteur, modele)) or list(_A_LIBERER))

URL = "http://127.0.0.1:1234/v1"
_INSTALLES = [
    {"cle": "google/gemma-4-12b-qat", "taille": 7151067268, "params": "12B",
     "quant": "Q4_0", "ctx_max": 262144, "instances": []},
    {"cle": "google/gemma-4-e4b", "taille": 6326918619, "params": "7.5B",
     "quant": "Q4_K_M", "ctx_max": 131072,
     "instances": [("google/gemma-4-e4b", 32768)]},
]


class _Detour:
    """Remplace des attributs d'un module le temps d'un bloc `with`."""

    def __init__(self, module, **remplacements):
        self.module, self.remp, self.vrais = module, remplacements, {}

    def __enter__(self):
        for nom, valeur in self.remp.items():
            self.vrais[nom] = getattr(self.module, nom)
            setattr(self.module, nom, valeur)
        return self

    def __exit__(self, *a):
        for nom, valeur in self.vrais.items():
            setattr(self.module, nom, valeur)


def _attendre(condition, delai=5.0):
    fin = time.time() + delai
    while time.time() < fin:
        _APP.processEvents()
        if condition():
            return True
        time.sleep(0.02)
    return False


def _boutons(widget):
    return widget.findChildren(QPushButton)


def _fenetre(etat="ok", installes=_INSTALLES):
    with _Detour(lm, etat_api=lambda u: etat,
                 modeles_installes=lambda u: list(installes)), \
         _Detour(dlgmod, vram_totale=lambda: None):
        return dlgmod.LMStudioModelsDialog(URL)


# ── la fenetre ────────────────────────────────────────────────────────────

def test_it_builds_in_the_four_languages():
    for code in TRANSLATIONS:
        lang_manager.set_language(code)
        d = _fenetre()
        s = TRANSLATIONS[code]
        assert d.windowTitle() == s.lms_title, (code, d.windowTitle())
        assert d._lbl_suppr.text() == s.lms_delete_hint, code
    lang_manager.set_language("fr")


def test_there_is_no_delete_and_no_cancel_button():
    """L'API n'a ni l'un ni l'autre : un bouton qui ne peut rien faire
    mentirait. La suppression est EXPLIQUEE, pas proposee."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    d = _fenetre()
    textes = {b.text() for b in _boutons(d)} | {b.toolTip() for b in _boutons(d)}
    assert s.md_cancel not in textes, textes
    assert s.md_delete_tip not in textes, textes


def test_loaded_and_unloaded_models_get_the_right_gesture():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    d = _fenetre()
    textes = [b.text() for b in d._btns_geste]
    assert textes == [s.lms_load, s.lms_unload], textes


def test_an_old_lm_studio_greys_everything_and_says_why():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    d = _fenetre(etat="ancien", installes=[])
    assert not d._corps.isEnabled()
    assert d._lbl_bloquant.text() == s.lms_need_update


def test_a_silent_server_greys_everything_and_says_so():
    s = TRANSLATIONS["fr"]
    d = _fenetre(etat="muet", installes=[])
    assert not d._corps.isEnabled()
    assert d._lbl_bloquant.text() == s.ia_lmstudio_server_down


def test_a_download_shows_progress_and_says_closing_does_not_stop_it():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    d = _fenetre()
    reponses = [{"etat": "en_cours", "recu": 50, "total": 100, "debit": None,
                 "fin": None, "message": ""},
                {"etat": "termine", "recu": 100, "total": 100, "debit": None,
                 "fin": None, "message": ""}]
    appels = []

    def etat(u, job):
        appels.append(job)
        return reponses[min(len(appels) - 1, 1)]

    with _Detour(lm, demarrer=lambda u, cle: {"etat": "en_cours", "job": "j1"},
                 etat=etat, modeles_installes=lambda u: list(_INSTALLES)):
        d._lancer("google/gemma-3-1b")
        assert _attendre(lambda: len(appels) >= 1), "aucune requete d'etat"
        assert _attendre(lambda: d._barre.value() == 500), d._barre.value()
        assert d._lbl_note.text() == s.lms_keeps_running
        assert _attendre(lambda: d._lbl_detail.text() == s.md_done, 4), d._lbl_detail.text()
    assert d._lbl_note.text() == "", "la note ne vaut que pendant un telechargement"
    assert d._job is None and not d._minuterie.isActive()


def test_a_reopened_window_picks_up_the_running_download():
    """QA AV2, 2026-11-06 : fermer la fenetre pendant un telechargement puis
    la rouvrir ne montrait plus RIEN, alors que LM Studio continuait (les
    `.part` grossissaient, le job restait `downloading`). Le numero de suivi
    vivait dans la fenetre, detruite a la fermeture."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    lm._SUIVIS.clear()
    progres = {"recu": 30}

    def etat(u, job):
        assert job == "j7", job
        if progres["recu"] >= 100:
            return {"etat": "termine", "recu": 100, "total": 100, "debit": None,
                    "fin": None, "message": ""}
        return {"etat": "en_cours", "recu": progres["recu"], "total": 100,
                "debit": None, "fin": None, "message": ""}

    with _Detour(lm, demarrer=lambda u, cle: {"etat": "en_cours", "job": "j7"},
                 etat=etat, modeles_installes=lambda u: list(_INSTALLES)):
        d1 = _fenetre()
        d1._lancer("google/gemma-3-4b")
        assert _attendre(lambda: d1._barre.value() == 300), d1._barre.value()
        d1.close()
        progres["recu"] = 70
        d2 = _fenetre()
        assert not d2._zone.isHidden(), "la fenetre rouverte ne montre rien"
        assert "google/gemma-3-4b" in d2._lbl_etat.text(), d2._lbl_etat.text()
        assert d2._lbl_note.text() == s.lms_keeps_running
        assert _attendre(lambda: d2._barre.value() == 700), d2._barre.value()
        assert not any(btn.isEnabled() for *_x, btn in d2._lignes), \
            "un seul telechargement a la fois, meme apres reouverture"
        progres["recu"] = 100
        assert _attendre(lambda: d2._lbl_detail.text() == s.md_done, 4), \
            d2._lbl_detail.text()
    assert lm.suivi(URL) is None, "un telechargement fini ne doit plus etre suivi"


def test_a_download_that_finished_while_closed_is_said_finished():
    """⛔ LM Studio OUBLIE un job termine (404, mesure du 2026-11-06) : la
    premiere version annoncait « Echec » pour un telechargement REUSSI
    pendant que la fenetre etait fermee. La liste tranche — et le modele n'y
    porte pas le nom demande (google/gemma-3-4b -> gemma-3-4b-it)."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    lm._SUIVIS.clear()
    lm.suivre(URL, "google/gemma-3-4b", "j9", avant=[f["cle"] for f in _INSTALLES])
    arrive = list(_INSTALLES) + [
        {"cle": "gemma-3-4b-it", "taille": 2489757856, "params": "4B",
         "quant": "Q4_K_M", "ctx_max": 131072, "instances": []}]
    with _Detour(lm, etat=lambda u, job: {"etat": "perdu", "message": "not found"},
                 modeles_installes=lambda u: list(arrive)):
        d = _fenetre(installes=arrive)
        assert _attendre(lambda: d._lbl_detail.text() == s.md_done, 4), \
            d._lbl_detail.text()
    assert lm.suivi(URL) is None


def test_a_lost_download_that_never_arrived_says_so():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    lm._SUIVIS.clear()
    lm.suivre(URL, "google/gemma-3-4b", "j9", avant=[f["cle"] for f in _INSTALLES])
    with _Detour(lm, etat=lambda u, job: {"etat": "perdu", "message": "not found"},
                 modeles_installes=lambda u: list(_INSTALLES)):
        d = _fenetre()
        assert _attendre(lambda: d._lbl_detail.text() == s.lms_lost, 4), \
            d._lbl_detail.text()
    assert lm.suivi(URL) is None


def test_nothing_followed_means_nothing_shown():
    lm._SUIVIS.clear()
    d = _fenetre()
    assert d._zone.isHidden() and d._job is None


def test_a_model_below_the_floor_is_marked_unusable_and_cannot_be_loaded():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    petit = [{"cle": "vieux/modele-4k", "taille": 1_000_000_000, "params": "1B",
              "quant": "Q4", "ctx_max": 4096, "instances": []}]
    d = _fenetre(installes=petit + _INSTALLES)
    textes = [w.text() for w in d._inst_host.findChildren(dlgmod.QLabel)]
    assert any("vieux/modele-4k" in t and s.md_unusable_ctx.format(n=4096) in t
               for t in textes), textes
    assert not d._btns_geste[0].isEnabled(), "un modele inutilisable se charge"


def test_the_cards_memory_is_said_once_in_windows_units():
    """QA du 2026-11-06 : « 17.1 Go » sur chaque ligne se lisait comme la
    taille des modeles, et ne correspondait pas aux 16 Go de la carte."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Detour(lm, etat_api=lambda u: "ok",
                 modeles_installes=lambda u: list(_INSTALLES)), \
         _Detour(dlgmod, vram_totale=lambda: 16311 * 1024 * 1024):
        d = dlgmod.LMStudioModelsDialog(URL)
    assert d._lbl_vram.text() == s.md_vram.format(vram="16 Go"), d._lbl_vram.text()
    textes = " ".join(w.text() for w in d.findChildren(dlgmod.QLabel))
    assert "17.1" not in textes, "la memoire en milliards d'octets est revenue"


def test_a_refused_download_says_what_to_do_not_lm_studios_raw_text():
    """Depuis le 2026-11-06 (demande de l'auteur) : plus de texte brut. Un nom
    inconnu -- souvent une faute de frappe -- dit de verifier le nom."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    d = _fenetre()
    with _Detour(lm, demarrer=lambda u, cle: {"etat": "erreur",
                                              "message": "x/y not found"}):
        d._lancer("x/y")
        assert _attendre(lambda: d._lbl_detail.text() == s.dl_not_found), d._lbl_detail.text()
    assert "not found" not in d._lbl_detail.text()


def test_load_asks_the_module_and_rereads_the_list():
    lang_manager.set_language("fr")
    d = _fenetre()
    demandes = []
    from ui.ai_config import ai_config
    avant = ai_config._data.get("lmstudio_num_ctx")
    ai_config._data["lmstudio_num_ctx"] = 20480          # en memoire seulement
    try:
        with _Detour(lm, charger=lambda u, cle, ctx=None, **k: (demandes.append((cle, ctx)) or (True, "")),
                     modeles_installes=lambda u: list(_INSTALLES)):
            d._btns_geste[0].click()
            assert _attendre(lambda: demandes and not d._occupe), demandes
    finally:
        ai_config._data["lmstudio_num_ctx"] = avant
    # La taille reglee sur la page (2026-11-06), et non plus 16 384 fixes.
    assert demandes == [("google/gemma-4-12b-qat", 20480)], demandes


def test_loading_from_the_window_frees_the_others_and_says_so():
    """Decision de l'auteur (2026-11-06) : sur les deux moteurs."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    d = _fenetre()
    _LIBERATIONS.clear()
    _A_LIBERER[:] = [("llama3.1:8b", "Ollama")]
    try:
        with _Detour(lm, charger=lambda u, cle, ctx=None, **k: (True, ""),
                     modeles_installes=lambda u: list(_INSTALLES)):
            d._btns_geste[0].click()
            assert _attendre(lambda: _LIBERATIONS and not d._occupe), _LIBERATIONS
    finally:
        _A_LIBERER.clear()
    assert _LIBERATIONS == [("lmstudio", "google/gemma-4-12b-qat")], _LIBERATIONS
    assert d._lbl_libere.text() == s.mem_freed.format(liste="llama3.1:8b (Ollama)")


def test_a_refused_load_says_what_lm_studio_said():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    d = _fenetre()
    with _Detour(lm, charger=lambda u, cle, ctx=None, **k: (False, "insufficient system resources"),
                 modeles_installes=lambda u: list(_INSTALLES)):
        d._btns_geste[0].click()
        assert _attendre(lambda: not d._occupe and not d._lbl_info.isHidden())
    # Refus pour manque de memoire : la phrase courte, plus le texte brut (2026-11-06).
    assert d._lbl_info.text() == s.load_no_memory_short


# ── la page : le bouton « Charger pour Promptuino » ──────────────────────

def _page():
    from ui.ia_view import _LMStudioPage
    return _LMStudioPage()


class _SansModeleConfigure:
    """La vraie configuration, mais aucun modele LM Studio choisi. Ne sait
    que lire : rien ne peut atteindre le fichier de l'utilisateur."""
    lmstudio_model = ""

    def __init__(self, vraie):
        self._vraie = vraie

    def __getattr__(self, nom):
        return getattr(self._vraie, nom)


def _poser_etat(page, etat, modele="google/gemma-4-e4b"):
    page._model_combo.clear()
    page._model_combo.addItems([modele] if modele else [])
    page._availability_state = (etat, None)
    page._render_availability()


def test_the_load_button_appears_only_when_it_can_help():
    p = _page()
    for etat, visible in (("lmstudio_no_model", True), ("lmstudio_ctx_small", True),
                          ("lmstudio_ok", False), ("lmstudio_server_down", False)):
        _poser_etat(p, etat)
        assert (not p._btn_charger.isHidden()) == visible, (etat, visible)
    # ⚠️ Liste vide = la page se rabat sur le modele CONFIGURE. Ce test lisait
    # la vraie configuration : vert le matin, rouge l'apres-midi une fois
    # qu'un modele avait ete choisi en QA (2026-11-06). Lecture seule.
    import ui.ia_view as ia_view
    with _Detour(ia_view, ai_config=_SansModeleConfigure(ia_view.ai_config)):
        _poser_etat(p, "lmstudio_no_model", modele="")
    assert p._btn_charger.isHidden(), "sans modele choisi, rien a charger"


def test_the_page_button_loads_the_chosen_model():
    import ui.ia_view as ia_view
    p = _page()
    _poser_etat(p, "lmstudio_no_model")
    demandes = []
    avant = ia_view.ai_config._data.get("lmstudio_num_ctx")
    ia_view.ai_config._data["lmstudio_num_ctx"] = 20480   # en memoire seulement
    try:
        with _Detour(lm, etat_api=lambda u: "ok",
                     charger=lambda u, cle, ctx=None, **k: (demandes.append((cle, ctx)) or (True, ""))), \
             _Detour(p, refresh_availability=lambda: None):
            p._btn_charger.click()
            assert _attendre(lambda: demandes and not p._chargement_en_cours), demandes
    finally:
        ia_view.ai_config._data["lmstudio_num_ctx"] = avant
    assert demandes == [("google/gemma-4-e4b", 20480)], demandes
    assert p._lbl_charge_err.isHidden()
    assert ia_view._LMSTUDIO_CTX_MIN == lm.CTX_PROMPTUINO


def test_the_page_button_explains_an_old_lm_studio():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    p = _page()
    _poser_etat(p, "lmstudio_no_model")
    with _Detour(lm, etat_api=lambda u: "ancien"), \
         _Detour(p, refresh_availability=lambda: None):
        p._btn_charger.click()
        assert _attendre(lambda: not p._chargement_en_cours)
    assert p._lbl_charge_err.text() == s.lms_need_update


TESTS = [
    test_it_builds_in_the_four_languages,
    test_there_is_no_delete_and_no_cancel_button,
    test_loaded_and_unloaded_models_get_the_right_gesture,
    test_an_old_lm_studio_greys_everything_and_says_why,
    test_a_silent_server_greys_everything_and_says_so,
    test_a_download_shows_progress_and_says_closing_does_not_stop_it,
    test_a_reopened_window_picks_up_the_running_download,
    test_a_download_that_finished_while_closed_is_said_finished,
    test_a_lost_download_that_never_arrived_says_so,
    test_nothing_followed_means_nothing_shown,
    test_a_model_below_the_floor_is_marked_unusable_and_cannot_be_loaded,
    test_the_cards_memory_is_said_once_in_windows_units,
    test_a_refused_download_says_what_to_do_not_lm_studios_raw_text,
    test_load_asks_the_module_and_rereads_the_list,
    test_loading_from_the_window_frees_the_others_and_says_so,
    test_a_refused_load_says_what_lm_studio_said,
    test_the_load_button_appears_only_when_it_can_help,
    test_the_page_button_loads_the_chosen_model,
    test_the_page_button_explains_an_old_lm_studio,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
        finally:
            lm._SUIVIS.clear()       # un echec ne doit pas fuir dans le suivant
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
