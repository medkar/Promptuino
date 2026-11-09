"""L'interrupteur « Réfléchir avant de répondre » sur les pages Ollama et
LM Studio (TODO #123, decisions de l'auteur du 2026-11-06).

Le MEME widget sur les deux pages, desactive par defaut, grise quand le
modele ne sait pas reflechir (decoche) ou reflechit toujours (coche), avec
une ligne d'aide qui dit pourquoi.

Aucun reseau : les lectures du serveur sont remplacees. Basculer ECRIT la
configuration : la constante de module `CONFIG_PATH` est detournee vers un
dossier temporaire.

Run: python scripts/test_reflexion_pages.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

import ui.ai_config as aicfg  # noqa: E402
import ui.ia_view as ia_view  # noqa: E402
import ui.lmstudio_models as lm  # noqa: E402
import ui.ollama_models as om  # noqa: E402
from ui import reflexion as rf  # noqa: E402
from ui.ai_config import ai_config  # noqa: E402
from ui.i18n import TRANSLATIONS, lang_manager  # noqa: E402

_TMP = tempfile.TemporaryDirectory()
_VRAI_CHEMIN = aicfg.CONFIG_PATH
aicfg.CONFIG_PATH = Path(_TMP.name) / "config.json"

GEMMA4 = rf.depuis_ollama({"thinking": {"values": [False, True], "default": True}})
LLAMA31 = rf.depuis_ollama({"capabilities": ["completion", "tools"]})


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


def _reglage(cle, valeur):
    ai_config._data[cle] = valeur          # en memoire : rien n'est ecrit


def _ollama(cap):
    with _Detour(ia_view, is_server_running=lambda: True,
                 is_model_available=lambda m: True,
                 is_installed=lambda: True, is_process_running=lambda: False,
                 list_local_models=lambda: ["gemma4:e2b"]), \
         _Detour(om, en_memoire=lambda nom: None,
                 contexte_max=lambda nom: 131072,
                 reflexion_modele=lambda nom: cap):
        sec = ia_view._BackendSection("ollama")
        sec._model_combo.clear()
        sec._model_combo.addItems(["gemma4:e2b"])
        sec.refresh_availability()
    return sec


def _lmstudio(options):
    fiche = {"cle": "google/gemma-4-12b-qat", "ctx_max": 262144, "instances": [],
             "reflexion": options}
    with _Detour(ia_view.lmstudio_api, server_responds=lambda url: True,
                 is_loaded=lambda url, m: True,
                 loaded_context=lambda url, m: 16384), \
         _Detour(lm, fiche=lambda url, m: fiche):
        p = ia_view._LMStudioPage()
        p._model_combo.clear()
        p._model_combo.addItems(["google/gemma-4-12b-qat"])
        p.refresh_availability()
    return p


# ── Ollama ────────────────────────────────────────────────────────────────

def test_ollama_the_switch_follows_the_setting_for_a_model_that_thinks():
    lang_manager.set_language("fr")
    s = TRANSLATIONS["fr"]
    for voulu in (False, True):
        _reglage("ollama_think", voulu)
        t = _ollama(GEMMA4)._think
        assert t.est_actif() and t.est_coche() is voulu
        assert t.aide() == s.think_help
    _reglage("ollama_think", False)


def test_ollama_a_model_that_cannot_think_greys_the_switch_and_says_why():
    lang_manager.set_language("fr")
    _reglage("ollama_think", True)
    t = _ollama(LLAMA31)._think
    _reglage("ollama_think", False)
    assert not t.est_actif() and not t.est_coche()
    assert t.aide() == TRANSLATIONS["fr"].think_unavailable


def test_ollama_ticking_saves_and_tells_the_engine():
    _reglage("ollama_think", False)
    sec = _ollama(GEMMA4)
    vus = []
    sec.reglage_change.connect(lambda: vus.append(1))
    sec._think._case.click()
    assert ai_config.ollama_think is True and vus == [1]
    sec._think._case.click()
    assert ai_config.ollama_think is False and vus == [1, 1]


def test_refreshing_the_page_never_saves_anything():
    """`regler` n'emet rien : relire la page n'ecrit pas la configuration."""
    _reglage("ollama_think", True)
    sec = _ollama(GEMMA4)
    vus = []
    sec._think.bascule.connect(vus.append)
    with _Detour(ia_view, is_server_running=lambda: True,
                 is_model_available=lambda m: True), \
         _Detour(om, en_memoire=lambda nom: None, contexte_max=lambda nom: 131072,
                 reflexion_modele=lambda nom: LLAMA31):
        sec.refresh_availability()
    _reglage("ollama_think", False)
    assert vus == [] and not sec._think.est_coche()


# ── LM Studio ─────────────────────────────────────────────────────────────

def test_lmstudio_a_model_that_allows_both_follows_the_setting():
    _reglage("lmstudio_think", False)
    t = _lmstudio(["off", "on"])._think
    assert t.est_actif() and not t.est_coche()


def test_lmstudio_a_model_that_always_thinks_is_greyed_on():
    lang_manager.set_language("fr")
    _reglage("lmstudio_think", False)
    t = _lmstudio(("on",))._think
    assert not t.est_actif() and t.est_coche()
    assert t.aide() == TRANSLATIONS["fr"].think_always


def test_lmstudio_a_model_without_reasoning_is_greyed_off():
    _reglage("lmstudio_think", True)
    t = _lmstudio(())._think
    _reglage("lmstudio_think", False)
    assert not t.est_actif() and not t.est_coche()


def test_lmstudio_ticking_saves_and_rebuilds_the_engine():
    """Le moteur LM Studio porte le reglage depuis sa construction :
    `reglage_change` le fait recreer."""
    _reglage("lmstudio_think", False)
    p = _lmstudio(("off", "on"))
    vus = []
    p.reglage_change.connect(lambda: vus.append(1))
    p._think._case.click()
    assert ai_config.lmstudio_think is True and vus == [1]
    _reglage("lmstudio_think", False)


def test_the_label_is_translated_in_four_languages():
    textes = set()
    for code in ("fr", "en", "es", "it"):
        lang_manager.set_language(code)
        p = _lmstudio(("off", "on"))
        textes.add(p._think._case.text())
        assert p._think._case.text() == TRANSLATIONS[code].think_label
    lang_manager.set_language("fr")
    assert len(textes) == 4, textes


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_")]


def main() -> int:
    echecs = 0
    try:
        for t in TESTS:
            try:
                t()
                print(f"OK   {t.__name__}")
            except Exception as e:
                echecs += 1
                print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    finally:
        aicfg.CONFIG_PATH = _VRAI_CHEMIN
    print(f"\n{len(TESTS) - echecs}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if echecs else 0)


if __name__ == "__main__":
    main()
