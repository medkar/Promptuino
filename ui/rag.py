"""Library retrieval (RAG) — runtime entry point.

Public API: ``retrieve_libs(prompt, k=3, threshold=0.25)`` returns the top-K
corpus entries whose embedded description+keywords best match the user
prompt by cosine similarity, filtered by ``threshold``.

The model, corpus and embedding matrix are loaded lazily on first call and
cached for the process lifetime. Any failure (missing assets, model load
error, encode error) returns an empty list so the caller can degrade
gracefully — no library context is better than the wrong context.

Stack: onnxruntime + tokenizers, model = paraphrase-multilingual-MiniLM-L12-v2
exported to ONNX (int8 dynamic quantized, ~113 MB). The model lives under
``assets/rag/model/`` — fully self-contained, no HF Hub call at runtime. See
``scripts/export_onnx_model.py`` for the one-shot conversion pipeline.
"""
from __future__ import annotations

import json
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parent.parent
_CORPUS_PATH = _REPO_ROOT / "assets" / "rag" / "corpus.json"
_EMBEDDINGS_PATH = _REPO_ROOT / "assets" / "rag" / "embeddings.npy"
_MODEL_DIR = _REPO_ROOT / "assets" / "rag" / "model"
_MODEL_PATH = _MODEL_DIR / "model.onnx"
_TOKENIZER_PATH = _MODEL_DIR / "tokenizer.json"
_MAX_SEQ_LEN = 128  # sentence-transformers default for this checkpoint

_lock = threading.Lock()
_corpus: list[dict] | None = None
_corpus_by_id: dict[str, dict] | None = None
_embeddings: np.ndarray | None = None
_session: Any | None = None
_tokenizer: Any | None = None
_input_names: set[str] = set()
_load_failed = False          # failure of the SEMANTIC path (encoder + embeddings)
_corpus_load_failed = False   # failure of the corpus-only load (corpus.json missing/corrupted)

# ── UI status sink ────────────────────────────────────────────────────────────
# The "[RAG] …" diagnostics used to go to stdout ONLY — invisible in the
# packaged app, so every degraded mode (embeddings desync, nothing retrieved,
# basic-component guard…) failed 100 % silently for the user. The studio view
# registers a sink here to mirror those messages into the generation journal.
# The sink runs on whatever thread calls the RAG (UI thread today); it must
# never raise into the retrieval path.
_status_sink = None


def set_status_sink(fn) -> None:
    """Register a callable(str) that receives every ``[RAG]`` status message
    (in addition to stdout). Pass ``None`` to unregister."""
    global _status_sink
    _status_sink = fn


def _log(msg: str) -> None:
    """Print ``msg`` to stdout AND mirror it to the UI sink (if any)."""
    print(msg, flush=True)
    sink = _status_sink
    if sink is not None:
        try:
            sink(msg)
        except Exception:
            pass


def _load_encoder() -> bool:
    """Load ONLY the ONNX model + the tokenizer (neither corpus nor
    embeddings). Used by `_load()` AND by
    scripts/build_rag_embeddings.py — the latter must be able to encode even
    when embeddings.npy is stale or absent, otherwise the rebuild would be
    impossible (chicken-and-egg).

    Acquires `_lock` itself; do NOT call it from a block that already holds
    `_lock` (Lock is non-reentrant)."""
    global _session, _tokenizer, _input_names
    if _session is not None and _tokenizer is not None:
        return True
    with _lock:
        if _session is not None and _tokenizer is not None:
            return True
        try:
            if not _MODEL_PATH.exists() or not _TOKENIZER_PATH.exists():
                return False
            import onnxruntime as ort
            from tokenizers import Tokenizer

            tokenizer = Tokenizer.from_file(str(_TOKENIZER_PATH))
            tokenizer.enable_padding()
            tokenizer.enable_truncation(max_length=_MAX_SEQ_LEN)
            session = ort.InferenceSession(
                str(_MODEL_PATH), providers=["CPUExecutionProvider"]
            )
            _session = session
            _tokenizer = tokenizer
            _input_names = {i.name for i in session.get_inputs()}
            return True
        except Exception:
            return False


def _load_corpus() -> bool:
    """Load ONLY `corpus.json` (neither the ONNX encoder nor the embeddings).

    Decoupled from `_load()` on purpose: the **curated clarification** (keywords →
    corpus ids) and the lexical "named chip" guard must work even
    when the ONNX encoder is unavailable (e.g. onnxruntime failing to load) —
    otherwise an encoder failure ALSO shuts down the clarification, silently.

    Acquires `_lock` itself; do NOT call it while already holding `_lock`."""
    global _corpus, _corpus_by_id, _corpus_load_failed
    if _corpus is not None:
        return True
    if _corpus_load_failed:
        return False
    with _lock:
        if _corpus is not None:
            return True
        if _corpus_load_failed:
            return False
        try:
            if not _CORPUS_PATH.exists():
                _corpus_load_failed = True
                return False
            with _CORPUS_PATH.open(encoding="utf-8") as f:
                corpus = json.load(f)
            _corpus = corpus
            _corpus_by_id = {e["id"]: e for e in corpus if e.get("id")}
            return True
        except Exception:
            _corpus_load_failed = True
            return False


def _load() -> bool:
    """Load the full SEMANTIC path: encoder + corpus + embeddings.

    Returns True on success. Independent of `_load_corpus()` (which can succeed
    on its own): here we need both the encoder AND the embedding matrix aligned
    with the corpus."""
    global _embeddings, _load_failed
    if _load_failed:
        return False
    if (
        _corpus is not None
        and _embeddings is not None
        and _session is not None
        and _tokenizer is not None
    ):
        return True
    if not _load_encoder():
        _load_failed = True
        return False
    if not _load_corpus():
        _load_failed = True
        return False
    with _lock:
        if _load_failed:
            return False
        if _embeddings is not None:
            return True
        try:
            if not _EMBEDDINGS_PATH.exists():
                _load_failed = True
                return False
            embeddings = np.load(_EMBEDDINGS_PATH)
            if embeddings.shape[0] != len(_corpus):
                # Desync: we REFUSE (skewed results otherwise) but we SAY so
                # — without this log, the failure is silent (RAG shut down with
                # no trace at all). Cf. scripts/build_rag_embeddings.py.
                _log(
                    f"[RAG] DÉSACTIVÉ : embeddings ({embeddings.shape[0]}) "
                    f"désync avec corpus ({len(_corpus)}). "
                    f"Lance scripts/build_rag_embeddings.py — aucun exemple "
                    f"de lib ne sera injecté."
                )
                _load_failed = True
                return False
            _embeddings = embeddings.astype(np.float32, copy=False)
            return True
        except Exception:
            _load_failed = True
            return False


def corpus_entry(entry_id: str) -> dict | None:
    """Copy of the corpus entry with id `entry_id`, or None. Loads the corpus
    alone (without the encoder) if needed. Used by the curated clarification to
    turn an id into a real corpus entry (forceable via forced_libs)."""
    if not _load_corpus():
        return None
    e = (_corpus_by_id or {}).get(entry_id)
    return dict(e) if e is not None else None


def all_corpus_entries() -> list[dict]:
    """Every curated corpus entry, or [] if the corpus is unreadable.

    Exposed so consumers stop re-reading corpus.json on their own: two readers
    of the same file drift the moment one of them forgets a field.

    Each entry is a SHALLOW copy (`dict(e)`, same discipline as `corpus_entry`
    just above): `list(_corpus)` only copied the outer list, so every dict was
    still the cache's own object -- an accessor whose reason to exist is to
    prevent drift between readers was handing out the live entries while its
    docstring claimed a copy. Nested values (keywords, headers) are still
    shared: do not mutate those in place.
    """
    if not _load_corpus():
        return []
    return [dict(e) for e in (_corpus or [])]


