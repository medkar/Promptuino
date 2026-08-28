"""
PromptuinoUI main window.

Structure:
    ┌──────────┬──────────────────────────────────┐
    │  Sidebar │  TopBar                          │
    │ (full    ├──────────────────────────────────┤
    │  height) │  QStackedWidget (views)          │
    └──────────┴──────────────────────────────────┘
"""
from PyQt6.QtCore import Qt, QThread, QTimer, QUrl, QRectF, pyqtSignal
from PyQt6.QtGui import (
    QAction, QActionGroup, QDesktopServices, QKeySequence, QPalette, QColor,
    QPainter, QPen, QPainterPath,
)
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QStackedWidget, QLabel, QDialog,
)
from .theme import ColorScheme, theme_manager, selection_bg
from .i18n import LANGUAGE_NAMES, lang_manager, Strings
# Le brouillon d'adoption a demenage ici (2026-08-13) : le crayon des cards de
# la modale d'ambiguite en a besoin lui aussi, et ce qu'il fabrique est un
# `DeclaredComponent`. Garde son ancien nom prive de ce cote-ci : c'est par
# cette porte que la fenetre principale l'appelle, et c'est elle que la QA I5
# exerce (`scripts/test_adopt_keeps_lib_choice.py`).
from .declared_components import adoptable_entry as _adoptable_entry
from .sidebar import Sidebar, NAV_ITEMS
from .topbar import TopBar
from .settings_dialog import SettingsDialog
from .about_dialog import AboutDialog
from .board_view import BoardView
from .ia_view import IAView
from . import studio_view as _studio_view_mod
from .studio_view import StudioView
from .chat.chat_controller import ChatController
from .chat.chat_view import ChatView
from .projects_view import ProjectsView
from .statusbar import StatusBar
from .board_manager import board_manager, detect_board, _KNOWN_DEVICES
from .usb_watcher import USBWatcher
from .session import session
from .project_manager import project_manager, projects_root, TYPE_DIR_NAMES
from .tutorial import TutorialOverlay, TutorialStep


_OVERLAY_W = 16        # size of the clickable chevron (overlaid)
_OVERLAY_H = 30


class _ChevronOverlay(QWidget):
    """Clickable collapse chevron, OVERLAID on the separator bar
    (raised child of the central area, positioned by hand).

    TRANSPARENT background (WA_TranslucentBackground): it lets the 1px line
    and the REAL panels behind it show through. No color assumption -> no
    possible band, whatever colors it crosses (topbar, project bar,
    content grid, chat…). Replaces the collapse buttons.

    `point_left_when_open` = chevron direction when the panel is OPEN:
      - sidebar (bar to its right) → open: « ‹ » (collapse to the left)
      - chat    (bar to its left)  → open: « › » (collapse to the right)
    """

    clicked = pyqtSignal()
    hover_changed = pyqtSignal(bool)   # hover over the chevron itself (to link it to the chat title)

    def __init__(self, point_left_when_open: bool, parent=None):
        super().__init__(parent)
        self._point_left_when_open = point_left_when_open
        self._open = True
        self._hover = False
        self._linked = False   # hover over the LINKED widget (« _ASSISTANT IA » title)
        self.setFixedSize(_OVERLAY_W, _OVERLAY_H)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        theme_manager.changed.connect(lambda *_: self.update())

    def set_open(self, is_open: bool) -> None:
        if is_open != self._open:
            self._open = is_open
            self.update()

    def set_linked_hover(self, hovered: bool) -> None:
        """The linked widget (collapsed chat title) is hovered -> we light up too."""
        if hovered != self._linked:
            self._linked = hovered
            self.update()

    def enterEvent(self, e):
        self._hover = True
        self.hover_changed.emit(True)
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.hover_changed.emit(False)
        self.update()
        super().leaveEvent(e)

    def mouseReleaseEvent(self, e):
        if (e.button() == Qt.MouseButton.LeftButton
                and self.rect().contains(e.position().toPoint())):
            self.clicked.emit()
        super().mouseReleaseEvent(e)

    def paintEvent(self, _e):
        c = theme_manager.current
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = float(self.width())
        h = float(self.height())
        cx = w / 2.0
        cy = h / 2.0
        # Effective hover: the chevron OR the linked chat title (they light up
        # together). Without hover the widget is entirely transparent.
        hovered = self._hover or self._linked
        # rounded halo on hover (feedback).
        if hovered:
            halo = QRectF(cx - 7.0, cy - 11.0, 14.0, 22.0)
            halo_path = QPainterPath()
            halo_path.addRoundedRect(halo, 5.0, 5.0)
            p.fillPath(halo_path, QColor(c.nav_hover_bg))
        # chevron centered on the bar: white (text_primary), green on hover.
        points_left = (self._point_left_when_open if self._open
                       else not self._point_left_when_open)
        pen = QPen(QColor(c.signal_ok if hovered else c.text_primary))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        p.setPen(pen)
        dx, dy = 3.0, 5.0
        chev = QPainterPath()
        if points_left:
            chev.moveTo(cx + dx, cy - dy)
            chev.lineTo(cx - dx, cy)
            chev.lineTo(cx + dx, cy + dy)
        else:
            chev.moveTo(cx - dx, cy - dy)
            chev.lineTo(cx + dx, cy)
            chev.lineTo(cx - dx, cy + dy)
        p.drawPath(chev)
        p.end()


class _StartupDetectThread(QThread):
    # Also emits the VID:PID so the watcher knows what it is monitoring
    found = pyqtSignal(str, str, int, int)  # (env_id, model, vid, pid)

    def run(self):
        try:
            from serial.tools import list_ports
            for port in list_ports.comports():
                if port.vid is None or port.pid is None:
                    continue
                result = _KNOWN_DEVICES.get((port.vid, port.pid))
                if result:
                    self.found.emit(result[0], result[1], port.vid, port.pid)
                    return
        except Exception:
            pass


