"""Ollama backend — uses the local Ollama server (http://localhost:11434)."""
import json
import os
import shutil
import sys
from pathlib import Path
import threading
import re
import urllib.error
import urllib.request

from .base import AIBackend

# Adjustable SLM/LLM boundary (billions of parameters). Movable in
# one line. Starting point: Gemma 2B / Mistral 7B = SLM; Llama 3 8B = LLM.
_SLM_MAX_PARAMS_B = 7.0


def _parse_param_size_b(text) -> float | None:
    """'8.0B' -> 8.0, '2.6B' -> 2.6, '350M' -> 0.35. None if not parsable."""
    if text is None:
        return None
    m = re.match(r"\s*([\d.]+)\s*([BMbm])", str(text))
    if not m:
        return None
    val = float(m.group(1))
    return val if m.group(2).upper() == "B" else val / 1000.0

# 127.0.0.1 and NOT localhost: on Windows, "localhost" tries IPv6 first
# (::1) whereas Ollama only listens on IPv4 → ~2 s of latency per request before
# falling back to 127.0.0.1. The literal address avoids DNS/IPv6 resolution.
_BASE_URL = "http://127.0.0.1:11434"
_TIMEOUT_CHECK = 3    # seconds — availability ping
_TIMEOUT_GEN   = 300  # seconds — code generation (can be long)

# LOW temperature for ALL code tasks (generation, repair,
# explanation, comments, lint — they all go through _call). The Ollama
# default (~0.8) is too high for a local SLM: it occasionally picks an
# improbable path → prose without code, missing void setup()/loop(), a
# hallucinated constant. 0.25 = deterministic without freezing (0 can loop on some
# models). CHAT keeps the default (chat()/chat_stream(), /api/chat) to
# stay natural. This is THE knob to tune if the generated code varies too much / goes off the rails.
_CODE_TASK_TEMPERATURE = 0.25


# ── Server helpers ───────────────────────────────────────────────────────────

def _get(path: str, timeout: int = _TIMEOUT_CHECK) -> dict:
    with urllib.request.urlopen(f"{_BASE_URL}{path}", timeout=timeout) as r:
        return json.loads(r.read())


