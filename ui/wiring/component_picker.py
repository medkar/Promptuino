"""Le picker de composants de la modale d'ambiguite : recherche + cards.

Il ne decide de rien et ne dessine rien de neuf. Il ASSEMBLE :

- ce qui est proposable vient de `picker_logic.visible_items` (module pur,
  teste seul) — champ vide : les candidats de la categorie detectee ; des
  qu'on tape : toute la bibliotheque ;
- chaque proposition est une `ambiguity_cards.ComponentCard`, c'est-a-dire la
  fiche de l'onglet « Composants », selectionnable.

Ce qu'il ajoute, et que ni l'un ni l'autre ne peut porter, c'est l'ARBITRAGE :
l'exclusivite entre cards (une card ne connait pas ses soeurs), et la regle Q9
heritee de `LibChoiceDialog` — rien d'invisible ne doit etre validable.

Aucune regle QSS sur un type nu de widget : une feuille posee sur un
conteneur s'applique a TOUS ses descendants (265 pixels rouges reproduits le
2026-08-12 sur une simple QFrame) et une feuille posee sur un dialogue
s'echappe dans ses dialogues enfants. Le champ de recherche prend
`theme.input_qss`, les cards `theme.card_qss` ; le picker lui-meme se peint au
QPalette.

⚠️ PAS de QScrollArea ici : `AmbiguityDialog` enveloppe DEJA toutes ses
sections dans la sienne (`#ambiguityScroll`, barre toujours visible). Une
seconde zone defilante imbriquee capterait la molette et afficherait deux
ascenseurs pour un seul contenu. Le picker grandit, c'est la modale qui
defile — mais sa croissance est BORNEE (`_MAX_CARDS`), sans quoi une requete
d'une lettre le ferait mesurer 7 959 px et pousserait toutes les autres
sections de la modale hors de l'ecran.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QGridLayout, QLabel, QLineEdit, QVBoxLayout, QWidget,
)

from ..declared_components import TYPE_PREFIX
from ..i18n import lang_manager
from ..theme import ColorScheme, input_qss, theme_manager
from .ambiguity_cards import ComponentCard
from .picker_logic import PickerGroups, PickerItem, visible_items

GRID_COLS = 2
"""Deux colonnes fixes, comme la grille de l'onglet « Composants »
(`components_view.GRID_COLS`). Non adaptative a la largeur : a verifier a
l'oeil en fenetre etroite ET large, comme la sienne."""

_MAX_CARDS = 60
"""Nombre de cards construites au maximum — meme constante, meme raison que
`lib_choice_dialog._MAX_CARDS`.

Le filtre rend TOUS les correspondants ; c'est l'affichage qui plafonne. Sans
plafond, une requete d'UNE lettre construit 134 des 148 entrees de la
bibliotheque : 95 ms de construction, ~180 ms de gel reel une fois comptes les
destructions differees et la premiere mise en page (351 ms a la premiere
occurrence), et une colonne de 7 959 px qui pousse toutes les autres sections
de la modale hors de l'ecran. Avec le plafond : ~45 ms, sous le budget de
50 ms que la modale de bibliotheque s'est fixe, et une hauteur bornee.

⚠️ Le cout suit le NOMBRE DE CARDS, pas le rang de la lettre tapee. La
premiere version de ce fichier affirmait qu'il « retombe a 6-8 ms des la
deuxieme lettre » : vrai des mots echantillonnes ('bmp', 'servo'), faux en
general — 'se' construit 91 ms et 'bm' 102 ms, tous deux au deuxieme
caractere. Se regler sur un echantillon est exactement ce qui a tue le filet
auto du RAG (CLAUDE.md).

Le plafond est ANNONCE (`picker_count_capped`) : un plafond muet se lirait
« voila tout ce qui existe ».
"""


