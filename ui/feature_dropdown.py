"""Dropdown de sélection des fonctionnalités (remplace le bandeau de puces).

Un bouton « Fonctionnalités » ouvre un popup listant une ligne par
fonctionnalité :

    [✓] [pastille] libellé …            [↻] [🗑]

- La **case à cocher** sert à la sélection MULTI pour le surlignage : le popup
  reste ouvert pendant qu'on (dé)coche. `selection_changed(list[str])` est émis
  À CHAQUE (dé)cochage (surlignage immédiat et persistant, sans attendre la
  fermeture) ET au repli (clic dehors / re-clic bouton). Le survol d'une ligne
  émet `hover_preview(id)` (aperçu temporaire additif), "" au leave.
- Les **actions ↻ (Régénérer) / 🗑 (Supprimer)** sont posées SUR CHAQUE LIGNE et
  agissent sur CETTE fonctionnalité uniquement (indépendamment des cases
  cochées). Elles émettent `regen_requested([id])` / `delete_requested([id])`
  (liste à 1 élément, pour rester compatible avec les handlers multi du studio).
  ↻ n'existe pas si `can_regenerate=False` (fenêtre stable : 🗑 par ligne seul).

Le bouton est désactivé s'il n'y a AUCUNE fonctionnalité, ou pendant une
opération (`set_busy(True)`, qui replie aussi le popup). API alignée sur
l'ancien FeatureChipsBar (set_features / selected_ids / clear_selection /
set_busy) + signaux `regen_requested` / `delete_requested`.
"""
from PyQt6.QtCore import (
    Qt, pyqtSignal, QSize, QEvent, QObject, QPoint, QElapsedTimer,
)
from PyQt6.QtGui import QColor, QCursor, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QFrame, QHBoxLayout, QPushButton, QToolTip,
    QVBoxLayout, QWidget,
)

from .theme import (
    ColorScheme, theme_manager, feature_color, selection_bg, install_icon_hover,
    neutral_button_qss,
)
from .i18n import lang_manager, Strings
from .generation.gen_prompts import feature_combo_label, feature_combo_tooltip
from .generation.feature_model import MANUAL_ID
from . import icons as IC

_DOT_SIZE = 10
_LABEL_MAX = 60


def _dot_icon(color: str) -> QIcon:
    """Petit disque plein de la couleur de la fonctionnalité (rendu au DPR
    écran pour rester net sur affichage scalé)."""
    screen = QApplication.primaryScreen()
    dpr = screen.devicePixelRatio() if screen is not None else 1.0
    pm = QPixmap(round(_DOT_SIZE * dpr), round(_DOT_SIZE * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color)); p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(0, 0, _DOT_SIZE, _DOT_SIZE)
    p.end()
    return QIcon(pm)


