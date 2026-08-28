"""
Capture les écrans principaux de PromptuinoUI pour le brief de refonte visuelle.

Rend chaque vue via QWidget.grab() (pas de capture OS : plus fiable, pas de
fenêtre à amener au premier plan). Bypasse le WelcomeDialog et le check du
modèle ONNX (pas nécessaires pour le rendu de l'UI).

Sorties : docs/refonte-visuelle/*.png

Usage : python scripts/capture_ui_screenshots.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtTest import QTest

from ui import MainWindow
from ui.fonts import setup_fonts
from ui.theme import theme_manager, build_app_palette
from ui.auto_hide_scrollbar import install_global_auto_hide

# Replicates the global style from main.py for a FAITHFUL rendering. `_app_style`
# on purpose, never `theme.app_qss` directly: this harness must render what
# main.py applies TODAY, not what it will apply later -- otherwise a "before"
# capture would already show the "after" state and the comparison would be
# worthless.
from main import _app_style, _apply_tooltip_palette, _GreenInfoStyle

# The PNGs in docs/refonte-visuelle/ are TRACKED BY GIT: they are the captures
# of 2026-06-21, the dated record of the state before the Direction B redesign.
# Overwriting them would destroy evidence, so the default writes elsewhere --
# build/ is already git-ignored. Pass a directory to aim somewhere explicitly:
#     python scripts/capture_ui_screenshots.py build/avant-allumage
_OUT_ARG = (Path(sys.argv[1]) if len(sys.argv) > 1
            else ROOT / "build" / "ui-captures")
# Resolved against the repo root, so that a relative argument works from
# anywhere -- and so that the progress line below can always shorten the path.
OUT_DIR = _OUT_ARG if _OUT_ARG.is_absolute() else (ROOT / _OUT_ARG)

# (nom de fichier, tab_id, mode) — le mode n'est visible que dans Studio (console).
CAPTURES = [
    ("studio-debutant",  "console",      "beginner"),
    ("studio-avance",    "console",      "advanced"),
    ("projets",          "projets",      "advanced"),
    ("bibliotheque",     "bibliotheque", "advanced"),
    ("carte",            "carte",        "advanced"),
    ("ia",               "ia",           "advanced"),
]


def _set_mode(window, mode):
    sel = window._topbar.mode_selector
    if sel.active_mode != mode:
        sel._select(mode)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    app = QApplication(sys.argv)
    app.setApplicationName("PromptuinoUI")
    # SAME ORDER as main.py, and it matters: without setup_fonts() the embedded
    # fonts are missing and an offscreen render shows tofu boxes instead of
    # text; without the palette, container backgrounds fall back to the native
    # ones. This harness rendered NEITHER until 2026-08-11 -- so it was
    # rendering something other than the app it was supposed to document.
    app.setStyle(_GreenInfoStyle())
    setup_fonts(app)
    app.setPalette(build_app_palette(theme_manager.current))
    app.setStyleSheet(_app_style(theme_manager.current))
    _apply_tooltip_palette(theme_manager.current)
    install_global_auto_hide(app)

    window = MainWindow()
    window.resize(1280, 800)
    window.show()
    QTest.qWait(800)  # laisse le layout + _restore_last_session se stabiliser

    for theme_name in ("dark", "light"):
        if theme_name == "dark":
            theme_manager.apply_dark()
        else:
            theme_manager.apply_light()
        # Replay what main.py's `_on_theme_changed` does: the widgets listen to
        # theme_manager, but the APPLICATION palette and stylesheet do not --
        # they are re-applied by hand there, so they must be here too.
        app.setPalette(build_app_palette(theme_manager.current))
        app.setStyleSheet(_app_style(theme_manager.current))
        _apply_tooltip_palette(theme_manager.current)
        QTest.qWait(300)

        for name, tab_id, mode in CAPTURES:
            # Light theme is only useful for the 2 key screens (cf. brief).
            if theme_name == "light" and name not in ("studio-avance", "projets"):
                continue
            try:
                _set_mode(window, mode)
                window._goto_tab(tab_id)
                QTest.qWait(450)
                suffix = "" if theme_name == "dark" else "-light"
                out = OUT_DIR / f"{name}{suffix}.png"
                window.grab().save(str(out))
                shown = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
                print(f"  OK  {shown}")
            except Exception as e:  # capture best-effort, on continue
                print(f"  ERR {name} ({theme_name}): {e}")

    window.close()
    print("Terminé.")


if __name__ == "__main__":
    main()
