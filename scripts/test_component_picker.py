"""Le picker de composants de la modale d'ambiguite : recherche + cards.

Il reunit deux moities deja testees ailleurs — le filtre pur
(`test_picker_logic.py`) et la card (`test_ambiguity_cards.py`) — et n'ajoute
qu'une chose : l'ARBITRAGE. Ce que ce fichier verrouille est donc ce que ni
l'un ni l'autre ne peut voir : l'exclusivite entre cards, la regle Q9 (rien
d'invisible n'est validable), la traduction `custom:` du crayon, et l'absence
d'orphelins apres un re-filtre.

Le harnais monte l'app comme main.py — style `windows11` + `_GreenInfoStyle` —
et non le Fusion par defaut de QT_QPA_PLATFORM=offscreen. Le curseur est
ecarte a (2000, 2000) : offscreen, `QCursor.pos()` est FIGE a (10, 10), donc
tout widget proche de l'origine se peint `:hover` en permanence.

Run : python scripts/test_component_picker.py
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

from PyQt6.QtCore import Qt, QCoreApplication, QEvent  # noqa: E402
from PyQt6.QtGui import QCursor, QKeyEvent  # noqa: E402
from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton  # noqa: E402

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

from ui.i18n import TRANSLATIONS, lang_manager  # noqa: E402
from ui.theme import theme_manager, build_app_palette  # noqa: E402
from ui.wiring.ambiguity_cards import ComponentCard  # noqa: E402
from ui.wiring.component_picker import ComponentPicker  # noqa: E402
from ui.wiring.netlist import Component, Pin  # noqa: E402


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


# ── Fixtures ──────────────────────────────────────────────────────────────

def _led_d5() -> Component:
    return Component(ref="D1", type="led",
                     pins=[Pin("A", "D5"), Pin("K", "GND")],
                     attributes={"category": "single_output",
                                 "_confidence": "low"})


def _bme280_i2c() -> Component:
    """Un composant I2C, c'est-a-dire une GRANDE famille (84 candidats).

    ⚠️ Plusieurs tests ci-dessous sondaient la LED avec << bmp180 >> ou << e >>
    pour obtenir une longue liste. Depuis le TODO #67, le picker ne propose
    plus que ce qui ABOUTIT : une LED (`single_output`) ne peut pas devenir un
    BMP180 (`i2c`) -- le moteur refuse, et il le refusait deja EN SILENCE, ce
    que ces tests prenaient pour une fonctionnalite. Le comportement qu'ils
    verifient (plafond de grille, compteurs, cards orphelines, hauteur) n'a pas
    change d'un pouce ; seule la sonde devait devenir une famille ou la longue
    liste existe vraiment."""
    return Component(ref="U1", type="bme280",
                     pins=[Pin("VCC", "5V"), Pin("GND", "GND"),
                           Pin("SDA", "A4"), Pin("SCL", "A5")],
                     attributes={"category": "i2c", "_confidence": "low"})


def _resistor() -> Component:
    """Infrastructure : explicitement NON_REPLACEABLE, rien a proposer."""
    return Component(ref="R1", type="resistor",
                     pins=[Pin("1", "D5"), Pin("2", "NET_X")],
                     attributes={})


def _picker(component=None, lang="fr") -> ComponentPicker:
    _styled_app()
    p = ComponentPicker(component if component is not None else _led_d5(),
                        lang=lang)
    # Loin de l'origine : le curseur figé a (10, 10) forcerait le `:hover`.
    p.move(800, 800)
    return p


def _dispose(w) -> None:
    """Detruire POUR DE VRAI, tout de suite.

    `deleteLater()` seul est un no-op dans un harnais sans boucle
    d'evenements : le widget reste vivant, donc abonne a
    `theme_manager.changed`, et chaque test suivant repeint tous les pickers
    des tests precedents. Mesure avant correctif : la duree par test montait
    de 45 ms a 2 042 ms le long du fichier. C'est exactement le piege que le
    code de production documente (`_clear_cards`), paye ici par le test.

    ⚠️ `processEvents()` NE SUFFIT PAS, et c'est le piege dans le piege :
    `QCoreApplication.processEvents` EXCLUT deliberement les evenements
    `DeferredDelete` — ils ne sont delivres qu'a la sortie de la boucle
    d'evenements qui les a postes, ou a la demande. Verifie ici le
    2026-08-13 : `setParent(None) + deleteLater() + processEvents()` laisse
    `sip.isdeleted(w)` FAUX, et la courbe des durees montait toujours. Seul
    `sendPostedEvents(None, DeferredDelete)` detruit vraiment."""
    w.setParent(None)
    w.deleteLater()
    _APP.processEvents()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def _visible_card_ids(p) -> list[str]:
    return p.visible_type_ids()


def _card_count(p) -> int:
    return len(p.visible_type_ids())


def _selected_ids(p) -> list[str]:
    return [t for t in p.visible_type_ids()
            if p.card_for(t) is not None and p.card_for(t).is_selected()]


def _click_card(p, type_id: str) -> None:
    """Espace sur la card : le VRAI chemin utilisateur d'une card (le meme
    que le clic, `ComponentCard` emet `picked` pour les deux)."""
    card = p.card_for(type_id)
    assert card is not None, f"aucune card pour {type_id} ({p.visible_type_ids()})"
    card.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space,
                                 Qt.KeyboardModifier.NoModifier, " "))


def _count_text(p) -> str:
    """Le libelle du compteur, lu sur le widget.

    Passe par l'attribut plutot que par un accesseur public : le contrat du
    picker est fixe par le plan, et une methode qui n'existerait que pour ce
    test l'elargirait sans qu'aucun appelant reel ne s'en serve."""
    return p._lbl_count.text()