def module_forced_libs(prompt: str) -> list[dict]:
    """Si le prompt nomme un module hardware (HW-612…), retourne les entrées
    corpus de ses puces (à forcer dans le contexte de génération, comme un choix
    de clarification). Liste vide sinon.

    Les puces sont résolues **via le registre de composants** (`chip → documents
    → entrées corpus`), et non par égalité de chaîne avec un id de corpus.

    Pourquoi (mesuré le 2026-08-18, TODO #54 étape 2) : `HardwareModule.chips`
    doit désigner **à la fois** un id de registre — le câblage s'en sert pour
    fusionner la boîte — et la source des libs à forcer. Or **29 composants sur
    148 ont un id qui n'est PAS un id de corpus** (`mpu6050` → document
    `adafruit-mpu6050`, `dht22` → `dht-sensor-library`, `hcsr04` → `newping`…).
    L'égalité de chaîne ne tenait que pour le HW-612, dont les deux puces
    (`mpu9250`, `bmp280`) se trouvent porter le même nom des deux côtés — la
    cinquième « jointure par coïncidence » du même genre que les quatre que le
    registre a remplacées.

    Conséquence concrète : déclarer un GY-521 (MPU6050) était **impossible** —
    `chips=("mpu6050",)` passait la garde du registre en ne forçant AUCUNE
    bibliothèque, et `chips=("adafruit-mpu6050",)` aurait forcé la lib en
    cassant la garde et la fusion du schéma.

    Repli conservé sur l'ancien comportement (la puce lue comme un id de corpus)
    pour ne rien retirer ; la tolérance d'origine est intacte : une puce qui ne
    résout nulle part est ignorée, et `test_every_module_chip_actually_forces_a_library`
    empêche qu'elle passe inaperçue.
    """
    from .hardware_modules import detect_module
    mod = detect_module(prompt)
    if mod is None:
        return []
    from .component_registry import by_id as _component_by_id
    out: list[dict] = []
    seen: set[str] = set()
    for chip_id in mod.chips:
        comp = _component_by_id(chip_id)
        doc_ids = list(comp.documents) if comp is not None else [chip_id]
        for doc_id in doc_ids or [chip_id]:
            if doc_id in seen:
                continue
            entry = corpus_entry(doc_id)
            if entry is not None:
                seen.add(doc_id)
                out.append(entry)
    return out


def forced_libs_for_generation(prompt: str) -> list[dict]:
    """Libs a FORCER dans le contexte de generation, SANS aucune modale
    (decision 2026-07-08). On garde les DEUX forcages silencieux qui existaient
    avant, seule la fenetre de clarification a disparu :
      1. puces des modules NOMMES (HW-612...) -> module_forced_libs ;
      2. puces NOMMEES d'une famille (SSD1306, VMA335...) auto-resolues par
         detect_lib_ambiguities (2e valeur = auto_forced), qui n'ouvraient
         deja PAS de modale.
    Les familles restees AMBIGUES (1re valeur = to_clarify) sont ignorees : le
    RAG choisit la lib la plus probable, correction a posteriori dans le schema.
    Dedoublonne par id ; ordre : module d'abord, puis puce nommee."""
    module_forced = module_forced_libs(prompt)
    _to_clarify, auto_forced = detect_lib_ambiguities(prompt)
    out: list[dict] = []
    seen: set[str | None] = set()
    for lib in list(module_forced) + list(auto_forced):
        lid = lib.get("id")
        if lid not in seen:
            seen.add(lid)
            out.append(lib)
    return out


def prompt_names_a_chip(prompt: str) -> bool:
    """True if the prompt contains a "part-number" token of a corpus
    entry (e.g. ``dht22``, ``bme280``, ``ssd1306``) → the user named their
    chip explicitly. Purely lexical (reuses `_signature_tokens`), so
    reliable even without the ONNX encoder. Serves as a "named = no modal" guard."""
    if not prompt or not prompt.strip():
        return False
    if not _load_corpus():
        return False
    prompt_tokens = _prompt_tokens(prompt)
    if not prompt_tokens:
        return False
    for entry in _corpus:
        if _signature_tokens(entry) & prompt_tokens:
            return True
    return False


def named_corpus_libs(prompt: str) -> list[dict]:
    """Corpus entries whose part-number the prompt writes VERBATIM.

    Same lexical criterion as `prompt_names_a_chip` (which only answers
    yes/no), so it inherits the strictness of `_signature_tokens`: a chip is
    "named" or it is not — no score, no threshold, nothing to calibrate.

    Exists for TODO #40 part 2 (a). When an unknown part-number suppresses the
    semantic retrieval (#37), the suppression used to take the chips the user
    NAMED with it. One net caught some of them, `forced_libs_for_generation`,
    but it only sees candidates of a curated `ClarifyGroup`: 62 of the 91
    corpus entries. Measured 2026-08-10, the 29 others fell through — among
    them `servo`, `adafruit-neopixel`, `hx711`, `keypad`, `irremote`,
    `pir-motion-sensor`, `tinygps-plus`, `l298n`, `nema17`, `onewire`.

    Order follows the corpus so the result is stable across runs (a `set`
    would make the injected block depend on PYTHONHASHSEED — the bug found in
    the #37 review)."""
    if not prompt or not prompt.strip():
        return []
    if not _load_corpus():
        return []
    prompt_tokens = _prompt_tokens(prompt)
    if not prompt_tokens:
        return []
    return [dict(entry) for entry in _corpus
            if _signature_tokens(entry) & prompt_tokens]


_known_part_tokens_cache: set[str] | None = None


def known_part_tokens() -> set[str]:
    """Union of the "part-number" signature tokens of ALL corpus entries
    (cf. ``_signature_tokens``). Cached for the process lifetime (the corpus is
    immutable at runtime). Used by ``registry_lookup.detect_unknown_part_tokens``
    to tell "the user named a chip we KNOW" from "the user named a chip the
    corpus has never heard of". Empty set if the corpus cannot be loaded."""
    global _known_part_tokens_cache
    if _known_part_tokens_cache is None:
        if not _load_corpus():
            return set()
        toks: set[str] = set()
        for entry in _corpus:
            toks |= _signature_tokens(entry)
        _known_part_tokens_cache = toks
    return _known_part_tokens_cache


def encode(texts: list[str]) -> np.ndarray:
    """Encode a batch of texts into L2-normalized embeddings (float32).

    Mean-pools the token embeddings using the attention mask, then
    L2-normalizes — same recipe sentence-transformers applies for this
    checkpoint. Returns shape (len(texts), 384). Raises if the model is
    not loaded; callers in this module rely on ``_load()`` first.
    """
    encs = _tokenizer.encode_batch(texts)
    ids = np.array([e.ids for e in encs], dtype=np.int64)
    mask = np.array([e.attention_mask for e in encs], dtype=np.int64)
    inputs = {"input_ids": ids, "attention_mask": mask}
    if "token_type_ids" in _input_names:
        inputs["token_type_ids"] = np.zeros_like(ids)
    token_embeds = _session.run(None, inputs)[0]  # (B, L, D)

    mask_f = mask.astype(np.float32)[..., None]
    summed = (token_embeds * mask_f).sum(axis=1)
    counts = np.maximum(mask_f.sum(axis=1), 1e-9)
    pooled = summed / counts

    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return (pooled / norms).astype(np.float32)


# NOTE (mesuré 2026-07-29) — DÉCOUPAGE du fichier de contexte : écarté.
# L'encodeur tronque à _MAX_SEQ_LEN (128 tokens), donc un long fichier de
# contexte n'est que partiellement vu par la similarité. Le découper en morceaux
# encodés séparément (similarité = max sur les morceaux) a été implémenté puis
# RETIRÉ après mesure :
#   - le gain réel est quasi nul — le BOOST LEXICAL scanne déjà le texte ENTIER,
#     donc une puce NOMMÉE en fin de fichier remonte de toute façon (mesuré :
#     DHT22 cité après 30 lignes de remplissage sort quand même top-1 à 0.527) ;
#   - le coût est réel : chaque morceau a sa propre chance de dépasser le
#     plancher, donc des lignes de prose sans rapport font remonter des libs au
#     hasard (mesuré : INA3221 / ILI9341 / TM1637 sur un texte de câblage
#     générique) — exactement le bruit qu'on cherche à supprimer.
# Rouvrir seulement avec une meilleure idée que « max sur les morceaux ».


# Hedged header for a lib that only surfaced by similarity (not named/forced):
# the model must be free to ignore it. Shared verbatim between the "pure
# retrieval" path and the declared-component supplement block below — a
# second copy would drift the wording the #37 authority split relies on.
_HEDGED_HEADER = (
    "Possibly relevant Arduino libraries (retrieved by similarity, the "
    "user did not name a chip). If one of them drives the component the "
    "user described, use its exact APIs and patterns as shown — do not "
    "invent function names. If NONE of them matches the requested "
    "component, IGNORE this section entirely and write a plain sketch "
    "for the described component: never use a library written for a "
    "different part."
)


def _lib_key(lib: dict) -> str:
    """Dedup key for a lib entry: its corpus/registry id when present, else
    its display name. Used so a lib already in the forced (imperative) block
    never ALSO shows up in the retrieved (hedged) supplement block — a weak
    SLM handed the same lib twice under two contradictory tones is exactly
    the confusion this split exists to avoid."""
    return str(lib.get("id") or lib.get("name") or "")


def _render_lib_block(lib: dict) -> str:
    """Render one corpus/forced/registry entry as a markdown-ish block: name,
    headers, API signatures (if any) and example code."""
    name = lib.get("name") or lib.get("id") or ""
    headers = lib.get("headers") or []
    headers_line = ", ".join(f"`{h}`" for h in headers) if headers else "—"
    example = (lib.get("example_code") or "").strip()
    api_block = _format_api_signatures(lib.get("api_signatures") or {}, example)
    parts = [f"### {name}", f"Headers: {headers_line}"]
    if api_block:
        parts.append(api_block)
    parts.append(f"Example:\n```cpp\n{example}\n```")
    return "\n".join(parts)


