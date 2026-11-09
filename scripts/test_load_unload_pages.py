"""Charger / Decharger depuis les pages Ollama et LM Studio (2026-11-06).

Demande de l'auteur en QA AV1 : la page LM Studio offrait « Charger pour
Promptuino » mais pas « Decharger », et la page Ollama n'offrait ni l'un ni
l'autre. Voulu : le comportement le plus proche possible sur les deux.

La seule difference voulue est la COULEUR du « pas charge » : rouge chez
LM Studio (une generation y ECHOUE, mesure du 2026-11-04), gris chez Ollama
(il charge seul a la premiere demande, juste plus lentement).

Aucun reseau : les fonctions des modules sont remplacees le temps de chaque
test, et rien n'ecrit la configuration de l'utilisateur.

Run: python scripts/test_load_unload_pages.py
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

from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

import ui.ia_view as ia_view  # noqa: E402
import ui.lmstudio_models as lm  # noqa: E402
import ui.ollama_models as om  # noqa: E402
import ui.ai_backends.ollama_backend as ob  # noqa: E402
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

# Ni PowerShell ni journal reel : la verification du debordement de LM Studio
# (WMI + main.log) est neutralisee pour tout le fichier ; les tests qui en
# parlent la remplacent eux-memes.
import ui.debordement as _db  # noqa: E402
_db.lmstudio_deborde = lambda ctx: None

# Ni `/api/show` reel : ce que le modele permet en matiere de reflexion
# (TODO #123) est sans objet ici.
om.reflexion_modele = lambda nom: None


class _Detour:
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


# ── Ollama ────────────────────────────────────────────────────────────────

from ui.ai_config import ai_config  # noqa: E402


class _Reglages:
    """Les tailles de contexte fixees EN MEMOIRE : ces tests ne dependent ni
    de la configuration de l'utilisateur ni ne l'ecrivent."""

    def __init__(self, ollama=16384, lmstudio=16384):
        self.v = {"ollama_num_ctx": ollama, "lmstudio_num_ctx": lmstudio}
        self.avant = {}

    def __enter__(self):
        for k, v in self.v.items():
            self.avant[k] = ai_config._data.get(k)
            ai_config._data[k] = v

    def __exit__(self, *a):
        ai_config._data.update(self.avant)


def _ollama(memoire, *, serveur=True, modele_la=True, ctx_max=131072):
    """La section Ollama, sans reseau : serveur, modele et memoire au choix."""
    with _Detour(ia_view, is_server_running=lambda: serveur,
                 is_model_available=lambda m: modele_la,
                 is_installed=lambda: True, is_process_running=lambda: False,
                 list_local_models=lambda: ["gemma4:e2b"]), \
         _Detour(om, en_memoire=lambda nom: memoire,
                 contexte_max=lambda nom: ctx_max):
        sec = ia_view._BackendSection("ollama")
        sec._model_combo.clear()
        sec._model_combo.addItems(["gemma4:e2b"])
        sec.refresh_availability()
    return sec


def _visibles(sec):
    return (not sec._btn_charger_mem.isHidden(), not sec._btn_decharger_mem.isHidden())


def test_ollama_not_loaded_is_grey_and_offers_to_load():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages():
        sec = _ollama({"charge": False, "ctx": None})
    assert not sec._lbl_memoire.isHidden()
    assert sec._lbl_memoire.text() == s.om_not_loaded
    assert _visibles(sec) == (True, False)
    assert sec._btn_charger_mem.text() == s.lms_load_for_app


def test_ollama_loaded_at_the_setting_offers_to_unload():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages(ollama=16384):
        sec = _ollama({"charge": True, "ctx": 16384})
        assert sec._lbl_memoire.text() == s.om_loaded.format(n=16384)
        assert _visibles(sec) == (False, True)
        sec2 = _ollama({"charge": True, "ctx": None})
        assert sec2._lbl_memoire.text() == s.om_loaded_unknown, "on n'invente pas"


def test_ollama_loaded_at_another_size_offers_to_reload():
    """Decision du 2026-11-06 : la meme mecanique que LM Studio -- l'etat,
    puis « Recharger » et « Decharger »."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages(ollama=32768):
        sec = _ollama({"charge": True, "ctx": 16384})
        assert sec._lbl_memoire.text() == s.ctx_differs.format(charge=16384, voulu=32768)
        assert _visibles(sec) == (True, True)
        assert sec._btn_charger_mem.text() == s.ctx_reload


