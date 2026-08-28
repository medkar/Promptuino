"""#60 -- les entrées corpus n'ont-elles pas été recopiées sur la batterie ?

L'isolation des deux rédacteurs est une CONSIGNE, pas une barrière technique.
Cette garde la rend vérifiable : si une entrée avait été écrite en regardant
les prompts qui l'évaluent, la mesure réussirait par construction -- la faute
qui a tué le filet d'ambiguïté automatique en juin 2026.

Le critère est le 4-gramme partagé. Un vocabulaire commun est NORMAL et
attendu (« pressure sensor » des deux côtés) ; quatre mots consécutifs
identiques ne le sont pas.

Run: python scripts/test_battery_b_independence.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

BATTERY = ROOT / "scripts" / "bench_rag_prompts_b.json"
N = 4


def _grams(text: str, n: int = N) -> set[tuple[str, ...]]:
    words = re.findall(r"[a-zà-ÿ0-9]+", text.lower())
    return {tuple(words[i:i + n]) for i in range(len(words) - n + 1)}


def test_no_entry_shares_a_four_gram_with_its_own_prompts():
    import ui.rag as rag
    cases = json.loads(BATTERY.read_text(encoding="utf-8"))
    by_id: dict[str, list[str]] = {}
    for c in cases:
        # TOUS les ids attendus, pas seulement le premier. Deux composants du
        # lot (`max1704x`, `microsd_card_module`) se sont reveles etre des
        # DOUBLONS d'entrees curees (`max17043`, `sd`) : leurs mots-cles ont
        # ete verses dans celles-ci et l'entree en doublon supprimee. Indexee
        # sur `expect[0]` seul, la garde ne trouvait plus d'entree a ce nom et
        # sautait le cas -- elle devenait aveugle exactement la ou du texte
        # avait bouge.
        for cid in c["expect"]:
            by_id.setdefault(cid, []).append(c["prompt"])
    entries = {e["id"]: e for e in rag.all_corpus_entries()}
    offenders = []
    for cid, prompts in by_id.items():
        entry = entries.get(cid)
        if entry is None:
            continue          # pas encore écrite : ce test tourne aussi avant
        text = (entry.get("description") or "") + " " + \
               " ".join(entry.get("keywords") or [])
        entry_grams = _grams(text)
        for p in prompts:
            shared = entry_grams & _grams(p)
            if shared:
                offenders.append((cid, p, sorted(shared)[:2]))
    assert not offenders, (
        "entrees et prompts partagent des sequences de 4 mots -- l'une a "
        "probablement ete ecrite en regardant l'autre :\n  "
        + "\n  ".join(f"{cid}: {p!r} -> {g}" for cid, p, g in offenders[:10]))


TESTS = [test_no_entry_shares_a_four_gram_with_its_own_prompts]


def main() -> int:
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"  OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} tests OK")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
