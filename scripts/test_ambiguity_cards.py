"""La card de composant selectionnable de la modale d'ambiguite.

Meme contenu que la fiche de l'onglet « Composants » (nom, ligne
bibliotheque, description, ligne de cablage, pastille « Perso », crayon) et
meme mecanique de selection que la card de `LibChoiceDialog`. Ce fichier
verrouille les deux moities : ce que la card DIT, et ce qu'elle FAIT.

Le harnais monte l'app comme main.py — style `windows11` + `_GreenInfoStyle` —
et non le Fusion par defaut de QT_QPA_PLATFORM=offscreen : une mesure visuelle
prise sous Fusion ne dit rien de ce que l'utilisateur voit. Le curseur est
ecarte a (2000, 2000) et les widgets mesures sont deplaces loin de l'origine :
offscreen, `QCursor.pos()` est FIGE a (10, 10), donc tout widget place pres de
l'origine se peint `:hover` en permanence et une comparaison rend 0 px
d'ecart.

Run : python scripts/test_ambiguity_cards.py
"""
from __future__ import annotations
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONUTF8", "1")
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# QApplication gardee au niveau module : sans reference, une app temporaire
# GC-ee puis la construction d'un QWidget plante le process (0xC0000409).
from PyQt6.QtWidgets import QApplication  # noqa: E402
_APP = QApplication.instance() or QApplication([])

from PyQt6.QtCore import Qt, QEvent  # noqa: E402
from PyQt6.QtGui import QCursor, QKeyEvent  # noqa: E402
from PyQt6.QtWidgets import QLabel, QPushButton  # noqa: E402

# Le curseur figé force le :hover sur tout widget proche de l'origine.
QCursor.setPos(2000, 2000)

from ui.fonts import setup_fonts  # noqa: E402
setup_fonts(_APP)

# ── Hermetisme : AUCUN test ne doit lire ~/Documents/Promptuino ────────────
import ui.declared_components as dc  # noqa: E402
import ui.registry_lookup as rl  # noqa: E402
import ui.component_libs as cl  # noqa: E402

dc.set_registry([])
rl.set_cache_for_tests({})
cl.set_registry({})

from ui.theme import theme_manager, build_app_palette  # noqa: E402
from ui.i18n import lang_manager  # noqa: E402
from ui.component_index import (  # noqa: E402
    ComponentInfo, ORIGIN_DECLARED, build_index,
)
from ui.wiring.ambiguity_cards import ComponentCard  # noqa: E402


def _styled_app():
    try:
        from PyQt6.QtWidgets import QStyleFactory
        base = QStyleFactory.create("windows11")
        if base is not None:
            _APP.setStyle(base)
        import main as _main
        _APP.setStyle(_main._GreenInfoStyle())
        theme_manager.apply_dark()
        _APP.setPalette(build_app_palette(theme_manager.current))
        _APP.setStyleSheet(_main._app_style(theme_manager.current))
    except Exception:
        theme_manager.apply_dark()


_INDEX: dict[str, ComponentInfo] = {}


def _info_for(key: str) -> ComponentInfo:
    if not _INDEX:
        _INDEX.update({i.key: i for i in build_index()})
    return _INDEX[key]


def _declared_info() -> ComponentInfo:
    """Une fiche « perso » fabriquee a la main : le registre declare reste
    vide (hermetisme), donc build_index() n'en produit aucune."""
    return ComponentInfo(
        key="monchip", name="MonChip", lib="", origin=ORIGIN_DECLARED,
        editable=True, pin_count=3, wiring="known", library="unknown",
        description="Un composant que j'ai decrit moi-meme.",
        keywords=("monchip",))


def _all_label_texts(w) -> list[str]:
    """Le texte de chaque QLabel de la card. `_ElidedLabel` coupe a
    l'affichage : on lit son texte COMPLET, sinon une card non affichee
    (largeur 0) et une card affichee ne rendraient pas la meme chose."""
    out = []
    for lbl in w.findChildren(QLabel):
        out.append(lbl.fullText() if hasattr(lbl, "fullText") else lbl.text())
    return out


def _badge_of(card):
    """Le QLabel de la pastille « Perso », ou None."""
    wanted = lang_manager.current.components_filter_declared
    for lbl in card.findChildren(QLabel):
        if lbl.text() == wanted:
            return lbl
    return None