def test_ollama_says_nothing_when_it_cannot_know():
    """Serveur arrete, modele absent, ou `/api/ps` muet : aucune ligne."""
    with _Reglages():
        for sec in (_ollama({"charge": False, "ctx": None}, serveur=False),
                    _ollama({"charge": False, "ctx": None}, modele_la=False),
                    _ollama(None)):
            assert sec._lbl_memoire.isHidden() and _visibles(sec) == (False, False)


def test_a_model_below_the_floor_is_unusable_and_says_why():
    """Decision de l'auteur : INUTILISABLE, en precisant que c'est son
    contexte qui est trop petit. Ni ligne memoire, ni curseur actif."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages():
        sec = _ollama({"charge": False, "ctx": None}, ctx_max=8192)
    assert sec._availability_state == ("ollama_ctx_too_small", "8192")
    assert s.ctx_unusable.format(n="8192", min=16384) in sec._lbl_availability.text()
    assert sec._lbl_memoire.isHidden() and not sec._ctx._slider.isEnabled()


def test_ollama_loads_at_the_generation_context():
    """⛔ Mesure : un autre `num_ctx` RECHARGE le modele. Le bouton doit donc
    charger au contexte que la generation demandera -- la meme methode."""
    with _Reglages():
        sec = _ollama({"charge": False, "ctx": None})
    demandes = []

    class _Backend:
        def __init__(self, modele):
            self.modele = modele

        def generation_context(self):
            return 6144

    with _Detour(om, charger=lambda nom, ctx, **k: (demandes.append((nom, ctx)) or (True, ""))), \
         _Detour(ob, OllamaBackend=_Backend), \
         _Detour(sec, refresh_availability=lambda: None):
        sec._btn_charger_mem.click()
        assert _attendre(lambda: demandes and not sec._geste_en_cours), demandes
    assert demandes == [("gemma4:e2b", 6144)], demandes
    assert sec._lbl_memoire_err.isHidden()


def test_the_generation_context_is_the_setting_bounded_by_the_model():
    """Le curseur regle la generation ET le chat (decision du 2026-11-06)."""
    with _Reglages(ollama=65536):
        b = ob.OllamaBackend("m")
        b._show_cache = {"model_info": {"m.context_length": 131072}}
        assert b.generation_context() == b.effective_chat_context() == 65536
        b._show_cache = {"model_info": {"m.context_length": 32768}}
        assert b.generation_context() == 32768, "borne au modele"
        b._show_cache = {"model_info": {}}
        assert b.generation_context() == 65536, "maximum inconnu : le reglage"


def test_ollama_unloads_and_says_a_refusal():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages():
        sec = _ollama({"charge": True, "ctx": 16384})
    with _Detour(om, decharger=lambda nom: (False, "boom")), \
         _Detour(sec, refresh_availability=lambda: None):
        sec._btn_decharger_mem.click()
        assert _attendre(lambda: not sec._geste_en_cours)
    assert sec._lbl_memoire_err.text() == s.om_unload_failed, "jamais le texte brut"
    assert not sec._lbl_memoire_err.isHidden()


# ── LM Studio ─────────────────────────────────────────────────────────────

def _page(etat, modele="google/gemma-4-e4b", charge="16384"):
    p = ia_view._LMStudioPage()
    p._model_combo.clear()
    p._model_combo.addItems([modele])
    p._availability_state = (etat, charge)
    p._render_availability()
    return p


def test_lmstudio_offers_unload_when_the_model_is_loaded():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    for etat, visible in (("lmstudio_ok", True), ("lmstudio_ctx_small", True),
                          ("lmstudio_no_model", False),
                          ("lmstudio_server_down", False)):
        p = _page(etat)
        assert (not p._btn_decharger.isHidden()) == visible, (etat, visible)
    assert _page("lmstudio_ok")._btn_decharger.text() == s.lms_unload


def test_lmstudio_loaded_at_another_size_offers_reload_and_unload():
    """Le meme trio d'etats que la page Ollama. LM Studio arrondit au
    multiple de 256 superieur : ce n'est PAS une difference (mesure
    2026-11-06 : 20 000 demandes -> 20 224 charges)."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages(lmstudio=32768):
        p = _page("lmstudio_ok")
        p._availability_state = p._etat_charge(16384)
        p._render_availability()
        assert p._availability_state == ("lmstudio_ctx_differs", "16384")
        assert p._lbl_ctx.text() == s.ctx_differs.format(charge="16384", voulu=32768)
        assert not p._btn_charger.isHidden() and p._btn_charger.text() == s.ctx_reload
        assert not p._btn_decharger.isHidden()
        assert p._etat_charge(32768 + 255)[0] == "lmstudio_ok", "l'arrondi n'est pas un ecart"


