"""Le moteur LM Studio : l'adaptateur compatible OpenAI, plus la reflexion
(TODO #123) et sans plafond de reponse.

Mesure du 2026-11-06 sur LM Studio 0.4 : par l'API compatible OpenAI, SEULE
`reasoning_effort: "none"` coupe la reflexion de gemma-4 (0 token, 0,3 s au
lieu de 5,3 s). Faux transport, fausse fiche : ni reseau ni serveur.

Run: python scripts/test_lmstudio_backend.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui.ai_backends.lmstudio_backend import LMStudioBackend  # noqa: E402

MSG = [{"role": "user", "content": "hi"}]


class _Transport:
    def __init__(self):
        self.payloads = []

    def post_json(self, url, headers, payload, timeout):
        self.payloads.append(payload)
        return {"choices": [{"message": {"content": "ok"}}]}

    def iter_sse(self, url, headers, payload, timeout):
        self.payloads.append(payload)
        yield "data: [DONE]"


class _Fiche:
    """Compte les lectures : la capacite du modele se lit UNE fois."""
    def __init__(self, *reponses):
        self.reponses = list(reponses)
        self.lectures = 0

    def __call__(self):
        self.lectures += 1
        return self.reponses.pop(0) if len(self.reponses) > 1 else self.reponses[0]


def _moteur(reflexion, fiche):
    t = _Transport()
    b = LMStudioBackend("http://127.0.0.1:1234/v1", "google/gemma-4-12b-qat",
                        reflexion=reflexion, context_window_hint=16384,
                        fiche=fiche, transport=t)
    return b, t


def _tous_les_appels(b):
    b._complete("S", MSG)
    b.chat("S", MSG)
    list(b.chat_stream("S", MSG))
    b.probe_model()


GEMMA4 = {"reflexion": ("off", "on")}


def test_switched_off_the_model_is_told_not_to_think_everywhere():
    b, t = _moteur(False, _Fiche(GEMMA4))
    _tous_les_appels(b)
    assert len(t.payloads) == 4
    for p in t.payloads:
        assert p.get("reasoning_effort") == "none", p


def test_switched_on_nothing_is_sent_the_model_thinks_by_default():
    b, t = _moteur(True, _Fiche(GEMMA4))
    _tous_les_appels(b)
    for p in t.payloads:
        assert "reasoning_effort" not in p, p


def test_a_model_without_reasoning_or_that_always_thinks_gets_nothing():
    for fiche in ({"reflexion": ()}, {"reflexion": ("on",)}, {"reflexion": None}):
        b, t = _moteur(False, _Fiche(fiche))
        b.chat("S", MSG)
        assert "reasoning_effort" not in t.payloads[-1], (fiche, t.payloads[-1])


def test_the_capability_is_read_once_but_retried_while_the_server_is_silent():
    fiche = _Fiche(None, GEMMA4)
    b, t = _moteur(False, fiche)
    b.chat("S", MSG)
    assert "reasoning_effort" not in t.payloads[-1]     # inconnu : rien
    b.chat("S", MSG)
    b.chat("S", MSG)
    assert t.payloads[-1].get("reasoning_effort") == "none"
    assert fiche.lectures == 2, fiche.lectures


def test_no_answer_cap_and_no_key():
    b, t = _moteur(True, _Fiche(GEMMA4))
    b.chat("S", MSG)
    assert "max_tokens" not in t.payloads[-1]
    assert not b.requires_api_key and b.backend_id == "lmstudio"


def test_the_factory_builds_it_from_the_settings():
    from ui.ai_config import ai_config
    from ui.ai_backends.factory import get_backend_instance
    ancien = ai_config._data.get("lmstudio_think")
    try:
        # Le MEME moteur suit le reglage change apres sa creation (pastille
        # du chat, 2026-11-07) ; la capacite est posee pour ne rien lire.
        from ui import reflexion
        b = get_backend_instance("lmstudio")
        assert isinstance(b, LMStudioBackend)
        b._capacite = reflexion.Capacite(True, True, "on")
        ai_config._data["lmstudio_think"] = False      # en memoire, jamais ecrit
        assert b._champs_en_plus() == {"reasoning_effort": "none"}
        ai_config._data["lmstudio_think"] = True
        assert b._champs_en_plus() == {}
    finally:
        ai_config._data["lmstudio_think"] = ancien


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_")]


def main() -> int:
    echecs = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as e:
            echecs += 1
            print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(TESTS) - echecs}/{len(TESTS)} passed")
    return 1 if echecs else 0


if __name__ == "__main__":
    raise SystemExit(main())
