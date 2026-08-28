"""La modale de choix de bibliotheque : cards, etats, clavier, contrat.

Le harnais monte l'app comme main.py — style `windows11` + `_GreenInfoStyle` —
et non le Fusion par defaut de QT_QPA_PLATFORM=offscreen. Lecon payee le
2026-08-12 : une mesure visuelle prise sous Fusion ne dit rien de ce que
l'utilisateur voit.

Run : python scripts/test_lib_choice_dialog.py
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

from PyQt6.QtCore import Qt  # noqa: E402
from ui.fonts import setup_fonts  # noqa: E402
setup_fonts(_APP)

from ui.theme import theme_manager, build_app_palette  # noqa: E402
from ui import library_index as li  # noqa: E402
from ui.library_index import LibraryRecord  # noqa: E402
import ui.lib_choice_dialog as lcd  # noqa: E402

# ⚠️ NEUTRALISATION DU CHARGEUR, valable pour TOUT ce fichier.
#
# `LibChoiceDialog.__init__` lance un `_IndexLoader` des que l'index n'est pas
# charge et qu'un fichier de config est fourni. Sans ce remplacement, chaque
# construction dans un test invoquerait un VRAI `arduino-cli` : lent, dependant
# de la machine, et surtout le fil rendrait la main en appelant
# `set_index([])`, ce qui ECRASERAIT l'index que le test vient d'injecter. Un
# test vert un jour sur deux, pour une raison invisible.
class _FakeSignal:
    def connect(self, *_a, **_k):
        pass


class _FakeLoader:
    def __init__(self, *_a, **_k):
        self.done = _FakeSignal()

    def start(self):
        pass


lcd._IndexLoader = _FakeLoader


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


def _rec(name, **kw):
    return LibraryRecord(name=name, **kw)


def _s():
    """Les chaines de la langue en vigueur."""
    from ui.i18n import lang_manager
    return lang_manager.current


def test_a_card_shows_what_the_registry_declares():
    _styled_app()
    from PyQt6.QtWidgets import QLabel
    card = lcd._LibraryCard(_rec(
        "Adafruit AS7341", author="Adafruit", version="1.4.1",
        category="Sensors", sentence="Arduino library for the AS7341",
        architectures=("*",), dependencies=("Adafruit BusIO",)), arch="avr")
    texts = " | ".join(l.text() for l in card.findChildren(QLabel))
    assert "Adafruit AS7341" in texts
    assert "Adafruit" in texts and "1.4.1" in texts and "Sensors" in texts
    assert "Arduino library for the AS7341" in texts
    assert "Adafruit BusIO" in texts
    card.deleteLater()


def test_a_card_falls_back_to_the_paragraph_when_the_sentence_is_empty():
    """Correction post-chantier (2026-08-12) : le schema du registre permet
    une entree dont `sentence` est vide et `paragraph` renseigne. Avant ce
    correctif, `_LibraryCard` ne lisait jamais `paragraph` -- la card restait
    sans aucune description alors que le texte etait deja charge en
    memoire."""
    _styled_app()
    from PyQt6.QtWidgets import QLabel
    card = lcd._LibraryCard(_rec(
        "Grove Moisture Sensor", sentence="", paragraph="Longer description"),
        arch="avr")
    texts = " | ".join(l.text() for l in card.findChildren(QLabel))
    assert "Longer description" in texts
    card.deleteLater()


def test_a_card_prefers_the_sentence_over_the_paragraph_when_both_exist():
    """La moitie inverse : quand les deux sont renseignes, c'est `sentence`
    (le plus court, prevu pour cet usage) qui s'affiche, pas `paragraph`."""
    _styled_app()
    from PyQt6.QtWidgets import QLabel
    card = lcd._LibraryCard(_rec(
        "Servo", sentence="Short one", paragraph="Much longer one"),
        arch="avr")
    texts = " | ".join(l.text() for l in card.findChildren(QLabel))
    assert "Short one" in texts
    assert "Much longer one" not in texts
    card.deleteLater()


