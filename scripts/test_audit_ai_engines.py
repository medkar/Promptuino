"""Audit du 2026-11-06 : moteurs IA (ui/ai_backends/*, ui/ai_config.py).

Un test par constat corrige. Configuration ISOLEE : la constante de module
`CONFIG_PATH` est detournee vers un dossier temporaire ; keyring remplace par
un magasin en memoire.

Run : python scripts/test_audit_ai_engines.py
"""
from __future__ import annotations
import json, os, sys, tempfile, types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

_store: dict = {}
_fk = types.ModuleType("keyring")
_fk.get_password = lambda s, k: _store.get((s, k))
_fk.set_password = lambda s, k, v: _store.__setitem__((s, k), v)
_fk.delete_password = lambda s, k: _store.pop((s, k), None)
sys.modules["keyring"] = _fk

import ui.ai_config as aicfg

_VRAI_CHEMIN = aicfg.CONFIG_PATH


# ── 8. migration d'un backend retire : rien d'autre n'est perdu ─────────

def test_migration_keeps_the_other_settings_on_disk():
    with tempfile.TemporaryDirectory() as tmp:
        chemin = Path(tmp) / "config.json"
        chemin.write_text(json.dumps({
            "ai_backend": "backend_inconnu_retire",
            "ollama_model": "llama3.1:8b",
            "models": {"openai": "gpt-4o"},
            "custom_base_url": "http://x/v1",
            "lmstudio_model": "mon-modele",
            "ollama_num_ctx": 32768,
            "ollama_think": True,
        }), encoding="utf-8")
        aicfg.CONFIG_PATH = chemin
        c = aicfg.AIConfig()
        assert c.backend_migre_depuis_retire is True
        sur_disque = json.loads(chemin.read_text(encoding="utf-8"))
        assert sur_disque["ai_backend"] == "ollama", sur_disque
        assert sur_disque["ollama_model"] == "llama3.1:8b", sur_disque
        assert sur_disque["models"] == {"openai": "gpt-4o"}, sur_disque
        assert sur_disque["custom_base_url"] == "http://x/v1", sur_disque
        assert sur_disque["lmstudio_model"] == "mon-modele", sur_disque
        assert sur_disque["ollama_num_ctx"] == 32768, sur_disque
        assert sur_disque["ollama_think"] is True, sur_disque


# ── 9. la cle « custom » part avec les autres a la desinstallation ──────

def test_clear_all_api_keys_also_clears_the_custom_key():
    with tempfile.TemporaryDirectory() as tmp:
        aicfg.CONFIG_PATH = Path(tmp) / "config.json"
        c = aicfg.AIConfig()
        c.set_api_key("custom", "sk-distant")
        c.set_api_key("openai", "sk-abc")
        assert c.api_key("custom") == "sk-distant"
        c.clear_all_api_keys()
        assert c.api_key("custom") == "", "la cle custom a survecu"
        assert c.api_key("openai") == ""


# ── 1. ChatGPT : un renouvellement injoignable n'est pas « deconnecte » ─

class _Transport:
    def iter_sse(self, *a, **k):
        raise AssertionError("aucune requete ne doit partir sans jeton")
        yield  # pragma: no cover


def test_chatgpt_network_failure_on_refresh_is_not_signed_out():
    from ui.chatgpt_auth import Session
    from ui.ai_backends.chatgpt_plan import ChatGPTPlanBackend

    class _Coffre:
        def __init__(self):
            self.t = json.dumps({"access_token": "vieux", "refresh_token": "r",
                                 "client_id": "c", "expires_at": 0})
        def lire(self): return self.t
        def ecrire(self, t): self.t = t

    for statut in (None, 503):
        coffre = _Coffre()
        sess = Session(coffre=coffre, poster=lambda *a, st=statut: (st, {}),
                       horloge=lambda: 10_000.0)
        b = ChatGPTPlanBackend("gpt-x", session=sess, transport=_Transport())
        try:
            b._complete("", [{"role": "user", "content": "q"}])
            raise AssertionError("aucune erreur")
        except RuntimeError as e:
            msg = str(e)
        assert "pas connect" not in msg and "Not signed in" not in msg, msg
        assert "OpenAI" in msg, msg
        assert json.loads(coffre.t).get("refresh_token") == "r"   # gardes

    # Un vrai refus du serveur reste « deconnecte ».
    coffre = _Coffre()
    sess = Session(coffre=coffre, poster=lambda *a: (400, {"error": "x"}),
                   horloge=lambda: 10_000.0)
    b = ChatGPTPlanBackend("gpt-x", session=sess, transport=_Transport())
    try:
        b._complete("", [{"role": "user", "content": "q"}])
        raise AssertionError("aucune erreur")
    except RuntimeError as e:
        assert "pas connect" in str(e) or "Not signed in" in str(e), str(e)


