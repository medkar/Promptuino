"""OpenAICompatBackend tests. Run: python scripts/test_openai_compat_backend.py"""
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.ai_backends.openai_compat import OpenAICompatBackend, HttpError


class FakeTransport:
    """Records the last request and returns a canned completion."""
    def __init__(self, content="hello", sse_lines=None, error=None,
                 models_payload=None):
        self.content = content
        self.sse_lines = sse_lines or []
        self.error = error
        self.models_payload = models_payload
        self.last = None   # (url, headers, payload, timeout)

    def post_json(self, url, headers, payload, timeout):
        self.last = (url, headers, payload, timeout)
        if self.error:
            raise self.error
        return {"choices": [{"message": {"content": self.content}}]}

    def iter_sse(self, url, headers, payload, timeout):
        self.last = (url, headers, payload, timeout)
        if self.error:
            raise self.error
        yield from self.sse_lines

    def get_json(self, url, headers, timeout):
        self.last = (url, headers, None, timeout)
        if self.error:
            raise self.error
        return self.models_payload


def _backend(transport, **kw):
    defaults = dict(
        base_url="https://api.example.com/v1", api_key="sk-test",
        model="m-1", backend_id="openai", label="OpenAI",
        context_window_hint=128_000, transport=transport)
    defaults.update(kw)
    return OpenAICompatBackend(**defaults)


def test_complete_builds_payload_and_headers():
    t = FakeTransport(content="RESULT")
    b = _backend(t)
    out = b._complete("SYS", [{"role": "user", "content": "hi"}])
    assert out == "RESULT"
    url, headers, payload, timeout = t.last
    assert url == "https://api.example.com/v1/chat/completions"
    assert headers["Authorization"] == "Bearer sk-test"
    assert headers["Content-Type"] == "application/json"
    assert payload["model"] == "m-1"
    assert payload["messages"][0] == {"role": "system", "content": "SYS"}
    assert payload["messages"][1] == {"role": "user", "content": "hi"}
    assert payload["stream"] is False
    assert timeout == 300


def test_complete_omits_empty_system():
    t = FakeTransport()
    b = _backend(t)
    b._complete("", [{"role": "user", "content": "hi"}])
    _, _, payload, _ = t.last
    assert payload["messages"][0]["role"] == "user"   # no system message


def test_extra_headers_merged():
    t = FakeTransport()
    b = _backend(t, extra_headers={"X-Title": "Promptuino"})
    b._complete("S", [{"role": "user", "content": "x"}])
    _, headers, _, _ = t.last
    assert headers["X-Title"] == "Promptuino"


def test_capabilities():
    b = _backend(FakeTransport())
    assert b.context_window_hint == 128_000
    assert b.is_slm is False
    assert b.backend_id == "openai"
    assert b.requires_api_key is True
    assert b.is_available() is True
    assert _backend(FakeTransport(), api_key="").is_available() is False


def test_complete_handles_null_content():
    class NullTransport(FakeTransport):
        def post_json(self, url, headers, payload, timeout):
            self.last = (url, headers, payload, timeout)
            return {"choices": [{"message": {"content": None}}]}
    b = _backend(NullTransport())
    assert b._complete("S", [{"role": "user", "content": "x"}]) == ""


def test_extra_headers_cannot_clobber_auth():
    t = FakeTransport()
    b = _backend(t, extra_headers={"Authorization": "Bearer EVIL"})
    b._complete("S", [{"role": "user", "content": "x"}])
    _, headers, _, _ = t.last
    assert headers["Authorization"] == "Bearer sk-test"


def test_api_key_whitespace_not_available():
    b = _backend(FakeTransport(), api_key="   ")
    assert b.is_available() is False


def _sse(content_chunks, with_done=True):
    import json as _j
    lines = []
    for c in content_chunks:
        lines.append("data: " + _j.dumps({"choices": [{"delta": {"content": c}}]}))
        lines.append("")          # blank line between SSE events
    if with_done:
        lines.append("data: [DONE]")
    return lines


def test_chat_stream_yields_chunks():
    t = FakeTransport(sse_lines=_sse(["Hel", "lo", " world"]))
    b = _backend(t)
    chunks = list(b.chat_stream("SYS", [{"role": "user", "content": "hi"}]))
    assert "".join(chunks) == "Hello world"
    _, _, payload, _ = t.last
    assert payload["stream"] is True


def test_chat_stream_ignores_keepalives_and_done():
    lines = ["", ": keepalive",
             'data: {"choices":[{"delta":{"content":"A"}}]}',
             'data: {"choices":[{"delta":{}}]}',          # no content
             "data: [DONE]",
             'data: {"choices":[{"delta":{"content":"B"}}]}']  # after DONE: ignored
    t = FakeTransport(sse_lines=lines)
    b = _backend(t)
    assert "".join(b.chat_stream("S", [{"role": "user", "content": "x"}])) == "A"


