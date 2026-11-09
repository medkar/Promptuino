"""Le backend << forfait ChatGPT >> : Responses API en flux (TODO #122).

Faux transport, fausse session : ni reseau ni trousseau. Les evenements SSE
reprennent la forme documentee (developers.openai.com/siwc/
token-sharing-open-source/models-and-inference et errors-and-recovery) : texte
dans `response.output_text.delta`, succes SEULEMENT a `response.completed`,
echec dans `response.failed`, forfait epuise = 429
`subscription_sharing_usage_limit_exceeded`, possible en plein flux.

Run: python scripts/test_chatgpt_plan_backend.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PROMPTUINO_NO_MIGRATION", "1")

from ui.ai_backends.chatgpt_plan import ChatGPTPlanBackend, PAGE_USAGE  # noqa: E402
from ui.ai_backends.openai_compat import HttpError  # noqa: E402

MSG = [{"role": "user", "content": "allume la LED"}]


def _ev(obj) -> str:
    return "data: " + json.dumps(obj)


def _flux_ok(*morceaux):
    lignes = ["event: response.created", _ev({"type": "response.created"})]
    for m in morceaux:
        lignes += ["event: response.output_text.delta",
                   _ev({"type": "response.output_text.delta", "delta": m})]
    lignes += ["event: response.completed", _ev({"type": "response.completed",
                                                 "response": {"status": "completed"}})]
    return lignes


_QUOTA = {"error": {"code": "subscription_sharing_usage_limit_exceeded",
                    "message": "You've reached your usage limit."}}


class _Session:
    def __init__(self, jetons=("acces-1",), compte=None):
        self.jetons = list(jetons)
        self.appels = []
        self._compte = compte if compte is not None else {"email": "e@x", "forfait": True}

    def jeton(self, *, forcer=False):
        self.appels.append(forcer)
        return self.jetons.pop(0) if self.jetons else None

    def compte(self):
        return self._compte


class _Transport:
    """Chaque appel consomme la reponse suivante : une liste de lignes SSE,
    ou une exception a lever."""

    def __init__(self, *reponses, modeles=None):
        self.reponses = list(reponses)
        self.modeles = modeles
        self.requetes = []

    def iter_sse(self, url, headers, payload, timeout):
        self.requetes.append((url, dict(headers), payload, timeout))
        rep = self.reponses.pop(0)
        if isinstance(rep, Exception):
            raise rep
        for ligne in rep:
            if isinstance(ligne, Exception):
                raise ligne
            yield ligne

    def get_json(self, url, headers, timeout):
        self.requetes.append((url, dict(headers), None, timeout))
        if isinstance(self.modeles, Exception):
            raise self.modeles
        return self.modeles

    def close_inflight(self):
        pass


def _backend(transport, session=None, modele="gpt-6.1-sol"):
    return ChatGPTPlanBackend(modele, session=session or _Session(), transport=transport)


def _erreur(fn) -> str:
    try:
        fn()
    except RuntimeError as e:
        return str(e)
    raise AssertionError("aucune erreur levee")


# ── la requete ────────────────────────────────────────────────────────────

def test_the_request_follows_the_documented_contract():
    t = _Transport(_flux_ok("ok"))
    _backend(t).chat("SYSTEME", MSG)
    url, headers, payload, _timeout = t.requetes[0]
    assert url == "https://api.openai.com/v1/responses", url
    assert headers["Authorization"] == "Bearer acces-1"
    assert payload["model"] == "gpt-6.1-sol"
    assert payload["stream"] is True and payload["store"] is False, payload
    assert payload["instructions"] == "SYSTEME"
    assert payload["input"] == MSG
    assert "temperature" not in payload and "max_output_tokens" not in payload, payload


def test_the_text_is_the_concatenated_deltas():
    t = _Transport(_flux_ok("void ", "setup()", " {}"))
    assert _backend(t).chat("S", MSG) == "void setup() {}"


def test_streaming_yields_each_delta():
    t = _Transport(_flux_ok("a", "b"))
    assert list(_backend(t).chat_stream("S", MSG)) == ["a", "b"]


def test_generation_goes_through_the_same_path():
    t = _Transport(_flux_ok("void setup(){}"))
    b = _backend(t)
    assert b.generate_code("LED", "Arduino Uno", "") == "void setup(){}"
    assert t.requetes[0][2]["instructions"], "le prompt systeme de generation est transmis"


# ── ce qui n'est PAS un succes ───────────────────────────────────────────

def test_a_stream_that_stops_without_completed_is_a_failure():
    """Doc : « Treat inference as successful only after receiving
    response.completed »."""
    lignes = _flux_ok("void setup")[:-2]          # sans l'evenement final
    msg = _erreur(lambda: _backend(_Transport(lignes)).chat("S", MSG))
    assert msg


def test_a_quota_reached_mid_stream_keeps_the_text_and_says_where_to_look():
    lignes = _flux_ok("Bon")[:-2] + [_ev({"type": "response.failed",
                                          "response": {"error": _QUOTA["error"]}})]
    recu = []

    def lire():
        for m in _backend(_Transport(lignes)).chat_stream("S", MSG):
            recu.append(m)
    msg = _erreur(lire)
    assert recu == ["Bon"], recu
    assert PAGE_USAGE in msg, msg


def test_a_quota_refused_upfront_says_where_to_look():
    t = _Transport(HttpError(429, json.dumps(_QUOTA)))
    msg = _erreur(lambda: _backend(t).chat("S", MSG))
    assert PAGE_USAGE in msg, msg


def test_a_forbidden_account_is_explained_with_openais_words():
    t = _Transport(HttpError(403, json.dumps({"error": {"message": "Not eligible"}})))
    msg = _erreur(lambda: _backend(t).chat("S", MSG))
    assert "Not eligible" in msg, msg


def test_an_explicit_error_event_is_a_failure():
    lignes = [_ev({"type": "error", "code": "server_error", "message": "boom"})]
    msg = _erreur(lambda: _backend(_Transport(lignes)).chat("S", MSG))
    assert "boom" in msg, msg


# ── le jeton ──────────────────────────────────────────────────────────────

def test_a_401_renews_once_and_retries():
    s = _Session(jetons=("perime", "frais"))
    t = _Transport(HttpError(401, "{}"), _flux_ok("ok"))
    assert _backend(t, s).chat("S", MSG) == "ok"
    assert s.appels == [False, True], s.appels
    assert t.requetes[1][1]["Authorization"] == "Bearer frais"


def test_a_second_401_asks_to_sign_in_again():
    s = _Session(jetons=("a", "b"))
    t = _Transport(HttpError(401, "{}"), HttpError(401, "{}"))
    msg = _erreur(lambda: _backend(t, s).chat("S", MSG))
    assert msg and len(t.requetes) == 2


def test_signed_out_never_reaches_the_network():
    s = _Session(jetons=())
    t = _Transport()
    msg = _erreur(lambda: _backend(t, s).chat("S", MSG))
    assert msg and t.requetes == []


# ── modeles, sonde, disponibilite ────────────────────────────────────────

def test_the_model_list_keeps_listed_slugs_only():
    t = _Transport(modeles={"models": [
        {"slug": "gpt-6.1-sol", "display_name": "GPT-6.1 Sol", "visibility": "list"},
        {"slug": "interne-x", "visibility": "hide"},
        {"slug": "gpt-6.1-mini", "visibility": "list"}]})
    modeles, kind = _backend(t).list_models_detailed()
    assert modeles == ["gpt-6.1-sol", "gpt-6.1-mini"] and kind == "", (modeles, kind)
    url, headers, _p, _t = t.requetes[0]
    assert url == "https://api.openai.com/v1/models"
    assert headers["Authorization"] == "Bearer acces-1"


def test_the_model_list_says_auth_when_signed_out():
    modeles, kind = _backend(_Transport(), _Session(jetons=())).list_models_detailed()
    assert modeles == [] and kind == "auth"


def test_the_probe_is_green_only_on_completed():
    assert _backend(_Transport(_flux_ok("pong"))).probe_model() == (True, "")
    ok, msg = _backend(_Transport(HttpError(429, json.dumps(_QUOTA)))).probe_model()
    assert not ok and PAGE_USAGE in msg, msg


def test_available_needs_plan_usage_and_a_model():
    assert _backend(_Transport()).is_available()
    assert not _backend(_Transport(), modele="").is_available()
    assert not _backend(_Transport(), _Session(compte={"email": "e", "forfait": False})).is_available()
    sans = _Session()
    sans._compte = None
    assert not _backend(_Transport(), sans).is_available()
    assert not _backend(_Transport()).requires_api_key


# ── le niveau de reflexion (TODO #123) ───────────────────────────────────
# `reasoning.effort` n'est PAS documente pour la connexion ChatGPT. La doc
# des erreurs dit en revanche qu'un 400 `subscription_sharing_unsupported_
# capability` nomme le champ fautif dans `error.param`, et qu'il faut
# « retirer l'entree non prise en charge » plutot que renvoyer le meme corps.

def _refus(param):
    corps = {"error": {"code": "subscription_sharing_unsupported_capability",
                       "message": "Unsupported.", "param": param}}
    return HttpError(400, json.dumps(corps))


def _avec_effort(transport, effort, modele="gpt-6.1-sol"):
    return ChatGPTPlanBackend(modele, effort=effort, session=_Session(jetons=("a", "b", "c")),
                              transport=transport)


def _oublier_les_refus():
    import ui.ai_backends.chatgpt_plan as cp
    cp._REFLEXION_REFUSEE.clear()


def test_the_chosen_level_rides_along_with_every_request():
    _oublier_les_refus()
    t = _Transport(_flux_ok("ok"))
    _avec_effort(t, "high").chat("S", MSG)
    assert t.requetes[0][2]["reasoning"] == {"effort": "high"}, t.requetes[0][2]


def test_no_level_sends_no_reasoning_field():
    _oublier_les_refus()
    t = _Transport(_flux_ok("ok"))
    _avec_effort(t, None).chat("S", MSG)
    assert "reasoning" not in t.requetes[0][2]


def test_a_refused_level_is_dropped_once_and_remembered_for_the_session():
    _oublier_les_refus()
    import ui.ai_backends.chatgpt_plan as cp
    t = _Transport([_refus("reasoning.effort")][0], _flux_ok("ok"), _flux_ok("encore"))
    b = _avec_effort(t, "low")
    assert b.chat("S", MSG) == "ok"
    assert "reasoning" in t.requetes[0][2] and "reasoning" not in t.requetes[1][2]
    assert cp.reflexion_refusee("gpt-6.1-sol")
    # Un nouveau moteur pour le meme modele ne redemande pas.
    _avec_effort(t, "low").chat("S", MSG)
    assert "reasoning" not in t.requetes[2][2]
    assert not cp.reflexion_refusee("autre-modele")
    _oublier_les_refus()


def test_a_refusal_about_another_field_is_a_plain_error():
    _oublier_les_refus()
    import ui.ai_backends.chatgpt_plan as cp
    t = _Transport(_refus("tools"))
    _erreur(lambda: _avec_effort(t, "low").chat("S", MSG))
    assert len(t.requetes) == 1 and not cp.reflexion_refusee("gpt-6.1-sol")


def test_the_factory_passes_the_setting():
    """Le MEME moteur suit le reglage change apres sa creation : la pastille
    du chat bascule sans recreer le moteur (2026-11-07)."""
    from ui.ai_config import ai_config
    from ui.ai_backends.factory import get_backend_instance
    ancien = ai_config._data.get("chatgpt_reasoning")
    try:
        ai_config._data["chatgpt_reasoning"] = "low"     # en memoire, jamais ecrit
        b = get_backend_instance("chatgpt")
        b._model = "gpt-x"
        assert b._corps("", [])["reasoning"] == {"effort": "low"}
        ai_config._data["chatgpt_reasoning"] = "high"
        assert b._corps("", [])["reasoning"] == {"effort": "high"}
    finally:
        ai_config._data["chatgpt_reasoning"] = ancien


TESTS = [
    test_the_chosen_level_rides_along_with_every_request,
    test_no_level_sends_no_reasoning_field,
    test_a_refused_level_is_dropped_once_and_remembered_for_the_session,
    test_a_refusal_about_another_field_is_a_plain_error,
    test_the_factory_passes_the_setting,
    test_the_request_follows_the_documented_contract,
    test_the_text_is_the_concatenated_deltas,
    test_streaming_yields_each_delta,
    test_generation_goes_through_the_same_path,
    test_a_stream_that_stops_without_completed_is_a_failure,
    test_a_quota_reached_mid_stream_keeps_the_text_and_says_where_to_look,
    test_a_quota_refused_upfront_says_where_to_look,
    test_a_forbidden_account_is_explained_with_openais_words,
    test_an_explicit_error_event_is_a_failure,
    test_a_401_renews_once_and_retries,
    test_a_second_401_asks_to_sign_in_again,
    test_signed_out_never_reaches_the_network,
    test_the_model_list_keeps_listed_slugs_only,
    test_the_model_list_says_auth_when_signed_out,
    test_the_probe_is_green_only_on_completed,
    test_available_needs_plan_usage_and_a_model,
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