def build_lib_context(prompt: str, k: int = 3, threshold: float | None = None,
                      forced_libs: list[dict] | None = None,
                      declared_component_forced: bool = False,
                      on_resemblance: Callable[[bool], None] | None = None,
                      ranking_hint: str = ""
                      ) -> str:
    """Enveloppe publique de `_build_lib_context` : rend le contexte seul.

    Tous les paramètres sauf ``on_resemblance`` sont transmis tels quels et
    documentés dans `_build_lib_context` — c'est elle qui les utilise, et n'en
    tenir qu'une seule description évite qu'elles divergent.

    ``on_resemblance`` (TODO #61), quand il est fourni, est appelé EXACTEMENT
    UNE FOIS avant le retour, avec ``True`` si les libs du bloc ont été
    choisies par similarité sémantique pour un prompt qui ne nommait rien de
    reconnu. C'est l'app qui a deviné, et l'utilisateur ne l'apprenait nulle
    part : le modèle, lui, était déjà prévenu par un en-tête hedgé.

    Un rappel PAR APPEL plutôt qu'un enregistrement au niveau du module : ce
    dernier créerait un couplage temporel (un appelant qui lit après un chemin
    n'ayant pas rappelé la fonction obtiendrait une valeur périmée). Et plutôt
    qu'une valeur de retour : ça changerait la signature d'une fonction
    appelée par six scripts de test et trois sites de production, pour un
    booléen. Par défaut ``None`` — aucun appelant existant n'est modifié.
    """
    ctx, by_resemblance = _build_lib_context(
        prompt, k=k, threshold=threshold, forced_libs=forced_libs,
        declared_component_forced=declared_component_forced,
        ranking_hint=ranking_hint)
    if on_resemblance is not None:
        on_resemblance(by_resemblance)
    return ctx


def _build_lib_context(prompt: str, k: int = 3, threshold: float | None = None,
                       forced_libs: list[dict] | None = None,
                       declared_component_forced: bool = False,
                       ranking_hint: str = ""
                       ) -> tuple[str, bool]:
    """Run retrieval and format results as a context block ready to be
    prepended to a user prompt. Empty string if no lib clears the threshold
    or RAG is unavailable. Logs the retrieved libs to stdout for tracing.

    ``threshold`` defaults to ``_CODEGEN_MIN_SCORE`` (the code-gen injection
    floor) when left ``None`` — a literal default can't reference that constant
    here as it is defined further down the module.

    ``prompt`` is used both for retrieval and for logging — pass the bare
    user prompt here, not a wrapped/instrumented prompt.

    If ``forced_libs`` is provided (multi-family clarification, module,
    part-number lookup, declared component…), we skip the retrieval and
    format THESE entries (typically a single one, the chip chosen by the
    user or resolved for them).

    ``declared_component_forced`` (TODO #40, part 1): set by the caller when
    — and ONLY when — ``forced_libs`` was populated by the user-declared-
    component trigger (``studio_view._declared_lookup_request``) with no
    unknown-part-number token also involved. Full suppression of the
    retrieval is deliberate and MEASURED for the part-number trigger (a named
    but corpus-unknown chip makes semantic retrieval toxic — see
    ``registry_lookup``) and for the empty-``forced_libs`` case (registry
    found nothing either); it was never measured or intended for the
    declared-component trigger, which just matches the user's own keywords.
    When true, the retrieval still runs, but strictly as a SEPARATE, hedged
    supplement block appended after the imperative one — never merged into
    it (that would either make the forced lib permissive or the retrieved
    lib falsely authoritative, the exact regression #37 fixed). Defaults to
    ``False`` so every existing caller keeps today's behavior unchanged.

    ``ranking_hint`` (TODO #64) : les numeros de piece que le projet utilise
    DEJA (« bme280 »), fabriques par `project_chips.chip_hint`. Ajoute au seul
    texte donne a ``retrieve_libs`` — donc au CLASSEMENT, et a rien d'autre.

    ⚠️ C'est la toute la subtilite, et elle est deliberee. Le reflexe serait de
    le coller au ``prompt`` comme le fait deja ``retrieval_context`` ; ce
    serait changer trois choses de plus, dont deux qu'on ne demande pas :

      1. l'AUTORITE de l'en-tete (``prompt_names_a_chip`` ci-dessous). Mesure
         du 2026-08-26 : sur les 40 cas de la batterie C, **21** passeraient de
         hedge a imperatif. Or la regle categorielle dit « l'utilisateur a
         nomme une puce, ou pas » — ici c'est l'APP qui l'a lue dans le code.
         La distinction se perdrait sans que la mesure l'ait demande : le gain
         mesure (7 fautes -> 0) vient du classement seul.
      2. la garde « composant de base » : « fais clignoter la LED plus vite »
         sur un projet BME280 n'injecte RIEN aujourd'hui, et un indice colle au
         prompt ferait sauter la garde. Zero cas de la batterie C le montre —
         elle ne contient aucun prompt de ce genre, donc ce zero est un trou de
         couverture, pas une preuve.
      3. la note « module » et ``named_corpus_libs``, qui lisent aussi ``prompt``.

    Cadeau du meme choix : le court-circuit « scanner I2C » et le journal
    restent sur le texte de l'utilisateur.

    Rend ``(contexte, choisi_par_ressemblance)``. Le second dit que les libs
    du bloc viennent de ``retrieve_libs`` pour un prompt qui ne nommait rien
    de reconnu — donc une DEVINETTE, que l'utilisateur a le droit de
    connaître (TODO #61). Il est faux pour tout le reste, y compris le
    court-circuit « scanner I2C », dont l'injection est déterministe bien que
    son en-tête soit hedgé.
    """
    if threshold is None:
        threshold = _CODEGEN_MIN_SCORE
    # Le SEUL texte qui porte l'indice. Tout le reste de cette fonction lit
    # `prompt` — cf. la docstring, c'est la raison d'etre du parametre.
    ranked_on = prompt
    if ranking_hint and ranking_hint.strip():
        ranked_on = prompt + "\n" + ranking_hint
    # Quelle branche a fourni les libs ? Un drapeau explicite plutôt qu'une
    # déduction a posteriori : une branche ajoutée plus tard devra se
    # positionner, au lieu de tomber par défaut du mauvais côté.
    plain_retrieval = False
    if forced_libs is not None:
        # TODO #40, part 2 (a): forcing a lib SUPPRESSES the semantic
        # retrieval, and that suppression is right — measured again on the
        # 2026-08-10 corpus, what similarity returns for a corpus-unknown part
        # is not noise but a FUNCTIONALLY ADJACENT chip (AS7341 → TCS34725,
        # VEML7700 → BH1750, ADS1220 → HX711), the substitution that compiles
        # and is silently wrong. But it was too wide: it also dropped the chips
        # the user NAMED. Those come back here — by the same lexical,
        # categorical criterion as `prompt_names_a_chip`, never by similarity,
        # so nothing is guessed and nothing is calibrated. They join the
        # AUTHORITATIVE block rather than a hedged one: on such a prompt they
        # are the only thing we are sure of.
        libs = list(forced_libs)
        forced_keys = {_lib_key(lib) for lib in libs}
        libs += [lib for lib in named_corpus_libs(prompt)
                 if _lib_key(lib) not in forced_keys]
    elif _prompt_is_i2c_scan(prompt):
        # I2C scanner: inject the canonical `Wire` (core lib) sketch
        # deterministically. No third-party lib is needed, but without context a
        # weak SLM hallucinates `#include <TwoWire.h>`. The example hands it the
        # correct `#include <Wire.h>` pattern. (Not retrievable: Wire is a core
        # lib outside the corpus, and the prompt scores as noise.)
        _log("[RAG] scanner I2C -> exemple Wire (core) injecte")
        libs = [dict(_WIRE_I2C_SCANNER_REF)]
    else:
        plain_retrieval = True
        # "Basic component" guard: a plain LED, button, buzzer, pot… need
        # NO library. We do NOT run the retrieval — otherwise the
        # low threshold (0.25) lets through off-topic, weakly
        # correlated libs (e.g. "led on D10" → DallasTemperature / PCF8574 /
        # MCP23017) that pollute the prompt and derail the SLM. An
        # explicitly NAMED chip (DHT11, SSD1306…) disables the guard and stays
        # retrieved. Symmetric with guard 1.5 of the clarification pipeline.
        if _prompt_is_basic_component(prompt) and not prompt_names_a_chip(prompt):
            _log(f"[RAG] composant de base, aucune lib injectée : "
                 f"{prompt[:80]!r}")
            return "", False
        try:
            libs = retrieve_libs(ranked_on, k=k, threshold=threshold)
        except Exception as e:
            _log(f"[RAG] retrieve_libs failed: {e}")
            return "", False
    if not libs:
        _log(f"[RAG] no libs retrieved for prompt: {prompt[:80]!r}")
        return "", False
    lines = ["[RAG] retrieved:"]
    for lib in libs:
        api = lib.get("api_signatures") or {}
        n_sigs = sum(len(v) for v in api.values())
        # `_score` absent for a lib FORCED by the curated clarification (user
        # choice, not a similarity score) → tolerant log, no KeyError.
        score = lib.get("_score")
        score_str = f"{score:.3f}" if isinstance(score, (int, float)) else "forcé"
        lines.append(
            f"  {score_str}  {lib.get('name')}  "
            f"(api: {len(api)} classes / {n_sigs} signatures)"
        )
    _log("\n".join(lines))
    blocks: list[str] = [_render_lib_block(lib) for lib in libs]
    # ── Autorité du contexte : nommé/forcé vs simplement retrouvé ──────────
    # Le dégât d'un mauvais retrieval n'est pas seulement « la mauvaise lib est
    # remontée » : c'est qu'elle est présentée comme FAISANT AUTORITÉ
    # (« reference these exact APIs »), donc le SLM l'utilise docilement pour un
    # composant qui n'a rien à voir. Quand l'utilisateur a NOMMÉ sa puce (ou
    # qu'elle est forcée : module, clarification, registre), l'en-tête reste
    # impératif. Sinon le contexte n'est qu'une PISTE : on donne explicitement au
    # modèle le droit de l'ignorer plutôt que d'utiliser la lib d'une autre puce.
    #
    # Ce n'est PAS un seuil (mesure 2026-07-29 : les scores d'un composant décrit
    # que le corpus connaît — 0.41 à 0.59 — et d'un composant décrit qu'il ne
    # connaît pas — 0.26 à 0.52 — se chevauchent, et l'écart top1-top2 aussi :
    # 0.015-0.068 contre 0.003-0.029. Aucun seuil ne les sépare ; c'est ce qui a
    # fait désactiver le filet auto en 2026-06-27). C'est une distinction
    # CATÉGORIELLE, sans calibrage : l'utilisateur a nommé une puce, ou pas.
    authoritative = forced_libs is not None or prompt_names_a_chip(prompt)
    if authoritative:
        header = (
            "Relevant Arduino libraries — reference these exact APIs and "
            "patterns when applicable. Do not invent function names that "
            "are not shown here."
        )
    else:
        header = _HEDGED_HEADER
    # Quand l'utilisateur NOMME un module (HW-612, GY-91...), les libs injectees
    # sont ses PUCES mais rien ne le dit. Sans cette note, un SLM voit deux libs
    # sans lien avec « HW612 », les juge hors-sujet et les abandonne (fallback
    # analogRead). On rend le lien module -> puces EXPLICITE.
    module_note = ""
    if forced_libs is not None:
        from .hardware_modules import detect_module
        mod = detect_module(prompt)
        if mod is not None:
            module_note = (
                f"The request names the \"{mod.label}\" module: a SINGLE breakout "
                f"board that integrates the chips listed below (it is NOT a separate, "
                f"unknown part). To fulfil the request you MUST program these chips "
                f"using the libraries and APIs shown here. Do not treat the module as "
                f"unknown and do not substitute an analog read.\n\n"
            )
    result = module_note + header + "\n\n" + "\n\n".join(blocks)
    # ── Supplement (TODO #40, part 1): declared-component trigger ONLY ─────
    # See the docstring above for the full rationale. `forced_libs is not
    # None` is checked again (belt-and-braces: `declared_component_forced`
    # is meaningless without it, and the caller contract requires both) —
    # this branch never touches the i2c-scan / basic-component / plain-
    # retrieval paths above, which are untouched by this parameter.
    if declared_component_forced and forced_libs is not None:
        try:
            candidates = retrieve_libs(ranked_on, k=k, threshold=threshold)
        except Exception as e:
            _log(f"[RAG] retrieve_libs (declared-component supplement) failed: {e}")
            candidates = []
        forced_keys = {_lib_key(lib) for lib in libs}
        extra_libs = [lib for lib in candidates
                     if _lib_key(lib) not in forced_keys]
        if extra_libs:
            extra_lines = ["[RAG] declared component forced + also retrieved:"]
            for lib in extra_libs:
                score = lib.get("_score")
                score_str = f"{score:.3f}" if isinstance(score, (int, float)) else "forcé"
                extra_lines.append(f"  {score_str}  {lib.get('name')}")
            _log("\n".join(extra_lines))
            extra_blocks = [_render_lib_block(lib) for lib in extra_libs]
            result += ("\n\n" + _HEDGED_HEADER + "\n\n"
                      + "\n\n".join(extra_blocks))
    return result, plain_retrieval and not authoritative