def test_generate_code_uses_system_builder():
    t = FakeTransport(content="void setup(){}")
    b = _backend(t)
    out = b.generate_code("blink an LED", "Arduino Uno")
    assert out == "void setup(){}"
    _, _, payload, _ = t.last
    sys_msg = payload["messages"][0]
    assert sys_msg["role"] == "system"
    assert "Arduino Uno" in sys_msg["content"]          # from _build_system_prompt
    assert payload["messages"][1]["content"] == "blink an LED"


def test_fix_code_maps_builders():
    t = FakeTransport(content="fixed")
    b = _backend(t)
    b.fix_code("int x", "expected ;", "Arduino Uno")
    _, _, payload, _ = t.last
    assert "compilation error" in payload["messages"][0]["content"].lower()
    assert "Arduino Uno" in payload["messages"][0]["content"]
    assert "expected ;" in payload["messages"][1]["content"]


def test_explain_error_no_system():
    t = FakeTransport(content="c'est un point-virgule manquant")
    b = _backend(t)
    b.explain_error("expected ';'", "French")
    _, _, payload, _ = t.last
    # explain_error has no system prompt -> first message is the user prompt
    assert payload["messages"][0]["role"] == "user"
    assert "French" in payload["messages"][0]["content"]
    assert len(payload["messages"]) == 1


def test_repair_code_returns_tuple():
    t = FakeTransport(content="[SUMMARY]\n- **Line 1:** fix\n[/SUMMARY]\nint x = 0;")
    b = _backend(t)
    code, summary = b.repair_code("int x = ", "error", "French", "Arduino Uno")
    assert isinstance(code, str) and isinstance(summary, str)


def test_error_mapping():
    for status in (401, 403, 404, 429, 500):
        t = FakeTransport(error=HttpError(status))
        b = _backend(t)
        try:
            b.chat("S", [{"role": "user", "content": "x"}])
            assert False, f"expected RuntimeError for {status}"
        except RuntimeError as e:
            assert str(e)            # non-empty message


def test_connection_error_mapped():
    t = FakeTransport(error=ConnectionError("refused"))
    b = _backend(t)
    try:
        b.chat("S", [{"role": "user", "content": "x"}])
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert str(e)


def test_chat_stream_http_error_mapped():
    t = FakeTransport(error=HttpError(401))
    b = _backend(t)
    try:
        list(b.chat_stream("S", [{"role": "user", "content": "x"}]))
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert str(e)


def test_chat_stream_connection_error_mapped():
    t = FakeTransport(error=ConnectionError("reset"))
    b = _backend(t)
    try:
        list(b.chat_stream("S", [{"role": "user", "content": "x"}]))
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert str(e)


def test_list_models_parses_and_filters():
    payload = {"data": [
        {"id": "gpt-4o"},
        {"id": "gpt-4o-mini"},
        {"id": "text-embedding-3-small"},   # non-chat -> filtered out
        {"id": "whisper-1"},                # non-chat -> filtered out
        {"id": "dall-e-3"},                 # non-chat -> filtered out
    ]}
    t = FakeTransport(models_payload=payload)
    b = _backend(t)
    models = b.list_models()
    assert "gpt-4o" in models and "gpt-4o-mini" in models
    assert "text-embedding-3-small" not in models
    assert "whisper-1" not in models and "dall-e-3" not in models
    # request shape: GET {base_url}/models with auth header
    url, headers, _, _ = t.last
    assert url == "https://api.example.com/v1/models"
    assert headers["Authorization"] == "Bearer sk-test"


def test_list_models_error_returns_empty():
    for err in (HttpError(401), ConnectionError("x")):
        t = FakeTransport(error=err)
        b = _backend(t)
        assert b.list_models() == []   # never raises; UI falls back


def test_list_models_detailed_success():
    payload = {"data": [{"id": "gpt-4o"}, {"id": "text-embedding-3-small"}]}
    models, kind = _backend(FakeTransport(models_payload=payload)).list_models_detailed()
    assert models == ["gpt-4o"] and kind == ""


def test_list_models_detailed_auth():
    models, kind = _backend(FakeTransport(error=HttpError(401))).list_models_detailed()
    assert models == [] and kind == "auth"


def test_list_models_detailed_unsupported():
    models, kind = _backend(FakeTransport(error=HttpError(404))).list_models_detailed()
    assert models == [] and kind == "unsupported"


def test_list_models_detailed_empty():
    models, kind = _backend(FakeTransport(models_payload={"data": []})).list_models_detailed()
    assert models == [] and kind == "empty"


