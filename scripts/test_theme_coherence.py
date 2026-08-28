"""Coherence visuelle des controles (spec 2026-08-11).

Ce fichier porte deux familles de tests :
1. Des tests PURS sur les chaines QSS de ui/theme.py (input_qss, app_qss) --
   aucune QApplication necessaire, un style est une chaine.
2. (Task 4) La GARDE source-scan : aucun selecteur de controle standard
   hors de theme.py, avec liste d'exemptions nominative qui ne peut que
   retrecir.

⚠️ IDIOME D'ASSERTION -- a suivre pour toute extension de ce fichier :
chercher une chaine dans le DOCUMENT entier ne verrouille rien. Mesure du
2026-08-11 : quatre mutants d'`input_qss` (bordure ROUGE au survol ; survol
qui REMPLIT en vert au lieu de border ; QSS qui ne style AUCUN champ, les
selecteurs relegues dans un commentaire ; parametres nommes ignores)
passaient les 4 tests 4/4. On extrait donc le bloc de la regle qui PRODUIT
la propriete (`_rule`) puis on asserte la valeur de la propriete (`_prop`).

Run : python scripts/test_theme_coherence.py
"""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ui import theme
from ui.theme import DARK, LIGHT


# -- Reading a QSS document as rules, not as a bag of characters -------------

_BLOCK_RE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def _blocks(qss: str) -> list[tuple[str, str]]:
    """(selector list, body) for every rule of a QSS document.

    Comments are stripped FIRST: a selector named only in a comment styles
    nothing, and an assertion unable to tell the two apart guards nothing."""
    return [(m.group(1).strip(), m.group(2).strip())
            for m in _BLOCK_RE.finditer(re.sub(r"/\*.*?\*/", "", qss, flags=re.S))]


def _rule(qss: str, selector: str) -> str:
    """Body of the rule whose selector list contains `selector` (exact match on
    one of the comma-separated selectors), so that a property can be asserted
    against the rule that produces it. Raises when no rule targets it -- an
    absent rule must fail loudly, never pass by looking elsewhere."""
    for selectors, body in _blocks(qss):
        if selector in [s.strip() for s in selectors.split(",")]:
            return body
    raise AssertionError(f"aucune regle pour le selecteur {selector!r} dans :\n{qss}")


def _prop(body: str, name: str) -> str | None:
    """Value of the `name` declaration inside a rule body, None if absent.
    Exact key match: asking for `border` never returns `border-radius`."""
    for decl in body.split(";"):
        key, sep, value = decl.partition(":")
        if sep and key.strip() == name:
            return value.strip()
    return None


# -- input_qss : le style de champ reinvente 9 fois devient UN helper ---------

def test_input_qss_targets_line_edit_and_spinbox():
    """Both controls must be styled BY THE SAME rule -- the helper's promise is
    that a spinbox is a line edit with buttons, not a lookalike drifting on its
    own. And the rule must really paint (a mention is not a style)."""
    qss = theme.input_qss(DARK)
    base = _rule(qss, "QLineEdit")
    assert base == _rule(qss, "QSpinBox"), qss
    assert _prop(base, "background-color"), base
    assert _prop(base, "border"), base


def test_input_qss_hover_and_focus_are_green():
    """La convention de juin : bordure signal_ok au hover ET au focus (meme
    comportement que combo_qss). C'est precisement le symptome utilisateur
    (« pas le meme comportement en hover partout »).

    The green is a BORDER: a rule repainting the fill would look like a
    different control on hover, which is the very drift being fixed."""
    for scheme in (DARK, LIGHT):
        qss = theme.input_qss(scheme)
        for selector in ("QLineEdit:hover", "QSpinBox:hover",
                         "QLineEdit:focus", "QSpinBox:focus"):
            body = _rule(qss, selector)
            assert _prop(body, "border-color") == scheme.signal_ok, (selector, body)
            assert _prop(body, "background-color") is None, (selector, body)


def test_input_qss_uses_the_input_background():
    for scheme in (DARK, LIGHT):
        base = _rule(theme.input_qss(scheme), "QLineEdit")
        assert _prop(base, "background-color") == scheme.input_bg, base


def test_input_qss_has_a_disabled_state():
    for scheme in (DARK, LIGHT):
        body = _rule(theme.input_qss(scheme), "QLineEdit:disabled")
        assert _prop(body, "color") == scheme.disabled_text, body


def test_input_qss_honours_its_named_parameters():
    """font_pt / padding / radius exist for the call sites that must keep a
    tighter field (the delestage tasks will pass them); hard-coded values would
    silently ignore the caller."""
    base = _rule(theme.input_qss(DARK, font_pt=13, padding="2px 5px", radius=11),
                 "QLineEdit")
    assert _prop(base, "font-size") == "13pt", base
    assert _prop(base, "padding") == "2px 5px", base
    assert _prop(base, "border-radius") == "11px", base


# -- app_qss : LA feuille globale, composee uniquement de helpers -------------

def test_app_qss_builds_for_both_themes():
    for scheme in (DARK, LIGHT):
        assert len(theme.app_qss(scheme)) > 1000