def _groups_of(g) -> tuple:
    return (g.category, g.promotions, g.yours)


def _label_texts(w) -> list[str]:
    """Le texte des QLabel qui SE PEINDRAIENT si le picker etait affiche.

    `isVisibleTo` et non `isVisible` : le picker de ce harnais n'est jamais
    montre, donc `isVisible()` est faux partout et le filtre ne dirait rien.
    Le tri par visibilite est indispensable ici — les separateurs et le
    libelle « aucun composant » EXISTENT en permanence et ne font que
    s'afficher ou non ; les compter comme presents rendrait tout test de
    groupe vide vert pour la mauvaise raison."""
    out = []
    for lbl in w.findChildren(QLabel):
        if not lbl.isVisibleTo(w):
            continue
        out.append(lbl.fullText() if hasattr(lbl, "fullText") else lbl.text())
    return out


# ── Les cinq tests du plan ────────────────────────────────────────────────

def test_empty_field_shows_category_candidates_as_cards():
    p = _picker()
    assert p.current_type_id() == "led"          # type courant preselectionne
    assert _card_count(p) >= 8, p.visible_type_ids()
    _dispose(p)


def test_typing_reaches_the_library_but_only_what_can_be_applied():
    """La frappe franchit la frontiere de FAMILLE -- pas celle du possible.

    Avant #67 ce test s'appelait `..._crosses_category` et sondait une LED avec
    << bmp180 >>. Il passait, et il mentait : la card s'affichait, mais cliquer
    dessus ne faisait RIEN -- `apply_saved_resolution` laissait le composant en
    LED, broches inchangees. Il verifiait une promesse vide.

    Ce qu'il verifie maintenant est vrai des deux cotes : depuis un BME280 on
    atteint bien un BMP180 hors de sa famille (meme categorie, le swap
    aboutit), et on n'atteint PAS un DS18B20, que le moteur refuse."""
    p = _picker(_bme280_i2c())
    p.set_query("bmp180")
    assert "bmp180" in _visible_card_ids(p), _visible_card_ids(p)
    p.set_query("ds18b20")
    assert "ds18b20" not in _visible_card_ids(p), _visible_card_ids(p)
    _dispose(p)


def test_selection_is_exclusive_and_emits():
    p = _picker()
    got = []
    p.type_chosen.connect(got.append)
    _click_card(p, "buzzer")
    assert got == ["buzzer"], got
    assert _selected_ids(p) == ["buzzer"], _selected_ids(p)
    _dispose(p)


def test_clearing_query_restores_the_short_list():
    p = _picker()
    p.set_query("bmp")
    p.set_query("")
    assert "bmp180" not in _visible_card_ids(p), p.visible_type_ids()
    _dispose(p)