def test_lmstudio_unload_frees_every_instance_of_the_chosen_model():
    p = _page("lmstudio_ok")
    liberees = []
    installes = [{"cle": "google/gemma-4-e4b", "taille": 1, "params": "", "quant": "",
                  "ctx_max": 131072,
                  "instances": [("google/gemma-4-e4b", 16384), ("google/gemma-4-e4b:2", 4096)]},
                 {"cle": "autre", "taille": 1, "params": "", "quant": "",
                  "ctx_max": 1, "instances": [("autre", 4096)]}]
    with _Detour(lm, etat_api=lambda u: "ok",
                 modeles_installes=lambda u: list(installes),
                 decharger=lambda u, i: (liberees.append(i) or (True, ""))), \
         _Detour(p, refresh_availability=lambda: None):
        p._btn_decharger.click()
        assert _attendre(lambda: liberees and not p._chargement_en_cours), liberees
    assert liberees == ["google/gemma-4-e4b", "google/gemma-4-e4b:2"], \
        "les AUTRES modeles ne sont jamais touches"


def test_lmstudio_unload_refusal_is_said():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    p = _page("lmstudio_ok")
    installes = [{"cle": "google/gemma-4-e4b", "taille": 1, "params": "", "quant": "",
                  "ctx_max": 1, "instances": [("google/gemma-4-e4b", 16384)]}]
    with _Detour(lm, etat_api=lambda u: "ok",
                 modeles_installes=lambda u: list(installes),
                 decharger=lambda u, i: (False, "instance busy")), \
         _Detour(p, refresh_availability=lambda: None):
        p._btn_decharger.click()
        assert _attendre(lambda: not p._chargement_en_cours)
    assert p._lbl_charge_err.text() == s.lms_unload_failed, "jamais le texte brut"


def _ordre_des_gestes(moteur_page, cliquer, charger_attr, charger_fn, module):
    """Clique, et rend l'ordre : liberation puis chargement."""
    ordre = []
    vraie = _mm.liberer_autres
    _mm.liberer_autres = lambda moteur, modele, url: (
        ordre.append(("liberer", moteur, modele))
        or [("google/gemma-4-e4b", "LM Studio")])
    try:
        with _Detour(module, **{charger_attr: lambda *a, **k: (ordre.append("charger") or charger_fn())}):
            cliquer()
            _attendre(lambda: "charger" in ordre and not moteur_page(), 5)
    finally:
        _mm.liberer_autres = vraie
    return ordre