# ── 2. ChatGPT : Annuler ferme aussi un flux SSE ────────────────────────

def test_cancel_closes_a_streaming_response():
    import urllib.request
    from ui.ai_backends.openai_compat import _UrllibTransport

    class _Rep:
        def __init__(self):
            self.fermee = False
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def close(self): self.fermee = True
        def __iter__(self):
            yield b"data: un\n"
            yield b"data: deux\n"

    rep = _Rep()
    try:
        t = _UrllibTransport()
        # Le transport ouvre par sa `Coupure` (socket coupable avant les
        # en-tetes, 2026-11-07) : c'est elle qu'on remplace.
        t._coupure.urlopen = lambda req, timeout=None: rep
        it = t.iter_sse("http://x/responses", {}, {}, None)
        assert next(it) == "data: un"
        assert not rep.fermee
        t.close_inflight()
        assert rep.fermee, "Annuler n'a rien ferme sur le flux"
        list(it)                      # va au bout
        t.close_inflight()            # plus rien en vol : sans effet
    finally:
        pass


# ── 3. LM Studio : la fenetre vue = le reglage BORNE au modele ──────────

def test_lmstudio_context_is_capped_to_the_model_maximum():
    from ui.ai_backends.lmstudio_backend import LMStudioBackend
    lectures = []

    def fiche_petite():
        lectures.append(1)
        return {"ctx_max": 32768, "reflexion": ()}

    b = LMStudioBackend("http://127.0.0.1:1234/v1", "m", reflexion=False,
                        context_window_hint=131072, fiche=fiche_petite)
    assert b.context_window_hint == 32768
    assert b.generation_context() == 32768
    assert b.effective_chat_context() == 32768
    assert len(lectures) == 1, "le maximum se lit une seule fois"
    # Maximum plus grand que le reglage : le reglage reste.
    b2 = LMStudioBackend("http://x/v1", "m", reflexion=False,
                         context_window_hint=20480,
                         fiche=lambda: {"ctx_max": 131072, "reflexion": ()})
    assert b2.context_window_hint == 20480
    # Serveur muet / maximum inconnu : le reglage tel quel.
    b3 = LMStudioBackend("http://x/v1", "m", reflexion=False,
                         context_window_hint=65536, fiche=lambda: None)
    assert b3.context_window_hint == 65536
    b4 = LMStudioBackend("http://x/v1", "m", reflexion=False,
                         context_window_hint=65536,
                         fiche=lambda: {"ctx_max": None, "reflexion": ()})
    assert b4.context_window_hint == 65536


# ── 6. OpenAI : max_completion_tokens (modeles a raisonnement) ──────────

class _TransportJson:
    def __init__(self, finish_reason="stop", content="ok"):
        self.last = None
        self.finish_reason = finish_reason
        self.content = content

    def post_json(self, url, headers, payload, timeout):
        self.last = payload
        return {"choices": [{"message": {"content": self.content},
                             "finish_reason": self.finish_reason}]}

    def iter_sse(self, url, headers, payload, timeout):
        self.last = payload
        yield "data: [DONE]"

    def get_json(self, url, headers, timeout):
        return {}


def test_openai_preset_sends_max_completion_tokens_others_keep_max_tokens():
    from ui.ai_config import ai_config
    from ui.ai_backends import get_backend_instance
    msg = [{"role": "user", "content": "hi"}]
    for pid in ("openai", "gemini", "mistral"):
        ai_config.set_api_key(pid, "sk-test")
        b = get_backend_instance(pid)
        t = _TransportJson()
        b._transport = t
        vus = []
        b._complete("S", msg); vus.append(t.last)
        b.chat("S", msg); vus.append(t.last)
        list(b.chat_stream("S", msg)); vus.append(t.last)
        b.probe_model(); vus.append(t.last)
        for p in vus:
            if pid == "openai":
                assert "max_tokens" not in p, p
                assert p.get("max_completion_tokens") in (8192, 1), p
            else:
                assert "max_completion_tokens" not in p, (pid, p)
                assert p.get("max_tokens") in (8192, 1), (pid, p)


# ── 7. Reponse coupee par le plafond : dite, pas rendue comme complete ──