def test_selection_survives_a_filter_that_hides_it():
    """Le choix reste 'led' meme si la recherche le masque — regle heritee
    de LibChoiceDialog (Q9) : rien d'invisible ne doit etre validable, donc
    le picker DESELECTIONNE quand la card choisie disparait de l'ecran."""
    p = _picker()
    _click_card(p, "buzzer")
    p.set_query("bmp180")
    assert p.current_type_id() is None or p.current_type_id() == "bmp180"
    _dispose(p)


# ── Ce que le nom du test ci-dessus dit et que son assertion ne dit pas ────

def test_the_hidden_choice_comes_back_when_the_filter_releases_it():
    """Les deux moities de la regle Q9, ensemble.

    Le titre du test precedent dit « survives », sa docstring dit
    « DESELECTIONNE » : les deux sont vrais, mais de deux choses
    differentes. Ce qui ne doit JAMAIS etre validable, c'est un choix
    INVISIBLE — pas le souvenir de ce que l'utilisateur a clique. Effacer ce
    souvenir en plus punirait une faute de frappe : taper trois lettres puis
    les effacer rendrait le picker vierge et griserait Valider alors que
    l'utilisateur n'a rien annule.

    Donc : masque -> `current_type_id()` rend None (rien a valider) ;
    demasque -> la card se repeint selectionnee et le choix redevient
    validable.
    """
    p = _picker()
    _click_card(p, "buzzer")
    p.set_query("bmp180")
    assert p.current_type_id() is None
    p.set_query("")
    assert p.current_type_id() == "buzzer"
    assert _selected_ids(p) == ["buzzer"], _selected_ids(p)
    _dispose(p)


def test_the_picker_says_when_the_choice_becomes_invalidatable():
    """Sans ce signal, la modale ne peut pas griser Valider : le filtre
    change l'etat de resolution sans qu'aucun clic ne se produise, et
    `_update_ok_state` n'est appele que depuis les entonnoirs de choix."""
    p = _picker()
    cleared, chosen = [], []
    p.selection_cleared.connect(lambda: cleared.append(True))
    p.type_chosen.connect(chosen.append)
    _click_card(p, "buzzer")
    assert chosen == ["buzzer"] and cleared == []
    p.set_query("bmp180")             # le choix disparait de l'ecran
    assert cleared == [True], cleared
    p.set_query("")                   # ... et revient
    assert chosen == ["buzzer", "buzzer"], chosen
    _dispose(p)


# ── Preselection, exclusivite, contenu ────────────────────────────────────

def test_preselection_is_silent():
    """`select()` est un ORDRE de la modale, pas un choix de l'utilisateur.
    S'il emettait, la modale se rappellerait elle-meme a la construction
    (meme raison que `ComponentCard.set_selected`, qui n'emet rien non plus)."""
    p = _picker()
    got = []
    p.type_chosen.connect(got.append)
    p.select("buzzer")
    assert got == []
    assert p.current_type_id() == "buzzer"
    assert _selected_ids(p) == ["buzzer"], _selected_ids(p)
    _dispose(p)


def test_a_type_without_a_fiche_still_gets_a_card():
    """`module_generic` est une echappatoire legitime, pas un composant : il
    n'a AUCUNE fiche au registre. Sans la card de repli il disparaitrait
    silencieusement de la modale."""
    from ui.component_index import build_index
    assert "module_generic" not in {i.key for i in build_index("fr")}
    p = _picker()
    assert "module_generic" in p.visible_type_ids()
    card = p.card_for("module_generic")
    assert card is not None and card.info is None
    _dispose(p)


