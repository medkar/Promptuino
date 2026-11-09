"""Le modele a-t-il deborde de la carte graphique ? (2026-11-06)

Demande de l'auteur : une fois le modele charge, LIRE s'il a deborde, et le
dire en orange (« branche mais lent »). Les signaux et leurs seuils viennent
des mesures du jour (docs/superpowers/measures/2026-11-06-contexte-vram.md) :

- Ollama : `size_vram / size` dans `/api/ps` -- 100 % quand il tient, 64 %
  quand il deborde (llama3.1:8b @128k) ;
- LM Studio, deux debordements differents, deux signaux :
  * memoire graphique PARTAGEE du processus `llama-server` : 0,13 a 0,17 Gio
    quand il tient, 6,41 Gio quand il deborde (Qwen3 4B @128k) ;
  * couches sur le processeur : seul `main.log` le dit (« raw num offload
    layers '23' » pour gemma-4-26b) -- la memoire partagee ne le voit pas.

Aucun reseau, aucun PowerShell, aucun journal reel : tout est injecte.

Run: python scripts/test_debordement.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.debordement as db  # noqa: E402
import ui.ollama_models as om  # noqa: E402

G = 2 ** 30


class _Serveur:
    def __init__(self, routes):
        self.routes = routes

    def __call__(self, methode, url, corps, timeout):
        return self.routes.get((methode, url.split("11434", 1)[1]), (404, {}))


def _ps(size, size_vram, nom="llama3.1:8b", ctx=131072):
    return _Serveur({("GET", "/api/ps"): (200, {"models": [
        {"name": nom, "size": size, "size_vram": size_vram, "context_length": ctx}]})})


# ── Ollama ────────────────────────────────────────────────────────────────

def test_ollama_says_overflow_when_part_of_the_model_is_not_in_vram():
    """Mesure : 21,65 Gio dont 13,75 en VRAM (64 %)."""
    m = om.en_memoire("llama3.1:8b", transport=_ps(int(21.65 * G), int(13.75 * G)))
    assert m == {"charge": True, "ctx": 131072, "deborde": True}, m


def test_ollama_entirely_in_vram_is_not_an_overflow():
    m = om.en_memoire("llama3.1:8b", transport=_ps(int(6.56 * G), int(6.56 * G), ctx=16384))
    assert m["deborde"] is False, m


def test_ollama_not_loaded_or_silent_says_nothing():
    vide = _Serveur({("GET", "/api/ps"): (200, {"models": []})})
    assert om.en_memoire("llama3.1:8b", transport=vide) == {
        "charge": False, "ctx": None, "deborde": None}
    sans_tailles = _Serveur({("GET", "/api/ps"): (200, {"models": [{"name": "llama3.1:8b"}]})})
    assert om.en_memoire("llama3.1:8b", transport=sans_tailles)["deborde"] is None


# ── LM Studio : la memoire partagee ───────────────────────────────────────

def test_shared_gpu_memory_is_summed_over_the_engine_processes():
    sortie = f"{int(7.05 * G)};{int(0.13 * G)}\n{0};{int(0.01 * G)}\n"
    assert db.memoire_partagee(executer=lambda cmd: sortie) == int(0.13 * G) + int(0.01 * G)


def test_no_engine_process_or_no_answer_is_unknown():
    assert db.memoire_partagee(executer=lambda cmd: "") is None
    assert db.memoire_partagee(executer=lambda cmd: None) is None


# ── LM Studio : les couches sur le processeur, d'apres main.log ──────────

_JOURNAL = """\
[2026-11-06 16:23:14.991] [error] [LM Studio] Model load size estimate with raw num offload layers 'max' and context length '16384':
  Model: 6.52 GB
[2026-11-06 16:23:36.579] [error] [LM Studio] Model load size estimate with raw num offload layers '23' and context length '16384':
  Model: 12.35 GB
"""


def test_a_number_of_layers_means_part_of_the_model_runs_on_the_cpu():
    """gemma-4-26b : 23 couches sur 30 sur la carte -- recopie du journal."""
    assert db.couches_partielles(16384, lire=lambda: _JOURNAL) is True


def test_max_layers_means_the_whole_model_is_on_the_card():
    assert db.couches_partielles(16384, lire=lambda: _JOURNAL.split("\n[2026-11-06 16:23:36")[0]) is False


def test_a_last_load_at_another_context_is_not_ours():
    """Le journal ne nomme pas le modele : le dernier bloc n'est le notre que
    si sa taille de contexte concorde. Sinon, on se tait."""
    assert db.couches_partielles(131072, lire=lambda: _JOURNAL) is None
    assert db.couches_partielles(16384, lire=lambda: "") is None
    assert db.couches_partielles(16384, lire=lambda: None) is None


# ── LM Studio : la conclusion ─────────────────────────────────────────────

def test_either_signal_is_enough_and_silence_stays_silence():
    peu, beaucoup = int(0.15 * G), int(6.41 * G)
    assert db.lmstudio_deborde(16384, partage=lambda: beaucoup, couches=lambda c: False) is True
    assert db.lmstudio_deborde(16384, partage=lambda: peu, couches=lambda c: True) is True
    assert db.lmstudio_deborde(16384, partage=lambda: peu, couches=lambda c: False) is False
    assert db.lmstudio_deborde(16384, partage=lambda: peu, couches=lambda c: None) is False
    assert db.lmstudio_deborde(16384, partage=lambda: None, couches=lambda c: None) is None


def test_the_threshold_sits_between_what_was_measured():
    assert int(0.17 * G) < db.SEUIL_PARTAGE < int(6.41 * G)


TESTS = [
    test_ollama_says_overflow_when_part_of_the_model_is_not_in_vram,
    test_ollama_entirely_in_vram_is_not_an_overflow,
    test_ollama_not_loaded_or_silent_says_nothing,
    test_shared_gpu_memory_is_summed_over_the_engine_processes,
    test_no_engine_process_or_no_answer_is_unknown,
    test_a_number_of_layers_means_part_of_the_model_runs_on_the_cpu,
    test_max_layers_means_the_whole_model_is_on_the_card,
    test_a_last_load_at_another_context_is_not_ours,
    test_either_signal_is_enough_and_silence_stays_silence,
    test_the_threshold_sits_between_what_was_measured,
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
