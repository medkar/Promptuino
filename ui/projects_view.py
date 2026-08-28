"""
"Projects" view — lists user projects, by type, with actions.

Layout:
    ┌──────────────────────────────────────────────────────────────┐
    │  Mes projets                              [+ Nouveau projet] │
    │  [Tous] [Arduino] [ESP32 (grisé, bientôt)]                   │
    │  ──────────────────────────────────────────────────────────  │
    │  ┌ card ─────────────────────────────────────────────────┐   │
    │  │ 📁  Mon blink             [Arduino] [Débutant]  ⋯    │   │
    │  │      Uno · Modifié 2026-04-17                         │   │
    │  │      "Faire clignoter une LED sur la broche 13…"     │   │
    │  │      [Ouvrir] [Ouvrir le dossier]                     │   │
    │  └──────────────────────────────────────────────────────┘   │
    │  …                                                           │
    └──────────────────────────────────────────────────────────────┘
"""
from __future__ import annotations

import html
import os
import subprocess
import sys
from pathlib import Path

from PyQt6.QtCore import Qt, QSize, QEvent, pyqtSignal
from PyQt6.QtGui import QPalette, QColor, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QScrollArea, QSizePolicy, QDialog, QLineEdit, QComboBox, QMenu,
    QMessageBox,
)

from .theme import (
    ColorScheme, theme_manager, primary_button_qss, secondary_button_qss,
    install_icon_hover, combo_qss, filter_pill_qss, icon_button_qss,
    neutral_button_qss, input_qss,
)
from .i18n import lang_manager, Strings
from .message_box import ask_yes_no
from . import icons as IC
from .project_manager import (
    Project, ProjectType, ProjectManager, project_manager,
    TYPE_LABELS, is_name_valid, Function,
)
from .board_manager import COMING_SOON_ENVS
# Color palette for features: moved to theme.py (shared with the Studio
# feature chips bar).
from .theme import FUNCTION_PALETTE


# Number of items shown in the card when the section is collapsed.
# Beyond that, a chevron allows expanding to see all features.
_CARD_FUNCTIONS_COLLAPSED = 3

# Fixed width of the left column (info + actions) so the Features
# column starts at the same X on every project card, regardless
# of the prompt or name length.
_CARD_LEFT_WIDTH = 350


def _function_display_name(fn: Function) -> str:
    """Display name of a function: custom if set, otherwise auto.

    Follows the Studio convention: a non-empty Function.name takes priority
    over "Fonctionnalite N" derived from the id (f1 -> 1, f12 -> 12).
    """
    name = (getattr(fn, "name", "") or "").strip()
    if name:
        return name
    fid = fn.id or ""
    n = fid[1:] if fid.startswith("f") else fid
    return lang_manager.current.studio_function_name_fmt.format(n=n or "?")


# ─── Filter display order ────────────────────────────────────────────────────
_FILTER_ORDER: list[ProjectType] = [
    ProjectType.ARDUINO, ProjectType.ESP32,   # ESP32 = grayed out (coming soon)
]


def _reveal_folder(path: Path) -> None:
    """Open the folder in the native file explorer."""
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
#  Filter button (simple segmented control)
# ─────────────────────────────────────────────────────────────────────────────
class _FilterButton(QPushButton):
    def __init__(self, text: str, parent=None, coming_soon: bool = False):
        super().__init__(text, parent)
        self._coming_soon = coming_soon
        # Coming soon (ESP32): not selectable, but stays ENABLED so the
        # "Coming soon" tooltip shows on hover (a disabled
        # widget does not show a tooltip).
        self.setCheckable(not coming_soon)
        self.setCursor(Qt.CursorShape.PointingHandCursor if not coming_soon
                       else Qt.CursorShape.ArrowCursor)
        self.setFixedHeight(30)
        self.apply_theme(theme_manager.current)

    def apply_theme(self, c: ColorScheme):
        # Filter pill (spec §3): checked = nav_active + signal_ok border;
        # unchecked = transparent + text_primary + border border; radius 4.
        #
        # ⚠️ `padding="4px 14px"` and not the helper's default `3px 12px`:
        # this bar's pills have always been the roomier ones, and aligning
        # them would widen each by 4 px (measured `sizeHint`) -- a redesign,
        # which TODO #50 forbids.
        self.setStyleSheet(filter_pill_qss(
            c, checked=self.isChecked(), disabled=self._coming_soon,
            padding="4px 14px"))


