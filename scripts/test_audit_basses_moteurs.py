"""Constats de gravite BASSE de l'audit du 2026-11-06, zone « moteurs ».

Chaque test rejoue le scenario du constat. Aucun reseau : les fonctions qui
parleraient a Ollama ou LM Studio sont remplacees, le trousseau est un
dictionnaire, et `config.json` est detourne vers un dossier temporaire AVANT
toute ecriture (le vrai chemin est la constante de module `CONFIG_PATH`).

Run: python scripts/test_audit_basses_moteurs.py
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

_store: dict = {}
_fk = types.ModuleType("keyring")
_fk.get_password = lambda s, k: _store.get((s, k))
_fk.set_password = lambda s, k, v: _store.__setitem__((s, k), v)
_fk.delete_password = lambda s, k: _store.pop((s, k), None)
sys.modules["keyring"] = _fk

from PyQt6.QtWidgets import QApplication  # noqa: E402

_APP = QApplication.instance() or QApplication(sys.argv)

import ui.ai_config as _cfg_mod  # noqa: E402
from ui.ai_config import ai_config  # noqa: E402

# ⛔ Avant toute ecriture : la configuration de l'utilisateur n'est jamais
# touchee.
_TMP = Path(tempfile.mkdtemp())
_cfg_mod.CONFIG_PATH = _TMP / "config.json"

# Ni serveur Ollama, ni LM Studio, ni PowerShell.
import ui.ia_view as ia_view  # noqa: E402
ia_view.is_server_running = lambda: False
ia_view.is_installed = lambda: True
ia_view.is_process_running = lambda: False
ia_view.list_local_models = lambda: []
ia_view.lmstudio_api.server_responds = lambda url, **k: False
ia_view.lmstudio_api.chat_models = lambda url, **k: []
import ui.debordement as _db  # noqa: E402
_db.lmstudio_deborde = lambda ctx: None
import ui.ollama_models as _om  # noqa: E402
_om.reflexion_modele = lambda nom: None


# ── ollama_backend ──────────────────────────────────────────────────────

def test_ollama_show_failure_is_not_cached():
    """L'app demarre avant Ollama : un echec de /api/show ne doit pas rester
    en cache pour toute la vie du moteur du chat."""
    import ui.ai_backends.ollama_backend as ob
    vrai = ob._post
    reponses = [RuntimeError("refused"),
                {"model_info": {"g.context_length": 131072}}]

    def faux(path, payload, timeout=None, **k):
        r = reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r
    ob._post = faux
    try:
        b = ob.OllamaBackend("gemma4:e2b")
        assert b._show() == {}
        assert b._contexte_max_connu() == 131072, \
            "l'echec du premier /api/show est reste en cache"
    finally:
        ob._post = vrai


def test_ollama_loaded_context_matches_what_the_page_expects():
    """Maximum non multiple de 1 024 : le moteur chargeait a 200 000, la page
    attendait 199 680, d'ou « Recharger » sans fin."""
    import ui.ai_backends.ollama_backend as ob
    from ui import contexte
    b = ob.OllamaBackend("x")
    b._show_cache = {"model_info": {"g.context_length": 200000}}
    avant = ai_config._data.get("ollama_num_ctx")
    ai_config._data["ollama_num_ctx"] = 262144          # en memoire
    try:
        charge = b._contexte_regle()
        voulu = contexte.ramener(262144, 200000)
        assert contexte.accorde(charge, voulu), (charge, voulu)
        # Un modele sous le plancher garde son maximum.
        b._show_cache = {"model_info": {"g.context_length": 8192}}
        assert b._contexte_regle() == 8192
    finally:
        ai_config._data["ollama_num_ctx"] = avant


# ── openai_compat ───────────────────────────────────────────────────────

class _ReponseLente:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        raise TimeoutError("timed out")


