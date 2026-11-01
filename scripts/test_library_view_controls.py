"""Les controles de ui/library_view.py, MESURES A L'ECRAN (TODO #50).

Le delestage du QSS de controle (spec 2026-08-11) a remplace 8 des 9 blocs de
ce fichier par des helpers de `ui/theme.py`. Un test de SOURCE ne prouverait
rien ici : le risque n'est pas qu'on appelle le mauvais nom, c'est que le
bouton ne RESSEMBLE plus a ce qu'il etait. On rend donc les vrais widgets et
on compte des pixels, en DARK et en LIGHT, au repos ET au survol.

⚠️ INSTRUMENT DE SURVOL. Le survol ne se declenche pas hors ecran : ni
`WA_UnderMouse`, ni un `QEnterEvent`, ni `unpolish/polish` ne font repeindre
le bouton (mesure du 2026-08-11 : la pastille reste rouge dans les trois cas).
On appelle donc `style().drawControl(CE_PushButton, opt, ...)` -- exactement ce
que fait `QPushButton::paintEvent` -- avec `State_MouseOver` pose sur l'option.
C'est le vrai moteur QSS sur le vrai widget avec sa vraie feuille ; seul le
bit d'etat est fourni a la main.

⚠️ TEMOIN GELE. `_LEGACY_*` sont les blocs QSS tels qu'ils etaient ecrits a la
main AVANT le delestage. Ils sont ici pour une raison precise : le cadre du
chantier est « le style actuel EST la reference, zero redesign ». Si un jour
ces temoins deviennent faux, c'est qu'on a REDESSINE -- ce qui peut etre
legitime, mais doit alors etre une decision, pas un effet de bord. On ne les
met pas a jour pour faire passer la suite.

Ce que la mesure a etabli le 2026-08-11 (les 8 blocs convertis) :

    pastille cochee        0 / 2688 px  (DARK et LIGHT, repos/survol/desactive)
    pastille non cochee    0 / 2688 px  (idem)
    bouton ⋯ de la carte   0 /  960 px  (idem)
    bouton « Installer »  58 / 3300 px (1.8 %) -- voir ci-dessous

Le bouton « Installer » est le SEUL a bouger, et il bouge pour une raison
connue : `primary_button_qss` declare `border: 1px solid btn_primary_bg`
la ou le bloc local ecrivait `border: none`. La bordure a exactement la
couleur du fond -- aucune bande n'apparait -- mais elle change l'antialiasing
des quatre coins arrondis (56 des 58 pixels) et rogne 2 px d'antialiasing sur
le jambage du « I ». Elle elargit aussi le bouton de 2 px (sizeHint 136 ->
138). C'est le prix assume de la mise en commun ; les tests ci-dessous
verrouillent ce qui se VOIT (les couleurs de fond dans les trois etats et la
position du texte), pas l'antialiasing.

Run : python scripts/test_library_view_controls.py
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from PyQt6.QtWidgets import QApplication
_APP = QApplication.instance() or QApplication([])

from PyQt6.QtGui import QPixmap, QPainter, QColor
from PyQt6.QtWidgets import QPushButton, QStyle, QStyleOptionButton
from ui.theme import DARK, LIGHT, ColorScheme, app_qss, filter_pill_qss
import ui.library_view as LV

# Les widgets doivent survivre a la fonction qui les cree : un QPushButton
# collecte pendant qu'on le peint fait tomber l'interpreteur natif.
_ALIVE: list = []

# Fond de la mire : une couleur qu'aucun theme n'emploie, pour que
# « transparent » se distingue de « peint ».
_BACKDROP = "#ff00ff"

SCHEMES = ((DARK, "DARK"), (LIGHT, "LIGHT"))


# ── Les 4 blocs tels qu'ils etaient ecrits a la main (temoin gele) ──────────
def _legacy_pill(c: ColorScheme, checked: bool) -> str:
    if checked:
        return f"""
            QPushButton {{
                background-color: {c.nav_active_bg};
                color: {c.signal_ok};
                border: 1px solid {c.signal_ok};
                border-radius: 4px;
                font-size: 9pt; font-weight: 600;
                padding: 3px 12px;
            }}
        """
    return f"""
        QPushButton {{
            background: transparent;
            color: {c.text_primary};
            border: 1px solid {c.border};
            border-radius: 4px;
            font-size: 9pt; font-weight: 500;
            padding: 3px 12px;
        }}
        QPushButton:hover {{
            border-color: {c.signal_ok};
            color: {c.signal_ok};
        }}
    """


def _legacy_more_button(c: ColorScheme) -> str:
    return f"""
        QPushButton {{
            background: transparent;
            border: none; border-radius: 6px;
        }}
        QPushButton:hover {{ background-color: {c.nav_hover_bg}; }}
    """


def _legacy_install_button(c: ColorScheme) -> str:
    return f"""
        QPushButton {{
            background-color: {c.btn_primary_bg};
            color: {c.btn_primary_text};
            border: none; border-radius: 6px;
            padding: 4px 14px;
            font-size: 9pt; font-weight: 600;
        }}
        QPushButton:hover {{ background-color: {c.signal_ok}; }}
        QPushButton:disabled {{
            background-color: {c.surface};
            color: {c.disabled_text};
        }}
    """


# ── Instruments ─────────────────────────────────────────────────────────────
def _paint(btn: QPushButton, *, hover: bool = False):
    """Peint le bouton par le chemin de son propre paintEvent (cf. en-tete)."""
    px = QPixmap(btn.size())
    px.fill(QColor(_BACKDROP))
    opt = QStyleOptionButton()
    btn.initStyleOption(opt)
    if hover:
        opt.state |= QStyle.StateFlag.State_MouseOver
    p = QPainter(px)
    btn.style().drawControl(QStyle.ControlElement.CE_PushButton, opt, p, btn)
    p.end()
    return px.toImage()


def _diff(a, b) -> int:
    assert a.size() == b.size(), (a.size(), b.size())
    return sum(1 for y in range(a.height()) for x in range(a.width())
               if a.pixel(x, y) != b.pixel(x, y))


def _rgb(img, x: int, y: int) -> str:
    v = img.pixel(x, y)
    return f"#{(v >> 16) & 255:02x}{(v >> 8) & 255:02x}{v & 255:02x}"


def _ink_bbox(img, fill: int) -> tuple[int, int, int, int]:
    """Boite de l'encre INTERIEURE (on ecarte les 2 px de bord, qui portent
    l'antialiasing des coins, pour ne mesurer que le texte)."""
    pts = [(x, y) for y in range(3, img.height() - 3)
           for x in range(3, img.width() - 3) if img.pixel(x, y) != fill]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _under_app_qss(scheme: ColorScheme):
    """Pose la feuille d'application REELLE : c'est la seule condition dans
    laquelle les regles globales (survol du bouton secondaire par defaut,
    :disabled...) peuvent se superposer a la feuille locale -- et donc la
    seule ou la mesure vaut pour l'app."""
    _APP.setStyleSheet(app_qss(scheme))