# ─────────────────────────────────────────────────────────────────────────────
#  Dialog « + Nouveau projet »  —  name + type
# ─────────────────────────────────────────────────────────────────────────────
class _NewProjectDialog(QDialog):
    def __init__(self, parent=None, default_type: ProjectType = ProjectType.ARDUINO):
        super().__init__(parent)
        s = lang_manager.current
        self.setWindowTitle(s.projects_new_dialog_title)
        self.setModal(True)
        self.setFixedWidth(420)

        c = theme_manager.current
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        self._lbl_name = QLabel(s.projects_new_dialog_prompt)
        self._edit = QLineEdit()
        self._edit.setPlaceholderText("blink_led")
        self._edit.setMaxLength(80)
        self._edit.setFixedHeight(32)

        self._lbl_type = QLabel(s.projects_new_type_label)
        self._combo = QComboBox()
        self._combo.setFixedHeight(32)
        self._combo.setCursor(Qt.CursorShape.PointingHandCursor)
        for t in _FILTER_ORDER:
            self._combo.addItem(TYPE_LABELS[t], t.value)
            if t.value in COMING_SOON_ENVS:
                # ESP32 "coming soon": grayed-out non-selectable item +
                # tooltip (combo item tooltips show in the drop-down
                # list even when the item is disabled).
                item = self._combo.model().item(self._combo.count() - 1)
                if item is not None:
                    item.setEnabled(False)
                    item.setToolTip(lang_manager.current.board_coming_soon)
        idx = self._combo.findData(default_type.value)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)

        self._err = QLabel("")
        self._err.setStyleSheet(f"color: {c.signal_error}; font-size: 9pt;")
        self._err.setVisible(False)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._btn_cancel = QPushButton(s.projects_cancel)
        self._btn_create = QPushButton(s.projects_create)
        self._btn_cancel.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_create.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_cancel.setFixedHeight(32)
        self._btn_create.setFixedHeight(32)
        # Entrée doit CRÉER, jamais annuler. « Annuler » est ajouté au layout
        # avant « Créer », donc sans ceci c'est LUI que Qt promeut bouton par
        # défaut : sur un nom invalide (« Réveil », « l'alarme », « v1.2 » —
        # _NAME_RE refuse accents, apostrophes et points), `_on_ok` renonce
        # sans `accept()`, l'événement Return poursuit sa route jusqu'au
        # bouton par défaut, et la modale se ferme sans que le message
        # d'erreur ait été vu une seule fois.
        self._btn_cancel.setAutoDefault(False)
        self._btn_cancel.setDefault(False)
        self._btn_create.setAutoDefault(True)
        self._btn_create.setDefault(True)
        self._btn_cancel.clicked.connect(self.reject)
        self._btn_create.clicked.connect(self._on_ok)
        self._edit.returnPressed.connect(self._on_ok)
        btn_row.addWidget(self._btn_cancel)
        btn_row.addWidget(self._btn_create)

        root.addWidget(self._lbl_name)
        root.addWidget(self._edit)
        root.addWidget(self._lbl_type)
        root.addWidget(self._combo)
        root.addWidget(self._err)
        root.addSpacing(4)
        root.addLayout(btn_row)

        self._apply_theme(c)

    def _apply_theme(self, c: ColorScheme):
        # ⚠️ CONTAINER SCOPE: this sheet sits on the QDialog, so its QLineEdit
        # rule reaches EVERY text field of this modal, present and future.
        # `input_qss` is therefore appended rather than set on the field: the
        # scope is unchanged, only the recipe stops being a hand-written copy.
        #
        # The local copy had no `:hover`, so the field was the one control of
        # the modal that did NOT tint green under the cursor while its
        # neighbours did. Switching to the helper RESTORES that hover — a
        # deliberate behaviour change (step 2 of TODO #50), not a silent one.
        self.setStyleSheet(f"""
            QDialog {{ background-color: {c.main_bg}; }}
            QLabel  {{ color: {c.text_primary}; font-size: 10pt; }}
        """ + input_qss(c, padding="4px 8px"))
        # Board type: same style as the Board's "Model" field but
        # WITHOUT an arrow (arrow=False) — a single click on the field opens the list.
        self._combo.setStyleSheet(combo_qss(c, arrow=False))
        # "Cancel" = secondary (outlined), "Create" = primary (filled),
        # agreed centralized style (green on hover). cf theme.*_button_qss.
        self._btn_cancel.setStyleSheet(secondary_button_qss(c, padding="4px 14px"))
        self._btn_create.setStyleSheet(primary_button_qss(c, padding="4px 14px"))

    def _show_err(self, msg: str):
        self._err.setText(msg)
        self._err.setVisible(True)

    def _on_ok(self):
        name = self._edit.text().strip()
        s = lang_manager.current
        if not is_name_valid(name):
            self._show_err(s.projects_invalid_name)
            return
        ptype = ProjectType(self._combo.currentData())
        # Collision: suffix (1), (2)... automatically rather than
        # blocking. The final name is resolved at create() time.
        self._name = name
        self._ptype = ptype
        self.accept()

    def result_values(self) -> tuple[str, ProjectType]:
        return self._name, self._ptype