def test_a_retired_library_says_so():
    _styled_app()
    from PyQt6.QtWidgets import QLabel
    card = lcd._LibraryCard(_rec("Vieux truc", types=("Retired",)), arch="avr")
    texts = " | ".join(l.text() for l in card.findChildren(QLabel))
    assert _s().lib_choice_badge_retired in texts
    card.deleteLater()


def test_an_incompatible_library_says_so_only_when_the_board_is_known():
    """Regle d'honnetete : sans carte selectionnee, aucune revendication."""
    _styled_app()
    from PyQt6.QtWidgets import QLabel
    bad = _rec("Esp only", architectures=("esp32",))
    known = lcd._LibraryCard(bad, arch="avr")
    unknown = lcd._LibraryCard(bad, arch="")
    t_known = " | ".join(l.text() for l in known.findChildren(QLabel))
    t_unknown = " | ".join(l.text() for l in unknown.findChildren(QLabel))
    badge = _s().lib_choice_badge_incompatible
    assert badge in t_known
    assert badge not in t_unknown
    # Et surtout : pas non plus de « compatible toutes cartes » invente.
    assert _s().lib_choice_meta_all_boards not in t_unknown
    for c in (known, unknown):
        c.deleteLater()


def test_a_card_is_focusable_and_selects_on_space():
    """Remplacer une QRadioButton par une card PERD le clavier : il doit etre
    rendu, sinon la refonte est une regression d'accessibilite."""
    _styled_app()
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent
    card = lcd._LibraryCard(_rec("Servo"), arch="avr")
    assert card.focusPolicy() == Qt.FocusPolicy.StrongFocus
    got = []
    card.picked.connect(lambda rec: got.append(rec))
    card.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                                 Qt.KeyboardModifier.NoModifier, " "))
    assert [r.name for r in got] == ["Servo"]
    card.deleteLater()


def test_selection_state_is_independent_per_card():
    """Chaque card porte son propre etat -- ce test ne prouve PAS
    l'exclusivite (une seule selectionnee a la fois) : ca reste le travail de
    la modale a la tache suivante, la card ne connaissant pas ses soeurs
    (docstring de `_LibraryCard`). Il verifie seulement que `set_selected` sur
    une card ne modifie pas l'etat d'une autre."""
    _styled_app()
    a = lcd._LibraryCard(_rec("A"), arch="avr")
    b = lcd._LibraryCard(_rec("B"), arch="avr")
    a.set_selected(True)
    b.set_selected(True)
    a.set_selected(False)
    assert a.is_selected() is False and b.is_selected() is True
    for c in (a, b):
        c.deleteLater()


def test_the_in_use_badge_shows_only_when_in_use():
    """Depuis la Task 2, l'ordre de la liste NE dit PAS quelle bibliotheque
    l'app utilise (_pick_candidate et _match_rank divergent) : ce badge est
    donc la SEULE chose qui porte cette information a l'utilisateur. Les deux
    moitiees comptent -- un badge qui s'affiche toujours ne dirait rien."""
    _styled_app()
    from PyQt6.QtWidgets import QLabel
    used = lcd._LibraryCard(_rec("Servo"), arch="avr", in_use=True)
    unused = lcd._LibraryCard(_rec("Servo"), arch="avr", in_use=False)
    t_used = " | ".join(l.text() for l in used.findChildren(QLabel))
    t_unused = " | ".join(l.text() for l in unused.findChildren(QLabel))
    badge = _s().lib_choice_badge_in_use
    assert badge in t_used
    assert badge not in t_unused
    for c in (used, unused):
        c.deleteLater()


def test_only_space_selects_not_enter_or_arrows():
    """Le commentaire du code dit qu'Espace SEUL selectionne (Entree reste au
    bouton de la modale -- le piege deja paye sur les modales du cablage, cf.
    test_dialog_enter_key.py). Seul le cas Espace etait teste jusqu'ici ; ceci
    verifie l'autre moitie du contrat, sinon un futur refactor pourrait faire
    declencher Entree sans qu'aucun test rougisse."""
    _styled_app()
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent
    card = lcd._LibraryCard(_rec("Servo"), arch="avr")
    got = []
    card.picked.connect(lambda rec: got.append(rec))
    for key, text in ((Qt.Key.Key_Return, "\r"), (Qt.Key.Key_Down, "")):
        card.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key,
                                     Qt.KeyboardModifier.NoModifier, text))
    assert got == []
    card.deleteLater()


