"""Une erreur renvoyee en HTTP 200 n'est pas une reponse (TODO #119).

OpenRouter le documente (docs/api-reference/errors, 2026-11-01) : le 200 part
des qu'un fournisseur accepte la requete. Une panne ulterieure arrive DANS le
corps -- en flux comme evenement SSE portant `error` et
`finish_reason: "error"`, hors flux comme un corps sans `choices`, y compris
quand TOUS les fournisseurs d'un modele ont echoue. L'adaptateur ne lisait que
le code HTTP : chat coupe sans message, generation en << Reponse illisible >>,
sonde VERTE sur un modele qui ne repond pas.

L'URL des tests n'est PAS celle d'OpenRouter : le controle est generique, et
c'est ce choix que ces tests verrouillent autant que le comportement.

⚠️ En plein flux `error.code` est une CHAINE (`"server_error"`), avant le flux
un entier : les fixtures reprennent les deux formes de la doc.

Run: python scripts/test_http200_error_body.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui.ai_backends.openai_compat as oc  # noqa: E402
from ui.ai_backends.openai_compat import OpenAICompatBackend  # noqa: E402

_MSG = [{"role": "user", "content": "x"}]

# Hors flux : le basculement a epuise les fournisseurs -> 200, `error` seul.
_ALL_FAILED = {"error": {"code": 502, "message": "All providers failed"}}

# En flux : evenement final reconstitue a partir des fragments de la doc
# (champ `error` au premier niveau, code CHAINE, `finish_reason: "error"`).
_STREAM_ERROR = ("data: " + json.dumps({
    "id": "cmpl-abc123", "object": "chat.completion.chunk",
    "error": {"code": "server_error",
              "message": "Provider disconnected unexpectedly"},
    "choices": [{"index": 0, "delta": {"content": ""},
                 "finish_reason": "error"}],
}))


class _Transport:
    """Rend un corps fixe en 200 -- jamais de reseau."""

    def __init__(self, body=None, sse_lines=()):
        self.body = body
        self.sse_lines = list(sse_lines)

    def post_json(self, url, headers, payload, timeout):
        return self.body

    def iter_sse(self, url, headers, payload, timeout):
        yield from self.sse_lines


def _backend(transport) -> OpenAICompatBackend:
    return OpenAICompatBackend(
        base_url="https://api.example.com/v1", api_key="sk-test",
        model="m-1", backend_id="openai", label="OpenAI",
        transport=transport)


def _raises(fn) -> str:
    try:
        fn()
    except RuntimeError as e:
        return str(e)
    raise AssertionError("aucune erreur levee : le 200 a ete pris pour une reponse")


# ── hors flux ─────────────────────────────────────────────────────────────

def test_a_200_error_body_is_not_an_unreadable_response():
    """Avant : KeyError sur `choices` -> << Reponse illisible >>, et le
    message du fournisseur, le seul utile, etait perdu."""
    msg = _raises(lambda: _backend(_Transport(_ALL_FAILED)).chat("S", _MSG))
    assert "All providers failed" in msg, msg
    assert not msg.startswith(oc._error_message("bad_response")), msg


def test_the_announced_code_picks_the_message():
    for code, kind in ((429, "quota"), (401, "auth"), (403, "auth")):
        body = {"error": {"code": code, "message": "detail"}}
        msg = _raises(lambda: _backend(_Transport(body)).chat("S", _MSG))
        assert msg.startswith(oc._error_message(kind)), (code, msg)


def test_a_string_or_missing_code_means_provider_error():
    for err in ({"code": "server_error", "message": "x"},
                {"message": "x"},
                "plain text error"):
        msg = _raises(lambda: _backend(_Transport({"error": err})).chat("S", _MSG))
        assert msg.startswith(oc._error_message("provider")), (err, msg)


def test_partial_content_with_an_error_finish_is_rejected():
    """Un sketch tronque servi comme une reponse : la boucle de reparation
    le prendrait pour du code a corriger."""
    body = {"choices": [{
        "message": {"content": "void setup() {"},
        "finish_reason": "error",
        "error": {"code": 502, "message": "upstream died"}}]}
    msg = _raises(lambda: _backend(_Transport(body)).chat("S", _MSG))
    assert "upstream died" in msg, msg


def test_a_null_error_field_is_not_an_error():
    body = {"error": None, "choices": [{"message": {"content": "ok"}}]}
    assert _backend(_Transport(body)).chat("S", _MSG) == "ok"


# ── en flux ───────────────────────────────────────────────────────────────

def test_the_stream_keeps_its_text_then_raises():
    """Le chat garde deja le tampon sur `stream_error` : il suffit que
    l'erreur SOIT levee au lieu d'etre ignoree."""
    lines = ['data: {"choices":[{"delta":{"content":"Hel"}}]}',
             'data: {"choices":[{"delta":{"content":"lo"}}]}',
             _STREAM_ERROR]
    recu = []

    def lire():
        for morceau in _backend(_Transport(sse_lines=lines)).chat_stream("S", _MSG):
            recu.append(morceau)

    msg = _raises(lire)
    assert recu == ["Hel", "lo"], recu
    assert "Provider disconnected unexpectedly" in msg, msg


# ── la sonde ──────────────────────────────────────────────────────────────

def test_the_probe_is_red_on_a_200_error_body():
    ok, msg = _backend(_Transport(_ALL_FAILED)).probe_model()
    assert ok is False, "pastille verte sur un modele qui ne repond pas"
    assert "All providers failed" in msg, msg


def test_the_probe_stays_green_for_a_thinking_model():
    """⛔ QA AI1 : a max_tokens=1 un modele a raisonnement rend 200 SANS
    contenu. Seul un champ `error` doit faire rougir."""
    body = {"choices": [{"message": {"role": "assistant"},
                         "finish_reason": "length"}]}
    assert _backend(_Transport(body)).probe_model() == (True, "")


TESTS = [
    test_a_200_error_body_is_not_an_unreadable_response,
    test_the_announced_code_picks_the_message,
    test_a_string_or_missing_code_means_provider_error,
    test_partial_content_with_an_error_finish_is_rejected,
    test_a_null_error_field_is_not_an_error,
    test_the_stream_keeps_its_text_then_raises,
    test_the_probe_is_red_on_a_200_error_body,
    test_the_probe_stays_green_for_a_thinking_model,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