def _pill(scheme: ColorScheme, *, checked: bool = False,
          coming_soon: bool = False) -> QPushButton:
    btn = LV._PlatformButton("ESP32" if coming_soon else "Arduino",
                             coming_soon=coming_soon)
    _ALIVE.append(btn)
    if not coming_soon:
        btn.setChecked(checked)
    btn.apply_theme(scheme)
    btn.show()
    _APP.processEvents()
    btn.resize(max(96, btn.sizeHint().width()), 28)
    return btn


_LIB = {"name": "Adafruit GFX Library", "version": "1.11.9",
        "author": "Adafruit", "sentence": "Graphics primitives.",
        "install_dir": ""}


def _card_button(scheme: ColorScheme, mode: str) -> QPushButton:
    card = LV._LibraryCard(dict(_LIB), mode=mode)
    _ALIVE.append(card)
    card.apply_theme(scheme)
    btn = card._action_btn
    btn.show()
    _APP.processEvents()
    if mode == "search":
        btn.resize(110, 30)
    return btn


def _same_as_legacy(btn: QPushButton, legacy: str, states) -> dict:
    """Rend le MEME widget avec sa feuille puis avec le temoin -- meme
    instance, donc meme geometrie : ce qui reste ne peut venir que du style."""
    live = btn.styleSheet()
    out = {}
    for state in states:
        btn.setEnabled(state != "disabled")
        btn.setStyleSheet(live)
        _APP.processEvents()
        a = _paint(btn, hover=(state == "hover"))
        btn.setStyleSheet(legacy)
        _APP.processEvents()
        b = _paint(btn, hover=(state == "hover"))
        out[state] = _diff(a, b)
    btn.setEnabled(True)
    btn.setStyleSheet(live)
    return out


