import sys
from pathlib import Path

# AVANT tout le reste : un `print` de diagnostic ne doit jamais pouvoir tuer
# l'app. Une ligne « [REGISTRY] … → lib … » sur une console cp1252 levait une
# UnicodeEncodeError DANS un slot Qt, et PyQt6 abandonne le processus (segfault,
# sortie 139) — au moment précis où une recherche registre réussissait.
# Cf. ui/console_output.py.
from ui.console_output import make_console_lenient
make_console_lenient()

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QDialog, QToolTip, QProxyStyle, QStyle
from PyQt6.QtGui import QColor, QPalette, QIcon, QPixmap, QPainter
from ui import MainWindow
from ui.theme import (
    theme_manager, ColorScheme, build_app_palette, app_qss,
)
from ui.fonts import setup_fonts
from ui.i18n import lang_manager
from ui.session import session
from ui.welcome_dialog import WelcomeDialog
from ui.auto_hide_scrollbar import install_global_auto_hide
from ui.cursors import install_button_cursors
from ui.onnx_setup import ensure_model_or_exit
from ui import crash_log


def _green_info_icon(size: int = 64) -> QIcon:
    """Information icon « i » with a GREEN background (signal_ok of the current theme) instead
    of the native blue. Drawn with QPainter (circle + white « i »)."""
    green = theme_manager.current.signal_ok
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    s = size / 64.0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(green))
    p.drawEllipse(int(2 * s), int(2 * s), int(60 * s), int(60 * s))
    p.setBrush(QColor("#ffffff"))
    p.drawEllipse(int(27.5 * s), int(15 * s), int(9 * s), int(9 * s))   # dot of the i
    p.drawRoundedRect(int(27.5 * s), int(28 * s), int(9 * s), int(21 * s),
                      int(4.5 * s), int(4.5 * s))                        # bar of the i
    p.end()
    return QIcon(pm)


class _GreenInfoStyle(QProxyStyle):
    """Proxy style: GLOBALLY replaces the native blue information icon of
    QMessageBox with our green « i » (consistent with the app's accent), including
    for the static QMessageBox.information() calls. Delegates everything else to the
    base style."""

    def standardIcon(self, standardIcon, option=None, widget=None):
        if standardIcon == QStyle.StandardPixmap.SP_MessageBoxInformation:
            return _green_info_icon()
        return super().standardIcon(standardIcon, option, widget)


def _apply_tooltip_palette(c: ColorScheme) -> None:
    """Configure QToolTip.palette() so that the text color is taken
    into account even when Qt renders the tooltip in rich-text (which happens as
    soon as the tooltip is long: Qt then wraps the text in <qt><p>...</p></qt>,
    and the rich-text engine ignores the QSS `color` and falls back to the
    palette's ToolTipText). So we force the global palette.
    """
    pal = QToolTip.palette()
    text_color = "#ffffff" if theme_manager.is_dark else c.text_primary
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(text_color))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(c.sidebar_bg))
    QToolTip.setPalette(pal)


def _app_style(c: ColorScheme) -> str:
    """The application-wide stylesheet. A THIN ALIAS on purpose.

    The sheet itself lives in `theme.app_qss`, which is now the single source
    of the global style: standard controls (buttons, combos, radios,
    checkboxes, text fields) are coherent BY DEFAULT, so a new dialog can no
    longer forget to be styled. `_tooltip_style` and `_scrollbar_style` used
    to be written right here; they moved to theme.py with the rest.

    The name survives because the two capture harnesses import it
    (scripts/capture_ui_screenshots.py, scripts/screenshot_modals.py): they
    must render exactly what main.py applies, so they follow this indirection
    instead of reaching for app_qss themselves.
    """
    return app_qss(c)


def _apply_os_color_scheme(app: QApplication, is_dark: bool) -> None:
    """Imposes the app's Qt color scheme (dark/light) INDEPENDENTLY of the
    OS theme. Qt 6.8+: `QStyleHints.setColorScheme`. On a too
    old version or failure, we silently ignore it (the Direction B palette already
    set covers the essentials)."""
    try:
        scheme = Qt.ColorScheme.Dark if is_dark else Qt.ColorScheme.Light
        app.styleHints().setColorScheme(scheme)
    except Exception:
        pass


