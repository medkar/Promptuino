"""
Components view — browse every component the app knows about.

`component_index.build_index()` merges three populations (declared by the
user, curated component registry, components the app had to guess a library
for) into one list of `ComponentInfo`. This view renders that list and lets
the user search / filter it; it does not compute anything itself —
`component_index` already owns filtering (`filter_components`), this module
only renders.

Layout (idiom borrowed from `library_view.py`: debounced search + QFrame
cards in a QScrollArea):
    ┌────────────────────────────────────────────────────────────────┐
    │  Components                                                    │
    │  ┌ 🔍 Search a component… ──────────────────┐ [Describe...]    │
    │  └────────────────────────────────────────────┘                │
    │  [All] [Custom] [With a library] [Drawable]                    │
    │  ──────────────────────────────────────────────────────────── │
    │  ┌ card ─────────────────┐  ┌ card ─────────────────┐          │
    │  │ DHT22            custom│  │ Button                 │          │
    │  │ DHT sensor library    │  │ 2 pins                  │          │
    │  │ 3 pins             ✎  │  │                         │          │
    │  └────────────────────────┘  └────────────────────────┘          │
    └────────────────────────────────────────────────────────────────┘

The "declare a component" flow (form dialog) is wired in a later task: this
view only emits `declare_requested` with the card key to edit ("" to create
a brand new one).
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSignal
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QPushButton,
    QLineEdit, QFrame, QScrollArea, QSizePolicy,
)

from .theme import (
    ColorScheme, theme_manager, install_icon_hover, selection_bg,
    secondary_button_qss, input_qss, primary_button_qss, filter_pill_qss,
    icon_button_qss, perso_badge_qss
)
from .i18n import lang_manager, Strings
from . import icons as IC
from .component_index import (
    ComponentInfo, ORIGIN_CORPUS, ORIGIN_DECLARED, ORIGIN_LOOKED_UP,
    build_index, filter_components,
)

# Local list, no network involved (unlike library_view's arduino-cli search),
# so the debounce only exists to avoid re-rendering the grid on every
# keystroke — it can stay short.
SEARCH_DEBOUNCE_MS = 150

# Two columns: cards carry a name + a library line + a pin count line, a
# single column would waste the tab's width.
GRID_COLS = 2

# Corpus descriptions are full sentences; a card shows one secondary line of
# it (the whole text stays available as a tooltip). The cap is a cheap first
# cut only -- what actually fits is decided in PIXELS by `_ElidedLabel`, since
# a character count says nothing about a rendered width.
DESC_MAX_CHARS = 90


class _ElidedLabel(QLabel):
    """QLabel qui se REPLIE au lieu d'imposer sa largeur au parent.

    Un QLabel ordinaire annonce le texte entier comme largeur minimale : la
    carte ne pouvait donc pas rétrécir (mesuré : `minimumSizeHint` ==
    `sizeHint`, jusqu'à 594 px pour ~419 px de colonne disponible), et la
    grille débordait horizontalement dès que la fenêtre passait sous sa
    largeur exigée. Celui-ci accepte n'importe quelle largeur et coupe à
    l'affichage, donc les cartes suivent la fenêtre.

    Le texte complet reste en infobulle : élider ne doit pas perdre
    l'information, seulement la replier.
    """

    def __init__(self, text: str = "", parent=None):
        super().__init__(parent)
        self._full = text or ""
        # `Preferred` et non `Ignored` : la largeur SOUHAITÉE reste celle du
        # texte entier, donc rien ne bouge tant qu'il y a la place ; c'est le
        # `minimumSizeHint` nul ci-dessous qui autorise le repli quand il n'y
        # en a plus. `Ignored` ferait toujours occuper tout l'espace et
        # collerait la pastille contre le bord droit.
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Preferred)
        self._relayout()

    def setFullText(self, text: str) -> None:
        self._full = text or ""
        self._relayout()

    def fullText(self) -> str:
        return self._full

    def minimumSizeHint(self) -> QSize:
        # Largeur minimale NULLE : c'est tout l'intérêt. La hauteur reste
        # celle d'une ligne de la police courante.
        return QSize(0, super().minimumSizeHint().height())

    def sizeHint(self) -> QSize:
        """Largeur souhaitée = celle du texte ENTIER, jamais du texte coupé.

        Sans ça, une fois élidé le libellé ne demande plus que la largeur de
        ce qu'il affiche : en réélargissant la fenêtre, la mise en page ne lui
        rendrait jamais la place et le nom resterait tronqué pour toujours.
        """
        hint = super().sizeHint()
        return QSize(self.fontMetrics().horizontalAdvance(self._full),
                     hint.height())

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._relayout()

    def _relayout(self) -> None:
        width = max(0, self.width())
        elided = self.fontMetrics().elidedText(
            self._full, Qt.TextElideMode.ElideRight, width) if width else self._full
        if elided != super().text():
            super().setText(elided)

_FILTER_KEYS = ("all", "declared", "with_library", "drawable")


def _filter_label(kind: str, s: Strings) -> str:
    return {
        "all":          s.components_filter_all,
        "declared":     s.components_filter_declared,
        "with_library": s.components_filter_with_library,
        "drawable":     s.components_filter_drawable,
    }[kind]


# ─────────────────────────────────────────────────────────────────────────────
#  Filter pill (segmented control) — same visual idiom as library_view's
#  platform selector: checked = green border + text, unchecked = neutral.
# ─────────────────────────────────────────────────────────────────────────────
class _FilterButton(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(28)
        self.setAutoDefault(False)
        self.setDefault(False)
        self.apply_theme(theme_manager.current)

    def apply_theme(self, c: ColorScheme):
        # `checked` stays an explicit Python argument rather than a QSS
        # `:checked` rule: the two states are two different sheets (the
        # selected pill has no hover rule at all, it is already green), and
        # `_on_filter_clicked` re-applies the theme after every toggle. The
        # branch is passed to the helper, not lost.
        self.setStyleSheet(filter_pill_qss(c, checked=self.isChecked()))


# ─────────────────────────────────────────────────────────────────────────────
#  Component card
# ─────────────────────────────────────────────────────────────────────────────
class _ComponentCardWidget(QFrame):
    """One card: name (+ "custom" badge and edit button for a declared
    component), library line (name / "library to determine" / "no library
    needed", following the `library` axis -- a library line that just
    repeats the name is not drawn), description line when there is one,
    wiring line (pin count / "generic drawing" / "nothing to wire",
    following the `wiring` axis)."""

    edit_requested = pyqtSignal(str)        # card key
    change_lib_requested = pyqtSignal(str)  # card key

    def __init__(self, info: ComponentInfo, s: Strings, parent=None):
        super().__init__(parent)
        self._info = info
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._build(s)
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)

    def _build(self, s: Strings):
        info = self._info
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 10)
        root.setSpacing(4)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)

        # Élidé, pas fixe : « écran LCD Nokia 5110 (PCD8544) » imposait 594 px
        # à une colonne qui en offre ~419 en fenêtre étroite.
        self._lbl_name = _ElidedLabel(info.name)
        self._lbl_name.setToolTip(info.name)
        title_row.addWidget(self._lbl_name)

        self._lbl_badge = None
        if info.origin == ORIGIN_DECLARED:
            self._lbl_badge = QLabel(s.components_filter_declared)
            self._lbl_badge.setToolTip(s.components_custom_badge_tip)
            title_row.addWidget(self._lbl_badge)

        title_row.addStretch()

        # TOUS les composants sont modifiables (QA I4, 2026-08-08). Modifier
        # un composant qu'on n'a pas déclaré, c'est le REPRENDRE À SON COMPTE :
        # le formulaire s'ouvre pré-rempli avec ce que l'app sait, et
        # enregistrer en fait une entrée perso. C'est ce qui rend la
        # préférence EFFECTIVE — le déclencheur « composant déclaré » force la
        # librairie dans le contexte de génération, alors qu'une préférence
        # posée sur une fiche curée n'aurait atteint personne (le RAG passe
        # par le corpus, et la détection de part-number exclut ses puces).
        self._btn_edit = None
        if info.key:
            self._btn_edit = QPushButton()
            self._btn_edit.setToolTip(
                s.components_custom_badge_tip if info.origin == ORIGIN_DECLARED
                else s.components_adopt_tip)
            self._btn_edit.setFixedSize(26, 26)
            self._btn_edit.setCursor(Qt.CursorShape.PointingHandCursor)
            self._btn_edit.setAutoDefault(False)
            self._btn_edit.setDefault(False)
            self._btn_edit.clicked.connect(
                lambda: self.edit_requested.emit(info.key)
            )
            install_icon_hover(self._btn_edit, IC.PENCIL, 15,
                               normal_role="text_secondary")
            title_row.addWidget(self._btn_edit)

        root.addLayout(title_row)

        # The library line follows the `library` axis, not a boolean: a
        # plain LED legitimately needs `none` ("aucune bibliothèque
        # nécessaire"), a declared component with no library yet is
        # `unknown` ("lib à déterminer") -- those two used to be the same
        # silent absence.
        # The `lib == name` dedup below is a corpus-only quirk: `lib == name`
        # on 29 of the 91 corpus cards ("ArduinoJson" in bold, then
        # "ArduinoJson" again underneath) is a repeated label, so the second
        # line is dropped. A declared component has no such guarantee — the
        # Arduino ecosystem is full of libraries named exactly after the chip
        # (MPU6050, TM1637, MFRC522, Servo…), where `lib == name` is the only
        # information the card has, not a repeat of it.
        if info.library == "known":
            lib_text = info.lib
            if info.origin == ORIGIN_CORPUS and info.lib == info.name:
                lib_text = ""
        elif info.library == "unknown":
            lib_text = s.components_lib_unknown
        else:  # "none"
            lib_text = s.components_library_none
        self._lbl_lib = None
        if lib_text:
            self._lbl_lib = _ElidedLabel(lib_text)
            self._lbl_lib.setToolTip(lib_text)
            root.addWidget(self._lbl_lib)

        # The description is what tells a corpus card apart from a bare
        # pinout; carried by the descriptor and asserted by the tests since
        # task 2, it was simply never rendered. One secondary line, elided —
        # corpus descriptions run to a full sentence.
        self._lbl_desc = None
        desc = " ".join((info.description or "").split())
        if desc:
            if len(desc) > DESC_MAX_CHARS:
                desc = desc[:DESC_MAX_CHARS].rstrip() + "…"
            self._lbl_desc = _ElidedLabel(desc)
            self._lbl_desc.setToolTip(info.description)
            root.addWidget(self._lbl_desc)

        # The wiring line follows the `wiring` axis, not a boolean: `none`
        # ("rien à brancher") and `unknown` ("dessin générique") used to be
        # the same silent absence -- an EEPROM built into the board has
        # nothing to wire, that is not the same as "the app draws it as a
        # plain rectangle". `unknown` says the DRAWING is generic, never that
        # the pinout is unknown: the detector wires a DS18B20 correctly,
        # pull-up included, it simply has no dedicated footprint for it.
        if info.wiring == "known":
            pins_text = s.components_pin_count.format(n=info.pin_count)
        elif info.wiring == "unknown":
            pins_text = s.components_wiring_unknown
        else:  # "none"
            pins_text = s.components_wiring_none
        self._lbl_pins = QLabel(pins_text)
        root.addWidget(self._lbl_pins)

        # Plus de bouton « Changer de librairie » sur la carte : la librairie
        # se choisit DANS le formulaire, au même endroit pour tout le monde,
        # et le crayon ci-dessus y mène depuis les deux provenances éditables.
        # Deux chemins pour la même action, c'est un de trop — et c'était
        # celui-là qui envoyait au mauvais endroit (QA I4, 2026-08-08).
        self._btn_change_lib = None

    def apply_theme(self, c: ColorScheme):
        # Card = surface, radius 6, hover border.
        #
        # One mechanism per level, and this view is the only one of the three
        # card grids to hold that line: ComponentsView.apply_theme paints its
        # own background with the palette alone, and this card styles itself
        # with QSS alone. Do NOT take the elders as the model — both
        # library_view._LibraryCard and projects_view.ProjectCard set the
        # palette AND a stylesheet on the same widget for the same colour, and
        # both top-level views (LibraryView, ProjectsView) stylesheet
        # themselves on top of their own palette too.
        #
        # That duplication is left alone rather than aligned on this file
        # because exactly one of those sites says why it exists:
        # ProjectsView.apply_theme (comment born with the code in 02bd0aa,
        # 2026-04-20, translated FR→EN in bb44e725) claims the stylesheet
        # guarantees correct rendering from the first paint, the palette alone
        # possibly not propagating before the widget is first shown. Nothing
        # measures that claim here, so the QSS stays where it is — but it is
        # not a pattern to spread.
        self.setStyleSheet(f"""
            _ComponentCardWidget {{
                background-color: {c.surface};
                border: 1px solid {c.border};
                border-radius: 6px;
            }}
            _ComponentCardWidget:hover {{
                border: 1px solid {c.signal_ok};
            }}
        """)
        self._lbl_name.setStyleSheet(
            f"color: {c.text_primary}; font-size: 11pt; font-weight: 700;"
            "background-color: transparent;"
        )
        if self._lbl_badge is not None:
            # Recette DÉPLACÉE dans theme.py (2026-08-12) sans changer un
            # pixel : la card de la modale d'ambiguïté affiche la même
            # pastille, et deux recettes locales pour un même dessin
            # divergent — c'est la leçon du TODO #50.
            self._lbl_badge.setStyleSheet(perso_badge_qss(c))
        if self._lbl_lib is not None:
            self._lbl_lib.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 9pt;"
                "background-color: transparent;"
            )
        if self._lbl_desc is not None:
            self._lbl_desc.setStyleSheet(
                f"color: {c.text_secondary}; font-size: 9pt;"
                "background-color: transparent;"
            )
        # No `is not None` guard here, unlike the two above: the wiring line is
        # built unconditionally (the `wiring` axis always has one of its three
        # values). A guard would read as "this label is sometimes absent",
        # which stopped being true when the axis replaced the boolean.
        self._lbl_pins.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 9pt;"
            "background-color: transparent;"
        )
        if self._btn_edit is not None:
            # Icon-only button: the background tint is its ONLY hover
            # affordance (QSS cannot recolor the QIcon -- that is what the
            # companion `install_icon_hover` above is for), hence
            # `icon_button_qss` and not `variant="bare"`.
            self._btn_edit.setStyleSheet(icon_button_qss(c))
        if self._btn_change_lib is not None:
            self._btn_change_lib.setStyleSheet(
                secondary_button_qss(c, font_pt=9, padding="3px 12px"))


# ─────────────────────────────────────────────────────────────────────────────
#  Main view
# ─────────────────────────────────────────────────────────────────────────────
class ComponentsView(QWidget):
    """Search + filter + grid of every component card the app knows about."""

    declare_requested = pyqtSignal(str)   # card key to edit, "" to create
    change_lib_requested = pyqtSignal(str)  # card key of a looked-up component

    def __init__(self, parent=None):
        super().__init__(parent)
        self._query: str = ""
        self._kind: str = "all"
        self._components: list[ComponentInfo] = []

        self._build()
        self.apply_theme(theme_manager.current)
        theme_manager.changed.connect(self.apply_theme)
        lang_manager.changed.connect(self.apply_lang)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self._render)

        # ⛔ PAS de `refresh()` ici, et ce n'est pas un oubli.
        #
        # Cette grille construit UNE CARD PAR COMPOSANT du registre : mesuré
        # le 2026-08-29, 1943 objets Qt sur les 2841 de la fenêtre principale
        # — 68 % de l'arbre — pour un onglet que l'utilisateur n'a peut-être
        # jamais ouvert. Et le prix ne se payait pas qu'au démarrage : tout
        # changement de thème fait re-polir l'arbre ENTIER par Qt, y compris
        # ces widgets invisibles. Mesuré : une bascule de thème coûtait
        # ~1,7 s, dont ~1 s pour le seul `app.setStyleSheet` — un appel dont
        # le coût suit le nombre de widgets et PAS le contenu de la feuille
        # (une feuille vide coûtait pareil).
        #
        # Rien n'est perdu : `main_window._switch_tab` appelle déjà
        # `refresh()` à l'activation de l'onglet, et `showEvent` ci-dessous
        # rattrape tout chemin qui l'atteindrait autrement.
        self._rendered = False

    # ── Construction ─────────────────────────────────────────────
    def _build(self):
        s = lang_manager.current
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(12)

        self._lbl_title = QLabel(s.nav_composants)
        root.addWidget(self._lbl_title)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText(s.components_search_placeholder)
        self._search_edit.setFixedHeight(34)
        self._search_edit.setClearButtonEnabled(True)
        self._search_edit.textChanged.connect(self._on_search_text_changed)
        top_row.addWidget(self._search_edit, stretch=1)

        self._btn_declare = QPushButton(s.components_declare_button)
        self._btn_declare.setFixedHeight(34)
        self._btn_declare.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_declare.setAutoDefault(False)
        self._btn_declare.setDefault(False)
        self._btn_declare.clicked.connect(lambda: self.declare_requested.emit(""))
        top_row.addWidget(self._btn_declare)

        root.addLayout(top_row)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)
        self._filter_btns: dict[str, _FilterButton] = {}
        for kind in _FILTER_KEYS:
            btn = _FilterButton(_filter_label(kind, s))
            btn.setChecked(kind == self._kind)
            btn.clicked.connect(lambda _, k=kind: self._on_filter_clicked(k))
            filter_row.addWidget(btn)
            self._filter_btns[kind] = btn
        filter_row.addStretch()
        root.addLayout(filter_row)

        # ── Scroll area + grid of cards ──────────────────────────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._grid_host = QWidget()
        self._grid_host.setObjectName("componentsGridHost")
        host_layout = QVBoxLayout(self._grid_host)
        host_layout.setContentsMargins(0, 0, 0, 0)
        host_layout.setSpacing(10)

        self._lbl_empty = QLabel("")
        self._lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_empty.setWordWrap(True)
        self._lbl_empty.setVisible(False)
        host_layout.addWidget(self._lbl_empty)

        self._grid_layout = QGridLayout()
        self._grid_layout.setSpacing(10)
        for col in range(GRID_COLS):
            self._grid_layout.setColumnStretch(col, 1)
        host_layout.addLayout(self._grid_layout)
        host_layout.addStretch()

        self._scroll.setWidget(self._grid_host)
        root.addWidget(self._scroll, stretch=1)

    # ── Public API ───────────────────────────────────────────────
    def showEvent(self, event):
        """Premier affichage = premier rendu.

        Filet volontairement large : `_switch_tab` appelle deja `refresh()` a
        l'activation, mais se reposer sur ce seul chemin ferait dependre
        l'affichage d'un appelant. `_rendered` garantit qu'un seul des deux
        rend, jamais les deux."""
        super().showEvent(event)
        if not self._rendered:
            self.refresh()

    def refresh(self):
        """Rebuild the index (declared + corpus + wiring) and re-render.

        Passes the current UI language so wiring-only component names (the
        only population `_label`-localized inside `component_index`) follow
        it -- `component_index` itself stays Qt-free and never reads
        `lang_manager`. Called at tab activation (main_window) and after the
        declare form saves a component (wired in a later task); also fires on
        every language change since this view is connected to
        `lang_manager.changed` via `apply_lang`."""
        self._components = build_index(lang_manager.lang)
        self._rendered = True
        self._render()

    # ── Slots / interaction ──────────────────────────────────────
    def _on_search_text_changed(self, text: str):
        self._query = text.strip()
        self._search_timer.start()

    def _on_filter_clicked(self, kind: str):
        if kind == self._kind:
            # Re-click on the active filter: keep it checked (exclusive
            # group of plain QPushButtons doesn't enforce "always one on").
            self._filter_btns[kind].setChecked(True)
            return
        self._kind = kind
        c = theme_manager.current
        for k, b in self._filter_btns.items():
            b.setChecked(k == kind)
            b.apply_theme(c)
        self._render()

    # ── Rendering ────────────────────────────────────────────────
    def _clear_grid(self):
        while self._grid_layout.count():
            item = self._grid_layout.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()

    def _render(self):
        s = lang_manager.current
        self._clear_grid()
        filtered = filter_components(self._components, query=self._query,
                                     kind=self._kind)
        if not filtered:
            self._lbl_empty.setText(s.components_empty)
            self._lbl_empty.setVisible(True)
            return
        self._lbl_empty.setVisible(False)
        for i, info in enumerate(filtered):
            widget = _ComponentCardWidget(info, s)
            widget.edit_requested.connect(self.declare_requested)
            widget.change_lib_requested.connect(self.change_lib_requested)
            row, col = divmod(i, GRID_COLS)
            self._grid_layout.addWidget(widget, row, col)

    # ── i18n / theme ─────────────────────────────────────────────
    def apply_lang(self, s: Strings):
        self._lbl_title.setText(s.nav_composants)
        self._search_edit.setPlaceholderText(s.components_search_placeholder)
        self._btn_declare.setText(s.components_declare_button)
        for kind, btn in self._filter_btns.items():
            btn.setText(_filter_label(kind, s))
        # Full refresh, not just a re-render: wiring-only component *names*
        # are baked in at build_index() time (the only localized lookup among
        # the three populations), so a language switch needs a rebuild to
        # follow.
        self.refresh()

    def apply_theme(self, c: ColorScheme):
        p = self.palette()
        p.setColor(QPalette.ColorRole.Window, QColor(c.main_bg))
        self.setPalette(p)
        self.setAutoFillBackground(True)

        self._lbl_title.setStyleSheet(
            f"color: {c.text_primary}; font-size: 16pt; font-weight: 700;"
        )
        self._search_edit.setStyleSheet(input_qss(c, padding="4px 10px"))
        # Was the ONLY primary button in the app that did not turn green on
        # hover: its copy hovered to btn_primary_hover. That is precisely the
        # « les boutons ne se comportent pas tous pareil au survol » this
        # refactor exists to fix, so it takes the real helper -- with its own
        # metrics, so its size does not move.
        self._btn_declare.setStyleSheet(
            primary_button_qss(c, font_pt=9, padding="4px 16px"))
        for btn in self._filter_btns.values():
            btn.apply_theme(c)

        self._lbl_empty.setStyleSheet(
            f"color: {c.text_secondary}; font-size: 10pt; padding: 24px;"
        )

        self._scroll.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
        )
        self._grid_host.setStyleSheet(
            f"QWidget#componentsGridHost {{ background: {c.main_bg}; }}"
        )
        vp = self._scroll.viewport()
        vp_p = vp.palette()
        vp_p.setColor(QPalette.ColorRole.Window, QColor(c.main_bg))
        vp_p.setColor(QPalette.ColorRole.Base,   QColor(c.main_bg))
        vp.setPalette(vp_p)
        vp.setBackgroundRole(QPalette.ColorRole.Window)
        vp.setAutoFillBackground(True)
