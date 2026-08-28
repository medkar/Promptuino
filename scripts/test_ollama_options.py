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


def _capture():
    """Monkeypatch _post pour capturer les payloads (aucun serveur requis)."""
    calls: list[tuple[str, dict]] = []

    def fake_post(path, payload, timeout=None, register=None):
        # `register` : le point d'accroche d'annulation ajoute au TODO #24.
        # Accepte et ignore — cette doublure n'a pas de socket a fermer.
        calls.append((path, payload))
        # Neutral response: no model_info -> context_window_hint = 8192.
        return {"response": "void setup(){}\nvoid loop(){}",
                "model_info": {}, "details": {}}

    ob._post = fake_post
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
    assert opts.get("num_ctx") == 8192, opts
    assert opts.get("num_predict") == -1, opts


def test_repair_code_sets_token_budget():
    calls = _capture()
    be = ob.OllamaBackend("gemma4:e2b")
    be.repair_code("void setup(){}\nvoid loop(){}", "error: x",
                   "French", "Arduino Uno")
    opts = _gen_options(calls)
    assert opts.get("num_ctx") == 8192, opts
    assert opts.get("num_predict") == -1, opts


TESTS = [
    test_generate_code_sets_token_budget,
    test_repair_code_sets_token_budget,
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