def test_a_component_declared_after_construction_gets_a_full_fiche():
    """LE flux pour lequel le picker existe : le crayon ouvre le formulaire,
    l'utilisateur decrit son composant, et il revient dans la grille.

    Les fiches sont indexees a la construction. Sans re-indexation, le
    composant que l'utilisateur VIENT de decrire s'affiche en card de REPLI —
    nom seul, ni ligne bibliotheque, ni description, ni pastille « Perso » —
    a cote de voisins complets, alors que l'app connait tout de lui.
    """
    from ui.declared_components import DeclaredComponent
    from ui.component_index import ORIGIN_DECLARED
    p = _picker()                      # construit AVANT la declaration
    dc.set_registry([DeclaredComponent(
        id="monchip", name="MonChip", headers=("monchip.h",),
        pins=(), lib="MaLib", keywords=("monchip",))])
    try:
        p.refresh_index()
        card = p.card_for("custom:monchip")
        assert card is not None, p.visible_type_ids()
        assert card.info is not None, "card de repli : fiche non indexee"
        assert card.info.origin == ORIGIN_DECLARED
        assert card.info.lib == "MaLib"
        assert lang_manager.current.components_filter_declared \
            in _label_texts(card), _label_texts(card)
        # Et sans appel explicite : une frappe suffit a rattraper l'oubli.
        p2 = _picker()
        dc.set_registry([DeclaredComponent(
            id="autre", name="Autre", headers=("autre.h",),
            pins=(), lib="", keywords=("autre",))])
        p2.set_query("autre")
        c2 = p2.card_for("custom:autre")
        assert c2 is not None and c2.info is not None, "index encore perime"
        _dispose(p2)
        _dispose(p)
    finally:
        dc.set_registry([])


def test_a_declared_id_that_collides_with_a_curated_one_stays_in_its_lane():
    """`new_entry_id` ne dedoublonne que contre les AUTRES entrees declarees,
    jamais contre le registre cure : un debutant qui nomme son composant
    « LED » produit l'id `led`, et `build_index` fait gagner le declare.

    Avec un seul index par cle, sa fiche s'affichait alors sur LES DEUX
    cards — pastille « Perso » comprise sur la LED curee, qui devenait
    introuvable. Un `custom:` ne resout que vers une fiche declaree, un id nu
    que vers une fiche curee.
    """
    from ui.declared_components import DeclaredComponent
    from ui.component_index import ORIGIN_DECLARED
    dc.set_registry([DeclaredComponent(
        id="led", name="MA LED PERSO", headers=("maled.h",),
        pins=(), lib="", keywords=("maled",))])
    try:
        s = lang_manager.current
        p = _picker()
        mine = p.card_for("custom:led")
        curated = p.card_for("led")
        assert mine is not None and curated is not None, p.visible_type_ids()
        # Sens 1 : ma fiche va bien sur MA card.
        assert mine.info is not None and mine.info.origin == ORIGIN_DECLARED
        assert s.components_filter_declared in _label_texts(mine)
        # Sens 2 : la card curee ne porte NI mon nom, NI ma pastille. Elle
        # tombe en repli (build_index ne rend plus qu'une fiche pour cette
        # cle) — un repli n'affirme rien, une usurpation si.
        assert curated.info is None or \
            curated.info.origin != ORIGIN_DECLARED, curated.info
        assert s.components_filter_declared not in _label_texts(curated)
        assert "MA LED PERSO" not in _label_texts(curated), _label_texts(curated)
        _dispose(p)
    finally:
        dc.set_registry([])


def test_the_pencil_of_a_declared_card_emits_the_prefixed_type_id():
    """LE piege de la tache 5 : `ComponentCard.edit_requested` emet la cle NUE
    (`monchip`), alors que la modale attend le type de cablage
    (`custom:monchip`) pour distinguer « modifier mon entree » de « adopter un
    composant cure ». Le picker est le seul endroit qui connait les deux."""
    from ui.declared_components import DeclaredComponent
    dc.set_registry([DeclaredComponent(
        id="monchip", name="MonChip", headers=("monchip.h",),
        pins=(), lib="", keywords=("monchip",))])
    try:
        p = _picker()
        got = []
        p.edit_requested.connect(got.append)
        assert "custom:monchip" in p.visible_type_ids(), p.visible_type_ids()
        card = p.card_for("custom:monchip")
        card.findChild(QPushButton).click()
        assert got == ["custom:monchip"], got
        # ... et un composant cure emet bien son id nu (pas de prefixe fabrique)
        got.clear()
        p.card_for("buzzer").findChild(QPushButton).click()
        assert got == ["buzzer"], got
        _dispose(p)
    finally:
        dc.set_registry([])