# ─────────────────────────────────────────────────────────────────────────────
#  Project card
# ─────────────────────────────────────────────────────────────────────────────
class ProjectCard(QFrame):
    open_requested      = pyqtSignal(object)
    delete_requested    = pyqtSignal(object)
    duplicate_requested = pyqtSignal(object)
    rename_requested    = pyqtSignal(object)
    # Click on the card body (outside child buttons). ProjectsView
    # interprets the modifiers to handle Ctrl/Shift-click selection.
    card_clicked        = pyqtSignal(object, Qt.KeyboardModifier)

    def __init__(self, project: Project, parent=None):
        super().__init__(parent)
        self._project = project
        self._selected = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setAutoFillBackground(True)
        self._build()
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    @property
    def project(self) -> Project:
        return self._project

    def is_selected(self) -> bool:
        return self._selected

    def set_selected(self, selected: bool) -> None:
        if self._selected == selected:
            return
        self._selected = selected
        self.apply_theme(theme_manager.current)

    def _build(self):
        # Root = 2 columns: info + actions on the left, the features
        # list on the right. The card stays a single QFrame so that
        # a click on any area selects the project.
        root_row = QHBoxLayout(self)
        root_row.setContentsMargins(14, 12, 14, 12)
        root_row.setSpacing(12)

        # Fixed width so the Features column starts at the same
        # X on every card. A stretch at the end of root_row pushes the
        # ⋯ menu to the far right of the card.
        left_container = QWidget()
        left_container.setFixedWidth(_CARD_LEFT_WIDTH)
        left_col = QVBoxLayout(left_container)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(6)
        root_row.addWidget(left_container, stretch=0)

        root = left_col  # alias to minimize the diff with the existing code

        # ── Row 1: icon + name + badges + menu ────────────────
        row1 = QHBoxLayout()
        row1.setSpacing(10)

        self._icon = QLabel()
        self._icon.setFixedSize(QSize(22, 22))
        row1.addWidget(self._icon)

        self._lbl_name = QLabel(self._project.name)
        self._lbl_name.setStyleSheet("font-size: 11pt; font-weight: 700;")
        row1.addWidget(self._lbl_name)

        row1.addSpacing(6)

        self._badge_type = QLabel(TYPE_LABELS.get(self._project.type, ""))
        self._badge_mode = QLabel(self._mode_label())
        for b in (self._badge_type, self._badge_mode):
            b.setFixedHeight(20)
            b.setContentsMargins(8, 0, 8, 0)
            b.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row1.addWidget(self._badge_type)
        row1.addWidget(self._badge_mode)

        row1.addStretch()

        # The menu button is moved to the far right of the card (after the
        # Features column), so it is no longer added to row1.
        self._btn_menu = QPushButton()
        self._btn_menu.setFixedSize(28, 28)
        self._btn_menu.setIconSize(QSize(16, 16))
        self._btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_menu.setToolTip(lang_manager.current.projects_actions_tooltip)
        self._btn_menu.clicked.connect(self._show_menu)
        # « … » icon: gray at rest, GREEN on hover (follows the theme).
        install_icon_hover(self._btn_menu, IC.MORE_HORIZONTAL, 16,
                           normal_role="text_secondary")

        root.addLayout(row1)

        # ── Row 2: board + date ───────────────────────────────
        self._lbl_sub = QLabel(self._subtitle())
        self._lbl_sub.setStyleSheet("font-size: 9pt;")
        root.addWidget(self._lbl_sub)

        # ── Row 3: prompt preview (truncated) ─────────────────
        self._lbl_prompt = QLabel(self._prompt_preview())
        self._lbl_prompt.setWordWrap(True)
        self._lbl_prompt.setStyleSheet("font-size: 9pt; font-style: italic;")
        if self._lbl_prompt.text():
            root.addWidget(self._lbl_prompt)

        # ── Row 4: actions ────────────────────────────────────
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self._btn_open = QPushButton(lang_manager.current.projects_open)
        self._btn_open.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_open.setFixedHeight(30)
        self._btn_open.clicked.connect(lambda: self.open_requested.emit(self._project))
        actions.addWidget(self._btn_open)

        self._btn_folder = QPushButton(lang_manager.current.projects_open_folder)
        self._btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_folder.setFixedHeight(30)
        self._btn_folder.clicked.connect(lambda: _reveal_folder(self._project.path))
        actions.addWidget(self._btn_folder)

        actions.addStretch()
        root.addLayout(actions)

        # ── Right column: features list (collapsible) ─
        # Hidden if the project has no function yet (no first gen).
        # Beyond _CARD_FUNCTIONS_COLLAPSED, a chevron allows expanding.
        self._functions_expanded = False
        self._fn_item_labels: list[QLabel] = []

        self._functions_section = QWidget()
        self._functions_section.setObjectName("FunctionsSection")
        self._functions_section.setMinimumWidth(180)
        fn_root = QVBoxLayout(self._functions_section)
        fn_root.setContentsMargins(0, 0, 0, 0)
        fn_root.setSpacing(2)

        self._lbl_fn_title = QLabel()
        fn_root.addWidget(self._lbl_fn_title)

        self._fn_items_host = QWidget()
        self._fn_items_layout = QVBoxLayout(self._fn_items_host)
        self._fn_items_layout.setContentsMargins(0, 4, 0, 0)
        self._fn_items_layout.setSpacing(4)
        fn_root.addWidget(self._fn_items_host)

        # Collapse/expand chevron placed below the items list, aligned
        # left — visible only when n > _CARD_FUNCTIONS_COLLAPSED.
        self._btn_fn_toggle = QPushButton()
        self._btn_fn_toggle.setFixedSize(22, 22)
        self._btn_fn_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_fn_toggle.setIconSize(QSize(16, 16))
        self._btn_fn_toggle.clicked.connect(self._toggle_functions_expanded)
        fn_root.addWidget(
            self._btn_fn_toggle, alignment=Qt.AlignmentFlag.AlignHCenter,
        )
        fn_root.addStretch()

        # Top alignment so the banner starts at the height
        # of the name, not vertically centered relative to the left column.
        root_row.addWidget(
            self._functions_section, stretch=0, alignment=Qt.AlignmentFlag.AlignTop,
        )
        # Stretch to fill the space between the Features column and
        # the ⋯ menu, which must stay pinned to the far right.
        root_row.addStretch(1)
        # ⋯ menu button at the far right of the card, top-aligned to stay
        # at the height of the name and badges.
        root_row.addWidget(
            self._btn_menu, stretch=0, alignment=Qt.AlignmentFlag.AlignTop,
        )
        self._rebuild_functions_list()

    # ── Dynamic labels ────────────────────────────────────────
    def _mode_label(self) -> str:
        s = lang_manager.current
        return {
            "beginner":     s.mode_beginner,
            "intermediate": s.mode_intermediate,
            "advanced":     s.mode_advanced,
        }.get(self._project.mode, s.mode_beginner)

    def _subtitle(self) -> str:
        s = lang_manager.current
        parts: list[str] = []
        board = self._project.board_model or self._project.board_env
        parts.append(board if board else s.projects_board_unknown)
        if self._project.updated_at:
            parts.append(f"{s.projects_last_modified} {self._project.updated_at[:10]}")
        return "  ·  ".join(parts)

    def _prompt_preview(self) -> str:
        p = (self._project.last_prompt or "").strip()
        if not p:
            return ""
        p = p.replace("\n", " ")
        return (p[:110] + "…") if len(p) > 110 else p

    # ── Features section ──────────────────────────────────
    def _rebuild_functions_list(self):
        """(Re)create the function labels and update the header + chevron.

        Applies visibility according to `_functions_expanded`: collapsed => max
        `_CARD_FUNCTIONS_COLLAPSED` items; expanded => all. Hides the whole
        section if the project has no registered function.
        """
        # Purge the old labels (cases: i18n changed, or theoretical rebuild).
        while self._fn_items_layout.count():
            it = self._fn_items_layout.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        self._fn_item_labels = []

        fns = list(self._project.functions or [])
        n = len(fns)
        if n == 0:
            self._functions_section.setVisible(False)
            return
        self._functions_section.setVisible(True)

        s = lang_manager.current
        # Header = "Features (N)"
        self._lbl_fn_title.setText(f"{s.studio_functions_title} ({n})")

        # Shown limit
        limit = n if self._functions_expanded else _CARD_FUNCTIONS_COLLAPSED
        shown = fns[:limit]
        for idx, fn in enumerate(shown):
            color = (fn.color or "").strip() or FUNCTION_PALETTE[idx % len(FUNCTION_PALETTE)]
            lbl = QLabel(_function_display_name(fn))
            lbl.setProperty("fn_color", color)
            # Tooltip = the function's current prompt, truncated to stay
            # readable, wrapped in HTML to force multi-line wrapping.
            prompt = (fn.current_prompt or "").strip()
            if prompt:
                preview = (prompt[:300] + "…") if len(prompt) > 300 else prompt
                lbl.setToolTip(
                    f"<div style='max-width:360px'>{html.escape(preview)}</div>"
                )
            self._fn_items_layout.addWidget(lbl)
            self._fn_item_labels.append(lbl)

        # Chevron visible only if the list exceeds the collapsed limit.
        show_toggle = n > _CARD_FUNCTIONS_COLLAPSED
        self._btn_fn_toggle.setVisible(show_toggle)
        # Refresh the icon (depends on the current theme + collapsed/expanded state).
        self._refresh_fn_toggle_icon(theme_manager.current)
        # Refresh the label colors according to the current theme.
        self._apply_fn_items_color(theme_manager.current)

    def _toggle_functions_expanded(self):
        self._functions_expanded = not self._functions_expanded
        self._rebuild_functions_list()

    def _refresh_fn_toggle_icon(self, c: ColorScheme):
        if self._functions_expanded:
            self._btn_fn_toggle.setIcon(
                IC.make_icon(IC.CHEVRON_UP, c.text_secondary, 14)
            )
        else:
            self._btn_fn_toggle.setIcon(
                IC.make_icon(IC.CHEVRON_DOWN, c.text_secondary, 14)
            )

    def _apply_fn_items_color(self, c: ColorScheme):
        self._lbl_fn_title.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 10pt; font-weight: 600;"
            "background-color: transparent;"
        )
        # Pills: background = project card color (stands out from the box
        # background) + signature left border = Studio's Function.color.
        for lbl in self._fn_item_labels:
            fn_color = lbl.property("fn_color") or c.accent
            lbl.setStyleSheet(f"""
                QLabel {{
                    color: {c.text_primary};
                    font-size: 10pt;
                    background-color: {c.nav_hover_bg};
                    border-left: 4px solid {fn_color};
                    border-top-left-radius: 3px;
                    border-bottom-left-radius: 3px;
                    border-top-right-radius: 4px;
                    border-bottom-right-radius: 4px;
                    padding: 3px 8px;
                }}
            """)
        # Chevron: same icon-button recipe as the card's « … », with its own
        # radius and a plain `border` tint (it sits on the card, not on it).
        self._btn_fn_toggle.setStyleSheet(
            icon_button_qss(c, radius=4, hover_bg=c.border))

    # ── Events ───────────────────────────────────────────────────
    def mousePressEvent(self, e):
        # A click on a child button does not reach here (Qt accept()s it).
        # We emit to ProjectsView and accept() the event: without this,
        # it would bubble up to _list_host, whose eventFilter would immediately
        # clear the selection we just set.
        if e.button() == Qt.MouseButton.LeftButton:
            self.card_clicked.emit(self._project, e.modifiers())
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.open_requested.emit(self._project)
        super().mouseDoubleClickEvent(e)

    def _show_menu(self):
        s = lang_manager.current
        menu = QMenu(self)
        act_rename = menu.addAction(s.projects_rename)
        act_dup    = menu.addAction(s.projects_duplicate)
        menu.addSeparator()
        act_del    = menu.addAction(s.projects_delete)
        chosen = menu.exec(self._btn_menu.mapToGlobal(self._btn_menu.rect().bottomLeft()))
        if chosen == act_rename:
            self.rename_requested.emit(self._project)
        elif chosen == act_dup:
            self.duplicate_requested.emit(self._project)
        elif chosen == act_del:
            self.delete_requested.emit(self._project)

    # ── i18n / theme ─────────────────────────────────────────────
    def apply_lang(self, _s: Strings):
        self._badge_mode.setText(self._mode_label())
        self._lbl_sub.setText(self._subtitle())
        self._btn_open.setText(_s.projects_open)
        self._btn_folder.setText(_s.projects_open_folder)
        self._btn_menu.setToolTip(_s.projects_actions_tooltip)
        # Le chevron « déplier les fonctionnalités » était le seul bouton
        # icône-seule de cette carte sans infobulle — juste à côté du « ⋯ »
        # qui en a une depuis toujours, ce qui rend l'oubli visible.
        self._btn_fn_toggle.setToolTip(_s.tip_card_functions)
        # The auto names ("Feature N") depend on the
        # current language: we rebuild the list to reflect them.
        self._rebuild_functions_list()

    def apply_theme(self, c: ColorScheme):
        # Selection: we replace the background/border with an accented variant.
        # Border thickness unchanged (1px) to avoid any visual shift
        # between normal, hover and selected states.
        # Card = surface (spec §3); signal_ok border if selected, otherwise
        # border. Hover: text_secondary border (or signal_ok if already selected).
        bg = c.surface
        border = c.signal_ok if self._selected else c.border
        # Hover: GREEN border (user request), not gray.
        hover_border = c.signal_ok
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(bg))
        self.setPalette(p)
        self.setStyleSheet(f"""
            ProjectCard {{
                background-color: {bg};
                border: 1px solid {border};
                border-radius: 6px;
            }}
            ProjectCard:hover {{
                border: 1px solid {hover_border};
            }}
        """)
        self._icon.setPixmap(IC.make_icon(IC.FOLDER, c.accent, 22).pixmap(22, 22))
        self._lbl_name.setStyleSheet(f"color: {c.text_primary}; font-size: 11pt; font-weight: 700;")
        self._lbl_sub.setStyleSheet(f"color: {c.text_secondary}; font-size: 9pt;")
        if hasattr(self, "_lbl_prompt"):
            self._lbl_prompt.setStyleSheet(f"color: {c.text_secondary}; font-size: 9pt; font-style: italic;")
        # Neutral badge (spec §3): text_secondary text + border, radius 3.
        badge_css = f"""
            QLabel {{
                color: {c.text_secondary};
                border: 1px solid {c.border};
                border-radius: 3px;
                padding: 2px 7px;
                font-size: 8pt; font-weight: 600;
            }}
        """
        self._badge_type.setStyleSheet(badge_css)
        self._badge_mode.setStyleSheet(badge_css)
        # « … »: background on hover; the icon turns GREEN (handled by
        # install_icon_hover set in _build — QSS does not recolor a QIcon).
        self._btn_menu.setStyleSheet(icon_button_qss(c))
        # « Ouvrir le dossier » (filled, green border+text on hover) and
        # « Ouvrir » (filled, background turns green on hover) are the app's
        # neutral and primary buttons — they were written out by hand here.
        #
        # Both helpers additionally declare a `:disabled` the local blocks did
        # not have. Neither button is ever disabled in this file (no
        # `setEnabled` on them), so the difference is latent today; it is
        # nonetheless a real addition, not a no-op.
        # `primary_button_qss` also draws a 1px border in `btn_primary_bg` —
        # the very colour of the background, hence invisible.
        self._btn_open.setStyleSheet(
            primary_button_qss(c, font_pt=9, padding="4px 14px"))
        self._btn_folder.setStyleSheet(
            neutral_button_qss(c, bg=c.surface, font_pt=9,
                               padding="4px 12px", radius=6))
        # Features section: colors follow the current theme.
        self._apply_fn_items_color(c)
        self._refresh_fn_toggle_icon(c)


