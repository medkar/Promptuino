"""Charger un modele libere d'abord les AUTRES, sur les DEUX moteurs.

Decision de l'auteur du 2026-11-06, apres avoir trouve deux modeles charges
dans LM Studio en meme temps : au chargement d'un modele depuis Promptuino,
les autres sont decharges -- y compris ceux de l'AUTRE moteur (passer de
LM Studio a Ollama libere le modele de LM Studio, et inversement).
« Decharger » reste disponible a la main.

Aucun reseau : les fonctions des deux modules sont remplacees.

Run: python scripts/test_memoire_modeles.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.lmstudio_models as lm  # noqa: E402
import ui.memoire_modeles as mm  # noqa: E402
import ui.ollama_models as om  # noqa: E402

URL = "http://127.0.0.1:1234/v1"


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


def _fiche(cle, *instances):
    return {"cle": cle, "taille": 1, "params": "", "quant": "", "ctx_max": 131072,
            "instances": [(i, 16384) for i in instances]}


def _monde(ollama: dict, lms: list, refus=()):
    """Deux serveurs factices ; `decharges` note ce qui a ete libere."""
    decharges = []

    def dech_o(nom):
        decharges.append(("ollama", nom))
        return (False, "occupe") if nom in refus else (True, "")

    def dech_l(url, inst):
        decharges.append(("lmstudio", inst))
        return (False, "occupe") if inst in refus else (True, "")

    return decharges, (
        _Detour(om, modeles_charges=lambda: dict(ollama), decharger=dech_o),
        _Detour(lm, modeles_installes=lambda url: list(lms), decharger=dech_l))


def test_loading_on_ollama_frees_the_other_ollama_models_and_lm_studio():
    decharges, (d1, d2) = _monde({"llama3.1:8b": 8192, "gemma4:e2b": 16384},
                                 [_fiche("google/gemma-4-e4b", "google/gemma-4-e4b"),
                                  _fiche("gemma-3-4b-it")])
    with d1, d2:
        liberes = mm.liberer_autres("ollama", "gemma4:e2b", URL)
    assert decharges == [("ollama", "llama3.1:8b"), ("lmstudio", "google/gemma-4-e4b")], decharges
    assert liberes == [("llama3.1:8b", "Ollama"), ("google/gemma-4-e4b", "LM Studio")], liberes


def test_loading_on_lm_studio_frees_ollama_and_the_other_lm_studio_models():
    decharges, (d1, d2) = _monde({"llama3.1:8b": 8192},
                                 [_fiche("google/gemma-4-e4b", "google/gemma-4-e4b"),
                                  _fiche("google/gemma-4-12b-qat", "google/gemma-4-12b-qat")])
    with d1, d2:
        liberes = mm.liberer_autres("lmstudio", "google/gemma-4-12b-qat", URL)
    assert ("lmstudio", "google/gemma-4-12b-qat") not in decharges, "le modele a charger"
    assert set(decharges) == {("ollama", "llama3.1:8b"), ("lmstudio", "google/gemma-4-e4b")}


def test_an_untagged_ollama_name_is_the_same_model():
    """`mistral` et `mistral:latest` : le meme modele, il n'est pas libere."""
    decharges, (d1, d2) = _monde({"mistral:latest": 4096}, [])
    with d1, d2:
        mm.liberer_autres("ollama", "mistral", URL)
    assert decharges == [], decharges


def test_a_refused_unload_is_not_announced_as_freed():
    decharges, (d1, d2) = _monde({"llama3.1:8b": 8192}, [], refus=("llama3.1:8b",))
    with d1, d2:
        assert mm.liberer_autres("lmstudio", "x", URL) == []


def test_silent_servers_free_nothing_and_never_raise():
    def muet(*a, **k):
        raise ConnectionRefusedError("serveur arrete")
    with _Detour(om, modeles_charges=lambda: {}, decharger=muet), \
         _Detour(lm, modeles_installes=lambda url: [], decharger=muet):
        assert mm.liberer_autres("ollama", "x", URL) == []
    with _Detour(om, modeles_charges=muet), _Detour(lm, modeles_installes=muet):
        assert mm.liberer_autres("ollama", "x", URL) == []


# ── Decharger a la fermeture ce que Promptuino a charge (2026-11-07) ──────

def _transport(appels, reponse):
    def t(methode, url, corps, timeout):
        appels.append((url.rsplit("/", 2)[-2:], corps, timeout))
        return reponse(url, corps)
    return t


def test_what_promptuino_loads_is_remembered_and_unloaded_at_exit():
    om.EPINGLES.clear(); lm.EPINGLES.clear()
    appels = []
    ok_o = _transport(appels, lambda u, c: (200, {}))
    ok_l = _transport(appels, lambda u, c: (200, {"instance_id": "gemma-x"})
                      if u.endswith("/load") else (200, {}))
    with _Detour(lm, modeles_installes=lambda url, **k: []):
        assert om.charger("gemma4:e2b", 16384, transport=ok_o)[0]
        assert lm.charger(URL, "gemma-x", 16384, transport=ok_l)[0]
    assert om.EPINGLES == {"gemma4:e2b"} and lm.EPINGLES == {(URL, "gemma-x")}
    liberes = []
    with _Detour(om, decharger=lambda nom, **k: (liberes.append(nom) or (True, ""))), \
         _Detour(lm, decharger=lambda url, inst, **k: (liberes.append(inst) or (True, ""))):
        rendu = mm.decharger_les_notres()
    assert sorted(liberes) == ["gemma-x", "gemma4:e2b"], liberes
    assert {m for m, _ in rendu} == {"gemma-x", "gemma4:e2b"}
    om.EPINGLES.clear(); lm.EPINGLES.clear()


def test_a_model_unloaded_by_hand_is_forgotten():
    om.EPINGLES.clear()
    ok = _transport([], lambda u, c: (200, {}))
    om.charger("mistral", 8192, transport=ok)
    om.decharger("mistral:latest", transport=ok)
    assert om.EPINGLES == set()


def test_a_failed_load_is_not_remembered_and_nothing_else_is_touched():
    om.EPINGLES.clear(); lm.EPINGLES.clear()
    ko = _transport([], lambda u, c: (500, {"error": "no memory"}))
    om.charger("gemma4:e2b", 16384, transport=ko)
    assert om.EPINGLES == set()
    touche = []
    with _Detour(om, decharger=lambda *a, **k: touche.append(a)), \
         _Detour(lm, decharger=lambda *a, **k: touche.append(a)):
        assert mm.decharger_les_notres() == []
    assert touche == [], "un modele charge par un autre moyen n'est jamais touche"


TESTS = [
    test_loading_on_ollama_frees_the_other_ollama_models_and_lm_studio,
    test_loading_on_lm_studio_frees_ollama_and_the_other_lm_studio_models,
    test_an_untagged_ollama_name_is_the_same_model,
    test_a_refused_unload_is_not_announced_as_freed,
    test_silent_servers_free_nothing_and_never_raise,
    test_what_promptuino_loads_is_remembered_and_unloaded_at_exit,
    test_a_model_unloaded_by_hand_is_forgotten,
    test_a_failed_load_is_not_remembered_and_nothing_else_is_touched,
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