def test_group_separators_show_only_for_a_non_empty_group():
    s = lang_manager.current
    p = _picker()
    texts = _label_texts(p)
    # Champ vide : promotions non vides (servo, moteur...), aucun composant
    # declare (registre vide) -> un seul separateur.
    assert s.picker_group_requalify in texts, texts
    assert s.picker_group_yours not in texts, texts
    # Une recherche qui ne rend QUE des requalifications. « servo » depuis une
    # LED : l'une des cinq. (« bmp180 » ne convient plus -- #67, le picker ne
    # propose plus ce que le moteur refuse.)
    p.set_query("servo")
    texts = _label_texts(p)
    assert s.picker_group_requalify in texts, texts
    assert s.picker_group_yours not in texts, texts
    # Aucun resultat : plus aucun separateur, seulement le libelle de vide.
    p.set_query("zzzzzzz")
    texts = _label_texts(p)
    assert s.picker_group_requalify not in texts, texts
    assert s.components_empty in texts, texts
    _dispose(p)


def test_a_declared_component_gets_its_own_group_and_separator():
    from ui.declared_components import DeclaredComponent
    dc.set_registry([DeclaredComponent(
        id="monchip", name="MonChip", headers=("monchip.h",),
        pins=(), lib="", keywords=("monchip",))])
    try:
        s = lang_manager.current
        p = _picker()
        assert s.picker_group_yours in _label_texts(p)
        _dispose(p)
    finally:
        dc.set_registry([])


def test_the_count_distinguishes_the_pin_from_the_whole_library():
    """Le compteur dit COMBIEN et D'OU — les deux verifies contre une source
    independante.

    La premiere version comparait le libelle a un format de `_card_count(p)` :
    les deux `n` sortaient du meme dictionnaire, donc un compteur faux ne
    pouvait pas la faire rougir. Le nombre attendu vient maintenant de
    `visible_items`, la couche pure, qui ne sait rien des widgets.
    """
    from ui.wiring.picker_logic import visible_items
    s = lang_manager.current
    p = _picker(_bme280_i2c())
    g = visible_items(_bme280_i2c(), "", "fr")
    expected = len(g.category) + len(g.promotions) + len(g.yours)
    assert not g.crossed_filter
    assert _count_text(p) == s.picker_count_category.format(n=expected)
    p.set_query("bmp180")
    g = visible_items(_bme280_i2c(), "bmp180", "fr")
    expected = len(g.category) + len(g.promotions) + len(g.yours)
    assert g.crossed_filter
    assert _count_text(p) == s.picker_count_all.format(n=expected)
    _dispose(p)


def test_the_cap_bounds_the_grid_and_says_so():
    """Un plafond MUET se lirait « voila tout ce qui existe ».

    Sans plafond, une requete d'une lettre construisait 134 cards : 95 ms de
    construction, ~180 ms de gel percu, et une colonne de 7 959 px qui pousse
    toutes les autres sections de la modale hors de l'ecran. Meme constante et
    meme raison que `lib_choice_dialog._MAX_CARDS`.
    """
    from ui.wiring.component_picker import _MAX_CARDS
    from ui.wiring.picker_logic import visible_items
    s = lang_manager.current
    p = _picker(_bme280_i2c())
    p.set_query("e")
    total = sum(len(x) for x in _groups_of(visible_items(_bme280_i2c(), "e", "fr")))
    assert total > _MAX_CARDS, total    # sinon ce test ne teste rien
    assert _card_count(p) == _MAX_CARDS, _card_count(p)
    assert _count_text(p) == s.picker_count_capped.format(
        total=total, shown=_MAX_CARDS)
    # ... et le plafond ne s'applique QUE quand il y a de quoi deborder.
    p.set_query("bmp")
    assert _count_text(p) != s.picker_count_capped.format(
        total=3, shown=_card_count(p))
    _dispose(p)