def test_list_models_strips_gemini_prefix():
    payload = {"data": [{"id": "models/gemini-2.5-flash"}, {"id": "models/gemini-2.5-pro"}]}
    models, kind = _backend(FakeTransport(models_payload=payload)).list_models_detailed()
    assert models == ["gemini-2.5-flash", "gemini-2.5-pro"] and kind == ""


def test_list_models_filters_non_chat_families():
    # Non-chat families across providers must be dropped (shared filter).
    payload = {"data": [
        {"id": "gemini-2.5-flash"},          # kept
        {"id": "imagen-3.0-generate-001"},   # image gen ("image")
        {"id": "veo-2.0"},                   # video gen
        {"id": "aqa"},                       # attributed QA
        {"id": "text-embedding-004"},        # embedding
        {"id": "mistral-ocr-latest"},        # OCR
        {"id": "nano-banana-pro-preview"},   # Google image-gen codename
        {"id": "lyria-realtime-exp"},        # music gen
        {"id": "gemini-2.5-deep-research"},  # research agent
        {"id": "gemini-robotics-er-1.5-preview"},  # robotics
    ]}
    models, kind = _backend(FakeTransport(models_payload=payload)).list_models_detailed()
    assert models == ["gemini-2.5-flash"] and kind == ""


def test_gemini_native_capability_filter():
    # Gemini host -> native /v1beta/models, keep only generateContent models,
    # then apply substring markers on top (robotics dropped despite generateContent).
    payload = {"models": [
        {"name": "models/gemini-2.5-flash",
         "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/gemma-3-27b-it",
         "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/imagen-3.0-generate-001",
         "supportedGenerationMethods": ["predict"]},             # image -> dropped
        {"name": "models/veo-2.0",
         "supportedGenerationMethods": ["predictLongRunning"]},  # video -> dropped
        {"name": "models/text-embedding-004",
         "supportedGenerationMethods": ["embedContent"]},        # embed -> dropped
        {"name": "models/lyria-realtime-exp",
         "supportedGenerationMethods": ["bidiGenerateContent"]}, # music -> dropped
        {"name": "models/gemini-robotics-er-1.5-preview",
         "supportedGenerationMethods": ["generateContent"]},     # marker -> dropped
    ]}
    b = OpenAICompatBackend(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        api_key="k", model="gemini-2.5-flash", backend_id="gemini",
        label="Gemini", transport=FakeTransport(models_payload=payload))
    models, kind = b.list_models_detailed()
    assert models == ["gemini-2.5-flash", "gemma-3-27b-it"], models
    assert kind == ""
    url, headers, _, _ = b._transport.last
    assert url.endswith("/v1beta/models?pageSize=1000"), url
    assert headers["x-goog-api-key"] == "k"


def test_anthropic_native_models():
    # Anthropic /models needs x-api-key + anthropic-version, NOT Bearer.
    payload = {"data": [
        {"id": "claude-sonnet-4-5-20250929"},
        {"id": "claude-opus-4-1-20250805"},
    ]}
    b = OpenAICompatBackend(
        base_url="https://api.anthropic.com/v1", api_key="k",
        model="claude-sonnet-4-6", backend_id="anthropic", label="Anthropic",
        transport=FakeTransport(models_payload=payload))
    models, kind = b.list_models_detailed()
    assert models == ["claude-opus-4-1-20250805",
                      "claude-sonnet-4-5-20250929"], models
    assert kind == ""
    url, headers, _, _ = b._transport.last
    assert url.endswith("/v1/models?limit=1000"), url
    assert headers["x-api-key"] == "k"
    assert headers.get("anthropic-version")
    assert "Authorization" not in headers   # must NOT send Bearer to /models


TESTS = [test_complete_builds_payload_and_headers, test_complete_omits_empty_system,
         test_extra_headers_merged, test_capabilities,
         test_complete_handles_null_content,
         test_extra_headers_cannot_clobber_auth, test_api_key_whitespace_not_available,
         test_chat_stream_yields_chunks, test_chat_stream_ignores_keepalives_and_done,
         test_generate_code_uses_system_builder, test_fix_code_maps_builders,
         test_explain_error_no_system, test_repair_code_returns_tuple,
         test_error_mapping, test_connection_error_mapped,
         test_chat_stream_http_error_mapped, test_chat_stream_connection_error_mapped,
         test_list_models_parses_and_filters, test_list_models_error_returns_empty,
         test_list_models_detailed_success, test_list_models_detailed_auth,
         test_list_models_detailed_unsupported, test_list_models_detailed_empty,
         test_list_models_strips_gemini_prefix,
         test_list_models_filters_non_chat_families,
         test_gemini_native_capability_filter,
         test_anthropic_native_models]


def main() -> int:
    for t in TESTS:
        t()
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