# ⛔ LES PLAFONDS ONT ÉTÉ SUPPRIMÉS le 2026-08-26 (TODO #66, décision
# utilisateur). Ils valaient `_MAX_SIGS_PER_CLASS = 10`, `_MAX_SIGS_TOTAL = 25`
# et `_MAX_CLASSES = 2`, et sont retirés plutôt que laissés à 999 : une
# constante qui ne borne plus rien ferait croire à un plafond qui n'existe pas.
#
# Ce qui reste comme filtres, et ce n'est PAS un plafond : le dédoublonnage des
# surcharges par nom (six écritures de `readline` n'apprennent rien de plus que
# la première) et `_is_internal_name` pour les aides internes que l'exemple
# n'appelle pas. Mesuré : ces deux-là seuls ramènent le plus gros bloc de
# 2 145 à 1 405 tokens estimés.
#
# Pourquoi les supprimer : banc `scripts/bench_api_ceiling_scope.py`, 72
# générations, 2 modèles. Tout injecter ne dégrade RIEN (18/18 des deux côtés
# sur les tâches dans le périmètre de l'exemple, zéro fonction inventée), et
# le plafond faisait perdre la cible sur les tâches HORS de ce périmètre
# (2/18 contre 18/18). Il ne provoquait aucune hallucination — il provoquait
# du repli maladroit, et parfois la perte pure et simple de la tâche : sur
# RTClib, le modèle écrivait la bonne fonction EN COMMENTAIRE en expliquant
# que « the provided API does not include » de quoi lire la température.
# Mesure : docs/superpowers/measures/2026-08-26-66-plafond-tout-injecter.md


def _function_name(sig: str) -> str:
    """Extract the function name from a signature string for dedup keying.

    `void drawCircle(int16_t x0, ...)` → `drawCircle`. Constructors return
    `ClassName`. Falls back to the whole sig if the heuristic misses."""
    paren = sig.find("(")
    if paren <= 0:
        return sig
    head = sig[:paren].strip()
    # Last whitespace-separated token before `(` is the function name.
    parts = head.split()
    if not parts:
        return sig
    name = parts[-1].lstrip("*&")
    return name or sig


def _is_internal_name(name: str) -> bool:
    """Filter out batch-drawing internals + helpers that aren't part of
    the typical user-facing API. ``write*`` (camelCase) are GFX's pixel-
    batch primitives; ``startWrite``/``endWrite`` bracket them; ``*Helper``
    are circle/triangle math helpers. Keeping them crowds out the actually
    useful methods (``drawCircle``, ``setCursor``…) under per-class caps.

    The bare ``write`` (Print's char primitive) is preserved.
    """
    if name in {"startWrite", "endWrite"}:
        return True
    if name.endswith("Helper"):
        return True
    if (
        len(name) > 5
        and name.startswith("write")
        and name[5].isupper()
    ):
        return True
    return False


_CALL_RE = re.compile(r"\b\w+\s*\.\s*(\w+)\s*\(")


def _example_calls(example: str) -> set[str]:
    """Method names the official example actually calls (``obj.method(``).

    The example ships in the SAME injected block as the API list, so it is the
    best available ground truth for which methods matter — and it costs
    nothing, being already there."""
    return set(_CALL_RE.findall(example or ""))


