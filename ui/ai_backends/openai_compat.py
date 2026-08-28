"""Unified OpenAI-compatible backend (POST /chat/completions).

One adapter for every cloud/BYO provider (see providers.py). The HTTP
transport is injectable so tests never touch the network. Ollama keeps its
native transport (num_ctx control) — it is NOT routed through this class.
"""
from __future__ import annotations

import json
import http.client
import threading
import urllib.error
import urllib.request
from typing import Iterator

from .base import AIBackend

_TIMEOUT = 300          # seconds — generation can be long
_LIST_TIMEOUT = 15      # seconds — GET /models should be quick
_CHAT_MAX_TOKENS = 2048
_GEN_MAX_TOKENS = 8192   # generous for full-program generation/repair

# Substrings that mark a non-chat model id (filtered out of the model list).
# Shared by ALL providers: OpenAI (dall-e / embeddings / audio / moderation),
# Gemini (imagen — caught by "image" — / veo / aqa), Mistral (ocr), etc.
_NON_CHAT_MODEL_MARKERS = (
    "embed", "whisper", "tts", "dall-e", "dalle", "stable-diffusion",
    "moderation", "rerank", "audio", "speech", "transcribe", "image",
    # Google specialized / non-chat families (codenames have no "image" token):
    "veo", "aqa", "ocr", "nano-banana", "lyria", "deep-research",
    "antigravity", "robotics",
)

_ERR_FALLBACK = {
    "auth":         "Invalid or missing API key for this provider.",
    "notfound":     "Model or URL not found — check the model and base URL.",
    "quota":        "Quota or rate limit exceeded — try again later.",
    "provider":     "Provider error — try again later.",
    "network":      "Provider unreachable — check your connection and the base URL.",
    "bad_response": "Unreadable response from the provider.",
}


def _error_message(kind: str) -> str:
    """i18n error message for `kind`, English fallback if i18n unavailable."""
    try:
        from ..i18n import lang_manager
        val = getattr(lang_manager.current, f"ia_err_{kind}", "")
        if val:
            return val
    except Exception:
        pass
    return _ERR_FALLBACK.get(kind, _ERR_FALLBACK["provider"])


def _status_kind(status: int) -> str:
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "notfound"
    if status == 429:
        return "quota"
    return "provider"


class HttpError(Exception):
    """Non-2xx HTTP response from the provider."""
    def __init__(self, status: int, body: str = ""):
        super().__init__(f"HTTP {status}")
        self.status = status
        self.body = body


class _UrllibTransport:
    """Default transport over urllib.

    Raises HttpError on a non-2xx response and ConnectionError on a network
    failure. A non-JSON 2xx body lets json.JSONDecodeError propagate — the
    caller (_complete) classifies it as a bad response.
    """

    def __init__(self):
        # Reponse en vol, pour `close_inflight` (TODO #24).
        self._inflight = None
        self._inflight_lock = threading.Lock()

    def close_inflight(self) -> None:
        """Ferme la reponse en cours, s'il y en a une.

        ⚠️ METHODE OPTIONNELLE DU PROTOCOLE, ET C'EST DELIBERE. La premiere
        version ajoutait un parametre `register` a `post_json` — ce qui CASSAIT
        le protocole : le transport est injectable (`transport or
        _UrllibTransport()`), et une doublure qui ignorait l'argument echouait
        avec << Reponse illisible du fournisseur >>, un message qui n'a aucun
        rapport. Attrape par `test_openai_compat_backend.py`. Une methode en
        plus, appelee via `getattr`, laisse tout transport existant intact.
        """
        with self._inflight_lock:
            r = self._inflight
        if r is None:
            return
        try:
            r.close()
        except Exception:
            pass

    def post_json(self, url: str, headers: dict, payload: dict,
                  timeout) -> dict:
        req = self._req(url, headers, payload)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                with self._inflight_lock:
                    self._inflight = r
                try:
                    return json.loads(r.read())
                finally:
                    with self._inflight_lock:
                        self._inflight = None
        except urllib.error.HTTPError as e:
            raise HttpError(e.code, _safe_body(e)) from e
        except urllib.error.URLError as e:
            raise ConnectionError(str(e.reason)) from e

    def iter_sse(self, url: str, headers: dict, payload: dict,
                 timeout: int) -> Iterator[str]:
        req = self._req(url, headers, payload)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                for raw in r:
                    yield raw.decode("utf-8", errors="replace").rstrip("\r\n")
        except urllib.error.HTTPError as e:
            raise HttpError(e.code, _safe_body(e)) from e
        except urllib.error.URLError as e:
            raise ConnectionError(str(e.reason)) from e
        except (OSError, http.client.HTTPException) as e:
            # Mid-stream connection reset / truncated body (not a URLError).
            raise ConnectionError(str(e)) from e

    def get_json(self, url: str, headers: dict, timeout: int) -> dict:
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raise HttpError(e.code, _safe_body(e)) from e
        except urllib.error.URLError as e:
            raise ConnectionError(str(e.reason)) from e

    @staticmethod
    def _req(url, headers, payload):
        data = json.dumps(payload).encode()
        return urllib.request.Request(url, data=data, headers=headers)