def test_loading_on_ollama_frees_the_others_first_and_says_so():
    """Decision de l'auteur (2026-11-06) : charger un modele decharge d'abord
    les AUTRES, sur les deux moteurs -- et le dit."""
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages():
        sec = _ollama({"charge": False, "ctx": None})

    class _Backend:
        def __init__(self, modele):
            pass

        def generation_context(self):
            return 16384

    with _Detour(ob, OllamaBackend=_Backend), \
         _Detour(sec, refresh_availability=lambda: None):
        ordre = _ordre_des_gestes(lambda: sec._geste_en_cours,
                                  sec._btn_charger_mem.click, "charger",
                                  lambda: (True, ""), om)
    assert ordre == [("liberer", "ollama", "gemma4:e2b"), "charger"], ordre
    assert sec._lbl_libere.text() == s.mem_freed.format(
        liste="google/gemma-4-e4b (LM Studio)")
    assert not sec._lbl_libere.isHidden()


def test_loading_on_lm_studio_frees_the_others_first_and_says_so():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages():
        p = _page("lmstudio_no_model")
        with _Detour(lm, etat_api=lambda u: "ok"), \
             _Detour(p, refresh_availability=lambda: None):
            ordre = _ordre_des_gestes(lambda: p._chargement_en_cours,
                                      p._btn_charger.click, "charger",
                                      lambda: (True, ""), lm)
    assert ordre == [("liberer", "lmstudio", "google/gemma-4-e4b"), "charger"], ordre
    assert p._lbl_libere.text() == s.mem_freed.format(
        liste="google/gemma-4-e4b (LM Studio)")


def test_unloading_by_hand_frees_nothing_else():
    """« Decharger » reste un geste manuel, sur le seul modele choisi."""
    _LIBERATIONS.clear()
    with _Reglages():
        sec = _ollama({"charge": True, "ctx": 16384})
    with _Detour(om, decharger=lambda nom: (True, "")), \
         _Detour(sec, refresh_availability=lambda: None):
        sec._btn_decharger_mem.click()
        assert _attendre(lambda: not sec._geste_en_cours)
    assert _LIBERATIONS == [], _LIBERATIONS


# ── Branche mais lent : le modele a deborde de la carte (2026-11-06) ──────

def test_an_ollama_model_that_overflowed_is_orange_and_still_loaded():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages():
        sec = _ollama({"charge": True, "ctx": 16384, "deborde": True})
    assert s.slow_overflow in sec._lbl_availability.text()
    assert sec.etat_publie() == "ollama_slow"
    assert not sec._lbl_memoire.isHidden(), "il reste charge, et Decharger aussi"
    with _Reglages():
        sain = _ollama({"charge": True, "ctx": 16384, "deborde": False})
    assert sain.etat_publie() == "ollama_ok"
    assert s.slow_overflow not in sain._lbl_availability.text()


def test_an_lm_studio_model_that_overflowed_is_orange():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages():
        p = _page("lmstudio_ok")
        p._apres_debordement(("debordement", (p._verification, True)))
    assert s.slow_overflow in p._lbl_availability.text()
    assert p.etat_publie() == "lmstudio_slow"
    assert not p._btn_decharger.isHidden()


def test_a_stale_overflow_answer_is_ignored():
    """La verification tourne dans un fil : si la page a ete relue entre-temps,
    sa reponse parle d'un etat qui n'est plus le notre."""
    with _Reglages():
        p = _page("lmstudio_ok")
        p._apres_debordement(("debordement", (p._verification - 1, True)))
    assert p.etat_publie() == "lmstudio_ok"


def test_the_overflow_check_runs_only_for_a_loaded_model():
    demandes = []
    with _Reglages(), _Detour(_db, lmstudio_deborde=lambda ctx: demandes.append(ctx) or False):
        for etat, extra in (("lmstudio_no_model", None), ("lmstudio_server_down", None),
                            ("lmstudio_ok", "20480")):
            p = _page(etat, charge=extra)
            p._verifier_debordement()
        _attendre(lambda: demandes, 3)
    assert demandes == [20480], demandes