_STATES = ("rest", "hover", "disabled")


# ── Tests ───────────────────────────────────────────────────────────────────
def test_the_platform_pills_render_exactly_as_before_the_delestage():
    """`filter_pill_qss` rend la pastille au pixel pres, cochee et non cochee.

    Zero pixel d'ecart, y compris a l'etat desactive : contrairement a
    `primary_button_qss`, ce helper ne declare AUCUNE regle `:disabled` -- il
    n'ajoute donc rien que le bloc local n'avait."""
    for scheme, name in SCHEMES:
        _under_app_qss(scheme)
        for checked in (True, False):
            btn = _pill(scheme, checked=checked)
            got = _same_as_legacy(btn, _legacy_pill(scheme, checked), _STATES)
            assert set(got.values()) == {0}, (name, f"checked={checked}", got)


def test_the_coming_soon_pill_keeps_its_own_python_branch():
    """L'ESP32 « bientot disponible » est peint par un `if` Python, pas par
    `:disabled` -- le bouton reste ENABLED pour que son infobulle sorte au
    survol. `filter_pill_qss` ne couvre volontairement pas cet etat.

    Deux verrous : la pastille ne doit pas prendre la feuille du helper, et
    surtout elle ne doit PAS verdir au survol. Ce second point n'a rien
    d'evident : la feuille globale `app_qss` porte, elle, un
    `QPushButton:hover` vert -- s'il fuyait a travers la feuille locale, le
    « bientot disponible » s'allumerait comme un bouton cliquable."""
    for scheme, name in SCHEMES:
        _under_app_qss(scheme)
        soon = _pill(scheme, coming_soon=True)
        assert soon.styleSheet().strip() != filter_pill_qss(
            scheme, checked=False).strip(), (
            f"[{name}] la branche « bientot disponible » a ete repliee sur "
            "le helper : elle a perdu son texte grise")
        assert _diff(_paint(soon), _paint(soon, hover=True)) == 0, (
            f"[{name}] la pastille « bientot disponible » reagit au survol")
        # ... et elle ne se lit pas comme une pastille active.
        live = _pill(scheme, checked=False)
        live.resize(soon.size())
        assert _diff(_paint(soon), _paint(live)) > 0, (
            f"[{name}] « bientot disponible » est indistinguable d'un onglet "
            "selectionnable")