def test_app_qss_has_the_default_button_and_the_variants():
    """Secondary est le defaut de tout QPushButton nu ; primary/destructive/
    bare s'activent par propriete dynamique (le mecanisme que
    dialog_controls_qss utilise depuis juin, generalise)."""
    qss = theme.app_qss(DARK)
    assert 'QPushButton[variant="primary"]' in qss, "variant primary absent"
    assert 'QPushButton[variant="destructive"]' in qss, "variant destructive absent"
    assert 'QPushButton[variant="bare"]' in qss, "variant bare absent"


def test_app_qss_covers_every_standard_control():
    qss = theme.app_qss(DARK)
    for sel in ("QPushButton", "QComboBox", "QRadioButton", "QCheckBox",
                "QLineEdit", "QSpinBox", "QToolTip", "QScrollBar", "QMenu",
                "QMessageBox"):
        assert sel in qss, f"{sel} absent de app_qss"


def test_app_qss_never_paints_widget_backgrounds():
    """Regle CLAUDE.md : les fonds de conteneurs restent a la QPalette.
    Un selecteur QWidget/QDialog nu dans la feuille globale casserait la
    convention (conflits QPalette/QSS) -- on verifie qu'il n'y en a AUCUN."""
    import re
    for scheme in (DARK, LIGHT):
        qss = theme.app_qss(scheme)
        hits = re.findall(r"(?<![\w])Q(?:Widget|Dialog)\s*\{", qss)
        assert not hits, hits


def test_bare_button_is_transparent_and_borderless():
    qss = theme.bare_button_qss(DARK)
    assert 'QPushButton[variant="bare"]' in qss
    assert "transparent" in qss
    assert "border: none" in qss


def test_help_button_declares_its_own_padding():
    """LA regression de l'allumage, verrouillee. Le bouton rond « ? » fait
    24x24 : sans `padding: 0` il herite du padding 7px 18px du defaut global,
    qui pousse le point d'interrogation HORS du bouton -- le glyphe disparait
    purement et simplement. Tout bouton a taille fixe doit declarer son
    padding."""
    body = _rule(theme.help_button_qss(DARK), 'QPushButton[variant="help"]')
    assert _prop(body, "padding") == "0", body
    assert _prop(body, "background-color") == DARK.signal_ok, body


# -- LA GARDE : le QSS de controle standard vit dans theme.py ----------------

# Un litteral QSS qui ouvre un bloc sur un selecteur de controle standard :
# `QPushButton {`, `QLineEdit:focus {{`, `QPushButton[variant="x"]:hover {`,
# `QMessageBox QPushButton {`, `QComboBox QAbstractItemView::item {`...
#
# Cette forme a ete VERIFIEE empiriquement (11 chaines a matcher, 6 pieges
# Python a ignorer). Trois points la rendent juste, et une version naive
# echoue sur les deux premiers :
#  - attributs et pseudo-etats dans N'IMPORTE QUEL ordre : en QSS on ecrit
#    `QPushButton[variant="primary"]:hover`, attribut AVANT pseudo ;
#  - selecteurs DESCENDANTS et listes a virgule, y compris sur deux lignes ;
#  - l'accolade doit etre sur la MEME ligne (`[ \t]*`, pas `\s*`) : sinon
#    `from ... import QPushButton, QComboBox` suivi plus bas d'un dict Python
#    devient un faux positif. Le piege inverse, `dict[str, QPushButton] = {}`,
#    est ecarte parce qu'aucune alternative ne consomme `]` ni `=`.
#
# ⚠️ `QSlider` AJOUTE le 2026-08-11, et ce n'est pas un detail de couverture :
# le curseur etait ecrit DEUX fois, byte-identique aux espaces pres (Studio /
# onglet IA), et cette duplication a survecu a tout le chantier **parce que la
# garde ne la voyait pas**. Un controle absent d'ici n'est pas seulement non
# verifie : rien n'empeche sa 3e copie. L'elargissement fait mecaniquement
# GROSSIR le perimetre mesure -- c'est voulu : on prefere un compteur honnete
# a un compteur flatteur.
_CONTROL_QSS_RE = re.compile(
    r"Q(?:PushButton|ComboBox|CheckBox|RadioButton|LineEdit|SpinBox|Slider)"
    r"(?:\[[^\]\n]*\]|::?[\w-]+|\s*,\s*Q\w+|\s+Q\w+)*"
    r"[ \t]*\{")