def test_slow_is_orange_in_the_status_bar():
    from ui.ai_status import KINDS_WARN, KINDS_OK
    assert {"ollama_slow", "lmstudio_slow"} <= KINDS_WARN
    assert not ({"ollama_slow", "lmstudio_slow"} & KINDS_OK)


def test_the_not_loaded_message_speaks_of_THIS_model():
    """QA du 2026-11-06 : deux modeles etaient charges dans LM Studio, et le
    message du troisieme disait « Aucun modele charge »."""
    for code, s in TRANSLATIONS.items():
        debut = s.ia_lmstudio_no_model_loaded.split()[0].lower()
        assert debut not in ("aucun", "no", "ningún", "nessun"), (code, debut)


def test_the_bottom_of_the_local_page_is_never_clipped():
    """⛔ Capture de l'auteur du 2026-11-06 : message rouge sur deux lignes ->
    l'aide sous le curseur coupee. La carte etait centree par `AlignHCenter`,
    et Qt calculait sa hauteur sur toute la largeur du conteneur (890 px
    annonces pour 939 necessaires)."""
    v = ia_view.IAView()
    v.resize(1200, 760)
    v.show()
    v._local.select_engine("lmstudio")
    page = v._local.pages["lmstudio"]
    for etat in (("lmstudio_no_model", None), ("lmstudio_ok", "16384")):
        page._availability_state = etat
        page._render_availability()
        _attendre(lambda: False, 0.4)
        aide = page._ctx._lbl_aide
        assert aide.height() >= aide.heightForWidth(aide.width()), \
            (etat[0], aide.height(), aide.heightForWidth(aide.width()))
    v.close()


def test_the_new_texts_exist_in_the_four_languages():
    for code, s in TRANSLATIONS.items():
        for cle in ("om_loaded", "om_loaded_unknown", "om_not_loaded", "om_load_tip",
                    "om_load_failed", "om_unload_failed",
                    "ctx_help", "ctx_unusable", "ctx_differs", "ctx_reload",
                    "md_unusable_ctx", "md_vram", "mem_freed", "slow_overflow"):
            assert getattr(s, cle).strip(), (code, cle)
        # `{err}` est RETIRE depuis le 2026-11-06 : plus de texte brut affiche.
        assert "{n}" in s.om_loaded and "{err}" not in s.om_load_failed, code


# ── Annuler un chargement en cours (2026-11-07) ───────────────────────────
# Mesure sur les vrais serveurs : couper la requete fait ABANDONNER le
# chargement (LM Studio coupe a 4 s d'un chargement de 43 s, Ollama a 2 s :
# rien de charge 45 s plus tard). Ici, un faux `charger` attend que la
# coupure soit demandee, comme le ferait la requete bloquee du serveur.

def _charger_qui_attend(vus):
    def charger(*a, coupure=None, **k):
        vus.append(coupure)
        fin = time.time() + 5
        while time.time() < fin and not (coupure and coupure.annulee):
            time.sleep(0.02)
        return (False, "") if coupure and coupure.annulee else (True, "")
    return charger


def test_cancelling_a_load_on_the_ollama_page():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages():
        sec = _ollama({"charge": False, "ctx": None})

    class _Backend:
        def __init__(self, modele):
            pass

        def generation_context(self):
            return 16384
    vus = []
    with _Detour(om, charger=_charger_qui_attend(vus)), \
         _Detour(ob, OllamaBackend=_Backend), \
         _Detour(sec, refresh_availability=lambda: None):
        sec._btn_charger_mem.click()
        assert _attendre(lambda: vus), "le chargement n'a pas demarre"
        assert sec._btn_charger_mem.text() == s.md_cancel
        assert sec._btn_charger_mem.isEnabled(), "c'est lui qui annule"
        sec._btn_charger_mem.click()                       # « Annuler »
        assert _attendre(lambda: not sec._geste_en_cours)
    assert vus[0] is not None and vus[0].annulee, "la requete n'a pas ete coupee"
    assert s.load_cancelled in sec._lbl_libere.text()
    assert sec._lbl_memoire_err.isHidden(), "annuler n'est pas une panne"