def _press(widget, key, text=""):
    widget.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key,
                                   Qt.KeyboardModifier.NoModifier, text))


# ── Ce que la card DIT ────────────────────────────────────────────────────

def test_card_shows_the_component_facts():
    """nom + ligne lib + broches — les memes lignes que l'onglet."""
    _styled_app()
    info = _info_for("buzzer")
    card = ComponentCard(info, selectable=True)
    texts = _all_label_texts(card)
    assert any("buzzer" in t for t in texts), texts
    assert any("librairie" in t.lower() or "library" in t.lower()
               or (info.lib and info.lib in t) for t in texts), texts
    # La ligne de cablage suit l'axe `wiring`, comme dans l'onglet.
    s = lang_manager.current
    assert any(t == s.components_pin_count.format(n=info.pin_count)
               for t in texts), texts
    card.deleteLater()


def test_the_library_line_follows_the_three_state_axis():
    """`none` et `unknown` etaient la meme absence silencieuse dans l'ancien
    booleen : la card doit les distinguer, exactement comme l'onglet."""
    _styled_app()
    s = lang_manager.current
    none_card = ComponentCard(_info_for("led"))           # library == "none"
    unknown_card = ComponentCard(_declared_info())        # library == "unknown"
    assert s.components_library_none in _all_label_texts(none_card)
    assert s.components_lib_unknown in _all_label_texts(unknown_card)
    for c in (none_card, unknown_card):
        c.deleteLater()


def test_perso_badge_only_on_declared():
    _styled_app()
    declared = ComponentCard(_declared_info(), selectable=True)
    curated = ComponentCard(_info_for("led"), selectable=True)
    assert _badge_of(declared) is not None
    assert _badge_of(curated) is None
    for c in (declared, curated):
        c.deleteLater()


def test_the_badge_is_painted_by_the_shared_theme_helper():
    """La pastille de la card et celle de l'onglet doivent rester
    IDENTIQUES : c'est la raison d'etre du helper `theme.perso_badge_qss`.
    Deux recettes locales derivent — c'est la lecon du TODO #50."""
    _styled_app()
    from ui.theme import perso_badge_qss
    card = ComponentCard(_declared_info(), selectable=True)
    badge = _badge_of(card)
    assert badge is not None
    assert badge.styleSheet() == perso_badge_qss(theme_manager.current)
    card.deleteLater()


def test_the_tab_and_the_modal_render_the_same_badge():
    """Preuve en PIXELS, pas en chaine : les deux portes affichent la meme
    pastille. Une egalite de QSS ne dit rien si les deux widgets n'ont ni la
    meme police ni la meme taille."""
    _styled_app()
    from ui.components_view import _ComponentCardWidget
    info = _declared_info()
    tab_card = _ComponentCardWidget(info, lang_manager.current)
    modal_card = ComponentCard(info, selectable=True)
    # Loin de l'origine : le curseur figé a (10, 10) force le :hover sur tout
    # ce qui s'y trouve, et les deux mesures deviendraient identiques pour la
    # mauvaise raison.
    grabs = []
    for card in (tab_card, modal_card):
        card.move(800, 800)
        badge = _badge_of(card)
        assert badge is not None
        badge.adjustSize()
        grabs.append(badge.grab().toImage())
    assert grabs[0].size() == grabs[1].size(), (grabs[0].size(),
                                                grabs[1].size())
    diff = sum(1 for y in range(grabs[0].height())
               for x in range(grabs[0].width())
               if grabs[0].pixel(x, y) != grabs[1].pixel(x, y))
    assert diff == 0, f"{diff} pixels differents entre les deux portes"
    for c in (tab_card, modal_card):
        c.deleteLater()


def test_the_two_cards_say_the_same_thing_about_every_component():
    """LE verrou que la factorisation de la pastille ne donne pas.

    Le QSS de la pastille a demenage dans theme.py pour que les deux portes
    ne divergent pas — mais le CONTENU, lui, est encore ecrit DEUX fois
    (~50 lignes : les deux axes a trois etats, le dedoublonnage `lib == name`
    propre au corpus, le plafond de description). Rien ne l'empechait de
    deriver : c'est exactement la faute que la factorisation pretendait
    corriger, laissee ouverte a cote.

    Balaye TOUT l'index, pas un echantillon : une divergence n'apparaitrait
    que sur la fiche qui porte l'etat rare (le seul composant dont la lib
    porte le nom, le seul dont le cablage vaut `none`...).
    """
    _styled_app()
    from ui.components_view import _ComponentCardWidget
    s = lang_manager.current
    infos = build_index()
    # Un index vide rendrait ce test vert sans rien verifier.
    assert len(infos) > 100, len(infos)
    diffs = []
    for info in infos:
        tab = _ComponentCardWidget(info, s)
        modal = ComponentCard(info)
        if _all_label_texts(tab) != _all_label_texts(modal):
            diffs.append((info.key, _all_label_texts(tab),
                          _all_label_texts(modal)))
        tab.deleteLater()
        modal.deleteLater()
    assert not diffs, diffs


