"""Genere 3 versions realistes de l'Arduino Uno R3 en orientation PORTRAIT
avec le CONTOUR REEL du PCB (non rectangulaire : step sur le bord +
coupe diagonale au coin), extrait du SVG de reference de l'utilisateur.

Le path est en orientation paysage dans le SVG d'origine. On l'applique
ici via une transform qui :
- scale le path non uniformement (0.5217 x 0.4533) pour faire rentrer
  la bbox originale (709.22 x 551.50) dans 370 x 250 px portrait
- rotate(90) pour passer paysage -> portrait
- translate pour positionner la PCB a (20,40)-(270,410)

Compatibilite drop-in : un rect#board-body invisible reste a x=20, y=40,
w=250, h=370 pour que le wiring.layout trouve la bbox du PCB. Le contour
visible (avec ses notches) est dessine par le path.

Niveaux de detail :
- v1 'epure'   : juste le contour realiste + connecteurs + DIP
- v2 'fidele'  : + composants (LEDs, ICSP, 16U2, regulateur, capas) +
                 logo Arduino UNO
- v3 'enrichi' : + serigraphie complete, ovale UNO pointille, ombrages
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "scripts" / "wiring_layout_test_output"
OUT.mkdir(parents=True, exist_ok=True)


# ─── Contour PCB reel (extrait du SVG de reference utilisateur) ──────────
# Path original en orientation PAYSAGE. Bbox approximative dans le path :
# x ∈ [118.6, 827.82], y ∈ [174.22, 725.72] (largeur 709.22, hauteur 551.5).
# Ce contour inclut : les 4 coins arrondis, le step horizontal du cote
# droit (vers x=802 puis x=827) et la coupe diagonale au coin bas-droit.
PCB_CONTOUR_PATH = (
    "m127.56 174.22"
    "c-5.1338 0.64979-7.661 3.9081-8.9452 8.4076"
    "l0.10634 535.54"
    "c0 4.2653 3.5872 7.5437 7.3946 7.5437"
    "h667.57"
    "c4.5491-0.75372 6.4818-3.6379 7.1624-7.5437"
    "l1.5252-18.289 21.278-21.293 4.1738-14.871"
    "v-331.6"
    "c-8.7397-9.2989-24.957-25.491-24.957-25.491"
    "l-0.5565-120.22-12.178-12.071z"
)
# Transform pour passer paysage -> portrait avec PCB body a (20,40)-(270,410).
# Verifie : (118.6, 174.22) -> (270, 40) [TR], (827.82, 725.72) -> (20, 410) [BL].
PCB_TRANSFORM = "translate(348.97, -21.87) rotate(90) scale(0.5217, 0.4533)"


# ─── Geometrie portrait ─────────────────────────────────────────────────
# Memes dimensions que uno_r3.svg (drop-in)
W, H = 290, 430
PCB_X, PCB_Y, PCB_W, PCB_H = 20, 40, 250, 370

# USB-B et barrel jack : sortent vers le HAUT
USB  = dict(x=180, y=6,  w=70, h=44)
JACK = dict(x=50,  y=12, w=58, h=38)

# Composants centraux (positions adaptees au contour reel)
RESET    = dict(x=160, y=58,  w=20, h=20)
ICSP2    = dict(x=205, y=85,  w=18, h=22)
ATMEGA16 = dict(x=200, y=120, w=22, h=22)
LED_L    = dict(cx=210, cy=165, w=5, h=8)
LED_TX   = dict(cx=195, cy=170, w=5, h=8)
LED_RX   = dict(cx=180, cy=170, w=5, h=8)
LED_ON   = dict(cx=110, cy=78,  w=5, h=8)
REG      = dict(x=78,  y=58,  w=18, h=22)
CAP1     = dict(cx=85,  cy=120, r=12)
CAP2     = dict(cx=85,  cy=152, r=12)
ATMEGA   = dict(x=128, y=210, w=34, h=170)
ICSP1    = dict(x=215, y=225, w=18, h=22)
# Mounting holes (positions datasheet, mappees portrait)
MH = [(151, 122), (151, 396), (56, 396), (258, 314)]


# ─── Pin layout (identique a uno_r3.svg) ────────────────────────────────
PINS_RIGHT = [
    ("SCL",  "SCL",       50), ("SDA",  "SDA",      70),
    ("AREF", "AREF",      90), ("GND1", "GND",      110),
    ("D13",  "SCK/D13",   130),("D12",  "MISO/D12", 150),
    ("D11",  "MOSI/~D11", 170),("D10",  "SS/~D10",  190),
    ("D9",   "~D9",       210),("D8",   "D8",       230),
    ("D7",   "D7",        250),("D6",   "~D6",      270),
    ("D5",   "~D5",       290),("D4",   "D4",       310),
    ("D3",   "~D3",       330),("D2",   "D2",       350),
    ("D1",   "TX/D1",     370),("D0",   "RX/D0",    390),
]
PINS_LEFT = [
    ("NC",    "NC",     50), ("IOREF", "IOREF",  70),
    ("RESET", "RST",    90), ("V3V3",  "3V3",    110),
    ("V5V",   "5V",     130),("GND2",  "GND",    150),
    ("GND3",  "GND",    170),("VIN",   "VIN",    190),
    ("A0",    "A0",     210),("A1",    "A1",     230),
    ("A2",    "A2",     250),("A3",    "A3",     270),
    ("A4",    "A4/SDA", 290),("A5",    "A5/SCL", 310),
]


# ─── Helpers SVG ─────────────────────────────────────────────────────────
def pcb_contour(fill: str = "#017e7b", stroke: str = "none",
                stroke_width: float = 0.0) -> str:
    """Path PCB realiste avec les notches. Le rect#board-body invisible
    en parallele permet a wiring.layout de trouver la bbox du PCB."""
    stroke_attr = (
        f' stroke="{stroke}" stroke-width="{stroke_width}" '
        f'vector-effect="non-scaling-stroke"' if stroke != "none" else ""
    )
    return f"""
  <!-- Bbox invisible pour compatibilite wiring.layout -->
  <rect id="board-body" x="{PCB_X}" y="{PCB_Y}" width="{PCB_W}" height="{PCB_H}"
        fill="none" stroke="none"/>
  <!-- Contour PCB reel (avec notches) -->
  <g transform="{PCB_TRANSFORM}">
    <path d="{PCB_CONTOUR_PATH}" fill="{fill}"{stroke_attr}/>
  </g>
