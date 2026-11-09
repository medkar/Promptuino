"""La reflexion (« thinking ») des modeles locaux : ce que le modele permet,
ce que l'interrupteur montre, ce qu'on envoie au moteur (TODO #123).

Les reponses recopiees ici viennent de mesures du 2026-11-06 :
- Ollama 0.40.5, `/api/show` : gemma4:e2b `thinking: {values: [False, True],
  default: True}` ; qwen3-coder:30b `{values: [False], default: False}` sans
  la capacite « thinking » ; llama3.1:8b aucun champ `thinking`.
- LM Studio 0.4, `GET /api/v1/models` : gemma-4 `reasoning: {allowed_options:
  ['off', 'on'], default: 'on'}` ; phi-4-mini-reasoning `['on']` seul ;
  qwen3-4b-2507 aucune cle `reasoning`.

Run: python scripts/test_reflexion.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ui import reflexion as rf  # noqa: E402

GEMMA4_OLLAMA = {"capabilities": ["completion", "vision", "audio", "tools", "thinking"],
                 "thinking": {"values": [False, True], "default": True}}
QWEN_CODER_OLLAMA = {"capabilities": ["completion", "tools"],
                     "thinking": {"values": [False], "default": False}}
LLAMA31_OLLAMA = {"capabilities": ["completion", "tools"]}
NIVEAUX_OLLAMA = {"capabilities": ["completion", "thinking"],
                  "thinking": {"values": ["low", "medium", "high"], "default": "medium"}}
ANCIEN_OLLAMA = {"capabilities": ["completion", "thinking"]}


# ── Ce que le modele permet ──────────────────────────────────────────────

def test_ollama_a_model_that_can_think_and_stop():
    cap = rf.depuis_ollama(GEMMA4_OLLAMA)
    assert cap.peut_reflechir and cap.peut_couper and cap.allumer is True


def test_ollama_a_model_whose_only_value_is_false_cannot_think():
    cap = rf.depuis_ollama(QWEN_CODER_OLLAMA)
    assert not cap.peut_reflechir


def test_ollama_a_model_without_the_field_cannot_think():
    assert not rf.depuis_ollama(LLAMA31_OLLAMA).peut_reflechir


def test_ollama_named_levels_think_with_the_default_and_cannot_stop():
    cap = rf.depuis_ollama(NIVEAUX_OLLAMA)
    assert cap.peut_reflechir and not cap.peut_couper
    assert cap.allumer == "medium"


def test_ollama_older_servers_only_give_the_capability():
    cap = rf.depuis_ollama(ANCIEN_OLLAMA)
    assert cap.peut_reflechir and cap.peut_couper and cap.allumer is True


def test_ollama_an_empty_answer_is_unknown():
    assert rf.depuis_ollama({}) is None
    assert rf.depuis_ollama(None) is None


def test_lmstudio_off_and_on():
    cap = rf.depuis_lmstudio(("off", "on"))
    assert cap.peut_reflechir and cap.peut_couper


def test_lmstudio_on_only_cannot_stop():
    cap = rf.depuis_lmstudio(("on",))
    assert cap.peut_reflechir and not cap.peut_couper


def test_lmstudio_no_reasoning_key_cannot_think():
    assert not rf.depuis_lmstudio(()).peut_reflechir


def test_lmstudio_unknown_when_the_server_does_not_say():
    assert rf.depuis_lmstudio(None) is None


# ── Ce que l'interrupteur montre : (actif, coche) ────────────────────────

def test_the_switch_follows_the_setting_when_the_model_allows_both():
    cap = rf.depuis_ollama(GEMMA4_OLLAMA)
    assert rf.interrupteur(cap, True) == (True, True)
    assert rf.interrupteur(cap, False) == (True, False)


def test_the_switch_is_greyed_off_when_the_model_cannot_think():
    cap = rf.depuis_ollama(LLAMA31_OLLAMA)
    assert rf.interrupteur(cap, True) == (False, False)


def test_the_switch_is_greyed_on_when_the_model_always_thinks():
    cap = rf.depuis_lmstudio(("on",))
    assert rf.interrupteur(cap, False) == (False, True)


def test_the_switch_stays_usable_when_the_model_is_unknown():
    """Serveur muet : on laisse regler, on ne devine pas."""
    assert rf.interrupteur(None, True) == (True, True)


# ── Ce qu'on envoie ──────────────────────────────────────────────────────

def test_ollama_sends_what_the_switch_says():
    cap = rf.depuis_ollama(GEMMA4_OLLAMA)
    assert rf.ollama_think(cap, True) is True
    assert rf.ollama_think(cap, False) is False


def test_ollama_never_asks_a_model_that_cannot_think_to_think():
    """Ollama refuse `think: true` sur un modele qui ne sait pas reflechir :
    l'interrupteur allume ne doit pas casser la generation."""
    for show in (LLAMA31_OLLAMA, QWEN_CODER_OLLAMA):
        assert rf.ollama_think(rf.depuis_ollama(show), True) is False


def test_ollama_a_model_that_always_thinks_gets_its_level():
    assert rf.ollama_think(rf.depuis_ollama(NIVEAUX_OLLAMA), False) == "medium"


def test_ollama_unknown_keeps_the_historical_false():
    assert rf.ollama_think(None, True) is False


def test_lmstudio_cuts_only_with_the_one_field_it_honours():
    """Mesure : seule `reasoning_effort: "none"` coupe ; les autres formes
    sont ignorees sans erreur."""
    cap = rf.depuis_lmstudio(("off", "on"))
    assert rf.lmstudio_champs(cap, False) == {"reasoning_effort": "none"}
    assert rf.lmstudio_champs(cap, True) == {}


def test_lmstudio_sends_nothing_it_has_not_measured():
    """Modele sans reflexion, qui reflechit toujours, ou inconnu : rien."""
    for cap in (rf.depuis_lmstudio(()), rf.depuis_lmstudio(("on",)), None):
        assert rf.lmstudio_champs(cap, False) == {}


# ── ChatGPT : trois crans ────────────────────────────────────────────────

def test_chatgpt_three_levels_and_a_middle_default():
    assert rf.NIVEAUX_CHATGPT == ("low", "medium", "high")
    assert rf.NIVEAU_CHATGPT_DEFAUT == "medium"
    assert rf.niveau_chatgpt("high") == "high"
    assert rf.niveau_chatgpt("nimporte") == "medium"
    assert rf.niveau_chatgpt(None) == "medium"


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_")]


def main() -> int:
    assert len(TESTS) > 20, len(TESTS)
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
