"""La pastille « thinking » du chat et de la generation (2026-11-07).

Decisions de l'auteur : un seul reglage par moteur, COUPLE entre le chat, la
generation et l'onglet Modele IA ; pastille pleine (active), vide et barree
(desactive), grisee (pas de mode) ; « thinking » jamais traduit ; P3 (le clic
fait defiler les niveaux, un anneau les montre) dans le chat et la
generation, P4 (curseur a crans) dans l'onglet.

Aucun reseau : la capacite du modele est posee dans le cache, la
configuration n'est modifiee qu'EN MEMOIRE (`ai_config._data`), jamais
ecrite.
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

from ui import reflexion  # noqa: E402
from ui.ai_config import ai_config  # noqa: E402
from ui.i18n import TRANSLATIONS, lang_manager  # noqa: E402
from ui.thinking_etat import thinking_etat  # noqa: E402

_CLES = ("ai_backend", "ollama_model", "ollama_think", "ollama_think_level",
         "lmstudio_think", "lmstudio_think_level", "lmstudio_model",
         "chatgpt_reasoning")


class _Config:
    """Reglages en memoire, restaures a la sortie ; `_save_backend` neutralise
    pour que rien n'atteigne config.json."""

    def __init__(self, **v):
        self.v, self.avant = v, {}

    def __enter__(self):
        self.avant = {k: ai_config._data.get(k) for k in _CLES}
        self.save = ai_config._save_backend
        ai_config._save_backend = lambda *a, **k: None
        ai_config._data.update(self.v)
        return self

    def __exit__(self, *a):
        ai_config._data.update(self.avant)
        ai_config._save_backend = self.save


def _cap(moteur, modele, cap):
    thinking_etat._caps[(moteur, modele)] = cap


def test_states_and_untranslated_word():
    with _Config(ai_backend="ollama", ollama_model="m", ollama_think=False):
        _cap("ollama", "m", reflexion.Capacite(True, True, True))
        assert thinking_etat.etat() == "off"
        ai_config._data["ollama_think"] = True
        assert thinking_etat.etat() == "on"
        _cap("ollama", "m", reflexion.Capacite(False, True, None))
        assert thinking_etat.etat() == "absent"
    with _Config(ai_backend="chatgpt"):
        assert thinking_etat.etat() == "toujours"
    with _Config(ai_backend="openai"):
        assert thinking_etat.etat() == "non_reglable"
    for code, s in TRANSLATIONS.items():
        for k in ("think_pill_on", "think_pill_off", "think_pill_absent",
                  "think_pill_always", "think_pill_engine"):
            assert "thinking" in getattr(s, k), (code, k)


def test_a_click_toggles_a_model_without_levels():
    with _Config(ai_backend="lmstudio", lmstudio_model="g", lmstudio_think=False):
        _cap("lmstudio", "g", reflexion.Capacite(True, True, "on"))
        thinking_etat.basculer()
        assert ai_config.lmstudio_think is True and thinking_etat.etat() == "on"
        thinking_etat.basculer()
        assert ai_config.lmstudio_think is False


def test_p3_cycles_off_then_levels_then_off():
    niveaux = ("low", "medium", "high")
    with _Config(ai_backend="ollama", ollama_model="o", ollama_think=False,
                 ollama_think_level=""):
        _cap("ollama", "o", reflexion.Capacite(True, True, True, niveaux))
        vus = []
        for _ in range(5):
            thinking_etat.basculer()
            vus.append(thinking_etat.niveau() or thinking_etat.etat())
        assert vus == ["low", "medium", "high", "off", "low"], vus


def test_p3_loops_levels_when_the_model_cannot_be_switched_off():
    with _Config(ai_backend="chatgpt", chatgpt_reasoning="high"):
        thinking_etat.basculer()
        assert ai_config.chatgpt_reasoning == "low"
        thinking_etat.basculer()
        assert ai_config.chatgpt_reasoning == "medium"


def test_absent_and_engine_without_setting_are_not_clickable():
    with _Config(ai_backend="ollama", ollama_model="x", ollama_think=False):
        _cap("ollama", "x", reflexion.Capacite(False, True, None))
        thinking_etat.basculer()
        assert ai_config.ollama_think is False
    with _Config(ai_backend="openai"):
        assert not thinking_etat.cliquable()


def test_the_chat_and_the_generation_pills_stay_coupled():
    from ui.thinking_pastille import PastilleThinking
    lang_manager.set_language("fr")
    with _Config(ai_backend="ollama", ollama_model="c", ollama_think=False):
        _cap("ollama", "c", reflexion.Capacite(True, True, True))
        chat, gen = PastilleThinking(), PastilleThinking()
        chat.click()
        _APP.processEvents()
        assert ai_config.ollama_think is True
        assert gen.toolTip() == chat.toolTip() == "thinking activé"