"""


def usb_jack_svg() -> str:
    return f"""
  <rect x="{USB['x']}" y="{USB['y']}" width="{USB['w']}" height="{USB['h']}" fill="#9aa1a8" stroke="#3a3f44" stroke-width="1.4" rx="2"/>
  <rect x="{USB['x']+5}" y="{USB['y']+5}" width="{USB['w']-10}" height="{USB['h']-10}" fill="#bdc3c7" stroke="#7a7e82" stroke-width="0.6"/>
  <rect x="{USB['x']+11}" y="{USB['y']+11}" width="{USB['w']-22}" height="{USB['h']-22}" fill="#5a5e62" stroke="#1a1a1a" stroke-width="0.5"/>
  <line x1="{USB['x']+5}" y1="{USB['y']+9}" x2="{USB['x']+USB['w']-5}" y2="{USB['y']+9}" stroke="#7a7e82" stroke-width="0.4"/>
  <line x1="{USB['x']+5}" y1="{USB['y']+USB['h']-9}" x2="{USB['x']+USB['w']-5}" y2="{USB['y']+USB['h']-9}" stroke="#7a7e82" stroke-width="0.4"/>
  <rect x="{JACK['x']}" y="{JACK['y']}" width="{JACK['w']}" height="{JACK['h']}" fill="#1a1a1a" stroke="#000" stroke-width="1.2" rx="3"/>
  <rect x="{JACK['x']+5}" y="{JACK['y']+8}" width="{JACK['w']-10}" height="{JACK['h']-16}" fill="#0a0a0a"/>
  <circle cx="{JACK['x']+JACK['w']/2}" cy="{JACK['y']+JACK['h']-8}" r="8" fill="#0a0a0a" stroke="#444" stroke-width="0.5"/>
  <circle cx="{JACK['x']+JACK['w']/2}" cy="{JACK['y']+JACK['h']-8}" r="3.5" fill="#2a2a2a"/>