def _format_api_signatures(api: dict, example: str = "") -> str:
    """Render the api_signatures dict as a markdown-ish API block.

    Trimmed to keep the LLM focused: dedupes overloads by function name
    (first variant wins), caps each class at ``_MAX_SIGS_PER_CLASS`` and
    the whole block at ``_MAX_SIGS_TOTAL``.

    ⚠️ WHY THE CAPS EXIST, stated honestly (TODO #66, 2026-08-26). This
    docstring used to say that sending all 122 sigs of an Adafruit_SSD1306 +
    Adafruit_GFX combo "derailed Gemma 3 4B", which lost the task and
    hallucinated `SSD1306_SWITCHCAPITAL_WRAM`. Two problems with that
    sentence, both established rather than suspected:

      - **the model named never existed here.** `git log -S "gemma3" --all`
        returns nothing; at the commit that introduced the caps (`aa02017`,
        2026-04-28) the default was `gemma4:e2b`.
      - **the failure could not be reproduced.** Bench, replayable:
        `scripts/bench_api_ceiling.py`. Same task, capped block vs. all 122
        signatures, on both installed models, 3 generations each: 0/12
        invented functions, 0/12 invented constants, 0/12 lost tasks. Fed the
        whole 122, the small model writes `SSD1306_SWITCHCAPVCC` — the REAL
        constant.

    That does NOT establish the failure never happened; it may well have been
    real in April, on another build or another `num_ctx`. It establishes that
    the justification can no longer be checked, so it cannot carry the weight
    of an argument from authority. The caps are kept because a shorter block
    is cheaper and stays focused — not because of a measurement nobody can
    reproduce.

    ``example`` decides WHICH signatures fill those slots (TODO #40 (c),
    2026-08-10). It used to be declaration order, which has nothing to do with
    usage: measured on the corpus, **19 of the 77 entries with both an API and
    an example emitted a block that contradicted itself** — the header says
    "use only these" while the example printed just below calls methods the cap
    had removed. And not marginal ones: `readTemperature` for the BME280,
    `requestTemperatures` for the DS18B20, `init`/`backlight`/`setCursor` for
    the LCD, `Color` for the NeoPixel. The reason each library exists.

    Ordering applies at BOTH levels, because both were wrong. Adafruit_BME280's
    real class is the 4th of 4: with ``_MAX_CLASSES`` at 2, declaration order
    never reached it and the block advertised two unified-sensor wrappers
    nobody calls. Constructors rank with the called methods — an example writes
    `LiquidCrystal_I2C lcd(0x27, 16, 2);`, which is not a `.` call, yet the
    model cannot instantiate anything without it.

    THE CAPS YIELD TO THE EXAMPLE — and to it alone (TODO #66, 2026-08-26).
    Ranking first was not enough: when an example calls more methods than a
    cap allows, the surplus was still cut, and the block ended up saying "use
    only these" above an example calling others. Five entries were in that
    state (`tmp102`, `ina228`, `si4713`, `bluefruit_le`, `nau7802`). All three
    caps now give way, in decreasing order of latitude:

      - per class, a signature the example calls is never dropped;
      - the total does the same, otherwise it would re-cut exactly what the
        per-class cap just let through;
      - ``_MAX_CLASSES`` gives way too, but NARROWLY: an extra class is
        admitted only for the calls no already-emitted class provides, and it
        contributes only those. Measured on the 137 entries, exactly ONE needs
        it — `bluefruit_le`, whose `readline` lives in the 3rd class of 8.

    Everything the example does NOT justify stays capped as before. Measured
    2026-08-26: worst-case filler 16 (under the cap of 20), largest block 27
    signatures / 344 estimated tokens on an 8192 window, and +212 tokens over
    the WHOLE corpus. An SSD1306 still exposes 122 signatures for 6 calls, so
    the 116 others stay cut."""
    if not api:
        return ""
    called = _example_calls(example)

    def _class_key(indexed: tuple) -> tuple:
        """Evidence is GRADED, not yes/no — a binary rank was measurably too
        coarse. Adafruit_MPU6050 ships three unified-sensor wrappers that each
        expose `getEvent`, which the example calls, so all of them tied with
        the real class and declaration order handed them the two slots. Naming
        the class in the example is the strongest signal (that is where it gets
        instantiated); the count of called methods breaks the remaining ties."""
        idx, (class_name, sigs) = indexed
        named = 0 if (example and class_name in example) else 1
        hits = sum(1 for s in sigs if _function_name(s) in called)
        return (named, -hits, idx)

    def _sig_rank(class_name: str, sig: str) -> int:
        fname = _function_name(sig)
        return 0 if (fname in called or fname == class_name) else 1

    lines = ["API (use only these — do NOT invent others):"]
    # `sorted` is stable and the key ends with the declaration index, so the
    # emission order is unchanged; only the (now absent) caps have moved.
    for _idx, (class_name, sigs) in sorted(enumerate(api.items()),
                                           key=_class_key):
        if not sigs:
            continue
        seen: set[str] = set()
        kept: list[str] = []
        for sig in sorted(sigs, key=lambda s: _sig_rank(class_name, s)):
            fname = _function_name(sig)
            # Deduplicate OVERLOADS by name, first variant wins. Kept although
            # the caps are gone: six spellings of `readline` teach the model
            # nothing the first one did not, and the block is read, not
            # compiled.
            if fname in seen:
                continue
            # A filter written for one library must not amputate another:
            # `writeDisplay` (HT16K33) fell under GFX's anti-`write*` rule even
            # though the HT16K33 example calls it.
            if _is_internal_name(fname) and fname not in called:
                continue
            seen.add(fname)
            kept.append(sig)
        if not kept:
            continue
        lines.append(f"- {class_name}:")
        for sig in kept:
            lines.append(f"  - {sig}")
    if len(lines) == 1:
        return ""
    return "\n".join(lines)


def augment_user_prompt(
    prompt: str,
    k: int = 3,
    threshold: float | None = None,
    retrieval_prompt: str | None = None,
    forced_libs: list[dict] | None = None,
    retrieval_context: str = "",
    declared_component_forced: bool = False,
    on_resemblance: Callable[[bool], None] | None = None,
    ranking_hint: str = "",
) -> str:
    """Prepend retrieved-lib context to ``prompt``. Returns ``prompt``
    unchanged if RAG returns nothing.

    ``declared_component_forced``: forwarded as-is to ``build_lib_context``
    (see its docstring) — set by the caller only when ``forced_libs`` comes
    exclusively from the user-declared-component trigger, so the retrieval
    still runs as a separate hedged supplement instead of being fully
    suppressed. Defaults to ``False``: every existing caller is unaffected.

    ``on_resemblance`` : transmis tel quel à ``build_lib_context`` (voir sa
    docstring). ``None`` par défaut.

    ``ranking_hint`` : transmis tel quel à ``build_lib_context`` (voir sa
    docstring) — les puces que le projet utilise déjà. Contrairement à
    ``retrieval_context`` ci-dessous, il ne rejoint PAS le signal de recherche
    ici : il descend séparément, parce qu'il ne doit peser que sur le
    classement. Vide par défaut, donc aucun appelant existant ne change.

    ``retrieval_prompt`` (defaults to ``prompt``) is the text used for the
    embedding similarity AND for the sandwich's top "Task:" line. Pass the
    bare user prompt here when ``prompt`` is a wrapped/instrumented version
    with boilerplate (Serial directives, metadata-marker instructions,
    EXAMPLE blocks, existing-code dumps). Without this split, the
    boilerplate dominates the embedding and skews retrieval — e.g. an
    "OLED smiley" prompt wrapped with Serial directives matches
    SoftwareSerial instead of Adafruit_SSD1306.

    ``retrieval_context`` (e.g. the attached context file) is appended to the
    SEARCH signal ONLY — never to the "Task:" line — so hardware the user
    documented there (e.g. a "L298 I2C seeed" driver) surfaces the right lib
    even when the bare prompt is task-only ("fais suivre la ligne"). It is NOT
    fed to the clarification modal (that stays on the bare prompt) so a
    documented sensor doesn't pop a spurious "which chip?" question. The lexical
    boost scans the whole signal; the encoder truncates the embedding (~128
    tokens), so the most useful files lead with their components.

    Lightweight sandwich: only the bare task (~one line) is repeated at
    the top to prime the goal before reference material — a small LLM
    otherwise latched onto example_code's "Hello, world!" instead of the user
    task. The full enriched prompt sits at the bottom for final-position
    weight without doubling the directive boilerplate (Serial /
    PROMPTUINO_NAME / EXAMPLE / EXISTING CODE).

    ⚠️ This observation used to name "Gemma 3 4B". That model has never
    existed in this repo (`git log -S "gemma3" --all` is empty; the default at
    the time was `gemma4:e2b`), so the NAME is dropped rather than swapped for
    another guess — the effect was real enough to shape the layout, the model
    it was seen on is no longer knowable. Same correction as TODO #66, which
    covers the sibling claim on `_format_api_signatures`; unlike that one, this
    one has NOT been re-measured, so it is left standing and merely stripped of
    a false attribution.
    """
    bare_task = retrieval_prompt if retrieval_prompt is not None else prompt
    search_text = (f"{bare_task}\n{retrieval_context}"
                   if retrieval_context and retrieval_context.strip()
                   else bare_task)
    ctx = build_lib_context(search_text, k=k, threshold=threshold,
                            forced_libs=forced_libs,
                            declared_component_forced=declared_component_forced,
                            on_resemblance=on_resemblance,
                            ranking_hint=ranking_hint)
    if not ctx:
        return prompt
    return (
        f"Task: {bare_task}\n\n"
        f"{ctx}\n\n"
        f"---\n\n"
        f"{prompt}"
    )


# Lexical boost: bonus added to an entry's semantic score when one of
# its "part-number" tokens appears verbatim in the prompt. +0.30 is enough to
# lift the entry to the top while letting relative_gate flush out the noise.
_LEXICAL_BOOST = 0.30