def test_the_card_more_button_tints_its_background_on_hover():
    """LE bouton ⋯ d'une carte de librairie. Il porte une QIcon, que le QSS ne
    recolore pas (d'ou `install_icon_hover`) : la teinte de FOND est sa seule
    affordance de survol. Le passer a `variant="bare"` -- qui n'a aucun fond --
    la supprimerait en silence, et le bouton n'aurait plus l'air cliquable.

    On echantillonne a mi-hauteur, a gauche de l'icone 16x16 centree."""
    for scheme, name in SCHEMES:
        _under_app_qss(scheme)
        btn = _card_button(scheme, "installed")
        x, y = 2, btn.height() // 2
        assert _rgb(_paint(btn), x, y) == _BACKDROP, (
            f"[{name}] le bouton ⋯ peint un fond au repos (il doit etre "
            "transparent)")
        assert _rgb(_paint(btn, hover=True), x, y) == scheme.nav_hover_bg, (
            f"[{name}] le bouton ⋯ ne teinte plus son fond au survol : "
            f"{_rgb(_paint(btn, hover=True), x, y)} au lieu de "
            f"{scheme.nav_hover_bg}")
        got = _same_as_legacy(btn, _legacy_more_button(scheme), _STATES)
        assert set(got.values()) == {0}, (name, got)


def test_the_card_install_button_stays_the_filled_primary_button():
    """« Installer » / « Installe » : plein au repos, VERT au survol, `surface`
    une fois desactive (badge « deja installee », ou installation en cours).

    On verrouille les couleurs et la position du texte, pas le nombre de
    pixels : `primary_button_qss` ajoute une bordure d'1 px de la couleur du
    fond, invisible mais qui deplace l'antialiasing des coins (mesure :
    58/3300 px, cf. en-tete)."""
    for scheme, name in SCHEMES:
        _under_app_qss(scheme)
        btn = _card_button(scheme, "search")
        x, y = 5, btn.height() // 2          # a gauche du texte (padding 14)
        attendu = {"rest": scheme.btn_primary_bg,
                   "hover": scheme.signal_ok,
                   "disabled": scheme.surface}
        for state, couleur in attendu.items():
            btn.setEnabled(state != "disabled")
            _APP.processEvents()
            got = _rgb(_paint(btn, hover=(state == "hover")), x, y)
            assert got == couleur, (
                f"[{name}] fond du bouton « Installer » a l'etat {state} : "
                f"{got} au lieu de {couleur}")
        btn.setEnabled(True)
        _APP.processEvents()


def test_the_install_button_label_did_not_move():
    """Le garde-fou de la police et du padding : `font_pt=9` et
    `padding="4px 14px"` sont passes au helper a la main, et une erreur sur
    l'un des deux ne se verrait sur AUCUNE couleur -- seulement sur la place
    du texte. On compare donc la boite d'encre au temoin gele.

    Tolerance 1 px a gauche : la bordure d'1 px du helper retrecit d'autant la
    boite de contenu, ce qui coupe le tout premier liseré du « I »."""
    for scheme, name in SCHEMES:
        _under_app_qss(scheme)
        btn = _card_button(scheme, "search")
        live = btn.styleSheet()
        a = _paint(btn)
        btn.setStyleSheet(_legacy_install_button(scheme))
        _APP.processEvents()
        b = _paint(btn)
        btn.setStyleSheet(live)
        boite_a = _ink_bbox(a, a.pixel(btn.width() // 2, 3))
        boite_b = _ink_bbox(b, b.pixel(btn.width() // 2, 3))
        ecarts = [abs(u - v) for u, v in zip(boite_a, boite_b)]
        assert max(ecarts) <= 1, (
            f"[{name}] le libelle du bouton « Installer » a bouge : "
            f"{boite_a} au lieu de {boite_b} (ecarts {ecarts}) -- "
            "font_pt ou padding ne correspondent plus au bloc d'origine")


TESTS = [
    test_the_platform_pills_render_exactly_as_before_the_delestage,
    test_the_coming_soon_pill_keeps_its_own_python_branch,
    test_the_card_more_button_tints_its_background_on_hover,
    test_the_card_install_button_stays_the_filled_primary_button,
    test_the_install_button_label_did_not_move,
]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
            print(f"OK   {t.__name__}")
        except Exception as e:
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{passed}/{len(TESTS)} tests passed")
    sys.stdout.flush()
    os._exit(0 if passed == len(TESTS) else 1)