def test_pencil_present_and_enabled_on_every_card():
    """Decision utilisateur : crayon actif partout, comme dans l'onglet."""
    _styled_app()
    for key in ("led", "buzzer"):
        card = ComponentCard(_info_for(key), selectable=True)
        btn = card.findChild(QPushButton)
        assert btn is not None and btn.isEnabled(), key
        card.deleteLater()


def test_the_pencil_emits_the_card_key():
    _styled_app()
    card = ComponentCard(_info_for("buzzer"), selectable=True)
    got = []
    card.edit_requested.connect(got.append)
    card.findChild(QPushButton).click()
    assert got == ["buzzer"]
    card.deleteLater()


def test_fallback_card_for_a_type_without_fiche():
    """module_generic n'a pas de fiche (non-composant) : card minimale,
    nom seul, jamais l'id brut."""
    _styled_app()
    assert "module_generic" not in {i.key for i in build_index()}
    card = ComponentCard.fallback("module_generic", "module", selectable=True)
    texts = _all_label_texts(card)
    assert any("module" in t for t in texts), texts
    assert not any("module_generic" in t for t in texts), texts
    card.deleteLater()


def test_a_fallback_card_invents_no_library_nor_pin_count():
    """« Nom seul » n'est pas une economie de mise en page : une card sans
    fiche n'a AUCUN fait a annoncer, et en inventer un (« aucune librairie a
    installer », « 0 broches ») serait presenter une ignorance comme un
    verdict."""
    _styled_app()
    s = lang_manager.current
    card = ComponentCard.fallback("module_generic", "module")
    texts = _all_label_texts(card)
    for forbidden in (s.components_library_none, s.components_lib_unknown,
                      s.components_wiring_none, s.components_wiring_unknown,
                      s.components_pin_count.format(n=0)):
        assert forbidden not in texts, (forbidden, texts)
    # Et surtout : aucune fiche n'est FABRIQUEE. `info is None` est le
    # sentinel — un ComponentInfo bidon aurait porte un `wiring` et un
    # `library` inventes, que le picker aurait ensuite promenes partout.
    assert card.info is None
    assert card.key == "module_generic" and card.name == "module"
    card.deleteLater()


# ── Ce que la card FAIT ───────────────────────────────────────────────────

def test_the_card_inherits_the_shared_card_style():
    """`libCard` est ce qui la branche sur `theme.card_qss` : aucun QSS
    nouveau, la meme recette que la card de bibliotheque."""
    _styled_app()
    from ui.theme import card_qss
    card = ComponentCard(_info_for("led"))
    assert card.objectName() == "libCard"
    assert card.styleSheet() == card_qss(theme_manager.current, selected=False)
    card.deleteLater()


def test_selection_is_visual_and_exclusive_via_signal():
    """⚠️ Le nom vient du plan ; ce qu'il verrouille est plus etroit, et
    c'est volontaire :

    - VISUEL : `set_selected` pose la propriete dynamique `picked` ET
      repeint via `card_qss(selected=...)` — la propriete rend l'etat
      lisible de l'exterieur, mais c'est bien la feuille qui peint ;
    - EXCLUSIF : il verifie surtout que `set_selected` n'emet RIEN. C'est
      la condition de l'exclusivite, pas l'exclusivite elle-meme (qui
      appartient au picker : une card ne connait pas ses soeurs). Un ordre
      du picker n'est pas un choix de l'utilisateur — s'il emettait,
      deselectionner les soeurs relancerait le picker sur lui-meme.

    L'exclusivite entre plusieurs cards se teste en tache 6, sur le picker.
    """
    _styled_app()
    from ui.theme import card_qss
    card = ComponentCard(_info_for("led"), selectable=True)
    got = []
    card.picked.connect(lambda c: got.append(c))
    card.set_selected(True)
    assert card.property("picked") is True    # card_qss(selected) route
    assert card.is_selected() is True
    assert card.styleSheet() == card_qss(theme_manager.current, selected=True)
    # `set_selected` est l'ordre de la modale, pas un choix de l'utilisateur :
    # il ne doit RIEN emettre, sinon preselectionner declencherait une boucle.
    assert got == []
    card.set_selected(False)
    assert card.property("picked") is False
    card.deleteLater()