"""


def mounting_holes_svg() -> str:
    return "\n  ".join(
        f'<circle cx="{cx}" cy="{cy}" r="6" fill="#fff" stroke="#888" stroke-width="0.8"/>'
        f'<circle cx="{cx}" cy="{cy}" r="3" fill="#1a1a1a"/>'
        for cx, cy in MH
    )


def pin_holes_svg(label_color: str = "#fff", show_strips: bool = False) -> str:
    """Pins V2/V3 : header strips noires + cercles fonces avec stroke."""
    parts = []
    if show_strips:
        parts.append(f'<rect x="234" y="44" width="20" height="192" fill="#1a1a1a" stroke="#000" stroke-width="0.5" rx="1"/>')
        parts.append(f'<rect x="234" y="244" width="20" height="156" fill="#1a1a1a" stroke="#000" stroke-width="0.5" rx="1"/>')
        parts.append(f'<rect x="36" y="44" width="20" height="156" fill="#1a1a1a" stroke="#000" stroke-width="0.5" rx="1"/>')
        parts.append(f'<rect x="36" y="204" width="20" height="116" fill="#1a1a1a" stroke="#000" stroke-width="0.5" rx="1"/>')
    for pid, label, cy in PINS_RIGHT:
        parts.append(f'<rect x="240" y="{cy-5}" width="8" height="10" fill="#0a0a0a" stroke="#000" stroke-width="0.3"/>')
        parts.append(f'<circle id="pin-{pid}-pos" cx="244" cy="{cy}" r="2.2" fill="#3a3a3a" stroke="#000" stroke-width="0.4"/>')
        parts.append(f'<text x="228" y="{cy+3.5}" font-family="sans-serif" font-size="9" font-weight="bold" text-anchor="end" fill="{label_color}">{label}</text>')
    for pid, label, cy in PINS_LEFT:
        parts.append(f'<rect x="42" y="{cy-5}" width="8" height="10" fill="#0a0a0a" stroke="#000" stroke-width="0.3"/>')
        parts.append(f'<circle id="pin-{pid}-pos" cx="46" cy="{cy}" r="2.2" fill="#3a3a3a" stroke="#000" stroke-width="0.4"/>')
        parts.append(f'<text x="61" y="{cy+3.5}" font-family="sans-serif" font-size="9" font-weight="bold" text-anchor="start" fill="{label_color}">{label}</text>')
    return "\n  ".join(parts)


def pin_holes_simple_svg() -> str:
    """Pins V1 : style identique a uno_r3.svg (simples cercles blancs +
    labels horizontaux en gras blanc, pas de header strips)."""
    parts = []
    for pid, label, cy in PINS_RIGHT:
        parts.append(
            f'<circle id="pin-{pid}-pos" cx="244" cy="{cy}" r="3" '
            f'fill="#ffffff" stroke="#ffffff" stroke-width="1"/>'
        )
        parts.append(
            f'<text id="pin-{pid}-label" x="228.80127" y="{cy+3.5}" '
            f'font-family="sans-serif" font-size="9" font-weight="bold" '
            f'text-anchor="end" fill="#ffffff">{label}</text>'
        )
    for pid, label, cy in PINS_LEFT:
        parts.append(
            f'<circle id="pin-{pid}-pos" cx="46" cy="{cy}" r="3" '
            f'fill="#ffffff" stroke="#ffffff" stroke-width="1"/>'
        )
        parts.append(
            f'<text id="pin-{pid}-label" x="60.894531" y="{cy+3.5}" '
            f'font-family="sans-serif" font-size="9" font-weight="bold" '
            f'text-anchor="start" fill="#ffffff">{label}</text>'
        )
    return "\n  ".join(parts)


def reset_button_svg() -> str:
    return f"""
  <rect x="{RESET['x']}" y="{RESET['y']}" width="{RESET['w']}" height="{RESET['h']}" fill="#1a1a1a" stroke="#000" stroke-width="0.8" rx="2"/>
  <rect x="{RESET['x']+2}" y="{RESET['y']+2}" width="{RESET['w']-4}" height="{RESET['h']-4}" fill="#0a0a0a"/>
  <circle cx="{RESET['x']+RESET['w']/2}" cy="{RESET['y']+RESET['h']/2}" r="5" fill="#a52a2a" stroke="#5a0a0a" stroke-width="0.5"/>