# ─────────────────────────────────────────────────────────────────────────────
#  Main view
# ─────────────────────────────────────────────────────────────────────────────
class ProjectsView(QWidget):
    """List of user projects, filterable by type."""

    open_project_requested = pyqtSignal(object)   # emits a Project
    project_deleted        = pyqtSignal(object)   # emits the deleted Project
    project_renamed        = pyqtSignal(str, object)  # (old_path, updated Project)

    def __init__(self, parent=None, pm: ProjectManager | None = None):
        super().__init__(parent)
        self._pm = pm or project_manager
        self._filter: ProjectType | None = None
        # Multi-selection: Ctrl/Shift-click adds/extends the selection.
        # _cards keeps the display order (needed for the Shift-range).
        # _anchor_path is the last anchor point for the Shift-range
        # (stores the path string — more stable than a Project reference
        # after a refresh() that rebuilds the objects).
        self._cards: list[ProjectCard] = []
        self._selected_paths: set[str]  = set()
        self._anchor_path: str | None   = None
        self._build()
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

        # Keyboard shortcuts: Delete on the selection, Escape to clear.
        # Scope: WidgetWithChildren — Delete/Escape must only fire
        # with focus inside the Projects view (not from Studio/Board/etc.).
        self._sc_delete = QShortcut(QKeySequence.StandardKey.Delete, self)
        self._sc_delete.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sc_delete.activated.connect(self._on_bulk_delete)
        self._sc_escape = QShortcut(QKeySequence(Qt.Key.Key_Escape), self)
        self._sc_escape.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self._sc_escape.activated.connect(self._clear_selection)
        # Without focusPolicy, the root QScrollArea/QWidget does not grab focus
        # after a click on a card — the shortcuts would stay inactive.
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.refresh()

    # ── Construction ─────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # ── Header: title + "+ Nouveau projet" button ───────────
        header = QHBoxLayout()
        header.setSpacing(10)

        self._lbl_title = QLabel(lang_manager.current.projects_title)
        self._lbl_title.setStyleSheet("font-size: 16pt; font-weight: 700;")
        header.addWidget(self._lbl_title)
        header.addStretch()

        self._btn_new = QPushButton(f"  {lang_manager.current.projects_new}")
        self._btn_new.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_new.setFixedHeight(34)
        self._btn_new.setIconSize(QSize(16, 16))
        self._btn_new.clicked.connect(self._on_new)
        header.addWidget(self._btn_new)

        root.addLayout(header)

        # ── Filters ──────────────────────────────────────────────
        filters = QHBoxLayout()
        filters.setSpacing(6)
        self._filter_btns: dict[ProjectType | None, _FilterButton] = {}
        btn_all = _FilterButton(lang_manager.current.projects_filter_all)
        btn_all.setChecked(True)
        btn_all.clicked.connect(lambda: self._on_filter(None))
        filters.addWidget(btn_all)
        self._filter_btns[None] = btn_all
        for t in _FILTER_ORDER:
            soon = t.value in COMING_SOON_ENVS
            b = _FilterButton(TYPE_LABELS[t], coming_soon=soon)
            if soon:
                b.setToolTip(lang_manager.current.board_coming_soon)
            else:
                b.clicked.connect(lambda _, tt=t: self._on_filter(tt))
            filters.addWidget(b)
            self._filter_btns[t] = b
        filters.addStretch()
        # Selection trash icon: ON THE SAME ROW as the tabs (on the
        # right), hidden as long as no project is selected. Since a
        # hidden widget takes no space, showing it no longer creates an
        # extra row -> the content no longer shifts down (user
        # request). Height 30 = that of the tabs (zero shift).
        self._btn_sel_delete = QPushButton()
        self._btn_sel_delete.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_sel_delete.setFixedSize(32, 30)
        self._btn_sel_delete.setIconSize(QSize(18, 18))
        self._btn_sel_delete.setToolTip(lang_manager.current.projects_delete_selection)
        self._btn_sel_delete.clicked.connect(self._on_bulk_delete)
        # Icon swap on hover (QSS :hover cannot re-tint a QIcon):
        # see the eventFilter extension below.
        self._btn_sel_delete.installEventFilter(self)
        self._btn_sel_delete.setVisible(False)
        filters.addWidget(self._btn_sel_delete)
        root.addLayout(filters)

        # ── Scroll area + cards container ───────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._list_host = QWidget()
        self._list_host.setObjectName("projectsListHost")
        self._list_layout = QVBoxLayout(self._list_host)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(10)
        self._list_layout.addStretch()
        # Clicking in the empty space between/below the cards deselects everything.
        # ProjectCards intercept their own clicks (mousePressEvent
        # accept()) — only clicks outside a card bubble up here.
        self._list_host.installEventFilter(self)

        self._scroll.setWidget(self._list_host)
        # The QScrollArea viewport can receive clicks below the last
        # card if the content does not fill the whole height.
        self._scroll.viewport().installEventFilter(self)
        root.addWidget(self._scroll, stretch=1)

        # ── Empty state ──────────────────────────────────────────
        self._empty = QWidget()
        self._empty.setObjectName("projectsEmpty")
        e_layout = QVBoxLayout(self._empty)
        e_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e_layout.setSpacing(6)
        self._empty_icon = QLabel()
        self._empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_title = QLabel(lang_manager.current.projects_empty)
        self._empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_title.setStyleSheet("font-size: 12pt; font-weight: 600;")
        self._empty_hint = QLabel(lang_manager.current.projects_empty_hint)
        self._empty_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_hint.setStyleSheet("font-size: 10pt;")
        e_layout.addStretch()
        e_layout.addWidget(self._empty_icon)
        e_layout.addWidget(self._empty_title)
        e_layout.addWidget(self._empty_hint)
        e_layout.addStretch()
        self._empty.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._empty.setVisible(False)
        root.addWidget(self._empty, stretch=1)

    # ── Public API ───────────────────────────────────────────────
    def refresh(self):
        """Reload the list from disk and rebuild the cards."""
        # Purge the current cards
        while self._list_layout.count() > 1:
            item = self._list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self._cards = []
        projects = self._pm.list_projects(self._filter)
        self._empty.setVisible(not projects)
        self._scroll.setVisible(bool(projects))
        # The selection is kept by path across refreshes — we clean it
        # of entries that no longer reference an existing project (deletion,
        # filter change…).
        existing_paths = {str(p.path) for p in projects}
        self._selected_paths &= existing_paths
        if self._anchor_path not in existing_paths:
            self._anchor_path = None
        for proj in projects:
            card = ProjectCard(proj)
            card.open_requested.connect(self.open_project_requested.emit)
            card.delete_requested.connect(self._on_delete)
            card.duplicate_requested.connect(self._on_duplicate)
            card.rename_requested.connect(self._on_rename)
            card.card_clicked.connect(self._on_card_clicked)
            if str(proj.path) in self._selected_paths:
                card.set_selected(True)
            self._list_layout.insertWidget(self._list_layout.count() - 1, card)
            self._cards.append(card)
        self._update_selection_bar()

    # ── Multiple selection ───────────────────────────────────────
    def mousePressEvent(self, e):
        # Left click anywhere in the view = deselection.
        # The trash button, the cards and the other QPushButtons absorb
        # their own click (explicit accept() or Qt default), so only
        # a click "in the empty space" (margins, gaps between widgets, empty
        # title area) bubbles up here.
        if e.button() == Qt.MouseButton.LeftButton:
            self._clear_selection()
        super().mousePressEvent(e)

    def showEvent(self, e):
        # App-wide filter: lets us catch clicks outside the view
        # (sidebar, topbar, other views) to clear the selection. Installed
        # only when the view is shown to limit event traffic.
        super().showEvent(e)
        app = QApplication.instance()
        if app is not None:
            app.installEventFilter(self)

    def hideEvent(self, e):
        app = QApplication.instance()
        if app is not None:
            app.removeEventFilter(self)
        super().hideEvent(e)

    def eventFilter(self, obj, ev):
        # WARNING: this filter starts being called AS SOON AS the 1st widget
        # does installEventFilter(self) — potentially in the middle of _build(),
        # before _list_host/_scroll exist. The getattr(..., None) calls avoid
        # an AttributeError (which caused a C-level crash at startup).
        btn_sel = getattr(self, "_btn_sel_delete", None)
        if obj is btn_sel and btn_sel is not None:
            if ev.type() == QEvent.Type.Enter and hasattr(self, "_btn_sel_delete_icon_hover"):
                btn_sel.setIcon(self._btn_sel_delete_icon_hover)
            elif ev.type() == QEvent.Type.Leave and hasattr(self, "_btn_sel_delete_icon_normal"):
                btn_sel.setIcon(self._btn_sel_delete_icon_normal)
            return super().eventFilter(obj, ev)

        # Left click in the empty area of the list (between cards, below the
        # last one, or directly on the scroll viewport) = clears the
        # selection. ProjectCards intercept their own clicks so
        # only the "outside a card" case reaches this filter.
        list_host = getattr(self, "_list_host", None)
        scroll    = getattr(self, "_scroll", None)
        viewport  = scroll.viewport() if scroll is not None else None
        if (
            obj is not None
            and obj in (list_host, viewport)
            and ev.type() == QEvent.Type.MouseButtonPress
            and ev.button() == Qt.MouseButton.LeftButton
        ):
            self._clear_selection()
            return super().eventFilter(obj, ev)

        # Left click OUTSIDE the Projects view (sidebar, topbar, other view) =
        # deselection. Active only thanks to the app-filter (installed in
        # showEvent). The isAncestorOf test excludes the whole subtree
        # of the view: cards, buttons, bars, viewport — those already have
        # their own logic (or are handled by mousePressEvent above).
        if (
            ev.type() == QEvent.Type.MouseButtonPress
            and ev.button() == Qt.MouseButton.LeftButton
            and isinstance(obj, QWidget)
            and obj is not self
            and not self.isAncestorOf(obj)
        ):
            self._clear_selection()
        return super().eventFilter(obj, ev)

    def _on_card_clicked(self, project: Project, modifiers: Qt.KeyboardModifier):
        """Click on a card — same pattern as FunctionsPanel:

        - Plain click: single selection (replaces). Re-clicking the card
          that is already the only one selected deselects it.
        - Ctrl+click : toggles membership in the selection (multi).
        - Shift+click: selects the range [anchor, this card] (replaces).
        """
        ctrl  = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)
        # Grab focus so that Delete/Escape apply to the view.
        self.setFocus()
        path = str(project.path)
        paths_in_order = [str(c.project.path) for c in self._cards]

        if shift and self._anchor_path in paths_in_order:
            try:
                a = paths_in_order.index(self._anchor_path)
                b = paths_in_order.index(path)
            except ValueError:
                self._selected_paths = {path}
                self._anchor_path = path
            else:
                lo, hi = (a, b) if a <= b else (b, a)
                self._selected_paths = set(paths_in_order[lo:hi + 1])
                # The anchor does not move on a shift+click: the range can
                # be re-extended by clicking higher or lower.
        elif ctrl:
            if path in self._selected_paths:
                self._selected_paths.discard(path)
            else:
                self._selected_paths.add(path)
            self._anchor_path = path
        else:
            # Plain click: toggle if already the only one selected, otherwise replace.
            if self._selected_paths == {path}:
                self._selected_paths.clear()
                self._anchor_path = None
            else:
                self._selected_paths = {path}
                self._anchor_path = path
        self._sync_cards_selected()
        self._update_selection_bar()

    def _clear_selection(self):
        if not self._selected_paths:
            return
        self._selected_paths.clear()
        self._anchor_path = None
        self._sync_cards_selected()
        self._update_selection_bar()

    def _sync_cards_selected(self):
        for card in self._cards:
            card.set_selected(str(card.project.path) in self._selected_paths)

    def _update_selection_bar(self):
        self._btn_sel_delete.setVisible(bool(self._selected_paths))

    def _on_bulk_delete(self):
        if not self._selected_paths:
            return
        s = lang_manager.current
        # We keep the Projects via the current cards — more reliable
        # than a lookup on disk after deletion.
        targets = [c.project for c in self._cards if str(c.project.path) in self._selected_paths]
        if not targets:
            return
        if not ask_yes_no(self, s.projects_delete_bulk_title,
                          s.projects_delete_bulk_msg.format(n=len(targets))):
            return
        errors: list[str] = []
        for proj in targets:
            try:
                self._pm.delete(proj)
                self.project_deleted.emit(proj)
            except Exception as e:
                errors.append(f"{proj.name} : {e}")
        self._selected_paths.clear()
        self._anchor_path = None
        self.refresh()
        if errors:
            QMessageBox.warning(self, s.projects_delete, "\n".join(errors))

    # ── Slots ────────────────────────────────────────────────────
    def _on_filter(self, t: ProjectType | None):
        if self._filter == t:
            # re-check the current button (prevents it from unchecking)
            btn = self._filter_btns.get(t)
            if btn:
                btn.setChecked(True)
                btn.apply_theme(theme_manager.current)
            return
        self._filter = t
        for key, btn in self._filter_btns.items():
            btn.setChecked(key == t)
            btn.apply_theme(theme_manager.current)
        self.refresh()

    def _on_new(self):
        default = self._filter if self._filter else ProjectType.ARDUINO
        dlg = _NewProjectDialog(self, default_type=default)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, ptype = dlg.result_values()
        from .project_manager import type_dir
        base_dir = type_dir(ptype)
        base_dir.mkdir(parents=True, exist_ok=True)
        name = self._pm.unique_name(name, base_dir)
        try:
            proj = self._pm.create(name, ptype, initial_code=lang_manager.editor_template())
        except Exception as e:
            QMessageBox.warning(self, lang_manager.current.projects_new_dialog_title, str(e))
            return
        self.refresh()
        self.open_project_requested.emit(proj)

    def _on_delete(self, project: Project):
        s = lang_manager.current
        ans = ask_yes_no(
            self, s.projects_delete_confirm_title,
            s.projects_delete_confirm_msg.format(name=project.name))
        if not ans:
            return
        try:
            self._pm.delete(project)
        except Exception as e:
            QMessageBox.warning(self, s.projects_delete, str(e))
            return
        self.project_deleted.emit(project)
        self.refresh()

    def _on_duplicate(self, project: Project):
        try:
            self._pm.duplicate(project)
        except Exception as e:
            QMessageBox.warning(self, lang_manager.current.projects_duplicate, str(e))
        self.refresh()

    def _on_rename(self, project: Project):
        from PyQt6.QtWidgets import QInputDialog
        s = lang_manager.current
        new_name, ok = QInputDialog.getText(
            self, s.projects_rename_dialog_title,
            s.projects_rename_prompt, text=project.name,
        )
        if not ok:
            return
        new_name = new_name.strip()
        if not new_name or new_name == project.name:
            return
        if not is_name_valid(new_name):
            QMessageBox.warning(self, s.projects_rename, s.projects_invalid_name)
            return
        # Collision: suffix (1), (2)... automatically.
        new_name = self._pm.unique_name(
            new_name, project.path.parent, exclude=project.path,
        )
        old_path = str(project.path)
        try:
            self._pm.rename(project, new_name)
        except Exception as e:
            QMessageBox.warning(self, s.projects_rename, str(e))
            return
        self.project_renamed.emit(old_path, project)
        self.refresh()

    # ── i18n / theme ─────────────────────────────────────────────
    def apply_lang(self, s: Strings):
        self._lbl_title.setText(s.projects_title)
        self._btn_new.setText(f"  {s.projects_new}")
        # The "Tous" filter is the only translatable one — the types are proper nouns
        btn_all = self._filter_btns.get(None)
        if btn_all:
            btn_all.setText(s.projects_filter_all)
        self._empty_title.setText(s.projects_empty)
        self._empty_hint.setText(s.projects_empty_hint)
        self._btn_sel_delete.setToolTip(s.projects_delete_selection)
        # Meme oubli que dans board_view : l'infobulle « Bientot disponible »
        # des filtres ESP32 etait posee a la construction, donc figee.
        for b in self._filter_btns.values():
            if getattr(b, "_coming_soon", False):
                b.setToolTip(s.board_coming_soon)

    def apply_theme(self, c: ColorScheme):
        # View background: palette + stylesheet with objectName — the stylesheet
        # guarantees correct rendering from the first paint (the palette alone may
        # not propagate before the widget is shown for the first time).
        self.setObjectName("projectsView")
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.main_bg))
        self.setPalette(p)
        self.setAutoFillBackground(True)
        self.setStyleSheet(f"QWidget#projectsView {{ background-color: {c.main_bg}; }}")

        self._lbl_title.setStyleSheet(f"color: {c.text_primary}; font-size: 16pt; font-weight: 700;")
        self._btn_new.setIcon(IC.make_icon(IC.PLUS, c.btn_primary_text, 16))
        # Left-aligned because the icon sits at the left of the label.
        self._btn_new.setStyleSheet(
            primary_button_qss(c, padding="4px 14px", text_align="left"))
        for btn in self._filter_btns.values():
            btn.apply_theme(c)

        # Trash button: transparent at rest, subtle red tint on
        # hover (destructive affordance without garishness).
        # Same icon-button recipe as the card's « … », with the red tint
        # passed in: the colour is deliberate, only the CSS around it was
        # duplicated.
        delete_hover = "#7f1d1d" if theme_manager.is_dark else "#fecaca"
        self._btn_sel_delete.setStyleSheet(
            icon_button_qss(c, hover_bg=delete_hover))
        self._btn_sel_delete_icon_normal = IC.make_icon(IC.TRASH, c.text_secondary, 18)
        self._btn_sel_delete_icon_hover  = IC.make_icon(IC.TRASH, "#ffffff", 18)
        self._btn_sel_delete.setIcon(self._btn_sel_delete_icon_normal)

        # Scroll area: transparent frame, background carried by _list_host (cf. board_view)
        # The QScrollBars are styled globally in main.py.
        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self._list_host.setStyleSheet(f"QWidget#projectsListHost {{ background: {c.main_bg}; }}")

        # QScrollArea viewport: inherits Base by default (white) — we force Window.
        vp = self._scroll.viewport()
        vp_p = vp.palette()
        vp_p.setColor(QPalette.ColorRole.Window, QColor(c.main_bg))
        vp_p.setColor(QPalette.ColorRole.Base,   QColor(c.main_bg))
        vp.setPalette(vp_p)
        vp.setBackgroundRole(QPalette.ColorRole.Window)
        vp.setAutoFillBackground(True)

        # Empty state
        self._empty.setStyleSheet(f"QWidget#projectsEmpty {{ background: {c.main_bg}; }}")
        self._empty_icon.setPixmap(IC.make_icon(IC.FOLDER_OPEN, c.text_secondary, 48).pixmap(48, 48))
        self._empty_title.setStyleSheet(f"color: {c.text_primary}; font-size: 12pt; font-weight: 600;")
        self._empty_hint.setStyleSheet(f"color: {c.text_secondary}; font-size: 10pt;")
