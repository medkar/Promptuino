"""Enrich assets/rag/corpus.json with `api_signatures` per entry.

Pour chaque entree du corpus qui n'a PAS DEJA la clef `api_signatures` (meme
absente ou vide) :
  - Resoudre chaque en-tete liste dans entry["headers"] a un fichier sous
    <cache_root>/<lib>/.
  - Lancer extract_api_signatures.extract() sur les en-tetes resolus.
  - INSERER le dict {class: [signatures]} resultant sous entry["api_signatures"].

Les entrees qui ont DEJA la clef `api_signatures` — meme avec une valeur
vide (`{}`, ou l'ancien format `[]`) — sont laissees intactes : ce script
n'ecrit jamais par-dessus une clef existante, il se contente d'INSERER la
clef manquante. Chaque entree touchee est donc une insertion pure : le
fichier ne perd jamais une ligne de contenu (seule une virgule finale peut
s'ajouter au dernier champ existant, consequence syntaxique inevitable de
l'ajout d'une clef).

Les en-tetes qui ne se resolvent pas (en-tetes Arduino de base comme SPI.h /
Wire.h, ou tout ce qui est absent du repertoire source) sont silencieusement
ignores — ils n'ont pas de surface d'API publique qu'on controle de toute
facon.

Usage:
    python scripts/enrich_corpus_with_api.py
        # utilise le repertoire par defaut (~/.cache/promptuino_rag_build)
    python scripts/enrich_corpus_with_api.py --cache-root <chemin>
        # utilise un autre repertoire source pour les en-tetes (ex. les
        # bibliotheques reellement installees dans un workspace Arduino),
        # sans rien changer d'autre au comportement du script
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `from extract_api_signatures import extract` when running from repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_api_signatures import extract  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = REPO_ROOT / "assets" / "rag" / "corpus.json"
DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "promptuino_rag_build"


def _build_header_index(cache_root: Path) -> dict[str, list[Path]]:
    """Map header filename → list of full paths under `cache_root`.

    Multiple matches happen for very common names (OneWire.h appears in its
    own repo and inside DallasTemperature). The corpus entry's lib name
    disambiguates at lookup time.
    """
    index: dict[str, list[Path]] = {}
    if not cache_root.exists():
        return index
    for path in cache_root.rglob("*.h"):
        index.setdefault(path.name, []).append(path)
    for path in cache_root.rglob("*.hpp"):
        index.setdefault(path.name, []).append(path)
    return index


def _resolve_header(
    header_name: str, entry_id: str, index: dict[str, list[Path]],
    cache_root: Path,
) -> Path | None:
    """Pick the best-matching path for `header_name`.

    Prefer paths under a top-level folder (under `cache_root`) whose name
    fuzzy-matches the corpus entry id (so OneWire.h inside DallasTemperature's
    tree wins for the dallas-temperature entry, and the standalone OneWire
    repo wins for the onewire entry).
    """
    candidates = index.get(header_name, [])
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    entry_norm = entry_id.replace("-", "").replace("_", "").lower()
    best = None
    best_score = -1
    for c in candidates:
        # Top folder under cache_root
        try:
            top = c.relative_to(cache_root).parts[0]
        except ValueError:
            continue
        top_norm = top.replace("-", "").replace("_", "").lower()
        # Score: longer common prefix wins.
        score = sum(1 for a, b in zip(top_norm, entry_norm) if a == b)
        if score > best_score:
            best_score = score
            best = c
    return best or candidates[0]


def _format_api_signatures_snippet(api: dict, newline: str) -> str:
    """Serialize `api` the way it already appears in corpus.json.

    `json.dump(corpus, indent=2)` on the WHOLE file would reformat every
    entry (compact single-line arrays elsewhere in the file get expanded),
    which is exactly the "reordering/reformatting" the task forbids. Only
    the `api_signatures` value itself is serialized here, then spliced into
    the untouched original text -- so nothing else in the file moves.

    The base indent of the `"api_signatures"` key is 4 spaces (entries sit
    2-space-indented inside the top-level array, their fields 2 more) --
    matched against the existing entries that already carry this field.
    `newline` matches the file's own line ending (corpus.json is CRLF).
    """
    dumped = json.dumps(api, indent=2, ensure_ascii=False)
    lines = dumped.split("\n")
    return newline.join([lines[0]] + ["    " + line for line in lines[1:]])


def _splice_api_signatures(content: str, entry_id: str, api: dict, newline: str) -> str:
    """Insert `"api_signatures": <api>` into the entry whose `"id"` is
    `entry_id`, as the last key of that JSON object, without touching a
    single byte outside that object.

    Locates the entry's exact span with `json.JSONDecoder.raw_decode` (a
    real parser, unlike brace-counting on raw text -- several entries embed
    literal `{`/`}` inside `example_code` C++ snippets, which would throw
    off a naive scan). `content` is read with `newline=""` (no universal
    newline translation) so the file's own CRLF line endings are preserved
    byte-for-byte outside the spliced-in text.
    """
    marker = f'"id": "{entry_id}"'
    id_pos = content.find(marker)
    if id_pos == -1:
        raise ValueError(f"id marker not found for {entry_id!r}")
    start = content.rfind("{", 0, id_pos)
    decoder = json.JSONDecoder()
    parsed, end = decoder.raw_decode(content, start)
    entry_text = content[start:end]

    if "api_signatures" in parsed:
        # The caller only calls this for entries that had NO api_signatures
        # key at all (see the skip condition in main()) -- this is a pure
        # insertion, never a value replacement, so an existing key here
        # (even an empty placeholder written by an earlier run) is a bug
        # upstream, not something to silently overwrite.
        raise ValueError(f"{entry_id!r} already has an api_signatures key -- refusing to touch it")

    snippet = _format_api_signatures_snippet(api, newline)
    closing = f"{newline}  }}"
    if not entry_text.endswith(closing):
        raise ValueError(f"unexpected entry tail for {entry_id!r}: {entry_text[-40:]!r}")
    new_entry_text = (
        entry_text[: -len(closing)]
        + f',{newline}    "api_signatures": {snippet}'
        + closing
    )
    return content[:start] + new_entry_text + content[end:]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cache-root",
        type=Path,
        default=DEFAULT_CACHE_ROOT,
        help="Repertoire racine ou chercher les en-tetes de bibliotheques "
             "(defaut : ~/.cache/promptuino_rag_build). Sert a pointer vers "
             "un repertoire de bibliotheques reellement installe quand ce "
             "cache est vide.",
    )
    args = parser.parse_args(argv)
    cache_root: Path = args.cache_root

    # newline="" : pas de traduction universelle -- corpus.json est en CRLF,
    # et le but de cette passe est de ne PAS reformater le fichier.
    with CORPUS_PATH.open(encoding="utf-8", newline="") as f:
        content = f.read()
    newline = "\r\n" if "\r\n" in content else "\n"
    corpus = json.loads(content)

    index = _build_header_index(cache_root)
    if not index:
        print(f"[!] cache empty or missing: {cache_root}", file=sys.stderr)
        return 1

    total_sigs = 0
    total_classes = 0
    skipped_headers: list[tuple[str, str]] = []
    already_enriched: list[str] = []
    to_apply: list[tuple[str, dict]] = []

    for entry in corpus:
        entry_id = entry["id"]
        # Ne jamais toucher une entree qui a deja la clef api_signatures --
        # meme un placeholder vide ecrit par un run precedent (`{}` / l'ancien
        # `[]`) reste intact : ce script ne fait qu'INSERER la clef manquante
        # (les 48 entrees fraichement ajoutees au corpus), jamais la
        # remplacer. Une entree deja presente est une insertion pure, donc un
        # diff sans aucune suppression de contenu existant.
        if "api_signatures" in entry:
            already_enriched.append(entry_id)
            continue
        headers = entry.get("headers", []) or []
        resolved: list[Path] = []
        for h in headers:
            path = _resolve_header(h, entry_id, index, cache_root)
            if path is None:
                skipped_headers.append((entry_id, h))
                continue
            resolved.append(path)
        if not resolved:
            print(f"  {entry_id:30s}  (no resolvable headers)")
            to_apply.append((entry_id, {}))
            continue
        api = extract(resolved)
        to_apply.append((entry_id, api))
        n_sigs = sum(len(v) for v in api.values())
        total_sigs += n_sigs
        total_classes += len(api)
        print(
            f"  {entry_id:30s}  classes={len(api):2d}  "
            f"signatures={n_sigs:3d}  from={[h.name for h in resolved]}"
        )

    # Splice one entry at a time into the ORIGINAL text -- every entry that
    # is not in `to_apply` keeps its exact original bytes.
    for entry_id, api in to_apply:
        content = _splice_api_signatures(content, entry_id, api, newline)

    with CORPUS_PATH.open("w", encoding="utf-8", newline="") as f:
        f.write(content)

    print()
    print(f"Total: {total_sigs} signatures across {total_classes} classes "
          f"in {len(corpus)} entries "
          f"({len(already_enriched)} entrees deja enrichies, laissees intactes).")
    if skipped_headers:
        print(f"Skipped (not in cache, expected for core/system headers): "
              f"{len(skipped_headers)}")
        for eid, h in skipped_headers:
            print(f"  - {eid}: {h}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
