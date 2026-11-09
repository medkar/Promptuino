"""Gerer les modeles LM Studio depuis l'app -- module pur (TODO #121).

Les reponses ci-dessous sont COPIEES des mesures faites le 2026-11-06 sur
LM Studio 0.4.27 (telechargement reel de google/gemma-3-270m, chargement a
16 384 tokens, erreurs sur identifiant et instance inconnus). Seule l'instance
chargee du Gemma 4 E4B est reconstituee : sa configuration n'avait pas ete
relevee, sa forme est celle de l'instance du 270M.

Run: python scripts/test_lmstudio_models.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.lmstudio_models as lm  # noqa: E402

URL = "http://127.0.0.1:1234/v1"      # ce que l'utilisateur configure

_LISTE = {"models": [
    {"type": "llm", "publisher": "google", "key": "google/gemma-4-12b-qat",
     "display_name": "Gemma 4 12B QAT", "quantization": {"name": "Q4_0", "bits_per_weight": 4},
     "size_bytes": 7151067268, "params_string": "12B", "loaded_instances": [],
     "max_context_length": 262144, "format": "gguf"},
    {"type": "llm", "publisher": "google", "key": "google/gemma-4-e4b",
     "quantization": {"name": "Q4_K_M", "bits_per_weight": 4},
     "size_bytes": 6330000000, "params_string": "7.5B",
     "loaded_instances": [{"id": "google/gemma-4-e4b",
                           "config": {"context_length": 4096, "parallel": 4}}],
     "max_context_length": 131072, "format": "gguf"},
    {"type": "embedding", "publisher": "nomic",
     "key": "text-embedding-nomic-embed-text-v1.5",
     "quantization": {"name": "Q4_K_M"}, "size_bytes": 84000000,
     "params_string": None, "loaded_instances": [], "max_context_length": 2048},
]}

_DEBUT = {"job_id": "job_0be5f98f4c", "status": "downloading",
          "total_size_bytes": 241474213, "started_at": "2026-11-06T10:03:40.702Z"}
# La RELANCE pendant le telechargement : meme job, mais total FAUX.
_RELANCE = {"job_id": "job_0be5f98f4c", "status": "downloading",
            "total_size_bytes": 64005, "started_at": "2026-11-06T10:03:40.702Z"}
_EN_COURS = {"job_id": "job_0be5f98f4c", "status": "downloading",
             "downloaded_bytes": 48537316, "total_size_bytes": 241474213,
             "bytes_per_second": 2928964.408934084,
             "estimated_completion": "2026-11-06T10:05:03.184Z"}
_DEBUT_SANS_ESTIMATION = {"job_id": "job_0be5f98f4c", "status": "downloading",
                          "downloaded_bytes": 0, "total_size_bytes": 241474213,
                          "bytes_per_second": 0,
                          "estimated_completion": "9999-12-31T23:59:59.999Z"}
_TERMINE = {"job_id": "job_0be5f98f4c", "downloaded_bytes": 241474213,
            "total_size_bytes": 241474213, "status": "completed",
            "completed_at": "2026-11-06T10:04:30.997Z"}
_INCONNU = {"error": {"message": "promptuino/modele-qui-nexiste-pas not found - it either "
                      "does not exist or you do not have permission to read it",
                      "type": "model_not_found"}}
_CHARGE = {"type": "llm", "instance_id": "google/gemma-3-270m",
           "load_time_seconds": 2.589, "status": "loaded"}
_TROP_GROS = {"error": {"type": "model_load_failed", "message":
              "Failed to load LLM 'google/gemma-3-270m': Error: Model loading was "
              "stopped due to insufficient system resources."}}


class _Serveur:
    """Transport bouchon : (methode, chemin) -> (statut, json). Note chaque
    appel pour que les tests verifient ce qui a ete DEMANDE."""

    def __init__(self, routes):
        self.routes = routes
        self.appels = []

    def __call__(self, methode, url, corps, timeout):
        chemin = url.split("1234", 1)[1]
        self.appels.append((methode, chemin, corps))
        rep = self.routes.get((methode, chemin))
        if rep is None:
            return 404, {"error": {"message": "route absente du bouchon"}}
        if isinstance(rep, Exception):
            raise rep
        return rep


def _muet(methode, url, corps, timeout):
    raise ConnectionRefusedError("serveur arrete")


# ── l'API v1 est-elle la ? ────────────────────────────────────────────────

def test_the_api_state_tells_old_from_silent():
    assert lm.etat_api(URL, transport=_Serveur({("GET", "/api/v1/models"): (200, _LISTE)})) == "ok"
    # LM Studio < 0.4 : le serveur repond, mais la v1 n'existe pas.
    assert lm.etat_api(URL, transport=_Serveur({})) == "ancien"
    assert lm.etat_api(URL, transport=_muet) == "muet"


def test_the_v1_root_is_found_whatever_suffix_the_user_typed():
    for saisie in ("http://127.0.0.1:1234/v1", "http://127.0.0.1:1234",
                   "http://127.0.0.1:1234/api/v0"):
        s = _Serveur({("GET", "/api/v1/models"): (200, _LISTE)})
        assert lm.etat_api(saisie, transport=s) == "ok", saisie


# ── la liste ──────────────────────────────────────────────────────────────

def test_the_installed_list_drops_embeddings_and_keeps_exact_sizes():
    fiches = lm.modeles_installes(URL, transport=_Serveur({("GET", "/api/v1/models"): (200, _LISTE)}))
    cles = [f["cle"] for f in fiches]
    assert cles == ["google/gemma-4-12b-qat", "google/gemma-4-e4b"], cles
    e4b = fiches[1]
    assert e4b["taille"] == 6330000000
    assert e4b["params"] == "7.5B" and e4b["quant"] == "Q4_K_M"
    assert e4b["ctx_max"] == 131072
    assert e4b["instances"] == [("google/gemma-4-e4b", 4096)], e4b["instances"]
    assert fiches[0]["instances"] == []


def test_a_silent_server_gives_an_empty_list_not_an_exception():
    assert lm.modeles_installes(URL, transport=_muet) == []


def test_each_card_says_what_reasoning_the_model_allows():
    """`capabilities.reasoning.allowed_options`, recopie de LM Studio 0.4
    (2026-11-06). Pas de cle `reasoning` = le modele ne reflechit pas ; pas
    de `capabilities` du tout = on ne sait pas (TODO #123)."""
    liste = {"models": [
        {"type": "llm", "key": "google/gemma-4-12b-qat", "loaded_instances": [],
         "capabilities": {"vision": True, "trained_for_tool_use": True,
                          "reasoning": {"allowed_options": ["off", "on"], "default": "on"}}},
        {"type": "llm", "key": "microsoft/phi-4-mini-reasoning", "loaded_instances": [],
         "capabilities": {"vision": False, "trained_for_tool_use": False,
                          "reasoning": {"allowed_options": ["on"], "default": "on"}}},
        {"type": "llm", "key": "qwen/qwen3-4b-2507", "loaded_instances": [],
         "capabilities": {"vision": False, "trained_for_tool_use": True}},
        {"type": "llm", "key": "zz/ancien", "loaded_instances": []},
    ]}
    fiches = {f["cle"]: f for f in lm.modeles_installes(
        URL, transport=_Serveur({("GET", "/api/v1/models"): (200, liste)}))}
    assert fiches["google/gemma-4-12b-qat"]["reflexion"] == ("off", "on")
    assert fiches["microsoft/phi-4-mini-reasoning"]["reflexion"] == ("on",)
    assert fiches["qwen/qwen3-4b-2507"]["reflexion"] == ()
    assert fiches["zz/ancien"]["reflexion"] is None


# ── le telechargement ─────────────────────────────────────────────────────

def test_starting_a_download_returns_the_job_and_NO_total():
    """⛔ Le total de la reponse de demarrage est faux quand c'est une relance
    (64 005 octets mesures pour 241 474 213) : le module ne le rend jamais."""
    for rep in (_DEBUT, _RELANCE):
        s = _Serveur({("POST", "/api/v1/models/download"): (200, rep)})
        r = lm.demarrer(URL, "google/gemma-3-270m", transport=s)
        assert r == {"etat": "en_cours", "job": "job_0be5f98f4c"}, r
        assert s.appels[0][2] == {"model": "google/gemma-3-270m"}


def test_an_installed_model_is_said_so_without_a_job():
    s = _Serveur({("POST", "/api/v1/models/download"): (200, {"status": "already_downloaded"})})
    assert lm.demarrer(URL, "google/gemma-4-e4b", transport=s) == {"etat": "deja_la"}


def test_an_unknown_model_carries_lm_studios_own_message():
    s = _Serveur({("POST", "/api/v1/models/download"): (404, _INCONNU)})
    r = lm.demarrer(URL, "promptuino/modele-qui-nexiste-pas", transport=s)
    assert r["etat"] == "erreur", r
    assert "not found" in r["message"], r


def test_starting_with_a_silent_server_says_silent():
    assert lm.demarrer(URL, "x/y", transport=_muet) == {"etat": "muet"}


def test_progress_reads_bytes_speed_and_end():
    s = _Serveur({("GET", "/api/v1/models/download/status/job_0be5f98f4c"): (200, _EN_COURS)})
    r = lm.etat(URL, "job_0be5f98f4c", transport=s)
    assert r["etat"] == "en_cours"
    assert r["recu"] == 48537316 and r["total"] == 241474213
    assert round(r["debit"]) == 2928964
    assert r["fin"] == "2026-11-06T10:05:03.184Z"


def test_the_sentinel_end_date_and_zero_speed_mean_unknown():
    """LM Studio ecrit 9999-12-31 quand il ne sait pas : l'afficher dirait
    << fin dans 7 973 ans >>."""
    s = _Serveur({("GET", "/api/v1/models/download/status/job_0be5f98f4c"): (200, _DEBUT_SANS_ESTIMATION)})
    r = lm.etat(URL, "job_0be5f98f4c", transport=s)
    assert r["fin"] is None and r["debit"] is None, r


def test_a_finished_job_says_finished():
    s = _Serveur({("GET", "/api/v1/models/download/status/job_0be5f98f4c"): (200, _TERMINE)})
    r = lm.etat(URL, "job_0be5f98f4c", transport=s)
    assert r["etat"] == "termine" and r["recu"] == r["total"] == 241474213


def test_a_failed_job_is_an_error_even_without_a_message():
    s = _Serveur({("GET", "/api/v1/models/download/status/j"): (200, {"job_id": "j", "status": "failed"})})
    r = lm.etat(URL, "j", transport=s)
    assert r["etat"] == "echec", r
    assert r["message"] == "", r


def test_a_job_lm_studio_forgot_is_lost_not_failed():
    """⛔ Mesure du 2026-11-06 (QA AV2) : un job TERMINE disparait — 404
    `job_not_found` quelques minutes apres la fin. Le dire « echec »
    annoncait un echec pour un telechargement reussi pendant que la fenetre
    etait fermee. Seule la liste des installes peut trancher."""
    s = _Serveur({("GET", "/api/v1/models/download/status/job_x"):
                  (404, {"error": {"type": "job_not_found",
                                   "message": "Download job with id 'job_x' not found"}})})
    r = lm.etat(URL, "job_x", transport=s)
    assert r["etat"] == "perdu" and "not found" in r["message"], r


def test_another_refusal_stays_a_failure():
    s = _Serveur({("GET", "/api/v1/models/download/status/job_x"):
                  (500, {"error": {"message": "boom"}})})
    r = lm.etat(URL, "job_x", transport=s)
    assert r["etat"] == "echec" and r["message"] == "boom", r


# ── charger / decharger ───────────────────────────────────────────────────

def test_loading_asks_for_promptuinos_context():
    s = _Serveur({("GET", "/api/v1/models"): (200, _LISTE),
                  ("POST", "/api/v1/models/load"): (200, _CHARGE)})
    ok, msg = lm.charger(URL, "google/gemma-4-12b-qat", transport=s)
    assert ok and msg == "", (ok, msg)
    charge = [c for c in s.appels if c[1] == "/api/v1/models/load"]
    assert charge[0][2] == {"model": "google/gemma-4-12b-qat",
                            "context_length": lm.CTX_PROMPTUINO}, charge


def test_loading_is_capped_by_the_models_own_maximum():
    petit = {"models": [{"type": "llm", "key": "a/petit", "size_bytes": 1,
                         "loaded_instances": [], "max_context_length": 8192}]}
    s = _Serveur({("GET", "/api/v1/models"): (200, petit),
                  ("POST", "/api/v1/models/load"): (200, _CHARGE)})
    lm.charger(URL, "a/petit", transport=s)
    charge = [c for c in s.appels if c[1] == "/api/v1/models/load"]
    assert charge[0][2]["context_length"] == 8192, charge


def test_reloading_unloads_the_too_small_instance_first():
    """Le cas << contexte trop petit >> : charger une seconde instance
    laisserait la premiere, a 4 096 tokens, occuper la memoire -- et rien ne
    dit laquelle LM Studio servirait."""
    s = _Serveur({("GET", "/api/v1/models"): (200, _LISTE),
                  ("POST", "/api/v1/models/unload"): (200, {"instance_id": "google/gemma-4-e4b"}),
                  ("POST", "/api/v1/models/load"): (200, _CHARGE)})
    ok, _ = lm.charger(URL, "google/gemma-4-e4b", transport=s)
    assert ok
    ordre = [(m, c) for m, c, _b in s.appels if m == "POST"]
    assert ordre == [("POST", "/api/v1/models/unload"), ("POST", "/api/v1/models/load")], ordre
    assert s.appels[1][2] == {"instance_id": "google/gemma-4-e4b"}


def test_a_refused_load_carries_lm_studios_explanation():
    s = _Serveur({("GET", "/api/v1/models"): (200, _LISTE),
                  ("POST", "/api/v1/models/load"): (500, _TROP_GROS)})
    ok, msg = lm.charger(URL, "google/gemma-4-12b-qat", transport=s)
    assert not ok and "insufficient system resources" in msg, msg


def test_unloading_reports_success_and_unknown_instance():
    s = _Serveur({("POST", "/api/v1/models/unload"): (200, {"instance_id": "a"})})
    assert lm.decharger(URL, "a", transport=s) == (True, "")
    s = _Serveur({("POST", "/api/v1/models/unload"):
                  (404, {"error": {"type": "model_not_found",
                                   "message": "Model with instance identifier 'z' is not loaded."}})})
    ok, msg = lm.decharger(URL, "z", transport=s)
    assert not ok and "not loaded" in msg


def test_nothing_ever_raises_toward_the_screen():
    for appel in (lambda: lm.etat_api(URL, transport=_muet),
                  lambda: lm.modeles_installes(URL, transport=_muet),
                  lambda: lm.demarrer(URL, "a", transport=_muet),
                  lambda: lm.etat(URL, "j", transport=_muet),
                  lambda: lm.charger(URL, "a", transport=_muet),
                  lambda: lm.decharger(URL, "a", transport=_muet)):
        appel()


# ── les suggestions ───────────────────────────────────────────────────────

def test_the_suggestions_start_with_the_equivalent_of_ollamas_default():
    assert lm.SUGGERES[0][0] == "google/gemma-4-e2b"
    for cle, taille, params in lm.SUGGERES:
        assert "/" in cle and taille > 0 and params, cle


def test_promptuinos_context_is_one_number_shared_with_the_screen():
    import ui.ia_view as ia_view  # noqa: F401  (charge PyQt6, sans fenetre)
    assert ia_view._LMSTUDIO_CTX_MIN == lm.CTX_PROMPTUINO == 16384


def test_a_followed_download_is_kept_by_the_module_whatever_the_suffix():
    """La fenetre est detruite a la fermeture (QA AV2, 2026-11-06) : le
    numero de suivi vit dans le module, indexe par la racine native comme
    toutes les requetes."""
    lm._SUIVIS.clear()
    assert lm.suivi("http://127.0.0.1:1234/v1") is None
    lm.suivre("http://127.0.0.1:1234/v1", "google/gemma-3-4b", "job_1",
              avant=["google/gemma-4-e4b"])
    assert lm.suivi("http://127.0.0.1:1234") == {
        "cle": "google/gemma-3-4b", "job": "job_1",
        "avant": frozenset({"google/gemma-4-e4b"})}
    assert lm.suivi("http://127.0.0.1:5678/v1") is None, "un autre serveur"
    lm.oublier("http://127.0.0.1:1234/")
    assert lm.suivi("http://127.0.0.1:1234/v1") is None
    lm.oublier("http://127.0.0.1:1234/v1")       # deja oublie : sans effet


TESTS = [
    test_a_followed_download_is_kept_by_the_module_whatever_the_suffix,
    test_the_api_state_tells_old_from_silent,
    test_the_v1_root_is_found_whatever_suffix_the_user_typed,
    test_the_installed_list_drops_embeddings_and_keeps_exact_sizes,
    test_each_card_says_what_reasoning_the_model_allows,
    test_a_silent_server_gives_an_empty_list_not_an_exception,
    test_starting_a_download_returns_the_job_and_NO_total,
    test_an_installed_model_is_said_so_without_a_job,
    test_an_unknown_model_carries_lm_studios_own_message,
    test_starting_with_a_silent_server_says_silent,
    test_progress_reads_bytes_speed_and_end,
    test_the_sentinel_end_date_and_zero_speed_mean_unknown,
    test_a_finished_job_says_finished,
    test_a_failed_job_is_an_error_even_without_a_message,
    test_a_job_lm_studio_forgot_is_lost_not_failed,
    test_another_refusal_stays_a_failure,
    test_loading_asks_for_promptuinos_context,
    test_loading_is_capped_by_the_models_own_maximum,
    test_reloading_unloads_the_too_small_instance_first,
    test_a_refused_load_carries_lm_studios_explanation,
    test_unloading_reports_success_and_unknown_instance,
    test_nothing_ever_raises_toward_the_screen,
    test_the_suggestions_start_with_the_equivalent_of_ollamas_default,
    test_promptuinos_context_is_one_number_shared_with_the_screen,
]


def main():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