"""


def icsp_header_svg(box: dict) -> str:
    x, y, w, h = box['x'], box['y'], box['w'], box['h']
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#1a1a1a" stroke="#000" stroke-width="0.6" rx="1"/>']
    pin_w = 3.5
    for col in range(2):
        for row in range(3):
            cx = x + 5 + col * (w - 10)
            cy = y + 4 + row * (h - 8) / 2
            s.append(f'<rect x="{cx-pin_w/2}" y="{cy-pin_w/2}" width="{pin_w}" height="{pin_w}" fill="#d4af37" stroke="#7d6500" stroke-width="0.3"/>')
    return "\n  ".join(s)


def voltage_regulator_svg() -> str:
    x, y, w, h = REG['x'], REG['y'], REG['w'], REG['h']
    return f"""
  <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#1a1a1a" stroke="#000" stroke-width="0.6" rx="1"/>
  <rect x="{x-3}" y="{y+1}" width="3" height="{h-2}" fill="#9aa1a8" stroke="#555" stroke-width="0.3"/>
  <rect x="{x+w}" y="{y+2}" width="3" height="3" fill="#9aa1a8" stroke="#555" stroke-width="0.3"/>
  <rect x="{x+w}" y="{y+h/2-1.5}" width="3" height="3" fill="#9aa1a8" stroke="#555" stroke-width="0.3"/>
  <rect x="{x+w}" y="{y+h-5}" width="3" height="3" fill="#9aa1a8" stroke="#555" stroke-width="0.3"/>
"""


def cap_electrolytic_svg(spec: dict) -> str:
    cx, cy, r = spec['cx'], spec['cy'], spec['r']
    return f"""
  <circle cx="{cx}" cy="{cy}" r="{r}" fill="#1a1a1a" stroke="#000" stroke-width="0.7"/>
  <circle cx="{cx}" cy="{cy}" r="{r-2.5}" fill="#f0f0f0" stroke="#888" stroke-width="0.4"/>
  <line x1="{cx}" y1="{cy-r+3}" x2="{cx}" y2="{cy+r-3}" stroke="#888" stroke-width="0.5"/>
"""


def atmega328_svg(detailed: bool = False) -> str:
    x, y, w, h = ATMEGA['x'], ATMEGA['y'], ATMEGA['w'], ATMEGA['h']
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#1a1a1a" stroke="#000" stroke-width="1" rx="1"/>']
    if detailed:
        s.append(f'<path d="M {x+w/2-5} {y} a 5 5 0 0 0 10 0" fill="#0a0a0a" stroke="#444" stroke-width="0.4"/>')
        s.append(f'<circle cx="{x+5}" cy="{y+8}" r="1.3" fill="#fff"/>')
        for i in range(14):
            yy = y + 6 + i * (h - 12) / 13
            s.append(f'<rect x="{x-3}" y="{yy-1.5}" width="3" height="3" fill="#9aa1a8" stroke="#444" stroke-width="0.3"/>')
            s.append(f'<rect x="{x+w}" y="{yy-1.5}" width="3" height="3" fill="#9aa1a8" stroke="#444" stroke-width="0.3"/>')
    return "\n  ".join(s)


def atmega16u2_svg() -> str:
    x, y, w, h = ATMEGA16['x'], ATMEGA16['y'], ATMEGA16['w'], ATMEGA16['h']
    return f"""
  <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#1a1a1a" stroke="#000" stroke-width="0.8" rx="1"/>
  <circle cx="{x+3}" cy="{y+3}" r="0.8" fill="#fff"/>
