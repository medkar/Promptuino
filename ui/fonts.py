"""Font loading (Phase 2 §5/§6).

Policy: **system fallback first**. Embedded fonts are loaded if present
(placed in ``assets/fonts/``), otherwise the app uses system fonts:

- UI   : Geist (if embedded) -> Segoe UI Variable Display -> Segoe UI -> system-ui
- Mono : JetBrains Mono (if embedded) -> Cascadia Mono -> Cascadia Code -> Consolas

To enable Geist / JetBrains Mono: drop the ``.ttf``/``.otf`` files into
``assets/fonts/`` (see the folder README). No other change required —
``setup_fonts()`` loads them at startup and Qt resolves the first available family.
"""
from pathlib import Path

from PyQt6.QtGui import QFont, QFontDatabase

_FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"

# Target families, preferred -> fallbacks. Qt picks the first available (embedded
# OR system).
_UI_STACK = ["Geist", "Segoe UI Variable Display", "Segoe UI"]
_MONO_STACK = ["JetBrains Mono", "Cascadia Mono", "Cascadia Code", "Consolas"]

# Mono stack ready to paste into a QSS sheet (``font-family: {MONO_CSS}``).
MONO_CSS = "'JetBrains Mono', 'Cascadia Mono', 'Cascadia Code', Consolas, monospace"


def _load_embedded() -> None:
    """Recursively loads .ttf/.otf from assets/fonts/ (subdirectories
    included — archives can be extracted as-is). Skips VARIABLE fonts
    (`*VariableFont*`, `*[wght]*`) in favor of statics, and .woff2.
    No-op if the directory is absent."""
    if not _FONTS_DIR.is_dir():
        return
    for f in sorted(_FONTS_DIR.rglob("*")):
        if f.suffix.lower() not in (".ttf", ".otf"):
            continue
        if "VariableFont" in f.name or "[" in f.name:
            continue
        QFontDatabase.addApplicationFont(str(f))


def setup_fonts(app) -> None:
    """Loads embedded fonts (if present) then sets the application default UI
    font to the first available family from ``_UI_STACK``.

    Only the **family** is changed (not the size) to avoid any layout shift:
    sizes remain controlled by QSS in ``pt`` (spec §6)."""
    _load_embedded()
    available = set(QFontDatabase.families())
    ui_family = next((f for f in _UI_STACK if f in available), None)
    if ui_family is not None:
        base = app.font()
        base.setFamily(ui_family)
        app.setFont(base)


def mono_font(point_size: int) -> QFont:
    """Monospace QFont from ``_MONO_STACK`` (for widgets that set their font
    via QFont rather than QSS, e.g. the code editor)."""
    f = QFont()
    f.setFamilies(_MONO_STACK)
    f.setPointSize(point_size)
    f.setStyleHint(QFont.StyleHint.Monospace)
    return f


def mono_caps_font(point_size: int) -> QFont:
    """QFont for section headers in the "PROMPT IA" style (spec §6):
    rendered in ALL CAPS (without modifying the underlying text) + letter-spacing
    108% — both impossible in QSS, hence the QFont (cf. gap §5)."""
    f = mono_font(point_size)
    f.setCapitalization(QFont.Capitalization.AllUppercase)
    f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 108)
    return f