def test_selection_state_is_independent_per_card():
    """La card ne connait pas ses soeurs : l'exclusivite appartient au
    picker (meme partage des roles que `_LibraryCard`)."""
    _styled_app()
    a = ComponentCard(_info_for("led"), selectable=True)
    b = ComponentCard(_info_for("buzzer"), selectable=True)
    a.set_selected(True)
    b.set_selected(True)
    a.set_selected(False)
    assert a.is_selected() is False and b.is_selected() is True
    for c in (a, b):
        c.deleteLater()


def test_a_selectable_card_is_focusable_and_selects_on_space():
    """Remplacer une QRadioButton par une card PERD le clavier : il doit
    etre rendu, sinon la refonte est une regression d'accessibilite."""
    _styled_app()
    card = ComponentCard(_info_for("led"), selectable=True)
    assert card.focusPolicy() == Qt.FocusPolicy.StrongFocus
    got = []
    card.picked.connect(got.append)
    _press(card, Qt.Key.Key_Space, " ")
    assert got == [card]
    card.deleteLater()


def test_only_space_selects_not_enter_or_arrows():
    """Entree reste au bouton de la modale — le piege deja paye sur les
    modales du cablage (cf. test_dialog_enter_key.py)."""
    _styled_app()
    card = ComponentCard(_info_for("led"), selectable=True)
    got = []
    card.picked.connect(got.append)
    for key, text in ((Qt.Key.Key_Return, "\r"), (Qt.Key.Key_Enter, "\r"),
                      (Qt.Key.Key_Down, "")):
        _press(card, key, text)
    assert got == []
    card.deleteLater()


def test_a_non_selectable_card_never_picks_and_takes_no_focus():
    """`selectable=False` sert a MONTRER un composant sans le proposer :
    une card qui repond quand meme au clavier ferait croire a un choix."""
    _styled_app()
    card = ComponentCard(_info_for("led"), selectable=False)
    assert card.focusPolicy() == Qt.FocusPolicy.NoFocus
    got = []
    card.picked.connect(got.append)
    _press(card, Qt.Key.Key_Space, " ")
    assert got == []
    card.deleteLater()


def test_a_theme_switch_repaints_the_card_and_its_badge():
    """Bascule de theme modale ouverte (procedure QA R7) : la card, sa
    pastille et son crayon doivent suivre."""
    _styled_app()
    from ui.theme import card_qss, perso_badge_qss
    card = ComponentCard(_declared_info(), selectable=True)
    card.set_selected(True)
    theme_manager.apply_light()
    try:
        light = theme_manager.current
        assert card.styleSheet() == card_qss(light, selected=True)
        assert _badge_of(card).styleSheet() == perso_badge_qss(light)
    finally:
        theme_manager.apply_dark()
    card.deleteLater()


TESTS = [
    test_card_shows_the_component_facts,
    test_the_library_line_follows_the_three_state_axis,
    test_perso_badge_only_on_declared,
    test_the_badge_is_painted_by_the_shared_theme_helper,
    test_the_tab_and_the_modal_render_the_same_badge,
    test_the_two_cards_say_the_same_thing_about_every_component,
    test_pencil_present_and_enabled_on_every_card,
    test_the_pencil_emits_the_card_key,
    test_fallback_card_for_a_type_without_fiche,
    test_a_fallback_card_invents_no_library_nor_pin_count,
    test_the_card_inherits_the_shared_card_style,
    test_selection_is_visual_and_exclusive_via_signal,
    test_selection_state_is_independent_per_card,
    test_a_selectable_card_is_focusable_and_selects_on_space,
    test_only_space_selects_not_enter_or_arrows,
    test_a_non_selectable_card_never_picks_and_takes_no_focus,
    test_a_theme_switch_repaints_the_card_and_its_badge,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t()
            print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1
            print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