def test_a_response_cut_by_the_cap_is_reported_not_returned_as_complete():
    from ui.ai_backends.openai_compat import OpenAICompatBackend
    msg = [{"role": "user", "content": "hi"}]

    def moteur(t):
        return OpenAICompatBackend("https://x/v1", "k", "m", backend_id="gemini",
                                   label="G", transport=t)
    for contenu in ("int x = 1; void loop() {", None):
        t = _TransportJson(finish_reason="length", content=contenu)
        try:
            moteur(t)._complete("S", msg)
            raise AssertionError("une reponse coupee est passee pour complete")
        except RuntimeError as e:
            assert "limit" in str(e).lower() or "limite" in str(e).lower(), str(e)
    # Une reponse normale, ou un finish_reason absent, passe.
    assert moteur(_TransportJson("stop", "ok"))._complete("S", msg) == "ok"
    assert moteur(_TransportJson(None, "ok"))._complete("S", msg) == "ok"
    # La sonde ne s'en offusque pas (max_tokens=1 coupe toujours).
    assert moteur(_TransportJson("length", None)).probe_model()[0] is True


# ── 4. Ollama : une etiquette precisee exige la MEME etiquette ──────────

def test_a_tagged_model_needs_its_exact_tag():
    import ui.ai_backends.ollama_backend as ob
    vrai = ob.list_local_models
    try:
        ob.list_local_models = lambda: ["gemma4:e4b", "gemma4:latest"]
        assert ob.is_model_available("gemma4:e2b") is False
        assert ob.is_model_available("gemma4:e4b") is True
        # sans etiquette : le nom suffit (comportement conserve)
        assert ob.is_model_available("gemma4") is True
        assert ob.is_model_available("llama3") is False
    finally:
        ob.list_local_models = vrai


# ── 5. Ollama : une reponse HTTP d'erreur n'est pas un serveur eteint ───

def _http_error(code: int, corps: str):
    import io, urllib.error
    return urllib.error.HTTPError(
        "http://127.0.0.1:11434/api/generate", code, "err", {},
        io.BytesIO(corps.encode("utf-8")))


def test_an_http_error_is_not_reported_as_a_stopped_server():
    import ui.ai_backends.ollama_backend as ob
    vrai_post, vrai_stream = ob._post, ob._post_stream
    try:
        def _404(*a, **k):
            raise _http_error(404, json.dumps({"error": "model 'x' not found"}))
        ob._post = _404
        b = ob.OllamaBackend("x")
        for appel in (lambda: b._call("p"),
                      lambda: b.chat("s", [{"role": "user", "content": "q"}])):
            try:
                appel()
                raise AssertionError("aucune erreur levee")
            except RuntimeError as e:
                msg = str(e)
            assert "pas lanc" not in msg, msg
            assert "404" in msg and "not found" in msg, msg

        def _500_stream(*a, **k):
            raise _http_error(500, json.dumps(
                {"error": "requires more system memory"}))
            yield  # pragma: no cover
        ob._post_stream = _500_stream
        try:
            list(b.chat_stream("s", [{"role": "user", "content": "q"}]))
            raise AssertionError("aucune erreur levee")
        except RuntimeError as e:
            msg = str(e)
        assert "pas lanc" not in msg and "memory" in msg, msg
        # Un vrai serveur eteint reste dit comme tel.
        import urllib.error
        def _off(*a, **k):
            raise urllib.error.URLError("refused")
        ob._post = _off
        try:
            b._call("p")
            raise AssertionError("aucune erreur levee")
        except RuntimeError as e:
            assert "pas lanc" in str(e)
    finally:
        ob._post, ob._post_stream = vrai_post, vrai_stream


TESTS = [
    test_openai_preset_sends_max_completion_tokens_others_keep_max_tokens,
    test_a_response_cut_by_the_cap_is_reported_not_returned_as_complete,
    test_chatgpt_network_failure_on_refresh_is_not_signed_out,
    test_cancel_closes_a_streaming_response,
    test_migration_keeps_the_other_settings_on_disk,
    test_clear_all_api_keys_also_clears_the_custom_key,
    test_lmstudio_context_is_capped_to_the_model_maximum,
    test_a_tagged_model_needs_its_exact_tag,
    test_an_http_error_is_not_reported_as_a_stopped_server,
]


def main() -> int:
    failed = 0
    try:
        for t in TESTS:
            try:
                t(); print(f"OK   {t.__name__}")
            except Exception as e:
                failed += 1; print(f"FAIL {t.__name__}: {type(e).__name__}: {e}")
    finally:
        aicfg.CONFIG_PATH = _VRAI_CHEMIN
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