# Code-generation injection floor (build_lib_context / augment_user_prompt).
# A library block is injected into the generation prompt ONLY if its score
# clears this floor.
#
# WHY it was raised, and it still holds: the old 0.25 threshold let the generic
# band through — "fais un scanner I2C" injected MCP9600/MQ-135/PIR (a flat noise
# cluster the relative_gate cannot drop, because nothing leads), and the SLM
# dutifully wrote a thermocouple reader.
#
# ⚠️ RE-MEASURED 2026-08-18 (TODO #54 step 4) on the 164 frozen cases of
# `scripts/bench_rag_prompts.json`, 4 languages. The bands this comment used to
# claim — named 0.69-0.97, described 0.45-0.53, generic 0.42-0.48 — were
# measured in 2026-06-27 on a hand-made battery and were WRONG, in a way that
# flattered the floor. What is actually true, boost included:
#
#   band                n     score range      clears 0.50 ?
#   named              72     0.562 – 1.136    always
#   described/specific 48     0.404 – 1.141    mostly
#   described/vague    32     0.462 – 0.984    mostly
#   generic            12     0.225 – 0.543    TWO of them do
#
# Two things the old numbers hid:
#
#  - The floor does NOT sit "in a gap". The generic ceiling (0.543) and the
#    named floor (0.562) are **0.019 apart**, and 0.50 sits INSIDE the generic
#    band, not below it. Two generic prompts clear it today (a Spanish and an
#    Italian "seconds counter on the serial monitor", both pulling a TM1637
#    7-segment driver). They are held in a characterization guard, not fixed:
#    `KNOWN_GENERIC_INJECTIONS` in scripts/test_rag_injection_invariants.py.
#  - The named band's margin is 0.062, not the ~0.19 the old range implied. The
#    "name your component and it works" contract still holds on this battery —
#    but it holds narrowly, so ANY corpus growth must be measured rather than
#    assumed. That is what `python scripts/bench_rag.py` is for.
#
# Down side, unchanged and accepted (it matches the same contract): a vaguely
# described un-named part may inject nothing → name it, or correct it
# downstream ("Corriger dans Studio"). Tune here if needed; this floor is still
# the single calibration point — and the bench is now the way to see what
# tuning it costs.
_CODEGEN_MIN_SCORE = 0.50

# Auto safety net (detect_lib_ambiguities step 2): minimum top-1 score for an
# UNCURATED retrieval to be treated as a genuine ambiguity worth a modal.
# Several weak matches clustered low (~0.30-0.40) mean the model is unsure
# about everything (tangential hits), not a real choice between strong
# candidates -> no modal, let RAG/generation proceed. Calibrated so genuine
# close ambiguities (≥0.5 top) still surface while servo/rfid/sd-style noise
# (~0.35-0.41) is dropped. Curated families (step 1) are exempt: they are
# keyword-matched, not score-gated.
_AMBIGUITY_MIN_TOP_SCORE = 0.45

# ── Auto ambiguity safety net — DISABLED (2026-06-27) ───────────────────────
# The "auto safety net" (step 2 of `detect_lib_ambiguities`) GUESSES ambiguity
# from embedding clustering: if ≥2 corpus libs score above
# `_AMBIGUITY_MIN_TOP_SCORE`, it opens a pre-generation clarification modal. It
# is FRAGILE BY CONSTRUCTION — it infers an *intent to choose* from raw semantic
# proximity, so it fires on prompts that are not ambiguous at all ("fais tourner
# le servo de 0 à 180", "fais un scanner d'adresses I2C", …). The 0.45 floor
# cannot be calibrated to be both sensitive to real ambiguity and quiet on
# noise — every threshold is wrong somewhere. This was the source of the
# recurring unwanted modals.
#
# Decision (user, 2026-06-27): keep ONLY the CURATED groups (step 1), which
# encode real, intentional "vague need → several chips" families (screen,
# temperature, distance, IMU, …) and trigger on explicit keywords. When the
# curated path misses, let RAG pick the most likely lib at generation time and
# rely on the DOWNSTREAM correction flow ("Corriger dans Studio" / chat) rather
# than a blocking pre-generation modal.
#
# The net's code is intentionally PRESERVED below (not deleted). To RE-ENABLE
# it, flip this flag to True. The basic-component (1.5) and I2C-scan (1.6)
# guards exist only to tame the net — they are its guard rails and stay with it.
_AUTO_AMBIGUITY_NET_ENABLED = False


# Jetons supplémentaires, ÉCRITS À LA MAIN (TODO #46, 2026-08-10).
#
# Le constat : `_signature_tokens` ne retient un jeton que s'il fait ≥4
# caractères ET contient un chiffre, plus l'id de l'entrée s'il tient en un
# seul mot. Pour le ruban NeoPixel, ça donne `ws2812`, `sk6812`… mais PAS
# `neopixel`, et l'id `adafruit-neopixel` est composite donc rejeté. **Le seul
# mot que l'utilisateur écrit est précisément celui qui ne déclenche rien.**
# Mesuré : « Fais défiler un arc-en-ciel sur un ruban NeoPixel » remontait
# HT16K33, MAX7219 et TM1637 ; « allume un anneau neopixel » ne remontait
# RIEN. Le contrat affiché est pourtant « nomme ton composant et ça marchera ».
#
# Pourquoi une table à la main plutôt qu'une règle. Deux généralisations ont
# été mesurées sur les 91 documents et écartées : « tous les jetons uniques du
# corpus » (+452 jetons, mais `button`, `search`, `network`, `config`…) et
# « les jetons du NOM seul » (27 entrées, mais `full`, `array`, `rate` et
# surtout `sparkfun`). Les deux se règlent sur un échantillon — exactement ce
# qui a tué le filet d'ambiguïté automatique en juin 2026. Une table explicite
# ne devine rien et se relit.
#
# ⚠️ Chaque entrée est vérifiée UNIQUE dans tout le corpus avant d'être
# ajoutée : `test_extra_tokens_are_unique_in_the_corpus`. `dallastemperature`
# a été écarté à ce titre — il vit aussi dans l'entrée `onewire`.
#
# ⚠️ LIMITE CONNUE, non corrigée ici : la tokenisation coupe sur les accents
# (`photorésistance` → `photor` + `sistance`), donc un mot français accentué
# ne peut pas servir de déclencheur. Le repliement d'accents existe ailleurs
# (`declared_components.match_prompt`) ; l'apporter ici toucherait aussi
# `prompt_names_a_chip` et le boost, et mérite sa propre mesure.
_EXTRA_SIGNATURE_TOKENS: dict[str, tuple[str, ...]] = {
    "adafruit-neopixel": ("neopixel",),
    "liquidcrystal-i2c": ("liquidcrystal",),
    "buzzer":            ("piezo",),
    "ldr":               ("photoresistor",),
    # TODO #56. `keypad` had ONE signature token, in English, so « lire un
    # clavier matriciel 4x4 » named its component in full and was still served
    # under the hedged header. This map is the only route available: the
    # regular filter keeps tokens of >= 4 chars WITH a digit, which no
    # translation can satisfy, and `prompt_names_a_chip` intersects SINGLE
    # tokens, so a multi-word expression could not match either.
    #
    # ⚠️ CES JETONS ÉTAIENT `clavier` / `teclado` / `tastiera` JUSQU'AU
    # 2026-08-26. #56 assumait un compromis — « dans un prompt Arduino le mot
    # désigne en pratique le clavier matriciel » — qui était vrai sur un corpus
    # de 91 entrées où `keypad` était le SEUL clavier. **#60 a périmé cette
    # prémisse** en ajoutant une puce de clavier tactile (`mpr121`), un clavier
    # BLE (`bluefruit_le`) et une grille de boutons (`trellis`). Mesuré : « gérer
    # un clavier tactile capacitif » servait `keypad` SEUL, sous en-tête
    # impératif, alors que la réponse est MPR121 ; « un clavier bluetooth »
    # plaçait `keypad` devant `bluefruit_le`.
    #
    # Les jetons sont donc devenus PRÉCIS plutôt qu'ambigus. `matriciel` et
    # `matricial` sont uniques à `keypad` dans le corpus, vérifié. L'italien
    # n'avait aucun mot unique — `matrice` est partagé avec `led_matrix`,
    # `ht16k33`, `amg8833` et `trellis` — d'où l'ajout du mot-clé
    # « tastierino matriciale » à l'entrée corpus : `tastierino` est le terme
    # italien du PAVÉ, distinct de `tastiera` (le clavier). Cet ajout est
    # neutre pour l'embedding (vérifié bit à bit : le texte de `keypad` fait
    # déjà 131 tokens pour un budget de 128, le mot-clé tombe au-delà de la
    # coupure), donc aucun rebuild n'est nécessaire.
    #
    # ⚠️ Limite assumée : « tastiera A MATRICE », autre tournure italienne
    # courante, ne porte aucun de ces jetons et reste servie sous en-tête
    # hedgé. `keypad` y est TOUJOURS retrouvé — c'est l'autorité de l'en-tête
    # qui se perd, pas le composant. (Les 4 prompts `keypad` du banc, eux,
    # écrivent « matriciel / matricial / matriciale / matrix keypad » : tous
    # les quatre gardent l'en-tête impératif.) Le compromis inverse — garder
    # `tastiera` — coûtait une mauvaise réponse AFFIRMÉE dans les trois autres
    # langues, ce qui est le défaut le plus cher du dépôt.
    "keypad":            ("matriciel", "matricial", "matriciale", "tastierino"),
}