def test_a_timeout_during_read_is_a_network_error():
    import ui.ai_backends.openai_compat as oc
    t = oc._UrllibTransport()
    t._coupure = types.SimpleNamespace(urlopen=lambda req, timeout=None: _ReponseLente())
    try:
        t.post_json("http://x/v1/chat/completions", {}, {}, 1)
    except ConnectionError:
        pass
    else:
        raise AssertionError("post_json n'a pas leve ConnectionError")
    vrai = oc.urllib.request.urlopen
    oc.urllib.request.urlopen = lambda req, timeout=None: _ReponseLente()
    try:
        t.get_json("http://x/v1/models", {}, 1)
    except ConnectionError:
        pass
    else:
        raise AssertionError("get_json n'a pas leve ConnectionError")
    finally:
        oc.urllib.request.urlopen = vrai


def test_inline_reasoning_is_removed_from_generated_code():
    import ui.ai_backends.openai_compat as oc

    class _T:
        def post_json(self, url, headers, payload, timeout):
            return {"choices": [{"finish_reason": "stop", "message": {
                "content": "<think>Okay, the user wants\na blink.</think>\n"
                           "#include <Arduino.h>\nvoid setup(){}\nvoid loop(){}"}}]}
    b = oc.OpenAICompatBackend("http://x/v1", "k", "m", backend_id="groq",
                               label="Groq", transport=_T())
    code = b.generate_code("blink", "Arduino Uno")
    assert "<think>" not in code and "Okay" not in code, code
    assert code.startswith("#include"), code
    # Une chaine du sketch qui contient le mot n'est pas touchee.
    assert oc._sans_reflexion('x = "<think>a</think>";') == 'x = "<think>a</think>";'


# ── ai_config ───────────────────────────────────────────────────────────

def test_a_failed_save_leaves_the_previous_config_intact():
    """Une ecriture coupee en route ne doit pas laisser config.json tronque."""
    path = _cfg_mod.CONFIG_PATH
    path.write_text(json.dumps({"ai_backend": "ollama", "ollama_model": "a"}),
                    encoding="utf-8")
    avant = ai_config._data.get("custom_model")
    ai_config._data["custom_model"] = object()       # json.dump echoue en route
    try:
        ai_config._save_backend()
    finally:
        ai_config._data["custom_model"] = avant
    data = json.loads(path.read_text(encoding="utf-8"))   # lisible
    assert data["ollama_model"] == "a", data
    restes = [p.name for p in path.parent.iterdir() if p.name != "config.json"]
    assert not restes, restes


# ── chatgpt_auth ────────────────────────────────────────────────────────

class _Coffre:
    def __init__(self, texte):
        self.texte = texte

    def lire(self):
        return self.texte

    def ecrire(self, t):
        self.texte = t

    def effacer(self):
        self.texte = ""


def test_a_rate_limited_refresh_keeps_the_credentials():
    import ui.chatgpt_auth as auth
    rec = {"access_token": "a", "refresh_token": "r", "expires_at": 0,
           "client_id": "c"}
    for statut in (429, 408):
        coffre = _Coffre(json.dumps(rec))
        s = auth.Session(coffre=coffre, poster=lambda *a, st=statut: (st, {}),
                         horloge=lambda: 1000.0)
        assert s.jeton() is None
        assert s.panne_reseau, statut
        assert json.loads(coffre.texte).get("refresh_token") == "r", \
            f"un {statut} a efface les identifiants"
    # Un vrai refus deconnecte toujours.
    coffre = _Coffre(json.dumps(rec))
    s = auth.Session(coffre=coffre, poster=lambda *a: (400, {}),
                     horloge=lambda: 1000.0)
    assert s.jeton() is None and not s.panne_reseau
    assert not json.loads(coffre.texte).get("refresh_token")


# ── lmstudio_models_dialog ─────────────────────────────────────────────

def test_a_suggestion_installed_under_another_name_is_recognised():
    from ui.lmstudio_models_dialog import _installe_de
    installes = [{"cle": "gemma-3-4b-it"}, {"cle": "gemma-3-12b"}]
    assert _installe_de("google/gemma-3-4b", installes)["cle"] == "gemma-3-4b-it"
    assert _installe_de("google/gemma-3-1b", installes) is None
    assert _installe_de("gemma-3-12b", installes)["cle"] == "gemma-3-12b"