"""


def led_svg(spec: dict, color: str, stroke: str) -> str:
    cx, cy, w, h = spec['cx'], spec['cy'], spec['w'], spec['h']
    return f'<rect x="{cx-w/2}" y="{cy-h/2}" width="{w}" height="{h}" fill="{color}" stroke="{stroke}" stroke-width="0.5" rx="0.5"/>'


def arduino_logo_svg(detailed: bool = False) -> str:
    cx, cy = 145, 408
    parts = [
        f'<text x="{cx-32}" y="{cy-3}" font-family="sans-serif" font-size="16" font-weight="bold" text-anchor="middle" fill="#fff">−</text>',
        f'<circle cx="{cx-15}" cy="{cy-7}" r="6" fill="none" stroke="#fff" stroke-width="1.7"/>',
        f'<circle cx="{cx-5}" cy="{cy-7}" r="6" fill="none" stroke="#fff" stroke-width="1.7"/>',
        f'<text x="{cx+15}" y="{cy-3}" font-family="sans-serif" font-size="14" font-weight="bold" text-anchor="middle" fill="#fff">+</text>',
        f'<text x="{cx-13}" y="{cy+13}" font-family="sans-serif" font-size="13" font-style="italic" font-weight="bold" text-anchor="middle" fill="#fff">Arduino</text>',
        f'<text x="{cx+45}" y="{cy+1}" font-family="sans-serif" font-size="16" font-weight="bold" text-anchor="middle" fill="#fff">UNO</text>',
    ]
    if detailed:
        parts.append(f'<text x="{cx+18}" y="{cy+8}" font-family="sans-serif" font-size="5" fill="#fff">TM</text>')
        parts.append(
            f'<ellipse cx="{cx+45}" cy="{cy-3}" rx="20" ry="10" fill="none" '
            f'stroke="#fff" stroke-width="0.8" stroke-dasharray="1,1.2"/>'
        )
    return "\n  ".join(parts)


def silkscreen_svg() -> str:
    return f"""
  <line x1="218" y1="40" x2="218" y2="394" stroke="#fff" stroke-width="0.8"/>
  <text x="214" y="220" font-family="sans-serif" font-size="9" font-weight="bold" text-anchor="middle" fill="#fff" transform="rotate(-90 214 220)">DIGITAL (PWM~)</text>
  <line x1="72" y1="40" x2="72" y2="200" stroke="#fff" stroke-width="0.8"/>
  <text x="68" y="125" font-family="sans-serif" font-size="9" font-weight="bold" text-anchor="middle" fill="#fff" transform="rotate(-90 68 125)">POWER</text>
  <line x1="72" y1="204" x2="72" y2="320" stroke="#fff" stroke-width="0.8"/>
  <text x="68" y="265" font-family="sans-serif" font-size="9" font-weight="bold" text-anchor="middle" fill="#fff" transform="rotate(-90 68 265)">ANALOG IN</text>
"""


# ─── Variant 1 : Epure ───────────────────────────────────────────────────
def variant_epure() -> str:
    """Style epure : contour reel + connecteurs + DIP + 'Arduino Uno R3'
    centre, AVEC les pins exactement comme dans uno_r3.svg actuel
    (simples cercles blancs + labels horizontaux blancs en gras)."""
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" version="1.1">
  <g id="board">
  {pcb_contour(fill="#017e7b")}
  {usb_jack_svg()}
  {mounting_holes_svg()}
  {atmega328_svg(detailed=False)}
  {pin_holes_simple_svg()}
  <!-- Board name 'Arduino Uno R3' au-dessus du DIP (le DIP occupe y=210-380,
       donc on place le texte dans la zone vide haut-centre y=180-200) -->
  <text id="board-name" x="145.20312" y="190" font-family="sans-serif" font-size="13" font-weight="bold" text-anchor="middle" fill="#ffffff">Arduino</text>
  <text x="145.20312" y="205" font-family="sans-serif" font-size="11" font-weight="bold" text-anchor="middle" fill="#ffffff">Uno R3</text>
  </g>
</svg>
"""


