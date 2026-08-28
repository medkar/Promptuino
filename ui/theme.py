"""
Centralized theme system.
Changing the values here is enough to alter the global appearance.
"""

# Shared height between the topbar and the sidebar logo cell
HEADER_H = 64
from dataclasses import dataclass
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QPalette, QColor


@dataclass
class ColorScheme:
    # ── Backgrounds ────────────────────────────────────────────
    sidebar_bg:     str   # shared sidebar + topbar background
    topbar_bg:      str   # alias of sidebar_bg (same value)
    main_bg:        str   # content area background
    surface:        str   # cards, panels, prompt field, inputs
    code_bg:        str   # code editor background (darkest)

    # ── Text ───────────────────────────────────────────────────
    text_primary:   str   # primary text, titles
    text_secondary: str   # secondary text, labels, metadata
    disabled_text:  str   # disabled text (grayed-out sections)

    # ── Accent & signal ────────────────────────────────────────
    # signal_ok (#00d9a0 phosphor) = EXCLUSIVELY the "it works" states
    # (compile OK, upload OK, port detected, lib installed…). Never the
    # primary button (cf. btn_primary_*). It's the semantic accent, not decorative.
    accent:         str   # alias of signal_ok (consistency with the existing)
    signal_ok:      str   # OK statuses only
    signal_error:   str   # KO / error statuses (badges §3) — theme-aware
    signal_warn:    str   # warning / manual statuses

    # ── Navigation ─────────────────────────────────────────────
    nav_active_bg:     str  # active item background (very dark phosphor tint)
    nav_active_border: str  # 2 px left bar of the active item
    nav_active_text:   str  # active item text
    nav_hover_bg:      str  # hover background
    nav_text:          str  # inactive items text

    # ── Buttons ────────────────────────────────────────────────
    btn_primary_bg:    str  # primary button background (inverted relative to the mode)
    btn_primary_text:  str  # primary button text
    btn_primary_hover: str  # primary button background on hover
    topbar_btn_text:   str  # topbar buttons icons / text
    topbar_btn_hover:  str  # topbar button background on hover

    # ── Borders & inputs ───────────────────────────────────────
    border:         str   # general borders, separators
    input_bg:       str   # input fields background, prompt area (= surface)


# ─── Dark theme (default) ─────────────────────────────────────────────────────
DARK = ColorScheme(
    # Backgrounds
    sidebar_bg      = "#0a0e14",
    topbar_bg       = "#0a0e14",   # = sidebar_bg
    main_bg         = "#10141d",
    surface         = "#161b26",
    code_bg         = "#0d1117",

    # Text
    text_primary    = "#e6edf7",
    text_secondary  = "#7d8898",
    disabled_text   = "#495568",

    # Accent & signal
    accent          = "#00d9a0",   # = signal_ok
    signal_ok       = "#00d9a0",
    signal_error    = "#e57373",   # KO red (spec §3 badges)
    signal_warn     = "#f59e0b",   # warning amber

    # Navigation
    nav_active_bg     = "#1c2a2a",
    nav_active_border = "#00d9a0",
    nav_active_text   = "#e6edf7",
    nav_hover_bg      = "#13192a",
    nav_text          = "#7d8898",

    # Buttons (primary inverted: light on dark background)
    btn_primary_bg    = "#e6edf7",
    btn_primary_text  = "#0a0e14",
    btn_primary_hover = "#cdd5e0",
    topbar_btn_text   = "#c5d0e0",
    topbar_btn_hover  = "#161b26",

    # Borders & inputs
    border          = "#1f2735",
    input_bg        = "#161b26",   # = surface
)

# ─── Light theme ──────────────────────────────────────────────────────────────
LIGHT = ColorScheme(
    # Backgrounds
    sidebar_bg      = "#f1f3f7",
    topbar_bg       = "#f1f3f7",   # = sidebar_bg
    main_bg         = "#ffffff",
    surface         = "#f7f8fa",
    code_bg         = "#f4f6f8",

    # Text
    text_primary    = "#0a0e14",
    text_secondary  = "#4b5563",
    disabled_text   = "#9ca3af",

    # Accent & signal
    accent          = "#008f6f",   # = signal_ok
    signal_ok       = "#008f6f",
    signal_error    = "#c62828",   # KO red (spec §3 badges)
    signal_warn     = "#b45309",   # warning amber

    # Navigation
    nav_active_bg     = "#e8f5f0",
    nav_active_border = "#008f6f",
    nav_active_text   = "#0a0e14",
    nav_hover_bg      = "#eaedf2",
    nav_text          = "#4b5563",

    # Buttons (primary inverted: dark on light background)
    btn_primary_bg    = "#0a0e14",
    btn_primary_text  = "#ffffff",
    btn_primary_hover = "#1f2735",
    topbar_btn_text   = "#4b5563",
    topbar_btn_hover  = "#e4e7ec",

    # Borders & inputs
    border          = "#e4e7ec",
    input_bg        = "#f7f8fa",   # = surface
)