# ── ia_view ─────────────────────────────────────────────────────────────

def test_without_a_key_the_model_field_keeps_its_no_key_prompt():
    from ui.i18n import lang_manager
    _store.clear()
    sec = ia_view._CloudSection()
    s = lang_manager.current
    assert sec._model_combo.lineEdit().placeholderText() == \
        s.ia_model_placeholder_no_key


def test_a_stale_probe_does_not_stop_the_live_one():
    sec = ia_view._CloudSection()
    pid = sec.selected_provider_id()
    sec._model_combo.setCurrentText("B")
    sec._sondes_en_vol |= {(pid, "A"), (pid, "B")}
    sec._start_checking_animation()
    sec._on_model_probed(pid, "A", True, "")
    assert sec._probe_timer is not None, \
        "la sonde perimee a coupe l'animation de celle en cours"
    # Changer de fournisseur arrete une animation qui ne le concerne plus.
    sec._sondes_en_vol.clear()
    sec._reload_fields()
    assert sec._probe_timer is None
    sec._stop_checking_animation()


def test_a_running_worker_is_detached_at_exit():
    import time
    from PyQt6 import sip
    from PyQt6.QtCore import QThread

    class _Lent(QThread):
        def run(self):
            time.sleep(8)
    sec = ia_view._CloudSection()
    remplace, dernier = _Lent(sec), _Lent(sec)
    for w in (remplace, dernier):
        sec._workers_vivants.add(w)
        w.start()
    sec._models_worker = dernier
    sec._stop_worker()
    for w in (remplace, dernier):
        assert w.parent() is None, "fil encore enfant de la fenetre"
        assert not sip.ispyowned(w)
    sec.deleteLater()
    for w in (remplace, dernier):
        w.wait()


def test_choosing_an_ollama_model_does_not_talk_about_a_key():
    from ui.i18n import lang_manager
    sec = ia_view._BackendSection("ollama")
    avant = ai_config._data.get("ollama_model")
    try:
        sec._on_model_selected("gemma3:4b")
    finally:
        ai_config._data["ollama_model"] = avant
    txt = sec._lbl_model_status.text()
    s = lang_manager.current
    assert s.ia_key_saved not in txt and s.ia_saved in txt, txt


def test_an_active_lmstudio_is_measured_at_startup():
    from ui.ai_status import ai_status
    avant = ai_config._data.get("ai_backend")
    ai_config._data["ai_backend"] = "lmstudio"          # en memoire
    try:
        v = ia_view.IAView()
        page = v._local.pages["lmstudio"]
        for _ in range(20):
            _APP.processEvents()
        assert page._availability_state is not None, \
            "LM Studio actif n'est pas mesure avant l'ouverture de l'onglet"
        assert ai_status.state == "lmstudio_server_down", ai_status.state
    finally:
        ai_config._data["ai_backend"] = avant


TESTS = [
    test_ollama_show_failure_is_not_cached,
    test_ollama_loaded_context_matches_what_the_page_expects,
    test_a_timeout_during_read_is_a_network_error,
    test_inline_reasoning_is_removed_from_generated_code,
    test_a_failed_save_leaves_the_previous_config_intact,
    test_a_rate_limited_refresh_keeps_the_credentials,
    test_a_suggestion_installed_under_another_name_is_recognised,
    test_without_a_key_the_model_field_keeps_its_no_key_prompt,
    test_a_stale_probe_does_not_stop_the_live_one,
    test_a_running_worker_is_detached_at_exit,
    test_choosing_an_ollama_model_does_not_talk_about_a_key,
    test_an_active_lmstudio_is_measured_at_startup,
]


def main():
    try:
        sys.stdout.reconfigure(errors="replace")    # « ✓ » sur une console cp1252
    except Exception:
        pass
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