# ─── Variant 2 : Fidele ──────────────────────────────────────────────────
def variant_fidele() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" version="1.1">
  <g id="board">
  {pcb_contour(fill="#017e7b")}
  {usb_jack_svg()}
  {mounting_holes_svg()}
  {reset_button_svg()}
  {icsp_header_svg(ICSP2)}
  {atmega16u2_svg()}
  {voltage_regulator_svg()}
  {cap_electrolytic_svg(CAP1)}
  {cap_electrolytic_svg(CAP2)}
  {atmega328_svg(detailed=True)}
  {icsp_header_svg(ICSP1)}
  {led_svg(LED_L,  "#f3c300", "#7d6500")}
  <text x="{LED_L['cx']+5}" y="{LED_L['cy']+3}" font-family="sans-serif" font-size="7" font-weight="bold" fill="#fff">L</text>
  {led_svg(LED_TX, "#f3c300", "#7d6500")}
  <text x="{LED_TX['cx']-5}" y="{LED_TX['cy']+3}" font-family="sans-serif" font-size="7" font-weight="bold" text-anchor="end" fill="#fff">TX</text>
  {led_svg(LED_RX, "#f3c300", "#7d6500")}
  <text x="{LED_RX['cx']-5}" y="{LED_RX['cy']+3}" font-family="sans-serif" font-size="7" font-weight="bold" text-anchor="end" fill="#fff">RX</text>
  {led_svg(LED_ON, "#3acc3a", "#1a661a")}
  <text x="{LED_ON['cx']+6}" y="{LED_ON['cy']+3}" font-family="sans-serif" font-size="7" font-weight="bold" fill="#fff">ON</text>
  <text x="{RESET['x']+RESET['w']/2}" y="{RESET['y']-3}" font-family="sans-serif" font-size="7" font-weight="bold" text-anchor="middle" fill="#fff">RESET</text>
  <text x="{ICSP1['x']-3}" y="{ICSP1['y']+ICSP1['h']/2+3}" font-family="sans-serif" font-size="7" font-weight="bold" text-anchor="end" fill="#fff">ICSP</text>
  <text x="{ICSP2['x']-3}" y="{ICSP2['y']+ICSP2['h']/2+3}" font-family="sans-serif" font-size="7" font-weight="bold" text-anchor="end" fill="#fff">ICSP2</text>
  {arduino_logo_svg(detailed=False)}
  {pin_holes_svg(label_color="#fff", show_strips=True)}
  </g>
