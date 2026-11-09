"""Vérifie que le backend Ollama configure le budget de tokens sur
/api/generate (num_ctx + num_predict) — sinon la sortie est tronquée et la fin
du code générée/réparée disparaît.

Convention repo : runner standalone, pas de pytest.
  QT_QPA_PLATFORM=offscreen python scripts/test_ollama_options.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ui.ai_backends.ollama_backend as ob
from ui.ai_config import ai_config

# Depuis le 2026-11-06, la generation alloue le REGLAGE de l'onglet IA (le
# meme que le chat, decision de l'auteur) et non plus 8 192 fixes. Fixe EN
# MEMOIRE pour ne dependre ni de la configuration de l'utilisateur, ni l'ecrire.
ai_config._data["ollama_num_ctx"] = 20480


def _capture(show=None):
    """Monkeypatch _post pour capturer les payloads (aucun serveur requis).
    `show` : ce que `/api/show` repond (la capacite de reflexion)."""
    calls: list[tuple[str, dict]] = []

    def fake_post(path, payload, timeout=None, register=None, coupure=None):
        # `register` : le point d'accroche d'annulation ajoute au TODO #24.
        # Accepte et ignore — cette doublure n'a pas de socket a fermer.
        calls.append((path, payload))
        if path == "/api/show" and show is not None:
            return show
        # Neutral response: no model_info -> maximum unknown -> the setting.
        return {"response": "void setup(){}\nvoid loop(){}",
                "message": {"content": "ok"},
                "model_info": {}, "details": {}}

    def fake_stream(path, payload, timeout=None):
        calls.append((path, payload))
        yield {"message": {"content": "ok"}}
        yield {"done": True}

    ob._post = fake_post
    ob._post_stream = fake_stream
    return calls


def _gen_options(calls) -> dict:
    gen = [p for (path, p) in calls if path == "/api/generate"]
    assert gen, "aucun appel /api/generate capturé"
    return gen[-1].get("options", {})


# ── Tests ────────────────────────────────────────────────────────

def test_generate_code_sets_token_budget():
    calls = _capture()
    be = ob.OllamaBackend("gemma4:e2b")
    be.generate_code("blink an LED", "Arduino Uno")
    opts = _gen_options(calls)
    assert opts.get("num_ctx") == 20480, opts   # reglage ; maximum inconnu
    assert opts.get("num_predict") == -1, opts


def test_repair_code_sets_token_budget():
    calls = _capture()
    be = ob.OllamaBackend("gemma4:e2b")
    be.repair_code("void setup(){}\nvoid loop(){}", "error: x",
                   "French", "Arduino Uno")
    opts = _gen_options(calls)
    assert opts.get("num_ctx") == 20480, opts   # reglage ; maximum inconnu
    assert opts.get("num_predict") == -1, opts


def _chat_options(calls) -> list:
    return [p.get("options", {}) for (path, p) in calls if path == "/api/chat"]


def test_chat_has_no_answer_cap():
    """Plus de plafond de 2 048 sur le chat (decision de l'auteur,
    2026-11-06) : un modele qui reflechit y depensait tout son budget."""
    calls = _capture()
    be = ob.OllamaBackend("gemma4:e2b")
    be.chat("sys", [{"role": "user", "content": "salut"}])
    list(be.chat_stream("sys", [{"role": "user", "content": "salut"}]))
    opts = _chat_options(calls)
    assert len(opts) == 2, calls
    for o in opts:
        assert o.get("num_predict") == -1, o


# ── Reflexion (TODO #123) : reponses de /api/show mesurees le 2026-11-06 ──
_GEMMA4 = {"capabilities": ["completion", "tools", "thinking"],
           "thinking": {"values": [False, True], "default": True},
           "model_info": {}, "details": {}}
_LLAMA31 = {"capabilities": ["completion", "tools"], "model_info": {}, "details": {}}


def _thinks(calls) -> list:
    return [p.get("think") for (path, p) in calls
            if path in ("/api/chat", "/api/generate")]


def _tous_les_appels(be):
    be.chat("sys", [{"role": "user", "content": "salut"}])
    list(be.chat_stream("sys", [{"role": "user", "content": "salut"}]))
    be.generate_code("blink an LED", "Arduino Uno")


def test_the_switch_reaches_chat_and_generation_alike():
    """Lu EN DIRECT, comme le contexte : basculer l'interrupteur s'applique
    a la demande suivante sans recreer le moteur."""
    for voulu in (True, False):
        ai_config._data["ollama_think"] = voulu
        calls = _capture(_GEMMA4)
        _tous_les_appels(ob.OllamaBackend("gemma4:e2b"))
        assert _thinks(calls) == [voulu] * 3, (voulu, _thinks(calls))
    ai_config._data["ollama_think"] = False


def test_a_model_that_cannot_think_is_never_asked_to():
    """Ollama refuse `think: true` sur llama3.1 : l'interrupteur allume ne
    doit pas casser la generation."""
    ai_config._data["ollama_think"] = True
    calls = _capture(_LLAMA31)
    _tous_les_appels(ob.OllamaBackend("llama3.1:8b"))
    ai_config._data["ollama_think"] = False
    assert _thinks(calls) == [False] * 3, _thinks(calls)


TESTS = [
    test_generate_code_sets_token_budget,
    test_repair_code_sets_token_budget,
    test_chat_has_no_answer_cap,
    test_the_switch_reaches_chat_and_generation_alike,
    test_a_model_that_cannot_think_is_never_asked_to,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests passed")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