class _InstantTip(QObject):
    """Affiche le tooltip du widget immédiatement au survol (sans délai Qt)."""
    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Enter and obj.toolTip():
            QToolTip.showText(
                obj.mapToGlobal(QPoint(obj.width() // 2, obj.height())),
                obj.toolTip(), obj)
        elif ev.type() == QEvent.Type.Leave:
            QToolTip.hideText()
        return False


class _RowHover(QObject):
    """Relaie enter/leave d'une ligne du popup vers hover_preview (aperçu
    temporaire). Installé sur CHAQUE widget d'une ligne (case + boutons ↻/🗑),
    tous porteurs de la propriété `feature_id`. Un Leave dont le curseur reste
    sur un widget de la MÊME ligne (même feature_id) est ignoré, sinon le
    surlignage clignoterait en passant de la case à un bouton."""
    def __init__(self, dd):
        super().__init__(dd)
        self._dd = dd

    def eventFilter(self, obj, ev):
        if ev.type() == QEvent.Type.Enter:
            self._dd.hover_preview.emit(obj.property("feature_id") or "")
        elif ev.type() == QEvent.Type.Leave:
            fid = obj.property("feature_id") or ""
            w = QApplication.widgetAt(QCursor.pos())
            if fid and w is not None and (w.property("feature_id") or "") == fid:
                return False   # curseur encore sur la même ligne
            self._dd.hover_preview.emit("")
        return False


class FeatureDropdown(QWidget):
    """Bouton « Fonctionnalités » + popup de lignes (case + actions ↻/🗑)."""

    selection_changed = pyqtSignal(list)   # list[str] au repli
    hover_preview = pyqtSignal(str)        # feature_id à l'enter, "" au leave
    regen_requested = pyqtSignal(list)     # [id] : ↻ (Régénérer) d'UNE ligne
    delete_requested = pyqtSignal(list)    # [id] : 🗑 (Supprimer) d'UNE ligne

    def __init__(self, can_regenerate: bool = True, parent=None):
        super().__init__(parent)
        self._can_regenerate = can_regenerate
        self._features_cache: list = []
        self._rows: list[tuple[str, QCheckBox]] = []   # (feature_id, checkbox)
        self._row_widgets: list[QWidget] = []          # conteneurs de ligne
        self._regen_btns: list[QPushButton] = []       # ↻ par ligne
        self._delete_btns: list[QPushButton] = []      # 🗑 par ligne
        # The `manual` row is the ONLY app-owned label of the popup: it must be
        # retranslated live (apply_lang), unlike its neighbours whose text is a
        # model-written summary. Kept as a reference like the row buttons above.
        self._manual_cb: QCheckBox | None = None
        self._busy = False
        # Anti mouse-replay: a click on the OPEN button first hides the Popup
        # (click-outside) then the SAME press is replayed to the button ->
        # _toggle_popup would reopen it. We ignore an open request that lands
        # within a few ms of the last Hide (bug review 2026-07-06 #5).
        self._hide_elapsed = QElapsedTimer()
        self._row_hover = _RowHover(self)
        self._tip = _InstantTip(self)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._btn = QPushButton(self)
        self._btn.setFixedHeight(24)
        self._btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn.setAutoDefault(False)
        self._btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._btn.clicked.connect(self._toggle_popup)
        lay.addWidget(self._btn)
        # Popup (Qt.Popup : clic dehors -> ferme automatiquement).
        self._popup = QFrame(self, Qt.WindowType.Popup)
        self._popup.setObjectName("featurePopup")
        self._pv = QVBoxLayout(self._popup)
        self._pv.setContentsMargins(6, 6, 6, 6)
        self._pv.setSpacing(2)
        self._popup.hide()
        self._popup.installEventFilter(self)   # Hide -> émission
        self.apply_lang(lang_manager.current)
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    def _make_row_action(self, icon: str, fid: str, signal) -> QPushButton:
        """Bouton icône transparent (blanc au repos, vert au survol) posé sur une
        ligne du popup ; agit sur SA fonctionnalité `fid` (émet `signal([fid])`)."""
        b = QPushButton(self._popup)
        b.setFixedSize(24, 22)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        b.setAutoDefault(False)
        b.setProperty("feature_id", fid)
        b.setProperty("variant", "bare")
        b.installEventFilter(self._tip)
        b.installEventFilter(self._row_hover)
        b._icon_hover = install_icon_hover(b, icon, 14)
        b.clicked.connect(lambda _=False, i=fid, s=signal: self._emit_row_action(s, i))
        return b

    def _emit_row_action(self, signal, fid: str) -> None:
        """Replie le popup PUIS émet l'action (la suite = dialog de confirmation
        ou génération, qui doit s'afficher sans le popup par-dessus)."""
        self._close()
        signal.emit([fid])

    # ── API ────────────────────────────────────────────────────
    def set_features(self, features) -> None:
        keep = set(self.selected_ids())
        self._features_cache = list(features)
        for row in self._row_widgets:
            row.setParent(None); row.deleteLater()
        self._rows = []
        self._row_widgets = []
        self._regen_btns = []
        self._delete_btns = []
        self._manual_cb = None   # the old rows are being deleted (deleteLater)
        s = lang_manager.current
        for idx, f in enumerate(self._features_cache):
            is_manual = f.id == MANUAL_ID
            color = feature_color(f.id)   # stable: survives reorders
            row = QWidget(self._popup)
            row.setProperty("feature_id", f.id)
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(4)
            # `manual` = hand-typed code: fixed i18n label (no prompt/summary).
            label = (s.studio_manual_feature_label if is_manual
                     else feature_combo_label(f, max_len=_LABEL_MAX))
            cb = QCheckBox(label, row)
            cb.setProperty("feature_id", f.id)
            cb.setIcon(_dot_icon(color))
            cb.setIconSize(QSize(_DOT_SIZE, _DOT_SIZE))
            cb.setChecked(f.id in keep)
            cb.setToolTip(label if is_manual else feature_combo_tooltip(f))
            cb.installEventFilter(self._row_hover)
            if is_manual:
                self._manual_cb = cb
            # Connecté APRÈS setChecked : la restauration de l'état coché lors
            # d'un rebuild ne déclenche pas d'émission parasite. (Dé)cocher émet
            # la sélection en direct -> surlignage immédiat et persistant.
            cb.toggled.connect(lambda _=False: self._emit_live_selection())
            rl.addWidget(cb, stretch=1)
            # `manual` is never regenerable (no rewritten prompt to replay) — the
            # ↻ is hidden even in a window where regeneration is enabled (#31).
            if self._can_regenerate and not is_manual:
                b_regen = self._make_row_action(IC.REFRESH, f.id, self.regen_requested)
                self._regen_btns.append(b_regen)
                rl.addWidget(b_regen)
            b_del = self._make_row_action(IC.TRASH, f.id, self.delete_requested)
            self._delete_btns.append(b_del)
            rl.addWidget(b_del)
            self._pv.addWidget(row)
            self._row_widgets.append(row)
            self._rows.append((f.id, cb))
        self._btn.setEnabled(bool(self._features_cache) and not self._busy)
        self.apply_lang(lang_manager.current)
        self.apply_theme(theme_manager.current)

    def selected_ids(self) -> list[str]:
        return [fid for fid, cb in self._rows if cb.isChecked()]

    def _emit_live_selection(self) -> None:
        """Émet la sélection à chaque (dé)cochage : le surlignage s'applique
        tout de suite et reste, sans devoir refermer le popup."""
        self.selection_changed.emit(self.selected_ids())

    def clear_selection(self) -> None:
        for _fid, cb in self._rows:
            cb.setChecked(False)
        self.selection_changed.emit([])

    def set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        self._btn.setEnabled(bool(self._features_cache) and not self._busy)
        if self._busy and self._popup.isVisible():
            self._close()

    # ── Popup ──────────────────────────────────────────────────
    def _toggle_popup(self):
        if self._popup.isVisible():
            self._close()
        elif not (self._hide_elapsed.isValid() and self._hide_elapsed.elapsed() < 200):
            # Not the replayed press that just closed the popup -> open.
            self._open()

    def _open(self):
        self._popup.adjustSize()
        self._popup.move(self._btn.mapToGlobal(QPoint(0, self._btn.height())))
        self._popup.show()

    def _close(self):
        if self._popup.isVisible():
            self._popup.hide()          # -> eventFilter(Hide) émet
        else:
            self.selection_changed.emit(self.selected_ids())

    def eventFilter(self, obj, ev):
        if obj is self._popup and ev.type() == QEvent.Type.Hide:
            # Fermeture (clic dehors OU _close) : émet la sélection cochée.
            self._hide_elapsed.restart()     # anti re-open par mouse-replay (#5)
            self.selection_changed.emit(self.selected_ids())
        return super().eventFilter(obj, ev)

    # ── Theme / lang ───────────────────────────────────────────
    def apply_lang(self, s: Strings):
        self._btn.setText(s.feature_dropdown_label + "  ▾")   # ▾
        for b in self._regen_btns:
            b.setToolTip(s.feature_action_regen)
        for b in self._delete_btns:
            b.setToolTip(s.feature_action_delete)
        # ONLY the `manual` row: the other rows show an AI-written summary, in
        # the language it was generated in — translating it would be a lie.
        if self._manual_cb is not None:
            self._manual_cb.setText(s.studio_manual_feature_label)
            self._manual_cb.setToolTip(s.studio_manual_feature_label)

    def apply_theme(self, c: ColorScheme):
        # Fond plein (main_bg) + bordure : même aspect que le bouton « Outils »
        # voisin, pour que les deux pastilles soient des frères visuels.
        # `neutral_button_qss` IS this style: filled main_bg, themed border,
        # green border + text on hover. It was hand-rolled here, which is how
        # the disabled state had drifted (text_secondary instead of the
        # disabled_text every other control uses).
        self._btn.setStyleSheet(neutral_button_qss(c, padding="0 10px"))
        # The popup keeps its own rule: this is a LIST OF ROWS, and the row
        # highlight on hover is the popup's own behaviour, not the checkbox
        # style (whose indicator comes from the application sheet).
        self._popup.setStyleSheet(f"""
            QFrame#featurePopup {{
                background: {c.sidebar_bg}; border: 1px solid {c.border};
                border-radius: 8px;
            }}
            QCheckBox {{ color: {c.text_primary}; padding: 4px 6px; }}
            QCheckBox:hover {{ background: {selection_bg(c)}; border-radius: 4px; }}
        """)