def test_the_cap_never_eats_the_pin_candidates_nor_your_own_components():
    """Ce qu'on tronque en DERNIER, ce sont les candidats de la broche et la
    bibliotheque de l'utilisateur.

    Un plafond applique betement dans l'ordre visuel (categorie, puis
    requalifications, puis persos) ferait disparaitre en premier le composant
    que l'utilisateur a lui-meme decrit, derriere cent requalifications —
    l'inverse exact de la promesse du picker.
    """
    from ui.declared_components import DeclaredComponent
    from ui.wiring.picker_logic import visible_items
    dc.set_registry([DeclaredComponent(
        id="monchipe", name="MonChipE", headers=("monchipe.h",),
        pins=(), lib="", keywords=("monchipe",))])
    try:
        p = _picker(_bme280_i2c())
        p.set_query("e")            # deborde largement le plafond
        g = visible_items(_bme280_i2c(), "e", "fr")
        assert sum(len(x) for x in _groups_of(g)) > 60
        shown = set(p.visible_type_ids())
        assert "custom:monchipe" in shown, "le composant de l'utilisateur a saute"
        for item in g.category:
            assert item.type_id in shown, item.type_id
        _dispose(p)
    finally:
        dc.set_registry([])


def test_no_match_says_so_and_shows_nothing():
    s = lang_manager.current
    p = _picker()
    p.set_query("zzzzzzz")
    assert p.visible_type_ids() == []
    assert s.components_empty in _label_texts(p)
    _dispose(p)


def test_infrastructure_is_never_proposable_even_when_typing():
    """Une resistance n'est pas un composant a choisir. `visible_items` le
    dit deja ; le picker ne doit pas rouvrir la porte par sa recherche."""
    p = _picker(_resistor())
    assert p.visible_type_ids() == []
    assert p.current_type_id() is None
    p.set_query("led")
    assert p.visible_type_ids() == []
    _dispose(p)


# ── Pieges Qt payes ailleurs, verrouilles ici ─────────────────────────────

def test_a_refilter_leaves_no_orphan_card_behind():
    """`takeAt` + `deleteLater` laisse des widgets ORPHELINS QUI SE PEIGNENT :
    la suppression differee n'est pas executee par la boucle imbriquee d'un
    `exec()`, donc ils restent enfants, visibles, a leur geometrie de
    construction. Le picker reconstruit sa grille a CHAQUE frappe :
    `setParent(None)` AVANT `deleteLater()`, sinon la modale accumule des
    cards fantomes a chaque lettre."""
    p = _picker()
    before = len(p.findChildren(ComponentCard))
    assert before >= 8
    p.set_query("relais")       # une seule card applicable (#67)
    alive = p.findChildren(ComponentCard)
    assert len(alive) == 1, f"{len(alive)} cards enfants, 1 visible"
    _dispose(p)


def test_surplus_height_falls_below_the_cards_not_between_them():
    """Constate a l'image le 2026-08-13 : dans un parent plus haut que le
    contenu (une recherche qui ne rend que trois cards dans une modale deja
    grande), le QVBoxLayout distribuait le surplus ENTRE les groupes — le
    compteur flottait seul au milieu de 400 px de vide, les cards en bas.
    Le ressort de fin de layout est ce qui l'empeche, et il ne se voit dans
    aucune assertion de contenu."""
    from PyQt6.QtWidgets import QVBoxLayout, QWidget
    _styled_app()
    host = QWidget()
    lay = QVBoxLayout(host)
    p = ComponentPicker(_bme280_i2c(), lang="fr")
    lay.addWidget(p)
    host.move(800, 800)
    host.resize(560, 720)          # bien plus haut que 3 cards
    host.show()
    _APP.processEvents()
    p.set_query("bmp")
    _APP.processEvents()
    assert len(p.visible_type_ids()) == 3, p.visible_type_ids()
    top = min(p.card_for(t).geometry().top() for t in p.visible_type_ids())
    # Champ (~34 px) + compteur + separateur : la premiere card doit demarrer
    # dans le premier tiers, pas au milieu d'un vide reparti.
    assert top < 140, f"premiere card a y={top} dans un picker de 720 px"
    _dispose(host)


def test_the_capped_worst_case_stays_a_scrollable_height():
    """La consequence du plafond qu'aucune assertion de contenu ne voit.

    Le picker n'a deliberement PAS de zone defilante propre (la modale en a
    deja une, et deux ascenseurs imbriques se disputeraient la molette) :
    c'est donc sa HAUTEUR qui pousse les autres sections. Sans plafond, une
    requete d'une lettre le faisait mesurer 7 959 px, soit onze fois la
    fenetre — la section suivante partait hors de l'ecran.
    """
    _styled_app()
    p = ComponentPicker(_bme280_i2c(), lang="fr")
    p.move(800, 800)
    p.set_query("e")
    h = p.sizeHint().height()
    assert h < 4200, f"pire cas plafonne a {h} px"
    # Et le plafond n'ecrase pas le cas nominal : 11 cards restent 11 cards.
    p.set_query("")
    assert p.sizeHint().height() < h
    _dispose(p)