def main():
    # Windows: dissociate from python.exe so that the app's icon (and not
    # Python's) appears in the taskbar when running via python.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "Promptuino.PromptuinoUI")
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("PromptuinoUI")

    # Bibliothèque de composants déclarés par l'utilisateur : chargée UNE fois
    # et injectée dans le registre en mémoire, que le catalogue et le câblage
    # consultent (jamais le disque). load() dégrade déjà en [] sur fichier
    # corrompu/illisible ; le try/except est une deuxième couche défensive,
    # au cas où une régression future y ferait fuiter une exception — ce
    # point est avant toute fenêtre, une exception ici tuerait l'app entière.
    try:
        from ui.declared_components import load as _load_declared, set_registry
        set_registry(_load_declared())
    except Exception:
        pass

    # Library preferences: same discipline as the declared components — loaded
    # ONCE into an in-memory registry that the generation path reads, never the
    # disk. Wrapped for the SAME reason as the block above, which is not
    # decoration: we are before any window AND before crash_log.install()
    # poses the excepthooks (below), so an exception leaking out of a
    # future regression here would kill the app with no trace at all.
    try:
        from ui.component_libs import load as _load_libs, set_registry as _set_libs
        _set_libs(_load_libs())
    except Exception:
        pass

    # Journal de plantage LOCAL (TODO #72 : la télémétrie a été retirée le
    # 2026-08-28, ceci n'envoie rien nulle part). Posé AVANT la création des
    # widgets : sans excepthook, une exception non rattrapée ne laisserait
    # aucune trace, et le Studio ne pourrait pas se déverrouiller (#49).
    crash_log.install()

    # Proxy style: info icon of QMessageBox in GREEN (instead of the native blue).
    # Set BEFORE palette/stylesheet; delegates everything else to the default style.
    app.setStyle(_GreenInfoStyle())

    # Restore the theme from the last session (default: dark) BEFORE setting
    # palette/stylesheet so that the app starts directly in the right theme.
    # Emitted without a listener here (the widgets don't exist yet) -> safe no-op.
    if not session.theme_is_dark:
        theme_manager.apply_light()

    # Restore the language the SAME way, and for the same reason: both are
    # app-wide preferences. Only the theme was ever persisted, so anyone
    # reading English, Spanish or Italian had to pick their language again at
    # every launch. Done here, before any widget exists, so nothing has to be
    # re-translated afterwards. `set_language` ignores an unknown code, which
    # is what makes a hand-edited or stale session file degrade to French
    # instead of raising.
    lang_manager.set_language(session.language)
    lang_manager.changed.connect(
        lambda *_: setattr(session, "language", lang_manager.lang))

    # Decoupling app theme / OS theme: we explicitly impose the Qt color
    # scheme (DARK by default, cf. theme_manager) instead of following the
    # light/dark setting of Windows. Without this, the native Windows 11 style tints
    # certain unstyled elements (window frames, combo popups,
    # QMessageBox…) according to the system theme. Updated on the light/dark toggle.
    _apply_os_color_scheme(app, theme_manager.is_dark)
    # App icon (taskbar / title): the « Prompt>uino » logo with
    # its background (visible on any taskbar).
    app.setWindowIcon(QIcon(str(
        Path(__file__).resolve().parent / "assets" / "logo" / "icon-dark.svg")))

    # Fonts (spec §5/§6): loads Geist/JetBrains Mono if present in
    # assets/fonts/, otherwise system fallback (Segoe UI Variable Display / Cascadia).
    # Sets the app's default UI family before creating the widgets.
    setup_fonts(app)

    # Global palette (Direction B foundation, spec §2/§7 P0): set BEFORE the
    # creation of the widgets so that they inherit it. Widgets that set their
    # own palette/QSS take precedence.
    app.setPalette(build_app_palette(theme_manager.current))

    # Global style: tooltips + scrollbars (both need to be
    # set at the QApplication level to apply everywhere). The QToolTip
    # palette is updated in addition to the stylesheet for the rich-text mode
    # (see _apply_tooltip_palette).
    app.setStyleSheet(_app_style(theme_manager.current))
    _apply_tooltip_palette(theme_manager.current)
    def _on_theme_changed(c: ColorScheme) -> None:
        app.setPalette(build_app_palette(c))
        app.setStyleSheet(_app_style(c))
        _apply_tooltip_palette(c)
        _apply_os_color_scheme(app, theme_manager.is_dark)
        session.theme_is_dark = theme_manager.is_dark   # persists the choice
    theme_manager.changed.connect(_on_theme_changed)

    # Auto-hidden scrollbars: invisible at rest, visible during a
    # scroll + 1.5 s. Their space stays reserved to avoid any
    # resizing on appearance / disappearance.
    install_global_auto_hide(app)

    # Hand cursor on every ENABLED button, app-wide. Kept on `app` so the
    # filter outlives this function -- a collected event filter stops
    # filtering, silently.
    app._button_cursors = install_button_cursors(app)

    # First launch (ONNX model absent): download via dialog.
    # If the user cancels, we quit without error.
    if not ensure_model_or_exit(app):
        return

    # First launch: ask where to store projects & libraries.
    # If the user closes without confirming, we quit the app.
    if not session.is_workspace_root_configured():
        welcome = WelcomeDialog()
        if welcome.exec() != QDialog.DialogCode.Accepted:
            return

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