# ─── Global QApplication palette (Direction B foundation, spec §2/§7 P0) ───────
def build_app_palette(c: ColorScheme) -> QPalette:
    """Application default palette, mapped onto the tokens (spec §2).

    Only lays down consistent defaults for NON-styled widgets
    (dialogs, combos, menus, text selection…). Widgets that set their
    own QPalette/QSS take precedence — so zero regression on the existing, just a
    Direction B baseline where there were only the system defaults.
    """
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window,          QColor(c.main_bg))
    pal.setColor(QPalette.ColorRole.WindowText,      QColor(c.text_primary))
    pal.setColor(QPalette.ColorRole.Base,            QColor(c.input_bg))
    pal.setColor(QPalette.ColorRole.AlternateBase,   QColor(c.surface))
    pal.setColor(QPalette.ColorRole.Text,            QColor(c.text_primary))
    pal.setColor(QPalette.ColorRole.Button,          QColor(c.btn_primary_bg))
    pal.setColor(QPalette.ColorRole.ButtonText,      QColor(c.btn_primary_text))
    # App-wide selection highlight = the SAME phosphor green as the prompt
    # field (selection_bg), so every default Qt selection (list/tree/table
    # views, etc.) matches the prompt instead of the old pale nav_active_bg.
    pal.setColor(QPalette.ColorRole.Highlight,       selection_qcolor(c))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(c.text_primary))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(c.text_secondary))
    pal.setColor(QPalette.ColorRole.Mid,             QColor(c.border))
    pal.setColor(QPalette.ColorRole.Light,           QColor(c.surface))
    # Disabled states: grayed-out text (spec §6, disabled_text).
    dis = QPalette.ColorGroup.Disabled
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText,
                 QPalette.ColorRole.ButtonText):
        pal.setColor(dis, role, QColor(c.disabled_text))
    return pal


def context_menu_qss(c: ColorScheme) -> str:
    """QSS for a QMenu (context menus). Applied BOTH at the QApplication level
    (baseline) AND directly on every created menu.

    Why both: on Windows, as soon as an app stylesheet is active, Qt
    renders QMenus through the stylesheet engine; a menu created by a widget that
    has ITS own stylesheet (the code editor) does not always inherit the
    global QMenu rule → panel with no background → TRANSPARENT popup. Styling the menu
    directly (`menu.setStyleSheet(context_menu_qss(...))`) guarantees an opaque
    background, as the menu bar already does. Same tokens everywhere."""
    return f"""
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
        QMenu::item:disabled {{
            color: {c.disabled_text};
        }}
        QMenu::separator {{
            height: 1px;
            background: {c.border};
            margin: 4px 8px;
        }}
    """


# ─── Unified control styling (buttons / radios / checkboxes) ──────────────────
# Agreed rule (dark / light):
#  - PRIMARY button: filled (white in dark / black in light) -> solid GREEN on hover.
#  - SECONDARY button: outline (white outline in dark / gray in light, transparent
#    background) -> GREEN border + text (+ icon) on hover.
#  - Radios / checkboxes: outline indicator (white in dark / gray in light) -> GREEN
#    on hover AND checked (solid green + white checkmark).
# Centralized here so that views AND modals share EXACTLY the same rendering.
from pathlib import Path as _Path

_CHECK_WHITE_URL = (_Path(__file__).parent / "check_white.svg").as_posix()
# Dropdowns "v" chevron (QSS image -> not recolorable, hence a per-theme
# variant). Secondary gray, legible on the input background in dark as in light.
_CHEVRON_DARK_URL = (_Path(__file__).parent / "chevron_down_dark.svg").as_posix()
_CHEVRON_LIGHT_URL = (_Path(__file__).parent / "chevron_down_light.svg").as_posix()


def _outline_color(c: ColorScheme) -> str:
    """Color of the "outline" (secondary border + unchecked indicators):
    white in dark, gray in light (cf. agreed rule)."""
    return c.text_primary if c is DARK else c.text_secondary


def primary_button_qss(c: ColorScheme, *, selector: str = "QPushButton",
                       font_pt: int = 10, padding: str = "7px 22px",
                       radius: int = 6, text_align: str | None = None) -> str:
    """PRIMARY button: filled (btn_primary_bg) -> GREEN (signal_ok) on hover.

    `text_align`: Qt centres a button's label by default, and the only way to
    change that is CSS -- there is no widget-level setter. The parameter exists
    so a left-aligned primary button (« Nouveau projet », whose icon sits at
    the left) does not have to re-declare the whole recipe just for one line.
    `None` emits nothing, so the default output is unchanged.
    """
    align = f"\n            text-align: {text_align};" if text_align else ""
    return f"""
        {selector} {{
            background-color: {c.btn_primary_bg};
            color: {c.btn_primary_text};
            border: 1px solid {c.btn_primary_bg};
            border-radius: {radius}px;
            font-size: {font_pt}pt; font-weight: 600;
            padding: {padding};{align}
        }}
        {selector}:hover {{
            background-color: {c.signal_ok};
            border-color: {c.signal_ok};
            color: {c.btn_primary_text};
        }}
        {selector}:disabled {{
            background-color: {c.surface};
            border-color: {c.surface};
            color: {c.disabled_text};
        }}
    """


def secondary_button_qss(c: ColorScheme, *, selector: str = "QPushButton",
                         font_pt: int = 10, padding: str = "7px 18px",
                         radius: int = 6) -> str:
    """SECONDARY button: transparent outline (white/gray border) -> GREEN
    border + text on hover. (Any icon is recolored by
    install_icon_hover: QSS cannot recolor a QIcon.)"""
    line = _outline_color(c)
    return f"""
        {selector} {{
            background-color: transparent;
            color: {line};
            border: 1px solid {line};
            border-radius: {radius}px;
            font-size: {font_pt}pt; font-weight: 600;
            padding: {padding};
        }}
        {selector}:hover {{
            border-color: {c.signal_ok};
            color: {c.signal_ok};
        }}
        {selector}:disabled {{
            background-color: transparent;
            color: {c.disabled_text};
            border-color: {c.border};
        }}
    """