def _safe_body(e) -> str:
    try:
        return e.read().decode("utf-8", errors="replace")[:500]
    except Exception:
        return ""


# ⚠️ Sentinelle « prends le defaut » (TODO #24), et elle ne peut PAS etre
# `None` : pour `urlopen`, `timeout=None` signifie deja « aucun delai », qui est
# exactement la valeur que `generate_code` doit pouvoir transmettre. Confondre
# les deux ferait silencieusement retomber la generation sur les 120 s qu'on
# vient de lui retirer — le bug est invisible, le code a l'air juste.
_DEFAULT_TIMEOUT = object()


class OpenAICompatBackend(AIBackend):

    def __init__(self, base_url: str, api_key: str, model: str, *,
                 backend_id: str, label: str,
                 context_window_hint: int = 8192,
                 code_task_temperature: float | None = None,
                 extra_headers=None,
                 transport=None):
        self._base_url = base_url.rstrip("/")
        self._api_key = (api_key or "").strip()
        self._model = model
        self._backend_id = backend_id
        self._label = label
        self._ctx_hint = context_window_hint
        self._code_temp = code_task_temperature
        self._extra_headers = dict(extra_headers or {})
        self._transport = transport or _UrllibTransport()

    # ── Identity / capabilities ──────────────────────────────
    @property
    def backend_id(self) -> str:
        return self._backend_id

    @property
    def name(self) -> str:
        return self._label

    @property
    def description(self) -> str:
        return f"{self._label} — {self._model}"

    @property
    def requires_api_key(self) -> bool:
        return True

    @property
    def context_window_hint(self) -> int:
        return self._ctx_hint

    def is_available(self) -> bool:
        return bool(self._api_key and self._base_url and self._model)

    def list_models_detailed(self) -> tuple[list[str], str]:
        """Like list_models() but also returns an error kind ('' on success).

        kinds: 'auth' (bad/absent key), 'quota', 'provider', 'unsupported'
        (provider has no /models endpoint, i.e. 404), 'network', 'bad_response',
        'empty' (call ok but no chat model found). Never raises.

        Per-provider /models exceptions (the CHAT endpoint stays uniform; only
        model DISCOVERY differs): Gemini uses its native capability endpoint;
        Anthropic's /models needs x-api-key + anthropic-version (not Bearer).
        """
        if "generativelanguage.googleapis.com" in self._base_url:
            return self._gemini_native_models()
        if "api.anthropic.com" in self._base_url:
            return self._anthropic_native_models()
        url = f"{self._base_url}/models"
        try:
            data = self._transport.get_json(url, self._headers(), _LIST_TIMEOUT)
        except HttpError as e:
            kind = "unsupported" if e.status == 404 else _status_kind(e.status)
            return [], kind
        except ConnectionError:
            return [], "network"
        try:
            ids = []
            for m in (data.get("data") or []):
                mid = m.get("id")
                if not mid:
                    continue
                mid = str(mid)
                if mid.startswith("models/"):
                    mid = mid[len("models/"):]   # Gemini returns 'models/<id>'
                ids.append(mid)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            return [], "bad_response"
        chat = sorted(i for i in ids
                      if not any(mark in i.lower() for mark in _NON_CHAT_MODEL_MARKERS))
        return chat, ("" if chat else "empty")

    def _gemini_native_models(self) -> tuple[list[str], str]:
        """Gemini's NATIVE /v1beta/models exposes supportedGenerationMethods.

        Keep only models supporting 'generateContent' (real chat/text models:
        gemini-*, gemma-*, learnlm-*, codegemma…), which drops the
        image/video/music/embedding/aqa families automatically — no per-name
        blocklist needed. The shared substring markers are still applied on top
        to drop generateContent-capable-but-specialized ids (e.g. robotics)."""
        # base_url is '<root>/v1beta/openai' -> native is '<root>/v1beta/models'.
        # pageSize is high enough to return the whole catalog in a single page.
        root = self._base_url.rsplit("/openai", 1)[0]
        url = f"{root}/models?pageSize=1000"
        headers = {"x-goog-api-key": self._api_key,
                   "Content-Type": "application/json"}
        try:
            data = self._transport.get_json(url, headers, _LIST_TIMEOUT)
        except HttpError as e:
            return [], ("unsupported" if e.status == 404
                        else _status_kind(e.status))
        except ConnectionError:
            return [], "network"
        try:
            out = []
            for m in (data.get("models") or []):
                methods = m.get("supportedGenerationMethods") or []
                if "generateContent" not in methods:
                    continue
                name = str(m.get("name") or "")
                if name.startswith("models/"):
                    name = name[len("models/"):]
                if name and not any(mark in name.lower()
                                    for mark in _NON_CHAT_MODEL_MARKERS):
                    out.append(name)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            return [], "bad_response"
        out = sorted(out)
        return out, ("" if out else "empty")

    def _anthropic_native_models(self) -> tuple[list[str], str]:
        """Anthropic's /v1/models needs its own auth (x-api-key +
        anthropic-version), NOT the Bearer header used for chat completions.

        Same URL as the generic path ({base_url}/models) but different headers.
        All returned entries are chat models; the shared substring markers are
        still applied on top for consistency."""
        url = f"{self._base_url}/models?limit=1000"
        headers = {"x-api-key": self._api_key,
                   "anthropic-version": "2023-06-01",
                   "Content-Type": "application/json"}
        try:
            data = self._transport.get_json(url, headers, _LIST_TIMEOUT)
        except HttpError as e:
            return [], ("unsupported" if e.status == 404
                        else _status_kind(e.status))
        except ConnectionError:
            return [], "network"
        try:
            ids = [str(m.get("id")) for m in (data.get("data") or [])
                   if m.get("id")]
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            return [], "bad_response"
        chat = sorted(i for i in ids
                      if not any(mark in i.lower() for mark in _NON_CHAT_MODEL_MARKERS))
        return chat, ("" if chat else "empty")

    def list_models(self) -> list[str]:
        """Provider's chat model ids (empty on any error). See list_models_detailed."""
        return self.list_models_detailed()[0]

    # ── Transport ────────────────────────────────────────────
    def _headers(self) -> dict:
        # Core headers set LAST so extra_headers can never clobber auth.
        h = dict(self._extra_headers)
        h["Authorization"] = f"Bearer {self._api_key}"
        h["Content-Type"] = "application/json"
        return h

    def _payload(self, system: str, messages: list[dict], *,
                 temperature, max_tokens, stream: bool) -> dict:
        msgs = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": m["role"], "content": m["content"]} for m in messages]
        p = {"model": self._model, "messages": msgs, "stream": stream,
             "max_tokens": max_tokens}
        if temperature is not None:
            p["temperature"] = temperature
        return p

    def cancel(self) -> None:
        """Coupe la requete de CODE en cours (cf. `AIBackend.cancel`).

        Meme raison et memes limites que l'override d'`OllamaBackend` : depuis
        le TODO #24 la generation part sans delai, donc plus rien ne libere le
        thread tout seul. Best-effort assume — l'appelant DETACHE le worker,
        donc l'utilisateur reprend la main quoi qu'il arrive ; ce qui se joue
        ici n'est que le sort d'un thread orphelin.

        Le chat, lui, streame (`iter_sse`) : son drapeau cooperatif est lu au
        chunk suivant, il n'a jamais eu besoin de ceci.

        `getattr` et non un appel direct : le transport est INJECTABLE, et un
        transport qui n'implemente pas `close_inflight` doit rester valide.
        """
        fermer = getattr(self._transport, "close_inflight", None)
        if fermer is None:
            return
        try:
            fermer()
        except Exception:
            pass

    def _complete(self, system: str, messages: list[dict], *,
                  temperature=None, max_tokens=_GEN_MAX_TOKENS,
                  timeout=_DEFAULT_TIMEOUT) -> str:
        """``timeout`` non fourni -> `_TIMEOUT` (le defaut historique) ;
        ``timeout=None`` -> AUCUN delai, transmis tel quel a `urlopen`.

        `generate_code` passe `None` (TODO #24) : une generation simplement
        lente etait tuee et l'utilisateur perdait tout. Les autres appels
        (reparation, explication, lint) gardent le delai — ils n'ont pas de
        bouton « Annuler », donc le leur retirer ne ferait qu'ajouter une
        requete que rien n'arreterait."""
        payload = self._payload(system, messages, temperature=temperature,
                                max_tokens=max_tokens, stream=False)
        url = f"{self._base_url}/chat/completions"
        try:
            data = self._transport.post_json(
                url, self._headers(), payload,
                _TIMEOUT if timeout is _DEFAULT_TIMEOUT else timeout)
            content = data["choices"][0]["message"]["content"]
            return content if content is not None else ""
        except HttpError as e:
            raise RuntimeError(_error_message(_status_kind(e.status))) from e
        except ConnectionError as e:
            raise RuntimeError(_error_message("network")) from e
        except (KeyError, IndexError, TypeError, ValueError) as e:
            raise RuntimeError(_error_message("bad_response")) from e

    # ── Code generation / repair / explanation ──────────────────────────────
    def generate_code(self, user_prompt: str, board_name: str,
                      rules_prompt: str | None = None) -> str:
        rules = rules_prompt if rules_prompt is not None else user_prompt
        system = self._build_system_prompt(board_name, rules)
        return self._clean(self._complete(
            system, [{"role": "user", "content": user_prompt}],
            temperature=self._code_temp, timeout=None))

    def fix_code(self, code: str, error: str, board_name: str) -> str:
        return self._clean(self._complete(
            self._build_fix_system_prompt(board_name),
            [{"role": "user", "content": self._build_fix_user_message(code, error)}],
            temperature=self._code_temp))

    def explain_error(self, error: str, language: str) -> str:
        return self._clean(self._complete(
            "", [{"role": "user",
                  "content": self._build_explain_prompt(error, language)}],
            max_tokens=_CHAT_MAX_TOKENS))

    def explain_code(self, code: str, selection: str, language: str,
                     board_name: str) -> str:
        return self._complete(
            self._build_explain_code_system(board_name, language),
            [{"role": "user",
              "content": self._build_explain_code_user(code, selection)}],
            max_tokens=_CHAT_MAX_TOKENS).strip()

    def lint_code(self, code: str, language: str, board_name: str) -> str:
        return self._complete(
            self._build_lint_code_system(board_name, language),
            [{"role": "user", "content": self._build_lint_code_user(code)}],
            max_tokens=_CHAT_MAX_TOKENS).strip()

    def add_comments(self, code: str, language: str, board_name: str) -> str:
        return self._clean(self._complete(
            self._build_add_comments_system(board_name, language),
            [{"role": "user", "content": self._build_add_comments_user(code)}],
            temperature=self._code_temp))

    def repair_code(self, code: str, errors: str, language: str,
                    board_name: str) -> tuple[str, str]:
        raw = self._complete(
            self._build_repair_code_system(board_name, language, code, errors),
            [{"role": "user", "content": self._build_repair_code_user(code, errors)}],
            temperature=self._code_temp)
        return self._repair_from_response(code, raw)

    def repair_region(self, region: str, errors: str, language: str,
                      board_name: str) -> str:
        return self._clean(self._complete(
            self._build_repair_region_system(board_name),
            [{"role": "user",
              "content": self._build_repair_region_user(region, errors)}],
            temperature=self._code_temp))

    def _complete_stream(self, system: str, messages: list[dict], *,
                         temperature=None, max_tokens=_CHAT_MAX_TOKENS) -> Iterator[str]:
        payload = self._payload(system, messages, temperature=temperature,
                                max_tokens=max_tokens, stream=True)
        url = f"{self._base_url}/chat/completions"
        try:
            for line in self._transport.iter_sse(url, self._headers(),
                                                 payload, _TIMEOUT):
                line = line.strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                delta = (obj.get("choices") or [{}])[0].get("delta") or {}
                chunk = delta.get("content")
                if isinstance(chunk, str) and chunk:
                    yield chunk
        except HttpError as e:
            raise RuntimeError(_error_message(_status_kind(e.status))) from e
        except ConnectionError as e:
            raise RuntimeError(_error_message("network")) from e
        except (AttributeError, KeyError, IndexError, TypeError, ValueError) as e:
            raise RuntimeError(_error_message("bad_response")) from e

    def chat(self, system_prompt: str, messages: list[dict]) -> str:
        return self._complete(system_prompt, messages,
                              max_tokens=_CHAT_MAX_TOKENS)

    def chat_stream(self, system_prompt: str, messages: list[dict]):
        yield from self._complete_stream(system_prompt, messages)