def _post(path: str, payload: dict, timeout: int | None = _TIMEOUT_GEN,
          register=None) -> dict:
    """POST JSON, reponse JSON.

    ``timeout=None`` : AUCUN delai. Sur cet endpoint le serveur n'envoie RIEN
    avant d'avoir fini, donc le delai de socket est en pratique un delai TOTAL
    de generation — c'est lui qui tuait une requete simplement lente (TODO #24).

    ``register`` : appele avec la reponse ouverte, puis avec ``None`` a la
    fermeture. C'est ce qui rend l'appel annulable : sans delai, fermer la
    reponse depuis un autre thread est la SEULE facon d'en sortir.
    """
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{_BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        if register is not None:
            register(r)
        try:
            return json.loads(r.read())
        finally:
            if register is not None:
                register(None)


def _post_stream(path: str, payload: dict, timeout: int = _TIMEOUT_GEN):
    """Streaming variant of _post. Yields each NDJSON line parsed
    into a dict as it arrives. The caller is responsible for extracting
    the useful field (e.g. message.content for /api/chat)."""
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        f"{_BASE_URL}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        for line in r:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def is_installed() -> bool:
    """Ollama est-il installe sur cette machine ?

    ⚠️ **`shutil.which` seul ne suffit pas.** Il lit le PATH DU PROCESSUS
    COURANT, et un processus ne voit jamais un PATH modifie apres son propre
    demarrage. Quelqu'un qui installe Ollama pendant que Promptuino est ouvert
    -- exactement ce que le message << le telecharger >> l'invite a faire --
    resterait donc invisible jusqu'au redemarrage de l'application.

    On regarde aussi les emplacements d'installation par defaut, comme
    `ui/arduino_cli.py::_candidate_paths()` le fait deja pour arduino-cli.

    ⚠️ Cette fonction n'est consultee que lorsque le SERVEUR ne repond pas :
    un Ollama qui tourne est detecte par HTTP, sans PATH ni fichier.
    """
    if shutil.which("ollama"):
        return True
    if sys.platform == "win32":
        bases = [os.environ.get("LOCALAPPDATA", ""), os.environ.get("ProgramFiles", ""),
                 os.environ.get("ProgramW6432", "")]
        chemins = [Path(b) / "Programs" / "Ollama" / "ollama.exe" for b in bases if b]
        chemins += [Path(b) / "Ollama" / "ollama.exe" for b in bases if b]
    elif sys.platform == "darwin":
        chemins = [Path("/usr/local/bin/ollama"),
                   Path("/opt/homebrew/bin/ollama"),
                   Path("/Applications/Ollama.app/Contents/Resources/ollama")]
    else:
        chemins = [Path("/usr/local/bin/ollama"), Path("/usr/bin/ollama"),
                   Path.home() / ".local" / "bin" / "ollama"]
    return any(p.is_file() for p in chemins)


def is_server_running() -> bool:
    """Returns True if the Ollama server responds on localhost:11434."""
    try:
        _get("/api/tags")
        return True
    except Exception:
        return False


def list_local_models() -> list[str]:
    """Returns the list of model names available locally."""
    try:
        data = _get("/api/tags")
        return [m["name"] for m in data.get("models", [])]
    except Exception:
        return []


def is_model_available(model: str) -> bool:
    """Returns True if the model is downloaded locally."""
    try:
        models = list_local_models()
        # Exact match or by prefix (e.g. "gemma4" matches "gemma4:e2b")
        tag_prefix = model.split(":")[0]
        return any(m == model or m.split(":")[0] == tag_prefix for m in models)
    except Exception:
        return False


# ── Backend ───────────────────────────────────────────────────────────────────

class OllamaBackend(AIBackend):

    def __init__(self, model: str = "gemma4:e2b"):
        self._model = model.strip() or "gemma4:e2b"
        self._show_cache: dict | None = None  # cache /api/show (lazy)
        # Reponse en vol d'une tache de CODE (non streamee). Le verrou protege
        # l'echange entre le thread worker qui la pose et le thread UI qui
        # l'annule. Le chat, lui, streame : son drapeau cooperatif est lu au
        # chunk suivant, donc il n'a besoin de rien de tout ca.
        self._inflight = None
        self._inflight_lock = threading.Lock()

    def _register_inflight(self, response) -> None:
        with self._inflight_lock:
            self._inflight = response

    def cancel(self) -> None:
        """Coupe la requete de CODE en cours (cf. `AIBackend.cancel`).

        ⚠️ Cet override est devenu OBLIGATOIRE avec le TODO #24 : tant que
        `_post` avait un delai de 300 s, ce delai finissait par liberer le
        thread. Sans delai, fermer la reponse est la seule sortie.

        Best-effort ASSUME : fermer une reponse ne debloque pas un `read()`
        deja engage sur toutes les plateformes. Ce n'est pas grave, et c'est un
        choix — l'appelant DETACHE le worker (patron du chat, `_on_stop_clicked`),
        donc l'utilisateur retrouve la main immediatement de toute facon ; ce
        qui reste ici ne decide que du sort d'un thread orphelin.
        """
        with self._inflight_lock:
            r = self._inflight
        if r is None:
            return
        try:
            r.close()
        except Exception:
            pass

    @property
    def backend_id(self) -> str:
        return "ollama"

    @property
    def name(self) -> str:
        return "Ollama (local)"

    @property
    def description(self) -> str:
        return f"Utilise le serveur Ollama local — modèle {self._model}."

    @property
    def requires_api_key(self) -> bool:
        return False

    def is_available(self) -> bool:
        """True if the server is running AND the model is available locally."""
        return is_server_running() and is_model_available(self._model)

    def _show(self) -> dict:
        """Fetches /api/show once and caches it. {} if unavailable."""
        if self._show_cache is not None:
            return self._show_cache
        try:
            data = _post("/api/show", {"model": self._model},
                         timeout=_TIMEOUT_CHECK)
        except Exception:
            data = {}
        self._show_cache = data
        return data

    @property
    def context_window_hint(self) -> int:
        info = self._show().get("model_info") or {}
        for k, v in info.items():
            if k.endswith(".context_length") and isinstance(v, (int, float)) \
                    and v > 0:
                return int(v)
        return 8192

    def generation_context(self) -> int:
        """Ce que `_call` alloue REELLEMENT pour une generation, prompt ET
        sortie. Source unique : `_call` lit cette methode, elles ne peuvent
        donc plus diverger — c'est tout l'interet, un garde-fou calcule sur un
        chiffre different de celui qui est alloue ne garderait rien."""
        return min(8192, self.context_window_hint)

    def effective_chat_context(self) -> int:
        """Chat budget = what we ask Ollama to allocate (num_ctx), bounded by
        the model's real context. Read live from ai_config so the IA-tab slider
        takes effect without re-instantiating the backend."""
        from ..ai_config import ai_config   # lazy import: avoid any cycle
        return min(ai_config.ollama_num_ctx, self.context_window_hint)

    @property
    def is_slm(self) -> bool:
        details = self._show().get("details") or {}
        b = _parse_param_size_b(details.get("parameter_size"))
        if b is None:  # fallback: parse the model name ("gemma:2b")
            m = re.search(r"(\d+\.?\d*)\s*b\b", self._model.lower())
            if m:
                b = float(m.group(1))
        if b is None:
            return False  # unknown size -> conservative (treat as LLM)
        return b <= _SLM_MAX_PARAMS_B

    def generate_code(self, user_prompt: str, board_name: str,
                      rules_prompt: str | None = None) -> str:
        """⚠️ SANS DELAI (TODO #24). Une generation simplement lente etait
        TUEE a 300 s et l'utilisateur perdait tout. La sortie n'est plus un
        couperet mais le bouton « Annuler », qui appelle `cancel()`."""
        prompt = self._build_full_prompt(user_prompt, board_name, rules_prompt)
        return self._clean(self._call(prompt, timeout=None))

    def fix_code(self, code: str, error: str, board_name: str) -> str:
        prompt = (
            f"{self._build_fix_system_prompt(board_name)}\n\n"
            f"{self._build_fix_user_message(code, error)}"
        )
        return self._clean(self._call(prompt))

    def explain_error(self, error: str, language: str) -> str:
        return self._clean(self._call(self._build_explain_prompt(error, language)))

    def explain_code(self, code: str, selection: str, language: str,
                     board_name: str) -> str:
        prompt = (
            f"{self._build_explain_code_system(board_name, language)}\n\n"
            f"{self._build_explain_code_user(code, selection)}"
        )
        return self._call(prompt).strip()

    def lint_code(self, code: str, language: str, board_name: str) -> str:
        prompt = (
            f"{self._build_lint_code_system(board_name, language)}\n\n"
            f"{self._build_lint_code_user(code)}"
        )
        return self._call(prompt).strip()

    def add_comments(self, code: str, language: str, board_name: str) -> str:
        prompt = (
            f"{self._build_add_comments_system(board_name, language)}\n\n"
            f"{self._build_add_comments_user(code)}"
        )
        return self._clean(self._call(prompt))

    def repair_code(self, code: str, errors: str, language: str,
                    board_name: str) -> tuple[str, str]:
        prompt = (
            f"{self._build_repair_code_system(board_name, language, code, errors)}\n\n"
            f"{self._build_repair_code_user(code, errors)}"
        )
        return self._repair_from_response(code, self._call(prompt))

    def repair_region(self, region: str, errors: str, language: str,
                      board_name: str) -> str:
        # LIGHTWEIGHT prompt: only the lines flagged by the compiler. On a
        # local SLM, fixing 5 targeted lines succeeds where rewriting the whole
        # file fails (cf. base.repair_region for the generic default).
        prompt = (
            f"{self._build_repair_region_system(board_name)}\n\n"
            f"{self._build_repair_region_user(region, errors)}"
        )
        return self._clean(self._call(prompt))

    def chat(self, system_prompt: str,
              messages: list[dict]) -> str:
        # Ollama supports /api/chat natively with the messages format.
        full_messages = (
            [{"role": "system", "content": system_prompt}]
            + list(messages)
        )
        try:
            result = _post("/api/chat", {
                "model": self._model,
                "messages": full_messages,
                "stream": False,
                "think": False,   # reasoning models (qwen3.5…): otherwise the
                                  # reasoning fills the `thinking` field and eats
                                  # num_predict, leaving `response` empty.
                "options": {
                    "num_predict": 2048,
                    "num_ctx": self.effective_chat_context(),
                },
            })
            return result["message"]["content"]
        except urllib.error.URLError:
            raise RuntimeError(
                "Ollama n'est pas lancé.\n"
                "Démarrez-le avec : ollama serve"
            )
        except Exception as e:
            raise RuntimeError(f"Erreur Ollama : {e}")

    def chat_stream(self, system_prompt: str,
                     messages: list[dict]):
        """Native streaming via /api/chat with stream:true. The server
        returns a succession of JSON lines; each one contains
        message.content with the incremental chunk, and done:true on the
        last line."""
        full_messages = (
            [{"role": "system", "content": system_prompt}]
            + list(messages)
        )
        try:
            for parsed in _post_stream("/api/chat", {
                "model": self._model,
                "messages": full_messages,
                "stream": True,
                "think": False,   # cf. chat(): disables reasoning so that
                                  # the content arrives in message.content.
                "options": {
                    "num_predict": 2048,
                    "num_ctx": self.effective_chat_context(),
                },
            }):
                if parsed.get("done"):
                    break
                msg = parsed.get("message") or {}
                chunk = msg.get("content") or ""
                if chunk:
                    yield chunk
        except urllib.error.URLError:
            raise RuntimeError(
                "Ollama n'est pas lancé.\n"
                "Démarrez-le avec : ollama serve"
            )
        except Exception as e:
            raise RuntimeError(f"Erreur Ollama : {e}")

    def _call(self, prompt: str, timeout: int | None = _TIMEOUT_GEN) -> str:
        """``timeout=None`` : aucun delai (TODO #24). Reserve aux appels que
        l'utilisateur peut ANNULER — aujourd'hui la seule generation. La
        reparation, l'explication et le lint gardent les 300 s : sans bouton
        d'annulation, retirer leur delai ne ferait qu'ajouter un thread
        orphelin que rien ne pourrait plus arreter."""
        try:
            result = _post("/api/generate", timeout=timeout,
                           register=self._register_inflight, payload={
                "model": self._model,
                "prompt": prompt,
                "stream": False,
                "think": False,   # cf. chat(): without this, qwen3.5 & co start
                                  # reasoning and `response` stays empty (or times out).
                # EXPLICIT token budget. Without this, /api/generate uses the
                # model's default num_ctx (often 4096): on
                # generation/repair, prompt (system + full code + errors)
                # PLUS the output (full code) exceed the window → the end of the
                # code is truncated. num_predict=-1: generate until the
                # natural end (no hard cap). num_ctx capped by what the
                # model actually supports (context_window_hint).
                "options": {
                    "num_ctx": self.generation_context(),
                    "num_predict": -1,
                    # Code tasks -> low temperature (cf. _CODE_TASK_TEMPERATURE).
                    "temperature": _CODE_TASK_TEMPERATURE,
                },
            })
            return result.get("response", "")
        except urllib.error.URLError:
            raise RuntimeError(
                "Ollama n'est pas lancé.\n"
                "Démarrez-le avec : ollama serve"
            )
        except Exception as e:
            raise RuntimeError(f"Erreur Ollama : {e}")
