"""
Icônes SVG inline — style Lucide (trait fin, stroke, 24×24).
Utiliser make_icon(SVG_NAME, color, size) pour obtenir un QIcon.
"""
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtGui import QPixmap, QPainter, QIcon
from PyQt6.QtCore import Qt, QByteArray

# ─── SVG strings ──────────────────────────────────────────────────────────────
# All icons use stroke="currentColor".
# make_icon() replaces currentColor with the requested color.

HOME = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
  <polyline points="9 22 9 12 15 12 15 22"/>
</svg>"""

COMPASS = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/>
</svg>"""

TERMINAL = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="4 17 10 11 4 5"/>
  <line x1="12" y1="19" x2="20" y2="19"/>
</svg>"""

LAYOUT_DASHBOARD = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="3" y="3" width="7" height="9" rx="1"/>
  <rect x="14" y="3" width="7" height="5" rx="1"/>
  <rect x="14" y="12" width="7" height="9" rx="1"/>
  <rect x="3" y="16" width="7" height="5" rx="1"/>
</svg>"""

WRENCH = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/>
</svg>"""

LAYERS = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polygon points="12 2 2 7 12 12 22 7 12 2"/>
  <polyline points="2 17 12 22 22 17"/>
  <polyline points="2 12 12 17 22 12"/>
</svg>"""

CPU = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect x="7" y="7" width="10" height="10" rx="1"/>
  <path d="M9 7V4M12 7V4M15 7V4"/>
  <path d="M9 20v-3M12 20v-3M15 20v-3"/>
  <path d="M7 9H4M7 12H4M7 15H4"/>
  <path d="M20 9h-3M20 12h-3M20 15h-3"/>
</svg>"""

PANEL_LEFT_CLOSE = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect width="18" height="18" x="3" y="3" rx="2"/>
  <path d="M9 3v18"/>
  <path d="m16 15-3-3 3-3"/>
</svg>"""

PANEL_LEFT_OPEN = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect width="18" height="18" x="3" y="3" rx="2"/>
  <path d="M9 3v18"/>
  <path d="m13 9 3 3-3 3"/>
</svg>"""

# Right-side counterparts of PANEL_LEFT_*: separator on the right, inverted chevron.
# Used for the "Functions" panel that lives to the right of the Studio editor.
PANEL_RIGHT_CLOSE = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect width="18" height="18" x="3" y="3" rx="2"/>
  <path d="M15 3v18"/>
  <path d="m8 9 3 3-3 3"/>
</svg>"""

PANEL_RIGHT_OPEN = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <rect width="18" height="18" x="3" y="3" rx="2"/>
  <path d="M15 3v18"/>
  <path d="m11 15-3-3 3-3"/>
</svg>"""

CHEVRON_DOWN = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m6 9 6 6 6-6"/>
</svg>"""

CHEVRON_UP = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m18 15-6-6-6 6"/>
</svg>"""

# Bascule d'affichage — utilisee pour activer/desactiver le surlignage
# des lignes par fonction dans l'editeur (panneau Fonctions).
EYE = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"/>
  <circle cx="12" cy="12" r="3"/>
</svg>"""

EYE_OFF = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M9.88 9.88a3 3 0 1 0 4.24 4.24"/>
  <path d="M10.73 5.08A10.43 10.43 0 0 1 12 5c7 0 10 7 10 7a13.16 13.16 0 0 1-1.67 2.68"/>
  <path d="M6.61 6.61A13.526 13.526 0 0 0 2 12s3 7 10 7a9.74 9.74 0 0 0 5.39-1.61"/>
  <line x1="2" x2="22" y1="2" y2="22"/>
</svg>"""

MENU = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <line x1="4" y1="6" x2="20" y2="6"/>
  <line x1="4" y1="12" x2="20" y2="12"/>
  <line x1="4" y1="18" x2="20" y2="18"/>
</svg>"""

MOON = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
</svg>"""

SUN = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="5"/>
  <line x1="12" y1="1" x2="12" y2="3"/>
  <line x1="12" y1="21" x2="12" y2="23"/>
  <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
  <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
  <line x1="1" y1="12" x2="3" y2="12"/>
  <line x1="21" y1="12" x2="23" y2="12"/>
  <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
  <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
</svg>"""

REFRESH = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <polyline points="1 4 1 10 7 10"/>
  <path d="M3.51 15a9 9 0 1 0 .49-3.5"/>
</svg>"""

X_ICON = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M18 6 6 18"/>
  <path d="m6 6 12 12"/>
</svg>"""