def _dialog(*, current="Adafruit AS7341", alternatives=None, token="as7341",
            arch="avr", config_file="dummy.yaml"):
    return lcd.LibChoiceDialog(
        None, token=token, current_lib=current,
        alternatives=list(alternatives or ["DFRobot_AS7341"]),
        config_file=config_file, arch=arch)


def _card_names(dlg):
    return [c.record.name for c in dlg._cards]


def test_before_the_index_arrives_the_short_list_is_usable():
    _styled_app()
    li.set_index([]); li._LOADED = False
    dlg = _dialog()
    # Les alternatives en cache s'affichent tout de suite, la lib en usage en
    # tete — c'est la raison d'etre historique de la modale.
    assert _card_names(dlg) == ["Adafruit AS7341", "DFRobot_AS7341"]
    assert dlg._lbl_count.text() == _s().lib_choice_loading
    dlg.deleteLater()


def test_once_loaded_the_prefilled_query_filters_the_index():
    _styled_app()
    li.set_index([
        _rec("Adafruit AS7341", author="Adafruit"),
        _rec("DFRobot_AS7341", author="DFRobot"),
        _rec("SparkFun AS7341L", author="SparkFun"),
        _rec("Servo", author="Arduino"),
    ])
    dlg = _dialog()
    dlg._refresh()
    assert "Servo" not in _card_names(dlg)
    assert len(_card_names(dlg)) == 3
    dlg.deleteLater()


def test_clearing_the_field_returns_to_the_short_list():
    _styled_app()
    li.set_index([_rec("Adafruit AS7341"), _rec("Servo"), _rec("OLED")])
    dlg = _dialog()
    dlg._search.setText("")
    assert _card_names(dlg) == ["Adafruit AS7341", "DFRobot_AS7341"]
    dlg.deleteLater()


def test_the_library_in_use_is_selected_and_badged():
    _styled_app()
    li.set_index([_rec("Adafruit AS7341"), _rec("DFRobot_AS7341")])
    dlg = _dialog()
    dlg._refresh()
    sel = [c for c in dlg._cards if c.is_selected()]
    assert [c.record.name for c in sel] == ["Adafruit AS7341"]
    dlg.deleteLater()


def test_only_one_card_stays_selected():
    _styled_app()
    li.set_index([_rec("Adafruit AS7341"), _rec("DFRobot_AS7341")])
    dlg = _dialog()
    dlg._refresh()
    dlg._on_card_picked(dlg._cards[1].record)
    assert [c.is_selected() for c in dlg._cards] == [False, True]
    dlg.deleteLater()


def test_a_capped_result_set_says_how_many_were_dropped():
    _styled_app()
    li.set_index([_rec(f"Servo {i}") for i in range(200)])
    dlg = _dialog(current="", alternatives=[], token="servo")
    dlg._refresh()
    assert len(dlg._cards) == lcd._MAX_CARDS
    txt = dlg._lbl_count.text()
    assert "200" in txt and str(lcd._MAX_CARDS) in txt
    dlg.deleteLater()


def test_no_match_says_so_with_the_query():
    _styled_app()
    li.set_index([_rec("Servo")])
    dlg = _dialog(current="", alternatives=[], token="zxq9000")
    dlg._refresh()
    assert dlg._cards == []
    assert "zxq9000" in dlg._lbl_empty.text()
    dlg.deleteLater()


def test_without_a_cli_the_field_is_disabled_and_says_why():
    _styled_app()
    li.set_index([]); li._LOADED = False
    dlg = _dialog(config_file=None)
    assert dlg._search.isEnabled() is False
    assert dlg._lbl_empty.text() == _s().lib_choice_search_unavailable
    # ... et la liste courte reste proposee.
    assert _card_names(dlg) == ["Adafruit AS7341", "DFRobot_AS7341"]
    dlg.deleteLater()


def test_validating_the_incumbent_decides_nothing():
    _styled_app()
    li.set_index([_rec("Adafruit AS7341")])
    dlg = _dialog()
    dlg._refresh()
    dlg._on_ok()
    assert dlg.chosen_lib == ""
    dlg.deleteLater()


