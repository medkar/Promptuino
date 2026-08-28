"""La card de composant de la modale d'ambiguite.

Elle est la reunion de deux widgets qui existaient deja, et n'invente ni
contenu ni style :

- ce qu'elle DIT vient de la fiche de l'onglet « Composants »
  (`components_view._ComponentCardWidget`) : nom, ligne bibliotheque, une
  ligne de description, ligne de cablage, pastille « Perso », crayon. Memes
  cles i18n, memes axes a trois etats — un composant ne doit pas se decrire
  autrement selon l'ecran qui l'affiche ;
- ce qu'elle FAIT vient de la card de bibliotheque
  (`lib_choice_dialog._LibraryCard`) : selectionnable au clic et a l'Espace,
  focus clavier, `theme.card_qss` pour le dessin. L'exclusivite n'est PAS
  ici : une card ne connait pas ses soeurs, c'est le picker qui arbitre.

Aucune regle QSS sur un type nu de widget : une feuille posee sur un
dialogue s'echappe dans ses dialogues enfants (defaut paye le 2026-08-12 sur
le formulaire de declaration). Tout passe par `ui/theme.py`.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
)

from .. import icons as IC
from ..component_index import ComponentInfo, ORIGIN_CORPUS, ORIGIN_DECLARED
# `_ElidedLabel` et le plafond de description sont IMPORTES de l'onglet, pas
# recopies : la promesse de cette card est d'afficher les memes lignes, et
# deux implementations d'un meme repli finissent par diverger. Aucun cycle —
# `components_view` ne connait pas `ui.wiring`.
from ..components_view import DESC_MAX_CHARS, _ElidedLabel
from ..i18n import Strings, lang_manager
from ..theme import (
    ColorScheme, card_qss, icon_button_qss, install_icon_hover,
    perso_badge_qss, theme_manager,
)


class ComponentCard(QFrame):
    """Une card de composant, memes lignes que l'onglet Composants,
    selectionnable comme une card de LibChoiceDialog.

    ⚠️ La card NE SUIT PAS les changements de langue. Elle lit
    `lang_manager.current` une fois, a la construction : ses libelles sont
    figes ensuite. C'est le meme contrat que la fiche de l'onglet (qui le rend
    explicite en recevant `s` en parametre) et c'est deliberé — le
    proprietaire (l'onglet, le picker) reconstruit sa grille sur
    `lang_manager.changed`, une card ne se re-traduit pas toute seule.

    ⚠️ `edit_requested` emet `ComponentInfo.key`, c'est-a-dire l'id NU
    (`monchip`). `picker_logic.PickerItem.type_id`, lui, prefixe les
    composants declares (`custom:monchip`). Qui branche le crayon sur la
    bibliotheque declaree doit traduire l'un vers l'autre, sinon la recherche
    ne trouve rien.
    """

    picked = pyqtSignal(object)          # self, au clic / Espace
    edit_requested = pyqtSignal(str)     # ComponentInfo.key (crayon)

    def __init__(self, info: ComponentInfo | None, selectable: bool = True,
                 parent=None, *, type_id: str = "", name: str = ""):
        """`info=None` = ce type n'a AUCUNE fiche : la card se reduit a son
        nom (cf. `fallback`, le seul appelant de cette forme). Le sentinel est
        l'absence de fiche elle-meme — fabriquer un `ComponentInfo` bidon
        obligerait a lui inventer un `wiring` et un `library`, deux axes dont
        chaque valeur veut dire quelque chose de precis."""
        super().__init__(parent)
        # `libCard` branche la card sur `theme.card_qss` — la MEME recette que
        # la card de bibliotheque, aucun QSS nouveau.
        self.setObjectName("libCard")
        self.info = info
        # Identite lisible quelle que soit la provenance : le picker n'a pas a
        # savoir si la card a une fiche pour en tirer sa cle ou son nom.
        self.key = info.key if info is not None else (type_id or "")
        self.name = info.name if info is not None else (name or type_id or "")
        self._selectable = bool(selectable)
        self._selected = False
        # Propriete dynamique : l'etat de selection reste lisible de
        # l'exterieur (et une future regle `[picked="true"]` de card_qss
        # serait prise en compte, `setStyleSheet` re-polissant le widget).
        # Ce qui PEINT aujourd'hui reste `card_qss(selected=...)`, exactement
        # comme `_LibraryCard`.
        self.setProperty("picked", False)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Minimum)
        if self._selectable:
            # Le clavier que la QRadioButton donnait gratuitement.
            self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            self.setCursor(Qt.CursorShape.PointingHandCursor)
        else:
            self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._lbl_badge: QLabel | None = None
        self._lbl_lib: QLabel | None = None
        self._lbl_desc: QLabel | None = None
        self._lbl_pins: QLabel | None = None
        self._btn_edit: QPushButton | None = None
        # `install_icon_hover` demande de garder son filtre en vie ; il est
        # deja parente au bouton, cette reference ne fait que le dire.
        self._icon_filter = None
        self._build(lang_manager.current)
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)

    @classmethod
    def fallback(cls, type_id: str, name: str, selectable: bool = True,
                 parent=None) -> "ComponentCard":
        """Card d'un type SANS fiche (`module_generic`, `uart_module` : des
        echappatoires legitimes, pas des composants).

        Nom seul : ces types n'ont ni bibliotheque ni brochage a annoncer, et
        en inventer un (« aucune librairie a installer », « 0 broches »)
        presenterait une ignorance comme un verdict. Le crayon reste actif —
        c'est une action, pas une affirmation.

        Aucun `ComponentInfo` n'est fabrique ici : `info=None` DIT qu'il n'y a
        pas de fiche. Une fiche bidon aurait fallu poser `wiring=...` et
        `library=...`, deux axes ou « unknown » veut dire autre chose (« le
        dessin est generique », « il faut probablement une lib ») — deux
        affirmations fausses qui voyageraient ensuite dans tout le picker.
        """
        return cls(None, selectable, parent, type_id=type_id, name=name)

    # -- construction ---------------------------------------------------
    def _build(self, s: Strings) -> None:
        info = self.info
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        declared = info is not None and info.origin == ORIGIN_DECLARED

        # Elide, pas fixe : un nom long imposerait sa largeur a la colonne de
        # la grille, comme il le faisait dans l'onglet avant `_ElidedLabel`.
        self._lbl_name = _ElidedLabel(self.name)
        self._lbl_name.setToolTip(self.name)
        title_row.addWidget(self._lbl_name)

        if declared:
            self._lbl_badge = QLabel(s.components_filter_declared)
            self._lbl_badge.setToolTip(s.components_custom_badge_tip)
            title_row.addWidget(self._lbl_badge)

        title_row.addStretch()

        # TOUS les composants sont modifiables, comme dans l'onglet (QA I4) :
        # modifier un composant qu'on n'a pas declare, c'est le REPRENDRE A
        # SON COMPTE. La card n'ouvre aucun formulaire elle-meme — elle emet,
        # le picker decide : une feuille QSS posee sur un dialogue enfant de
        # la card s'echapperait dans tout ce qu'elle contient.
        if self.key:
            self._btn_edit = QPushButton()
            self._btn_edit.setToolTip(
                s.components_custom_badge_tip if declared
                else s.components_adopt_tip)
            self._btn_edit.setFixedSize(26, 26)
            self._btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            # Entree ne doit JAMAIS declencher ce bouton : le piege des
            # modales du cablage (test_dialog_enter_key.py).
            self._btn_edit.setAutoDefault(False)
            self._btn_edit.setDefault(False)
            self._btn_edit.clicked.connect(
                lambda: self.edit_requested.emit(self.key))
            self._icon_filter = install_icon_hover(
                self._btn_edit, IC.PENCIL, 15, normal_role="text_secondary")
            title_row.addWidget(self._btn_edit)

        root.addLayout(title_row)

        if info is None:
            return

        # Ligne bibliotheque : l'axe a trois etats, jamais un booleen. Une LED
        # a legitimement besoin de `none` (« aucune librairie necessaire »),
        # un composant declare sans lib est `unknown` (« lib a determiner »).
        # Le dedoublonnage `lib == name` est un tic du CORPUS (29 de ses 91
        # fiches repetent leur nom) ; un composant declare n'a pas cette
        # garantie — l'ecosysteme Arduino est plein de libs nommees d'apres la
        # puce, ou `lib == name` est la seule information de la card.
        if info.library == "known":
            lib_text = info.lib
            if info.origin == ORIGIN_CORPUS and info.lib == info.name:
                lib_text = ""
        elif info.library == "unknown":
            lib_text = s.components_lib_unknown
        else:
            lib_text = s.components_library_none
        if lib_text:
            self._lbl_lib = _ElidedLabel(lib_text)
            self._lbl_lib.setToolTip(lib_text)
            root.addWidget(self._lbl_lib)

        desc = " ".join((info.description or "").split())
        if desc:
            if len(desc) > DESC_MAX_CHARS:
                desc = desc[:DESC_MAX_CHARS].rstrip() + "…"
            self._lbl_desc = _ElidedLabel(desc)
            self._lbl_desc.setToolTip(info.description)
            root.addWidget(self._lbl_desc)

        # Ligne de cablage : meme axe a trois etats. `unknown` dit que le
        # DESSIN est generique, jamais que le brochage est inconnu — le
        # detecteur cable un DS18B20 correctement, pull-up comprise.
        if info.wiring == "known":
            pins_text = s.components_pin_count.format(n=info.pin_count)
        elif info.wiring == "unknown":
            pins_text = s.components_wiring_unknown
        else:
            pins_text = s.components_wiring_none
        self._lbl_pins = QLabel(pins_text)
        root.addWidget(self._lbl_pins)

    # -- selection ------------------------------------------------------
    def is_selected(self) -> bool:
        return self._selected

    def set_selected(self, sel: bool) -> None:
        """Ordre du picker, pas choix de l'utilisateur : n'emet RIEN.

        Emettre ici ferait de la preselection un evenement, et le picker qui
        deselectionne ses soeurs rentrerait dans sa propre boucle.
        """
        self._selected = bool(sel)
        self.setProperty("picked", self._selected)
        self.apply_theme(theme_manager.current)

    # -- theme ----------------------------------------------------------
    def apply_theme(self, c: ColorScheme) -> None:
        self.setStyleSheet(card_qss(c, selected=self._selected))
        self._lbl_name.setStyleSheet(
            f"color: {c.text_primary}; font-size: 11pt; font-weight: 700;"
            "background-color: transparent;")
        if self._lbl_badge is not None:
            self._lbl_badge.setStyleSheet(perso_badge_qss(c))
        for lbl in (self._lbl_lib, self._lbl_desc, self._lbl_pins):
            if lbl is not None:
                lbl.setStyleSheet(
                    f"color: {c.text_secondary}; font-size: 9pt;"
                    "background-color: transparent;")
        if self._btn_edit is not None:
            # Bouton icone seule : la teinte de fond est sa SEULE affordance
            # de survol (le QSS ne peut pas recolorer un QIcon — c'est le
            # role d'`install_icon_hover` ci-dessus).
            self._btn_edit.setStyleSheet(icon_button_qss(c))

    # -- entrees --------------------------------------------------------
    def mousePressEvent(self, ev):
        if self._selectable:
            self.setFocus()
            self.picked.emit(self)
        super().mousePressEvent(ev)

    def keyPressEvent(self, ev):
        # Espace SEUL selectionne. Entree est reserve : aucun bouton de ces
        # modales n'est `default`, et valider reste un clic explicite.
        if self._selectable and ev.key() == Qt.Key.Key_Space:
            self.picked.emit(self)
            ev.accept()
            return
        super().keyPressEvent(ev)
