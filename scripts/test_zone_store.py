"""Tests unitaires ZoneStore (peinture, undo/redo, JSON roundtrip)."""
from __future__ import annotations

import json
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ui_pkg = types.ModuleType("ui")
ui_pkg.__path__ = [str(ROOT / "ui")]
sys.modules["ui"] = ui_pkg

from ui.wiring.routing.zone_editor.zone_store import ZoneStore, grid_origin_offset


def test_paint_basic():
    store = ZoneStore()
    store.begin_action()
    assert store.paint((5, 10), "forbid") is True
    store.end_action()
    assert store.color_at((5, 10)) == "forbid"
    assert store.total_painted() == 1
    assert store.is_dirty() is True


def test_paint_noop_when_same_color():
    store = ZoneStore()
    store.begin_action()
    store.paint((1, 1), "cost")
    store.end_action()
    # Repeindre la meme couleur = no-op
    store.begin_action()
    assert store.paint((1, 1), "cost") is False
    store.end_action()
    assert store.total_painted() == 1


def test_paint_switches_color():
    store = ZoneStore()
    store.begin_action()
    store.paint((2, 3), "forbid")
    store.end_action()
    store.begin_action()
    assert store.paint((2, 3), "allow") is True
    store.end_action()
    # Plus dans forbid, dans allow
    assert store.color_at((2, 3)) == "allow"
    assert (2, 3) not in store.cells["forbid"]


def test_erase_with_none():
    store = ZoneStore()
    store.begin_action()
    store.paint((0, 0), "cost")
    store.end_action()
    store.begin_action()
    assert store.paint((0, 0), None) is True
    store.end_action()
    assert store.color_at((0, 0)) is None
    assert store.total_painted() == 0


def test_undo_redo_single():
    store = ZoneStore()
    store.begin_action()
    store.paint((10, 10), "forbid")
    store.end_action()
    assert store.color_at((10, 10)) == "forbid"

    action = store.undo()
    assert action is not None
    assert store.color_at((10, 10)) is None

    action = store.redo()
    assert action is not None
    assert store.color_at((10, 10)) == "forbid"


def test_undo_drag_batch():
    """Un drag = 1 action = 1 entree undo, peu importe le nb de cellules."""
    store = ZoneStore()
    store.begin_action()
    for col in range(5):
        store.paint((col, 0), "cost")
    store.end_action()
    assert store.total_painted() == 5

    store.undo()
    assert store.total_painted() == 0

    store.redo()
    assert store.total_painted() == 5


def test_undo_preserves_initial_color():
    """Si une action ecrase une couleur existante puis l'efface plus tard
    dans la meme action, undo doit restaurer la couleur INITIALE."""
    store = ZoneStore()
    store.begin_action()
    store.paint((1, 1), "forbid")
    store.end_action()
    # Nouvelle action : peint allow puis efface dans le meme batch
    store.begin_action()
    store.paint((1, 1), "allow")
    store.paint((1, 1), None)
    store.end_action()
    assert store.color_at((1, 1)) is None
    store.undo()
    assert store.color_at((1, 1)) == "forbid"


def test_redo_cleared_by_new_action():
    """Une nouvelle action vide la pile redo (comportement standard)."""
    store = ZoneStore()
    store.begin_action()
    store.paint((0, 0), "forbid")
    store.end_action()
    store.undo()
    # Apres undo, redo possible
    store.begin_action()
    store.paint((1, 1), "cost")
    store.end_action()
    # Redo doit etre vide maintenant
    assert store.redo() is None


def test_json_roundtrip():
    store = ZoneStore(cell_size=8, cost_value=80, bb_svg="assets/foo.svg",
                      bb_anchor=(30.0, 30.0))
    store.begin_action()
    store.paint((5, 5), "forbid")
    store.paint((6, 5), "forbid")
    store.paint((10, 20), "cost")
    store.paint((3, 3), "allow")
    store.end_action()

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.json"
        store.save(path)
        assert not store.is_dirty()
        # Verifie format JSON minimal
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert data["cell_size"] == 8
        assert data["cost_value"] == 80
        assert data["bb_svg"] == "assets/foo.svg"
        assert data["bb_anchor"] == {"x": 30.0, "y": 30.0}
        assert sorted(data["cells"]["forbid"]) == [[5, 5], [6, 5]]
        assert data["cells"]["cost"] == [[10, 20]]
        assert data["cells"]["allow"] == [[3, 3]]

        # Roundtrip
        store2 = ZoneStore.load(path)
        assert store2.cell_size == 8
        assert store2.cost_value == 80
        assert store2.bb_svg == "assets/foo.svg"
        assert store2.bb_anchor == (30.0, 30.0)
        assert store2.cells["forbid"] == {(5, 5), (6, 5)}
        assert store2.cells["cost"] == {(10, 20)}
        assert store2.cells["allow"] == {(3, 3)}
        assert not store2.is_dirty()


def test_grid_origin_offset_aligns_anchor_to_cell_center():
    """offset(anchor, cs) doit positionner la grille de sorte que les
    cellules contiennent l'anchor en leur centre."""
    # cs=8, anchor=30 -> offset = (30-4) % 8 = 2
    ox, oy = grid_origin_offset((30.0, 30.0), 8)
    assert (ox, oy) == (2.0, 2.0)
    # Cell ((30-2)//8, (30-2)//8) = (3, 3). Centre = (2 + 3*8 + 4, ...) = (30, 30) ✓
    # cs=4, anchor=30 -> offset = (30-2) % 4 = 0
    assert grid_origin_offset((30.0, 30.0), 4) == (0.0, 0.0)
    # cs=14 -> offset = (30-7) % 14 = 9
    assert grid_origin_offset((30.0, 30.0), 14) == (9.0, 9.0)
    # cs=1 -> offset = (30 - 0.5) % 1 = 0.5
    assert grid_origin_offset((30.0, 30.0), 1) == (0.5, 0.5)
    # cs=2 -> offset = (30-1) % 2 = 1
    assert grid_origin_offset((30.0, 30.0), 2) == (1.0, 1.0)


def test_clear_all_undoable():
    store = ZoneStore()
    store.begin_action()
    store.paint((0, 0), "forbid")
    store.paint((1, 1), "cost")
    store.end_action()
    store.clear_all()
    assert store.total_painted() == 0
    # Undo restore
    store.undo()
    assert store.total_painted() == 2
    assert store.color_at((0, 0)) == "forbid"
    assert store.color_at((1, 1)) == "cost"


def test_dedup_in_save():
    """Le save trie + dedupe les cellules (idempotence diff git)."""
    store = ZoneStore()
    # Inject directement dans le set pour simuler doublons impossibles via paint()
    store.cells["forbid"].update({(3, 3), (1, 1), (2, 2)})
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "out.json"
        store.save(path)
        data = json.loads(path.read_text(encoding="utf-8"))
        # Triees lex
        assert data["cells"]["forbid"] == [[1, 1], [2, 2], [3, 3]]


def main() -> int:
    tests = [
        test_paint_basic,
        test_paint_noop_when_same_color,
        test_paint_switches_color,
        test_erase_with_none,
        test_undo_redo_single,
        test_undo_drag_batch,
        test_undo_preserves_initial_color,
        test_redo_cleared_by_new_action,
        test_json_roundtrip,
        test_grid_origin_offset_aligns_anchor_to_cell_center,
        test_clear_all_undoable,
        test_dedup_in_save,
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  [OK]   {fn.__name__}")
        except AssertionError as e:
            print(f"  [FAIL] {fn.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERR]  {fn.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{len(tests) - failed}/{len(tests)} OK")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