def test_validating_another_card_returns_its_name():
    _styled_app()
    li.set_index([_rec("Adafruit AS7341"), _rec("DFRobot_AS7341")])
    dlg = _dialog()
    dlg._refresh()
    dlg._on_card_picked(dlg._cards[1].record)
    dlg._on_ok()
    assert dlg.chosen_lib == "DFRobot_AS7341"
    dlg.deleteLater()


def test_narrowing_the_search_away_from_a_pick_forgets_it():
    """LE defaut critique de la revue (2026-08-12) : choisir une card puis
    affiner la recherche jusqu'a l'exclure ne doit PAS laisser `_on_ok`
    valider une bibliotheque devenue invisible -- l'utilisateur croirait
    n'avoir rien choisi pendant qu'une preference s'ecrit. Meme regle que
    l'ancien `_clear_search_radios` (code a QRadioButton, retire par la
    Task 8) : on retombe sur la lib EN USAGE, jamais sur une alternative
    arbitraire."""
    _styled_app()
    li.set_index([_rec("Adafruit AS7341"), _rec("DFRobot_AS7341")])
    dlg = _dialog()
    dlg._search.setText("as734")
    dlg._refresh()
    other = next(c for c in dlg._cards if c.record.name == "DFRobot_AS7341")
    dlg._on_card_picked(other.record)
    dlg._search.setText("servo")  # ne matche plus rien, y compris le pick
    dlg._refresh()
    assert dlg._cards == []
    dlg._on_ok()
    assert dlg.chosen_lib != "DFRobot_AS7341"
    assert dlg.chosen_lib == ""
    dlg.deleteLater()


def test_narrowing_the_search_without_excluding_the_pick_keeps_it():
    """La moitie inverse du test precedent : si la card choisie reste dans
    les resultats apres une frappe de plus, la selection doit survivre --
    sinon le correctif serait juste un `_picked = self._current` aveugle qui
    oublierait TOUT choix a chaque frappe, pas seulement les invisibles."""
    _styled_app()
    li.set_index([_rec("Adafruit AS7341"), _rec("DFRobot_AS7341"),
                  _rec("SparkFun AS7341L")])
    dlg = _dialog()
    dlg._search.setText("as7341")
    dlg._refresh()
    other = next(c for c in dlg._cards if c.record.name == "DFRobot_AS7341")
    dlg._on_card_picked(other.record)
    dlg._search.setText("dfrobot")  # affine, mais le pick matche toujours
    dlg._refresh()
    assert _card_names(dlg) == ["DFRobot_AS7341"]
    assert dlg._cards[0].is_selected() is True
    dlg._on_ok()
    assert dlg.chosen_lib == "DFRobot_AS7341"
    dlg.deleteLater()


def test_clearing_the_field_after_a_capped_search_still_finds_the_incumbent():
    """Verrou de la limite assumee documentee sur `_records_to_show` : une
    lib en usage classee au-dela du plafond d'affichage n'apparait pas dans
    une recherche large -- mais vider le champ retombe sur la liste courte,
    qui la contient TOUJOURS (`choices_for` la place en premier). L'echap-
    patoire doit rester praticable, pas seulement vraie sur le papier."""
    _styled_app()
    # 70 leurres qui matchent "as7341" en PREFIXE (rang 1) devancent
    # "Adafruit AS7341", qui ne matche qu'en SOUS-CHAINE (rang 2) -- mesure
    # le 2026-08-12 : la lib en usage tombe en position 70, hors du plafond
    # de 60 cards.
    fillers = [_rec(f"AS7341 Filler{i:03d}") for i in range(70)]
    li.set_index(fillers + [_rec("Adafruit AS7341")])
    dlg = _dialog(alternatives=[])
    dlg._search.setText("as7341")
    dlg._refresh()
    assert "Adafruit AS7341" not in _card_names(dlg)
    dlg._search.setText("")
    dlg._refresh()
    assert "Adafruit AS7341" in _card_names(dlg)
    dlg.deleteLater()