class PlaceholderView(QWidget):
    """Empty temporary view — will be replaced by a real module."""

    def __init__(self, label_key: str, parent=None):
        super().__init__(parent)
        self._label_key = label_key
        layout = QVBoxLayout(self)
        self._lbl = QLabel(getattr(lang_manager.current, label_key))
        self._lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl.setStyleSheet("font-size: 18pt; color: #4338ca; font-weight: 600;")
        layout.addWidget(self._lbl)
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

    def apply_theme(self, c: ColorScheme):
        self.setStyleSheet(f"QWidget {{ background-color: {c.main_bg}; }}")

    def apply_lang(self, s: Strings):
        self._lbl.setText(getattr(s, self._label_key))


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PromptuinoUI")
        # Widened minimum (#4): wide enough for the editor (456px floor)
        # + the right journal/buttons column (380px) to fit without overflowing
        # on the right as long as at least one side panel (sidebar/chat) is collapsed.
        # (Full guarantee with BOTH expanded ≈ 1460px, but too wide for
        # small screens → we stop at 1280, which covers the common cases.)
        # Height (#9): tall enough for the ADVANCED view (the densest: its
        # prompt header with the comments slider is ~42 px taller than the
        # other modes) to fit WITHOUT overflowing at the bottom. Bottom of the code area ≈ 656 px
        # + status bar ⇒ real minimum ~678; 700 leaves a safety margin
        # (DPI/fonts) while staying compatible with 1366×768 laptops.
        self.setMinimumSize(1280, 700)
        self.resize(1400, 820)
        self._build_menubar()
        self._build_ui()
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self._apply_lang_menubar)
        self._startup_detect()
        # Defer to the next event loop turn: show() has not been called yet
        # and the layouts are not computed — the mode selector's sizeHint()
        # would return values that are too small, causing tiny buttons until
        # the first resize.
        QTimer.singleShot(0, self._restore_last_session)
        # Position the collapse chevrons once the first layout pass is done (the
        # bar geometries are only valid after show/layout).
        QTimer.singleShot(0, self._position_collapse_handles)

    # ── Menu bar ──────────────────────────────────────────────

    def _build_menubar(self):
        mb = self.menuBar()
        s  = lang_manager.current

        # ── File ───────────────────────────────────────────────
        self._menu_file = mb.addMenu(s.menu_file)
        self._act_new   = QAction(s.mn_new_project, self)
        self._act_new.setShortcut(QKeySequence("Ctrl+N"))
        self._act_new.triggered.connect(self._action_new_project)
        self._menu_file.addAction(self._act_new)

        self._act_open = QAction(s.mn_open_project, self)
        self._act_open.setShortcut(QKeySequence("Ctrl+O"))
        self._act_open.triggered.connect(lambda: self._goto_tab("projets"))
        self._menu_file.addAction(self._act_open)

        self._act_save = QAction(s.mn_save, self)
        # No shortcut here: studio_view already exposes Ctrl+S via QShortcut.
        self._act_save.triggered.connect(self._action_save)
        self._menu_file.addAction(self._act_save)

        self._menu_file.addSeparator()

        self._act_settings = QAction(s.topbar_settings, self)
        self._act_settings.triggered.connect(self._on_settings)
        self._menu_file.addAction(self._act_settings)

        self._menu_file.addSeparator()

        self._act_quit = QAction(s.mn_quit, self)
        self._act_quit.setShortcut(QKeySequence("Ctrl+Q"))
        self._act_quit.triggered.connect(self.close)
        self._menu_file.addAction(self._act_quit)

        # ── Edit ───────────────────────────────────────────────
        # No shortcuts on Annuler/Rétablir: studio_view already exposes
        # Ctrl+Z / Ctrl+Y via QShortcut (a duplicate here would make them
        # ambiguous and Qt would fire neither).
        self._menu_edit = mb.addMenu(s.menu_edit)
        self._act_undo = QAction(s.mn_undo, self)
        self._act_undo.triggered.connect(self._action_undo)
        self._menu_edit.addAction(self._act_undo)

        self._act_redo = QAction(s.mn_redo, self)
        self._act_redo.triggered.connect(self._action_redo)
        self._menu_edit.addAction(self._act_redo)

        self._menu_edit.addSeparator()

        self._act_copy_code = QAction(s.mn_copy_code, self)
        self._act_copy_code.triggered.connect(self._action_copy_code)
        self._menu_edit.addAction(self._act_copy_code)

        self._act_clear_prompt = QAction(s.mn_clear_prompt, self)
        self._act_clear_prompt.triggered.connect(self._action_clear_prompt)
        self._menu_edit.addAction(self._act_clear_prompt)

        # ── Board ──────────────────────────────────────────────
        self._menu_card = mb.addMenu(s.menu_card)
        self._act_goto_board = QAction(s.mn_goto_board, self)
        self._act_goto_board.triggered.connect(lambda: self._goto_tab("carte"))
        self._menu_card.addAction(self._act_goto_board)

        # ── View ───────────────────────────────────────────────
        self._menu_view = mb.addMenu(s.menu_view)
        self._act_theme = QAction(s.mn_theme_toggle, self)
        self._act_theme.setShortcut(QKeySequence("Ctrl+Shift+T"))
        self._act_theme.triggered.connect(theme_manager.toggle)
        self._menu_view.addAction(self._act_theme)

        self._menu_language = self._menu_view.addMenu(s.mn_language)
        self._lang_group = QActionGroup(self)
        self._lang_group.setExclusive(True)
        self._lang_actions: dict[str, QAction] = {}
        for code, native in LANGUAGE_NAMES.items():
            act = QAction(native, self, checkable=True)
            act.setChecked(code == lang_manager.lang)
            act.triggered.connect(lambda _checked=False, c=code: lang_manager.set_language(c))
            self._lang_group.addAction(act)
            self._menu_language.addAction(act)
            self._lang_actions[code] = act

        self._act_toggle_sidebar = QAction(s.mn_toggle_sidebar, self)
        self._act_toggle_sidebar.setShortcut(QKeySequence("Ctrl+B"))
        self._act_toggle_sidebar.triggered.connect(self._action_toggle_sidebar)
        self._menu_view.addAction(self._act_toggle_sidebar)

        self._act_fullscreen = QAction(s.mn_fullscreen, self, checkable=True)
        self._act_fullscreen.setShortcut(QKeySequence("F11"))
        self._act_fullscreen.triggered.connect(self._action_toggle_fullscreen)
        self._menu_view.addAction(self._act_fullscreen)

        self._menu_view.addSeparator()

        self._act_open_workspace = QAction(s.mn_open_workspace, self)
        self._act_open_workspace.triggered.connect(self._action_open_workspace)
        self._menu_view.addAction(self._act_open_workspace)

        # ── Help ───────────────────────────────────────────────
        self._menu_help = mb.addMenu(s.menu_help)
        self._act_about = QAction(s.mn_about, self)
        self._act_about.triggered.connect(self._action_about)
        self._menu_help.addAction(self._act_about)

        # Review the welcome tutorial (replays the tutorial for the current mode).
        self._act_review_tutorial = QAction(s.mn_review_tutorial, self)
        self._act_review_tutorial.triggered.connect(self._action_review_tutorial)
        self._menu_help.addAction(self._act_review_tutorial)

        # « Coulisses du prompt » (#42) : l'ancienne case « Mode débug —
        # afficher le prompt IA » vivait ICI, dans le menu Aide, et son état
        # se perdait à chaque lancement (assumé : « fonction de développeur »).
        # Ce n'en est pas une — c'est un aperçu pédagogique de ce que l'app
        # fabrique. Elle a donc déménagé dans Paramètres, où elle est
        # persistée (`session.prompt_backstage`).

        self._apply_menubar_style(theme_manager.current)

    def _apply_lang_menubar(self, s: Strings):
        # Les deux poignées de repli sont affichées EN PERMANENCE et n'avaient
        # aucune infobulle ni nom accessible : ce sont des QWidget dessinés au
        # QPainter, donc invisibles à tout balayage des boutons — l'angle mort
        # qui explique qu'elles soient passées entre les mailles. Posées ici
        # pour suivre la langue.
        self._sep_handle.setToolTip(s.tip_toggle_sidebar)
        self._chat_handle.setToolTip(s.tip_toggle_chat)
        self._menu_file.setTitle(s.menu_file)
        self._menu_edit.setTitle(s.menu_edit)
        self._menu_card.setTitle(s.menu_card)
        self._menu_view.setTitle(s.menu_view)
        self._menu_help.setTitle(s.menu_help)
        self._menu_language.setTitle(s.mn_language)

        self._act_new.setText(s.mn_new_project)
        self._act_open.setText(s.mn_open_project)
        self._act_save.setText(s.mn_save)
        self._act_quit.setText(s.mn_quit)
        self._act_undo.setText(s.mn_undo)
        self._act_redo.setText(s.mn_redo)
        self._act_copy_code.setText(s.mn_copy_code)
        self._act_clear_prompt.setText(s.mn_clear_prompt)
        self._act_goto_board.setText(s.mn_goto_board)
        self._act_theme.setText(s.mn_theme_toggle)
        self._act_toggle_sidebar.setText(s.mn_toggle_sidebar)
        self._act_fullscreen.setText(s.mn_fullscreen)
        self._act_settings.setText(s.topbar_settings)
        self._act_open_workspace.setText(s.mn_open_workspace)
        self._act_about.setText(s.mn_about)
        self._act_review_tutorial.setText(s.mn_review_tutorial)
        # The language choice stays checked on the current language.
        for code, act in self._lang_actions.items():
            act.setChecked(code == lang_manager.lang)

    def _apply_menubar_style(self, c: ColorScheme):
        self.menuBar().setStyleSheet(f"""
            QMenuBar {{
                background-color: {c.topbar_bg};
                color: {c.topbar_btn_text};
                border-bottom: 1px solid {c.border};
                font-size: 10pt;
                padding: 2px 4px;
            }}
            QMenuBar::item {{
                background: transparent;
                padding: 4px 10px;
                border-radius: 4px;
            }}
            QMenuBar::item:selected {{
                background-color: {c.nav_hover_bg};
                color: {c.text_primary};
            }}
            QMenuBar::item:pressed {{
                background-color: {selection_bg(c)};
                color: {c.text_primary};
            }}
            QMenu {{
                background-color: {c.sidebar_bg};
                color: {c.text_primary};
                border: 1px solid {c.border};
                border-radius: 6px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: {selection_bg(c)};
                color: {c.text_primary};
            }}
        """)

    # ── Construction ──────────────────────────────────────────

    def _build_ui(self):
        # ── Sidebar (full height) ──────────────────────────────
        self._sidebar = Sidebar()
        self._sidebar.tab_changed.connect(self._on_tab_changed)

        # ── Right panel: topbar + content ─────────────────────
        self._right_panel = QWidget()
        right_layout = QVBoxLayout(self._right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        self._topbar = TopBar()
        # Settings: button moved to the BOTTOM of the sidebar (no longer in the topbar).
        self._sidebar.settings_requested.connect(self._on_settings)
        self._topbar.set_sidebar(self._sidebar)
        # Undo/redo arrows (left of the mode selector) -> same handlers
        # as the Édition menu (lazy Studio lookup, safe at build time).
        self._topbar.undo_clicked.connect(self._action_undo)
        self._topbar.redo_clicked.connect(self._action_redo)
        # The chat is always present in the Studio tab (collapse via its own
        # buttons); this flag stays true (no more hiding via the topbar).
        self._chat_panel_wanted_visible = True
        self._chat_current_tab = "console"  # init while waiting for the first _on_tab_changed

        self._sidebar.width_changed.connect(lambda _w: self._topbar._position_mode_selector())
        right_layout.addWidget(self._topbar)

        # Separator line under the topbar (same principle as the one to the right of the sidebar)
        self._topbar_sep = QWidget()
        self._topbar_sep.setFixedHeight(1)
        right_layout.addWidget(self._topbar_sep)

        # ─── Chat panel (permanent vertical strip, between sidebar
        # and main stack) ────────────────────────────────────────────
        # The controller is instantiated with a None backend; it will be
        # updated when the user activates a backend in AI Model (Task 10).
        self._chat_controller = ChatController(
            backend=None, user_mode="beginner",
        )
        self._chat_view = ChatView(self._chat_controller)
        self._chat_view.history_changed.connect(self._on_chat_history_changed)
        self._chat_view.open_in_atelier_requested.connect(
            self._on_chat_open_in_studio
        )
        self._chat_view.request_modify_in_studio.connect(
            self._on_chat_modify_in_studio
        )
        self._chat_view.open_model_settings_requested.connect(
            lambda: self._goto_tab("ia")
        )

        # The right panel (under the topbar) only contains the view stack.
        # The chat is a FULL-HEIGHT strip on the right edge (root sibling,
        # see central area below): its header aligns with the topbar, like
        # the mockup. User decision (revised): the assistant goes all the way up.
        self._stack = QStackedWidget()
        right_layout.addWidget(self._stack, stretch=1)
        # The mode selector recenters when the chat width changes
        # (collapse) -> same mechanism as the sidebar.
        self._chat_view.width_changed.connect(
            lambda _w: self._topbar._position_mode_selector()
        )

        # Single reused Settings dialog (it embeds the live LibraryView whose
        # worker threads must not be destroyed mid-run): created lazily, kept
        # alive, just re-shown.
        self._settings_dlg: SettingsDialog | None = None

        self._views: dict[str, QWidget] = {}
        for tab_id, _svg, label_key in NAV_ITEMS:
            if tab_id == "carte":
                view = BoardView()
            elif tab_id == "ia":
                view = IAView()
            elif tab_id == "console":
                view = StudioView(mode_selector=self._topbar.mode_selector)
                view.projects_tab_requested.connect(
                    lambda: self._goto_tab("projets")
                )
                view.project_created.connect(self._on_project_created)
                # Rename from the Studio: refreshes the Projects list.
                view.project_renamed.connect(
                    lambda _op, p: self._on_project_created(p)
                )
                # The Studio no longer displays the project name in its top
                # bar: it is pushed into the window title
                # ("PromptuinoUI - ProjectName"). Empty => title without suffix.
                view.project_title_changed.connect(self._on_project_title_changed)
                # Contextual '?' bridge (F2 step 4): the Studio can request
                # to open the chat with a prefix + system extras from its
                # ambiguity modals or other UI surfaces.
                view.chat_help_requested.connect(self._on_chat_help_requested)
                view.wrong_component_help_requested.connect(
                    self._on_wrong_component_help
                )
            elif tab_id == "composants":
                from .components_view import ComponentsView
                view = ComponentsView()
                view.declare_requested.connect(self._on_declare_requested)
            elif tab_id == "projets":
                view = ProjectsView()
                view.open_project_requested.connect(self._on_open_project)
                view.project_deleted.connect(self._on_project_deleted)
                view.project_renamed.connect(self._on_project_renamed)
                # When the user changes the root via Settings, the project
                # list must reflect the new folder.
                session.workspace_root_changed.connect(
                    lambda _p, v=view: v.refresh()
                )
            else:
                view = PlaceholderView(label_key)
            self._stack.addWidget(view)
            self._views[tab_id] = view

        # ── Chat connections ───────────────────────────────────────────
        # Wire A: active backend (IAView -> ChatView)
        ia_view = self._views.get("ia")
        if ia_view is not None and hasattr(ia_view, "backend_activated"):
            ia_view.backend_activated.connect(self._chat_view.set_backend)
            # Init at startup with the already-active backend.
            if hasattr(ia_view, "get_active_backend"):
                current_backend = ia_view.get_active_backend()
                if current_backend is not None:
                    self._chat_view.set_backend(current_backend)

        # Wire B: user mode (TopBar.mode_selector -> ChatView)
        sel = self._topbar.mode_selector
        sel.mode_changed.connect(self._chat_view.set_user_mode)
        self._chat_view.set_user_mode(sel.active_mode)

        # Wire C: project context (StudioView -> ChatView)
        studio_view = self._views.get("console")
        if studio_view is not None:
            if hasattr(studio_view, "chat_context_changed"):
                studio_view.chat_context_changed.connect(
                    self._on_chat_context_changed
                )
            if hasattr(studio_view, "project_loaded"):
                studio_view.project_loaded.connect(
                    self._on_studio_project_loaded
                )
        # Pre-send hook: lets the chat request a refresh of the project
        # context right before each LLM send (otherwise code edited by hand
        # between 2 sends would not be seen).
        if studio_view is not None and hasattr(studio_view, "_emit_chat_context"):
            self._chat_view.pre_send_hook = studio_view._emit_chat_context

        # Wire D: shared attachment (ChatView <-> StudioView). Dropping /
        # attaching a file on the chat side feeds the SAME context file as the
        # "Generate a feature" prompt; the chip's x removes it.
        self._chat_view.attach_file_requested.connect(self._on_chat_attach_file)
        self._chat_view.detach_file_requested.connect(self._on_chat_detach_file)

        # Wire E: library choice (ComponentsView -> StudioView). Same shape as
        # Wire C: after the loop, from `_views`, with hasattr guards -- the view
        # set is data-driven by NAV_ITEMS, so nothing here may assume a tab
        # exists.
        components_view = self._views.get("composants")
        if components_view is not None and studio_view is not None:
            if hasattr(components_view, "change_lib_requested"):
                components_view.change_lib_requested.connect(
                    studio_view.on_change_lib_for_component)

        # ── Central area: sidebar | separator | right panel
        self._center = QWidget()
        center_layout = QHBoxLayout(self._center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)

        center_layout.addWidget(self._sidebar)

        # Sidebar separator: simple 1px line (the collapse chevron is placed
        # OVER it as an overlay, see _ChevronOverlay below).
        self._sep = QWidget()
        self._sep.setFixedWidth(1)
        center_layout.addWidget(self._sep)

        center_layout.addWidget(self._right_panel, stretch=1)

        # Chat: FULL-HEIGHT strip on the right edge (mockup / spec §1) —
        # its header aligns with the topbar. Separator = 1px line (chevron
        # overlaid).
        self._chat_sep = QWidget()
        self._chat_sep.setFixedWidth(1)
        center_layout.addWidget(self._chat_sep)
        center_layout.addWidget(self._chat_view)

        # ── Collapse chevrons OVERLAID on the bars ─────────────────────────
        # Raised children of _center, positioned by hand on each line
        # (see _position_collapse_handles). Transparent background -> no band,
        # whatever the colors behind. Replace the collapse buttons
        # (sidebar + chat).
        self._sep_handle = _ChevronOverlay(point_left_when_open=True,
                                           parent=self._center)
        self._sep_handle.set_open(self._sidebar.is_expanded())
        self._sep_handle.clicked.connect(self._action_toggle_sidebar)
        self._sidebar.expanded_changed.connect(self._sep_handle.set_open)
        self._sidebar.width_changed.connect(
            lambda _w: self._position_collapse_handles()
        )

        self._chat_handle = _ChevronOverlay(point_left_when_open=False,
                                            parent=self._center)
        self._chat_handle.set_open(not self._chat_view.is_collapsed())
        self._chat_handle.clicked.connect(self._chat_view.toggle_collapsed)
        # Posees ici EN PLUS de `_apply_lang_menubar` : celui-ci n'est branche
        # que sur le signal `changed`, donc il ne s'execute pas au demarrage —
        # les poignees seraient restees muettes jusqu'au premier changement de
        # langue.
        self._sep_handle.setToolTip(lang_manager.current.tip_toggle_sidebar)
        self._chat_handle.setToolTip(lang_manager.current.tip_toggle_chat)
        self._chat_view.collapsed_changed.connect(
            lambda collapsed: self._chat_handle.set_open(not collapsed)
        )
        self._chat_view.collapsed_changed.connect(
            lambda _c: self._position_collapse_handles()
        )
        self._chat_view.width_changed.connect(
            lambda _w: self._position_collapse_handles()
        )
        # Bidirectional hover link chevron <-> « _ASSISTANT IA » title:
        # hovering one lights up the other (both turn green together).
        self._chat_handle.hover_changed.connect(self._chat_view.set_title_linked_hover)
        self._chat_view.title_hover_changed.connect(self._chat_handle.set_linked_hover)

        # ── Root: central area + status bar ───────────────────
        self._root_widget = QWidget()
        root_layout = QVBoxLayout(self._root_widget)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        root_layout.addWidget(self._center, stretch=1)

        self._statusbar_sep = QWidget()
        self._statusbar_sep.setFixedHeight(1)
        root_layout.addWidget(self._statusbar_sep)

        self._statusbar = StatusBar()
        root_layout.addWidget(self._statusbar)

        self.setCentralWidget(self._root_widget)

        # ── Welcome tutorial (coachmark) ───────────────────────
        # Full-screen overlay of the central area (covers sidebar + topbar +
        # studio + chat). Triggered at the first launch (beginner) and the first
        # time through each mode; re-triggerable via Help » Review the tutorial.
        self._tutorial = TutorialOverlay(self._center)
        self._tutorial.closed.connect(self._on_tutorial_closed)
        self._active_tutorial_mode = "beginner"
        self._topbar.mode_selector.mode_changed.connect(self._on_mode_for_tutorial)

        self.apply_theme(theme_manager.current)
        # Initial sync of chat visibility with the current tab.
        self._refresh_chat_visibility()

    # ── Theme ─────────────────────────────────────────────────

    @staticmethod
    def _set_bg(widget: QWidget, hex_color: str):
        """Force the background color via QPalette — reliable even with QSS cascades."""
        palette = widget.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(hex_color))
        widget.setPalette(palette)
        widget.setAutoFillBackground(True)

    def apply_theme(self, c: ColorScheme):
        self._set_bg(self._root_widget, c.main_bg)
        self._set_bg(self._center,      c.main_bg)
        self._set_bg(self._right_panel, c.main_bg)
        self._set_bg(self._stack,       c.main_bg)
        self._sep.setStyleSheet(f"background-color: {c.border};")
        self._chat_sep.setStyleSheet(f"background-color: {c.border};")
        self._topbar_sep.setStyleSheet(f"background-color: {c.border};")
        self._statusbar_sep.setStyleSheet(f"background-color: {c.border};")
        self._apply_menubar_style(c)

    # ── Recentering the mode selector ─────────────────────────

    def resizeEvent(self, event):
        """Recenter the mode selector on the window at EVERY resize
        (robust safety net: the topbar's resizeEvent does not cover all window
        resize cases depending on the platform)."""
        super().resizeEvent(event)
        self._topbar._position_mode_selector()
        self._position_collapse_handles()
        if hasattr(self, "_tutorial"):
            self._tutorial.reposition()

    def _position_collapse_handles(self):
        """Recenter the collapse chevrons (overlay) on each separator bar:
        vertical middle of the central area, right on the 1px line.
        Called on resize, on collapse/expand (sidebar + chat) and on tab
        change."""
        if not hasattr(self, "_sep_handle"):
            return
        # During the tutorial, hide the collapse chevrons: otherwise they are
        # drawn over the bubble (re-raise on tab switch).
        if getattr(self, "_tutorial", None) is not None and self._tutorial.isVisible():
            self._sep_handle.setVisible(False)
            self._chat_handle.setVisible(False)
            return
        cy = self._center.height() // 2
        r = self._sep.geometry()
        self._sep_handle.move(
            r.center().x() - self._sep_handle.width() // 2,
            cy - self._sep_handle.height() // 2,
        )
        self._sep_handle.raise_()
        # The chat chevron follows the chat bar's visibility (hidden outside Studio).
        if self._chat_sep.isVisible():
            r2 = self._chat_sep.geometry()
            self._chat_handle.move(
                r2.center().x() - self._chat_handle.width() // 2,
                cy - self._chat_handle.height() // 2,
            )
            self._chat_handle.setVisible(True)
            self._chat_handle.raise_()
        else:
            self._chat_handle.setVisible(False)

    # ── Startup detection ─────────────────────────────────────

    def _startup_detect(self):
        self._usb_watcher = USBWatcher(self)
        self._usb_watcher.board_connected.connect(board_manager.set_board_connected)
        self._usb_watcher.board_disconnected.connect(
            lambda: board_manager.set_connected(False)
        )

        self._detect_thread = _StartupDetectThread(self)
        self._detect_thread.found.connect(self._on_startup_found)
        self._detect_thread.finished.connect(
            lambda: self._usb_watcher.start(self._startup_pid)
        )
        self._startup_pid = None
        self._detect_thread.start()

    def _on_startup_found(self, env: str, model: str, vid: int, pid: int):
        self._startup_pid = (vid, pid)
        board_manager.set_board_connected(env, model)

    # ── Session restoration ───────────────────────────────────

    def _restore_last_session(self):
        """Open the Studio tab at startup, with the last project if available.

        The last project's path is stored in ~/Documents/Promptuino/
        session.json and updated by the StudioView on every project load /
        creation.
        """
        path_str = session.last_project_path
        if path_str:
            from pathlib import Path
            path = Path(path_str)
            studio = self._views.get("console")
            # Only load if the project still exists on disk AND we can recover
            # its type from the path.
            if path.exists() and studio is not None:
                ptype = self._infer_type_from_path(path)
                if ptype is not None:
                    proj = project_manager._load_folder(path, ptype)
                    if proj is not None and hasattr(studio, "load_project"):
                        studio.load_project(proj)
            else:
                # Project gone: clean up the session so we do not retry.
                session.last_project_path = ""
        # In all cases, open the Studio tab at startup.
        self._goto_tab("console")
        # Welcome tutorial at the first launch (beginner mode, never seen).
        if (self._topbar.mode_selector.active_mode == "beginner"
                and not session.tutorial_seen("beginner")):
            QTimer.singleShot(350, lambda: self._start_tutorial("beginner"))

    @staticmethod
    def _infer_type_from_path(path):
        """Infer the ProjectType from the parent folder name (Arduino,
        Esp32). path = .../<TypeDir>/projects/<name>."""
        try:
            type_dir_name = path.parent.parent.name
        except Exception:
            return None
        for t, name in TYPE_DIR_NAMES.items():
            if name == type_dir_name:
                return t
        return None

    # ── Welcome tutorial (coachmark) ──────────────────────────
    def _tutorial_steps(self, mode: str) -> list:
        """Tutorial steps (target + i18n key) for a mode. Beginner = full set;
        intermediate/advanced = only the NEW elements of the mode. Targets
        resolved lazily and tolerantly (step skipped if the target is
        absent/hidden)."""
        studio = self._views.get("console")

        def w(*names):
            for n in names:
                x = getattr(studio, n, None) if studio is not None else None
                if x is not None:
                    return x
            return None

        def tab(tid):
            btns = getattr(self._sidebar, "_buttons", None)
            return btns.get(tid) if btns else None

        def sub(obj_name, attr):
            """Cible imbriquée (ex. la dropdown portée par _code_panel)."""
            obj = getattr(studio, obj_name, None) if studio is not None else None
            return getattr(obj, attr, None) if obj is not None else None

        if mode == "beginner":
            return [
                # 1) Studio tab FIRST OF ALL (the main workspace).
                TutorialStep(lambda: tab("console"), "tuto_beg_studio",
                             lambda: self._goto_tab("console"), "right_top"),
                # 2) The elements of the Studio view.
                TutorialStep(lambda: w("_prompt_field"), "tuto_beg_prompt",
                             lambda: self._goto_tab("console")),
                TutorialStep(lambda: w("_beginner_row"), "tuto_beg_actions"),
                TutorialStep(lambda: w("_beg_output_area"), "tuto_beg_journal"),
                TutorialStep(lambda: self._chat_view, "tuto_beg_chat"),
                # 3) The mode + theme toggles, BEFORE the other tabs.
                TutorialStep(lambda: getattr(self._topbar, "mode_selector", None),
                             "tuto_beg_mode", lambda: self._goto_tab("console")),
                TutorialStep(lambda: getattr(self._topbar, "_theme_toggle", None),
                             "tuto_beg_theme"),
                # 4) The other tabs (we NAVIGATE to them; Library skipped).
                TutorialStep(lambda: tab("projets"), "tuto_beg_projets",
                             lambda: self._goto_tab("projets"), "right_top"),
                TutorialStep(lambda: tab("carte"), "tuto_beg_carte",
                             lambda: self._goto_tab("carte"), "right_top"),
                TutorialStep(lambda: tab("ia"), "tuto_beg_ia",
                             lambda: self._goto_tab("ia"), "right_top"),
            ]
        if mode == "intermediate":
            return [
                TutorialStep(lambda: w("_btn_generate", "_gen_col_w"),
                             "tuto_int_generate"),
                TutorialStep(lambda: w("_editor", "_code_header_w"),
                             "tuto_int_editor"),
                TutorialStep(lambda: sub("_code_panel", "feature_dropdown"),
                             "tuto_int_features"),
                TutorialStep(lambda: w("_btn_ai_tools"), "tuto_int_tools"),
                # Cible SEULEMENT les 2 boutons (Compiler & Uploader + Voir le
                # schéma), pas toute la colonne compile (fallback si absent).
                TutorialStep(lambda: w("_ia_controls_w", "_code_compile_w"),
                             "tuto_int_compile"),
            ]
        if mode == "advanced":
            return [
                TutorialStep(lambda: w("_editor", "_code_header_w"),
                             "tuto_adv_editor"),
                TutorialStep(lambda: w("_stable_panel"), "tuto_adv_stable"),
                TutorialStep(lambda: w("_btn_transfer"), "tuto_adv_transfer"),
                TutorialStep(lambda: w("_comments_slider_w"), "tuto_adv_comments"),
                TutorialStep(lambda: w("_chk_serial_monitor"), "tuto_adv_serial"),
            ]
        return []

    def _start_tutorial(self, mode: str) -> None:
        self._active_tutorial_mode = mode
        self._tutorial.start(self._tutorial_steps(mode))

    def _on_mode_for_tutorial(self, mode: str) -> None:
        """First time through a mode -> start its tutorial (new elements). The
        tutorial is about the Studio, so we show it and let the layout
        recompute before measuring the targets."""
        if session.tutorial_seen(mode):
            return
        self._goto_tab("console")
        QTimer.singleShot(160, lambda: self._start_tutorial(mode))

    def _on_tutorial_closed(self) -> None:
        session.set_tutorial_seen(self._active_tutorial_mode, True)
        # The tour of the tabs may end elsewhere (e.g. AI Model) -> return to
        # Studio so the user starts again from the workspace.
        self._goto_tab("console")
        # Restore the collapse chevrons (hidden during the tutorial).
        self._position_collapse_handles()

    def _action_review_tutorial(self) -> None:
        self._goto_tab("console")
        mode = self._topbar.mode_selector.active_mode
        QTimer.singleShot(160, lambda: self._start_tutorial(mode))

    # ── Slots ─────────────────────────────────────────────────

    def _refresh_chat_visibility(self) -> None:
        """The chat is only visible in the Studio tab (console), AND only if
        the user has not forced the hide via the topbar toggle."""
        on_studio = self._chat_current_tab == "console"
        should_show = on_studio and self._chat_panel_wanted_visible
        self._chat_view.setVisible(should_show)
        self._chat_sep.setVisible(should_show)
        self._position_collapse_handles()

    def _on_tab_changed(self, tab_id: str):
        self._chat_current_tab = tab_id
        # Entering Studio: reset the chat toggle to "visible". Otherwise a
        # user who had toggled off before switching tabs (or accidentally)
        # would find the chat missing on return. The topbar toggle stays a
        # "temporary hide within the current Studio session", not a persistent
        # state.
        if tab_id == "console":
            self._chat_panel_wanted_visible = True
        self._refresh_chat_visibility()
        view = self._views.get(tab_id)
        if view:
            self._stack.setCurrentWidget(view)
        # The mode selector (topbar) only makes sense in the Studio.
        self._topbar.set_mode_visible(tab_id == "console")
        # Refresh the project list / component index on every tab activation
        # to catch creations/deletions made from the Studio or the declare
        # form (Components tab -- form wiring lands in a later task, but the
        # index it feeds is already live).
        if tab_id in ("projets", "composants") and view is not None and hasattr(view, "refresh"):
            view.refresh()

    def _goto_tab(self, tab_id: str):
        """Programmatically switch to a tab (sidebar + stack + topbar)."""
        self._sidebar.set_active_tab(tab_id)
        self._on_tab_changed(tab_id)

    def _on_declare_requested(self, key: str) -> None:
        """Open the declaration form from the "Composants" tab: "" creates a
        fresh entry, a component key edits the matching declared component.

        `key` is the bare id (`ComponentInfo.key` = `DeclaredComponent.id`,
        never the netlist type) -- `find_by_type` needs the `custom:` prefix
        put back on.

        Depuis la QA I4, le crayon existe aussi sur une fiche DEVINÉE, dont la
        clé ne désigne aucune entrée déclarée. Le formulaire s'ouvre alors
        pré-rempli avec ce que l'app sait — le nom et la librairie qu'elle a
        choisie — pour que l'utilisateur la reprenne à son compte au lieu de
        repartir d'une feuille vierge. C'est la seule information disponible :
        une devinette ne connaît ni brochage ni mots-clés.
        """
        from .wiring.declare_component_dialog import (
            DeclareComponentDialog, resolve_board_nets,
        )
        from .declared_components import find_by_type, TYPE_PREFIX
        entry = find_by_type(f"{TYPE_PREFIX}{key}") if key else None
        if entry is None and key:
            entry = _adoptable_entry(key, lang_manager.lang)
        old_lib = entry.lib if entry is not None else ""
        dlg = DeclareComponentDialog(
            self, component=None, existing=entry, board_nets=resolve_board_nets(),
            lang=lang_manager.lang)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            view = self._views.get("composants")
            if view is not None and hasattr(view, "refresh"):
                view.refresh()
            self._notify_lib_chosen_in_form(key, old_lib,
                                            dlg.result_component)

    def _notify_lib_chosen_in_form(self, key: str, old_lib: str, saved) -> None:
        """Prévient le Studio quand le formulaire vient de REMPLACER la
        librairie d'un composant, pour qu'il propose de régénérer — exactement
        comme la bannière. Sans ça, cette porte-là restait muette (QA I6,
        2026-08-10 : cf. `StudioView.on_lib_chosen_in_form`).

        Le jeton est le **nom** de l'entrée en minuscules, pas `key` :
        `studio_view._declared_lookup_token` en fait la source de vérité, et
        c'est sous ce nom que le retour d'écriture a rempli le cache. `key`
        est l'ID de la fiche — il coïncide pour une fiche devinée
        (« veml7700»), pas pour une entrée déclarée renommée
        (id `grove-ultrasonic-ranger`, jeton « grove ultrasonic ranger »).
        """
        studio = self._views.get("console")
        if saved is None or studio is None:
            return
        if not hasattr(studio, "on_lib_chosen_in_form"):
            return
        token = (saved.name or "").strip().lower() or key
        studio.on_lib_chosen_in_form(token, old_lib, saved.lib)

    def _on_settings(self):
        if self._settings_dlg is None:
            self._settings_dlg = SettingsDialog(self)
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    # ── Menu actions ──────────────────────────────────────────

    def _action_new_project(self):
        """Open the Studio tab then trigger the inline creation."""
        self._goto_tab("console")
        studio = self._views.get("console")
        if studio is not None and hasattr(studio, "_begin_inline_new_project"):
            studio._begin_inline_new_project()

    def _action_save(self):
        studio = self._views.get("console")
        if studio is not None and hasattr(studio, "save_project"):
            studio.save_project()

    def _action_undo(self):
        """Édition menu + topbar arrow: routed to the Studio (the only
        editable surface — prompt & code editor, focus-aware)."""
        studio = self._views.get("console")
        if studio is not None and hasattr(studio, "undo"):
            studio.undo()

    def _action_redo(self):
        studio = self._views.get("console")
        if studio is not None and hasattr(studio, "redo"):
            studio.redo()

    def _action_copy_code(self):
        studio = self._views.get("console")
        if studio is not None and hasattr(studio, "copy_code_to_clipboard"):
            studio.copy_code_to_clipboard()

    def _action_clear_prompt(self):
        studio = self._views.get("console")
        if studio is not None and hasattr(studio, "clear_prompt"):
            studio.clear_prompt()

    def _action_toggle_sidebar(self):
        self._sidebar.toggle_expand()

    def _action_toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self._act_fullscreen.setChecked(False)
        else:
            self.showFullScreen()
            self._act_fullscreen.setChecked(True)

    def _action_open_workspace(self):
        path = projects_root()
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _action_about(self):
        AboutDialog(self).exec()

    def _on_open_project(self, project):
        """Switch to Studio and pass the project."""
        studio = self._views.get("console")
        if studio and hasattr(studio, "load_project"):
            studio.load_project(project)
        # Use _goto_tab rather than set_active_tab alone: the latter does NOT
        # emit tab_changed, so _on_tab_changed does not run and the chat panel
        # stays hidden (`_chat_current_tab` not updated).
        # _goto_tab does set_active_tab + calls _on_tab_changed.
        self._goto_tab("console")
        self._topbar.set_mode_visible(True)

    def _on_project_deleted(self, project):
        studio = self._views.get("console")
        if studio and hasattr(studio, "on_project_deleted"):
            studio.on_project_deleted(project)

    def _on_project_renamed(self, old_path: str, project):
        studio = self._views.get("console")
        if studio and hasattr(studio, "on_project_renamed"):
            studio.on_project_renamed(old_path, project)

    def _on_project_created(self, _project):
        projects_view = self._views.get("projets")
        if projects_view is not None and hasattr(projects_view, "refresh"):
            projects_view.refresh()

    def _on_project_title_changed(self, name: str):
        """Update the window title: "PromptuinoUI - Name" if a project is
        loaded, otherwise just "PromptuinoUI"."""
        if name:
            self.setWindowTitle(f"PromptuinoUI - {name}")
        else:
            self.setWindowTitle("PromptuinoUI")

    # ── Close guard ─────────────────────────────────────────────
    def closeEvent(self, event):
        studio = self._views.get("console")
        if studio and hasattr(studio, "can_discard_changes") and not studio.can_discard_changes():
            event.ignore()
            return
        event.accept()

    # ── Public API ─────────────────────────────────────────────

    def add_view(self, tab_id: str, widget: QWidget):
        """
        Replace a tab's placeholder view with a real module.
        Example:
            window.add_view("console", MonModuleConsole())
        """
        old = self._views.get(tab_id)
        if old:
            idx = self._stack.indexOf(old)
            self._stack.removeWidget(old)
            old.deleteLater()
            self._stack.insertWidget(idx, widget)
        else:
            self._stack.addWidget(widget)
        self._views[tab_id] = widget

    def _on_chat_history_changed(self) -> None:
        """Persist the chat history in the current project."""
        view = self._views.get("console")
        if view is None:
            return
        project = getattr(view, "_current_project", None)
        if project is None:
            return
        project.chat_history = list(self._chat_controller.history)
        if hasattr(view, "save_project"):
            view.save_project()

    def _on_chat_context_changed(self, payload: dict) -> None:
        """Pass the updated project context to the ChatView."""
        self._chat_view.set_project_context(
            code=payload.get("code", ""),
            wiring_summary=payload.get("wiring_summary"),
            original_prompt=payload.get("original_prompt", ""),
            user_material=payload.get("user_material", ""),
            context_name=payload.get("context_name", ""),
            last_compile_error=payload.get("last_compile_error", ""),
        )

    def _on_chat_attach_file(self, path: str) -> None:
        """The chat dropped/picked a file: we route it to the Studio's shared
        context file (copy + persistence), which re-pushes the chip and
        updates the prompt badge."""
        studio = self._views.get("console")
        if studio is not None and hasattr(studio, "attach_context_file"):
            studio.attach_context_file(path)

    def _on_chat_detach_file(self) -> None:
        """Chip's ✕ on the chat side: removes the shared context file (badge +
        chip disappear together)."""
        studio = self._views.get("console")
        if studio is not None and hasattr(studio, "_on_context_removed"):
            studio._on_context_removed()

    def _on_studio_project_loaded(self, project) -> None:
        """Load the project's chat history into the ChatView."""
        if project is None:
            self._chat_view.load_project_history([])
        else:
            self._chat_view.load_project_history(
                list(getattr(project, "chat_history", []) or [])
            )

    def _on_chat_open_in_studio(self, user_text: str) -> None:
        """"Open in Studio" button on a GENERATION_REDIRECT chat bubble.
        Switch to the Studio tab and pre-fill the prompt field with the
        user's initial text."""
        self._goto_tab("console")
        studio = self._views.get("console")
        if studio is None:
            return
        if hasattr(studio, "set_prompt"):
            studio.set_prompt(user_text)

    def _on_chat_modify_in_studio(self, seed: str) -> None:
        """Bouton « Modifier dans le Studio » du chat : bascule sur le Studio
        et lance le flux Modifier pré-staged (prompt rempli + modale Modifier +
        fonction pré-cochée)."""
        self._goto_tab("console")
        studio = self._views.get("console")
        if studio is None:
            return
        if hasattr(studio, "open_modify_flow"):
            studio.open_modify_flow(seed)

    def _on_chat_help_requested(self, prefix_text: str,
                                 system_extras: str = "") -> None:
        """Contextual bridge: a widget (modal, code editor, console)
        requested to open the chat with a pre-filled context. Switch to
        Studio, make sure the chat panel is visible, and pre-fill via
        ChatView.preload."""
        self._goto_tab("console")
        # Make sure the chat panel is visible (may be hidden by the topbar
        # toggle). We force it visible for the duration of this session.
        self._chat_panel_wanted_visible = True
        self._refresh_chat_visibility()
        self._chat_view.set_collapsed(False)   # expand to show the context
        self._chat_view.preload(prefix_text, system_extras=system_extras)

    def _on_wrong_component_help(self, prefix_text: str,
                                  system_extras: str, ctx) -> None:
        """F2-5 safety net: open the correction chat with the context armed."""
        self._goto_tab("console")
        self._chat_panel_wanted_visible = True
        self._refresh_chat_visibility()
        self._chat_view.set_collapsed(False)   # expand to show the context
        self._chat_view.preload_correction(
            prefix_text, system_extras=system_extras,
            correction_context=ctx,
        )
