"""Tests retrieval concepts/cartes + accents.
Run : python scripts/test_chat_concepts_rag.py
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui.chat.chat_rag import _tokenize
from ui.chat.chat_rag import CorpusIndex


def test_tokenize_strips_accents():
    assert _tokenize("résistance") == ["resistance"]
    assert _tokenize("Référence") == ["reference"]
    assert _tokenize("à côté où") == ["a", "cote", "ou"]


def test_query_min_score_filters():
    entries = [
        {"id": "a", "name": "servo motor angle control", "category": "lib"},
        {"id": "b", "name": "temperature humidity sensor", "category": "lib"},
    ]
    idx = CorpusIndex.from_entries(entries)
    assert idx.query("servo", top_k=3, min_score=1000.0) == []
    hits = idx.query("servo", top_k=3)
    assert hits and hits[0].entry["id"] == "a"


def test_entry_text_includes_concept_fields():
    from ui.chat.chat_rag import _entry_text
    e = {"name": "PWM", "category": "concept",
         "aliases": ["duty cycle", "rapport cyclique"],
         "summary": "pulse width modulation",
         "facts": ["analogWrite 0..255"]}
    text = _entry_text(e)
    for needle in ["pwm", "duty", "cyclique", "pulse", "analogwrite"]:
        assert needle in text.lower(), f"'{needle}' absent de _entry_text"


def test_concept_entry_is_retrievable():
    entries = [
        {"id": "pwm", "name": "PWM", "category": "concept",
         "aliases": ["duty cycle", "rapport cyclique", "analogwrite"],
         "summary": "pulse width modulation, average voltage control",
         "facts": ["analogWrite(pin, 0..255) on Uno"]},
        {"id": "i2c", "name": "I2C", "category": "concept",
         "aliases": ["wire", "sda", "scl", "two wire"],
         "summary": "two-wire serial bus",
         "facts": ["SDA/SCL on A4/A5 on Uno"]},
    ]
    idx = CorpusIndex.from_entries(entries)
    hits = idx.query("c'est quoi le rapport cyclique", top_k=3)
    assert hits and hits[0].entry["id"] == "pwm", \
        f"Attendu pwm, eu {[h.entry['id'] for h in hits]}"


def test_find_board_entry():
    from ui.chat.chat_rag import find_board_entry
    boards = [
        {"id": "board-uno-r3", "name": "Arduino Uno R3", "category": "board",
         "aliases": ["uno", "uno r3", "atmega328p"], "facts": ["5V logic"]},
        {"id": "board-uno-r4-minima", "name": "Arduino Uno R4 Minima",
         "category": "board", "aliases": ["uno r4", "r4 minima", "renesas"],
         "facts": ["32-bit"]},
        {"id": "pwm", "name": "PWM", "category": "concept", "aliases": ["pwm"]},
    ]
    assert find_board_entry("Uno R4 Minima", boards)["id"] == "board-uno-r4-minima"
    assert find_board_entry("Uno", boards)["id"] == "board-uno-r3"
    assert find_board_entry("", boards) is None
    assert find_board_entry("STM32 Blue Pill", boards) is None


def test_find_board_entry_soft_pass():
    from ui.chat.chat_rag import find_board_entry
    boards = [
        {"id": "board-uno-r3", "name": "Arduino Uno R3", "category": "board",
         "aliases": ["uno", "uno r3", "atmega328p"]},
        {"id": "board-uno-r4-minima", "name": "Arduino Uno R4 Minima",
         "category": "board", "aliases": ["uno r4", "r4 minima", "renesas"]},
        {"id": "board-mega", "name": "Arduino Mega 2560", "category": "board",
         "aliases": ["mega", "mega 2560", "atmega2560"]},
    ]
    # "Arduino Uno" n'est pas un alias exact -> soft pass doit choisir la R3
    # (la plus proche), PAS la R4 (nom plus long).
    assert find_board_entry("Arduino Uno", boards)["id"] == "board-uno-r3"
    assert find_board_entry("Arduino Mega", boards)["id"] == "board-mega"


def _load_real_concepts():
    from ui.chat.chat_rag import load_concepts
    return load_concepts()


def test_concepts_file_count_and_categories():
    data = _load_real_concepts()
    assert len(data) >= 79, f"Attendu >=79 entrees, eu {len(data)}"
    cats = {e.get("category") for e in data}
    assert cats == {"concept", "board", "hardware_trap"}, f"Categories inattendues: {cats}"
    n_board = sum(1 for e in data if e["category"] == "board")
    assert n_board >= 16, f"Attendu >=16 cartes, eu {n_board}"
    for e in data:
        assert e.get("id") and e.get("name") and e.get("aliases"), \
            f"Entree incomplete: {e.get('id')}"
        assert isinstance(e.get("facts", []), list)


def test_critical_facts_present():
    from ui.chat.chat_rag import CorpusIndex
    data = _load_real_concepts()
    idx = CorpusIndex.from_entries(data)
    i2c = idx.query("broches i2c arduino uno sda scl", top_k=3)
    blob = " ".join(f for h in i2c for f in (h.entry.get("facts") or [])).lower()
    assert "a4" in blob and "a5" in blob, "I2C A4/A5 absent"
    esp = idx.query("esp32 tension logique voltage", top_k=3)
    blob = " ".join((h.entry.get("summary", "") + " " +
                     " ".join(h.entry.get("facts") or []))
                    for h in esp).lower()
    assert "3.3" in blob, "ESP32 3.3V absent"


def test_multilingual_concept_matching():
    from ui.chat.chat_rag import CorpusIndex
    data = _load_real_concepts()
    idx = CorpusIndex.from_entries(data)
    cases = [
        ("what is pwm", "pwm"),
        ("c'est quoi une résistance pull-up", "pull-up"),
        ("diferencia entre uno r3 y r4", None),
    ]
    for query, expect_id in cases:
        hits = idx.query(query, top_k=3)
        assert hits, f"Aucun hit pour: {query}"
        if expect_id:
            ids = [h.entry["id"] for h in hits]
            assert expect_id in ids, f"{expect_id} absent pour '{query}': {ids}"


def test_board_manager_models_map_correctly():
    """Les noms de modeles reels de board_manager.BOARDS doivent mapper sur
    la BONNE entree carte. Regression : "Wemos D1 Mini ESP32" tombait sur
    l'ESP8266 (dont l'alias "wemos d1" gagnait au closest-length)."""
    from ui.chat.chat_rag import find_board_entry
    data = _load_real_concepts()
    cases = {
        "Wemos D1 Mini ESP32": "board-esp32-devkit",
        "ESP32 DevKit v1": "board-esp32-devkit",
        "Uno R4 Minima": "board-uno-r4-minima",
        "Mega 2560": "board-mega-2560",
    }
    for model, expect_id in cases.items():
        e = find_board_entry(model, data)
        assert e is not None and e["id"] == expect_id, \
            f"{model} -> {e and e['id']}, attendu {expect_id}"


TESTS = [
    test_tokenize_strips_accents,
    test_query_min_score_filters,
    test_entry_text_includes_concept_fields,
    test_concept_entry_is_retrievable,
    test_find_board_entry,
    test_find_board_entry_soft_pass,
    test_concepts_file_count_and_categories,
    test_critical_facts_present,
    test_multilingual_concept_matching,
    test_board_manager_models_map_correctly,
]


def main() -> int:
    for t in TESTS:
        try:
            t()
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
            raise
    print(f"OK : {len(TESTS)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