def test_on_index_loaded_is_ignored_after_the_dialog_was_rejected():
    """L'IMPORTANT de la revue (2026-08-12) : `_on_index_loaded` n'avait
    aucune couverture d'execution (le `_FakeLoader` n'emet jamais `.done`).
    Simule directement l'arrivee tardive du thread apres que l'utilisateur a
    ferme la modale par Annuler -- le seul chemin qui doit court-circuiter,
    verifie via `_alive`, pose par l'override de `done()` (accept/reject
    passent tous deux par la, contrairement a `closeEvent` qu'aucun des deux
    n'atteint en PyQt6)."""
    _styled_app()
    li.set_index([_rec("Adafruit AS7341")])
    before = list(li.index())
    dlg = _dialog()
    dlg._refresh()
    cards_before = list(dlg._cards)
    dlg.reject()
    assert dlg._alive is False
    dlg._on_index_loaded([_rec("Should Not Appear")])
    assert li.index() == before
    assert dlg._cards == cards_before
    dlg.deleteLater()


def test_the_pinned_card_is_present_in_every_state():
    """Effacer son choix ne depend ni de l'index ni de la CLI : la card doit
    exister meme sans arduino-cli et meme avant le chargement de l'index."""
    _styled_app()
    li.set_index([]); li._LOADED = False
    for cfg in ("dummy.yaml", None):
        dlg = _dialog(config_file=cfg)
        assert isinstance(dlg._card_clear, lcd._LibraryCard), cfg
        # Epinglee HORS du bloc defilant : son parent est la modale, pas le
        # conteneur de la liste — c'est ce qui la garde atteignable sous 174
        # resultats.
        assert dlg._card_clear.parent() is dlg, cfg
        assert dlg._card_clear not in dlg._cards, cfg
        dlg.deleteLater()


def test_choosing_the_pinned_card_requests_a_clear_not_a_name():
    _styled_app()
    li.set_index([_rec("Adafruit AS7341")])
    dlg = _dialog()
    dlg._refresh()
    dlg._on_clear_picked()
    dlg._on_ok()
    assert dlg.clear_requested is True
    assert dlg.chosen_lib == ""
    dlg.deleteLater()


def test_cancelling_never_requests_a_clear():
    _styled_app()
    li.set_index([_rec("Adafruit AS7341")])
    dlg = _dialog()
    dlg._on_clear_picked()
    dlg.reject()
    assert dlg.clear_requested is False
    dlg.deleteLater()


def test_picking_a_library_after_the_pinned_card_cancels_the_clear():
    _styled_app()
    li.set_index([_rec("Adafruit AS7341"), _rec("DFRobot_AS7341")])
    dlg = _dialog()
    dlg._refresh()
    dlg._on_clear_picked()
    dlg._on_card_picked(dlg._cards[1].record)
    dlg._on_ok()
    assert dlg.clear_requested is False
    assert dlg.chosen_lib == "DFRobot_AS7341"
    dlg.deleteLater()


def test_the_pinned_selection_survives_narrowing_the_search():
    """L'interaction que la Task 9 n'avait pas vue : `_refresh` retombait sur
    `_current` des que `_picked` (mis a "" par `_on_clear_picked`) ne
    correspondait a aucune card VISIBLE -- la card epinglee n'est jamais dans
    `self._cards`, donc ce retour en arriere s'appliquait TOUJOURS des que la
    card epinglee etait choisie. Resultat sans le garde-fou : la card de la
    bibliotheque en usage se repeint selectionnee tandis que la card epinglee
    reste selectionnee aussi -- deux cards « cochees » a la fois.

    Le terme de recherche DOIT laisser `_current` (« Adafruit AS7341 »)
    visible -- c'est precisement elle que le retour en arriere re-selectionne
    (`_picked = self._current`). Une recherche qui l'exclut aussi (ex.
    "dfrobot") ne peut jamais faire rougir ce test, garde-fou ou pas : la
    comparaison `norm_lib_name(rec.name) == norm_lib_name(self._picked)` (avec
    `_picked` retombe sur `_current`) echoue de toute facon puisque aucune
    card visible ne s'appelle « Adafruit AS7341 ». Verifie a la main
    (2026-08-12) : retirer les deux `if not self._clear_selected:` de
    `_refresh` laissait ce test vert avec "dfrobot", et le faisait rougir
    seulement avec "adafruit" ci-dessous."""
    _styled_app()
    li.set_index([_rec("Adafruit AS7341"), _rec("DFRobot_AS7341")])
    dlg = _dialog()
    dlg._refresh()
    dlg._on_clear_picked()
    dlg._search.setText("adafruit")  # ne matche QUE _current, DFRobot exclu
    dlg._refresh()
    assert [c.record.name for c in dlg._cards] == ["Adafruit AS7341"]
    assert [c.is_selected() for c in dlg._cards] == [False]
    assert dlg._card_clear.is_selected() is True
    dlg._on_ok()
    assert dlg.clear_requested is True
    assert dlg.chosen_lib == ""
    dlg.deleteLater()