def destructive_button_qss(c: ColorScheme, *, selector: str = "QPushButton",
                           font_pt: int = 10, padding: str = "7px 18px",
                           radius: int = 6) -> str:
    """DESTRUCTIVE button: same outline shape as `secondary_button_qss`, but
    ROUGE au repos comme au survol.

    Le vert au survol est la convention de tous les autres controles (cf.
    `secondary_button_qss`) : il dit « continue ». Une suppression ne doit
    jamais l'emprunter, sinon le geste le plus irreversible de l'ecran se
    presente comme les autres. Le rouge est donc porte des le repos, pas
    seulement au survol -- l'utilisateur doit le voir AVANT d'approcher la
    souris, pas au moment ou il clique.
    """
    return f"""
        {selector} {{
            background-color: transparent;
            color: {c.signal_error};
            border: 1px solid {c.signal_error};
            border-radius: {radius}px;
            font-size: {font_pt}pt; font-weight: 600;
            padding: {padding};
        }}
        {selector}:hover {{
            background-color: {c.signal_error};
            color: {c.main_bg};
            border-color: {c.signal_error};
        }}
        {selector}:disabled {{
            background-color: transparent;
            color: {c.disabled_text};
            border-color: {c.border};
        }}
    """


def radio_checkbox_qss(c: ColorScheme, *, font_pt: int = 10,
                       font_weight: int | None = None,
                       indicator_px: int = 16) -> str:
    """Radios + checkboxes: outline indicator (white/gray) -> GREEN on hover and
    checked (solid green + white checkmark for checkboxes, green dot for radios).

    `font_weight` and `indicator_px` exist because four call sites appended the
    SAME two extra rules by hand (`font-weight: 700` on a big radio, a 14 px
    compact indicator). Passing them keeps the recipe in one place.

    ⚠️ `font_weight=None` (the default) emits NO declaration at all, rather
    than a nominal `400`. This helper feeds `app_qss`, so declaring a weight by
    default would stop every radio in the app from inheriting its parent's --
    a silent change of behaviour in exchange for a cosmetic default. Absent
    parameters must produce the previous output byte for byte.
    """
    line = _outline_color(c)
    # A radius that keeps following the indicator size: hard-coding 9/4 px
    # would turn a 14 px checkbox into a different shape than a 16 px one.
    radius_radio = indicator_px // 2 + 1
    radius_check = max(3, indicator_px // 4)
    poids = f"\n            font-weight: {font_weight};" if font_weight else ""
    return f"""
        QRadioButton, QCheckBox {{
            background-color: transparent;
            color: {c.text_primary};
            spacing: 8px;
            font-size: {font_pt}pt;{poids}
        }}
        QRadioButton::indicator {{
            width: {indicator_px}px; height: {indicator_px}px;
            border-radius: {radius_radio}px;
            border: 2px solid {line};
            background-color: transparent;
        }}
        QCheckBox::indicator {{
            width: {indicator_px}px; height: {indicator_px}px;
            border-radius: {radius_check}px;
            border: 2px solid {line};
            background-color: transparent;
        }}
        QRadioButton::indicator:unchecked:hover,
        QCheckBox::indicator:unchecked:hover {{
            border-color: {c.signal_ok};
        }}
        QRadioButton::indicator:checked {{
            border-color: {c.signal_ok};
            background-color: {c.signal_ok};
        }}
        QCheckBox::indicator:checked {{
            border-color: {c.signal_ok};
            background-color: {c.signal_ok};
            image: url({_CHECK_WHITE_URL});
        }}
        QRadioButton:disabled, QCheckBox:disabled {{ color: {c.disabled_text}; }}
        QRadioButton::indicator:disabled, QCheckBox::indicator:disabled {{
            border-color: {c.border};
        }}
    """


def dialog_controls_qss(c: ColorScheme) -> str:
    """Ready-to-apply QSS for a modal: radios + checkboxes + buttons (secondary by
    default, primary via the dynamic property `variant="primary"`). Mark the
    main button: `btn.setProperty("variant", "primary")` BEFORE show."""
    return (
        radio_checkbox_qss(c)
        + secondary_button_qss(c)
        + primary_button_qss(c, selector='QPushButton[variant="primary"]')
    )


def combo_qss(c: ColorScheme, *, arrow: bool = True, bg: str | None = None,
              font_pt: int = 10, padding: str = "0 14px", radius: int = 6) -> str:
    """QSS for a QComboBox consistent with the app (= the Board "Model" field):
    input background, GREEN border on hover/focus, themed popup (light green hover,
    solid green selection).

    `arrow=False` removes the arrow (0 px drop-down zone): a simple click on
    the field still drops the list (true for a non-editable QComboBox —
    the whole frame acts as a button, independently of the arrow sub-zone).
    `bg` = background color of the closed field (default input_bg); pass e.g.
    `c.code_bg` when the combo sits on a `surface` card (= input_bg) to
    make it stand out."""
    field_bg = bg if bg is not None else c.input_bg
    if arrow:
        # "v" chevron consistent on ALL dropdowns (the QSS on ::drop-down
        # hides the native arrow -> we provide our own image).
        chevron = _CHEVRON_DARK_URL if c is DARK else _CHEVRON_LIGHT_URL
        dropdown = (
            "QComboBox::drop-down { border: none; width: 26px;"
            " subcontrol-origin: padding; subcontrol-position: center right; }"
            f"QComboBox::down-arrow {{ image: url({chevron});"
            " width: 14px; height: 14px; }"
        )
    else:
        dropdown = (
            "QComboBox::drop-down { border: none; width: 0px; }"
            "QComboBox::down-arrow { image: none; width: 0px; height: 0px; }"
        )
    return f"""
        QComboBox {{
            background-color: {field_bg};
            color: {c.text_primary};
            border: 1px solid {c.border};
            border-radius: {radius}px;
            font-size: {font_pt}pt;
            padding: {padding};
        }}
        QComboBox:hover {{ border-color: {c.signal_ok}; }}
        QComboBox:focus {{ border-color: {c.signal_ok}; }}
        QComboBox:disabled {{
            color: {c.disabled_text};
            background-color: {field_bg};
        }}
        {dropdown}
        QComboBox QAbstractItemView {{
            background-color: {c.input_bg};
            color: {c.text_primary};
            border: 1px solid {c.border};
            selection-background-color: {selection_bg(c)};
            selection-color: {c.text_primary};
            outline: none;
            padding: 4px;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 6px 10px;
            border-radius: 6px;
        }}
        /* ACTIVE (selected) value: GREEN bar (signal_ok at 32%), not the
           native blue. */
        QComboBox QAbstractItemView::item:selected {{
            background-color: {selection_bg(c)};
            color: {c.text_primary};
        }}
        /* Hover on a non-active value: GREEN text, NO background change.
           Declared after :selected to take precedence over it when a hovered item is
           also marked selected (the list follows the mouse). */
        QComboBox QAbstractItemView::item:hover {{
            background-color: transparent;
            color: {c.signal_ok};
        }}
        /* Disabled item (e.g. ESP32 "coming soon"): grayed out, no
           background on hover. Declared LAST to take precedence over :hover when a
           disabled item is hovered (equal specificity -> the last rule
           wins). The tooltip stays shown on hover. */
        QComboBox QAbstractItemView::item:disabled {{
            color: {c.disabled_text};
            background-color: transparent;
        }}
    """


def input_qss(c: ColorScheme, *, font_pt: int = 10, padding: str = "6px 10px",
              radius: int = 6, font_family: str | None = None) -> str:
    """Text fields (QLineEdit + QSpinBox) consistent with combo_qss: input_bg
    fill, themed border, GREEN border on hover AND focus. Before this helper
    the same style was hand-rolled 9 times across 8 files, each with its own
    borders/padding -- the direct cause of the "not the same everywhere"
    feeling. QSpinBox shares the rule (it IS a line edit with buttons); its
    native up/down arrows are left untouched.

    `font_family` for the one field that types CODE rather than prose (the
    serial monitor's send box): everything else about it is the same field, so
    it takes the same rule instead of a tenth private copy."""
    family = f"\n            font-family: {font_family};" if font_family else ""
    return f"""
        QLineEdit, QSpinBox {{
            background-color: {c.input_bg};
            color: {c.text_primary};
            border: 1px solid {c.border};
            border-radius: {radius}px;
            font-size: {font_pt}pt;
            padding: {padding};{family}
        }}
        QLineEdit:hover, QSpinBox:hover {{ border-color: {c.signal_ok}; }}
        QLineEdit:focus, QSpinBox:focus {{ border-color: {c.signal_ok}; }}
        QLineEdit:disabled, QSpinBox:disabled {{
            color: {c.disabled_text};
            background-color: {c.input_bg};
        }}
    """


def bare_button_qss(c: ColorScheme, *, radius: int = 6) -> str:
    """BARE button (icon-only): transparent, borderless, green text/hover like
    every other control. Opt-out for buttons that must NOT take the global
    secondary default (toolbar icons, inline pencils/gears...):
    `btn.setProperty("variant", "bare")` BEFORE the first show.

    `padding: 0` for the same reason as `help_button_qss`: these buttons are
    typically fixed-size and tiny (14x14 pencils), so any inherited padding
    would clip their icon. There is no border and no background here, so
    padding would buy nothing anyway."""
    return f"""
        QPushButton[variant="bare"] {{
            background-color: transparent;
            color: {c.text_secondary};
            border: none;
            border-radius: {radius}px;
            padding: 0;
        }}
        QPushButton[variant="bare"]:hover {{ color: {c.signal_ok}; }}
        QPushButton[variant="bare"]:disabled {{ color: {c.disabled_text}; }}
    """


def icon_button_qss(c: ColorScheme, *, radius: int = 6,
                    hover_bg: str | None = None) -> str:
    """ICON-ONLY action button of a card (pencil, ⋯, …): transparent and
    borderless at rest, TINTED BACKGROUND on hover.

    Distinct from `bare_button_qss`, and the difference is load-bearing: the
    bare variant recolors the TEXT on hover and has no background at all.
    These buttons carry a QIcon -- which QSS cannot recolor, hence the
    companion `install_icon_hover` -- so the background tint is their ONLY
    hover affordance. Swapping them to `variant="bare"` would silently remove
    it (measured 2026-08-11).

    No `padding: 0` here, deliberately: measured on 22/26/28/32 px buttons,
    the global default does NOT shift a QIcon -- the clipping trap of
    `help_button_qss` only bites on a fixed-size button whose content is a
    TEXT glyph (cf. scripts/test_fixed_size_button_glyphs.py).
    """
    hover = hover_bg or c.nav_hover_bg
    return f"""
        QPushButton {{
            background: transparent;
            border: none;
            border-radius: {radius}px;
        }}
        QPushButton:hover {{ background-color: {hover}; }}
    """


def filter_pill_qss(c: ColorScheme, *, checked: bool = False,
                    disabled: bool = False,
                    padding: str = "3px 12px") -> str:
    """FILTER PILL (« Tous », « Perso », « Avec bibliothèque »...): small
    rounded toggle of a filter bar.

    Written three times by hand -- `components_view` and `library_view` were
    byte-identical, `projects_view` differed only by its padding. Hence
    `padding=` as a parameter: unifying it to the majority value would widen
    each projects_view pill by 4 px (measured `sizeHint`), i.e. a redesign,
    which this refactor forbids.

    `checked`: the selected pill fills with the phosphor tint.

    `disabled`: the « coming soon » look (ESP32) -- greyed label, and NO hover
    rule at all. It is NOT obtained by disabling the widget: these buttons must
    stay ENABLED for their "Coming soon" tooltip to appear on hover, so the
    state lives in a Python flag. Passing it here rather than hand-writing the
    block keeps that flag visible at the call site (`disabled=self._coming_soon`)
    while removing the third copy of the same CSS.
    """
    if disabled:
        return f"""
            QPushButton {{
                background: transparent;
                color: {c.disabled_text};
                border: 1px solid {c.border};
                border-radius: 4px;
                font-size: 9pt; font-weight: 500;
                padding: {padding};
            }}
        """
    if checked:
        return f"""
            QPushButton {{
                background-color: {c.nav_active_bg};
                color: {c.signal_ok};
                border: 1px solid {c.signal_ok};
                border-radius: 4px;
                font-size: 9pt; font-weight: 600;
                padding: {padding};
            }}
        """
    return f"""
        QPushButton {{
            background: transparent;
            color: {c.text_primary};
            border: 1px solid {c.border};
            border-radius: 4px;
            font-size: 9pt; font-weight: 500;
            padding: {padding};
        }}
        QPushButton:hover {{
            border-color: {c.signal_ok};
            color: {c.signal_ok};
        }}
    """


def chip_button_qss(c: ColorScheme, *, bg: str | None = None) -> str:
    """« + Attach » CHIP: small outlined chip that tints to phosphor on hover,
    floating over a text area.

    Written twice -- over the chat's input bar and over the Studio's prompt
    field -- and the comments of both sites already claimed they were the same
    element. The only real difference is the background, and it is NOT
    cosmetic: each chip sits on a different surface (the chat bar's `surface`,
    the prompt field's `code_bg`) and must blend into it. Hence `bg=` rather
    than one imposed value; unifying them would make one of the two float on
    a patch of the wrong colour.

    The `:disabled` state is deliberately part of the recipe: the chat's chip
    is switched off during a whole streaming answer, and without the rule it
    stayed painted exactly like a live button (measured 0 % difference).
    """
    return f"""
        QPushButton {{
            background-color: {bg if bg is not None else c.surface};
            color: {c.text_secondary};
            border: 1px solid {c.border};
            border-radius: 4px;
            padding: 2px 8px;
            font-size: 9pt;
        }}
        QPushButton:hover {{
            color: {c.signal_ok};
            border-color: {c.signal_ok};
        }}
        QPushButton:disabled {{
            color: {c.disabled_text};
            border-color: {c.border};
        }}
    """


def slider_qss(c: ColorScheme) -> str:
    """HORIZONTAL SLIDER: 2 px rail, phosphor-filled left side, square handle
    outlined in phosphor.

    Written twice, byte-identical up to whitespace (the Studio's « comments »
    slider and the AI tab's context slider). It stayed duplicated longer than
    the buttons for a mechanical reason: `QSlider` is NOT in the guard's
    `_CONTROL_QSS_RE`, so nothing made the copy visible -- and nothing would
    have stopped a third one.
    """
    return f"""
        QSlider::groove:horizontal {{
            background: {c.border};
            height: 2px;
            border-radius: 1px;
        }}
        QSlider::sub-page:horizontal {{
            background: {c.signal_ok};
            border-radius: 1px;
        }}
        QSlider::handle:horizontal {{
            background: {c.btn_primary_bg};
            border: 2px solid {c.signal_ok};
            width: 12px; height: 12px;
            margin: -5px 0;
            border-radius: 2px;
        }}
    """


def darken(hex_color: str, factor: float = 0.82) -> str:
    """Darken a #rrggbb color. Used for the pressed/hover state of the filled
    green controls, which cannot go greener."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"#{int(r * factor):02x}{int(g * factor):02x}{int(b * factor):02x}"


def selected_button_qss(c: ColorScheme, *, selector: str = "QPushButton") -> str:
    """SELECTED button: solid GREEN, white text, darker on hover. Carries the
    app-wide convention « green = the active choice » (checked boxes, chosen
    tiles). Same metrics as `secondary_button_qss` on purpose, so a button
    keeps its size when it becomes selected."""
    green = c.signal_ok
    hover = darken(green)
    return f"""
        {selector} {{
            background-color: {green};
            color: #ffffff;
            border: 1px solid {green};
            border-radius: 6px;
            font-size: 10pt; font-weight: 600;
            padding: 7px 18px;
        }}
        {selector}:hover {{
            background-color: {hover};
            border-color: {hover};
        }}
    """


def danger_button_qss(c: ColorScheme, *, selector: str = "QPushButton",
                      font_weight: int = 700) -> str:
    """FILLED red button: « Remplacer » in the overwrite dialog, and the
    « Annuler » that stops a running compilation.

    Distinct from `destructive_button_qss` (outline red), and deliberately so:
    that one MARKS a risky action among ordinary ones, this one INTERRUPTS --
    it has to be the loudest thing on screen at that moment. The two coexist
    on purpose; what did not have to coexist was the same filled red written
    out twice by hand in studio_view, with two different font weights.

    Colors are literal rather than theme tokens because the meaning is fixed:
    a stop button must stay red in both themes."""
    return f"""
        {selector} {{
            background-color: #ef4444;
            color: #ffffff;
            border: none; border-radius: 8px;
            font-size: 10pt; font-weight: {font_weight};
            padding: 0 20px;
        }}
        {selector}:hover {{ background-color: #dc2626; }}
    """


def log_action_button_qss(c: ColorScheme) -> str:
    """Call-to-action inside the console (« voir les corrections », « demander
    de l'aide »): a filled light block that pops against the log, GREEN on
    hover like every other control.

    Left-aligned and bold on purpose: these labels are sentences, not verbs,
    so centring them reads as a title rather than a button.

    NOTE: the resting fill is a hard-coded white rather than a theme token.
    That is how it was written, and it is kept as-is here rather than silently
    redesigned -- on the light theme the console is itself light, so this
    button has little contrast. Worth revisiting when the console gets its own
    design pass; changing it now would be a redesign, which this refactor is
    explicitly not."""
    return f"""
        QPushButton[variant="logAction"] {{
            background-color: #ffffff;
            color: #1f2937;
            border: 1px solid {c.border};
            border-radius: 4px;
            padding: 6px 12px;
            font-weight: bold;
            text-align: left;
        }}
        QPushButton[variant="logAction"]:hover {{
            background-color: {c.signal_ok};
            color: #ffffff;
            border-color: {c.signal_ok};
        }}
    """


def help_button_qss(c: ColorScheme, *, size: int = 24) -> str:
    """Round green "?" button (opens the chat on this component).

    Centralized because the two ambiguity dialogs each carried their own copy,
    which had already drifted apart: 12px font on one side, 13px on the other,
    and two different hover darkenings.

    ⚠️ `padding: 0` is LOAD-BEARING, not decoration. Without it the button
    inherits the global QPushButton padding (7px 18px), which pushes the "?"
    clean outside a 24x24 fixed-size button -- the glyph simply vanishes, and
    that is exactly what happened when the global sheet was switched on.
    ANY fixed-size button must declare its own padding here.
    """
    return f"""
        QPushButton[variant="help"] {{
            background-color: {c.signal_ok};
            color: #ffffff;
            border: none;
            border-radius: {size // 2}px;
            font-weight: bold;
            font-size: 12px;
            padding: 0;
        }}
        QPushButton[variant="help"]:hover {{
            background-color: {darken(c.signal_ok)};
        }}
    """


def tooltip_qss(c: ColorScheme) -> str:
    """Tooltips. Moved here from main.py (`_tooltip_style`): theme.py is the
    single source of the global stylesheet, so that `app_qss` can be composed
    of helpers only. The tooltip PALETTE (`_apply_tooltip_palette`) stays in
    main.py -- it is palette, not QSS.

    Pure white text in dark theme to make the rendering consistent with the
    button hovers (which are already white). In light theme, we keep
    text_primary, which is the black of the current text. The selector
    `QToolTip, QToolTip *` forces the color even on the sub-elements (some
    native Qt styles ignore `color` on QToolTip alone).
    """
    text_color = "#ffffff" if c is DARK else c.text_primary
    return f"""
        QToolTip, QToolTip * {{
            background-color: {c.sidebar_bg};
            color: {text_color};
            border: 1px solid {c.border};
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 10pt;
        }}
    """


def scrollbar_qss(c: ColorScheme) -> str:
    """Modern scrollbars: thin, rounded, themable. Moved here from main.py
    (`_scrollbar_style`) for the same reason as `tooltip_qss`: theme.py is the
    single source of the global stylesheet.

    Applied globally via app.setStyleSheet: all scrollable widgets
    (QPlainTextEdit, QTextEdit, QScrollArea, QListWidget…) inherit them
    automatically.
    """
    return f"""
        QScrollBar:vertical {{
            background: transparent;
            width: 10px;
            margin: 0;
            border: none;
        }}
        QScrollBar:horizontal {{
            background: transparent;
            height: 10px;
            margin: 0;
            border: none;
        }}
        QScrollBar::handle:vertical {{
            background: {c.accent};
            border-radius: 3px;
            min-height: 30px;
            margin: 2px;
        }}
        QScrollBar::handle:horizontal {{
            background: {c.accent};
            border-radius: 3px;
            min-width: 30px;
            margin: 2px;
        }}
        QScrollBar::handle:vertical:hover,
        QScrollBar::handle:horizontal:hover {{
            background: {c.accent};
        }}
        QScrollBar::handle:vertical:pressed,
        QScrollBar::handle:horizontal:pressed {{
            background: {c.accent};
        }}
        QScrollBar::add-line:vertical,
        QScrollBar::sub-line:vertical,
        QScrollBar::add-line:horizontal,
        QScrollBar::sub-line:horizontal {{
            width: 0; height: 0; border: none; background: transparent;
        }}
        QScrollBar::add-page:vertical,
        QScrollBar::sub-page:vertical,
        QScrollBar::add-page:horizontal,
        QScrollBar::sub-page:horizontal {{
            background: transparent;
        }}
        QScrollBar:vertical:disabled,
        QScrollBar:horizontal:disabled {{
            background: transparent;
        }}
        QAbstractScrollArea::corner {{
            background: transparent;
            border: none;
        }}
    """


def app_qss(c: ColorScheme) -> str:
    """THE application-wide stylesheet (spec 2026-08-11): every standard
    control is coherent BY DEFAULT, without writing a line -- a future dialog
    can no longer "forget" to be styled. Composition of the existing helpers;
    the variant rules come AFTER the bare-QPushButton default (higher
    specificity anyway thanks to [variant=...]).

    HARD RULE (CLAUDE.md): no bare QWidget/QDialog selector here -- container
    backgrounds belong to QPalette (test_app_qss_never_paints_widget_backgrounds
    locks this)."""
    return (
        input_qss(c)
        + combo_qss(c)
        + radio_checkbox_qss(c)
        + secondary_button_qss(c)                                   # default
        + primary_button_qss(c, selector='QPushButton[variant="primary"]')
        + destructive_button_qss(c, selector='QPushButton[variant="destructive"]')
        + bare_button_qss(c)
        + help_button_qss(c)
        + log_action_button_qss(c)
        + tooltip_qss(c)
        + scrollbar_qss(c)
        + context_menu_qss(c)
        + messagebox_qss(c)
    )


# Color palette of the project features. Shared by the Projects cards and
# the Studio (dropdown, editor highlights, transfer popup) so the same
# feature keeps the same color everywhere. Studio widgets derive the color
# from the feature ID via feature_color() below — NOT from the list
# position — so reordering/deleting never recolors the survivors.
FUNCTION_PALETTE: list[str] = [
    "#5EA9FF",  # blue
    "#FF8FA3",  # pink
    "#7BD389",  # green
    "#F4B860",  # soft orange
    "#B794F4",  # purple
    "#4FD1C5",  # turquoise
    "#F687B3",  # magenta
    "#FDD663",  # yellow
]


def feature_color(feature_id: str) -> str:
    """Stable color of a feature, derived from its ID (not its position):
    "fN" ids map to palette[N-1] — a natural-order list [f1, f2, …] looks
    exactly like the historical position-based coloring, but the color now
    sticks to the feature through reorders and deletions. Exotic ids fall
    back to a deterministic byte sum (NOT hash(), salted per process)."""
    fid = (feature_id or "").strip()
    if fid.startswith("f") and fid[1:].isdigit():
        idx = max(0, int(fid[1:]) - 1)
    else:
        idx = sum(fid.encode("utf-8", "ignore"))
    return FUNCTION_PALETTE[idx % len(FUNCTION_PALETTE)]


def selection_bg(c: ColorScheme) -> str:
    """Text selection highlight color: phosphor tint (signal_ok)
    at 32%. UNIFORM everywhere (code editor, prompt field, chat input) — it's
    the agreed "darker green", vs the old too-light nav_active_bg."""
    sk = c.signal_ok.lstrip("#")
    r, g, b = int(sk[0:2], 16), int(sk[2:4], 16), int(sk[4:6], 16)
    return f"rgba({r}, {g}, {b}, 0.32)"


def selection_qcolor(c: ColorScheme) -> QColor:
    """QColor form of `selection_bg` (same phosphor tint at 32%) for APIs that
    need a QColor rather than a CSS string — notably QPalette.Highlight, which
    drives the default selection color of every Qt item view."""
    sk = c.signal_ok.lstrip("#")
    r, g, b = int(sk[0:2], 16), int(sk[2:4], 16), int(sk[4:6], 16)
    return QColor(r, g, b, 82)   # 0.32 * 255 ≈ 82


def neutral_button_qss(c: ColorScheme, *, bg: str | None = None,
                       selector: str = "QPushButton",
                       font_pt: int = 10, padding: str = "7px 18px",
                       radius: int = 6) -> str:
    """NEUTRAL button: FILLED, opaque (does NOT let the content grid show through,
    unlike the transparent outline), text_primary text (black in light),
    GREEN border + text on hover. `bg` = background color (default main_bg =
    "background color" for "Voir le schéma"/"Outils"; pass e.g.
    `c.code_bg` for "Connecter" which must blend into the console/log)."""
    _bg = bg if bg is not None else c.main_bg
    return f"""
        {selector} {{
            background-color: {_bg};
            color: {c.text_primary};
            border: 1px solid {c.border};
            border-radius: {radius}px;
            font-size: {font_pt}pt; font-weight: 600;
            padding: {padding};
        }}
        {selector}:hover {{
            border-color: {c.signal_ok};
            color: {c.signal_ok};
        }}
        {selector}:disabled {{
            background-color: {c.surface};
            color: {c.disabled_text};
            border-color: {c.border};
        }}
    """


def card_qss(c: ColorScheme, *, selected: bool = False) -> str:
    """Card selectionnable (choix de bibliotheque).

    Vit ici plutot que dans la modale pour la raison etablie par le TODO #50 :
    une recette de controle ecrite en local est une recette qui derive. L'etat
    SELECTIONNE utilise `signal_ok`, comme tout etat actif de l'app.

    Cible `QFrame#libCard` : la card est stylee par QSS SEUL, sans QPalette,
    donc sans le conflit QPalette/QSS que la regle CLAUDE.md previent — meme
    forme que les cards existantes de components_view / library_view /
    projects_view.
    """
    border = c.signal_ok if selected else c.border
    return f"""
        QFrame#libCard {{
            background-color: {c.surface};
            border: 1px solid {border};
            border-radius: 6px;
        }}
        QFrame#libCard:hover {{ border-color: {c.signal_ok}; }}
        QFrame#libCard:disabled {{ border-color: {c.border}; }}
        QFrame#libCard QLabel {{ background: transparent; border: none; }}
    """


def perso_badge_qss(c: ColorScheme) -> str:
    """Pastille « Perso » d'une fiche de composant declare par l'utilisateur.

    Vert Promptuino (`signal_ok`) : la pastille dit « c'est toi qui l'as
    decrit », pas « attention ». L'ambre est reserve aux reserves et aux
    avertissements — ici il en ferait un defaut.

    Vit ici parce que DEUX ecrans l'affichent (l'onglet « Composants » et la
    card de la modale d'ambiguite) et que c'est le seul moyen qu'ils restent
    identiques : une recette de controle ecrite en local est une recette qui
    derive (TODO #50).

    Sans selecteur : la feuille se pose DIRECTEMENT sur le QLabel de la
    pastille, sans nommer de type — un selecteur `QLabel` la ferait descendre
    sur les AUTRES libelles de la card (une feuille posee sur un conteneur
    s'applique aussi a ses descendants).

    ⚠️ « Sans selecteur » ne veut PAS dire « ce widget seul ». Qt la traite
    comme un `* { ... }` : elle descend elle aussi dans les enfants du widget
    qui la porte — reproduit le 2026-08-12, une feuille sans selecteur posee
    sur un QFrame repeint la couleur ET la bordure d'un QLabel enfant. Ici
    c'est sans consequence (une pastille est une feuille de l'arbre, elle n'a
    pas d'enfants) ; ne pas en conclure qu'on peut la poser sur un conteneur
    en croyant ne styler que lui.
    """
    return f"""
        color: {c.signal_ok};
        border: 1px solid {c.signal_ok};
        border-radius: 4px;
        padding: 1px 6px;
        font-size: 8pt; font-weight: 600;
        background-color: transparent;
    """


def messagebox_qss(c: ColorScheme) -> str:
    """Themed baseline for ALL QMessageBox (applied at the application level).
    Without it, under the native Windows style the QMessageBox show native
    gray buttons that ignore the theme. We give the background + the text + SECONDARY
    buttons (outline, green on hover) by default. A dialog that wants a
    primary button (e.g. "Continuer") sets it explicitly on that button
    (the per-widget QSS takes precedence over the app rule)."""
    return (
        f"QMessageBox {{ background-color: {c.main_bg}; }}"
        f"QMessageBox QLabel {{ color: {c.text_primary}; background: transparent; }}"
        + secondary_button_qss(c, selector="QMessageBox QPushButton",
                               padding="5px 16px")
    )


def install_icon_hover(btn, svg: str, size: int = 16, *,
                       normal_role: str = "outline",
                       hover_role: str = "signal_ok"):
    """Recolors a button's icon on hover (signal_ok green), complementing the
    QSS :hover (border + text) which cannot touch a QIcon. Also follows the
    theme change. `normal_role` = resting color: "outline" (white dark
    / gray light, default, for the outline ones), "text_secondary" or "text_primary".

    Both icons (resting + hover) are pre-rendered once — at install time and on
    each theme change — then merely SWAPPED on enter/leave. So the hover is
    instant: no SVG is rendered on the mouse event (a cold per-event render
    showed a visible lag on the first hover). Returns the filter (keep it alive)."""
    from PyQt6.QtCore import QObject, QEvent, QSize
    from . import icons as _IC

    class _IconHover(QObject):
        def __init__(self, button):
            super().__init__(button)
            self._btn = button
            self._normal_icon = None
            self._hover_icon = None
            theme_manager.changed.connect(self._rebuild)
            self._rebuild()

        def _rebuild(self, *_):
            cur = theme_manager.current
            if normal_role == "text_secondary":
                color = cur.text_secondary
            elif normal_role == "text_primary":
                color = cur.text_primary
            else:
                color = cur.text_primary if cur is DARK else cur.text_secondary
            self._normal_icon = _IC.make_icon(svg, color, size)
            # `hover_role` : phosphore par defaut ; `signal_error` pour les
            # actions DESTRUCTRICES (la croix de suppression d'un modele) --
            # un survol vert sur une corbeille promettrait le contraire de
            # ce que le clic fait.
            teinte = (cur.signal_error if hover_role == "signal_error"
                      else cur.signal_ok)
            self._hover_icon = _IC.make_icon(svg, teinte, size)
            self._btn.setIconSize(QSize(size, size))
            # Keep the icon matching the current hover state across a theme change.
            self._btn.setIcon(
                self._hover_icon if self._btn.underMouse() else self._normal_icon
            )

        def eventFilter(self, obj, ev):
            t = ev.type()
            # ⚠️ Qt delivre Enter/Leave AUSSI aux boutons desactives. Sans ce
            # garde, survoler un bouton inerte ecrasait l'icone posee par son
            # proprietaire -- constate le 2026-08-28 sur la coche << deja
            # telecharge >> de la modale de modeles, remplacee par l'icone
            # download au survol, puis laissee grise par le Leave. Un controle
            # desactive n'a d'affordance de survol nulle part.
            if not self._btn.isEnabled():
                return False
            if t == QEvent.Type.Enter:
                self._btn.setIcon(self._hover_icon)
            elif t == QEvent.Type.Leave:
                self._btn.setIcon(self._normal_icon)
            return False

    f = _IconHover(btn)
    btn.installEventFilter(f)
    return f


# ─── Theme manager ────────────────────────────────────────────────────────────
class ThemeManager(QObject):
    """Emits a signal when the theme changes. Instantiated only once at the bottom."""

    changed = pyqtSignal(object)   # emits the new ColorScheme

    def __init__(self):
        super().__init__(None)
        self._current: ColorScheme = DARK
        self._is_dark: bool = True

    @property
    def current(self) -> ColorScheme:
        return self._current

    @property
    def is_dark(self) -> bool:
        return self._is_dark

    def toggle(self):
        self._is_dark = not self._is_dark
        self._current = DARK if self._is_dark else LIGHT
        self.changed.emit(self._current)

    def apply_dark(self):
        self._is_dark = True
        self._current = DARK
        self.changed.emit(self._current)

    def apply_light(self):
        self._is_dark = False
        self._current = LIGHT
        self.changed.emit(self._current)


# Global instance — import from the other modules
theme_manager = ThemeManager()