def test_the_level_goes_into_the_tooltip():
    from ui.thinking_pastille import infobulle
    with _Config(ai_backend="chatgpt", chatgpt_reasoning="medium"):
        assert infobulle(TRANSLATIONS["fr"]).endswith("· Moyen")


def test_ollama_sends_the_chosen_level():
    cap = reflexion.Capacite(True, False, "medium", ("low", "medium", "high"))
    assert reflexion.ollama_think(cap, True, "high") == "high"
    assert reflexion.ollama_think(cap, True, "") == "medium"
    assert reflexion.ollama_think(cap, True, "inconnu") == "medium"


def test_named_levels_are_read_and_ordered():
    cap = reflexion.depuis_ollama({"thinking": {"values": ["high", "low", "medium"],
                                                "default": "medium"}})
    assert cap.niveaux == ("low", "medium", "high") and not cap.peut_couper


def test_the_ia_tab_level_slider_is_always_shown_greyed_without_levels():
    """Invisible, il passait pour un oubli (retour de l'auteur, 2026-11-07) :
    toujours affiche, grise sans niveaux, avec la raison."""
    from ui.thinking_niveaux import CurseurNiveaux
    lang_manager.set_language("fr")
    c = CurseurNiveaux()
    c.regler((), "")
    assert not c.isHidden() and not c.est_actif()
    assert c.aide() == TRANSLATIONS["fr"].think_level_none
    c.regler(("low", "medium", "high"), "high")
    assert c.est_actif() and c.valeur() == "high" and c.aide() == ""


# ── TODO #125 : les niveaux de LM Studio (gpt-oss), mesures le 2026-11-07 ──
# Fiche reelle : `capabilities.reasoning` = {"allowed_options": ["low",
# "medium", "high"], "default": "low"}. L'API compatible OpenAI respecte
# `reasoning_effort` low/medium/high (67 / 220-268 / 312-552 tokens).

def test_lmstudio_reads_named_levels_from_the_card():
    cap = reflexion.depuis_lmstudio(("low", "medium", "high"))
    assert cap.niveaux == ("low", "medium", "high")
    assert cap.peut_reflechir and not cap.peut_couper   # gpt-oss ne se coupe pas
    gemma = reflexion.depuis_lmstudio(("off", "on"))
    assert gemma.niveaux == () and gemma.peut_couper


def test_lmstudio_sends_the_chosen_level_and_never_an_unknown_one():
    cap = reflexion.depuis_lmstudio(("low", "medium", "high"))
    assert reflexion.lmstudio_champs(cap, True, "high") == {"reasoning_effort": "high"}
    assert reflexion.lmstudio_champs(cap, True, "") == {"reasoning_effort": "low"}
    assert reflexion.lmstudio_champs(cap, True, "xtrem") == {"reasoning_effort": "low"}
    # ne se coupe pas : « desactive » n'envoie pas « none » (qui reviendrait a low)
    assert reflexion.lmstudio_champs(cap, False, "high") == {"reasoning_effort": "high"}
    gemma = reflexion.depuis_lmstudio(("off", "on"))
    assert reflexion.lmstudio_champs(gemma, False, "high") == {"reasoning_effort": "none"}
    assert reflexion.lmstudio_champs(gemma, True, "high") == {}


def test_the_lmstudio_pill_cycles_levels():
    with _Config(ai_backend="lmstudio", lmstudio_model="oss",
                 lmstudio_think=True, lmstudio_think_level="low"):
        ai_config._data["lmstudio_think_level"] = "low"
        _cap("lmstudio", "oss", reflexion.depuis_lmstudio(("low", "medium", "high")))
        assert thinking_etat.etat() == "toujours" and thinking_etat.niveau() == "low"
        thinking_etat.basculer()
        assert ai_config.lmstudio_think_level == "medium"
        thinking_etat.basculer(); thinking_etat.basculer()
        assert ai_config.lmstudio_think_level == "low", "boucle, jamais desactive"


TESTS = [v for k, v in dict(globals()).items() if k.startswith("test_")]

if __name__ == "__main__":
    failed = 0
    for t in TESTS:
        try:
            t(); print("PASS", t.__name__)
        except Exception as e:  # noqa: BLE001
            failed += 1; print("FAIL", t.__name__, repr(e)[:300])
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} OK")
    sys.stdout.flush()
    os._exit(1 if failed else 0)