TRASH = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M3 6h18"/>
  <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/>
  <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
  <line x1="10" y1="11" x2="10" y2="17"/>
  <line x1="14" y1="11" x2="14" y2="17"/>
</svg>"""

PENCIL = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/>
  <path d="m15 5 4 4"/>
</svg>"""

UNDO = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M9 14 4 9l5-5"/>
  <path d="M4 9h10.5a5.5 5.5 0 0 1 5.5 5.5v0a5.5 5.5 0 0 1-5.5 5.5H11"/>
</svg>"""

REDO = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m15 14 5-5-5-5"/>
  <path d="M20 9H9.5A5.5 5.5 0 0 0 4 14.5v0A5.5 5.5 0 0 0 9.5 20H13"/>
</svg>"""

PLUG = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 22v-5"/>
  <path d="M9 8V2"/>
  <path d="M15 8V2"/>
  <path d="M18 8H6a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4a2 2 0 0 0-2-2z"/>
</svg>"""

SPARKLES = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
  <path d="M5 3v4"/>
  <path d="M3 5h4"/>
  <path d="M19 17v4"/>
  <path d="M17 19h4"/>
</svg>"""

GLOBE = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="10"/>
  <line x1="2" y1="12" x2="22" y2="12"/>
  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
</svg>"""

FOLDER = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>
</svg>"""

FOLDER_OPEN = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m6 14 1.45-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.94 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.69.9l.81 1.2a2 2 0 0 0 1.67.9H18a2 2 0 0 1 2 2v2"/>
</svg>"""

FILE_TEXT = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/>
  <path d="M14 2v4a2 2 0 0 0 2 2h4"/>
  <path d="M10 9H8"/>
  <path d="M16 13H8"/>
  <path d="M16 17H8"/>
</svg>"""

PLUS = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 5v14"/>
  <path d="M5 12h14"/>
</svg>"""

MORE_HORIZONTAL = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="1"/>
  <circle cx="19" cy="12" r="1"/>
  <circle cx="5" cy="12" r="1"/>
</svg>"""

BOOK = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4 19.5v-15A2.5 2.5 0 0 1 6.5 2H20v20H6.5a2.5 2.5 0 0 1 0-5H20"/>
</svg>"""

MESSAGE_CIRCLE = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" \
fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" \
stroke-linejoin="round"><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"></path></svg>"""

# Pile de livres — Lucide "library". Quatre traits verticaux evoquant
# une rangee de livres serres.
LIBRARY = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m16 6 4 14"/>
  <path d="M12 6v14"/>
  <path d="M8 8v12"/>
  <path d="M4 4v16"/>
</svg>"""

SEARCH = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="11" cy="11" r="8"/>
  <path d="m21 21-4.3-4.3"/>
</svg>"""

DOWNLOAD = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/>
  <polyline points="7 10 12 15 17 10"/>
  <line x1="12" y1="15" x2="12" y2="3"/>
</svg>"""

SETTINGS = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="none" stroke="currentColor"
  stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="12" cy="12" r="3"/>
  <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06
           a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09
           A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83
           l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09
           A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83
           l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09
           a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83
           l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09
           a1.65 1.65 0 0 0-1.51 1z"/>
</svg>"""

# GitHub "Octocat" mark, vectorised from the logo placed in assets/logo (the
# wordmark/disc are dropped: illegible at icon size). Filled silhouette
# (fill="currentColor") so make_icon() recolours it to follow the theme.
GITHUB = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="currentColor">
  <path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577
           0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7
           c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998
           .108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22
           -.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405
           2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22
           0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286
           0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/>
</svg>"""

# Patreon logomark (circle + vertical bar). Filled (fill="currentColor") so
# make_icon() recolours it to follow the theme, like GITHUB.
PATREON = """<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24"
  viewBox="0 0 24 24" fill="currentColor">
  <path d="M14.82 2.41c3.96 0 7.18 3.24 7.18 7.21 0 3.96-3.22 7.18-7.18 7.18
           -3.97 0-7.21-3.22-7.21-7.18 0-3.97 3.24-7.21 7.21-7.21M2 21.6h3.5V2.41H2V21.6"/>
</svg>"""


# ─── Helper ───────────────────────────────────────────────────────────────────

def make_icon(svg_str: str, color: str, size: int = 20) -> QIcon:
    """Generate a QIcon from an SVG string by replacing currentColor."""
    colored = svg_str.replace("currentColor", color)
    data = QByteArray(colored.encode("utf-8"))
    renderer = QSvgRenderer(data)
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return QIcon(pixmap)