# Fichier -> raison. REGLE : cette liste ne peut que RETRECIR. Chaque zone du
# delestage retire les siens ; a la fin il ne doit rester que les widgets
# d'IDENTITE, dont le dessin propre est voulu. Une entree qui ne matche plus
# rien fait echouer la suite (entree morte), pour qu'on ne collectionne pas
# des fossiles.
_QSS_EXEMPTIONS: dict[str, str] = {
    # --- Delestage a venir (spec 2026-08-11). Compteur d'avancement.
    "ui/studio_view.py":                         "controles bespoke du Studio (pastille Outils, + rond, chevrons, champ titre)",
    "ui/feature_dropdown.py":                    "identite : lignes du popup de fonctionnalites (surlignage de ligne)",
    "ui/settings_dialog.py":                     "bespoke : pages de reglages (TODO #50)",
    "ui/board_view.py":                          "bespoke : cartes de selection de carte (TODO #50)",
    "ui/library_view.py":                        "bespoke : cartes de librairie (TODO #50)",
    "ui/wiring/wiring_diagram_dialog.py":        "bespoke : barre du schema, champ de zoom (TODO #50)",
    "ui/chat/chat_view.py":                      "bespoke : controles du panneau de chat (TODO #50)",
    # --- Widgets d'IDENTITE : dessin propre voulu, jamais delestes.
    # ia_view a ete DELESTE (radios en gras -> radio_checkbox_qss(font_weight=),
    # combo -> combo_qss) ; il ne reste que ce cas, qui n'est pas de la dette :
    # un QLineEdit rendu transparent DANS un combo editable, pour ne pas
    # repeindre le cadre du combo ni masquer sa fleche. Le commentaire du
    # fichier porte l'intention.
    "ui/ia_view.py":       "identite : lineEdit transparent dans le combo de modeles",
    "ui/sidebar.py":       "identite : navigation (etat actif, barre verte 2px)",
    "ui/topbar.py":        "identite : barre haute, boutons plats sur sidebar_bg",
    "ui/toggle_switch.py": "identite : segmented control dark/light anime",
    "ui/nudge_banner.py":  "identite : bandeau de progression, variantes de couleur",
    "ui/chat/chat_message.py": "identite : bulles de conversation",
    "ui/wiring/routing/zone_editor/toolbar.py": "outil interne de dev, hors app",
}


def _iter_ui_sources():
    yield ROOT / "main.py"
    for p in sorted((ROOT / "ui").rglob("*.py")):
        yield p


def test_standard_control_qss_lives_only_in_theme():
    """LE verrou anti-recidive. Sans lui, le prochain dialogue reinvente le
    bouton -- c'est arrive 424 fois, et le style de champ texte etait refait a
    la main dans 8 fichiers. Le QSS d'un controle standard s'ecrit UNE fois
    dans theme.py ; ailleurs on pose une propriete variant= ou on appelle un
    helper avec ses parametres."""
    offenders = []
    for path in _iter_ui_sources():
        rel = path.relative_to(ROOT).as_posix()
        if rel == "ui/theme.py" or rel in _QSS_EXEMPTIONS:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for m in _CONTROL_QSS_RE.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            offenders.append(f"{rel}:{line} -> {m.group(0)!r}")
    assert not offenders, (
        "QSS de controle standard hors theme.py :\n  " + "\n  ".join(offenders))


def test_every_exemption_still_matches_something():
    """Une exemption qui ne matche plus rien est une entree morte : la liste
    doit RETRECIR au rythme du delestage, jamais accumuler des fossiles. Ce
    test est ce qui rend la regle mecanique plutot que declarative."""
    dead = []
    for rel in _QSS_EXEMPTIONS:
        p = ROOT / rel
        if not p.exists():
            dead.append(f"{rel} (fichier disparu)")
        elif not _CONTROL_QSS_RE.search(
                p.read_text(encoding="utf-8", errors="replace")):
            dead.append(rel)
    assert not dead, f"exemptions mortes, a retirer : {dead}"


def test_card_qss_marks_selection_with_the_app_accent():
    """L'etat selectionne d'une card doit utiliser signal_ok, comme tout etat
    actif de l'app — sinon la card devient le seul controle a signaler la
    selection dans une autre couleur."""
    from ui.theme import DARK, LIGHT, card_qss
    for c in (DARK, LIGHT):
        assert c.signal_ok in card_qss(c, selected=True)
        assert c.signal_ok not in card_qss(c, selected=False).split(":hover")[0]
        # Le survol verdit dans les DEUX etats : c'est la convention de l'app.
        assert ":hover" in card_qss(c, selected=False)


def test_card_qss_declares_a_disabled_state_like_the_other_helpers():
    """Chaque helper de theme.py declare son :disabled — c'est ce que le
    delestage #50 a mesure comme systematiquement oublie en local."""
    from ui.theme import DARK, card_qss
    assert ":disabled" in card_qss(DARK)


TESTS = [
    test_input_qss_targets_line_edit_and_spinbox,
    test_input_qss_hover_and_focus_are_green,
    test_input_qss_uses_the_input_background,
    test_input_qss_has_a_disabled_state,
    test_input_qss_honours_its_named_parameters,
    test_app_qss_builds_for_both_themes,
    test_app_qss_has_the_default_button_and_the_variants,
    test_app_qss_covers_every_standard_control,
    test_app_qss_never_paints_widget_backgrounds,
    test_bare_button_is_transparent_and_borderless,
    test_help_button_declares_its_own_padding,
    test_standard_control_qss_lives_only_in_theme,
    test_every_exemption_still_matches_something,
    test_card_qss_marks_selection_with_the_app_accent,
    test_card_qss_declares_a_disabled_state_like_the_other_helpers,
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
