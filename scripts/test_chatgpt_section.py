"""La section « Compte ChatGPT » et son cablage (TODO #122).

⛔ La configuration est REMPLACEE par un double en memoire
(`ui.chatgpt_section.ai_config`) : marquer la fenetre d'accueil comme vue
ecrirait `config.json` de l'utilisateur. La session est un bouchon dont
`jeton()` rend None, si bien que relire les modeles ne part JAMAIS sur le
reseau. Le runner verifie par empreinte que config et session sont intactes.

Run: python scripts/test_chatgpt_section.py
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

import ui.chatgpt_section as sec  # noqa: E402
from ui.chatgpt_auth import PAGE_USAGE  # noqa: E402
from ui.i18n import TRANSLATIONS, lang_manager  # noqa: E402


class _Config:
    def __init__(self, modele="", accueil=False, actif="ollama", niveau="medium"):
        self.chatgpt_model = modele
        self.chatgpt_welcome_shown = accueil
        self.backend_id = actif
        self.chatgpt_reasoning = niveau


class _Session:
    def __init__(self, compte=None, resultat=None):
        self._compte = compte
        self.resultat = resultat or {"ok": True, "email": "e@x.fr", "forfait": True}
        self.appels_jeton = 0
        self.deconnexions = 0

    def compte(self):
        return self._compte

    def jeton(self, *, forcer=False):
        self.appels_jeton += 1
        return None                      # jamais de reseau

    def connecter(self, ouvrir, *, page_html, annule=lambda: False, delai=300):
        self.page_html = page_html
        if self.resultat.get("ok"):
            self._compte = {"email": self.resultat["email"],
                            "forfait": self.resultat["forfait"]}
        return self.resultat

    def deconnecter(self):
        self.deconnexions += 1
        self._compte = None


def _attendre(cond, delai=5.0):
    fin = time.time() + delai
    while time.time() < fin:
        _APP.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return False


def _section(session, config, accueils=None):
    sec.ai_config = config
    compteur = accueils if accueils is not None else []
    return sec.ChatGPTSection(session=session, ouvrir=lambda u: None,
                              accueil=lambda: compteur.append(1))


_VRAIE_CONFIG = sec.ai_config


# ── cablage ───────────────────────────────────────────────────────────────

def test_chatgpt_is_a_known_backend_so_the_migration_leaves_it_alone():
    """⛔ Sans cela, la migration generique du #118 ramenait l'utilisateur
    sur Ollama A CHAQUE DEMARRAGE."""
    from ui.ai_backends.factory import known_backend_ids, backend_requires_key
    from ui.ai_config import migre_backend_retire
    assert "chatgpt" in known_backend_ids()
    assert migre_backend_retire("chatgpt") == ("chatgpt", False)
    assert backend_requires_key("chatgpt") is False


def test_the_factory_builds_the_plan_backend():
    from ui.ai_backends.factory import get_backend_instance
    from ui.ai_backends.chatgpt_plan import ChatGPTPlanBackend
    assert isinstance(get_backend_instance("chatgpt"), ChatGPTPlanBackend)


def test_the_status_dot_knows_the_green_state():
    from ui.ai_status import KINDS_OK
    assert "chatgpt_ok" in KINDS_OK


def test_the_uninstall_purge_includes_the_sign_in_record():
    import inspect
    from ui.ai_config import AIConfig
    src = inspect.getsource(AIConfig)
    # Depuis le decoupage (limite de Windows), la purge efface TOUS les
    # morceaux, par la liste que tient chatgpt_auth.
    assert "noms_dans_le_trousseau" in src, "la connexion survivrait a la desinstallation"


# ── les etats de la section ──────────────────────────────────────────────

def test_signed_out_shows_only_the_official_button():
    s = TRANSLATIONS["fr"]
    lang_manager.set_language("fr")
    w = _section(_Session(), _Config())
    assert w._availability_state[0] == "chatgpt_signed_out"
    assert not w._btn_connecter.isHidden()
    assert w._btn_connecter.text() == s.ia_chatgpt_connect
    assert w._zone_modele.isHidden() and w._lbl_forfait.isHidden()


def test_signed_in_without_plan_usage_offers_to_sign_in_again():
    s = TRANSLATIONS["fr"]
    w = _section(_Session({"email": "e@x.fr", "forfait": False}), _Config())
    assert w._availability_state[0] == "chatgpt_no_plan"
    assert not w._btn_connecter.isHidden()
    assert s.ia_chatgpt_no_plan in w._lbl_etat.text()
    assert w._zone_modele.isHidden()


def test_signed_in_shows_the_plan_label_with_manage_usage_near_the_model():
    s = TRANSLATIONS["fr"]
    w = _section(_Session({"email": "e@x.fr", "forfait": True}), _Config())
    assert w._availability_state == ("chatgpt_no_model", "e@x.fr")
    assert not w._zone_modele.isHidden() and not w._lbl_forfait.isHidden()
    assert s.ia_chatgpt_using_plan in w._lbl_forfait.text()
    assert PAGE_USAGE in w._lbl_forfait.text()
    assert w._btn_connecter.isHidden()
    w2 = _section(_Session({"email": "e@x.fr", "forfait": True}), _Config(modele="gpt-x"))
    assert w2._availability_state[0] == "chatgpt_ok"
    assert w2._combo.currentText() == "gpt-x"


def test_nothing_touches_the_network_at_construction():
    sess = _Session({"email": "e@x.fr", "forfait": True})
    w = _section(sess, _Config(modele="gpt-x"))
    w.load_key()
    assert sess.appels_jeton == 0, "la vue est construite au demarrage de l'app"


# ── connexion, accueil, deconnexion ──────────────────────────────────────

def test_a_first_sign_in_shows_the_welcome_once_and_activates():
    accueils = []
    config = _Config()
    w = _section(_Session(), config, accueils)
    activations = []
    w.connecte.connect(lambda: activations.append(1))
    w._btn_connecter.click()
    assert _attendre(lambda: activations), "aucune activation apres la connexion"
    assert accueils == [1] and config.chatgpt_welcome_shown is True
    assert "Promptuino" in w._session.page_html
    w._btn_connecter.show()
    w._connecter()
    assert _attendre(lambda: len(activations) == 2)
    assert accueils == [1], "la fenetre d'accueil ne s'affiche qu'UNE fois"


def test_a_timeout_is_said_and_a_cancel_is_silent():
    s = TRANSLATIONS["fr"]
    w = _section(_Session(resultat={"ok": False, "erreur": "delai", "message": ""}), _Config())
    w._connecter()
    assert _attendre(lambda: not w._en_connexion)
    assert s.ia_chatgpt_err_timeout in w._lbl_etat.text()
    w2 = _section(_Session(resultat={"ok": False, "erreur": "annule", "message": ""}), _Config())
    w2._connecter()
    assert _attendre(lambda: not w2._en_connexion)
    assert w2._lbl_etat.text() == ""


def test_a_refused_sign_in_says_it_simply_never_openais_raw_words():
    """Consigne de l'auteur (2026-11-06) : « pas besoin d'afficher les
    erreurs ». Vu en QA : « OpenAI a refuse la connexion : invalid_grant ».
    Un refus a l'autorisation (compte gratuit, ou « Annuler » chez OpenAI)
    dit qu'il faut un forfait ; un echec de l'echange invite a reessayer."""
    for code in ("fr", "en", "es", "it"):
        lang_manager.set_language(code)
        s = TRANSLATIONS[code]
        for erreur, brut, attendu in (
                ("refus", "access_denied", s.ia_chatgpt_err_refused),
                ("echange", "invalid_grant", s.ia_chatgpt_err_exchange),
                ("echange", "", s.ia_chatgpt_err_exchange)):
            w = _section(_Session(resultat={"ok": False, "erreur": erreur,
                                            "message": brut}), _Config())
            w._connecter()
            assert _attendre(lambda: not w._en_connexion)
            texte = w._lbl_etat.text()
            assert attendu in texte, (code, erreur, texte)
            assert (not brut or brut not in texte) and "{msg}" not in texte, texte
    lang_manager.set_language("fr")


def test_signing_out_returns_to_the_button():
    sess = _Session({"email": "e@x.fr", "forfait": True})
    w = _section(sess, _Config(modele="gpt-x"))
    w._btn_deconnecter.click()
    assert sess.deconnexions == 1
    assert w._availability_state[0] == "chatgpt_signed_out"
    assert not w._btn_connecter.isHidden()


def test_it_builds_in_the_four_languages():
    for code in TRANSLATIONS:
        lang_manager.set_language(code)
        w = _section(_Session(), _Config())
        assert w.radio.text() == TRANSLATIONS[code].ia_chatgpt_title, code
    lang_manager.set_language("fr")


def test_the_iaview_offers_three_choices():
    sec.ai_config = _VRAIE_CONFIG
    from ui.ia_view import IAView
    v = IAView()
    assert v._sections["chatgpt"] is v._chatgpt
    assert v._chatgpt.radio in v._group.buttons()


# ── le niveau de reflexion (TODO #123) ───────────────────────────────────

_CONNECTE = {"email": "e@x.fr", "forfait": True}


def test_the_reasoning_slider_shows_the_setting_only_with_a_plan():
    lang_manager.set_language("fr")
    s = TRANSLATIONS["fr"]
    w = _section(_Session(compte=_CONNECTE), _Config(modele="gpt-6.1-sol", niveau="high"))
    assert not w._zone_reflexion.isHidden()
    assert w._curseur.value() == 2
    assert [l.text() for l in w._lbl_crans] == [s.chatgpt_level_low,
                                                 s.chatgpt_level_medium,
                                                 s.chatgpt_level_high]
    assert w._lbl_reflexion_aide.text() == s.chatgpt_reasoning_help
    w2 = _section(_Session(compte=None), _Config())
    assert w2._zone_reflexion.isHidden()


def test_moving_the_slider_saves_and_asks_for_a_new_engine():
    config = _Config(modele="gpt-6.1-sol")
    w = _section(_Session(compte=_CONNECTE), config)
    vus = []
    w.reglage_change.connect(lambda: vus.append(1))
    w._curseur.setValue(0)                      # comme le clavier
    assert config.chatgpt_reasoning == "low" and vus == [1]
    w._rendre()                                 # relire n'ecrit rien
    assert vus == [1]


def test_a_refused_level_is_said_under_the_slider():
    import ui.ai_backends.chatgpt_plan as cp
    lang_manager.set_language("fr")
    cp._REFLEXION_REFUSEE.add("gpt-6.1-sol")
    try:
        w = _section(_Session(compte=_CONNECTE), _Config(modele="gpt-6.1-sol"))
        assert w._lbl_reflexion_aide.text() == TRANSLATIONS["fr"].chatgpt_reasoning_refused
    finally:
        cp._REFLEXION_REFUSEE.clear()


TESTS = [
    test_the_reasoning_slider_shows_the_setting_only_with_a_plan,
    test_moving_the_slider_saves_and_asks_for_a_new_engine,
    test_a_refused_level_is_said_under_the_slider,
    test_chatgpt_is_a_known_backend_so_the_migration_leaves_it_alone,
    test_the_factory_builds_the_plan_backend,
    test_the_status_dot_knows_the_green_state,
    test_the_uninstall_purge_includes_the_sign_in_record,
    test_signed_out_shows_only_the_official_button,
    test_signed_in_without_plan_usage_offers_to_sign_in_again,
    test_signed_in_shows_the_plan_label_with_manage_usage_near_the_model,
    test_nothing_touches_the_network_at_construction,
    test_a_first_sign_in_shows_the_welcome_once_and_activates,
    test_a_timeout_is_said_and_a_cancel_is_silent,
    test_a_refused_sign_in_says_it_simply_never_openais_raw_words,
    test_signing_out_returns_to_the_button,
    test_it_builds_in_the_four_languages,
    test_the_iaview_offers_three_choices,
]


def _empreinte() -> str:
    d = Path.home() / "Documents" / "Promptuino"
    h = hashlib.md5()
    for nom in ("config.json", "session.json"):
        f = d / nom
        h.update(f.read_bytes() if f.exists() else b"-")
    return h.hexdigest()


def main():
    avant = _empreinte()
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
        finally:
            sec.ai_config = _VRAIE_CONFIG
    if _empreinte() != avant:
        failed += 1
        print("FAIL la configuration ou la session de l'utilisateur a ete modifiee")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