def test_cancelling_a_load_on_the_lm_studio_page():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    with _Reglages():
        p = _page("lmstudio_no_model")
    vus = []
    with _Detour(lm, etat_api=lambda u: "ok", charger=_charger_qui_attend(vus)), \
         _Detour(p, refresh_availability=lambda: None):
        p._btn_charger.click()
        assert _attendre(lambda: vus), "le chargement n'a pas demarre"
        assert p._btn_charger.text() == s.md_cancel and p._btn_charger.isEnabled()
        p._btn_charger.click()                             # « Annuler »
        assert _attendre(lambda: not p._chargement_en_cours)
    assert vus[0].annulee
    assert s.load_cancelled in p._lbl_libere.text()
    assert p._lbl_charge_err.isHidden()
    assert p._btn_charger.text() == s.lms_load_for_app


def test_a_cut_made_before_the_request_still_kills_it():
    """Annuler PENDANT la liberation des autres modeles, donc avant que la
    requete de chargement parte : la coupure unique la tue a la connexion."""
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import urllib.request
    from ui.ai_backends.coupure import Coupure

    class _Lent(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            time.sleep(5)
            self.send_response(200)
            self.end_headers()

    srv = ThreadingHTTPServer(("127.0.0.1", 0), _Lent)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        c = Coupure(unique=True)
        c.couper()                                         # AVANT la requete
        req = urllib.request.Request(
            f"http://127.0.0.1:{srv.server_address[1]}/x", data=b"{}")
        t = time.time()
        try:
            c.urlopen(req, timeout=None).read()
            leve = False
        except Exception:
            leve = True
        assert leve and time.time() - t < 2, "la requete est partie quand meme"
        # Le moteur, lui, garde l'ancienne semantique : une coupure non unique
        # ne condamne pas la requete suivante.
        assert not Coupure()._unique
    finally:
        srv.shutdown()


TESTS = [
    test_cancelling_a_load_on_the_ollama_page,
    test_cancelling_a_load_on_the_lm_studio_page,
    test_a_cut_made_before_the_request_still_kills_it,
    test_ollama_not_loaded_is_grey_and_offers_to_load,
    test_ollama_loaded_at_the_setting_offers_to_unload,
    test_ollama_loaded_at_another_size_offers_to_reload,
    test_ollama_says_nothing_when_it_cannot_know,
    test_a_model_below_the_floor_is_unusable_and_says_why,
    test_ollama_loads_at_the_generation_context,
    test_the_generation_context_is_the_setting_bounded_by_the_model,
    test_ollama_unloads_and_says_a_refusal,
    test_lmstudio_offers_unload_when_the_model_is_loaded,
    test_lmstudio_loaded_at_another_size_offers_reload_and_unload,
    test_lmstudio_unload_frees_every_instance_of_the_chosen_model,
    test_lmstudio_unload_refusal_is_said,
    test_loading_on_ollama_frees_the_others_first_and_says_so,
    test_loading_on_lm_studio_frees_the_others_first_and_says_so,
    test_unloading_by_hand_frees_nothing_else,
    test_an_ollama_model_that_overflowed_is_orange_and_still_loaded,
    test_an_lm_studio_model_that_overflowed_is_orange,
    test_a_stale_overflow_answer_is_ignored,
    test_the_overflow_check_runs_only_for_a_loaded_model,
    test_slow_is_orange_in_the_status_bar,
    test_the_not_loaded_message_speaks_of_THIS_model,
    test_the_bottom_of_the_local_page_is_never_clipped,
    test_the_new_texts_exist_in_the_four_languages,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}", flush=True)
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}", flush=True)
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