class ComponentPicker(QWidget):
    """Recherche + cards groupees (categorie, requalification, persos).

    Signaux :
      - `type_chosen(type_id)` : la selection EFFECTIVE a change. Emis quand
        l'utilisateur choisit une card, et quand un choix masque par la
        recherche redevient visible (cf. `current_type_id`). PAS emis par
        `select()`, qui est un ordre de la modale, pas un choix de
        l'utilisateur — meme contrat que `ComponentCard.set_selected`.
      - `card_clicked(type_id)` : l'utilisateur a CLIQUE une card, que la
        selection change ou non. Distinct de `type_chosen`, et la difference
        n'est pas cosmetique : les cards arrivent PRE-SELECTIONNEES sur la
        deduction du detecteur, donc le cas le plus courant — « oui, c'est
        bien une LED » — ne change RIEN et n'emettait donc aucun signal. Il
        fallait choisir un autre composant puis revenir pour confirmer
        (retour utilisateur, 2026-08-29). Un clic est un clic.
      - `selection_cleared()` : la selection effective est retombee a None
        parce que le filtre a masque la card choisie. Sans lui, la modale ne
        peut pas griser Valider : l'etat de resolution change sans qu'aucun
        clic ne se produise, et `_update_ok_state` n'est appele que depuis les
        entonnoirs de choix.
      - `edit_requested(type_id)` : le crayon d'une card. ⚠️ TRADUIT : la card
        emet la cle NUE de sa fiche (`monchip`), la modale a besoin du type de
        CABLAGE (`custom:monchip`) pour distinguer « modifier mon entree » de
        « adopter un composant cure ». Le picker est le seul endroit qui
        connait les deux.

    `lang` sert aux couches PURES (`visible_items`, `build_index`), qui
    prennent un code langue. Les libelles du widget, eux, viennent du i18n
    GLOBAL comme partout ailleurs — c'est deja le contrat de `ComponentCard`,
    et deux resolutions de langue dans la meme fenetre finiraient par
    diverger. Le picker ne suit pas les changements de langue a chaud : son
    proprietaire reconstruit (`AmbiguityDialog` se rebatit sur
    `lang_manager.changed`).
    """

    type_chosen = pyqtSignal(str)
    card_clicked = pyqtSignal(str)
    selection_cleared = pyqtSignal()
    edit_requested = pyqtSignal(str)

    def __init__(self, component, lang: str, parent=None):
        super().__init__(parent)
        self._component = component
        self._lang = lang or "fr"
        self._query = ""
        # Le SOUVENIR du choix, pas la selection effective : il survit a une
        # recherche qui le masque (cf. `current_type_id`).
        self._picked: str | None = None
        self._effective: str | None = None
        self._cards: dict[str, ComponentCard] = {}
        self._declared_infos: dict = {}
        self._curated_infos: dict = {}
        self._index_fiches()
        self._build()
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        # Type courant preselectionne : le picker s'ouvre sur ce que le
        # detecteur a cru voir.
        #
        # ⚠️ « jamais vierge » n'est plus vrai depuis 2026-08-29 : la
        # modale d'ambiguite appelle `select("")` juste apres, parce que
        # sur une AMBIGUITE ce type est un defaut (toute sortie nue sort
        # en « led ») et non une deduction. Le picker garde ce
        # comportement par defaut -- c'est l'appelant qui sait s'il tient
        # une information ou une ignorance.
        self._refresh()
        self.select(getattr(component, "type", "") or "")

    # -- construction ---------------------------------------------------
    def _build(self) -> None:
        s = lang_manager.current
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        self._search = QLineEdit()
        self._search.setPlaceholderText(s.picker_search_placeholder)
        # Le ✕ vient du controle standard : rien a dessiner, rien a styler.
        self._search.setClearButtonEnabled(True)
        self._search.textChanged.connect(self._on_text_changed)
        root.addWidget(self._search)

        self._lbl_count = QLabel("")
        self._lbl_count.setWordWrap(True)
        root.addWidget(self._lbl_count)

        self._grids: dict[str, QGridLayout] = {}
        self._seps: dict[str, QLabel] = {}
        for name, sep_text in (("category", None),
                               ("promotions", s.picker_group_requalify),
                               ("yours", s.picker_group_yours)):
            if sep_text is not None:
                sep = QLabel(sep_text)
                sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
                sep.setVisible(False)
                root.addWidget(sep)
                self._seps[name] = sep
            grid = QGridLayout()
            grid.setSpacing(10)
            for col in range(GRID_COLS):
                grid.setColumnStretch(col, 1)
            root.addLayout(grid)
            self._grids[name] = grid

        self._lbl_empty = QLabel(s.components_empty)
        self._lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_empty.setWordWrap(True)
        self._lbl_empty.setVisible(False)
        root.addWidget(self._lbl_empty)
        # Le surplus de hauteur tombe ICI, jamais entre les groupes. Sans ce
        # ressort, un parent plus haut que le contenu (une recherche qui rend
        # trois cards dans une modale deja grande) ecarte les grilles les unes
        # des autres : constate a l'image le 2026-08-13, le compteur flottait
        # seul au milieu de 400 px de vide. Un ressort a une hauteur souhaitee
        # de zero : le `sizeHint` du picker ne bouge pas.
        root.addStretch(1)

    # -- API ------------------------------------------------------------
    def set_query(self, text: str) -> None:
        """Filtre, sans debounce — le plafond de `_MAX_CARDS` s'en charge.

        Ce qui coute, ce n'est pas le filtre (3 a 6 ms sur les 148 entrees de
        la bibliotheque) : c'est de CONSTRUIRE les cards, et le cout suit leur
        NOMBRE, pas le rang de la lettre tapee. Sans plafond, une requete
        d'une lettre en rendait 134 : 95 ms de construction, et environ le
        DOUBLE de gel reellement percu (~180 ms en regime, 351 ms a la
        premiere occurrence) une fois comptes les destructions differees et
        la premiere mise en page. Plafonne a 60 cards, un re-filtre complet
        tient sous les 50 ms que la modale de bibliotheque s'est fixe comme
        budget.

        Ne pas re-deduire de ce commentaire qu'une deuxieme lettre suffit a
        rendre la frappe gratuite : 'se' et 'bm' construisaient 91 et 102 ms
        avant le plafond. C'est le nombre de correspondances qui decide.
        """
        if self._search.text() != text:
            self._search.setText(text)      # declenche _on_text_changed
            return
        self._on_text_changed(text)

    def current_type_id(self) -> str | None:
        """Le type choisi, ou None si RIEN n'est validable.

        None des que le choix n'est pas a l'ecran : c'est la regle Q9. Le
        souvenir du choix, lui, survit — sinon taper trois lettres puis les
        effacer viderait le picker et grisserait Valider alors que
        l'utilisateur n'a rien annule.
        """
        return self._effective

    def select(self, type_id: str) -> None:
        """Preselection externe. N'emet RIEN (cf. docstring de la classe)."""
        self._picked = type_id or None
        self._sync_selection(notify=False)

    def visible_type_ids(self) -> list[str]:
        """Les types actuellement a l'ecran, dans l'ordre d'affichage."""
        return list(self._cards)

    def card_for(self, type_id: str) -> ComponentCard | None:
        return self._cards.get(type_id)

    def refresh_index(self) -> None:
        """Relire les fiches ET rebatir la grille.

        A appeler quand la bibliotheque de l'utilisateur a change SANS que le
        picker en soit l'auteur — typiquement apres le formulaire de
        declaration ouvert depuis un crayon. Sans ca, le composant que
        l'utilisateur vient de decrire apparait en card de REPLI (nom seul,
        ni bibliotheque, ni description, ni pastille « Perso ») a cote de ses
        voisins complets : la fiche existe, le picker ne la connait pas
        encore. `select()` ne suffit pas — il ne reconstruit rien, et un type
        absent de la grille n'a pas de card a selectionner.
        """
        self._index_fiches()
        self._refresh()

    # -- filtrage / rendu -----------------------------------------------

    def _index_fiches(self) -> None:
        """Deux index SEPARES, un par espace de noms.

        Un seul dictionnaire par cle melangeait les deux populations, et
        `build_index` fait justement gagner le DECLARE en cas de collision :
        un composant declare avec l'id `led` (un debutant qui nomme le sien
        « LED » — `new_entry_id` ne dedoublonne que contre les autres entrees
        declarees, jamais contre le registre cure) s'affichait alors sur LES
        DEUX cards, pastille « Perso » comprise, et le vrai LED devenait
        introuvable. Un `custom:` ne peut resoudre que vers une fiche
        declaree, un id nu que vers une fiche curee.

        Consequence residuelle assumee : quand un id declare masque un id
        cure, la card curee tombe en repli (nom seul). Un repli n'AFFIRME
        rien — c'est le seul comportement honnete tant que `build_index`
        n'expose qu'une population dedoublonnee.
        """
        from ..component_index import ORIGIN_DECLARED, build_index
        from ..declared_components import registry as declared_registry
        self._declared_infos = {}
        self._curated_infos = {}
        for info in build_index(self._lang):
            target = (self._declared_infos if info.origin == ORIGIN_DECLARED
                      else self._curated_infos)
            target[info.key] = info
        # Signature de la bibliotheque declaree AU MOMENT de l'indexation.
        # `DeclaredComponent` est un dataclass frozen : l'egalite est par
        # VALEUR, donc modifier une entree (une lib enfin connue, une broche
        # de plus) se voit autant qu'en ajouter une.
        self._declared_sig = tuple(declared_registry())
    def _on_text_changed(self, text: str) -> None:
        self._query = text
        self._refresh()

    def _clear_cards(self) -> None:
        for grid in self._grids.values():
            while grid.count():
                item = grid.takeAt(0)
                w = item.widget()
                if w is not None:
                    # setParent(None) AVANT deleteLater : la suppression
                    # differee n'est pas executee par la boucle imbriquee d'un
                    # `exec()`, donc un widget seulement `deleteLater()` reste
                    # enfant, VISIBLE, a sa geometrie de construction. Le
                    # picker reconstruit sa grille a chaque frappe : sans
                    # cette ligne la modale accumule une couche de cards
                    # fantomes par lettre tapee.
                    w.setParent(None)
                    w.deleteLater()
        self._cards = {}

    def _fill(self, name: str, items: list[PickerItem]) -> None:
        grid = self._grids[name]
        sep = self._seps.get(name)
        if sep is not None:
            sep.setVisible(bool(items))
        for pos, item in enumerate(items):
            card = self._make_card(item)
            self._cards[item.type_id] = card
            grid.addWidget(card, pos // GRID_COLS, pos % GRID_COLS)

    def _make_card(self, item: PickerItem) -> ComponentCard:
        # La fiche d'un composant declare est indexee sous sa cle NUE ; son
        # type de cablage, lui, porte le prefixe. Et chaque espace de noms va
        # chercher dans SON index (cf. `_index_fiches`).
        info = (self._declared_infos.get(_bare_key(item.type_id))
                if item.type_id.startswith(TYPE_PREFIX)
                else self._curated_infos.get(item.type_id))
        card = (ComponentCard(info, selectable=True, parent=self)
                if info is not None
                else ComponentCard.fallback(item.type_id, item.name,
                                            selectable=True, parent=self))
        card.picked.connect(self._on_card_picked)
        # Le crayon repart avec le TYPE, pas avec la cle de la fiche : c'est
        # le type que la modale sait router (`custom:` -> mon entree, sinon
        # adoption).
        card.edit_requested.connect(
            lambda _key, tid=item.type_id: self.edit_requested.emit(tid))
        return card

    def _refresh(self) -> None:
        # Re-indexer si la bibliotheque declaree a bouge depuis la derniere
        # fois, et SEULEMENT dans ce cas : `build_index` relit le cache de
        # lookups sur le DISQUE, ce qui n'a rien a faire dans le chemin d'une
        # frappe. La comparaison, elle, est en memoire sur une liste que
        # l'utilisateur compte sur ses doigts. Sans ce garde-fou, oublier
        # `refresh_index()` quelque part rendrait a nouveau une card de repli
        # pour un composant que l'app connait.
        from ..declared_components import registry as declared_registry
        if tuple(declared_registry()) != self._declared_sig:
            self._index_fiches()
        groups: PickerGroups = visible_items(self._component, self._query,
                                             self._lang)
        total = len(groups.category) + len(groups.promotions) + len(groups.yours)
        cat, yours, promos = _capped(groups)
        self._clear_cards()
        self._fill("category", cat)
        self._fill("promotions", promos)
        self._fill("yours", yours)

        s = lang_manager.current
        n = len(self._cards)
        self._lbl_empty.setVisible(n == 0)
        if n < total:
            text = s.picker_count_capped.format(total=total, shown=n)
        elif groups.crossed_filter:
            text = s.picker_count_all.format(n=n)
        else:
            text = s.picker_count_category.format(n=n)
        self._lbl_count.setText(text if n else "")
        self._sync_selection(notify=True)

    # -- selection ------------------------------------------------------
    def _on_card_picked(self, card: ComponentCard) -> None:
        for type_id, other in self._cards.items():
            if other is card:
                self._picked = type_id
                break
        self._sync_selection(notify=True)
        # APRES `_sync_selection`, jamais avant : celui-ci publie la selection
        # effective, et qui ecoute `card_clicked` doit pouvoir lire un etat
        # deja a jour. `_sync_selection` sort tot quand rien n'a change --
        # c'est voulu, il est appele a chaque repeinture --, d'ou ce signal
        # separe pour le clic lui-meme.
        if self._picked is not None:
            self.card_clicked.emit(self._picked)

    def _sync_selection(self, *, notify: bool) -> None:
        """Peint l'exclusivite et publie la selection EFFECTIVE.

        Une card ne connait pas ses soeurs : l'exclusivite se joue ici, et
        `set_selected` n'emet rien, donc cette boucle ne peut pas se
        rappeler elle-meme.
        """
        effective = self._picked if self._picked in self._cards else None
        for type_id, card in self._cards.items():
            card.set_selected(type_id == effective)
        if effective == self._effective:
            return
        self._effective = effective
        if not notify:
            return
        if effective is None:
            self.selection_cleared.emit()
        else:
            self.type_chosen.emit(effective)

    # -- theme ----------------------------------------------------------
    def apply_theme(self, c: ColorScheme) -> None:
        # Fond au QPalette, jamais `setStyleSheet` sur soi-meme : une feuille
        # posee ici descendrait sur les cards et leurs libelles. `surface`
        # plutot que `main_bg` : le picker vit DANS le QGroupBox d'une section
        # de la modale, qui est peint en `surface` — `main_bg` y dessinerait
        # un rectangle d'une autre teinte.
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.surface))
        self.setPalette(p)
        self.setAutoFillBackground(True)
        self._search.setStyleSheet(input_qss(c, padding="4px 10px"))
        self._lbl_count.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 9pt;"
            " background: transparent;")
        self._lbl_empty.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 10pt; padding: 16px;"
            " background: transparent;")
        for sep in self._seps.values():
            sep.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 9pt;"
                " background: transparent;")
        # Les cards ne sont PAS repeintes ici : chacune s'abonne elle-meme a
        # `theme_manager.changed` et lit `theme_manager.current` a sa
        # construction, donc celles nees apres une bascule partent deja dans
        # le bon theme. Les repeindre en plus serait un second proprietaire
        # pour le meme dessin.


