"""Editeur graphique standalone PyQt6 pour peindre des zones manuelles
sur la grille d'occupation du routeur v3.

Usage :
    python scripts/cell_zone_editor.py
    python scripts/cell_zone_editor.py --json path/to/other.json

Sans --json : charge/sauve assets/wiring/manual_zones.json (defaut).
Avec --json : charge/sauve le fichier specifie (preview / multi-presets).

Voir docs/superpowers/specs/2026-05-15-cell-zone-editor-design.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence, QPalette, QColor
from PyQt6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QWidget,
)

from ui.wiring.routing.zone_editor.editor_widget import ZoneEditorView
from ui.wiring.routing.zone_editor.toolbar import ZoneToolbar
from ui.wiring.routing.zone_editor.zone_store import (
    DEFAULT_BB_SVG,
    ZoneStore,
)

DEFAULT_JSON_PATH = ROOT / "assets" / "wiring" / "manual_zones.json"
DEFAULT_BB_SVG_PATH = ROOT / "assets" / "wiring" / "breadboards" / "mini.svg"


class ZoneEditorWindow(QMainWindow):
    def __init__(self, json_path: Path = DEFAULT_JSON_PATH):
        super().__init__()
        self.setWindowTitle(f"PromptuinoUI — Cell Zone Editor ({json_path.name})")
        self.resize(1100, 760)
        self._apply_palette()

        self.json_path: Path = json_path

        # ── Store : auto-load si fichier existe ─────────────────────────
        if self.json_path.exists():
            try:
                self.store = ZoneStore.load(self.json_path)
                print(f"[zone-editor] charge {self.json_path}")
            except Exception as exc:
                print(f"[zone-editor] erreur load {self.json_path} : {exc}")
                self.store = ZoneStore(bb_svg=DEFAULT_BB_SVG)
        else:
            self.store = ZoneStore(bb_svg=DEFAULT_BB_SVG)

        # ── Toolbar + view ──────────────────────────────────────────────
        self.toolbar = ZoneToolbar(
            cell_size=self.store.cell_size,
            cost_value=self.store.cost_value,
        )
        # bb_svg du JSON est relatif a la racine du repo (ex
        # "assets/wiring/breadboards/mini.svg"). Si introuvable, fallback
        # sur le BB par defaut.
        bb_svg_path = (ROOT / self.store.bb_svg) if self.store.bb_svg else DEFAULT_BB_SVG_PATH
        if not bb_svg_path.exists():
            print(f"[zone-editor] BB SVG introuvable : {bb_svg_path}, "
                  f"fallback sur {DEFAULT_BB_SVG_PATH}")
            bb_svg_path = DEFAULT_BB_SVG_PATH
        self.view = ZoneEditorView(bb_svg_path, self.store)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.view, 1)
        self.setCentralWidget(central)

        # ── Wiring signaux ──────────────────────────────────────────────
        self.toolbar.tool_changed.connect(self.view.set_tool)
        self.toolbar.cell_size_changed.connect(self._on_cell_size_changed)
        self.toolbar.cost_value_changed.connect(self._on_cost_value_changed)
        self.toolbar.zoom_in.connect(self.view.zoom_in)
        self.toolbar.zoom_out.connect(self.view.zoom_out)
        self.toolbar.zoom_reset.connect(self.view.zoom_reset)
        self.view.cell_painted.connect(self._update_stats)
        self.view.zoom_changed.connect(self.toolbar.set_zoom_pct)

        # Sync etat initial
        self.view.set_tool(self.toolbar.current_tool())
        self._update_stats()

        # ── Menu bar ────────────────────────────────────────────────────
        self._build_menus()

        # ── Statusbar ───────────────────────────────────────────────────
        self.statusBar().showMessage(f"JSON : {self.json_path}")

    # ─── Menus ───────────────────────────────────────────────────────────
    def _build_menus(self) -> None:
        mb = self.menuBar()
        # File
        file_menu = mb.addMenu("&File")
        act_save = QAction("&Save", self)
        act_save.setShortcut(QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self.action_save)
        file_menu.addAction(act_save)

        act_reload = QAction("&Reload", self)
        act_reload.setShortcut("Ctrl+R")
        act_reload.triggered.connect(self.action_reload)
        file_menu.addAction(act_reload)

        file_menu.addSeparator()
        act_quit = QAction("&Quit", self)
        act_quit.setShortcut(QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # Edit
        edit_menu = mb.addMenu("&Edit")
        act_undo = QAction("&Undo", self)
        act_undo.setShortcut(QKeySequence.StandardKey.Undo)
        act_undo.triggered.connect(self.view.undo)
        edit_menu.addAction(act_undo)

        act_redo = QAction("&Redo", self)
        act_redo.setShortcut(QKeySequence.StandardKey.Redo)
        act_redo.triggered.connect(self.view.redo)
        edit_menu.addAction(act_redo)
        # Alternative redo Ctrl+Y (qui n'est pas la standard sur toutes
        # plateformes ; on l'ajoute en plus du raccourci natif Ctrl+Shift+Z)
        act_redo_alt = QAction("Redo (Ctrl+Y)", self)
        act_redo_alt.setShortcut("Ctrl+Y")
        act_redo_alt.triggered.connect(self.view.redo)
        edit_menu.addAction(act_redo_alt)

        edit_menu.addSeparator()
        act_clear = QAction("Clear &All", self)
        act_clear.triggered.connect(self.action_clear_all)
        edit_menu.addAction(act_clear)

    # ─── Actions ─────────────────────────────────────────────────────────
    def action_save(self) -> None:
        try:
            self.store.save(self.json_path)
            self.statusBar().showMessage(f"Sauvegarde -> {self.json_path}", 4000)
            print(f"[zone-editor] sauvegarde {self.json_path}")
        except Exception as exc:
            QMessageBox.warning(self, "Erreur save", f"{exc}")

    def action_reload(self) -> None:
        if self.store.is_dirty():
            ret = QMessageBox.question(
                self,
                "Recharger",
                "Modifications non sauvegardees. Recharger quand meme ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                return
        if not self.json_path.exists():
            QMessageBox.information(
                self, "Reload", f"Pas de fichier : {self.json_path}"
            )
            return
        try:
            new_store = ZoneStore.load(self.json_path)
        except Exception as exc:
            QMessageBox.warning(self, "Erreur load", f"{exc}")
            return
        self.store = new_store
        self.view.store = new_store
        self.toolbar.set_cell_size(new_store.cell_size)
        self.toolbar.set_cost_value(new_store.cost_value)
        self.view.set_cell_size(new_store.cell_size)
        self.view._refresh_all_cells_from_store()
        self._update_stats()
        self.statusBar().showMessage(f"Recharge {self.json_path}", 4000)

    def action_clear_all(self) -> None:
        if self.store.total_painted() == 0:
            return
        ret = QMessageBox.question(
            self, "Clear All",
            "Effacer toutes les cellules peintes ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if ret != QMessageBox.StandardButton.Yes:
            return
        self.store.clear_all()
        self.view._refresh_all_cells_from_store()
        self._update_stats()

    def _on_cell_size_changed(self, size: int) -> None:
        # Avertir si des cellules sont deja peintes : changer cell_size
        # ne convertit pas les coords (les cellules a (col=23, row=45)
        # ne pointent plus le meme endroit canvas). On bloque ou warn.
        if self.store.total_painted() > 0:
            ret = QMessageBox.question(
                self, "Cell size",
                "Des cellules sont deja peintes. Changer cell_size "
                "garde les indices (col, row) mais leur position canvas "
                "change. Continuer ?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                self.toolbar.set_cell_size(self.store.cell_size)
                return
        self.view.set_cell_size(size)

    def _on_cost_value_changed(self, value: int) -> None:
        self.store.cost_value = value

    def _update_stats(self) -> None:
        self.toolbar.set_stats(
            forbid=len(self.store.cells["forbid"]),
            cost=len(self.store.cells["cost"]),
            allow=len(self.store.cells["allow"]),
        )

    def closeEvent(self, event):
        if not self.store.is_dirty():
            event.accept()
            return
        ret = QMessageBox.question(
            self, "Quitter",
            "Modifications non sauvegardees. Sauvegarder avant de quitter ?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            | QMessageBox.StandardButton.Cancel,
        )
        if ret == QMessageBox.StandardButton.Yes:
            self.action_save()
            event.accept()
        elif ret == QMessageBox.StandardButton.No:
            event.accept()
        else:
            event.ignore()

    def _apply_palette(self) -> None:
        pal = self.palette()
        pal.setColor(QPalette.ColorRole.Window, QColor("#181818"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#e0e0e0"))
        self.setPalette(pal)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--json", type=Path, default=DEFAULT_JSON_PATH,
        help=f"Fichier JSON a editer (defaut: {DEFAULT_JSON_PATH})",
    )
    # argparse + Qt : on filtre nos args avant de passer le reste a QApplication
    args, qt_argv = parser.parse_known_args()

    app = QApplication([sys.argv[0]] + qt_argv)
    win = ZoneEditorWindow(json_path=args.json)
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