def test_down_and_up_arrows_move_focus_through_the_cards():
    """La navigation clavier de la modale (`LibChoiceDialog.keyPressEvent`,
    distincte de l'Espace de la card) n'etait testee nulle part."""
    _styled_app()
    from PyQt6.QtCore import QEvent
    from PyQt6.QtGui import QKeyEvent
    li.set_index([_rec("Adafruit AS7341"), _rec("DFRobot_AS7341")])
    dlg = _dialog()
    dlg._refresh()
    dlg.show()
    _APP.processEvents()
    dlg._search.setFocus()
    _APP.processEvents()

    def press(key):
        dlg.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, key,
                                    Qt.KeyboardModifier.NoModifier))
        _APP.processEvents()

    press(Qt.Key.Key_Down)
    assert dlg._cards[0].hasFocus()
    press(Qt.Key.Key_Down)
    assert dlg._cards[1].hasFocus()
    press(Qt.Key.Key_Up)
    assert dlg._cards[0].hasFocus()
    press(Qt.Key.Key_Up)  # pas de debordement avant la premiere
    assert dlg._cards[0].hasFocus()
    dlg.close()
    dlg.deleteLater()


TESTS = [
    test_a_card_shows_what_the_registry_declares,
    test_a_card_falls_back_to_the_paragraph_when_the_sentence_is_empty,
    test_a_card_prefers_the_sentence_over_the_paragraph_when_both_exist,
    test_a_retired_library_says_so,
    test_an_incompatible_library_says_so_only_when_the_board_is_known,
    test_a_card_is_focusable_and_selects_on_space,
    test_selection_state_is_independent_per_card,
    test_the_in_use_badge_shows_only_when_in_use,
    test_only_space_selects_not_enter_or_arrows,
    test_before_the_index_arrives_the_short_list_is_usable,
    test_once_loaded_the_prefilled_query_filters_the_index,
    test_clearing_the_field_returns_to_the_short_list,
    test_the_library_in_use_is_selected_and_badged,
    test_only_one_card_stays_selected,
    test_a_capped_result_set_says_how_many_were_dropped,
    test_no_match_says_so_with_the_query,
    test_without_a_cli_the_field_is_disabled_and_says_why,
    test_validating_the_incumbent_decides_nothing,
    test_validating_another_card_returns_its_name,
    test_narrowing_the_search_away_from_a_pick_forgets_it,
    test_narrowing_the_search_without_excluding_the_pick_keeps_it,
    test_clearing_the_field_after_a_capped_search_still_finds_the_incumbent,
    test_on_index_loaded_is_ignored_after_the_dialog_was_rejected,
    test_the_pinned_card_is_present_in_every_state,
    test_choosing_the_pinned_card_requests_a_clear_not_a_name,
    test_cancelling_never_requests_a_clear,
    test_picking_a_library_after_the_pinned_card_cancels_the_clear,
    test_the_pinned_selection_survives_narrowing_the_search,
    test_down_and_up_arrows_move_focus_through_the_cards,
]


def main():
    failed = 0
    for t in TESTS:
        try:
            t(); print(f"OK   {t.__name__}")
        except Exception as e:
            failed += 1; print(f"FAIL {t.__name__}: {e}")
    print(f"\n{len(TESTS) - failed}/{len(TESTS)} passed")
    sys.stdout.flush()
    os._exit(1 if failed else 0)


if __name__ == "__main__":
    main()
