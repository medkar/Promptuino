"""CodePanel (ui/studio) : voile busy, verrou, dropdown, surlignage, overlay."""
import os
import sys
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
_app = QApplication.instance() or QApplication(sys.argv)   # ref module-level

from ui.generation import Feature
from ui.studio import CodePanel


def _feats(n):
    return [Feature(id=f"f{i}", prompt=f"p{i}", summary=f"s{i}")
            for i in range(1, n + 1)]


def test_set_features_populates_dropdown():
    # Le dropdown est peuplé au fil des fonctionnalités (le studio le place et
    # gère sa visibilité ; ici on vérifie seulement le remplissage).
    p = CodePanel()
    p.set_features(_feats(2))
    assert len(p.feature_dropdown._rows) == 2
    p.set_features([])
    assert len(p.feature_dropdown._rows) == 0


def test_dropdown_created_outside_panel_layout():
    # Le dropdown n'est JAMAIS ajouté au layout du panneau (le studio le place
    # sur la ligne d'outils). embed_chips n'a plus d'effet sur le placement.
    p_in = CodePanel(embed_chips=True)
    assert p_in.layout().indexOf(p_in.feature_dropdown) == -1
    p_out = CodePanel(embed_chips=False)
    assert p_out.layout().indexOf(p_out.feature_dropdown) == -1
    # Le câblage surlignage marche quand même (dropdown créé).
    p_out.set_features(_feats(2))
    p_out.feature_dropdown.selection_changed.emit(["f1"])
    assert p_out._selected_ids == ["f1"]


def test_busy_veil_and_readonly():
    p = CodePanel()
    assert not p.is_busy()
    assert not p.editor.isReadOnly()
    p.set_busy("Vérification")
    assert p.is_busy()
    assert p.editor.isReadOnly()
    assert not p._veil.isHidden()
    assert p._veil_timer.isActive()
    p.set_busy(None)
    assert not p.is_busy()
    assert not p.editor.isReadOnly()
    assert p._veil.isHidden()
    assert not p._veil_timer.isActive()


def test_set_locked():
    p = CodePanel()
    p.set_locked(True)     # ne doit pas lever ; verrou != readOnly
    assert not p.editor.isReadOnly()
    p.set_locked(False)


def test_comment_loader():
    p = CodePanel()
    assert p._cmt_overlay.isHidden()
    p.show_comment_loader(True)
    assert not p._cmt_overlay.isHidden()
    p.show_comment_loader(False)
    assert p._cmt_overlay.isHidden()


def test_selection_drives_highlight_no_crash():
    p = CodePanel()
    p.set_features(_feats(3))
    p.editor.setPlainText("void setup() {}\nvoid loop() {}\n")
    # Sélection -> surlignage (via le signal interne du dropdown).
    p.feature_dropdown.selection_changed.emit(["f2"])
    assert p._selected_ids == ["f2"]
    # Survol additif puis retour.
    p.feature_dropdown.hover_preview.emit("f1")
    assert p._hover_id == "f1"
    p.feature_dropdown.hover_preview.emit("")
    assert p._hover_id == ""


def test_clear_selection():
    p = CodePanel()
    p.set_features(_feats(2))
    p.feature_dropdown.selection_changed.emit(["f1"])
    assert p._selected_ids == ["f1"]
    p.clear_selection()
    assert p._selected_ids == [] and p._hover_id == ""


def test_refresh_highlights_resyncs_features():
    p = CodePanel()
    p.set_features(_feats(2))
    p.feature_dropdown.selection_changed.emit(["f1"])
    # Nouveau code livré avec une liste de features fraîche -> pas de crash,
    # la référence est resynchronisée.
    p.refresh_highlights(_feats(3))
    assert len(p._features) == 3


def test_dropdown_actions_per_line():
    # Les actions ↻/🗑 sont posees PAR LIGNE du popup : une paire par
    # fonctionnalite, independamment des cases cochees. Le voile busy grise le
    # bouton dropdown (et replie le popup).
    p = CodePanel()
    p.set_features(_feats(2))
    dd = p.feature_dropdown
    assert len(dd._regen_btns) == 2 and len(dd._delete_btns) == 2
    p.set_busy("Compilation")
    assert not dd._btn.isEnabled()
    p.set_busy(None)
    assert dd._btn.isEnabled()


TESTS = [test_set_features_populates_dropdown,
         test_dropdown_created_outside_panel_layout, test_busy_veil_and_readonly,
         test_set_locked, test_comment_loader,
         test_selection_drives_highlight_no_crash, test_clear_selection,
         test_refresh_highlights_resyncs_features,
         test_dropdown_actions_per_line]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        t()
        passed += 1
    print(f"{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0)
