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
# ⚠️ Le tokenizer est versionne et embarque, donc toujours a cote du code.
# Le MODELE, lui, peut avoir ete telecharge dans le dossier de
# l'utilisateur : `Program Files` n'est pas inscriptible. Resolu a
# l'appel, pas a l'import -- il peut apparaitre pendant la session.
from .model_path import model_path as _model_path
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
            _mp = _model_path()
            if not _mp.exists() or not _TOKENIZER_PATH.exists():
                return False
            import onnxruntime as ort
            from tokenizers import Tokenizer

            tokenizer = Tokenizer.from_file(str(_TOKENIZER_PATH))
            tokenizer.enable_padding()
            tokenizer.enable_truncation(max_length=_MAX_SEQ_LEN)
            session = ort.InferenceSession(
                str(_mp), providers=["CPUExecutionProvider"]
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


_INCLUDE_HEADER_RE = re.compile(
    r"#\s*include\s*[<\"]\s*([^>\"\s]+)\s*[>\"]")


def api_context_for_code(code: str, max_libs: int = 3) -> str:
    """Les blocs d'API des bibliotheques du CORPUS que `code` inclut.

    Ecrit pour le prompt de REPARATION (QA AB2 bis du #82, 2026-08-31) : le
    reparateur recevait l'erreur et le code, mais AUCUNE connaissance de
    l'API de la lib. Sur `motor2.forward(2000)` -- une methode reelle,
    appelee avec un argument qu'elle ne prend pas -- il devait DEVINER la
    signature, et un modele 2B devine mal : la reparation echouait sur un
    correctif d'une ligne (`forward()` est sans argument, la variante
    temporisee s'appelle `forwardFor`). Ce bloc lui donne la meme verite que
    la generation a recue.

    ⚠️ **Seul le PREMIER en-tete d'une entree lui appartient** -- meme regle,
    et pour la meme raison, que `lib_by_header._from_corpus` : les en-tetes
    suivants sont des COMPAGNONS (`Adafruit_GFX.h` sous `adafruit-ssd1306`),
    et associer un compagnon a l'entree affirmerait une correspondance
    fausse.

    Rend "" si aucun include ne correspond au corpus -- l'appelant n'ajoute
    alors rien au prompt. Borne a `max_libs` blocs (l'ordre des includes du
    code fait foi), le bloc median pesant ~95 tokens (#66).
    """
    if not code or not code.strip():
        return ""
    if not _load_corpus():
        return ""
    vus: list[str] = []
    blocs: list[str] = []
    for header in _INCLUDE_HEADER_RE.findall(code):
        if len(blocs) >= max_libs:
            break
        cle = header.strip().lower()
        for entry in _corpus:
            headers = entry.get("headers") or []
            if not headers or headers[0].strip().lower() != cle:
                continue
            eid = str(entry.get("id") or "")
            if eid in vus:
                break
            vus.append(eid)
            blocs.append(_render_lib_block(dict(entry)))
            break
    if not blocs:
        return ""
    return (
        "Authoritative API for the included libraries — any fix MUST match "
        "these exact signatures (do not invent methods or arguments):\n\n"
        + "\n\n".join(blocs)
    )


def build_lib_context(prompt: str, k: int = 3, threshold: float | None = None,
                      forced_libs: list[dict] | None = None,
                      declared_component_forced: bool = False,
                      on_resemblance: Callable[[bool], None] | None = None,
                      ranking_hint: str = "",
                      banned_libs: frozenset[str] = frozenset()
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
        ranking_hint=ranking_hint, banned_libs=banned_libs)
    if on_resemblance is not None:
        on_resemblance(by_resemblance)
    return ctx


def _build_lib_context(prompt: str, k: int = 3, threshold: float | None = None,
                       forced_libs: list[dict] | None = None,
                       declared_component_forced: bool = False,
                       ranking_hint: str = "",
                       banned_libs: frozenset[str] = frozenset()
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

    ``banned_libs`` (TODO #85) : ids corpus bannis par un swap de puce persist
    sur les features ciblées (``feat.banned_lib_ids``, cible NUE — servo →
    relais). C'est la porte UNIQUE du ban : elle filtre le retrieval
    (``retrieve_libs``), le sauvetage des puces nommées ET les ``forced_libs``
    résiduels. Mesuré le 2026-08-31 avant le correctif : ban « servo » + prompt
    qui écrit « servo » → le sauvetage ``named_corpus_libs`` réinjectait la lib
    bannie en bloc IMPÉRATIF (le swap était annulé), et le cas liste-vide
    coupait tout le retrieval (une feature servo+capteur perdait aussi le
    contexte du capteur). Un ban est inconditionnel — nommer la puce ne la
    ramène pas : le swap est postérieur au prompt, c'est lui la décision.
    Vide par défaut : aucun appelant existant ne change.

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
        # #85 : le ban gagne sur TOUT, y compris le sauvetage ci-dessus (la
        # fuite mesurée) et un forced résiduel — une lib bannie ne s'injecte
        # par aucune porte.
        if banned_libs:
            libs = [lib for lib in libs
                    if (lib.get("id") or "") not in banned_libs]
    elif _prompt_is_i2c_scan(prompt):
        # I2C scanner: inject the canonical `Wire` (core lib) sketch
        # deterministically. No third-party lib is needed, but without context a
        # weak SLM hallucinates `#include <TwoWire.h>`. The example hands it the
        # correct `#include <Wire.h>` pattern. (Not retrievable: Wire is a core
        # lib outside the corpus, and the prompt scores as noise.)
        _log("[RAG] scanner I2C -> exemple Wire (core) injecte")
        libs = [dict(_WIRE_I2C_SCANNER_REF)]
    elif _prompt_needs_debounce(prompt):
        # Anti-rebond (TODO #90) : même forme que le scanner I2C ci-dessus —
        # aucune bibliothèque n'est en jeu, mais sans le motif le modèle
        # écrit un compteur qui ne compte JAMAIS (mesuré 0/4 même sans
        # composition). Placé AVANT la garde « composant de base », qu'il
        # contourne donc par construction sans la modifier.
        _log("[RAG] anti-rebond -> motif Debounce.ino injecte")
        libs = [dict(_DEBOUNCE_PATTERN_REF)]
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
            libs = retrieve_libs(ranked_on, k=k, threshold=threshold,
                                 banned_ids=banned_libs)
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
            candidates = retrieve_libs(ranked_on, k=k, threshold=threshold,
                                       banned_ids=banned_libs)
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


# Deux formes, dans cet ordre : la DECLARATION (`L298N motor(EN, IN1, IN2)`,
# ou le nom qui compte est la CLASSE, pas la variable) puis l'appel
# (`motor.setSpeed(150)`). Une seule regex capturait `motor` au lieu de
# `L298N` et l'arite du constructeur n'etait jamais associee a la classe --
# mesure avant livraison : le bloc L298N passait au constructeur 2 broches
# que le cablage ignore deliberement (#83).
_DECL_ARITY_RE = re.compile(r"\b([A-Za-z_]\w*)\s+\w+\s*\(([^()]*)\)")
_ANY_CALL_ARITY_RE = re.compile(r"\b(\w+)\s*\(([^()]*)\)")


def _example_call_arities(example: str) -> dict[str, int]:
    """{nom -> arite} des appels de l'exemple, constructeurs compris.

    Sert au choix de la SURCHARGE emise (cf. `_format_api_signatures`) : la
    variante dont l'arite colle a l'appel de l'exemple gagne. Approximation
    assumee : les appels dont les arguments portent des parentheses
    imbriquees ne matchent pas la regex et ne se prononcent pas -- on retombe
    alors sur « la plus simple », jamais sur une erreur. Premiere occurrence
    vue = celle qui compte, et les declarations passent AVANT les appels
    (le nom de la variable peut collisionner avec une methode, jamais
    l'inverse).
    """
    arities: dict[str, int] = {}

    def _compter(args: str) -> int:
        corps = args.strip()
        return 0 if not corps else corps.count(",") + 1

    for regex in (_DECL_ARITY_RE, _ANY_CALL_ARITY_RE):
        for nom, args in regex.findall(example or ""):
            if nom in arities:
                continue
            arities[nom] = _compter(args)
    return arities


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
        # ⚠️ **Parmi les surcharges d'un meme nom : l'EXEMPLE d'abord, la
        # simplicite ensuite.** C'etait « premiere declaree gagne », et la QA
        # AB2 ter du #82 (2026-08-31) a montre le bloc TRAHIR un modele
        # obeissant : la lib L298N declare `forwardFor(delay, callback)` AVANT
        # `forwardFor(delay)`, donc le bloc n'annoncait que la variante a
        # callback — et le reparateur, somme de suivre « ces signatures
        # exactes », ecrivait un callback invente au lieu du correctif d'une
        # ligne.
        #
        # ⚠️ Et « la plus simple gagne » TOUT COURT etait trop general —
        # mesure sur les 125 entrees a API avant de livrer : 16 blocs
        # changeaient, plusieurs vers du PIRE, parce que pour un CONSTRUCTEUR
        # la variante la plus simple est souvent la degeneree
        # (`Adafruit_NeoPixel(void)`, `Encoder()`, `File(void)`) — et le
        # L298N passait au constructeur 2 broches que le cablage ignore
        # deliberement (#83). La regle juste est celle que ce formateur
        # applique deja partout : l'exemple est la verite terrain. La
        # surcharge dont l'arite colle a l'appel de l'exemple gagne
        # (bornes : parametres obligatoires ≤ arite ≤ parametres declares,
        # pour respecter les valeurs par defaut) ; la plus simple seulement
        # quand l'exemple ne se prononce pas. L'EMPLACEMENT de chaque nom
        # dans le bloc ne bouge pas — seul le texte de la variante retenue
        # change.
        arities = _example_call_arities(example)

        def _param_bounds(sig: str) -> tuple[int, int]:
            i, j = sig.find("("), sig.rfind(")")
            if i < 0 or j <= i:
                return (0, 0)
            corps = sig[i + 1:j].strip()
            if not corps:
                return (0, 0)
            parts = corps.split(",")
            requis = sum(1 for p in parts if "=" not in p)
            return (requis, len(parts))

        def _overload_key(sig: str, fname: str, decl_idx: int) -> tuple:
            requis, total = _param_bounds(sig)
            arite = arities.get(fname)
            colle = 0 if (arite is not None
                          and requis <= arite <= total) else 1
            return (_sig_rank(class_name, sig), colle, total, decl_idx)

        best_by_name: dict[str, tuple] = {}
        for k_idx, sig in enumerate(sigs):
            fname = _function_name(sig)
            cle = _overload_key(sig, fname, k_idx)
            if (fname not in best_by_name
                    or cle < best_by_name[fname][0]):
                best_by_name[fname] = (cle, sig)
        seen: set[str] = set()
        kept: list[str] = []
        for sig in sorted(sigs, key=lambda s: _sig_rank(class_name, s)):
            fname = _function_name(sig)
            if fname in seen:
                continue
            # A filter written for one library must not amputate another:
            # `writeDisplay` (HT16K33) fell under GFX's anti-`write*` rule even
            # though the HT16K33 example calls it.
            if _is_internal_name(fname) and fname not in called:
                continue
            seen.add(fname)
            kept.append(best_by_name[fname][1])
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
    banned_libs: frozenset[str] = frozenset(),
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

    ``banned_libs`` (TODO #85) : transmis tel quel à ``build_lib_context``
    (voir `_build_lib_context`) — les libs bannies par un swap de puce vers
    une cible nue. Vide par défaut : aucun appelant existant ne change.

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
                            ranking_hint=ranking_hint,
                            banned_libs=banned_libs)
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


_MOTOR_DRIVER_DOC_IDS: frozenset | None = None

# ⚠️ **Deux drivers du registre sont EXEMPTES du filtre, et la suite de tests
# les a designes elle-meme** (2026-08-31 : deux caracterisations existantes
# ont rougi, exactement sur ces deux entrees, et sur AUCUNE autre). La
# frontiere n'est pas « function=motor_driver » : c'est « le besoin a-t-il
# une forme SANS puce ». Un moteur DC ou un pas-a-pas se pilotent en broches
# nues, et la modale de cablage offre le choix du driver ensuite. Mais :
#   - `pca9685` : « driver 16 servos » -- Servo.h plafonne a 12 sorties sur
#     Uno, la puce EST le besoin. Le supprimer laissait remonter du bruit
#     radio/wifi (si4713, wiz820io...) a la place ;
#   - `drv2605` : « driver de vibration haptique » -- aucun equivalent nu.
# Meme statut que les ecrans : quelqu'un doit choisir une puce pour ecrire la
# premiere ligne, et mieux vaut le mecanisme visible et corrigeable que la
# memoire du SLM. Un NOUVEAU driver ajoute au registre est supprime PAR
# DEFAUT (la direction sure pour #82) ; l'exempter exige de passer ici et
# d'assumer l'argument « pas de forme nue ».
_NO_BARE_FORM_DRIVER_DOCS = frozenset({"pca9685", "drv2605"})
# Mots d'un nom de produit qui ne discriminent RIEN : le bruit d'edition
# (« library »), et -- dans une famille qui ne contient QUE des drivers de
# moteur -- les mots « motor »/« driver » eux-memes. Les exiger faisait
# echouer un nommage parfaitement explicite : « piloter deux moteurs DC avec
# un shield Adafruit » ne contient pas le mot anglais « motor » (le francais
# ecrit « moteurs », et meme l'anglais ecrit « motors », pluriel). Mesure au
# banc : 4 cas « decrit precis » passaient de correct a wrong sur ce seul
# oubli. Ce qui discrimine, c'est la marque et la forme (« adafruit »,
# « shield », « grove ») -- pas la categorie que tout le jeu partage.
_PRODUCT_NOISE_WORDS = {"library", "lib", "arduino",
                        "motor", "motors", "driver", "drivers"}


def _prompt_names_product(entry: dict, prompt_low: str) -> bool:
    """Le prompt ecrit le NOM DE PRODUIT complet de l'entree.

    Second passe-droit du filtre motor_driver, et il existe pour une raison
    precise : deux produits de ce jeu n'ont PAS de part-number nommable.
    « Grove I2C Motor Driver » n'a comme tokens de signature que `l298` et
    `0x0f` -- ecrire son nom en toutes lettres ne comptait pas comme le
    nommer. Le « Adafruit Motor Shield V2 » n'a AUCUN token. Sans ce test, le
    filtre transformait un nommage parfaitement explicite en silence.

    ⚠️ TOUS les mots du nom (≥3 caracteres, hors bruit « library »/« vN »)
    doivent etre presents : « motor driver » seul ne debloque rien, il faut
    « grove i2c motor driver ». C'est ce qui garde le test categoriel --
    nommer une CATEGORIE (« un pont en H ») n'est pas nommer un produit.
    Local au filtre : le boost lexical, lui, ne change pas.
    """
    name = (entry.get("arduino_lib_name") or "").lower()
    if not name:
        return False
    def _stem(w: str) -> str:
        # Singulier/pluriel replies : « shields » nomme autant que « shield ».
        return w[:-1] if len(w) > 3 and w.endswith("s") else w

    words = [w for w in re.findall(r"[a-z0-9]+", name)
             if len(w) >= 3 and w not in _PRODUCT_NOISE_WORDS
             and not re.fullmatch(r"v\d+", w)]
    if not words:
        return False
    prompt_words = {_stem(w) for w in re.findall(r"[a-z0-9]+", prompt_low)}
    return all(_stem(w) in prompt_words for w in words)


def _motor_driver_doc_ids() -> frozenset:
    """Documents du corpus rattaches a un composant `function="motor_driver"`
    du registre. DERIVE, jamais ecrit a la main : une liste locale aurait
    oublie le prochain driver ajoute, exactement le trou que la checklist de
    CLAUDE.md existe pour empecher.

    Mesure le 2026-08-31 : 11 documents (l298n, sparkfun-tb6612,
    grove-i2c-motor-driver, drv8825, tmc2209, stspin220, drv8833, l293d,
    pca9685, drv2605, adafruit-motorshield-v2).
    """
    global _MOTOR_DRIVER_DOC_IDS
    if _MOTOR_DRIVER_DOC_IDS is None:
        try:
            _MOTOR_DRIVER_DOC_IDS = (_all_motor_driver_doc_ids()
                                     - _NO_BARE_FORM_DRIVER_DOCS)
        except Exception:
            # Registre illisible : on prefere le comportement d'avant (tout
            # injectable) a un retrieval qui change de forme sur une erreur
            # d'import.
            _MOTOR_DRIVER_DOC_IDS = frozenset()
    return _MOTOR_DRIVER_DOC_IDS


_ALL_MOTOR_DRIVER_DOC_IDS: frozenset | None = None


def _all_motor_driver_doc_ids() -> frozenset:
    """Tous les documents des composants `function="motor_driver"`, SANS la
    soustraction des exemptions — celle-ci n'a de sens que pour le filtre
    d'injection (`_motor_driver_doc_ids`)."""
    global _ALL_MOTOR_DRIVER_DOC_IDS
    if _ALL_MOTOR_DRIVER_DOC_IDS is None:
        try:
            from .component_registry import REGISTRY
            comps = (REGISTRY.values() if isinstance(REGISTRY, dict)
                     else REGISTRY)
            _ALL_MOTOR_DRIVER_DOC_IDS = frozenset(
                doc for c in comps if c.function == "motor_driver"
                for doc in c.documents)
        except Exception:
            _ALL_MOTOR_DRIVER_DOC_IDS = frozenset()
    return _ALL_MOTOR_DRIVER_DOC_IDS


def prompt_names_motor_driver_lib(prompt: str) -> bool:
    """Le prompt nomme-t-il un driver moteur dont le corpus porte une LIB ?

    Sert au gating du bloc MOTOR du prompt systeme (`codegen_rules`) : quand
    la reponse est oui, le RAG injecte l'API de cette bibliotheque sous
    en-tete imperatif, et le pattern broches-nues du bloc MOTOR devient une
    consigne CONTRADICTOIRE. Mesure A/B en QA AB2 du #82 (2026-08-31,
    gemma4:e2b, 6 generations par bras) : sans le bloc MOTOR 0/6 chimeres,
    avec lui 3/6 — le modele epissait les deux consignes
    (`motor1.digitalWrite(...)`), le code ne compilait pas, et la reparation
    derivait vers le `setMotor` que le bloc lui ordonnait d'ecrire. Le
    conflit n'avait que deux jours : l'entree corpus L298N date du #83.

    Meme double critere de nommage que le filtre de `retrieve_libs` :
    tokens de signature (`l298n`), ou nom de produit complet en toutes
    lettres (« shield Adafruit », « Grove I2C motor driver ») — et TOUS les
    drivers du registre comptent ici, exemptions du filtre comprises :
    nommer un PCA9685 injecte aussi sa lib, le conflit est le meme.
    """
    if not prompt or not prompt.strip():
        return False
    if not _load_corpus():
        return False
    prompt_tokens = _prompt_tokens(prompt)
    prompt_low = prompt.lower()
    for doc_id in _all_motor_driver_doc_ids():
        entry = corpus_entry(doc_id)
        if not entry or not (entry.get("arduino_lib_name") or "").strip():
            continue
        if _signature_tokens(entry) & prompt_tokens:
            return True
        if _prompt_names_product(entry, prompt_low):
            return True
    return False


def retrieve_libs(
    prompt: str,
    k: int = 3,
    threshold: float = 0.25,
    relative_gate: float = 0.85,
    banned_ids: frozenset[str] = frozenset(),
) -> list[dict]:
    """Return up to ``k`` corpus entries with score ≥ ``threshold``.

    Sorted by descending score. Each entry is the raw corpus dict augmented
    with a ``_score`` float. Empty list on any failure or if nothing clears the
    threshold.

    ``banned_ids`` (TODO #85) : ids corpus qu'un swap de puce a BANNIS de la
    feature (cible nue, ``feat.banned_lib_ids``). Ils sont écartés du
    classement — sans quoi la lib remplacée ressurgirait par similarité, le
    prompt lui ressemblant toujours. Contrairement au filtre driver ci-dessous,
    nommer la puce ne la ramène PAS : le swap est POSTÉRIEUR au prompt, c'est
    lui la décision. Vide par défaut : aucun appelant existant ne change.

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
    # ⛔ **Une lib liee a une puce de DRIVER ne s'injecte que si la puce est
    # nommee** (TODO #82, mesure du 2026-08-31 : 7 prompts moteur generiques
    # sur 18 injectaient un driver -- « deux moteurs DC » recevait le
    # SparkFun TB6612 a 0.605 DEVANT l'entree generique, et « un robot a deux
    # roues » recevait L298N + Motor Shield sans meme `dc_motor`). Le SLM
    # obeit au contexte (mesure au #37), donc il codait pour une puce que
    # l'utilisateur n'a jamais mentionnee ; depuis que les noms de libs sont
    # corriges (#83), ca COMPILE -- l'echec silencieux que le #37 existe pour
    # supprimer.
    #
    # Le principe etait deja tranche ailleurs : le choix du driver appartient
    # a la modale de cablage (les ClarifyGroup excluent moteurs et drivers
    # pour cette raison), et le code moteur a une forme SANS lib -- PWM +
    # broches de direction -- qui est celle que tout le pipeline de cablage
    # attend (groupement niveau 3, cards de drivers, offre de regeneration).
    # S'engager sur une puce a la generation, c'est decider a la place de la
    # modale.
    #
    # Categoriel, sans seuil : le critere de nommage est EXACTEMENT celui du
    # boost lexical ci-dessus (`_signature_tokens & prompt_tokens`), donc une
    # puce nommee est a la fois boostee et injectable. Et comme
    # `_build_lib_context` concatene le `ranking_hint` (#64) au prompt AVANT
    # cet appel, la puce du PROJET passe aussi -- un prompt de suite sur un
    # projet L298N garde sa lib (bande 3 de `bench_motor_agnostic`, 0 perdu).
    #
    # ⚠️ NE PAS generaliser aux autres familles : un ecran ou un capteur n'a
    # PAS de forme sans lib -- quelqu'un doit choisir une puce pour ecrire la
    # premiere ligne, et mieux vaut que ce soit le mecanisme visible et
    # corrigeable (retrieval + bannière + swap) que la memoire du SLM.
    suppressed = _motor_driver_doc_ids()
    top_score: float | None = None
    out: list[dict] = []
    for idx in order:
        if len(out) >= k:
            break
        score = float(scores[idx])
        if score < threshold:
            break
        raw = _corpus[idx]
        # #85 : un ban est inconditionnel (pas de passe-droit « nommé »).
        if raw.get("id") in banned_ids:
            continue
        if (raw.get("id") in suppressed
                and not (_signature_tokens(raw) & prompt_tokens)
                and not _prompt_names_product(raw, prompt.lower())):
            continue
        if top_score is None:
            top_score = score
        elif score < relative_gate * top_score:
            break
        entry = dict(raw)
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


# ─── Anti-rebond : motif de code, pas bibliothèque (TODO #90) ────────────
# Mesuré le 2026-08-31 : sur « compte les appuis sur un bouton »,
# `gemma4:e2b` écrit un anti-rebond qui compte ZÉRO appui — dans les QUATRE
# configurations essayées (seul 0/4, en ajout 3/5, après consigne ciblée
# 4/5, après fusion 5/5). Toujours le même bug : une condition de front en
# TROP (`if (lastButtonState == HIGH)`) sur une variable que le bloc
# précédent vient d'aligner, ce qui rend l'incrément inatteignable. Ça
# compile, le schéma est juste, et rien ne le dit.
#
# Le modèle n'a besoin d'AUCUNE bibliothèque ici — il a besoin du bon
# MOTIF. Exactement la situation du scanner I2C ci-dessus, et le même
# remède : injection déterministe, sans seuil, dans la branche AVANT la
# garde « composant de base » (laquelle répond à une autre question — « ce
# composant a-t-il besoin d'une lib ? » — et reste intacte).
#
# Indices en DEUX groupes, tous deux exigés : un bouton, ET un besoin de
# détecter un ÉVÉNEMENT (compter, à chaque appui, anti-rebond). Un simple
# « allume la LED quand le bouton est appuyé » lit un ÉTAT, n'a pas besoin
# de ce motif et ne doit pas le recevoir — c'est le cas validé en QA AE1.
_DEBOUNCE_BUTTON_CUES = (
    "bouton", "boutons", "poussoir", "button", "buttons", "push-button",
    "pushbutton", "boton", "botón", "botones", "pulsador", "pulsante",
    "pulsanti",
)
_DEBOUNCE_EVENT_CUES = (
    # anti-rebond nommé explicitement
    "anti-rebond", "antirebond", "anti rebond", "rebond", "debounce",
    "antirrebote", "rimbalzo",
    # compter des appuis / réagir à CHAQUE appui (détection de front)
    "compte les appui", "compter les appui", "compte le nombre",
    "nombre d'appui", "nombre de fois", "combien de fois", "chaque appui",
    "chaque pression", "appuis", "appuye 3", "appuyé 3",
    "count the press", "counts the press", "number of press", "each press",
    # « presses » au PLURIEL seulement : « count the button presses » le
    # porte, « when the button is pressed » ne le porte pas (pressed).
    "presses",
    "press count", "times the button", "every press",
    "cuenta las pulsacion", "numero de pulsacion", "número de pulsacion",
    "cada pulsacion", "cada pulsación",
    "conta le pression", "numero di pression", "ogni pression",
)


def _prompt_needs_debounce(prompt: str) -> bool:
    """True si le prompt demande de détecter un ÉVÉNEMENT d'appui (compter,
    réagir à chaque appui, anti-rebond) — pas simplement de lire l'état d'un
    bouton. Les deux groupes d'indices sont exigés : sans le bouton, « compte
    le nombre de tours » n'a rien à voir ; sans l'événement, « allume la LED
    quand le bouton est appuyé » n'a pas besoin de ce motif (QA AE1)."""
    t = prompt.lower()
    return (any(c in t for c in _DEBOUNCE_BUTTON_CUES)
            and any(c in t for c in _DEBOUNCE_EVENT_CUES))


# Motif d'anti-rebond AUTHENTIQUE — celui de l'exemple officiel Arduino
# `Debounce.ino`, VÉRIFIÉ par simulation (`scripts/simu_rebond_reimplementation.py`) :
# il compte 3 sur 3 appuis nets de 200 ms, là où toutes les variantes
# écrites par le modèle comptent 0.
# ⚠️ Ne PAS y ajouter de condition de front supplémentaire sur
# `lastButtonState` : c'est précisément l'erreur du modèle, et elle rend
# l'incrément inatteignable (`buttonState` a déjà été aligné au-dessus).
_DEBOUNCE_PATTERN_REF = {
    "name": "Anti-rebond d'un bouton (motif Arduino officiel, sans bibliothèque)",
    "headers": [],
    "example_code": (
        "const int buttonPin = 2;\n"
        "int buttonState = HIGH;         // etat STABLE (apres anti-rebond)\n"
        "int lastReading = HIGH;         // derniere lecture BRUTE\n"
        "unsigned long lastDebounceTime = 0;\n"
        "const unsigned long debounceDelay = 50;\n"
        "int pressCount = 0;\n"
        "\n"
        "void setup() {\n"
        "  pinMode(buttonPin, INPUT_PULLUP);\n"
        "  Serial.begin(9600);\n"
        "}\n"
        "\n"
        "void loop() {\n"
        "  int reading = digitalRead(buttonPin);\n"
        "  if (reading != lastReading) {\n"
        "    lastDebounceTime = millis();   // la lecture bouge : on repart\n"
        "  }\n"
        "  if (millis() - lastDebounceTime > debounceDelay) {\n"
        "    if (reading != buttonState) {  // l'etat STABLE change\n"
        "      buttonState = reading;\n"
        "      if (buttonState == LOW) {    // front d'APPUI : compter ICI\n"
        "        pressCount++;\n"
        "        Serial.println(pressCount);\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "  lastReading = reading;\n"
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
