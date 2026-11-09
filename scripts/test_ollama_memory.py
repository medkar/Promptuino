"""Charger / decharger un modele Ollama depuis l'app (2026-11-06).

Les reponses du bouchon sont RECOPIEES des mesures du jour sur Ollama 0.40.5
(llama3.1:8b) : `done_reason` "load" / "unload", `/api/ps` avec
`context_length` et `expires_at` en 2319 pour un modele charge sans limite.
Aucun reseau.

Run: python scripts/test_ollama_memory.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.ollama_models as om  # noqa: E402


class _Serveur:
    """(methode, chemin) -> (statut, json) ; note chaque appel."""

    def __init__(self, routes):
        self.routes = routes
        self.appels = []

    def __call__(self, methode, url, corps, timeout):
        chemin = url.split("11434", 1)[1]
        self.appels.append((methode, chemin, corps))
        rep = self.routes.get((methode, chemin))
        if rep is None:
            return 404, {"error": "route absente du bouchon"}
        return rep


def _muet(methode, url, corps, timeout):
    raise ConnectionRefusedError("serveur arrete")


_PS = {"models": [
    {"name": "llama3.1:8b", "model": "llama3.1:8b", "size": 5009571839,
     "context_length": 2048, "expires_at": "2319-02-16T13:42:57+01:00",
     "size_vram": 5009571839},
    {"name": "mistral:latest", "model": "mistral:latest",
     "expires_at": "2026-11-06T14:01:02+01:00"},          # vieil Ollama : pas de contexte
]}


def test_the_loaded_list_reads_names_and_context():
    s = _Serveur({("GET", "/api/ps"): (200, _PS)})
    assert om.modeles_charges(transport=s) == {"llama3.1:8b": 2048,
                                               "mistral:latest": None}


def test_a_name_without_tag_is_the_latest_one():
    """`mistral` et `mistral:latest` sont le meme modele ; /api/ps rend
    toujours la forme etiquetee."""
    s = _Serveur({("GET", "/api/ps"): (200, _PS)})
    # `deborde` (2026-11-06) : None sans les tailles, False quand tout est en VRAM.
    assert om.en_memoire("mistral", transport=s) == {"charge": True, "ctx": None,
                                                     "deborde": None}
    assert om.en_memoire("llama3.1:8b", transport=s) == {"charge": True, "ctx": 2048,
                                                         "deborde": False}
    assert om.en_memoire("gemma4:e2b", transport=s) == {"charge": False, "ctx": None,
                                                        "deborde": None}


def test_a_silent_server_says_nothing_rather_than_not_loaded():
    """Muet n'est pas « pas charge » : la page ne doit rien affirmer."""
    assert om.modeles_charges(transport=_muet) == {}
    assert om.en_memoire("llama3.1:8b", transport=_muet) is None


def test_loading_asks_to_stay_until_unloaded_at_the_given_context():
    """⛔ Mesure : une demande a un AUTRE num_ctx recharge le modele (7,7 s),
    qui repart alors sur 5 min. Le contexte est donc celui que l'appelant
    passe -- la page passe celui de la generation."""
    s = _Serveur({("POST", "/api/generate"):
                  (200, {"model": "llama3.1:8b", "response": "", "done": True,
                         "done_reason": "load"})})
    assert om.charger("llama3.1:8b", 8192, transport=s) == (True, "")
    methode, chemin, corps = s.appels[0]
    assert corps == {"model": "llama3.1:8b", "keep_alive": -1, "stream": False,
                     "options": {"num_ctx": 8192}}, corps
    assert "prompt" not in corps, "sans prompt : charger, pas generer"


def test_a_refused_load_carries_ollamas_message():
    s = _Serveur({("POST", "/api/generate"):
                  (500, {"error": "model requires more system memory (9.1 GiB) than is available (4.0 GiB)"})})
    ok, msg = om.charger("gros:70b", 8192, transport=s)
    assert not ok and "more system memory" in msg, msg
    assert om.charger("x", 8192, transport=_muet)[0] is False


def test_unloading_asks_for_a_zero_keep_alive():
    s = _Serveur({("POST", "/api/generate"):
                  (200, {"model": "llama3.1:8b", "response": "", "done": True,
                         "done_reason": "unload"})})
    assert om.decharger("llama3.1:8b", transport=s) == (True, "")
    assert s.appels[0][2] == {"model": "llama3.1:8b", "keep_alive": 0,
                              "stream": False}


def test_the_models_maximum_context_is_read_from_show():
    """Recopie de la mesure du 2026-11-06 (llama3.1:8b)."""
    s = _Serveur({("POST", "/api/show"): (200, {"model_info": {
        "general.architecture": "llama", "llama.block_count": 32,
        "llama.context_length": 131072}})})
    assert om.contexte_max("llama3.1:8b", transport=s) == 131072
    assert s.appels[0][2] == {"model": "llama3.1:8b"}


def test_an_unspoken_maximum_is_unknown_not_a_guess():
    s = _Serveur({("POST", "/api/show"): (200, {"model_info": {"x.block_count": 2}})})
    assert om.contexte_max("x", transport=s) is None
    assert om.contexte_max("x", transport=_muet) is None


def test_the_models_thinking_is_read_from_show():
    """Recopie de la mesure du 2026-11-06 (gemma4:e2b, llama3.1:8b)."""
    s = _Serveur({("POST", "/api/show"): (200, {
        "capabilities": ["completion", "tools", "thinking"],
        "thinking": {"values": [False, True], "default": True}})})
    cap = om.reflexion_modele("gemma4:e2b", transport=s)
    assert cap.peut_reflechir and cap.peut_couper
    s = _Serveur({("POST", "/api/show"): (200, {"capabilities": ["completion", "tools"]})})
    assert not om.reflexion_modele("llama3.1:8b", transport=s).peut_reflechir
    assert om.reflexion_modele("x", transport=_muet) is None


def test_nothing_ever_raises_toward_the_screen():
    for appel in (lambda: om.modeles_charges(transport=_muet),
                  lambda: om.en_memoire("x", transport=_muet),
                  lambda: om.charger("x", 8192, transport=_muet),
                  lambda: om.decharger("x", transport=_muet)):
        appel()


TESTS = [
    test_the_loaded_list_reads_names_and_context,
    test_a_name_without_tag_is_the_latest_one,
    test_a_silent_server_says_nothing_rather_than_not_loaded,
    test_loading_asks_to_stay_until_unloaded_at_the_given_context,
    test_a_refused_load_carries_ollamas_message,
    test_unloading_asks_for_a_zero_keep_alive,
    test_the_models_maximum_context_is_read_from_show,
    test_an_unspoken_maximum_is_unknown_not_a_guess,
    test_the_models_thinking_is_read_from_show,
    test_nothing_ever_raises_toward_the_screen,
]


def main():
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