</svg>
"""


# ─── Variant 3 : Enrichi ─────────────────────────────────────────────────
def variant_enrichi() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" version="1.1">
  <defs>
    <filter id="softShadow3" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0.4" dy="0.8" stdDeviation="0.6" flood-opacity="0.4"/>
    </filter>
  </defs>
  <g id="board">
  {pcb_contour(fill="#017e7b")}
  {usb_jack_svg()}
  {mounting_holes_svg()}
  <g filter="url(#softShadow3)">
  {reset_button_svg()}
  {icsp_header_svg(ICSP2)}
  {atmega16u2_svg()}
  {voltage_regulator_svg()}
  {cap_electrolytic_svg(CAP1)}
  {cap_electrolytic_svg(CAP2)}
  {atmega328_svg(detailed=True)}
  {icsp_header_svg(ICSP1)}
  </g>
  {led_svg(LED_L,  "#f3c300", "#7d6500")}
  <text x="{LED_L['cx']+5}" y="{LED_L['cy']+3}" font-family="sans-serif" font-size="7" font-weight="bold" fill="#fff">L</text>
  {led_svg(LED_TX, "#f3c300", "#7d6500")}
  <text x="{LED_TX['cx']-5}" y="{LED_TX['cy']+3}" font-family="sans-serif" font-size="7" font-weight="bold" text-anchor="end" fill="#fff">TX</text>
  {led_svg(LED_RX, "#f3c300", "#7d6500")}
  <text x="{LED_RX['cx']-5}" y="{LED_RX['cy']+3}" font-family="sans-serif" font-size="7" font-weight="bold" text-anchor="end" fill="#fff">RX</text>
  {led_svg(LED_ON, "#3acc3a", "#1a661a")}
  <text x="{LED_ON['cx']+6}" y="{LED_ON['cy']+3}" font-family="sans-serif" font-size="7" font-weight="bold" fill="#fff">ON</text>
  <text x="{RESET['x']+RESET['w']/2}" y="{RESET['y']-3}" font-family="sans-serif" font-size="7" font-weight="bold" text-anchor="middle" fill="#fff">RESET</text>
  <text x="{ICSP1['x']-3}" y="{ICSP1['y']+ICSP1['h']/2+3}" font-family="sans-serif" font-size="7" font-weight="bold" text-anchor="end" fill="#fff">ICSP</text>
  <text x="{ICSP2['x']-3}" y="{ICSP2['y']+ICSP2['h']/2+3}" font-family="sans-serif" font-size="7" font-weight="bold" text-anchor="end" fill="#fff">ICSP2</text>
  <text x="{ICSP1['x']+ICSP1['w']+2}" y="{ICSP1['y']+5}" font-family="sans-serif" font-size="6" font-weight="bold" fill="#fff">1</text>
  {arduino_logo_svg(detailed=True)}
  {silkscreen_svg()}
  {pin_holes_svg(label_color="#fff", show_strips=True)}
  </g>
</svg>
"""


# ─── Comparaison ────────────────────────────────────────────────────────
def comparison() -> str:
    def extract_inner(svg: str) -> str:
        start = svg.find("<g id=\"board\">")
        end = svg.rfind("</g>")
        return svg[start:end + 4]

    v1 = extract_inner(variant_epure())
    v2 = extract_inner(variant_fidele())
    v3 = extract_inner(variant_enrichi())

    total_w = (W + 30) * 3 + 30
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{H+60}" viewBox="0 0 {total_w} {H+60}" version="1.1">
  <defs>
    <filter id="softShadow3" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0.4" dy="0.8" stdDeviation="0.6" flood-opacity="0.4"/>
    </filter>
  </defs>
  <rect width="{total_w}" height="{H+60}" fill="#fafafa"/>
  <text x="{30+W/2}" y="30" font-family="sans-serif" font-size="14" font-weight="bold" text-anchor="middle" fill="#222">Style 1 — Epure (contour reel)</text>
  <text x="{30+W+30+W/2}" y="30" font-family="sans-serif" font-size="14" font-weight="bold" text-anchor="middle" fill="#222">Style 2 — Fidele</text>
  <text x="{30+2*(W+30)+W/2}" y="30" font-family="sans-serif" font-size="14" font-weight="bold" text-anchor="middle" fill="#222">Style 3 — Enrichi</text>
  <g transform="translate(30, 40)">{v1}</g>
  <g transform="translate({30+W+30}, 40)">{v2}</g>
  <g transform="translate({30+2*(W+30)}, 40)">{v3}</g>
</svg>
"""


def main() -> int:
    out_dir = OUT / "uno_variants"
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / "v1_portrait.svg").write_text(variant_epure(),   encoding="utf-8")
    (out_dir / "v2_portrait.svg").write_text(variant_fidele(),  encoding="utf-8")
    (out_dir / "v3_portrait.svg").write_text(variant_enrichi(), encoding="utf-8")
    (OUT / "uno_variants_compare.svg").write_text(comparison(), encoding="utf-8")

    print("[uno variants portrait, contour reel] generated :")
    print(f"  - {(out_dir / 'v1_portrait.svg').relative_to(ROOT)}")
    print(f"  - {(out_dir / 'v2_portrait.svg').relative_to(ROOT)}")
    print(f"  - {(out_dir / 'v3_portrait.svg').relative_to(ROOT)}")
    print(f"  - {(OUT / 'uno_variants_compare.svg').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