def _capped(groups: PickerGroups) -> tuple[list, list, list]:
    """(categorie, tiens, requalifications) rognees a `_MAX_CARDS` au TOTAL.

    L'ordre du rognage n'est pas l'ordre d'affichage, et c'est le point : ce
    qu'on coupe en dernier, ce sont les candidats de la broche et LES
    COMPOSANTS DE L'UTILISATEUR. Un plafond applique betement dans l'ordre
    visuel ferait disparaitre en premier la bibliotheque que l'utilisateur a
    lui-meme decrite, derriere cent requalifications — exactement l'inverse
    de la promesse du picker. Le balayage de bibliotheque (`promotions`) est
    la seule liste qui puisse atteindre la centaine, donc la seule qu'on
    tronque en pratique.
    """
    budget = _MAX_CARDS
    cat = groups.category[:budget]
    budget -= len(cat)
    yours = groups.yours[:max(budget, 0)]
    budget -= len(yours)
    promos = groups.promotions[:max(budget, 0)]
    return cat, yours, promos


def _bare_key(type_id: str) -> str:
    """`custom:monchip` -> `monchip`. Le registre declare indexe ses fiches
    par id nu, le cablage les nomme avec leur prefixe."""
    return (type_id[len(TYPE_PREFIX):] if type_id.startswith(TYPE_PREFIX)
            else type_id)
