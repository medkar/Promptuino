"""Actions Regenerer/Supprimer du dropdown (via CodePanel) : posees PAR LIGNE
dans le popup + stable sans regen. Chaque bouton ↻/🗑 agit sur SA
fonctionnalite. On les pilote via `panel.feature_dropdown._regen_btns` /
`_delete_btns` (une entree par ligne).
"""
import os, sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication(sys.argv)
from ui.fonts import setup_fonts
setup_fonts(_APP)
from ui.studio.code_panel import CodePanel
from ui.generation.feature_model import Feature


def _feat(fid, prompt):
    return Feature(id=fid, prompt=prompt)


def test_one_action_pair_per_row():
    p = CodePanel(embed_chips=False)
    p.set_features([_feat("f1", "LED"), _feat("f2", "Bouton")])
    dd = p.feature_dropdown
    assert len(dd._regen_btns) == 2 and len(dd._delete_btns) == 2


def test_busy_disables_dropdown_button():
    p = CodePanel(embed_chips=False)
    p.set_features([_feat("f1", "LED")])
    p.set_busy("Compilation")
    assert not p.feature_dropdown._btn.isEnabled()
    p.set_busy(None)
    assert p.feature_dropdown._btn.isEnabled()


def test_stable_panel_has_no_regen():
    p = CodePanel(embed_chips=False, can_regenerate=False)
    p.set_features([_feat("f1", "LED")])
    dd = p.feature_dropdown
    assert dd._regen_btns == []              # pas de ↻ cote stable
    assert len(dd._delete_btns) == 1         # 🗑 par ligne present


def test_per_line_signals_carry_that_feature():
    p = CodePanel(embed_chips=False)
    got = {}
    p.feature_dropdown.regen_requested.connect(
        lambda ids: got.__setitem__("regen", list(ids)))
    p.feature_dropdown.delete_requested.connect(
        lambda ids: got.__setitem__("delete", list(ids)))
    p.set_features([_feat("f1", "LED"), _feat("f2", "Bouton")])
    p.feature_dropdown._regen_btns[1].click()    # ligne f2
    p.feature_dropdown._delete_btns[0].click()   # ligne f1
    assert got["regen"] == ["f2"]
    assert got["delete"] == ["f1"]


TESTS = [
    test_one_action_pair_per_row,
    test_busy_disables_dropdown_button,
    test_stable_panel_has_no_regen,
    test_per_line_signals_carry_that_feature,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t(); passed += 1
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