# Hyphenated runs, so « MH-Z19 » also reads as `mhz19`. Same normalisation as
# `registry_lookup.detect_unknown_part_tokens` (« ZXQ-9000 » -> `zxq9000`);
# duplicated rather than imported because `registry_lookup` imports THIS module.
_HYPHENATED_RUN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)+")


def _prompt_tokens(prompt: str) -> set[str]:
    """Alphanumeric tokens of a prompt, PLUS the joined form of hyphenated runs.

    TODO #56: « MH-Z19 » split into `mh` + `z19`, and the corpus entry knows
    `mhz19`/`mhz19b`/`mhz19c`/`z19b`/`z19c` but never bare `z19` -- so a prompt
    naming its component in full was served under the hedged header. People
    write part numbers with or without their hyphen; joining only ADDS tokens,
    it never removes one.

    Used by EVERY prompt-side lexical decision (`prompt_names_a_chip`,
    `named_corpus_libs`, the lexical boost of `retrieve_libs`, and the curated
    clarification). They must agree: a component named with a hyphen served
    authoritatively but not boosted -- or the reverse -- would be incoherent.
    """
    low = (prompt or "").lower()
    toks = set(re.findall(r"[a-z0-9]+", low))
    toks |= {m.replace("-", "") for m in _HYPHENATED_RUN_RE.findall(low)}
    return toks


def _signature_tokens(entry: dict) -> set[str]:
    """Distinctive "part-number" tokens of a corpus entry: alphanumeric
    tokens of at least 4 characters containing ≥1 digit (e.g.
    ``ina3221``, ``l298n``, ``dht11``, ``bme280``, ``0x40``), drawn from the name + the
    keywords. If they appear verbatim in the prompt, the user named
    this component explicitly → lexical boost (cf. ``retrieve_libs``).
    Generic words without a digit (``courant``) and short tokens
    (``i2c``, ``d13``) are deliberately excluded to avoid false boosts.

    Additionally, the entry's SINGLE-WORD id (``servo``, ``encoder``,
    ``keypad``, ``lora``…) counts as a distinctive name: many components are
    named by a plain word (no digit), so naming one verbatim is just as
    explicit as a part number. Restricted to single alnum-word ids ≥4 chars:
    composite ids (``dc_motor``, ``dht-sensor-library``) would tokenize into
    generic words (``sensor``/``motor``/``library``) and cause false boosts."""
    text = (entry.get("name", "") + " " + " ".join(entry.get("keywords", []))).lower()
    toks = re.findall(r"[a-z0-9]+", text)
    sig = {t for t in toks if len(t) >= 4 and any(c.isdigit() for c in t)}
    cid = (entry.get("id") or "").lower()
    if re.fullmatch(r"[a-z][a-z0-9]{3,}", cid):
        sig.add(cid)
    sig |= set(_EXTRA_SIGNATURE_TOKENS.get(cid, ()))
    return sig


_SIGNATURE_TOKEN_CACHE: frozenset[str] | None = None


def corpus_signature_tokens() -> frozenset[str]:
    """Tous les jetons « numero de piece » du corpus, en un seul ensemble.

    Meme criterion que `prompt_names_a_chip`, mais expose l'ENSEMBLE plutot
    qu'un oui/non : `project_chips` a besoin de savoir si un jeton donne fera
    reagir le boost lexical, ce qu'un booleen sur un prompt ne dit pas.

    Mis en cache : le corpus ne bouge pas en cours de session, et le calcul
    balaie ses 137 entrees.
    """
    global _SIGNATURE_TOKEN_CACHE
    if _SIGNATURE_TOKEN_CACHE is None:
        if not _load_corpus():
            return frozenset()          # non mis en cache : le corpus peut
        toks: set[str] = set()          # arriver au chargement suivant
        for entry in _corpus:
            toks |= _signature_tokens(entry)
        _SIGNATURE_TOKEN_CACHE = frozenset(toks)
    return _SIGNATURE_TOKEN_CACHE


def retrieve_libs(
    prompt: str,
    k: int = 3,
    threshold: float = 0.25,
    relative_gate: float = 0.85,
) -> list[dict]:
    """Return up to ``k`` corpus entries with score ≥ ``threshold``.

    Sorted by descending score. Each entry is the raw corpus dict augmented
    with a ``_score`` float. Empty list on any failure or if nothing clears the
    threshold.

    Score = cosine similarity + a LEXICAL BOOST (``_LEXICAL_BOOST``) when a
    "part-number" token of the entry (e.g. ``INA3221``) appears verbatim in the
    prompt. The semantic model alone drowns these rare tokens under generic
    words ("mesure", "tension", "capteur"), so an explicitly-named component can
    rank below unrelated libs. The boost pulls the named component to the top.

    Beyond rank 1, an entry is only kept if its score is ≥ ``relative_gate``
    × top-1 score. This drops low-confidence "noise" libs when the top match
    is clear — and, combined with the boost, evicts off-topic libs once a named
    component dominates. Genuine ambiguity (close scores) still surfaces
    multiple candidates. Pass ``relative_gate=0`` to disable.
    """
    if not prompt or not prompt.strip():
        return []
    if not _load():
        return []

    try:
        query = encode([prompt])
    except Exception:
        return []

    sims = (_embeddings @ query[0]).astype(np.float32)
    if sims.size == 0:
        return []

    # Lexical boost: +_LEXICAL_BOOST to entries whose part-number token
    # is present in the prompt.
    prompt_tokens = _prompt_tokens(prompt)
    scores = sims.copy()
    for i in range(len(_corpus)):
        if _signature_tokens(_corpus[i]) & prompt_tokens:
            scores[i] += _LEXICAL_BOOST

    order = np.argsort(-scores)
    top_score: float | None = None
    out: list[dict] = []
    for idx in order[:k]:
        score = float(scores[idx])
        if score < threshold:
            break
        if top_score is None:
            top_score = score
        elif score < relative_gate * top_score:
            break
        entry = dict(_corpus[idx])
        entry["_score"] = score
        out.append(entry)
    return out


def _curated_entries(group) -> list[dict]:
    """Turn the curated candidates of a `ClarifyGroup` into real corpus
    entries (forceable via `forced_libs`), enriched with `_display_label` +
    `_svg_type`, in the declared order. Ids absent from the corpus are ignored
    (not forceable) — hence the value of the `test_clarification_groups` test guard."""
    out: list[dict] = []
    for cand in group.candidates:
        entry = corpus_entry(cand.corpus_id)
        if entry is None:
            continue
        entry["_display_label"] = cand.label
        entry["_svg_type"] = cand.svg_type
        entry["_score"] = 1.0  # forced choice (not a similarity score)
        out.append(entry)
    return out


# Components without a library: keyword → overrides signalling a complex variant.
# If a keyword matches AND no override is present → basic component
# → the auto safety net (step 2) is shut down (too noisy for these elementary cases).
_BASIC_NO_LIB_KEYWORDS: dict[str, frozenset[str]] = {
    # Plain LED — overridden by strip/ring/matrix (justified complex variant)
    "led":  frozenset({"bande", "ruban", "anneau", "ring", "strip",
                       "matrice", "matrix", "8x8", "neopixel", "ws2812",
                       "apa102", "adressable", "addressable"}),
    "leds": frozenset({"bande", "ruban", "anneau", "ring", "strip",
                       "matrice", "matrix", "8x8", "neopixel", "ws2812",
                       "apa102", "adressable", "addressable"}),
    # Button (FR/EN/ES)
    "bouton":   frozenset(),
    "button":   frozenset(),
    "pulsador": frozenset(),
    # Buzzer (FR/EN/ES/IT)
    "buzzer":   frozenset(),
    "zumbador": frozenset(),
    # Potentiometer (FR/EN/ES/IT)
    "potentiometre":  frozenset(),
    "potentiomètre":  frozenset(),
    "potentiometer":  frozenset(),
    "potenciómetro":  frozenset(),
    "potenziometro":  frozenset(),
    # Resistor (FR/EN/ES/IT)
    "résistance":  frozenset(),
    "resistance":  frozenset(),
    "resistor":    frozenset(),
    "resistencia": frozenset(),
    "resistenza":  frozenset(),
}


def _prompt_is_basic_component(prompt: str) -> bool:
    """True if the prompt designates a component without a lib (plain LED, button…).

    A component is considered "basic" if a keyword from
    `_BASIC_NO_LIB_KEYWORDS` is present AND no override specific to that
    keyword (complex variant) is detected in the same prompt."""
    for kw, overrides in _BASIC_NO_LIB_KEYWORDS.items():
        if not re.search(rf"\b{re.escape(kw)}\b", prompt, re.IGNORECASE):
            continue
        if overrides and any(
            re.search(rf"\b{re.escape(ov)}\b", prompt, re.IGNORECASE)
            for ov in overrides
        ):
            continue
        return True
    return False