def test_enter_in_the_search_field_never_validates():
    """Piege C2 : Entree declenche le premier bouton `autoDefault` de la
    fenetre. Aucun bouton du picker ne doit l'etre — crayons compris."""
    p = _picker()
    p.set_query("")
    for btn in p.findChildren(QPushButton):
        assert not btn.autoDefault(), btn
        assert not btn.isDefault(), btn
    field = p.findChild(QLineEdit)
    assert field is not None and field.isClearButtonEnabled()
    _dispose(p)


def test_the_picker_paints_no_stylesheet_on_itself():
    """Fond au QPalette, jamais `setStyleSheet` sur soi-meme : une feuille
    posee sur un conteneur descend sur TOUS ses enfants (265 pixels rouges
    reproduits le 2026-08-12 sur une simple QFrame)."""
    p = _picker()
    assert p.styleSheet() == "", p.styleSheet()
    assert p.autoFillBackground() is True
    _dispose(p)


def test_a_theme_switch_repaints_the_picker_and_its_cards():
    from ui.theme import card_qss
    p = _picker()
    theme_manager.apply_light()
    try:
        light = theme_manager.current
        card = p.card_for("led")
        assert card.styleSheet() == card_qss(light, selected=True)
        assert p.palette().window().color().name().lower() \
            == light.surface.lower()
    finally:
        theme_manager.apply_dark()
    _dispose(p)


def test_the_five_new_keys_exist_in_all_four_languages():
    keys = ("picker_search_placeholder", "picker_count_category",
            "picker_count_all", "picker_count_capped",
            "picker_group_requalify", "picker_group_yours")
    for code, s in TRANSLATIONS.items():
        for k in keys:
            assert getattr(s, k, ""), f"{code}: cle '{k}' manquante/vide"
    # Les deux compteurs prennent bien un {n} dans les 4 langues : une
    # traduction qui l'oublie leve un KeyError a l'affichage, pas au demarrage.
    for code, s in TRANSLATIONS.items():
        for k in ("picker_count_category", "picker_count_all"):
            assert "{n}" in getattr(s, k), f"{code}: '{k}' sans {{n}}"
        capped = s.picker_count_capped
        assert "{total}" in capped and "{shown}" in capped, code


TESTS = [
    test_empty_field_shows_category_candidates_as_cards,
    test_typing_reaches_the_library_but_only_what_can_be_applied,
    test_selection_is_exclusive_and_emits,
    test_clearing_query_restores_the_short_list,
    test_selection_survives_a_filter_that_hides_it,
    test_the_hidden_choice_comes_back_when_the_filter_releases_it,
    test_the_picker_says_when_the_choice_becomes_invalidatable,
    test_preselection_is_silent,
    test_a_type_without_a_fiche_still_gets_a_card,
    test_a_component_declared_after_construction_gets_a_full_fiche,
    test_a_declared_id_that_collides_with_a_curated_one_stays_in_its_lane,
    test_the_pencil_of_a_declared_card_emits_the_prefixed_type_id,
    test_group_separators_show_only_for_a_non_empty_group,
    test_a_declared_component_gets_its_own_group_and_separator,
    test_the_count_distinguishes_the_pin_from_the_whole_library,
    test_the_cap_bounds_the_grid_and_says_so,
    test_the_cap_never_eats_the_pin_candidates_nor_your_own_components,
    test_no_match_says_so_and_shows_nothing,
    test_infrastructure_is_never_proposable_even_when_typing,
    test_a_refilter_leaves_no_orphan_card_behind,
    test_surplus_height_falls_below_the_cards_not_between_them,
    test_the_capped_worst_case_stays_a_scrollable_height,
    test_enter_in_the_search_field_never_validates,
    test_the_picker_paints_no_stylesheet_on_itself,
    test_a_theme_switch_repaints_the_picker_and_its_cards,
    test_the_five_new_keys_exist_in_all_four_languages,
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