# I2C bus/address scanner: a DIAGNOSTIC sketch that needs NO third-party
# library — only the core `Wire`. The word "scanner" otherwise drags tangential
# matches into the auto safety net (pn532 NFC 0.482, fingerprint 0.436). This
# guard serves TWO purposes: (1) shut the (disabled) net up on these prompts,
# and (2) drive the deterministic Wire injection below — without context a weak
# SLM hallucinates `#include <TwoWire.h>` (TwoWire is a CLASS in Wire.h, not a
# header). Detected language-light, like `_is_i2c_motor`: I2C cue + scan cue.
_I2C_SCAN_I2C_CUES = ("i2c", "i²c")
# "scan" substring covers scanner/scan/scanne (FR), scan/scanning (EN),
# scansione/scansiona (IT), escanear/escaner (ES); "escáner" for accented ES.
_I2C_SCAN_VERB_CUES = ("scan", "escáner")


def _prompt_is_i2c_scan(prompt: str) -> bool:
    """True if the prompt asks for an I2C bus/address scan (a no-lib diagnostic
    sketch). Requires BOTH an I2C cue and a scan cue so a plain "capteur i2c"
    or an unrelated "scanner de codes-barres" does not match."""
    t = prompt.lower()
    return (any(c in t for c in _I2C_SCAN_I2C_CUES)
            and any(s in t for s in _I2C_SCAN_VERB_CUES))


# Canonical `Wire` (core I2C library) reference, injected DETERMINISTICALLY for
# an I2C-scanner prompt (see `_prompt_is_i2c_scan`) — NOT via embeddings: Wire is
# a core lib absent from the corpus, and a scanner prompt scores as flat noise
# (~0.42) so it would never clear the injection floor. Formatted by
# `build_lib_context` like any retrieved lib (headers + example), so the SLM gets
# the exact `#include <Wire.h>` sketch instead of inventing `TwoWire.h`.
_WIRE_I2C_SCANNER_REF = {
    "name": "Wire (I2C core library)",
    "headers": ["Wire.h"],
    "example_code": (
        "#include <Wire.h>\n"
        "\n"
        "void setup() {\n"
        "  Wire.begin();\n"
        "  Serial.begin(9600);\n"
        "  while (!Serial) {}\n"
        "  Serial.println(\"Scan I2C...\");\n"
        "}\n"
        "\n"
        "void loop() {\n"
        "  byte count = 0;\n"
        "  for (byte address = 1; address < 127; address++) {\n"
        "    Wire.beginTransmission(address);\n"
        "    if (Wire.endTransmission() == 0) {\n"
        "      Serial.print(\"Peripherique trouve a 0x\");\n"
        "      if (address < 16) Serial.print(\"0\");\n"
        "      Serial.println(address, HEX);\n"
        "      count++;\n"
        "    }\n"
        "  }\n"
        "  if (count == 0) Serial.println(\"Aucun peripherique I2C\");\n"
        "  delay(5000);\n"
        "}"
    ),
}


def _named_candidate(prompt_tokens: set[str], candidates: list[dict]) -> dict | None:
    """If the prompt explicitly names one of a family's candidates (one of
    its "part-number" tokens — BME280, VMA335, SSD1306… — appears verbatim
    in the prompt), return THAT candidate; otherwise None.

    Serves the PER-FAMILY resolution: naming a family's chip resolves it (we
    force it, no modal) without preventing clarification of the OTHER families in
    the same prompt (e.g. "temperature with a vma335 and an oled" → BME280 forced +
    screen modal)."""
    for c in candidates:
        if _signature_tokens(c) & prompt_tokens:
            return c
    return None


def detect_lib_ambiguities(
    prompt: str, k: int = 3, threshold: float = 0.25
) -> tuple[list[list[dict]], list[dict]]:
    """Analyze the lib families of a prompt (MULTI-FAMILY clarification).

    Returns ``(to_clarify, auto_forced)``:
      - ``to_clarify``: AMBIGUOUS families (≥2 candidates, no named chip) →
        a modal each.
      - ``auto_forced``: libs of families RESOLVED by an explicit chip name
        ("vma335" → BME280) → forced directly, WITHOUT a modal, but injected
        into the context just like the choices (otherwise, as soon as another
        family is clarified, `build_lib_context` skips the retrieval and would lose
        that context).

    Pipeline (cf. multi-family clarification spec, curated-first PIVOT):
      1. **CURATED first**: each matching group (`match_all_groups`), kept
         if ≥2 real candidates AND candidates DISJOINT from the families already retained.
         The disjunction avoids re-clarifying one and the same need with
         overlapping keywords ("co2" also matches `air_quality`, which shares
         SCD30/MH-Z19… → only one) while keeping the distinct families
         (temperature vs screen → two). If a family's chip is NAMED
         (`_named_candidate`) → family auto-forced (no modal).
      2. **Auto SAFETY NET** (DISABLED, see `_AUTO_AMBIGUITY_NET_ENABLED`): if NO
         curated group. A named chip outside any family → [] (RAG lifts it via
         the lexical boost). Otherwise retrieve_libs ≥2 candidates with distinct
         ids → a single family to clarify. Currently dormant: when no curated
         group matches, the function returns ([], []) and RAG picks the lib."""
    if not prompt or not prompt.strip():
        return [], []

    prompt_tokens = _prompt_tokens(prompt)

    # 1. DISTINCT curated families (keywords). Robust to an encoder failure.
    try:
        from .clarification_groups import match_all_groups
        groups = match_all_groups(prompt)
    except Exception:
        groups = []
    to_clarify: list[list[dict]] = []
    auto_forced: list[dict] = []
    seen_ids: set[str] = set()
    for g in groups:
        cands = _curated_entries(g)
        if len(cands) < 2:
            continue
        ids = {c.get("id") for c in cands}
        if ids & seen_ids:
            continue   # concept already covered (overlap) → no re-clarif.
        seen_ids |= ids
        named = _named_candidate(prompt_tokens, cands)
        if named is not None:
            auto_forced.append(named)   # named chip → resolved, no modal
        else:
            to_clarify.append(cands)
    if to_clarify or auto_forced:
        return to_clarify, auto_forced

    # Auto safety net DISABLED (see `_AUTO_AMBIGUITY_NET_ENABLED`): past the
    # curated step, nothing else opens a pre-generation modal. Everything below
    # (guards 1.5/1.6 + the embedding net at step 2) is dormant until re-enabled.
    if not _AUTO_AMBIGUITY_NET_ENABLED:
        return [], []

    # 1.5. "Basic component" guard — plain LED, button, buzzer, etc.
    # The auto safety net (step 2) produces false positives on these
    # elementary prompts (e.g. "blink a LED" → [ht16k33, neopixel, ...]).
    # The complex variants (strip/ring/matrix) are handled by the curated
    # groups (step 1) — what remains here is unambiguous → nothing.
    if _prompt_is_basic_component(prompt):
        return [], []

    # 1.6. "I2C scanner" guard — a bus/address scan is a no-lib diagnostic
    # sketch; "scanner" otherwise lifts tangential candidates (NFC reader,
    # fingerprint scanner) past the confidence floor → spurious modal. Placed
    # AFTER the curated step so "scanne le bus i2c pour mon BME280" still forces
    # the named family.
    if _prompt_is_i2c_scan(prompt):
        return [], []

    # 2. Auto safety net: named chip outside any family → no ambiguity (RAG
    # lifts it via the boost). Otherwise ≥2 candidates with distinct ids.
    try:
        if prompt_names_a_chip(prompt):
            return [], []
    except Exception:
        pass
    try:
        libs = retrieve_libs(prompt, k=k, threshold=threshold)
    except Exception:
        return [], []
    if len(libs) < 2 or len({lib.get("id") for lib in libs}) < 2:
        return [], []
    # Absolute-confidence floor: only a CONFIDENT lead is a real ambiguity.
    # Weak clustered matches (~0.30-0.40) = tangential noise -> no modal.
    top_score = libs[0].get("_score")
    if not isinstance(top_score, (int, float)) or top_score < _AMBIGUITY_MIN_TOP_SCORE:
        return [], []
    return [libs], []


def detect_lib_ambiguity(prompt: str, k: int = 3,
                         threshold: float = 0.25) -> list[dict] | None:
    """Compat: FIRST family TO CLARIFY in the prompt (or None). Preserves
    the old single-family contract for callers that handle only one choice
    (tests). See `detect_lib_ambiguities` for the multi-family +
    auto-forcing version used by generation."""
    to_clarify, _ = detect_lib_ambiguities(prompt, k=k, threshold=threshold)
    return to_clarify[0] if to_clarify else None
